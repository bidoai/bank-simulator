"""
FastAPI routes for Liquidity Risk dashboard.
Prefix: /liquidity (mounted at /api by main.py)
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/liquidity", tags=["liquidity"])


class StressRequest(BaseModel):
    scenario: str  # "idiosyncratic" | "market_wide" | "combined"


@router.get("/lcr")
async def get_lcr() -> dict[str, Any]:
    from infrastructure.liquidity.lcr import lcr_engine
    return lcr_engine.calculate()


@router.get("/nsfr")
async def get_nsfr() -> dict[str, Any]:
    from infrastructure.liquidity.nsfr import nsfr_engine
    return nsfr_engine.calculate()


@router.get("/stress")
async def get_liquidity_stress() -> dict[str, Any]:
    from infrastructure.liquidity.stress_scenarios import liquidity_stress_engine
    return {"scenarios": liquidity_stress_engine.run_all_scenarios()}


@router.post("/stress")
async def run_liquidity_stress(body: StressRequest) -> dict[str, Any]:
    from infrastructure.liquidity.stress_scenarios import liquidity_stress_engine
    valid = {"idiosyncratic", "market_wide", "combined"}
    if body.scenario not in valid:
        raise HTTPException(status_code=422, detail=f"scenario must be one of {sorted(valid)}")
    return liquidity_stress_engine.run_scenario(body.scenario)


@router.get("/intraday")
async def get_intraday() -> dict[str, Any]:
    from infrastructure.liquidity.intraday import intraday_monitor
    return intraday_monitor.get_daily_summary()


@router.get("/ladder")
async def get_liquidity_ladder() -> dict[str, Any]:
    from infrastructure.liquidity.ladder import liquidity_ladder
    return {"ladder": liquidity_ladder.get_ladder(), "summary": liquidity_ladder.get_summary()}
