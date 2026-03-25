"""FastAPI routes for the IFRS 9 ECL credit portfolio engine."""
from __future__ import annotations

import dataclasses
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.credit.ifrs9_ecl import ecl_engine, _sample_portfolio, IFRSStage, Obligor

router = APIRouter(prefix="/credit", tags=["credit"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/ecl/portfolio")
def get_portfolio_ecl() -> dict:
    return ecl_engine.portfolio_ecl(_sample_portfolio)


@router.get("/ecl/obligors")
def get_obligors() -> list[dict]:
    results = []
    for ob in _sample_portfolio:
        ecl = ecl_engine.calculate_ecl(ob)
        results.append({
            "obligor_id": ob.obligor_id,
            "name": ob.name,
            "rating": ob.rating,
            "notional_usd": ob.notional_usd,
            "maturity_years": ob.maturity_years,
            **ecl,
        })
    return results


class ScenarioRequest(BaseModel):
    pd_multiplier: float = 1.0
    lgd_override: Optional[float] = None


@router.post("/ecl/scenario")
def run_ecl_scenario(body: ScenarioRequest) -> dict:
    if body.pd_multiplier <= 0:
        raise HTTPException(status_code=422, detail="pd_multiplier must be positive")
    if body.lgd_override is not None and not (0.0 < body.lgd_override <= 1.0):
        raise HTTPException(status_code=422, detail="lgd_override must be between 0 and 1")

    stressed: list[Obligor] = []
    for ob in _sample_portfolio:
        stressed_pd = min(ob.pd_1yr * body.pd_multiplier, 0.9999)
        stressed_lgd = body.lgd_override if body.lgd_override is not None else ob.lgd
        stressed.append(dataclasses.replace(ob, pd_1yr=stressed_pd, lgd=stressed_lgd))

    result = ecl_engine.portfolio_ecl(stressed)
    baseline = ecl_engine.portfolio_ecl(_sample_portfolio)

    result["scenario"] = {
        "pd_multiplier": body.pd_multiplier,
        "lgd_override": body.lgd_override,
        "baseline_ecl_usd": baseline["total_ecl_usd"],
        "stress_ecl_usd": result["total_ecl_usd"],
        "incremental_ecl_usd": round(result["total_ecl_usd"] - baseline["total_ecl_usd"], 2),
    }
    return result


@router.get("/ecl/stage/{stage}")
def get_obligors_by_stage(stage: int) -> list[dict]:
    if stage not in (1, 2, 3):
        raise HTTPException(status_code=422, detail="stage must be 1, 2, or 3")
    target = IFRSStage(stage)
    results = []
    for ob in _sample_portfolio:
        if ob.stage == target:
            ecl = ecl_engine.calculate_ecl(ob)
            results.append({
                "obligor_id": ob.obligor_id,
                "name": ob.name,
                "rating": ob.rating,
                "notional_usd": ob.notional_usd,
                "maturity_years": ob.maturity_years,
                **ecl,
            })
    return results
