"""
Nostro Account Manager — Apex Global Bank.

Pre-seeded with 4 correspondent accounts (USD/Fed, EUR, GBP, JPY).
Tracks current balances, credit lines, and intraday overdraft usage.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_PAYMENTS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS nostro_accounts (
    account_id          TEXT PRIMARY KEY,
    currency            TEXT NOT NULL,
    correspondent_bank  TEXT NOT NULL,
    opening_balance_usd REAL NOT NULL,
    current_balance_usd REAL NOT NULL,
    credit_line_usd     REAL NOT NULL DEFAULT 0.0,
    created_at          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS nostro_movements (
    movement_id  TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL REFERENCES nostro_accounts(account_id),
    direction    TEXT NOT NULL,   -- DEBIT | CREDIT
    amount_usd   REAL NOT NULL,
    reference    TEXT,
    recorded_at  TEXT NOT NULL
);
"""

_SEED_NOSTROS = [
    # (account_id, currency, bank, opening_balance, credit_line)
    ("NOSTRO-USD-FED",  "USD", "Federal Reserve (Fedwire)", 12_000_000_000.0, 5_000_000_000.0),
    ("NOSTRO-EUR-ECB",  "EUR", "Deutsche Bank (EUR proxy)", 3_500_000_000.0,  1_500_000_000.0),
    ("NOSTRO-GBP-BOE",  "GBP", "Barclays (GBP proxy)",     2_100_000_000.0,  1_000_000_000.0),
    ("NOSTRO-JPY-BOJ",  "JPY", "MUFG (JPY proxy)",         1_800_000_000.0,    800_000_000.0),
]


class NostroBook:
    def __init__(self, conn) -> None:
        self._lock = Lock()
        self._conn_factory = lambda: conn
        conn.executescript(_DDL)
        self._seed_if_empty(conn)

    @classmethod
    def create(cls) -> "NostroBook":
        conn = open_db(DB_PAYMENTS)
        return cls(conn)

    def _connect(self):
        return open_db(DB_PAYMENTS)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM nostro_accounts").fetchone()[0]
        if count > 0:
            return
        now = _now()
        for aid, ccy, bank, bal, line in _SEED_NOSTROS:
            conn.execute(
                "INSERT INTO nostro_accounts (account_id, currency, correspondent_bank, "
                "opening_balance_usd, current_balance_usd, credit_line_usd, created_at) "
                "VALUES (?,?,?,?,?,?,?)",
                (aid, ccy, bank, bal, bal, line, now),
            )
        conn.commit()
        log.info("nostro_book.seeded", count=len(_SEED_NOSTROS))

    def debit(self, account_id: str, amount_usd: float, reference: str = "") -> None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT current_balance_usd, credit_line_usd FROM nostro_accounts WHERE account_id=?",
                    (account_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Nostro {account_id!r} not found")
                available = float(row["current_balance_usd"]) + float(row["credit_line_usd"])
                if amount_usd > available:
                    raise ValueError(f"Daylight overdraft limit exceeded on {account_id}")
                new_bal = float(row["current_balance_usd"]) - amount_usd
                conn.execute("UPDATE nostro_accounts SET current_balance_usd=? WHERE account_id=?",
                             (new_bal, account_id))
                conn.execute(
                    "INSERT INTO nostro_movements (movement_id, account_id, direction, amount_usd, reference, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), account_id, "DEBIT", amount_usd, reference, _now()),
                )
                conn.commit()

    def credit(self, account_id: str, amount_usd: float, reference: str = "") -> None:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT current_balance_usd FROM nostro_accounts WHERE account_id=?",
                    (account_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Nostro {account_id!r} not found")
                new_bal = float(row["current_balance_usd"]) + amount_usd
                conn.execute("UPDATE nostro_accounts SET current_balance_usd=? WHERE account_id=?",
                             (new_bal, account_id))
                conn.execute(
                    "INSERT INTO nostro_movements (movement_id, account_id, direction, amount_usd, reference, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), account_id, "CREDIT", amount_usd, reference, _now()),
                )
                conn.commit()

    def get_balances(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM nostro_accounts ORDER BY currency").fetchall()
        return [dict(r) for r in rows]

    def get_daylight_overdraft_usage(self) -> dict[str, Any]:
        balances = self.get_balances()
        total_credit_line = sum(b["credit_line_usd"] for b in balances)
        total_usage = sum(
            max(0.0, -b["current_balance_usd"]) for b in balances
        )
        return {
            "accounts": [
                {
                    "account_id": b["account_id"],
                    "currency": b["currency"],
                    "current_balance_usd": b["current_balance_usd"],
                    "credit_line_usd": b["credit_line_usd"],
                    "overdraft_usage_usd": round(max(0.0, -b["current_balance_usd"]), 2),
                    "headroom_usd": round(b["current_balance_usd"] + b["credit_line_usd"], 2),
                }
                for b in balances
            ],
            "total_credit_line_usd": round(total_credit_line, 2),
            "total_overdraft_usage_usd": round(total_usage, 2),
        }


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
