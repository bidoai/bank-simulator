"""FastAPI routes for the Risk Management dashboard."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.params import Body
from pydantic import BaseModel

from infrastructure.risk.risk_service import risk_service
from infrastructure.risk.counterparty_registry import counterparty_registry
from infrastructure.risk.var_calculator import VaRCalculator
from infrastructure.risk.risk_position_reader import RiskPositionReader
from models.legal_entity import get_all_entities

router = APIRouter(prefix="/risk", tags=["risk"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/snapshot")
def get_snapshot() -> dict[str, Any]:
    """Full risk snapshot: VaR by desk, limit utilisation, counterparty summary."""
    return {
        "risk": risk_service.run_snapshot(),
        "counterparties": counterparty_registry.get_summary(),
        "counterparty_warnings": [
            c for c in counterparty_registry.get_report()
            if c["limit_status"] != "GREEN"
        ],
    }


@router.get("/limits")
def get_limits() -> list[dict]:
    """Full limit report sorted by utilisation."""
    return risk_service.limit_manager.get_report()


@router.get("/limits/summary")
def get_limits_summary() -> dict:
    """Top-level limit health summary."""
    return risk_service.limit_manager.get_summary()


@router.get("/counterparties")
def get_counterparties() -> list[dict]:
    """All counterparties sorted by PFE utilisation."""
    return counterparty_registry.get_report()


@router.get("/counterparties/summary")
def get_counterparties_summary() -> dict:
    """Counterparty health summary."""
    return counterparty_registry.get_summary()


class VaRRequest(BaseModel):
    positions: dict[str, float] = {"SPX": 10_000_000}
    vols: dict[str, float] = {"SPX": 0.20}
    confidence: float = 0.99


@router.post("/var")
def compute_var(body: Optional[VaRRequest] = Body(default=None)) -> dict:
    """Run Monte Carlo VaR on supplied positions (or default SPX position)."""
    if body is None:
        body = VaRRequest()
    calc = VaRCalculator(confidence=body.confidence, horizon_days=1)
    result = calc.monte_carlo_var(
        positions=body.positions,
        vols=body.vols,
        book_id="custom",
    )
    return {
        "book_id": result.book_id,
        "var_amount": float(result.var_amount),
        "cvar_amount": float(result.cvar_amount) if result.cvar_amount else None,
        "method": result.method,
        "confidence_level": float(result.confidence_level),
        "horizon_days": result.horizon_days,
    }


@router.get("/positions")
def get_positions() -> dict:
    """Firm-wide position report from PositionManager."""
    return risk_service.get_position_report()


@router.get("/entities")
def get_entities() -> list[dict]:
    """All Apex legal entities (booking model)."""
    return get_all_entities()


@router.get("/independence-check")
def independence_check() -> dict:
    """
    3LoD CQRS independence check.

    Compares PositionManager (1st-line, in-memory) notional against
    RiskPositionReader (2nd-line, EventLog-sourced) notional.
    Divergence > 1% indicates a control gap.
    """
    pm_notional = risk_service.position_manager.get_firm_report().get("gross_notional", 0.0)

    reader = RiskPositionReader()
    rpr_notional = reader.total_notional()

    if pm_notional > 0:
        divergence_pct = abs(pm_notional - rpr_notional) / pm_notional * 100
    else:
        divergence_pct = 0.0

    status = "ALIGNED" if divergence_pct < 1.0 else "DIVERGED"
    return {
        "pm_total_notional": pm_notional,
        "rpr_total_notional": rpr_notional,
        "divergence_pct": round(divergence_pct, 4),
        "status": status,
    }
