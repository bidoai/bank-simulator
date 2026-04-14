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


# ── Historical Crisis Replay endpoints (T3-D) ────────────────────────────────

@router.get("/crisis/scenarios")
def get_crisis_scenarios() -> dict:
    """Return the three historical crisis scenario definitions and shock parameters."""
    from infrastructure.stress.crisis_replay import crisis_replay_engine
    return crisis_replay_engine.get_scenarios()


@router.get("/crisis/replay-all")
def run_all_crisis_replays() -> dict:
    """Run all three crisis scenarios against live positions — comparative summary."""
    from infrastructure.stress.crisis_replay import crisis_replay_engine
    return crisis_replay_engine.run_all_scenarios()


@router.get("/crisis/replay/{scenario_id}")
def run_crisis_replay(scenario_id: str) -> dict:
    """Run a single crisis scenario against live positions. IDs: GFC_2008 | COVID_2020 | UK_GILT_2022."""
    from infrastructure.stress.crisis_replay import crisis_replay_engine, CRISIS_SCENARIOS
    if scenario_id not in CRISIS_SCENARIOS:
        raise HTTPException(status_code=404, detail=f"Unknown scenario: {scenario_id!r}")
    return crisis_replay_engine.run_replay(scenario_id)
