from __future__ import annotations

from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/collateral", tags=["collateral"])


# ── VM / CSA routes ─────────────────────────────────────────────────────────

@router.get("/summary")
async def collateral_summary():
    from infrastructure.collateral.vm_engine import vm_engine
    return vm_engine.get_portfolio_summary()


@router.get("/accounts")
async def collateral_accounts():
    from infrastructure.collateral.vm_engine import vm_engine
    return {"accounts": [a.to_dict() for a in vm_engine.get_all_accounts()]}


@router.get("/csas")
async def collateral_csas():
    from infrastructure.collateral.vm_engine import vm_engine
    return {"csas": [c.to_dict() for c in vm_engine.get_all_csas()]}


@router.get("/calls")
async def collateral_calls(status: str | None = None):
    from infrastructure.collateral.vm_engine import vm_engine
    calls = vm_engine.get_all_calls() if status == "all" else vm_engine.get_open_calls()
    return {"calls": [c.to_dict() for c in calls], "count": len(calls)}


# ── SIMM routes ─────────────────────────────────────────────────────────────

@router.get("/simm/sample")
async def simm_sample():
    """Compute SIMM IM on the representative Apex portfolio."""
    from infrastructure.collateral.simm import simm_engine
    result = simm_engine.compute_sample_portfolio()
    return result.to_dict()


class SIMMRequest(BaseModel):
    ir_deltas: list[dict] = []   # [{tenor, dv01_usd}]
    crq_deltas: list[dict] = []  # [{issuer_id, cs01_usd, rating}]


@router.post("/simm/compute")
async def simm_compute(req: SIMMRequest):
    from infrastructure.collateral.simm import simm_engine, SIMMInput, IRDelta, CRQDelta
    try:
        inputs = SIMMInput(
            ir_deltas=[IRDelta(**d) for d in req.ir_deltas],
            crq_deltas=[CRQDelta(**d) for d in req.crq_deltas],
        )
        result = simm_engine.compute(inputs)
        return result.to_dict()
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc))


# ── Close-out netting ────────────────────────────────────────────────────────

@router.get("/close-out/{counterparty_id}")
async def close_out(counterparty_id: str):
    """Compute close-out netting for a given counterparty at current MTM."""
    from infrastructure.collateral.vm_engine import vm_engine
    # Use the engine's seeded opening MTM as the current snapshot
    mtm_snapshot = dict(vm_engine._prev_mtm)
    result = vm_engine.compute_close_out(
        counterparty_id=counterparty_id,
        current_mtm_by_csa=mtm_snapshot,
    )
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


# ── Stress scenarios ────────────────────────────────────────────────────────

class ScenarioRequest(BaseModel):
    scenario: str  # "covid_week" | "lehman_event" | "gilt_crisis"
    params: dict = {}


@router.post("/scenario")
async def run_collateral_scenario(req: ScenarioRequest):
    from infrastructure.collateral.stress_scenarios import CollateralStressScenarios
    scenarios = CollateralStressScenarios()

    try:
        if req.scenario == "covid_week":
            result = scenarios.run_covid_week()
        elif req.scenario == "lehman_event":
            cp_id = req.params.get("counterparty_id", "CP004")
            result = scenarios.run_lehman_event(defaulting_counterparty_id=cp_id)
        elif req.scenario == "gilt_crisis":
            shock = float(req.params.get("bond_price_shock_pct", -0.12))
            result = scenarios.run_gilt_crisis(bond_price_shock_pct=shock)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown scenario: {req.scenario!r}. "
                                "Use: covid_week | lehman_event | gilt_crisis")
        return result.to_dict()
    except HTTPException:
        raise
    except Exception as exc:
        log.error("collateral.scenario_error", scenario=req.scenario, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
