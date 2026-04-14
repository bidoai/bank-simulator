"""FastAPI routes for the AML compliance monitoring engine."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.compliance.aml_monitor import aml_monitor

router = APIRouter(prefix="/compliance", tags=["compliance"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/aml/alerts")
def get_open_alerts() -> list[dict]:
    return aml_monitor.get_open_alerts()


@router.get("/aml/stats")
def get_alert_stats() -> dict:
    return aml_monitor.get_alert_stats()


class ScreenRequest(BaseModel):
    counterparty: str
    amount_usd: float
    tx_type: str


@router.post("/aml/screen")
def screen_transaction(body: ScreenRequest) -> dict:
    alerts = aml_monitor.screen_transaction(
        tx_id=str(uuid.uuid4()),
        counterparty=body.counterparty,
        amount_usd=body.amount_usd,
        tx_type=body.tx_type,
    )
    return {
        "alerts_raised": len(alerts),
        "alerts": [a.to_dict() for a in alerts],
        "clean": len(alerts) == 0,
    }


class StatusUpdate(BaseModel):
    status: str


@router.patch("/aml/alerts/{alert_id}")
def update_alert_status(alert_id: str, body: StatusUpdate) -> dict:
    valid_statuses = {"reviewed", "escalated", "closed"}
    if body.status not in valid_statuses:
        raise HTTPException(
            status_code=422,
            detail=f"status must be one of: {', '.join(sorted(valid_statuses))}",
        )
    updated = aml_monitor.update_alert_status(alert_id, body.status)
    if not updated:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return {"alert_id": alert_id, "status": body.status, "updated": True}


# ---------------------------------------------------------------------------
# Volcker Rule Attribution
# ---------------------------------------------------------------------------

@router.get("/volcker/report")
def volcker_report() -> dict:
    """Portfolio Volcker attribution — notional by classification class."""
    from infrastructure.compliance.volcker import volcker_engine
    from infrastructure.risk.risk_service import risk_service
    positions = risk_service.position_manager.get_all_positions()
    return volcker_engine.get_portfolio_attribution(positions)


@router.get("/volcker/flags")
def volcker_flags() -> dict:
    """Return positions classified as PROHIBITED_PROP with notional ≥ $1M."""
    from infrastructure.compliance.volcker import volcker_engine
    from infrastructure.risk.risk_service import risk_service
    positions = risk_service.position_manager.get_all_positions()
    return volcker_engine.get_compliance_report(positions)


class VolckerClassifyRequest(BaseModel):
    desk: str
    product_subtype: str | None = None
    tenor_years: float | None = None
    counterparty_id: str | None = None
    notional: float | None = None


@router.post("/volcker/classify")
def classify_single_trade(body: VolckerClassifyRequest) -> dict:
    """Classify a hypothetical trade under the Volcker Rule."""
    from infrastructure.compliance.volcker import classify_trade, VolckerClass
    vc = classify_trade(
        desk=body.desk,
        product_subtype=body.product_subtype,
        tenor_years=body.tenor_years,
        counterparty_id=body.counterparty_id,
        notional=body.notional,
    )
    return {
        "volcker_classification": vc.value,
        "is_prohibited": vc == VolckerClass.PROHIBITED_PROP,
        "description": {
            "MARKET_MAKING":           "Permitted — inventory held to service client orders",
            "PERMITTED_HEDGING":       "Permitted — hedging existing bank risk exposure",
            "CUSTOMER_FACILITATION":   "Permitted — executing on behalf of a customer",
            "UNDERWRITING":            "Permitted — underwriting securities distribution",
            "REPO_SECURITIES_FINANCE": "Permitted — repo/securities lending activity",
            "PROHIBITED_PROP":         "PROHIBITED — principal risk-taking with no client nexus",
        }.get(vc.value, ""),
    }
