from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/payments", tags=["payments"])

_DEFAULT_SENDER = "NOSTRO-USD-FED"
_DEFAULT_RECEIVER = "NOSTRO-USD-FED"


class SubmitPaymentRequest(BaseModel):
    rail: str                           # FEDWIRE | CHIPS | INTERNAL
    amount_usd: float
    sender_nostro: str = _DEFAULT_SENDER
    receiver_nostro: str = _DEFAULT_RECEIVER
    currency: str = "USD"
    reference: Optional[str] = None


@router.post("/submit")
async def submit_payment(body: SubmitPaymentRequest):
    from infrastructure.payments.ledger import payment_ledger
    try:
        return payment_ledger.submit(
            rail=body.rail,
            amount_usd=body.amount_usd,
            sender_nostro=body.sender_nostro,
            receiver_nostro=body.receiver_nostro,
            currency=body.currency,
            reference=body.reference,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/activity")
async def payment_activity(date: Optional[str] = None):
    from infrastructure.payments.ledger import payment_ledger
    return {"payments": payment_ledger.get_activity(date)}


@router.get("/nostro/balances")
async def nostro_balances():
    from infrastructure.payments.ledger import payment_ledger
    return {"nostro_accounts": payment_ledger._get_nostro_balances()}


@router.get("/nostro/overdraft")
async def nostro_overdraft():
    from infrastructure.payments.ledger import payment_ledger
    with payment_ledger._connect() as conn:
        rows = conn.execute("SELECT * FROM nostro_accounts").fetchall()
    accounts = []
    for r in rows:
        d = dict(r)
        d["overdraft_usage_usd"] = round(max(0.0, -d["current_balance_usd"]), 2)
        d["headroom_usd"] = round(d["current_balance_usd"] + d["credit_line_usd"], 2)
        accounts.append(d)
    return {
        "accounts": accounts,
        "total_credit_line_usd": round(sum(a["credit_line_usd"] for a in accounts), 2),
        "total_overdraft_usage_usd": round(sum(a["overdraft_usage_usd"] for a in accounts), 2),
    }


@router.get("/intraday-position")
async def intraday_position():
    from infrastructure.payments.ledger import payment_ledger
    return payment_ledger.get_intraday_position()


@router.post("/{payment_id}/settle")
async def settle_payment(payment_id: str):
    from infrastructure.payments.ledger import payment_ledger
    try:
        return payment_ledger.settle(payment_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/chips/settle-batch")
async def settle_chips_batch(settle_date: Optional[str] = None):
    from infrastructure.payments.ledger import payment_ledger
    return payment_ledger.settle_chips_batch(settle_date)
