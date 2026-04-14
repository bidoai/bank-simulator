from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import structlog

log = structlog.get_logger(__name__)
router = APIRouter(prefix="/ibd", tags=["ibd"])


class DealRequest(BaseModel):
    deal_type: str                  # MA | ECM | DCM
    deal_name: str
    client_name: str
    deal_value_usd: float
    fee_rate: float
    stage: str = "ORIGINATION"


class AdvanceStageRequest(BaseModel):
    to_stage: str


@router.get("/pipeline")
async def get_pipeline(stage: Optional[str] = None):
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    deals = deal_pipeline.get_pipeline(stage)
    return {"deals": deals, "count": len(deals), "filter_stage": stage}


@router.get("/pipeline/{deal_id}")
async def get_deal(deal_id: str):
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    deal = deal_pipeline.get_deal(deal_id)
    if not deal:
        raise HTTPException(status_code=404, detail=f"Deal {deal_id!r} not found")
    return deal


@router.post("/deals")
async def add_deal(body: DealRequest):
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    try:
        return deal_pipeline.add_deal(
            deal_type=body.deal_type,
            deal_name=body.deal_name,
            client_name=body.client_name,
            deal_value_usd=body.deal_value_usd,
            fee_rate=body.fee_rate,
            stage=body.stage,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.post("/deals/{deal_id}/advance")
async def advance_stage(deal_id: str, body: AdvanceStageRequest):
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    try:
        return deal_pipeline.advance_stage(deal_id, body.to_stage)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@router.get("/league-table")
async def league_table():
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    return deal_pipeline.get_league_table()


@router.get("/revenue")
async def fee_revenue():
    from infrastructure.ibd.deal_pipeline import deal_pipeline
    annual = deal_pipeline.get_annual_fee_revenue()
    ytd = deal_pipeline.get_ytd_fee_revenue()
    return {
        "annual_fee_revenue_usd": round(annual, 2),
        "ytd_fee_revenue_usd":    round(ytd, 2),
        "note":                   "Annual total from all CLOSED deals; YTD = current calendar year only",
    }
