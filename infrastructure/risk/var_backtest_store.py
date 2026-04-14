"""
VaR Backtesting History Store — SQLite-backed daily VaR vs realised P&L.

Traffic-light zones (Basel 250-day window):
  Green  : 0–4 exceptions  → k = 3.0
  Yellow : 5–9 exceptions  → k = 3.4 – 3.8 (interpolated)
  Red    : 10+ exceptions  → k = 4.0
"""
from __future__ import annotations

import random
import sqlite3
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "var_backtest.db"

_DDL = """
CREATE TABLE IF NOT EXISTS var_backtest (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_date    TEXT    NOT NULL UNIQUE,
    var_99        REAL    NOT NULL,
    var_95        REAL    NOT NULL,
    realized_pnl  REAL    NOT NULL,
    exception_99  INTEGER NOT NULL DEFAULT 0,
    exception_95  INTEGER NOT NULL DEFAULT 0,
    desk          TEXT    NOT NULL DEFAULT 'FIRM',
    created_at    TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_backtest_date ON var_backtest(trade_date DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_desk ON var_backtest(desk, trade_date DESC);
"""

# Yellow zone k multipliers (exceptions 5–9 interpolated linearly 3.4→3.8)
_YELLOW_K = {5: 3.40, 6: 3.50, 7: 3.65, 8: 3.75, 9: 3.85}


def _is_weekday(d: date) -> bool:
    return d.weekday() < 5


def _trading_days_ending(end: date, n: int) -> list[date]:
    """Return last n trading days up to and including end."""
    days: list[date] = []
    d = end
    while len(days) < n:
        if _is_weekday(d):
            days.append(d)
        d -= timedelta(days=1)
    return list(reversed(days))


def _seed_data(today: date) -> list[dict[str, Any]]:
    """
    Generate 252 trading days of deterministic backtesting history.
    Firm-level 99% VaR mean $85M std $12M; P&L mean $8M std $75M.
    Ensures approximately 2–3 exceptions in the 250-day Basel window.
    """
    random.seed(42)

    days = _trading_days_ending(today, 252)
    records: list[dict[str, Any]] = []

    # Pre-compute which days will be exceptions (exactly 3 in last 250)
    exception_indices: set[int] = {20, 95, 180}

    for i, d in enumerate(days):
        var_99 = max(50.0, random.gauss(85.0, 12.0))
        var_95 = var_99 * 0.72  # 95% VaR is ~72% of 99% VaR (normal dist approx)

        if i in exception_indices:
            # Force a loss that exceeds VaR
            realized_pnl = -(var_99 * random.uniform(1.05, 1.30))
        else:
            realized_pnl = random.gauss(8.0, 75.0)
            # Ensure it does NOT exceed VaR for non-exception days (probabilistic fix)
            # Only clamp if it would accidentally be an exception
            if abs(realized_pnl) > var_99 and realized_pnl < 0:
                realized_pnl = -var_99 * random.uniform(0.70, 0.95)

        exc_99 = 1 if realized_pnl < -var_99 else 0
        exc_95 = 1 if realized_pnl < -var_95 else 0

        records.append({
            "trade_date": d.isoformat(),
            "var_99": round(var_99, 4),
            "var_95": round(var_95, 4),
            "realized_pnl": round(realized_pnl, 4),
            "exception_99": exc_99,
            "exception_95": exc_95,
            "desk": "FIRM",
            "created_at": f"{d.isoformat()}T16:00:00",
        })

    return records


class VaRBacktestStore:
    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _DB_PATH

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create tables and seed historical data (idempotent)."""
        with self._connect() as conn:
            conn.executescript(_DDL)
            # Seed only if table is empty
            count = conn.execute("SELECT COUNT(*) FROM var_backtest").fetchone()[0]
            if count == 0:
                today = date(2026, 4, 3)
                records = _seed_data(today)
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO var_backtest
                      (trade_date, var_99, var_95, realized_pnl, exception_99, exception_95, desk, created_at)
                    VALUES
                      (:trade_date, :var_99, :var_95, :realized_pnl, :exception_99, :exception_95, :desk, :created_at)
                    """,
                    records,
                )
                log.info("var_backtest_store.seeded", rows=len(records))
            else:
                log.info("var_backtest_store.already_seeded", existing_rows=count)

    def add_observation(
        self,
        trade_date: str,
        var_99: float,
        var_95: float,
        realized_pnl: float,
        desk: str = "FIRM",
    ) -> None:
        exc_99 = 1 if realized_pnl < -var_99 else 0
        exc_95 = 1 if realized_pnl < -var_95 else 0
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO var_backtest
                  (trade_date, var_99, var_95, realized_pnl, exception_99, exception_95, desk, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, datetime('now'))
                """,
                (trade_date, var_99, var_95, realized_pnl, exc_99, exc_95, desk),
            )

    def get_history(self, desk: str = "FIRM", days: int = 250) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT trade_date, var_99, var_95, realized_pnl,
                       exception_99, exception_95, desk
                FROM var_backtest
                WHERE desk = ?
                ORDER BY trade_date DESC
                LIMIT ?
                """,
                (desk, days),
            ).fetchall()
        return [dict(r) for r in reversed(rows)]

    def get_exception_count(self, desk: str = "FIRM", days: int = 250) -> int:
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*) FROM (
                    SELECT 1 FROM var_backtest
                    WHERE desk = ? AND exception_99 = 1
                    ORDER BY trade_date DESC
                    LIMIT ?
                )
                """,
                (desk, days),
            ).fetchone()
        return int(row[0]) if row else 0

    def get_traffic_light_zone(self, desk: str = "FIRM") -> str:
        n = self.get_exception_count(desk, 250)
        if n <= 4:
            return "GREEN"
        if n <= 9:
            return "YELLOW"
        return "RED"

    def get_capital_multiplier(self, desk: str = "FIRM") -> float:
        n = self.get_exception_count(desk, 250)
        if n <= 4:
            return 3.0
        if n in _YELLOW_K:
            return _YELLOW_K[n]
        if n < 10:
            return 3.85
        return 4.0

    def get_backtest_summary(self) -> dict[str, Any]:
        with self._connect() as conn:
            desks = [r[0] for r in conn.execute("SELECT DISTINCT desk FROM var_backtest").fetchall()]

        summary: dict[str, Any] = {}
        for desk in desks:
            exc = self.get_exception_count(desk, 250)
            zone = self.get_traffic_light_zone(desk)
            k = self.get_capital_multiplier(desk)
            recent = self.get_history(desk, 10)
            summary[desk] = {
                "desk": desk,
                "exception_count_250d": exc,
                "traffic_light_zone": zone,
                "capital_multiplier_k": k,
                "recent_10d": recent,
            }

        log.info("var_backtest_store.summary_built", desks=list(summary.keys()))
        return summary


# Module-level singleton (initialised lazily — actual init call is in api/main.py lifespan)
backtest_store = VaRBacktestStore()
