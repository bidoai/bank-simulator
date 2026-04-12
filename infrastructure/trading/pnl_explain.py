"""
P&L Attribution Engine — decomposes daily trading P&L into Greek buckets.

Attribution formula per position:
  Delta P&L  = Σ delta_i × (ΔS_i / S_i)       [delta × fractional price move]
  Gamma P&L  = ½ × Σ gamma_i × ΔS_i²           [curvature correction, USD/pt²]
  Theta P&L  = Σ theta_i × Δt                   [time decay, Δt = 1/365]
  Vega  P&L  = Σ vega_i  × Δvol_i              [vol change assumed 1pp implied move]
  Unexplained = actual P&L − (delta + gamma + theta + vega)

For non-option positions:
  - Equities/FX: delta_pnl = qty × Δprice; all other Greeks = 0
  - Bonds: delta_pnl = DV01 × yield_move_bps (approximated from price move)
  - IRS: delta_pnl = DV01 × 1bp proxy

SOD (start-of-day) snapshot is taken at engine init and refreshed via
take_sod_snapshot(). The explain() call uses the difference between
SOD and current prices.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import structlog

from infrastructure.trading.greeks import GreeksCalculator, _BOND_DURATIONS

log = structlog.get_logger(__name__)

_EQUITY_TICKERS = frozenset({"AAPL", "MSFT", "GOOGL", "NVDA", "SPY", "CL1"})
_FX_TICKERS     = frozenset({"EURUSD", "GBPUSD"})


class PnLExplainEngine:
    """
    Decomposes daily P&L into Greek-attributed buckets per desk and firm-wide.

    Usage:
        engine.take_sod_snapshot(positions, prices)   # at start of day / session init
        result = engine.explain(positions, prices)    # at any point intraday
    """

    def __init__(self) -> None:
        self._sod_prices: dict[str, float] = {}
        self._sod_greeks: dict[str, dict] = {}   # instrument → greek dict at SOD
        self._sod_ts: Optional[str] = None

    # ------------------------------------------------------------------
    # SOD snapshot
    # ------------------------------------------------------------------

    def take_sod_snapshot(
        self,
        positions: list[dict],
        prices: dict[str, float],
    ) -> None:
        """Capture start-of-day prices and Greeks. Call once at market open."""
        self._sod_prices = dict(prices)
        self._sod_greeks = {}
        for pos in positions:
            ticker = pos.get("instrument", "")
            qty    = float(pos.get("quantity", 0.0))
            price  = float(prices.get(ticker, 0.0) or pos.get("last_price") or 0.0)
            if qty and price:
                self._sod_greeks[ticker] = GreeksCalculator.compute(ticker, qty, price, prices)
        self._sod_ts = datetime.now(timezone.utc).isoformat()
        log.info("pnl_explain.sod_snapshot", positions=len(positions), ts=self._sod_ts)

    # ------------------------------------------------------------------
    # Explain
    # ------------------------------------------------------------------

    def explain(
        self,
        positions: list[dict],
        prices: dict[str, float],
    ) -> dict:
        """
        Compute P&L attribution for all current positions.

        Returns:
        {
          "as_of": ISO timestamp,
          "sod_as_of": ISO timestamp | null,
          "portfolio": {delta_pnl, gamma_pnl, theta_pnl, vega_pnl, unexplained, total_actual_pnl},
          "by_desk": {desk: {same keys + "positions": [...]}}
        }
        """
        by_desk: dict[str, dict] = {}
        portfolio_keys = ("delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl",
                          "unexplained", "total_actual_pnl")
        port = {k: 0.0 for k in portfolio_keys}

        for pos in positions:
            ticker    = pos.get("instrument", "")
            qty       = float(pos.get("quantity", 0.0))
            desk      = pos.get("desk", "UNKNOWN")
            book_id   = pos.get("book_id", "")

            if qty == 0.0 or not ticker:
                continue

            sod_price  = self._sod_prices.get(ticker) or float(pos.get("avg_cost") or 0.0)
            eod_price  = float(prices.get(ticker) or pos.get("last_price") or sod_price)

            if sod_price == 0.0 and eod_price == 0.0:
                continue

            # Actual P&L for this position (unrealised MTM since SOD)
            actual_pnl = self._actual_pnl(pos, sod_price, eod_price, qty)

            # Attributed Greeks
            delta_pnl, gamma_pnl, theta_pnl, vega_pnl = self._attribute(
                ticker, qty, sod_price, eod_price, prices
            )

            unexplained = actual_pnl - (delta_pnl + gamma_pnl + theta_pnl + vega_pnl)

            entry = {
                "ticker":          ticker,
                "book_id":         book_id,
                "qty":             qty,
                "sod_price":       round(sod_price, 4),
                "eod_price":       round(eod_price, 4),
                "price_move":      round(eod_price - sod_price, 4),
                "delta_pnl":       round(delta_pnl, 2),
                "gamma_pnl":       round(gamma_pnl, 2),
                "theta_pnl":       round(theta_pnl, 2),
                "vega_pnl":        round(vega_pnl, 2),
                "unexplained":     round(unexplained, 2),
                "total_actual_pnl": round(actual_pnl, 2),
            }

            # Aggregate into desk bucket
            if desk not in by_desk:
                by_desk[desk] = {k: 0.0 for k in portfolio_keys}
                by_desk[desk]["positions"] = []
            by_desk[desk]["positions"].append(entry)
            for k in portfolio_keys:
                by_desk[desk][k] += entry[k]

            # Aggregate into portfolio
            for k in portfolio_keys:
                port[k] += entry[k]

        return {
            "as_of":       datetime.now(timezone.utc).isoformat(),
            "sod_as_of":   self._sod_ts,
            "portfolio":   {k: round(v, 2) for k, v in port.items()},
            "by_desk": {
                desk: {
                    **{k: round(v, 2) for k, v in data.items() if k != "positions"},
                    "positions": data["positions"],
                }
                for desk, data in by_desk.items()
            },
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _actual_pnl(
        self,
        pos: dict,
        sod_price: float,
        eod_price: float,
        qty: float,
    ) -> float:
        """
        Compute the actual MTM P&L for a position since SOD.
        Prefer the position's own realised + unrealised fields; fall back to
        qty × Δprice (works for equities/bonds/FX).
        """
        unrealised = float(pos.get("unrealised_pnl") or 0.0)
        realised   = float(pos.get("realised_pnl")   or 0.0)
        if unrealised != 0.0 or realised != 0.0:
            return unrealised + realised
        # Fallback: qty × Δprice (correct for linear instruments)
        return qty * (eod_price - sod_price)

    def _attribute(
        self,
        ticker: str,
        qty: float,
        sod_price: float,
        eod_price: float,
        prices: dict[str, float],
    ) -> tuple[float, float, float, float]:
        """Return (delta_pnl, gamma_pnl, theta_pnl, vega_pnl)."""
        dp = eod_price - sod_price  # price move

        if ticker in _BOND_DURATIONS:
            # Bond: P&L driven by DV01 × yield move
            # Δy ≈ −Δp / (D × p); DV01 is P&L per 1bp yield DECREASE,
            # so P&L = −DV01 × Δy_bps (positive Δy → price falls → loss for longs)
            dur = _BOND_DURATIONS[ticker]
            delta_yield_bps = -(dp / max(eod_price, 0.01)) / dur * 10_000  # bps, +ve = rates up
            face_value = abs(qty) * 1_000.0 * (eod_price / 100.0)
            dv01 = face_value * dur * 0.0001
            sign = 1 if qty >= 0 else -1
            delta_pnl = -dv01 * delta_yield_bps * sign  # rates up → negative for longs
            return delta_pnl, 0.0, 0.0, 0.0

        if "_CALL_" in ticker or "_PUT_" in ticker:
            return self._attribute_option(ticker, qty, sod_price, eod_price, dp, prices)

        # Equity / FX / commodity: pure delta
        delta_pnl = qty * dp
        return delta_pnl, 0.0, 0.0, 0.0

    def _attribute_option(
        self,
        ticker: str,
        qty: float,
        sod_price: float,
        eod_price: float,
        dp: float,
        prices: dict[str, float],
    ) -> tuple[float, float, float, float]:
        """Full BSM attribution for vanilla options."""
        try:
            from infrastructure.trading.greeks import _parse_option, _bsm

            underlying, opt_type, strike = _parse_option(ticker)
            S_sod = self._sod_prices.get(underlying, sod_price)
            S_eod = prices.get(underlying, eod_price)
            dS    = S_eod - S_sod

            # Greeks at SOD
            g_sod = _bsm(S_sod, strike, 0.25, 0.045, 0.30, opt_type, qty)
            delta = g_sod["delta"]
            gamma = g_sod["gamma"]
            theta = g_sod["theta"]
            vega  = g_sod["vega"]

            delta_pnl = delta * dS
            gamma_pnl = 0.5 * gamma * dS ** 2
            theta_pnl = theta * (1.0 / 365.0)
            # Assume 0 vol move in absence of vol surface data
            vega_pnl  = 0.0

            return delta_pnl, gamma_pnl, theta_pnl, vega_pnl
        except Exception:
            # Fallback to delta-only
            delta_pnl = qty * dp
            return delta_pnl, 0.0, 0.0, 0.0


# Module-level singleton
pnl_explain_engine = PnLExplainEngine()
