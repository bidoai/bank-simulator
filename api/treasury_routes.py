from __future__ import annotations

from fastapi import APIRouter, HTTPException
import structlog

log = structlog.get_logger()
router = APIRouter(prefix="/treasury", tags=["treasury"])


def _get_positions() -> list[dict]:
    """Pull live positions from the shared PositionManager (owned by risk_service)."""
    from infrastructure.risk.risk_service import risk_service
    return risk_service.position_manager.get_all_positions()


def _get_desk_pnl() -> dict[str, float]:
    """Return desk-level total P&L keyed by desk name."""
    from infrastructure.risk.risk_service import risk_service
    firm = risk_service.get_position_report()
    return {
        desk: data.get("total_pnl", 0.0)
        for desk, data in firm.get("by_desk", {}).items()
        if "error" not in data
    }


# ── FTP routes ─────────────────────────────────────────────────────────────

@router.get("/ftp/summary")
async def ftp_summary():
    from infrastructure.treasury.ftp import ftp_engine
    return ftp_engine.get_ftp_summary(_get_positions())


@router.get("/ftp/adjusted-pnl")
async def ftp_adjusted_pnl():
    from infrastructure.treasury.ftp import ftp_engine
    return ftp_engine.get_adjusted_pnl(_get_positions(), _get_desk_pnl())


@router.get("/ftp/curve")
async def ftp_curve():
    from infrastructure.treasury.ftp import ftp_engine
    return {
        "curve": ftp_engine.curve.snapshot(),
        "liquidity_premiums_bps": ftp_engine.curve.LIQUIDITY_PREMIUM_BPS,
    }


# ── ALM routes ─────────────────────────────────────────────────────────────

@router.get("/alm/report")
async def alm_report():
    from infrastructure.treasury.alm import alm_engine
    return alm_engine.get_full_alm_report()


@router.get("/alm/nii-sensitivity")
async def alm_nii_sensitivity():
    from infrastructure.treasury.alm import alm_engine
    return alm_engine.nii_sensitivity()


@router.get("/alm/eve-sensitivity")
async def alm_eve_sensitivity():
    from infrastructure.treasury.alm import alm_engine
    result = alm_engine.eve_sensitivity()
    if result.get("svb_warning"):
        log.warning("alm.svb_warning", detail=result["svb_warning_detail"])
    return result


@router.get("/alm/repricing-gap")
async def alm_repricing_gap():
    from infrastructure.treasury.alm import alm_engine
    return {
        "schedule": [p.to_dict() for p in alm_engine.get_repricing_gap_schedule()],
        "as_of": __import__("datetime").datetime.utcnow().isoformat(),
    }
