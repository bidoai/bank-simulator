"""
Capital Consumption Tracker — per-trade RWA consumption tracking.

Every time a trade is booked, we record the incremental RWA consumed:
  incremental_RWA = notional × Basel_SA_risk_weight(ticker)

Accumulates by desk and counterparty so the OMS can enforce RWA budget
gates pre-trade and dashboards can show live capital utilisation.

Note: this is a conservative additive accumulator — it does not net
positions. Real firms run SA-CCR netting, but the additive approach
gives a safe upper bound for limit purposes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import structlog

from infrastructure.risk.regulatory_capital import RegulatoryCapitalEngine

log = structlog.get_logger()

_RISK_WEIGHTS    = RegulatoryCapitalEngine.RISK_WEIGHTS
_PRODUCT_TYPE_MAP = RegulatoryCapitalEngine.PRODUCT_TYPE_MAP

# Baseline RWA from the regulatory engine (produces 13% CET1 at $45B)
_BASELINE_RWA_USD = 346_000_000_000.0   # $346B
_FIRM_CET1_USD    = 45_000_000_000.0    # $45B


def _risk_weight(ticker: str) -> float:
    product_type = _PRODUCT_TYPE_MAP.get(ticker, "equity")   # conservative default
    return _RISK_WEIGHTS.get(product_type, 1.00)


@dataclass
class _DeskState:
    desk: str
    rwa_consumed: float = 0.0
    trade_count:  int   = 0


class CapitalConsumptionTracker:
    """
    Tracks cumulative incremental RWA from booked trades.

    Public API
    ----------
    estimate_incremental_rwa(ticker, notional) → float
        Pre-trade estimate (does not record anything).
    record_trade(desk, ticker, notional, counterparty_id) → float
        Post-trade recording; returns the incremental RWA added.
    get_desk_rwa_consumed(desk) → float
    get_report() → dict
    get_live_cet1_ratio() → float
    """

    def __init__(self) -> None:
        self._by_desk: dict[str, _DeskState] = {}
        self._by_counterparty: dict[str, float] = {}
        self._total_incremental_rwa: float = 0.0

    # ── Pre-trade (no side effects) ───────────────────────────────────────────

    def estimate_incremental_rwa(self, ticker: str, notional: float) -> float:
        return abs(notional) * _risk_weight(ticker)

    # ── Post-trade recording ──────────────────────────────────────────────────

    def record_trade(
        self,
        desk: str,
        ticker: str,
        notional: float,
        counterparty_id: str | None = None,
    ) -> float:
        rw  = _risk_weight(ticker)
        rwa = abs(notional) * rw

        if desk not in self._by_desk:
            self._by_desk[desk] = _DeskState(desk=desk)
        s = self._by_desk[desk]
        s.rwa_consumed += rwa
        s.trade_count  += 1
        self._total_incremental_rwa += rwa

        if counterparty_id:
            self._by_counterparty[counterparty_id] = (
                self._by_counterparty.get(counterparty_id, 0.0) + rwa
            )

        log.debug(
            "capital_consumption.recorded",
            desk=desk, ticker=ticker,
            notional=round(notional, 0),
            incremental_rwa=round(rwa, 0),
            desk_rwa_total=round(s.rwa_consumed, 0),
        )
        return rwa

    # ── Read ──────────────────────────────────────────────────────────────────

    def get_desk_rwa_consumed(self, desk: str) -> float:
        s = self._by_desk.get(desk)
        return s.rwa_consumed if s else 0.0

    def get_total_incremental_rwa(self) -> float:
        return self._total_incremental_rwa

    def get_live_cet1_ratio(self) -> float:
        """
        Live CET1 ratio = firm CET1 / (baseline RWA + incremental trading-book RWA).
        Gives a real-time signal of how much capital headroom remains.
        """
        total_rwa = _BASELINE_RWA_USD + self._total_incremental_rwa
        return _FIRM_CET1_USD / total_rwa if total_rwa > 0 else 0.0

    def get_report(self) -> dict[str, Any]:
        from infrastructure.risk.capital_allocation import capital_allocation

        desk_rows = []
        for desk, s in self._by_desk.items():
            budget = capital_allocation.get_desk_rwa_budget(desk)
            util   = s.rwa_consumed / budget * 100.0 if budget > 0 else 0.0
            desk_rows.append({
                "desk":           desk,
                "rwa_consumed":   round(s.rwa_consumed, 2),
                "rwa_budget":     round(budget, 2),
                "utilisation_pct": round(util, 2),
                "headroom":       round(max(0.0, budget - s.rwa_consumed), 2),
                "trade_count":    s.trade_count,
            })

        return {
            "total_incremental_rwa":  round(self._total_incremental_rwa, 2),
            "baseline_rwa":           _BASELINE_RWA_USD,
            "total_rwa":              round(_BASELINE_RWA_USD + self._total_incremental_rwa, 2),
            "live_cet1_ratio":        round(self.get_live_cet1_ratio(), 6),
            "live_cet1_ratio_pct":    round(self.get_live_cet1_ratio() * 100, 4),
            "by_desk":                sorted(desk_rows, key=lambda r: -r["rwa_consumed"]),
            "by_counterparty":        {
                cp: round(rwa, 2) for cp, rwa in self._by_counterparty.items()
            },
        }


capital_consumption = CapitalConsumptionTracker()
