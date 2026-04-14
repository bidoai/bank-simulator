from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/custody", tags=["custody"])


class OpenAccountRequest(BaseModel):
    client_id: str
    client_name: str
    account_type: str   # OMNIBUS | SEGREGATED


class BookHoldingRequest(BaseModel):
    isin: str
    description: str
    quantity: float
    price_usd: float


class InstructRequest(BaseModel):
    isin: str
    quantity: float
    price_usd: float
    side: str                       # DVP_BUY | DVP_SELL
    account_id: str
    description: str = ""
    asset_class: Optional[str] = None   # EQUITY | BOND (auto-detected if omitted)


class AddCARequest(BaseModel):
    ca_type: str
    isin: str
    issuer: str
    ex_date: str
    record_date: str
    pay_date: str
    details: dict = {}


# ── Account endpoints ────────────────────────────────────────────────────────

@router.post("/accounts")
async def open_account(body: OpenAccountRequest):
    from infrastructure.custody.custody_accounts import custody_book
    try:
        return custody_book.open_account(body.client_id, body.client_name, body.account_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/accounts/{account_id}/holdings")
async def get_holdings(account_id: str):
    from infrastructure.custody.custody_accounts import custody_book
    acct = custody_book.get_account(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account {account_id!r} not found")
    holdings = custody_book.get_holdings(account_id)
    total_mv = sum(h.get("market_value_usd", 0.0) for h in holdings)
    return {
        "account": acct,
        "holdings": holdings,
        "total_market_value_usd": round(total_mv, 2),
    }


@router.post("/accounts/{account_id}/holdings")
async def book_holding(account_id: str, body: BookHoldingRequest):
    from infrastructure.custody.custody_accounts import custody_book
    acct = custody_book.get_account(account_id)
    if not acct:
        raise HTTPException(status_code=404, detail=f"Account {account_id!r} not found")
    return custody_book.book_holding(account_id, body.isin, body.description, body.quantity, body.price_usd)


# ── AuC endpoint ─────────────────────────────────────────────────────────────

@router.get("/auc")
async def total_auc():
    from infrastructure.custody.custody_accounts import custody_book
    return custody_book.get_total_auc()


# ── Settlement endpoints ─────────────────────────────────────────────────────

@router.post("/settlement/instruct")
async def instruct(body: InstructRequest):
    from infrastructure.custody.settlement import settlement_engine
    try:
        return settlement_engine.instruct(
            isin=body.isin,
            quantity=body.quantity,
            price_usd=body.price_usd,
            side=body.side,
            account_id=body.account_id,
            description=body.description,
            asset_class=body.asset_class,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/settlement/{instruction_id}/affirm")
async def affirm(instruction_id: str):
    from infrastructure.custody.settlement import settlement_engine
    try:
        return settlement_engine.affirm(instruction_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/settlement/settle-batch")
async def settle_batch(settle_date: Optional[str] = None):
    from infrastructure.custody.settlement import settlement_engine
    return settlement_engine.settle_batch(settle_date)


@router.get("/settlement/pending")
async def pending_settlements():
    from infrastructure.custody.settlement import settlement_engine
    instructions = settlement_engine.get_pending()
    return {"instructions": instructions, "count": len(instructions)}


# ── Corporate Actions endpoints ───────────────────────────────────────────────

@router.get("/corporate-actions")
async def list_corporate_actions():
    from infrastructure.custody.corporate_actions import corporate_action_processor
    return {"corporate_actions": corporate_action_processor.get_all_actions()}


@router.get("/corporate-actions/pending")
async def pending_corporate_actions():
    from infrastructure.custody.corporate_actions import corporate_action_processor
    actions = corporate_action_processor.get_pending_actions()
    return {"corporate_actions": actions, "count": len(actions)}


@router.post("/corporate-actions")
async def add_corporate_action(body: AddCARequest):
    from infrastructure.custody.corporate_actions import corporate_action_processor
    try:
        return corporate_action_processor.add_action(
            ca_type=body.ca_type,
            isin=body.isin,
            issuer=body.issuer,
            ex_date=body.ex_date,
            record_date=body.record_date,
            pay_date=body.pay_date,
            details=body.details,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/corporate-actions/{ca_id}/process")
async def process_corporate_action(ca_id: str):
    from infrastructure.custody.corporate_actions import corporate_action_processor
    try:
        return corporate_action_processor.process(ca_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
