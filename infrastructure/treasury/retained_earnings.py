"""
Retained Earnings Ledger — Apex Global Bank.

SQLite-backed ledger of period net income, dividends, and OCI.
Cumulative retained earnings flow into the dynamic CET1 calculation
in RegulatoryCapitalEngine.

Pre-seeded with 4 historical quarters of representative earnings
consistent with the JPMorgan-scale balance sheet.
"""
from __future__ import annotations

from datetime import datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_RETAINED_EARNINGS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS retained_earnings (
    period                      TEXT PRIMARY KEY,  -- e.g. "2025-Q1"
    net_income_usd              REAL NOT NULL,
    dividends_usd               REAL NOT NULL DEFAULT 0.0,
    other_comprehensive_income  REAL NOT NULL DEFAULT 0.0,
    cumulative_retained_earnings REAL NOT NULL,
    recorded_at                 TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_re_period ON retained_earnings(period DESC);
"""

# Seed: 4 historical quarters — consistent with ~$14B annual net income
_SEED_PERIODS = [
    ("2025-Q1", 3_500_000_000.0, 1_200_000_000.0,  400_000_000.0),
    ("2025-Q2", 3_700_000_000.0, 1_200_000_000.0, -150_000_000.0),
    ("2025-Q3", 3_400_000_000.0, 1_200_000_000.0,  200_000_000.0),
    ("2025-Q4", 3_600_000_000.0, 1_200_000_000.0,  100_000_000.0),
]


class RetainedEarningsLedger:
    """Period-by-period retained earnings tracker."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def _connect(self):
        return open_db(DB_RETAINED_EARNINGS)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM retained_earnings").fetchone()[0]
        if count > 0:
            return
        cumulative = 0.0
        now = _now()
        for period, net, div, oci in _SEED_PERIODS:
            cumulative += net - div + oci
            conn.execute(
                "INSERT INTO retained_earnings "
                "(period, net_income_usd, dividends_usd, other_comprehensive_income, "
                "cumulative_retained_earnings, recorded_at) VALUES (?,?,?,?,?,?)",
                (period, net, div, oci, cumulative, now),
            )
        conn.commit()
        log.info("retained_earnings.seeded", periods=len(_SEED_PERIODS), cumulative=cumulative)

    def accrue_period(
        self,
        period: str,
        net_income_usd: float,
        dividends_usd: float = 0.0,
        other_comprehensive_income: float = 0.0,
    ) -> dict[str, Any]:
        """Record a period's net income contribution and recompute cumulative RE."""
        previous = self.get_cumulative()
        new_cumulative = previous + net_income_usd - dividends_usd + other_comprehensive_income
        now = _now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO retained_earnings "
                    "(period, net_income_usd, dividends_usd, other_comprehensive_income, "
                    "cumulative_retained_earnings, recorded_at) VALUES (?,?,?,?,?,?)",
                    (period, net_income_usd, dividends_usd, other_comprehensive_income, new_cumulative, now),
                )
                conn.commit()
        log.info("retained_earnings.accrued", period=period, net_income=net_income_usd, cumulative=new_cumulative)
        return {"period": period, "net_income_usd": net_income_usd, "cumulative_retained_earnings": new_cumulative}

    def get_cumulative(self) -> float:
        """Return the most recent cumulative retained earnings balance."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT cumulative_retained_earnings FROM retained_earnings ORDER BY period DESC LIMIT 1"
            ).fetchone()
        return float(row[0]) if row else 0.0

    def get_history(self, limit: int = 20) -> list[dict[str, Any]]:
        """Return period history most-recent-first."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM retained_earnings ORDER BY period DESC LIMIT ?", (limit,)
            ).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self) -> dict[str, Any]:
        """Summary: cumulative RE, latest period details, running totals."""
        history = self.get_history(limit=8)
        if not history:
            return {"cumulative_retained_earnings": 0.0, "periods": []}
        latest = history[0]
        return {
            "cumulative_retained_earnings": latest["cumulative_retained_earnings"],
            "latest_period":                latest["period"],
            "latest_net_income_usd":        latest["net_income_usd"],
            "latest_dividends_usd":         latest["dividends_usd"],
            "total_net_income_usd":         sum(p["net_income_usd"] for p in history),
            "total_dividends_usd":          sum(p["dividends_usd"] for p in history),
            "periods":                      history,
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


retained_earnings_ledger = RetainedEarningsLedger()
