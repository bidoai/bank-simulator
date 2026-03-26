"""FastAPI routes for stress test scenario runner."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from api.scenario_state import scenario_state

router = APIRouter(prefix="/scenarios", tags=["scenarios"])

# ---------------------------------------------------------------------------
# Scenario library
# ---------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "gfc": {
        "name": "Global Financial Crisis (Oct 2008 – Sep 2009)",
        "description": "Calibrated to GFC stressed period per Basel §277-278",
        "shocks": {
            "ir_sigma_multiplier": 2.57,
            "fx_vol_multiplier": 1.89,
            "eq_vol_multiplier": 2.03,
            "credit_spread_multiplier": 2.67,
        },
        "stress_multiplier": 1.42,
    },
    "covid": {
        "name": "COVID-19 Market Dislocation (Mar 2020)",
        "description": "March 2020 equity crash and rates compression",
        "shocks": {
            "ir_sigma_multiplier": 1.60,
            "fx_vol_multiplier": 1.55,
            "eq_vol_multiplier": 2.80,
            "credit_spread_multiplier": 1.90,
        },
        "stress_multiplier": 1.21,
    },
    "rate_shock_200bp": {
        "name": "Parallel Rate Shock +200bp",
        "description": "Instantaneous +200bp shift in all IR curves",
        "shocks": {
            "ir_level_shift": 0.02,
            "fx_vol_multiplier": 1.20,
            "eq_vol_multiplier": 1.30,
            "credit_spread_multiplier": 1.40,
        },
        "stress_multiplier": 1.18,
    },
    "credit_widening": {
        "name": "Credit Spread Widening ×3",
        "description": "Investment grade credit spreads triple; HY spreads ×4",
        "shocks": {
            "ig_spread_multiplier": 3.0,
            "hy_spread_multiplier": 4.0,
            "credit_spread_multiplier": 3.0,
        },
        "stress_multiplier": 1.85,
    },
    "custom": {
        "name": "Custom Scenario",
        "description": "User-defined shocks",
        "shocks": {},
        "stress_multiplier": 1.0,
    },
}

# ---------------------------------------------------------------------------
# Baseline mock XVA values (USD millions unless noted)
# ---------------------------------------------------------------------------

_BASELINE = {
    "cva": -0.42,       # negative = cost to bank
    "dva": 0.08,
    "fva": -0.15,
    "mva": -0.03,
    "kva": -0.05,
    "pfe_peak_mm": 7.20,
    "eepe_mm": 4.85,
    # PFE time profile (20 quarterly steps, years 0.25 … 5.0)
    "pfe_profile": [
        1.2, 2.1, 3.0, 3.9, 4.8, 5.4, 6.0, 6.5, 6.9, 7.2,
        7.0, 6.7, 6.3, 5.8, 5.3, 4.7, 4.0, 3.2, 2.3, 1.4,
    ],
    "time_grid": [
        0.25, 0.50, 0.75, 1.00, 1.25, 1.50, 1.75, 2.00, 2.25, 2.50,
        2.75, 3.00, 3.25, 3.50, 3.75, 4.00, 4.25, 4.50, 4.75, 5.00,
    ],
}


def _compute_stressed(multiplier: float) -> dict[str, Any]:
    """Apply stress multiplier to baseline XVA metrics."""
    pfe_mult = multiplier * 0.8
    return {
        "cva": round(_BASELINE["cva"] * multiplier, 4),
        "dva": round(_BASELINE["dva"] * multiplier, 4),
        "fva": round(_BASELINE["fva"] * multiplier, 4),
        "mva": round(_BASELINE["mva"] * multiplier, 4),
        "kva": round(_BASELINE["kva"] * multiplier, 4),
        "pfe_peak_mm": round(_BASELINE["pfe_peak_mm"] * pfe_mult, 2),
        "eepe_mm": round(_BASELINE["eepe_mm"] * pfe_mult, 2),
        "pfe_profile": [round(v * pfe_mult, 3) for v in _BASELINE["pfe_profile"]],
        "time_grid": _BASELINE["time_grid"],
    }


def _change_table(baseline: dict, stressed: dict) -> list[dict[str, Any]]:
    """Build comparison rows for scalar metrics."""
    metrics = ["cva", "dva", "fva", "mva", "kva", "pfe_peak_mm", "eepe_mm"]
    rows = []
    for m in metrics:
        b = baseline[m]
        s = stressed[m]
        delta_abs = round(s - b, 4)
        delta_pct = round((s - b) / abs(b) * 100, 1) if b != 0 else None
        rows.append({
            "metric": m.upper(),
            "baseline": b,
            "stressed": s,
            "delta_abs": delta_abs,
            "delta_pct": delta_pct,
        })
    return rows


# ---------------------------------------------------------------------------
# Pydantic request model
# ---------------------------------------------------------------------------

class RunRequest(BaseModel):
    scenario_id: str = "gfc"
    custom_shocks: dict[str, float] = {}


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/list")
async def list_scenarios() -> JSONResponse:
    """Return all scenario keys with name and description."""
    items = [
        {
            "id": k,
            "name": v["name"],
            "description": v["description"],
            "shocks": v["shocks"],
            "stress_multiplier": v["stress_multiplier"],
        }
        for k, v in SCENARIOS.items()
    ]
    return JSONResponse({"scenarios": items})


@router.post("/run")
async def run_scenario(req: RunRequest) -> JSONResponse:
    """
    Run a stress scenario against baseline XVA.

    For predefined scenarios uses the configured stress_multiplier.
    For 'custom', the caller may supply custom_shocks; we derive a
    rough multiplier from the average shock magnitude.
    """
    scenario_id = req.scenario_id
    if scenario_id not in SCENARIOS:
        return JSONResponse(
            {"error": f"Unknown scenario_id '{scenario_id}'. "
             f"Valid ids: {list(SCENARIOS.keys())}"},
            status_code=422,
        )

    scenario = SCENARIOS[scenario_id]

    # Resolve multiplier
    if scenario_id == "custom" and req.custom_shocks:
        # Simple heuristic: average of supplied shock values capped at 4×
        vals = [v for v in req.custom_shocks.values() if isinstance(v, (int, float)) and v > 0]
        multiplier = round(min(sum(vals) / len(vals), 4.0), 3) if vals else 1.0
    else:
        multiplier = scenario["stress_multiplier"]

    baseline = {k: v for k, v in _BASELINE.items()}
    stressed = _compute_stressed(multiplier)

    return JSONResponse({
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "stress_multiplier": multiplier,
        "shocks_applied": req.custom_shocks if scenario_id == "custom" else scenario["shocks"],
        "baseline": {
            "cva": baseline["cva"],
            "dva": baseline["dva"],
            "fva": baseline["fva"],
            "mva": baseline["mva"],
            "kva": baseline["kva"],
            "pfe_peak_mm": baseline["pfe_peak_mm"],
            "eepe_mm": baseline["eepe_mm"],
            "pfe_profile": baseline["pfe_profile"],
            "time_grid": baseline["time_grid"],
        },
        "stressed": stressed,
        "change_table": _change_table(baseline, stressed),
    })


@router.post("/activate")
async def activate_scenario(req: RunRequest) -> JSONResponse:
    """
    Activate a scenario so the boardroom agents respond to it in character.

    The active scenario is injected into every agent's prompt on the next
    meeting. Only one scenario can be active at a time — calling this again
    replaces the current one.
    """
    scenario_id = req.scenario_id
    if scenario_id not in SCENARIOS:
        return JSONResponse(
            {"error": f"Unknown scenario_id '{scenario_id}'."},
            status_code=422,
        )
    scenario = SCENARIOS[scenario_id]
    shocks = req.custom_shocks if scenario_id == "custom" and req.custom_shocks else scenario["shocks"]
    scenario_state.activate(scenario_id, scenario["name"], shocks)
    return JSONResponse({
        "activated": True,
        "scenario_id": scenario_id,
        "scenario_name": scenario["name"],
        "shocks": shocks,
    })


@router.delete("/activate")
async def deactivate_scenario() -> JSONResponse:
    """Clear the active scenario — agents return to normal discussion."""
    scenario_state.deactivate()
    return JSONResponse({"deactivated": True})


@router.get("/active")
async def get_active_scenario() -> JSONResponse:
    """Return the currently active scenario, or active=false if none."""
    return JSONResponse(scenario_state.snapshot())


@router.get("/library")
async def scenario_library() -> JSONResponse:
    """Return the last 5 historical stress test runs (mock data)."""
    history = [
        {
            "run_id": "ST-2026-0312-001",
            "date": "2026-03-12",
            "scenario": "Global Financial Crisis (Oct 2008 – Sep 2009)",
            "scenario_id": "gfc",
            "peak_pfe_mm": 10.22,
            "cva_change_pct": 42.0,
            "status": "PASS",
            "notes": "Quarterly regulatory stress test — within CVA limits",
        },
        {
            "run_id": "ST-2026-0228-001",
            "date": "2026-02-28",
            "scenario": "COVID-19 Market Dislocation (Mar 2020)",
            "scenario_id": "covid",
            "peak_pfe_mm": 6.91,
            "cva_change_pct": 21.0,
            "status": "PASS",
            "notes": "Monthly scenario review",
        },
        {
            "run_id": "ST-2026-0214-002",
            "date": "2026-02-14",
            "scenario": "Parallel Rate Shock +200bp",
            "scenario_id": "rate_shock_200bp",
            "peak_pfe_mm": 6.80,
            "cva_change_pct": 18.0,
            "status": "PASS",
            "notes": "IRRBB supplementary test",
        },
        {
            "run_id": "ST-2026-0131-001",
            "date": "2026-01-31",
            "scenario": "Credit Spread Widening ×3",
            "scenario_id": "credit_widening",
            "peak_pfe_mm": 13.32,
            "cva_change_pct": 85.0,
            "status": "FAIL",
            "notes": "CVA exceeded 150% of base limit — escalated to CRO",
        },
        {
            "run_id": "ST-2025-1231-001",
            "date": "2025-12-31",
            "scenario": "Custom Scenario",
            "scenario_id": "custom",
            "peak_pfe_mm": 8.10,
            "cva_change_pct": 33.5,
            "status": "PASS",
            "notes": "Year-end bespoke geopolitical shock scenario",
        },
    ]
    return JSONResponse({"library": history, "count": len(history)})
