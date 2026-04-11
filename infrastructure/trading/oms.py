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

    def _pre_trade_check(
        self, desk: str, qty: float, price: float
    ) -> tuple[bool, str, float]:
        """
        Estimate incremental VaR using parametric method and compare against
        remaining limit headroom.
        Returns (approved, message, estimated_var_impact).
        """
        from infrastructure.risk.var_calculator import VaRCalculator

        limit_name = _DESK_LIMIT_MAP.get(desk)
        if not limit_name:
            return True, "No VaR limit configured for this desk.", 0.0

        vol = _DESK_VOLS.get(desk, 0.20)
        notional = abs(qty * price)

        calc = VaRCalculator(confidence=0.99, horizon_days=1)
        var_result = calc.parametric_var(notional, vol, book_id="pre_trade")
        est_var = float(var_result.var_amount)

        try:
            lim = risk_service.limit_manager.get_limit(limit_name)
            current = abs(lim.current_value)
            if lim.hard_limit <= 0:
                return True, f"Limit {limit_name} has no hard limit configured.", est_var
            projected_util = (current + est_var) / lim.hard_limit * 100.0
        except KeyError:
            return True, f"Limit {limit_name} not found; proceeding.", est_var

        if projected_util >= 100.0:
            msg = (
                f"Pre-trade REJECTED: projected {desk} VaR utilisation "
                f"{projected_util:.1f}% would breach 100% limit "
                f"(current ${current/1e6:.1f}M + est ${est_var/1e6:.1f}M > "
                f"limit ${lim.hard_limit/1e6:.1f}M)."
            )
            return False, msg, est_var

        msg = (
            f"Pre-trade OK. Projected {desk} VaR utilisation: "
            f"{projected_util:.1f}% of limit."
        )
        return True, msg, est_var

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
    ) -> TradeConfirmation:
        """
        Execute a market order synchronously.

        Fills at mid price from MarketDataFeed.  Raises ValueError if the
        feed is not injected or no quote is available for the ticker.
        """
        if self._feed is None:
            raise RuntimeError("MarketDataFeed not injected into OMS — call set_feed() in lifespan.")

        quote = self._feed.get_quote(ticker)
        if quote is None:
            raise ValueError(f"No market data for ticker: {ticker}")

        fill_price = float(quote.mid)
        signed_qty = qty if side.lower() == "buy" else -qty
        notional = abs(signed_qty * fill_price)

        # --- Pre-trade check (hard enforcement — rejected orders raise 422) ---
        approved, pre_msg, est_var = self._pre_trade_check(desk, signed_qty, fill_price)
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
        executed_at = datetime.now(timezone.utc)

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
