"""
Liquidity API routes — LCR, NSFR, stress scenarios, intraday, ladder.
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter(prefix="/liquidity", tags=["liquidity"])


class StressRequest(BaseModel):
    scenario: str  # "idiosyncratic" | "market_wide" | "combined"


def _lcr_engine():
    from infrastructure.liquidity.lcr import LCREngine
    return LCREngine()


def _nsfr_engine():
    from infrastructure.liquidity.nsfr import NSFREngine
    return NSFREngine()


def _stress_engine():
    from infrastructure.liquidity.stress_scenarios import LiquidityStressEngine
    return LiquidityStressEngine()


def _intraday_monitor():
    from infrastructure.liquidity.intraday import IntradayLiquidityMonitor
    return IntradayLiquidityMonitor()


def _ladder_engine():
    from infrastructure.liquidity.ladder import LiquidityLadder
    return LiquidityLadder()


@router.get("/lcr")
async def get_lcr() -> dict[str, Any]:
    return _lcr_engine().calculate()


@router.get("/nsfr")
async def get_nsfr() -> dict[str, Any]:
    return _nsfr_engine().calculate()


@router.get("/stress")
async def get_stress_all() -> dict[str, Any]:
    scenarios = _stress_engine().run_all_scenarios()
    return {"scenarios": scenarios}


@router.post("/stress")
async def post_stress(body: StressRequest) -> dict[str, Any]:
    valid = {"idiosyncratic", "market_wide", "combined"}
    if body.scenario not in valid:
        raise HTTPException(status_code=422, detail=f"scenario must be one of {sorted(valid)}")
    return _stress_engine().run_scenario(body.scenario)


@router.get("/intraday")
async def get_intraday() -> dict[str, Any]:
    return _intraday_monitor().get_daily_summary()


@router.get("/ladder")
async def get_ladder() -> dict[str, Any]:
    engine = _ladder_engine()
    return {
        "ladder": engine.get_ladder(),
        "survival_horizon": engine.get_survival_horizon(),
    }
