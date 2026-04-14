"""
Operational Risk routes — Basel III BIA capital, loss event database, RCSA.

Prefix: /api/oprisk
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/oprisk", tags=["oprisk"])


# ── Summary ───────────────────────────────────────────────────────────────────

@router.get("/summary")
async def oprisk_summary():
    """BIA capital charge + loss event statistics combined."""
    from infrastructure.risk.oprisk_capital import oprisk_engine
    from infrastructure.risk.loss_event_db import loss_event_db

    bia   = oprisk_engine.calculate_bia()
    basic = oprisk_engine.calculate_basic_indicator()
    loss_summary = loss_event_db.get_summary()

    return {
        "bia":               bia,
        "basic_indicator":   basic,
        "loss_events":       loss_summary,
    }


# ── Loss events ───────────────────────────────────────────────────────────────

class LossEventRequest(BaseModel):
    business_line:  str
    event_type:     str
    gross_loss_usd: float = Field(gt=0)
    recovery_usd:   float = Field(default=0.0, ge=0)
    description:    str
    event_date:     str | None = None   # ISO date YYYY-MM-DD; defaults to today


@router.post("/loss-events", status_code=201)
async def record_loss_event(req: LossEventRequest):
    """Record a new operational risk loss event."""
    from infrastructure.risk.loss_event_db import loss_event_db
    try:
        event = loss_event_db.record_event(
            business_line=req.business_line,
            event_type=req.event_type,
            gross_loss_usd=req.gross_loss_usd,
            recovery_usd=req.recovery_usd,
            description=req.description,
            event_date=req.event_date,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return event


@router.get("/loss-events")
async def list_loss_events(
    business_line: str | None = None,
    start_date:    str | None = None,
    end_date:      str | None = None,
    limit:         int = 100,
):
    """List loss events, optionally filtered by business line and date range."""
    from infrastructure.risk.loss_event_db import loss_event_db
    return loss_event_db.get_events(
        business_line=business_line,
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )


@router.get("/loss-events/{event_id}")
async def get_loss_event(event_id: str):
    from infrastructure.risk.loss_event_db import loss_event_db
    event = loss_event_db.get_event(event_id)
    if not event:
        raise HTTPException(status_code=404, detail="Loss event not found")
    return event


@router.get("/business-lines")
async def list_business_lines():
    from infrastructure.risk.loss_event_db import BUSINESS_LINES, EVENT_TYPES
    return {"business_lines": BUSINESS_LINES, "event_types": EVENT_TYPES}


# ── RCSA ──────────────────────────────────────────────────────────────────────

@router.get("/rcsa")
async def get_rcsa(business_line: str | None = None):
    """Return the RCSA control register, optionally filtered by business line."""
    from infrastructure.risk.rcsa import rcsa_framework
    return {
        "controls":   rcsa_framework.get_controls(business_line=business_line),
        "stats":      rcsa_framework.get_summary_stats(),
    }


@router.get("/rcsa/heat-map")
async def rcsa_heat_map():
    """Return residual risk heat map by business line."""
    from infrastructure.risk.rcsa import rcsa_framework
    return rcsa_framework.get_heat_map()


class EffectivenessUpdate(BaseModel):
    effectiveness: int = Field(ge=1, le=5)
    notes: str = ""


@router.patch("/rcsa/{control_id}")
async def update_control_effectiveness(control_id: str, body: EffectivenessUpdate):
    """Update a control's effectiveness score (1–5)."""
    from infrastructure.risk.rcsa import rcsa_framework
    try:
        updated = rcsa_framework.update_effectiveness(
            control_id, body.effectiveness, body.notes
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return updated
