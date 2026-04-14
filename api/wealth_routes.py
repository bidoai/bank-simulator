from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/wealth", tags=["wealth"])


class ClientRequest(BaseModel):
    client_id: str
    client_name: str
    segment: str            # HNWI | UHNWI | FAMILY_OFFICE
    aum_usd: float
    mandate_type: str       # DISCRETIONARY | ADVISORY | EXECUTION_ONLY
    risk_profile: str       # CONSERVATIVE | BALANCED | GROWTH | AGGRESSIVE


class UpdateAUMRequest(BaseModel):
    new_aum_usd: float


class BillingRequest(BaseModel):
    period: str


@router.get("/clients")
async def get_clients():
    from infrastructure.wealth.client_book import client_book
    clients = client_book.get_all_clients()
    return {"clients": clients, "count": len(clients)}


@router.get("/clients/{client_id}")
async def get_client(client_id: str):
    from infrastructure.wealth.client_book import client_book
    client = client_book.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id!r} not found")
    return client


@router.get("/clients/{client_id}/holdings")
async def get_holdings(client_id: str):
    from infrastructure.wealth.client_book import client_book
    client = client_book.get_client(client_id)
    if not client:
        raise HTTPException(status_code=404, detail=f"Client {client_id!r} not found")
    holdings = client_book.get_holdings(client_id)
    total = sum(h.get("market_value_usd", 0.0) for h in holdings)
    return {
        "client": client,
        "holdings": holdings,
        "total_market_value_usd": round(total, 2),
    }


@router.post("/clients")
async def add_client(body: ClientRequest):
    from infrastructure.wealth.client_book import client_book
    try:
        return client_book.add_client(
            client_id=body.client_id,
            client_name=body.client_name,
            segment=body.segment,
            aum_usd=body.aum_usd,
            mandate_type=body.mandate_type,
            risk_profile=body.risk_profile,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.put("/clients/{client_id}/aum")
async def update_aum(client_id: str, body: UpdateAUMRequest):
    from infrastructure.wealth.client_book import client_book
    try:
        return client_book.update_aum(client_id, body.new_aum_usd)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/summary")
async def client_summary():
    from infrastructure.wealth.client_book import client_book
    return client_book.get_client_summary()


@router.get("/revenue")
async def fee_revenue():
    from infrastructure.wealth.client_book import client_book
    annual = client_book.calculate_annual_fees()
    return {
        "annual_fee_revenue_usd": round(annual, 2),
        "note": "AUM × fee_bps / 10000 across all active clients",
    }


@router.post("/billing/run")
async def run_billing(body: BillingRequest):
    from infrastructure.wealth.client_book import client_book
    accruals = client_book.bill_fees(body.period)
    total = sum(a["fee_usd"] for a in accruals)
    return {
        "period":          body.period,
        "clients_billed":  len(accruals),
        "total_fees_usd":  round(total, 2),
        "accruals":        accruals,
    }
