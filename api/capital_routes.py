"""FastAPI routes for the Regulatory Capital and Concentration Risk dashboard."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.params import Body
from pydantic import BaseModel

from infrastructure.risk.regulatory_capital import capital_engine
from infrastructure.risk.concentration_risk import concentration_monitor
from infrastructure.risk.risk_service import risk_service
from infrastructure.risk.correlation_regime import CorrelationRegime

router = APIRouter(prefix="/capital", tags=["capital"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/snapshot")
def get_capital_snapshot() -> dict[str, Any]:
    """Full capital adequacy snapshot using live portfolio positions."""
    positions = risk_service.position_manager.get_all_positions()
    return capital_engine.calculate(positions)


@router.get("/rwa")
def get_rwa() -> dict[str, Any]:
    """RWA breakdown by asset class."""
    positions = risk_service.position_manager.get_all_positions()
    result = capital_engine.calculate(positions)
    return {
        "rwa_total_usd": result["rwa_total_usd"],
        "rwa_by_asset_class": result["rwa_by_asset_class"],
        "as_of": result["as_of"],
    }


@router.get("/ratios")
def get_capital_ratios() -> dict[str, Any]:
    """CET1, Tier 1, Total Capital, and Leverage ratios."""
    positions = risk_service.position_manager.get_all_positions()
    result = capital_engine.calculate(positions)
    return {
        "cet1_ratio":          result["cet1_ratio"],
        "tier1_ratio":         result["tier1_ratio"],
        "total_capital_ratio": result["total_capital_ratio"],
        "leverage_ratio":      result["leverage_ratio"],
        "cet1_buffer":         result["cet1_buffer"],
        "cet1_vs_target":      result["cet1_vs_target"],
        "capital_adequate":    result["capital_adequate"],
        "breaches":            result["breaches"],
        "as_of":               result["as_of"],
    }


@router.get("/concentration")
def get_concentration() -> dict[str, Any]:
    """Concentration risk analysis — single-name, sector, geography."""
    positions = risk_service.position_manager.get_all_positions()
    result = concentration_monitor.analyze(positions)
    hhi = concentration_monitor.get_herfindahl_index(positions)
    return {**result, "herfindahl_index": round(hhi, 6)}


class StressRequest(BaseModel):
    regime: str = "stress"   # "stress" | "normal"


@router.post("/stress")
def run_stress_capital(body: Optional[StressRequest] = Body(default=None)) -> dict[str, Any]:
    """
    Capital snapshot under a stress scenario.
    Stress regime uses spiked correlations; normal uses historical correlations.
    Returns capital adequacy snapshot plus the active correlation regime.
    """
    if body is None:
        body = StressRequest()

    regime_str = (body.regime or "stress").lower()
    regime = CorrelationRegime.STRESS if regime_str == "stress" else CorrelationRegime.NORMAL

    positions = risk_service.position_manager.get_all_positions()
    capital_result = capital_engine.calculate(positions)
    concentration_result = concentration_monitor.analyze(positions)
    hhi = concentration_monitor.get_herfindahl_index(positions)

    return {
        "regime": regime.value,
        "capital": capital_result,
        "concentration": {**concentration_result, "herfindahl_index": round(hhi, 6)},
    }
