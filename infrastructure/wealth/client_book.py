"""
Wealth Management Client Book — Apex Global Bank.

Manages HNWI, UHNWI, and Family Office clients with AUM, model portfolio
allocations, and annual fee billing. Fee revenue flows into the
ConsolidatedIncomeStatement, replacing the hardcoded wealth_management stub.

Fee schedule: HNWI 75bps, UHNWI 60bps, FAMILY_OFFICE 40bps.
Model portfolios: conservative / balanced / growth / aggressive.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_WEALTH
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS wealth_clients (
    client_id    TEXT PRIMARY KEY,
    client_name  TEXT NOT NULL,
    segment      TEXT NOT NULL,   -- HNWI | UHNWI | FAMILY_OFFICE
    aum_usd      REAL NOT NULL,
    mandate_type TEXT NOT NULL,   -- DISCRETIONARY | ADVISORY | EXECUTION_ONLY
    risk_profile TEXT NOT NULL,   -- CONSERVATIVE | BALANCED | GROWTH | AGGRESSIVE
    fee_bps      INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wealth_portfolios (
    portfolio_id     TEXT PRIMARY KEY,
    client_id        TEXT NOT NULL REFERENCES wealth_clients(client_id),
    model_portfolio  TEXT NOT NULL,
    asset_class      TEXT NOT NULL,   -- BONDS | EQUITIES | ALTERNATIVES | CASH
    allocation_pct   REAL NOT NULL,
    market_value_usd REAL NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS wealth_fee_accruals (
    accrual_id TEXT PRIMARY KEY,
    client_id  TEXT NOT NULL,
    period     TEXT NOT NULL,
    aum_usd    REAL NOT NULL,
    fee_bps    INTEGER NOT NULL,
    fee_usd    REAL NOT NULL,
    accrued_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_wc_segment ON wealth_clients(segment);
CREATE INDEX IF NOT EXISTS idx_wp_client  ON wealth_portfolios(client_id);
"""

# Model portfolio allocations (BONDS / EQUITIES / ALTERNATIVES / CASH)
_MODEL_PORTFOLIOS: dict[str, dict[str, float]] = {
    "conservative": {"BONDS": 0.70, "EQUITIES": 0.20, "ALTERNATIVES": 0.05, "CASH": 0.05},
    "balanced":     {"BONDS": 0.40, "EQUITIES": 0.50, "ALTERNATIVES": 0.07, "CASH": 0.03},
    "growth":       {"BONDS": 0.15, "EQUITIES": 0.70, "ALTERNATIVES": 0.12, "CASH": 0.03},
    "aggressive":   {"BONDS": 0.05, "EQUITIES": 0.80, "ALTERNATIVES": 0.14, "CASH": 0.01},
}

_RISK_TO_MODEL: dict[str, str] = {
    "CONSERVATIVE": "conservative",
    "BALANCED":     "balanced",
    "GROWTH":       "growth",
    "AGGRESSIVE":   "aggressive",
}

_FEE_BPS: dict[str, int] = {
    "HNWI":         75,
    "UHNWI":        60,
    "FAMILY_OFFICE": 40,
}

# Seed clients — $8.1B total AUM
_SEED_CLIENTS = [
    # (client_id, name, segment, aum_usd, mandate_type, risk_profile)
    ("WM-001", "Al-Rashid Family Office",    "FAMILY_OFFICE", 2_400_000_000, "DISCRETIONARY",  "BALANCED"),
    ("WM-002", "Pemberton Capital Partners", "UHNWI",         1_800_000_000, "DISCRETIONARY",  "GROWTH"),
    ("WM-003", "Chen Family Trust",          "FAMILY_OFFICE", 1_200_000_000, "ADVISORY",       "CONSERVATIVE"),
    ("WM-004", "Dr. Sarah Mitchell",         "UHNWI",           850_000_000, "DISCRETIONARY",  "AGGRESSIVE"),
    ("WM-005", "Henderson Manufacturing Estate", "HNWI",        950_000_000, "ADVISORY",       "BALANCED"),
    ("WM-006", "Sunrise Endowment Fund",     "FAMILY_OFFICE",   900_000_000, "EXECUTION_ONLY", "CONSERVATIVE"),
]


class ClientBook:
    """SQLite-backed wealth management client and portfolio registry."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def initialize(self) -> None:
        """Idempotent initialization (called from lifespan)."""
        pass

    def _connect(self):
        return open_db(DB_WEALTH)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM wealth_clients").fetchone()[0]
        if count > 0:
            return
        now = _now()
        for cid, name, segment, aum, mandate, risk in _SEED_CLIENTS:
            fee_bps = _FEE_BPS[segment]
            conn.execute(
                "INSERT INTO wealth_clients (client_id, client_name, segment, aum_usd, "
                "mandate_type, risk_profile, fee_bps, created_at) VALUES (?,?,?,?,?,?,?,?)",
                (cid, name, segment, aum, mandate, risk, fee_bps, now),
            )
            self._insert_portfolio(conn, cid, aum, risk, now)
        conn.commit()
        log.info("wealth_client_book.seeded", count=len(_SEED_CLIENTS))

    def _insert_portfolio(self, conn, client_id: str, aum_usd: float, risk_profile: str, now: str) -> None:
        model = _RISK_TO_MODEL.get(risk_profile, "balanced")
        allocs = _MODEL_PORTFOLIOS[model]
        for asset_class, pct in allocs.items():
            pid = f"PORT-{str(uuid.uuid4())[:8].upper()}"
            conn.execute(
                "INSERT INTO wealth_portfolios (portfolio_id, client_id, model_portfolio, "
                "asset_class, allocation_pct, market_value_usd, updated_at) VALUES (?,?,?,?,?,?,?)",
                (pid, client_id, model, asset_class, pct, round(aum_usd * pct, 2), now),
            )

    def add_client(
        self,
        client_id: str,
        client_name: str,
        segment: str,
        aum_usd: float,
        mandate_type: str,
        risk_profile: str,
    ) -> dict[str, Any]:
        if segment not in _FEE_BPS:
            raise ValueError(f"segment must be one of {list(_FEE_BPS)}")
        if risk_profile not in _RISK_TO_MODEL:
            raise ValueError(f"risk_profile must be one of {list(_RISK_TO_MODEL)}")
        if mandate_type not in ("DISCRETIONARY", "ADVISORY", "EXECUTION_ONLY"):
            raise ValueError("mandate_type must be DISCRETIONARY, ADVISORY, or EXECUTION_ONLY")

        fee_bps = _FEE_BPS[segment]
        now = _now()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO wealth_clients (client_id, client_name, segment, aum_usd, "
                    "mandate_type, risk_profile, fee_bps, created_at) VALUES (?,?,?,?,?,?,?,?)",
                    (client_id, client_name, segment, aum_usd, mandate_type, risk_profile, fee_bps, now),
                )
                if cur.rowcount > 0:
                    self._insert_portfolio(conn, client_id, aum_usd, risk_profile, now)
                conn.commit()
        log.info("wealth_client_book.client_added", client_id=client_id, aum=aum_usd, segment=segment)
        return self.get_client(client_id)

    def update_aum(self, client_id: str, new_aum_usd: float) -> dict[str, Any]:
        now = _now()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT risk_profile FROM wealth_clients WHERE client_id=?", (client_id,)
                ).fetchone()
                if not row:
                    raise ValueError(f"Client {client_id!r} not found")
                risk = row["risk_profile"]
                conn.execute(
                    "UPDATE wealth_clients SET aum_usd=? WHERE client_id=?",
                    (new_aum_usd, client_id),
                )
                # Rebuild portfolio market values
                conn.execute("DELETE FROM wealth_portfolios WHERE client_id=?", (client_id,))
                self._insert_portfolio(conn, client_id, new_aum_usd, risk, now)
                conn.commit()
        return self.get_client(client_id)

    def get_client(self, client_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM wealth_clients WHERE client_id=?", (client_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["annual_fee_usd"] = round(d["aum_usd"] * d["fee_bps"] / 10000, 2)
        return d

    def get_all_clients(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM wealth_clients ORDER BY aum_usd DESC"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["annual_fee_usd"] = round(d["aum_usd"] * d["fee_bps"] / 10000, 2)
            result.append(d)
        return result

    def get_holdings(self, client_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM wealth_portfolios WHERE client_id=? ORDER BY allocation_pct DESC",
                (client_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_client_summary(self) -> dict[str, Any]:
        clients = self.get_all_clients()
        total_aum = sum(c["aum_usd"] for c in clients)
        total_fees = sum(c["annual_fee_usd"] for c in clients)

        by_segment: dict[str, dict] = {}
        by_risk: dict[str, dict] = {}
        for c in clients:
            seg = c["segment"]
            risk = c["risk_profile"]
            if seg not in by_segment:
                by_segment[seg] = {"count": 0, "aum_usd": 0.0, "annual_fee_usd": 0.0}
            by_segment[seg]["count"] += 1
            by_segment[seg]["aum_usd"] += c["aum_usd"]
            by_segment[seg]["annual_fee_usd"] += c["annual_fee_usd"]

            if risk not in by_risk:
                by_risk[risk] = {"count": 0, "aum_usd": 0.0}
            by_risk[risk]["count"] += 1
            by_risk[risk]["aum_usd"] += c["aum_usd"]

        for seg in by_segment:
            by_segment[seg]["aum_usd"] = round(by_segment[seg]["aum_usd"], 2)
            by_segment[seg]["annual_fee_usd"] = round(by_segment[seg]["annual_fee_usd"], 2)
        for risk in by_risk:
            by_risk[risk]["aum_usd"] = round(by_risk[risk]["aum_usd"], 2)

        return {
            "client_count":               len(clients),
            "total_aum_usd":              round(total_aum, 2),
            "annual_fee_revenue_usd":     round(total_fees, 2),
            "avg_fee_bps":                round(total_fees / total_aum * 10000, 2) if total_aum else 0.0,
            "by_segment":                 by_segment,
            "by_risk_profile":            by_risk,
        }

    def calculate_annual_fees(self) -> float:
        """Total annual fee revenue across all clients (feeds ConsolidatedIncomeStatement)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT aum_usd, fee_bps FROM wealth_clients").fetchall()
        return sum(float(r["aum_usd"]) * r["fee_bps"] / 10000 for r in rows)

    def bill_fees(self, period: str) -> list[dict[str, Any]]:
        """Record annual fee accrual for each client and return accrual records."""
        clients = self.get_all_clients()
        accruals = []
        now = _now()
        with self._lock:
            with self._connect() as conn:
                for c in clients:
                    fee = round(c["aum_usd"] * c["fee_bps"] / 10000, 2)
                    aid = str(uuid.uuid4())
                    conn.execute(
                        "INSERT INTO wealth_fee_accruals (accrual_id, client_id, period, "
                        "aum_usd, fee_bps, fee_usd, accrued_at) VALUES (?,?,?,?,?,?,?)",
                        (aid, c["client_id"], period, c["aum_usd"], c["fee_bps"], fee, now),
                    )
                    accruals.append({
                        "accrual_id": aid,
                        "client_id":  c["client_id"],
                        "client_name": c["client_name"],
                        "period":     period,
                        "aum_usd":    c["aum_usd"],
                        "fee_bps":    c["fee_bps"],
                        "fee_usd":    fee,
                    })
                conn.commit()
        log.info("wealth.fees_billed", period=period, clients=len(accruals),
                 total_fees=round(sum(a["fee_usd"] for a in accruals), 2))
        return accruals


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


client_book = ClientBook()
