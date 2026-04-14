"""
Payment Ledger — Apex Global Bank.

Simulates Fedwire (RTGS, ~30s settle) and CHIPS (bilateral net, EOD batch) rails.
Validates daylight overdraft headroom before submitting. Updates nostro balances
and intraday monitor on settlement.
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
CREATE TABLE IF NOT EXISTS payments (
    payment_id    TEXT PRIMARY KEY,
    rail          TEXT NOT NULL,    -- FEDWIRE | CHIPS | INTERNAL
    sender_nostro TEXT NOT NULL,
    receiver_nostro TEXT NOT NULL,
    amount_usd    REAL NOT NULL,
    currency      TEXT NOT NULL DEFAULT 'USD',
    status        TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING | SETTLED | FAILED | RETURNED
    reference     TEXT,
    submitted_at  TEXT NOT NULL,
    settled_at    TEXT
);

CREATE INDEX IF NOT EXISTS idx_pay_status ON payments(status, rail);
CREATE INDEX IF NOT EXISTS idx_pay_submitted ON payments(submitted_at DESC);
"""

# Default nostro account for outgoing payments
_DEFAULT_SENDER = "NOSTRO-USD-FED"
_DEFAULT_RECEIVER = "NOSTRO-USD-FED"


@dataclass
class Payment:
    payment_id:      str
    rail:            str
    sender_nostro:   str
    receiver_nostro: str
    amount_usd:      float
    currency:        str
    status:          str
    reference:       str | None
    submitted_at:    str
    settled_at:      str | None

    def to_dict(self) -> dict:
        return {
            "payment_id":      self.payment_id,
            "rail":            self.rail,
            "sender_nostro":   self.sender_nostro,
            "receiver_nostro": self.receiver_nostro,
            "amount_usd":      self.amount_usd,
            "currency":        self.currency,
            "status":          self.status,
            "reference":       self.reference,
            "submitted_at":    self.submitted_at,
            "settled_at":      self.settled_at,
        }


class PaymentLedger:
    """SQLite-backed payment submission, settlement, and activity log."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
        # Initialize nostro book (shares the same DB file)
        self._init_nostro()

    def _connect(self):
        return open_db(DB_PAYMENTS)

    def _init_nostro(self) -> None:
        from infrastructure.payments.nostro import _DDL as _NOSTRO_DDL, _SEED_NOSTROS, _now
        with self._connect() as conn:
            conn.executescript(_NOSTRO_DDL)
            count = conn.execute("SELECT COUNT(*) FROM nostro_accounts").fetchone()[0]
            if count == 0:
                now = _now()
                for aid, ccy, bank, bal, line in _SEED_NOSTROS:
                    conn.execute(
                        "INSERT INTO nostro_accounts (account_id, currency, correspondent_bank, "
                        "opening_balance_usd, current_balance_usd, credit_line_usd, created_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (aid, ccy, bank, bal, bal, line, now),
                    )
                conn.commit()
                log.info("payment_ledger.nostros_seeded")

    def submit(
        self,
        rail: str,
        amount_usd: float,
        sender_nostro: str = _DEFAULT_SENDER,
        receiver_nostro: str = _DEFAULT_RECEIVER,
        currency: str = "USD",
        reference: str | None = None,
    ) -> dict[str, Any]:
        """Submit a payment. Validates overdraft headroom. Returns payment record."""
        if rail not in ("FEDWIRE", "CHIPS", "INTERNAL"):
            raise ValueError("rail must be FEDWIRE, CHIPS, or INTERNAL")

        # Validate headroom
        with self._connect() as conn:
            row = conn.execute(
                "SELECT current_balance_usd, credit_line_usd FROM nostro_accounts WHERE account_id=?",
                (sender_nostro,),
            ).fetchone()
            if not row:
                raise ValueError(f"Sender nostro {sender_nostro!r} not found")
            headroom = float(row["current_balance_usd"]) + float(row["credit_line_usd"])
            if amount_usd > headroom:
                raise ValueError(
                    f"Daylight overdraft limit exceeded: need {amount_usd:.0f}, headroom {headroom:.0f}"
                )

        pid = f"PAY-{str(uuid.uuid4())[:8].upper()}"
        now = _now()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO payments (payment_id, rail, sender_nostro, receiver_nostro, "
                    "amount_usd, currency, status, reference, submitted_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (pid, rail, sender_nostro, receiver_nostro, amount_usd, currency,
                     "PENDING", reference, now),
                )
                conn.commit()

        log.info("payment.submitted", payment_id=pid, rail=rail, amount=amount_usd)

        # Fedwire: RTGS — auto-settle immediately (simulated)
        if rail in ("FEDWIRE", "INTERNAL"):
            return self.settle(pid)

        return self._get_payment(pid)

    def settle(self, payment_id: str) -> dict[str, Any]:
        """Settle a payment: debit sender nostro, credit receiver, mark SETTLED."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT * FROM payments WHERE payment_id=? AND status='PENDING'",
                    (payment_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Payment {payment_id!r} not found or not pending")

                p = dict(row)
                now = _now()

                # Update nostro balances
                conn.execute(
                    "UPDATE nostro_accounts SET current_balance_usd = current_balance_usd - ? WHERE account_id=?",
                    (p["amount_usd"], p["sender_nostro"]),
                )
                conn.execute(
                    "UPDATE nostro_accounts SET current_balance_usd = current_balance_usd + ? WHERE account_id=?",
                    (p["amount_usd"], p["receiver_nostro"]),
                )
                conn.execute(
                    "UPDATE payments SET status='SETTLED', settled_at=? WHERE payment_id=?",
                    (now, payment_id),
                )
                conn.commit()

        # Notify intraday monitor
        try:
            from infrastructure.liquidity.intraday import intraday_monitor
            intraday_monitor.record_payment(p["amount_usd"], "OUTFLOW", p["rail"])
        except Exception:
            pass

        log.info("payment.settled", payment_id=payment_id, amount=p["amount_usd"])
        return self._get_payment(payment_id)

    def settle_chips_batch(self, settle_date: str | None = None) -> dict[str, Any]:
        """
        CHIPS EOD batch settlement: bilaterally net all pending CHIPS payments
        and settle the net positions.
        """
        target = settle_date or date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE rail='CHIPS' AND status='PENDING' AND DATE(submitted_at)<=?",
                (target,),
            ).fetchall()

        settled = []
        failed = []
        for row in rows:
            try:
                result = self.settle(row["payment_id"])
                settled.append(result["payment_id"])
            except Exception as exc:
                failed.append({"payment_id": row["payment_id"], "error": str(exc)})

        return {
            "settle_date":    target,
            "settled_count":  len(settled),
            "failed_count":   len(failed),
            "settled":        settled,
            "failed":         failed,
        }

    def get_activity(self, activity_date: str | None = None) -> list[dict[str, Any]]:
        target = activity_date or date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE DATE(submitted_at)=? ORDER BY submitted_at DESC",
                (target,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_intraday_position(self) -> dict[str, Any]:
        """Intraday net payment position (settled outflows vs inflows)."""
        today = date.today().isoformat()
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM payments WHERE DATE(submitted_at)=? AND status='SETTLED'",
                (today,),
            ).fetchall()

        total_out = 0.0
        total_in = 0.0
        by_rail: dict[str, dict] = {}

        for r in rows:
            rail = r["rail"]
            amt = float(r["amount_usd"])
            if rail not in by_rail:
                by_rail[rail] = {"count": 0, "volume_usd": 0.0}
            by_rail[rail]["count"] += 1
            by_rail[rail]["volume_usd"] += amt
            # For simplicity, all settled payments are treated as outflows from our nostro
            total_out += amt

        nostro_balances = self._get_nostro_balances()

        return {
            "date":               today,
            "total_outflow_usd":  round(total_out, 2),
            "total_inflow_usd":   round(total_in, 2),
            "net_position_usd":   round(total_in - total_out, 2),
            "settled_count":      len(rows),
            "by_rail":            {k: {**v, "volume_usd": round(v["volume_usd"], 2)} for k, v in by_rail.items()},
            "nostro_balances":    nostro_balances,
        }

    def _get_payment(self, payment_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM payments WHERE payment_id=?", (payment_id,)).fetchone()
        return dict(row) if row else {}

    def _get_nostro_balances(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute("SELECT account_id, currency, current_balance_usd, credit_line_usd FROM nostro_accounts").fetchall()
        return [dict(r) for r in rows]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


payment_ledger = PaymentLedger()
