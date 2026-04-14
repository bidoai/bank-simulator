from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/loans", tags=["loans"])


class OriginateRequest(BaseModel):
    borrower_id: str
    borrower_name: str
    facility_type: str          # TERM | REVOLVER | BULLET
    notional_usd: float
    rate_pct: float
    tenor_years: float
    sector: str = "CORPORATE"
    collateral_type: str = "UNSECURED"
    grade: str = "BBB"


class RepayRequest(BaseModel):
    amount_usd: float


@router.post("/originate")
async def originate_loan(body: OriginateRequest):
    from infrastructure.credit.loan_book import loan_book
    try:
        return loan_book.originate(
            borrower_id=body.borrower_id,
            borrower_name=body.borrower_name,
            facility_type=body.facility_type,
            notional_usd=body.notional_usd,
            rate_pct=body.rate_pct,
            tenor_years=body.tenor_years,
            sector=body.sector,
            collateral_type=body.collateral_type,
            grade=body.grade,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/portfolio")
async def get_portfolio():
    from infrastructure.credit.loan_book import loan_book
    return {"loans": loan_book.get_portfolio()}


@router.get("/portfolio/summary")
async def get_portfolio_summary():
    from infrastructure.credit.loan_book import loan_book
    return loan_book.get_portfolio_summary()


@router.get("/ecl")
async def get_loan_ecl():
    """Live ECL on the loan book from IFRS9 engine."""
    from infrastructure.credit.ifrs9_ecl import ecl_engine, _live_portfolio
    from infrastructure.credit.loan_book import loan_book
    # Use live portfolio (includes dynamically originated loans)
    result = ecl_engine.portfolio_ecl(_live_portfolio)
    summary = loan_book.get_portfolio_summary()
    return {
        **result,
        "loan_book_outstanding_usd": summary["total_outstanding_usd"],
        "loan_book_ecl_usd": summary["total_ecl_usd"],
        "loan_book_coverage_ratio": summary["ecl_coverage_ratio"],
    }


@router.get("/{loan_id}/amortization")
async def get_amortization(loan_id: str):
    from infrastructure.credit.loan_book import loan_book
    try:
        schedule = loan_book.get_amortization(loan_id)
        return {"loan_id": loan_id, "schedule": schedule, "periods": len(schedule)}
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/{loan_id}/repay")
async def repay_loan(loan_id: str, body: RepayRequest):
    from infrastructure.credit.loan_book import loan_book
    try:
        return loan_book.repay(loan_id, body.amount_usd)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/{loan_id}")
async def get_loan(loan_id: str):
    from infrastructure.credit.loan_book import loan_book
    loan = loan_book.get_loan(loan_id)
    if not loan:
        raise HTTPException(status_code=404, detail=f"Loan {loan_id!r} not found")
    return loan
