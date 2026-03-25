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
