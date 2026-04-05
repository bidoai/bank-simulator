"""FastAPI routes for DFAST/CCAR stress testing."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from infrastructure.stress.dfast_engine import dfast_engine, SCENARIOS

router = APIRouter(prefix="/stress", tags=["stress"])


@router.get("/dfast/meta")
def get_dfast_meta() -> dict:
    """Return the active scenario parameters and their calibration source."""
    return {
        "scenarios": SCENARIOS,
        "publication": "Federal Reserve Board — 2025 Supervisory Scenarios (Feb 5, 2025)",
        "horizon_quarters": 9,
    }


@router.get("/dfast")
def get_dfast_all() -> dict:
    """Run all three DFAST scenarios (baseline, adverse, severely_adverse) × 9 quarters."""
    results = dfast_engine.run_all_scenarios(quarters=9)
    return {
        name: result.to_dict()
        for name, result in results.items()
    }


@router.get("/dfast/{scenario}")
def get_dfast_scenario(scenario: str) -> dict:
    """Run a single DFAST scenario. Scenarios: baseline | adverse | severely_adverse."""
    if scenario not in SCENARIOS:
        raise HTTPException(
            status_code=404,
            detail=f"Unknown scenario '{scenario}'. Valid: {list(SCENARIOS)}",
        )
    result = dfast_engine.run_scenario(scenario, quarters=9)
    return result.to_dict()
