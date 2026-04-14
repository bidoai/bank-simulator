"""
Operational Risk Loss Event Database.

SQLite-backed log of operational loss events, feeding the BIA income
statement with actual loss history. Supports Basel III CRE10 internal
loss data requirements.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_LOSS_EVENTS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS loss_events (
    event_id        TEXT PRIMARY KEY,
    business_line   TEXT NOT NULL,
    event_type      TEXT NOT NULL,
    gross_loss_usd  REAL NOT NULL,
    recovery_usd    REAL NOT NULL DEFAULT 0.0,
    net_loss_usd    REAL NOT NULL,
    event_date      TEXT NOT NULL,
    description     TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'open',
    created_at      TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_loss_bline ON loss_events(business_line);
CREATE INDEX IF NOT EXISTS idx_loss_date  ON loss_events(event_date DESC);
"""

# Basel III CRE20 business lines
BUSINESS_LINES = [
    "CORPORATE_FINANCE",
    "TRADING_AND_SALES",
    "RETAIL_BANKING",
    "COMMERCIAL_BANKING",
    "PAYMENT_AND_SETTLEMENT",
    "AGENCY_SERVICES",
    "ASSET_MANAGEMENT",
    "RETAIL_BROKERAGE",
]

# Basel III CRE20 event types (Level 1)
EVENT_TYPES = [
    "INTERNAL_FRAUD",
    "EXTERNAL_FRAUD",
    "EMPLOYMENT_PRACTICES",
    "CLIENTS_PRODUCTS",
    "DAMAGE_TO_ASSETS",
    "BUSINESS_DISRUPTION",
    "EXECUTION_DELIVERY",
]

# Seed data — representative historical losses for a JPMorgan-scale institution
_SEED_EVENTS = [
    ("TRADING_AND_SALES",      "EXECUTION_DELIVERY",   42_000_000,  8_000_000, "2025-01-15", "Fat-finger equity trade — erroneous order in AAPL; recovered via market unwind"),
    ("PAYMENT_AND_SETTLEMENT", "EXECUTION_DELIVERY",   18_500_000,  5_000_000, "2025-02-03", "CHIPS payment to wrong account; partial recovery via recall"),
    ("RETAIL_BANKING",         "EXTERNAL_FRAUD",       11_200_000,  2_100_000, "2025-02-20", "Synthetic identity fraud ring — 47 accounts; partial insurance recovery"),
    ("COMMERCIAL_BANKING",     "CLIENTS_PRODUCTS",     95_000_000,      0.0,   "2025-03-08", "Mis-selling structured product to pension fund — regulatory fine + restitution"),
    ("TRADING_AND_SALES",      "INTERNAL_FRAUD",        8_300_000,      0.0,   "2025-03-22", "Unauthorized FX position by junior trader — detected at EOD"),
    ("CORPORATE_FINANCE",      "CLIENTS_PRODUCTS",     22_500_000,  4_500_000, "2025-04-11", "Conflict of interest in M&A advisory — SEC settlement"),
    ("ASSET_MANAGEMENT",       "EXECUTION_DELIVERY",    6_800_000,  1_200_000, "2025-05-05", "Index rebalancing error — incorrect weightings for 3 days"),
    ("PAYMENT_AND_SETTLEMENT", "BUSINESS_DISRUPTION",  14_000_000,  6_000_000, "2025-06-18", "Core payment system outage — 4hr window; customer compensation"),
    ("RETAIL_BANKING",         "EXTERNAL_FRAUD",        9_600_000,  3_200_000, "2025-07-29", "Card skimming network — 1,200 compromised accounts"),
    ("TRADING_AND_SALES",      "EXECUTION_DELIVERY",   31_000_000, 12_000_000, "2025-09-14", "Algorithmic trading glitch — erroneous sells in equity book"),
    ("COMMERCIAL_BANKING",     "EMPLOYMENT_PRACTICES",  7_200_000,      0.0,   "2025-10-02", "Wrongful termination class action settlement"),
    ("AGENCY_SERVICES",        "EXECUTION_DELIVERY",    5_400_000,  1_800_000, "2025-11-19", "Custody settlement fails — client compensation for missed corporate action"),
    ("RETAIL_BANKING",         "DAMAGE_TO_ASSETS",      3_100_000,  2_900_000, "2025-12-07", "Branch flooding — equipment loss; insurance covered most"),
    ("TRADING_AND_SALES",      "CLIENTS_PRODUCTS",     56_000_000,      0.0,   "2026-01-23", "Interest rate swap mis-valuation disclosed to corporate clients"),
    ("PAYMENT_AND_SETTLEMENT", "EXTERNAL_FRAUD",       19_700_000,  8_500_000, "2026-02-14", "SWIFT messaging compromise attempt — partial loss before detection"),
]


class LossEventDB:
    """SQLite-backed operational risk loss event log."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def _connect(self):
        return open_db(DB_LOSS_EVENTS)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM loss_events").fetchone()[0]
        if count > 0:
            return
        now = _now()
        for bl, et, gross, recovery, dt, desc in _SEED_EVENTS:
            conn.execute(
                "INSERT INTO loss_events "
                "(event_id, business_line, event_type, gross_loss_usd, recovery_usd, "
                "net_loss_usd, event_date, description, status, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'closed', ?)",
                (str(uuid.uuid4()), bl, et, gross, recovery, gross - recovery, dt, desc, now),
            )
        conn.commit()
        log.info("loss_event_db.seeded", count=len(_SEED_EVENTS))

    def record_event(
        self,
        business_line: str,
        event_type: str,
        gross_loss_usd: float,
        recovery_usd: float,
        description: str,
        event_date: str | None = None,
    ) -> dict[str, Any]:
        """Record a new operational loss event. Returns the persisted event dict."""
        if business_line not in BUSINESS_LINES:
            raise ValueError(f"Unknown business line: {business_line!r}. Valid: {BUSINESS_LINES}")
        if event_type not in EVENT_TYPES:
            raise ValueError(f"Unknown event type: {event_type!r}. Valid: {EVENT_TYPES}")

        event_id = str(uuid.uuid4())
        net_loss = max(0.0, gross_loss_usd - recovery_usd)
        dt = event_date or date.today().isoformat()
        now = _now()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO loss_events "
                    "(event_id, business_line, event_type, gross_loss_usd, recovery_usd, "
                    "net_loss_usd, event_date, description, status, created_at) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)",
                    (event_id, business_line, event_type, gross_loss_usd,
                     recovery_usd, net_loss, dt, description, now),
                )
                conn.commit()

        log.info("loss_event.recorded", event_id=event_id, net_loss_usd=net_loss, business_line=business_line)
        return self.get_event(event_id)

    def get_event(self, event_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM loss_events WHERE event_id = ?", (event_id,)
            ).fetchone()
        return dict(row) if row else None

    def get_events(
        self,
        business_line: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Return loss events filtered by business line and date range."""
        clauses: list[str] = []
        params: list[Any] = []
        if business_line:
            clauses.append("business_line = ?")
            params.append(business_line)
        if start_date:
            clauses.append("event_date >= ?")
            params.append(start_date)
        if end_date:
            clauses.append("event_date <= ?")
            params.append(end_date)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        params.append(limit)
        with self._connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM loss_events {where} ORDER BY event_date DESC LIMIT ?",
                params,
            ).fetchall()
        return [dict(r) for r in rows]

    def get_summary(self) -> dict[str, Any]:
        """Aggregate loss statistics by business line and event type."""
        with self._connect() as conn:
            total_row = conn.execute(
                "SELECT COUNT(*) as n, SUM(gross_loss_usd) as gross, "
                "SUM(net_loss_usd) as net, SUM(recovery_usd) as recovered "
                "FROM loss_events"
            ).fetchone()
            by_line = conn.execute(
                "SELECT business_line, COUNT(*) as n, SUM(net_loss_usd) as net_loss_usd "
                "FROM loss_events GROUP BY business_line ORDER BY net_loss_usd DESC"
            ).fetchall()
            by_type = conn.execute(
                "SELECT event_type, COUNT(*) as n, SUM(net_loss_usd) as net_loss_usd "
                "FROM loss_events GROUP BY event_type ORDER BY net_loss_usd DESC"
            ).fetchall()

        return {
            "total_events":        total_row["n"] or 0,
            "total_gross_loss_usd": round(total_row["gross"] or 0.0, 2),
            "total_net_loss_usd":   round(total_row["net"] or 0.0, 2),
            "total_recovery_usd":   round(total_row["recovered"] or 0.0, 2),
            "by_business_line":    [dict(r) for r in by_line],
            "by_event_type":       [dict(r) for r in by_type],
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


loss_event_db = LossEventDB()
