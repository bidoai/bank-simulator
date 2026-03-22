"""
P&L Calculator — Realised, unrealised, daily, MTD, and YTD P&L tracking.

P&L (Profit and Loss) is the heartbeat of the trading floor. Every morning
traders arrive to a P&L report. Every afternoon the risk manager checks it.
Every month the CFO reports it to the board. This class produces those numbers.

Two kinds of P&L:
- Realised P&L: locked in when a position is closed (a trade is a trade)
- Unrealised P&L: mark-to-market gain/loss on open positions (changes with prices)
  Also called "mark-to-market P&L" or "MTM P&L"

P&L explain (Greeks × market moves) is critical — if actual P&L diverges
significantly from what Greeks predict, something is wrong: either a model
error, a position mis-booking, or a market dislocation.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Optional
import structlog

log = structlog.get_logger()


@dataclass
class DailyPnL:
    """P&L record for one entity (book/desk/firm) for one trading day."""
    entity: str           # book_id, desk name, or "FIRM"
    date: date
    realised: float = 0.0
    unrealised: float = 0.0
    fees: float = 0.0     # transaction costs, financing charges
    fx_translation: float = 0.0  # P&L from FX conversion of non-USD books

    @property
    def total(self) -> float:
        return self.realised + self.unrealised + self.fees + self.fx_translation

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "date": self.date.isoformat(),
            "realised": round(self.realised, 2),
            "unrealised": round(self.unrealised, 2),
            "fees": round(self.fees, 2),
            "fx_translation": round(self.fx_translation, 2),
            "total": round(self.total, 2),
        }


@dataclass
class PnLSummary:
    """
    Aggregated P&L across time periods for a single entity.
    Mirrors how traders see P&L on their blotter: daily, WTD, MTD, YTD.
    """
    entity: str
    daily: float = 0.0
    wtd: float = 0.0    # week-to-date
    mtd: float = 0.0    # month-to-date
    ytd: float = 0.0    # year-to-date
    daily_high: float = 0.0   # best day this month
    daily_low: float = 0.0    # worst day this month
    losing_days: int = 0      # number of down days this month
    winning_days: int = 0

    @property
    def hit_rate(self) -> float:
        """% of profitable days this month."""
        total = self.winning_days + self.losing_days
        return (self.winning_days / total * 100.0) if total > 0 else 0.0

    def to_dict(self) -> dict:
        return {
            "entity": self.entity,
            "daily": round(self.daily, 2),
            "wtd": round(self.wtd, 2),
            "mtd": round(self.mtd, 2),
            "ytd": round(self.ytd, 2),
            "daily_high": round(self.daily_high, 2),
            "daily_low": round(self.daily_low, 2),
            "winning_days": self.winning_days,
            "losing_days": self.losing_days,
            "hit_rate_pct": round(self.hit_rate, 1),
        }


class PnLCalculator:
    """
    Central P&L ledger.

    Records daily P&L snapshots for books, desks, and the firm.
    Computes rolling summaries (MTD, YTD) on demand.
    Supports P&L attribution (Greeks × moves) for P&L explain.

    Usage:
        calc = PnLCalculator()

        # Record EOD P&L for a book
        calc.record_eod("EQ_BOOK_1", realised=150_000, unrealised=320_000)

        # Get current-day summary
        summary = calc.get_summary("EQ_BOOK_1")

        # P&L explain: predicted vs actual
        explain = calc.pnl_explain(
            entity="EQ_BOOK_1",
            delta_pnl=125_000,    # from Greeks × moves
            actual_pnl=138_000,   # from P&L ledger
        )
    """

    def __init__(self):
        self._ledger: dict[str, list[DailyPnL]] = {}   # entity → daily records
        self._today = date.today()

    def _get_records(self, entity: str) -> list[DailyPnL]:
        return self._ledger.setdefault(entity, [])

    # ── Writes ─────────────────────────────────────────────────────────────────

    def record_eod(
        self,
        entity: str,
        realised: float,
        unrealised: float,
        fees: float = 0.0,
        fx_translation: float = 0.0,
        as_of: Optional[date] = None,
    ) -> DailyPnL:
        """
        Record end-of-day P&L for an entity.
        Replaces any existing record for the same date.
        """
        record_date = as_of or self._today
        records = self._get_records(entity)

        # Remove existing record for same date (re-state)
        records[:] = [r for r in records if r.date != record_date]

        entry = DailyPnL(
            entity=entity,
            date=record_date,
            realised=realised,
            unrealised=unrealised,
            fees=fees,
            fx_translation=fx_translation,
        )
        records.append(entry)
        records.sort(key=lambda r: r.date)

        log.info(
            "pnl.recorded",
            entity=entity,
            date=record_date.isoformat(),
            total=entry.total,
        )
        return entry

    def record_intraday(
        self,
        entity: str,
        realised_delta: float,
        unrealised_delta: float,
    ) -> None:
        """
        Accumulate intraday P&L without creating a full EOD record.
        Used for live intraday P&L tracking.
        """
        records = self._get_records(entity)
        today_records = [r for r in records if r.date == self._today]
        if today_records:
            today_records[0].realised += realised_delta
            today_records[0].unrealised += unrealised_delta
        else:
            self.record_eod(entity, realised_delta, unrealised_delta)

    # ── Reads ──────────────────────────────────────────────────────────────────

    def get_daily(self, entity: str, as_of: Optional[date] = None) -> Optional[DailyPnL]:
        """Get the P&L record for a specific date."""
        target = as_of or self._today
        records = self._get_records(entity)
        matches = [r for r in records if r.date == target]
        return matches[0] if matches else None

    def get_summary(self, entity: str) -> PnLSummary:
        """
        Compute daily/WTD/MTD/YTD summary for an entity.
        """
        today = self._today
        records = self._get_records(entity)

        summary = PnLSummary(entity=entity)

        today_records = [r for r in records if r.date == today]
        if today_records:
            summary.daily = today_records[0].total

        # WTD: Monday to today
        monday = today - __import__('datetime').timedelta(days=today.weekday())
        wtd_records = [r for r in records if monday <= r.date <= today]
        summary.wtd = sum(r.total for r in wtd_records)

        # MTD: first of month to today
        month_start = today.replace(day=1)
        mtd_records = [r for r in records if month_start <= r.date <= today]
        summary.mtd = sum(r.total for r in mtd_records)
        if mtd_records:
            totals = [r.total for r in mtd_records]
            summary.daily_high = max(totals)
            summary.daily_low = min(totals)
            summary.winning_days = sum(1 for t in totals if t > 0)
            summary.losing_days  = sum(1 for t in totals if t < 0)

        # YTD: Jan 1 to today
        year_start = today.replace(month=1, day=1)
        ytd_records = [r for r in records if year_start <= r.date <= today]
        summary.ytd = sum(r.total for r in ytd_records)

        return summary

    def get_history(
        self,
        entity: str,
        start: Optional[date] = None,
        end: Optional[date] = None,
    ) -> list[dict]:
        """Return daily P&L history as list of dicts for charting."""
        records = self._get_records(entity)
        if start:
            records = [r for r in records if r.date >= start]
        if end:
            records = [r for r in records if r.date <= end]
        return [r.to_dict() for r in sorted(records, key=lambda r: r.date)]

    def pnl_explain(
        self,
        entity: str,
        delta_pnl: float,
        gamma_pnl: float = 0.0,
        vega_pnl: float = 0.0,
        theta_pnl: float = 0.0,
        carry_pnl: float = 0.0,
        actual_pnl: Optional[float] = None,
    ) -> dict:
        """
        P&L attribution / explain.

        Compares Greeks-predicted P&L vs actual. Unexplained P&L indicates:
        - Model error (Greeks are wrong)
        - Position mis-booking (something isn't in the system)
        - Market microstructure effects (slippage, bid-ask)
        - Higher-order effects not captured by first-order Greeks

        Rule of thumb: unexplained P&L > 10% of total warrants investigation.
        > 20% triggers a model risk escalation.
        """
        predicted = delta_pnl + gamma_pnl + vega_pnl + theta_pnl + carry_pnl
        actual = actual_pnl
        if actual is None:
            today_rec = self.get_daily(entity)
            actual = today_rec.total if today_rec else 0.0

        unexplained = actual - predicted
        unexplained_pct = (abs(unexplained) / max(abs(actual), 1.0)) * 100.0

        risk_flag = "CLEAR"
        if unexplained_pct > 20:
            risk_flag = "MODEL_RISK_ESCALATION"
        elif unexplained_pct > 10:
            risk_flag = "INVESTIGATE"

        return {
            "entity": entity,
            "predicted_pnl": round(predicted, 2),
            "actual_pnl": round(actual, 2),
            "unexplained_pnl": round(unexplained, 2),
            "unexplained_pct": round(unexplained_pct, 1),
            "attribution": {
                "delta": round(delta_pnl, 2),
                "gamma": round(gamma_pnl, 2),
                "vega":  round(vega_pnl, 2),
                "theta": round(theta_pnl, 2),
                "carry": round(carry_pnl, 2),
            },
            "risk_flag": risk_flag,
        }

    def aggregate_desks(self, desk_entities: list[str]) -> PnLSummary:
        """
        Aggregate P&L summaries from multiple books/desks.
        Used to roll up desk-level to firm-level P&L.
        """
        summaries = [self.get_summary(e) for e in desk_entities]
        agg = PnLSummary(entity="AGGREGATED")
        agg.daily = sum(s.daily for s in summaries)
        agg.wtd   = sum(s.wtd   for s in summaries)
        agg.mtd   = sum(s.mtd   for s in summaries)
        agg.ytd   = sum(s.ytd   for s in summaries)
        return agg
