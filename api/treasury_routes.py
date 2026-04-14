from __future__ import annotations

from fastapi import APIRouter, HTTPException
import structlog

log = structlog.get_logger(__name__)
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


# ── NMD routes ──────────────────────────────────────────────────────────────

@router.get("/nmd")
async def nmd_analysis():
    from infrastructure.treasury.nmd_model import nmd_model
    return nmd_model.get_full_report()


# ── ALM Hedging routes ──────────────────────────────────────────────────────

@router.get("/alm/hedge-recommendations")
async def alm_hedge_recommendations():
    from infrastructure.treasury.alm_hedging import alm_hedging_engine
    return {
        "recommendations": alm_hedging_engine.get_hedge_recommendations(),
        "duration_gap": alm_hedging_engine.get_duration_gap(),
        "nii_at_risk": alm_hedging_engine.get_nii_at_risk(100),
        "as_of": __import__("datetime").datetime.utcnow().isoformat(),
    }


@router.get("/alm/krd")
async def alm_krd():
    from infrastructure.treasury.alm_hedging import alm_hedging_engine
    return {
        "key_rate_durations": alm_hedging_engine.get_key_rate_durations(),
        "duration_gap": alm_hedging_engine.get_duration_gap(),
        "as_of": __import__("datetime").datetime.utcnow().isoformat(),
    }


# ── Dynamic FTP routes ──────────────────────────────────────────────────────

@router.get("/ftp/curve-dynamic")
async def ftp_curve_dynamic():
    from infrastructure.treasury.ftp_dynamic import dynamic_ftp_engine
    return {
        "base_curve": dynamic_ftp_engine.get_funding_curve(),
        "idiosyncratic_stress": dynamic_ftp_engine.get_funding_curve("idiosyncratic"),
        "market_wide_stress": dynamic_ftp_engine.get_funding_curve("market_wide"),
        "liquidity_premiums_bps": {
            k: v for k, v in __import__(
                "infrastructure.treasury.ftp_dynamic",
                fromlist=["LIQUIDITY_PREMIUM_BPS"]
            ).LIQUIDITY_PREMIUM_BPS.items()
        },
        "as_of": __import__("datetime").datetime.utcnow().isoformat(),
    }


@router.get("/ftp/raroc")
async def ftp_raroc():
    from infrastructure.treasury.raroc import raroc_engine
    return raroc_engine.calculate_portfolio_raroc()


# ── Balance Sheet Optimization routes ──────────────────────────────────────

@router.get("/balance-sheet/optimization")
async def balance_sheet_optimization():
    from infrastructure.treasury.balance_sheet_optimizer import balance_sheet_optimizer
    return balance_sheet_optimizer.get_full_optimization_report()


# ── Consolidated Income Statement ───────────────────────────────────────────

@router.get("/income-statement")
async def income_statement(period: str = "annual"):
    """
    Consolidated income statement aggregating NII, trading P&L, fee revenue,
    provisions, and op risk charges. period: 'annual' | 'quarterly' | 'daily'.
    """
    if period not in ("annual", "quarterly", "daily"):
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="period must be annual, quarterly, or daily")
    from infrastructure.treasury.consolidated_pnl import income_statement as _is
    return _is.get_statement(period=period)


@router.get("/retained-earnings")
async def retained_earnings():
    """Retained earnings history and cumulative balance."""
    from infrastructure.treasury.retained_earnings import retained_earnings_ledger
    return retained_earnings_ledger.get_summary()


class AccruePeriodRequest:
    pass


@router.post("/retained-earnings/accrue")
async def accrue_period(body: dict):
    """
    Record a period's net income. Body: {period, net_income_usd, dividends_usd?, other_comprehensive_income?}
    """
    from fastapi import HTTPException
    from infrastructure.treasury.retained_earnings import retained_earnings_ledger
    period = body.get("period")
    net_income = body.get("net_income_usd")
    if not period or net_income is None:
        raise HTTPException(status_code=422, detail="period and net_income_usd are required")
    return retained_earnings_ledger.accrue_period(
        period=period,
        net_income_usd=float(net_income),
        dividends_usd=float(body.get("dividends_usd", 0.0)),
        other_comprehensive_income=float(body.get("other_comprehensive_income", 0.0)),
    )
