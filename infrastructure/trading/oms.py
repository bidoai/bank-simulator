"""
Order Management System — the OMS is the entry point for all trade execution.

Flow per order:
  1. Get fill price from MarketDataFeed
  2. Pre-trade check (estimate VaR impact, check limit headroom)
  3. Book into PositionManager
  4. Compute Greeks via GreeksCalculator
  5. Re-run RiskService.run_snapshot() to update limits
  6. Build TradeConfirmation and add to in-memory blotter
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

import structlog
from fastapi import HTTPException

from infrastructure.risk.risk_service import risk_service
from infrastructure.trading.greeks import GreeksCalculator
from models.trade import TradeConfirmation

log = structlog.get_logger(__name__)

# Maps trading desk name → LimitManager limit key
_DESK_LIMIT_MAP: dict[str, str] = {
    "EQUITY":      "VAR_EQUITY",
    "RATES":       "VAR_RATES",
    "FX":          "VAR_FX",
    "CREDIT":      "VAR_CREDIT",
    "DERIVATIVES": "VAR_DERIV",
    "COMMODITIES": "VAR_COMM",
}

# Annualised vol assumptions by desk (mirrors RiskService)
_DESK_VOLS: dict[str, float] = {
    "EQUITY":      0.20,
    "RATES":       0.05,
    "FX":          0.08,
    "CREDIT":      0.15,
    "DERIVATIVES": 0.25,
    "COMMODITIES": 0.18,
}

# Fixed fill prices for OTC instruments not in the live feed
# (repo priced at par; structured products use representative market values)
_OTC_PRICES: dict[str, float] = {
    # Securities Finance — repo and stock-borrow at par notional
    "REPO_UST":    100.0,
    "REPO_MBS":    100.0,
    "EQUITY_LEND": 100.0,
    "PRIME_BROK":  100.0,
    # Securitized products — representative dirty prices
    "FNMA_TBA":   98.00,
    "SPEC_POOL":  98.81,
    "AUTO_ABS":   99.00,
    "CMBS_AA":    94.20,
    "CLO_AAA":    97.50,
}

# Expected desk spread (bps) used for incremental RAROC estimation
_DESK_SPREAD_BPS: dict[str, float] = {
    "EQUITY":             15.0,
    "RATES":               5.0,
    "FX":                  3.0,
    "CREDIT":             50.0,
    "DERIVATIVES":        80.0,
    "COMMODITIES":        20.0,
    "SECURITIES_FINANCE": 20.0,
    "SECURITIZED":        45.0,
}

# Representative tenor (years) for RAROC revenue annualisation
_DESK_TENOR_YEARS: dict[str, float] = {
    "EQUITY":             0.25,
    "RATES":              5.0,
    "FX":                 0.083,
    "CREDIT":             3.0,
    "DERIVATIVES":        2.0,
    "COMMODITIES":        0.5,
    "SECURITIES_FINANCE": 0.083,
    "SECURITIZED":        5.0,
}


class OrderManagementSystem:
    """
    Synchronous OMS singleton.  Async concerns (DB write, WS broadcast) are
    handled by the route handler that calls submit_order().
    """

    def __init__(self) -> None:
        self._fills: list[dict] = []
        self._feed = None   # MarketDataFeed injected in lifespan

    def set_feed(self, feed) -> None:
        self._feed = feed
        log.info("oms.feed_injected")

    # ── Pre-trade ─────────────────────────────────────────────────────────────

    def _option_fill_price(self, ticker: str, product_details: dict | None) -> float:
        """BSM mid price for a synthetic option ticker (e.g. SPY_CALL_670)."""
        import math
        parts = ticker.split("_")
        opt_idx = next((i for i, p in enumerate(parts) if p in ("CALL", "PUT")), None)
        if opt_idx is None:
            raise ValueError(f"Cannot parse option ticker: {ticker}")
        underlying = "_".join(parts[:opt_idx])
        opt_type = parts[opt_idx].lower()
        strike = float(parts[opt_idx + 1])

        uq = self._feed.get_quote(underlying) if self._feed else None
        if uq is None:
            raise ValueError(f"No market data for underlying: {underlying}")
        S = float(uq.mid)

        T = (product_details or {}).get("tenor_years", 0.25)
        r, sigma = 0.045, 0.30

        d1 = (math.log(S / strike) + (r + 0.5 * sigma ** 2) * T) / (sigma * math.sqrt(T))
        d2 = d1 - sigma * math.sqrt(T)

        def N(x):
            return 0.5 * (1.0 + math.erf(x / math.sqrt(2)))

        if opt_type == "call":
            price = S * N(d1) - strike * math.exp(-r * T) * N(d2)
        else:
            price = strike * math.exp(-r * T) * N(-d2) - S * N(-d1)

        return max(0.01, round(price, 4))

    def _pre_trade_check(
        self,
        desk: str,
        ticker: str,
        qty: float,
        price: float,
        counterparty_id: Optional[str] = None,
        override_raroc: bool = False,
    ) -> tuple[bool, str, float]:
        """
        Multi-dimensional pre-trade check:
        0. Desk suspension (P4)
        1. VaR headroom
        2. Greeks (Delta, DV01, Vega)
        3. Single-name concentration
        4. Large Exposure (counterparty CRE70)
        5. RWA budget (capital allocation gate)
        6. SecFin/Securitized notional limit (P5)
        7. RAROC gate (P6) — bypassable with override_raroc=True
        """
        from infrastructure.risk.var_calculator import VaRCalculator
        from infrastructure.trading.greeks import GreeksCalculator
        from infrastructure.risk.concentration_risk import concentration_monitor
        from infrastructure.risk.large_exposures import large_exposures_engine

        notional = abs(qty * price)
        errors = []

        # 0. ── Desk suspension check (P4) ────────────────────────────────────
        try:
            from infrastructure.risk.limit_actions import limit_action_engine
            if limit_action_engine.is_desk_suspended(desk):
                return False, (
                    f"Pre-trade REJECTED [SUSPENDED]: {desk} desk is suspended due to a RED "
                    f"limit breach. CRO approval required. "
                    f"Use POST /api/risk/suspensions/{desk}/lift to reinstate."
                ), 0.0
        except Exception as exc:
            log.warning("oms.suspension_check_skipped", error=str(exc))

        # 1. ── VaR Check ─────────────────────────────────────────────────────
        limit_name = _DESK_LIMIT_MAP.get(desk)
        est_var = 0.0
        if limit_name:
            vol = _DESK_VOLS.get(desk, 0.20)
            calc = VaRCalculator(confidence=0.99, horizon_days=1)
            var_result = calc.parametric_var(notional, vol, book_id="pre_trade")
            est_var = float(var_result.var_amount)

            try:
                lim = risk_service.limit_manager.get_limit(limit_name)
                if lim.hard_limit > 0:
                    projected_util = (abs(lim.current_value) + est_var) / lim.hard_limit * 100.0
                    if projected_util >= 100.0:
                        errors.append(f"VaR breach ({projected_util:.1f}%)")
            except KeyError:
                pass

        # 2. ── Greeks / Sensitivity Checks ───────────────────────────────────
        # Get all current prices for underlying lookup in BSM
        current_prices = {}
        if self._feed:
            current_prices = {t: float(q.mid) for t, q in self._feed.get_all_quotes().items()}
        
        incremental_greeks = GreeksCalculator.compute(ticker, qty, price, current_prices)
        
        # Check Delta (only for Equity desk)
        if desk == "EQUITY":
            try:
                lim = risk_service.limit_manager.get_limit("EQUITY_DELTA")
                inc_delta = incremental_greeks["delta"]
                # For net delta, we add. For gross we'd add abs. DEFAULT_LIMITS says "Net equity delta"
                new_delta = lim.current_value + inc_delta
                if abs(new_delta) > lim.hard_limit:
                    errors.append(f"Equity Delta breach (${abs(new_delta)/1e6:.1f}M > ${lim.hard_limit/1e6:.1f}M)")
            except KeyError:
                pass

        # Check DV01 (Firm-wide)
        if incremental_greeks["dv01"] != 0:
            try:
                lim = risk_service.limit_manager.get_limit("DV01_FIRM")
                new_dv01 = lim.current_value + incremental_greeks["dv01"]
                if abs(new_dv01) > lim.hard_limit:
                    errors.append(f"DV01 breach (${abs(new_dv01)/1e6:.1f}M > ${lim.hard_limit/1e6:.1f}M)")
            except KeyError:
                pass

        # Check Vega (Derivatives desk)
        if desk == "DERIVATIVES":
            try:
                lim = risk_service.limit_manager.get_limit("VEGA_FIRM")
                new_vega = lim.current_value + incremental_greeks["vega"]
                if abs(new_vega) > lim.hard_limit:
                    errors.append(f"Vega breach (${abs(new_vega)/1e6:.1f}M > ${lim.hard_limit/1e6:.1f}M)")
            except KeyError:
                pass

        # 3. ── Concentration Check (Single-name EQ) ──────────────────────────
        if desk == "EQUITY":
            try:
                lim_pct = risk_service.limit_manager.get_limit("SINGLE_NAME_EQ_PCT")
                # Estimate new pct: (current_name_notional + new_notional) / (total_book_notional + new_notional)
                # This is an approximation.
                all_pos = risk_service.position_manager.get_all_positions()
                eq_pos = [p for p in all_pos if p["desk"] == "EQUITY"]
                total_eq_notional = sum(abs(p["notional"]) for p in eq_pos)
                name_notional = sum(abs(p["notional"]) for p in eq_pos if p["instrument"] == ticker)
                
                projected_pct = (name_notional + notional) / (total_eq_notional + notional) * 100.0
                if projected_pct > lim_pct.hard_limit:
                    errors.append(f"Concentration breach ({ticker}: {projected_pct:.1f}% > {lim_pct.hard_limit}%)")
            except KeyError:
                pass

        # 4. ── Counterparty / Large Exposure Check ────────────────────────────
        if counterparty_id:
            from infrastructure.risk.large_exposures import TIER1_CAPITAL_USD
            # Simple check: Incremental notional + current exposure <= 25% Tier 1
            exposures = large_exposures_engine.calculate_exposures()
            cp_exp = next((e for e in exposures if e["counterparty_id"] == counterparty_id), None)
            if cp_exp:
                current_total = cp_exp["total_exposure_usd"]
                limit = cp_exp["limit_usd"]
                if (current_total + notional) > limit:
                    errors.append(f"Large Exposure breach (Cpty: {counterparty_id}, Projected ${ (current_total+notional)/1e9:.1f}B > Limit ${limit/1e9:.1f}B)")

        # 5. ── RWA Budget Check (capital allocation gate) ────────────────────
        try:
            from infrastructure.risk.capital_allocation import capital_allocation
            from infrastructure.risk.capital_consumption import capital_consumption
            incremental_rwa = capital_consumption.estimate_incremental_rwa(ticker, notional)
            rwa_budget   = capital_allocation.get_desk_rwa_budget(desk)
            rwa_consumed = capital_consumption.get_desk_rwa_consumed(desk)
            if rwa_budget > 0 and (rwa_consumed + incremental_rwa) > rwa_budget:
                errors.append(
                    f"RWA budget exhausted for {desk} desk "
                    f"(consumed ${rwa_consumed/1e9:.1f}B "
                    f"+ est ${incremental_rwa/1e9:.2f}B "
                    f"> budget ${rwa_budget/1e9:.1f}B; "
                    f"request CFO reallocation via POST /api/capital/reallocate)"
                )
        except Exception as exc:
            log.warning("oms.rwa_budget_check_skipped", error=str(exc))

        # 6. ── SecFin / Securitized notional limit (P5) ──────────────────────
        if desk in ("SECURITIES_FINANCE", "SECURITIZED"):
            limit_key = "NOTIONAL_SECFIN" if desk == "SECURITIES_FINANCE" else "NOTIONAL_SECURITIZED"
            try:
                n_lim = risk_service.limit_manager.get_limit(limit_key)
                if n_lim.hard_limit > 0 and (abs(n_lim.current_value) + notional) >= n_lim.hard_limit:
                    errors.append(
                        f"Notional limit breach for {desk}: projected "
                        f"${(abs(n_lim.current_value) + notional)/1e9:.1f}B "
                        f"> limit ${n_lim.hard_limit/1e9:.1f}B"
                    )
            except KeyError:
                pass

        # 7. ── RAROC gate (P6) ────────────────────────────────────────────────
        if not override_raroc:
            try:
                from infrastructure.treasury.raroc import (
                    EC_PARAMS, HURDLE_RATE, PD_BY_RATING, LGD_BY_PRODUCT, raroc_engine,
                )
                desk_type = desk.upper()
                ec_params = EC_PARAMS.get(desk_type, {})
                ec_pct = (ec_params.get("ec_pct_notional") or ec_params.get("ec_pct_aum") or 0.08)
                spread_bps   = _DESK_SPREAD_BPS.get(desk, 15.0)
                tenor        = _DESK_TENOR_YEARS.get(desk, 1.0)

                inc_revenue  = notional * (spread_bps / 10_000.0) * tenor
                inc_ec       = notional * ec_pct
                inc_el       = notional * PD_BY_RATING.get("A", 0.001) * LGD_BY_PRODUCT.get("default", 0.45)
                inc_ftp      = notional * 0.05 * tenor          # 5% FTP rate × tenor
                inc_net      = inc_revenue - inc_el - inc_ftp
                inc_raroc    = inc_net / inc_ec if inc_ec > 0 else 0.0

                if inc_raroc < HURDLE_RATE:
                    desk_raroc = raroc_engine.calculate_desk_raroc(desk, [], 0.0)
                    if not desk_raroc["above_hurdle"]:
                        errors.append(
                            f"RAROC gate: incremental RAROC {inc_raroc:.1%} < hurdle {HURDLE_RATE:.0%} "
                            f"and {desk} desk portfolio RAROC ({desk_raroc['raroc_pct']:.1f}%) "
                            f"is already below hurdle. Pass override_raroc=true to bypass."
                        )
            except Exception as exc:
                log.warning("oms.raroc_check_skipped", error=str(exc))

        if errors:
            return False, "REJECTED: " + " | ".join(errors), est_var

        return True, "Pre-trade OK", est_var

    # ── Order execution ────────────────────────────────────────────────────────

    def submit_order(
        self,
        desk: str,
        book_id: str,
        ticker: str,
        side: str,                      # "buy" or "sell" (normalised by route handler)
        qty: float,
        trader_id: str = "system",
        counterparty_id: Optional[str] = None,
        product_subtype: Optional[str] = None,
        product_details: Optional[dict] = None,
        override_raroc: bool = False,   # P6: bypass RAROC gate when True (requires explicit flag)
    ) -> TradeConfirmation:
        """
        Execute a market order synchronously.

        Fills at mid price from MarketDataFeed.  Raises ValueError if the
        feed is not injected or no quote is available for the ticker.
        """
        if self._feed is None:
            raise RuntimeError("MarketDataFeed not injected into OMS — call set_feed() in lifespan.")

        quote = self._feed.get_quote(ticker)
        if quote is None and ("_CALL_" in ticker or "_PUT_" in ticker):
            # Synthetic option ticker — price via BSM on underlying
            fill_price = self._option_fill_price(ticker, product_details)
        elif quote is None and ticker in _OTC_PRICES:
            # SecFin / Securitized OTC instrument — use fixed reference price
            fill_price = _OTC_PRICES[ticker]
        elif quote is None:
            raise ValueError(f"No market data for ticker: {ticker}")
        else:
            fill_price = float(quote.mid)
        signed_qty = qty if side.lower() == "buy" else -qty
        notional = abs(signed_qty * fill_price)

        # --- Pre-trade check (hard enforcement — rejected orders raise 422) ---
        approved, pre_msg, est_var = self._pre_trade_check(
            desk, ticker, signed_qty, fill_price, counterparty_id, override_raroc
        )
        if not approved:
            log.warning("oms.pre_trade_rejected", desk=desk, ticker=ticker, qty=qty, reason=pre_msg)
            raise HTTPException(status_code=422, detail=pre_msg)

        # --- Snapshot VaR before ---
        limit_name = _DESK_LIMIT_MAP.get(desk)
        var_before = 0.0
        if limit_name:
            try:
                var_before = abs(risk_service.limit_manager.get_limit(limit_name).current_value)
            except KeyError:
                pass

        # --- Book trade ---
        risk_service.position_manager.add_trade(
            desk=desk,
            book_id=book_id,
            instrument=ticker,
            qty=signed_qty,
            price=fill_price,
        )

        # --- Greeks for this incremental trade ---
        current_prices = {
            t: float(q.mid)
            for t, q in self._feed.get_all_quotes().items()
        }
        greeks = GreeksCalculator.compute(ticker, signed_qty, fill_price, current_prices)

        # --- Risk re-snapshot (updates limits) ---
        risk_service.run_snapshot()

        # --- Record RWA consumption ---
        from infrastructure.risk.capital_consumption import capital_consumption
        capital_consumption.record_trade(desk, ticker, notional, counterparty_id)

        # --- Update SecFin / Securitized notional limits after booking (P5) ---
        if desk in ("SECURITIES_FINANCE", "SECURITIZED"):
            limit_key = "NOTIONAL_SECFIN" if desk == "SECURITIES_FINANCE" else "NOTIONAL_SECURITIZED"
            try:
                positions = risk_service.position_manager.get_all_positions()
                desk_notional = sum(
                    abs(p.get("notional", abs(p.get("quantity", 0)) * p.get("avg_cost", 1.0)))
                    for p in positions if p.get("desk") == desk
                )
                risk_service.limit_manager.update(limit_key, desk_notional)
            except Exception as exc:
                log.warning("oms.secfin_notional_update_failed", error=str(exc))

        # --- Snapshot VaR after ---
        var_after = 0.0
        limit_status = "GREEN"
        limit_headroom_pct = 100.0
        if limit_name:
            try:
                lim = risk_service.limit_manager.get_limit(limit_name)
                var_after = abs(lim.current_value)
                util = abs(lim.current_value) / lim.hard_limit * 100.0 if lim.hard_limit > 0 else 0.0
                limit_headroom_pct = max(0.0, 100.0 - util)
                if util >= 100.0:
                    limit_status = "RED"
                elif util >= 90.0:
                    limit_status = "ORANGE"
                elif util >= 80.0:
                    limit_status = "YELLOW"
                else:
                    limit_status = "GREEN"
            except KeyError:
                pass

        # --- Build confirmation ---
        trade_id = str(uuid.uuid4())
        executed_at = datetime.now().astimezone()

        confirmation = TradeConfirmation(
            trade_id=trade_id,
            uti=trade_id,
            ticker=ticker,
            side=side.upper(),
            quantity=abs(qty),
            fill_price=fill_price,
            notional=notional,
            desk=desk,
            book_id=book_id,
            executed_at=executed_at,
            greeks=greeks,
            var_before=var_before,
            var_after=var_after,
            limit_headroom_pct=round(limit_headroom_pct, 1),
            limit_status=limit_status,
            pre_trade_approved=approved,
            pre_trade_message=pre_msg,
            counterparty_id=counterparty_id,
            product_subtype=product_subtype,
            product_details=product_details,
        )

        # --- Blotter entry (compact dict for fast rendering) ---
        blotter_entry = {
            "id":             trade_id[:12],
            "time":           executed_at.strftime("%H:%M:%S"),
            "book":           book_id,
            "instrument":     ticker,
            "side":           side.upper(),
            "qty":            abs(qty),
            "price":          round(fill_price, 4),
            "notional":       round(notional, 0),
            "status":         "FILLED",
            "limit_status":   limit_status,
            "product_subtype": product_subtype,
            "counterparty_id": counterparty_id,
            "product_details": product_details,
        }
        self._fills.insert(0, blotter_entry)
        if len(self._fills) > 1000:
            self._fills = self._fills[:1000]

        log.info(
            "oms.trade_filled",
            ticker=ticker, side=side, qty=qty, price=fill_price,
            desk=desk, book_id=book_id, limit_status=limit_status,
        )
        return confirmation

    def get_blotter(self, limit: int = 50) -> list[dict]:
        return self._fills[:limit]


# Module-level singleton — mirrors risk_service pattern
oms = OrderManagementSystem()
