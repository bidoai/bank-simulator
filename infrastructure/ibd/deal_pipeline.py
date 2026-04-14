"""
Investment Banking Division — Deal Pipeline.
Apex Global Bank.

Tracks M&A, ECM, and DCM deals through a 7-stage lifecycle.
Fee revenue accrues at CLOSED and feeds ConsolidatedIncomeStatement,
replacing the hardcoded investment_banking fee stub.

Fee rates: M&A 0.5–2%, ECM 3–5%, DCM 0.5–2% of deal value.
League table: ranked by fees earned and deal count by deal type.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_IBD
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS ibd_deals (
    deal_id        TEXT PRIMARY KEY,
    deal_type      TEXT NOT NULL,   -- MA | ECM | DCM
    deal_name      TEXT NOT NULL,
    client_name    TEXT NOT NULL,
    deal_value_usd REAL NOT NULL,
    fee_rate       REAL NOT NULL,
    stage          TEXT NOT NULL,
    fee_earned_usd REAL NOT NULL DEFAULT 0.0,
    opened_date    TEXT NOT NULL,
    closed_date    TEXT,
    created_at     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ibd_stage_log (
    log_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    deal_id    TEXT NOT NULL REFERENCES ibd_deals(deal_id),
    from_stage TEXT NOT NULL,
    to_stage   TEXT NOT NULL,
    changed_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ibd_stage ON ibd_deals(stage, deal_type);
"""

VALID_STAGES = [
    "ORIGINATION", "MANDATE", "PITCHING", "SIGNED",
    "EXECUTION", "CLOSED", "FALLEN_AWAY",
]
DEAL_TYPES = ("MA", "ECM", "DCM")

# Seed deals — representative IBD pipeline at JPMorgan scale
_SEED_DEALS = [
    # (deal_type, deal_name, client, deal_value_usd, fee_rate, stage)
    ("MA",  "Meridian/Atlas Merger",          "Meridian Corp",          28_000_000_000, 0.012, "CLOSED"),
    ("ECM", "Pacific Tech IPO",               "Pacific Tech Corp",       5_200_000_000, 0.040, "CLOSED"),
    ("DCM", "National Utilities Bond",        "National Utilities",      3_500_000_000, 0.008, "CLOSED"),
    ("MA",  "Summit/Horizon Acquisition",     "Summit Industrials",     15_000_000_000, 0.015, "EXECUTION"),
    ("ECM", "Atlas Healthcare Follow-On",     "Atlas Healthcare",        2_100_000_000, 0.035, "SIGNED"),
    ("DCM", "Coastal REIT Senior Notes",      "Coastal Real Estate",     1_800_000_000, 0.007, "PITCHING"),
    ("MA",  "Apex Energy Restructuring",      "Apex Energy Holdings",    8_500_000_000, 0.018, "MANDATE"),
    ("ECM", "Meridian Retail Rights Issue",   "Meridian Retail Group",     900_000_000, 0.045, "ORIGINATION"),
]


class DealPipeline:
    """SQLite-backed IBD deal pipeline with stage lifecycle and fee accrual."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def initialize(self) -> None:
        """Idempotent initialization (called from lifespan)."""
        pass  # __init__ handles it

    def _connect(self):
        return open_db(DB_IBD)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM ibd_deals").fetchone()[0]
        if count > 0:
            return
        now = _now()
        today = date.today().isoformat()
        for deal_type, deal_name, client, deal_value, fee_rate, stage in _SEED_DEALS:
            did = f"DEAL-{str(uuid.uuid4())[:6].upper()}"
            fee_earned = deal_value * fee_rate if stage == "CLOSED" else 0.0
            closed_date = "2025-12-31" if stage == "CLOSED" else None
            conn.execute(
                "INSERT INTO ibd_deals (deal_id, deal_type, deal_name, client_name, "
                "deal_value_usd, fee_rate, stage, fee_earned_usd, opened_date, closed_date, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (did, deal_type, deal_name, client, deal_value, fee_rate,
                 stage, fee_earned, "2025-01-15", closed_date, now),
            )
        conn.commit()
        log.info("deal_pipeline.seeded", count=len(_SEED_DEALS))

    def add_deal(
        self,
        deal_type: str,
        deal_name: str,
        client_name: str,
        deal_value_usd: float,
        fee_rate: float,
        stage: str = "ORIGINATION",
    ) -> dict[str, Any]:
        if deal_type not in DEAL_TYPES:
            raise ValueError(f"deal_type must be one of {DEAL_TYPES}")
        if stage not in VALID_STAGES:
            raise ValueError(f"stage must be one of {VALID_STAGES}")
        did = f"DEAL-{str(uuid.uuid4())[:6].upper()}"
        fee_earned = deal_value_usd * fee_rate if stage == "CLOSED" else 0.0
        now = _now()
        today = date.today().isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO ibd_deals (deal_id, deal_type, deal_name, client_name, "
                    "deal_value_usd, fee_rate, stage, fee_earned_usd, opened_date, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (did, deal_type, deal_name, client_name, deal_value_usd,
                     fee_rate, stage, fee_earned, today, now),
                )
                conn.commit()
        log.info("deal_pipeline.deal_added", deal_id=did, deal_type=deal_type, stage=stage)
        return self.get_deal(did)

    def advance_stage(self, deal_id: str, to_stage: str) -> dict[str, Any]:
        """Move a deal to the next stage. Fee accrues at CLOSED; zeroed at FALLEN_AWAY."""
        if to_stage not in VALID_STAGES:
            raise ValueError(f"to_stage must be one of {VALID_STAGES}")
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT stage, deal_value_usd, fee_rate FROM ibd_deals WHERE deal_id=?",
                    (deal_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Deal {deal_id!r} not found")
                from_stage = row["stage"]
                deal_value = float(row["deal_value_usd"])
                fee_rate = float(row["fee_rate"])

                fee_earned = 0.0
                closed_date = None
                if to_stage == "CLOSED":
                    fee_earned = deal_value * fee_rate
                    closed_date = date.today().isoformat()

                conn.execute(
                    "UPDATE ibd_deals SET stage=?, fee_earned_usd=?, closed_date=? "
                    "WHERE deal_id=?",
                    (to_stage, fee_earned, closed_date, deal_id),
                )
                conn.execute(
                    "INSERT INTO ibd_stage_log (deal_id, from_stage, to_stage, changed_at) "
                    "VALUES (?,?,?,?)",
                    (deal_id, from_stage, to_stage, _now()),
                )
                conn.commit()
        log.info("deal_pipeline.stage_advanced", deal_id=deal_id,
                 from_stage=from_stage, to_stage=to_stage, fee_earned=fee_earned)
        return self.get_deal(deal_id)

    def get_deal(self, deal_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM ibd_deals WHERE deal_id=?", (deal_id,)).fetchone()
        return dict(row) if row else None

    def get_pipeline(self, stage: str | None = None) -> list[dict[str, Any]]:
        with self._connect() as conn:
            if stage:
                rows = conn.execute(
                    "SELECT * FROM ibd_deals WHERE stage=? ORDER BY deal_value_usd DESC",
                    (stage,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM ibd_deals ORDER BY deal_value_usd DESC"
                ).fetchall()
        return [dict(r) for r in rows]

    def get_league_table(self) -> dict[str, Any]:
        """Rankings by fees earned and deal count, by deal type."""
        deals = self.get_pipeline()
        closed = [d for d in deals if d["stage"] == "CLOSED"]

        by_type: dict[str, list] = {"MA": [], "ECM": [], "DCM": []}
        for d in closed:
            dt = d["deal_type"]
            if dt in by_type:
                by_type[dt].append({
                    "deal_id":       d["deal_id"],
                    "deal_name":     d["deal_name"],
                    "client_name":   d["client_name"],
                    "deal_value_usd": d["deal_value_usd"],
                    "fee_earned_usd": d["fee_earned_usd"],
                    "closed_date":   d["closed_date"],
                })

        # Sort each type by fees descending
        for dt in by_type:
            by_type[dt].sort(key=lambda x: x["fee_earned_usd"], reverse=True)

        overall = sorted(closed, key=lambda d: d["fee_earned_usd"], reverse=True)

        return {
            "by_type":           {dt: v for dt, v in by_type.items()},
            "overall":           [{"deal_id": d["deal_id"], "deal_name": d["deal_name"],
                                   "deal_type": d["deal_type"], "fee_earned_usd": d["fee_earned_usd"]}
                                  for d in overall],
            "summary": {
                "total_closed_deals": len(closed),
                "total_fees_earned_usd": round(sum(d["fee_earned_usd"] for d in closed), 2),
                "by_deal_type_count": {dt: len(by_type[dt]) for dt in by_type},
                "by_deal_type_fees": {
                    dt: round(sum(d["fee_earned_usd"] for d in by_type[dt]), 2)
                    for dt in by_type
                },
            },
        }

    def get_annual_fee_revenue(self) -> float:
        """Sum of fees from CLOSED deals (annual total, feeds ConsolidatedIncomeStatement)."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(fee_earned_usd), 0.0) FROM ibd_deals WHERE stage='CLOSED'"
            ).fetchone()
        return float(row[0])

    def get_ytd_fee_revenue(self) -> float:
        """Year-to-date fee revenue (current calendar year)."""
        year_start = f"{date.today().year}-01-01"
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(fee_earned_usd), 0.0) FROM ibd_deals "
                "WHERE stage='CLOSED' AND closed_date >= ?",
                (year_start,),
            ).fetchone()
        return float(row[0])


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


deal_pipeline = DealPipeline()
