from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/deposits", tags=["deposits"])


class OpenAccountRequest(BaseModel):
    account_type: str           # CHECKING | SAVINGS | TERM
    customer_segment: str       # RETAIL | SME | CORPORATE
    customer_name: str
    initial_deposit: float = 0.0
    rate_pct: float = 0.0
    tenor_days: Optional[int] = None


class TransactionRequest(BaseModel):
    amount_usd: float


@router.post("/accounts")
async def open_account(body: OpenAccountRequest):
    from infrastructure.treasury.deposits import deposit_book
    try:
        return deposit_book.open_account(
            account_type=body.account_type,
            customer_segment=body.customer_segment,
            customer_name=body.customer_name,
            initial_deposit=body.initial_deposit,
            rate_pct=body.rate_pct,
            tenor_days=body.tenor_days,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/portfolio")
async def get_portfolio():
    from infrastructure.treasury.deposits import deposit_book
    return {"accounts": deposit_book.get_portfolio()}


@router.get("/portfolio/summary")
async def get_portfolio_summary():
    from infrastructure.treasury.deposits import deposit_book
    return deposit_book.get_portfolio_summary()


@router.get("/nmd-profile")
async def nmd_profile():
    from infrastructure.treasury.deposits import deposit_book
    return deposit_book.get_nmd_profile()


@router.get("/interest-expense")
async def interest_expense():
    from infrastructure.treasury.deposits import deposit_book
    return deposit_book.get_interest_expense()


@router.get("/{account_id}")
async def get_account(account_id: str):
    from infrastructure.treasury.deposits import deposit_book
    account = deposit_book.get_account(account_id)
    if not account:
        raise HTTPException(status_code=404, detail=f"Account {account_id!r} not found")
    return account


@router.post("/{account_id}/deposit")
async def make_deposit(account_id: str, body: TransactionRequest):
    from infrastructure.treasury.deposits import deposit_book
    try:
        return deposit_book.deposit(account_id, body.amount_usd)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/{account_id}/withdraw")
async def make_withdrawal(account_id: str, body: TransactionRequest):
    from infrastructure.treasury.deposits import deposit_book
    try:
        return deposit_book.withdraw(account_id, body.amount_usd)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
