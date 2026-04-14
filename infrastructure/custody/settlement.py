"""
Settlement Engine — Apex Global Bank.

T+1 equities, T+2 bonds. DVP (Delivery vs. Payment) model.
Affirm → Settle lifecycle. Fires SettlementCompleted event on batch settle.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone, timedelta
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_CUSTODY
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS settlement_instructions (
    instruction_id  TEXT PRIMARY KEY,
    isin            TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    quantity        REAL NOT NULL,
    price_usd       REAL NOT NULL,
    side            TEXT NOT NULL,   -- DVP_BUY | DVP_SELL
    account_id      TEXT NOT NULL,
    trade_date      TEXT NOT NULL,
    settlement_date TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | AFFIRMED | SETTLED | FAILED
    settled_at      TEXT,
    created_at      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_si_status ON settlement_instructions(status, settlement_date);
"""

# Settlement lag by asset class
_SETTLEMENT_LAG: dict[str, int] = {
    "EQUITY": 1,   # T+1
    "BOND":   2,   # T+2
}


def _infer_asset_class(isin: str) -> str:
    """Crude asset class inference from ISIN prefix."""
    # US912810... = UST bonds; US38141G... = corp bonds; else equity
    if isin.startswith("US9128") or isin.startswith("US38141"):
        return "BOND"
    return "EQUITY"


class SettlementEngine:
    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)

    def _connect(self):
        return open_db(DB_CUSTODY)

    def instruct(
        self,
        isin: str,
        quantity: float,
        price_usd: float,
        side: str,
        account_id: str,
        description: str = "",
        asset_class: str | None = None,
    ) -> dict[str, Any]:
        if side not in ("DVP_BUY", "DVP_SELL"):
            raise ValueError("side must be DVP_BUY or DVP_SELL")

        ac = asset_class or _infer_asset_class(isin)
        lag = _SETTLEMENT_LAG.get(ac, 2)
        trade_date = date.today().isoformat()
        settle_date = (date.today() + timedelta(days=lag)).isoformat()
        iid = f"SI-{str(uuid.uuid4())[:8].upper()}"
        now = _now()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO settlement_instructions "
                    "(instruction_id, isin, description, quantity, price_usd, side, account_id, "
                    "trade_date, settlement_date, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                    (iid, isin, description, quantity, price_usd, side, account_id,
                     trade_date, settle_date, "PENDING", now),
                )
                conn.commit()

        log.info("settlement.instructed", instruction_id=iid, isin=isin, side=side, quantity=quantity)
        return self._get_instruction(iid)

    def affirm(self, instruction_id: str) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT status FROM settlement_instructions WHERE instruction_id=?",
                    (instruction_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Instruction {instruction_id!r} not found")
                if row["status"] != "PENDING":
                    raise ValueError(f"Instruction {instruction_id!r} is {row['status']}, not PENDING")
                conn.execute(
                    "UPDATE settlement_instructions SET status='AFFIRMED' WHERE instruction_id=?",
                    (instruction_id,),
                )
                conn.commit()
        return self._get_instruction(instruction_id)

    def settle_batch(self, settle_date: str | None = None) -> dict[str, Any]:
        """Settle all AFFIRMED instructions with settlement_date <= target date."""
        target = settle_date or date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM settlement_instructions "
                "WHERE status IN ('AFFIRMED','PENDING') AND settlement_date<=?",
                (target,),
            ).fetchall()

        settled = []
        failed = []
        for row in rows:
            instr = dict(row)
            try:
                self._settle_instruction(instr)
                settled.append(instr["instruction_id"])
            except Exception as exc:
                log.warning("settlement.failed", instruction_id=instr["instruction_id"], error=str(exc))
                failed.append({"instruction_id": instr["instruction_id"], "error": str(exc)})
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE settlement_instructions SET status='FAILED' WHERE instruction_id=?",
                        (instr["instruction_id"],),
                    )
                    conn.commit()

        # Fire event
        try:
            from infrastructure.events.event_log import event_log
            event_log.append("Settlement", "BATCH", "SettlementCompleted", {
                "settled": len(settled), "failed": len(failed), "date": target,
            })
        except Exception:
            pass

        return {
            "settle_date":   target,
            "settled_count": len(settled),
            "failed_count":  len(failed),
            "settled":       settled,
            "failed":        failed,
        }

    def get_pending(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM settlement_instructions WHERE status IN ('PENDING','AFFIRMED') "
                "ORDER BY settlement_date",
            ).fetchall()
        return [dict(r) for r in rows]

    def _settle_instruction(self, instr: dict) -> None:
        """Apply settled instruction to custody holdings."""
        from infrastructure.custody.custody_accounts import custody_book

        isin = instr["isin"]
        qty = float(instr["quantity"])
        price = float(instr["price_usd"])
        account_id = instr["account_id"]
        side = instr["side"]
        desc = instr.get("description", isin)

        if side == "DVP_BUY":
            custody_book.book_holding(account_id, isin, desc, qty, price)
        else:
            # DVP_SELL: reduce holding (book negative quantity)
            custody_book.book_holding(account_id, isin, desc, -qty, price)

        now = _now()
        with self._connect() as conn:
            conn.execute(
                "UPDATE settlement_instructions SET status='SETTLED', settled_at=? WHERE instruction_id=?",
                (now, instr["instruction_id"]),
            )
            conn.commit()

        log.info("settlement.settled", instruction_id=instr["instruction_id"],
                 isin=isin, side=side, quantity=qty)

    def _get_instruction(self, instruction_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM settlement_instructions WHERE instruction_id=?",
                (instruction_id,),
            ).fetchone()
        return dict(row) if row else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


settlement_engine = SettlementEngine()
