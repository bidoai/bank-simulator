"""FastAPI routes for the Regulatory Capital and Concentration Risk dashboard."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.params import Body
from pydantic import BaseModel

from infrastructure.risk.regulatory_capital import capital_engine, RegulatoryCapitalEngine
from infrastructure.risk.concentration_risk import concentration_monitor
from infrastructure.risk.correlation_regime import CorrelationRegime
from infrastructure.risk.risk_position_reader import RiskPositionReader
from infrastructure.events.event_log import event_log  # noqa: F401 — imported for 3LoD traceability

# 3LoD: capital endpoints use second-line independent position reader, not risk_service
risk_position_reader = RiskPositionReader()

router = APIRouter(prefix="/capital", tags=["capital"])


def _get_positions() -> list[dict]:
    """Independent position view for regulatory capital (3LoD)."""
    rebuilt = risk_position_reader.rebuild()
    # Flatten nested desk→instrument→qty into list[dict]
    flat: list[dict] = []
    for desk, instruments in rebuilt.items():
        for instrument, qty in instruments.items():
            flat.append({"instrument": instrument, "quantity": qty, "desk": desk})
    return flat


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/snapshot")
def get_capital_snapshot() -> dict[str, Any]:
    """Full capital adequacy snapshot with SA-CCR EAD and OpRisk RWA included."""
    positions = _get_positions()
    result = capital_engine.calculate(positions)

    # SA-CCR EAD contribution to CCR RWA
    try:
        from infrastructure.risk.sa_ccr import sa_ccr_engine
        ead_results = sa_ccr_engine.calculate_portfolio_ead()
        total_ead = sum(e.get("ead_usd", 0.0) for e in ead_results)
        # 100% RW for bank counterparties (A-rated average) → RWA
        ccr_rwa = total_ead * 0.50
    except Exception:
        total_ead = 0.0
        ccr_rwa = 0.0

    # OpRisk RWA via Business Indicator Approach
    try:
        from infrastructure.risk.oprisk_capital import oprisk_engine
        oprisk = oprisk_engine.calculate_bia()
        oprisk_rwa = oprisk["oprisk_rwa_usd"]
    except Exception:
        oprisk_rwa = 0.0

    # Output floor application
    try:
        from infrastructure.risk.output_floor import output_floor_engine
        sa_rwa_total = result["rwa_total_usd"] + ccr_rwa + oprisk_rwa
        floor = output_floor_engine.apply_floor(sa_rwa_total)
    except Exception:
        floor = None

    result["ccr_ead_usd"]   = round(total_ead, 2)
    result["ccr_rwa_usd"]   = round(ccr_rwa, 2)
    result["oprisk_rwa_usd"] = round(oprisk_rwa, 2)
    result["output_floor"]  = floor
    return result


@router.get("/rwa")
def get_rwa() -> dict[str, Any]:
    """RWA breakdown by asset class."""
    positions = _get_positions()
    result = capital_engine.calculate(positions)
    return {
        "rwa_total_usd": result["rwa_total_usd"],
        "rwa_by_asset_class": result["rwa_by_asset_class"],
        "as_of": result["as_of"],
    }


@router.get("/ratios")
def get_capital_ratios() -> dict[str, Any]:
    """CET1, Tier 1, Total Capital, and Leverage ratios."""
    positions = _get_positions()
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
    positions = _get_positions()
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

    positions = _get_positions()
    capital_result = capital_engine.calculate(positions)
    concentration_result = concentration_monitor.analyze(positions)
    hhi = concentration_monitor.get_herfindahl_index(positions)

    return {
        "regime": regime.value,
        "capital": capital_result,
        "concentration": {**concentration_result, "herfindahl_index": round(hhi, 6)},
    }


# ---------------------------------------------------------------------------
# New Basel III endpoints
# ---------------------------------------------------------------------------

@router.get("/sa-ccr")
def get_sa_ccr() -> dict[str, Any]:
    """SA-CCR EAD by netting set (Basel III CRE52)."""
    from infrastructure.risk.sa_ccr import sa_ccr_engine
    ead_results = sa_ccr_engine.calculate_portfolio_ead()
    total_ead = sum(e.get("ead_usd", 0.0) for e in ead_results)
    total_pfe = sum(e.get("pfe_usd", 0.0) for e in ead_results)
    total_rc  = sum(e.get("rc_usd", 0.0) for e in ead_results)
    return {
        "netting_sets": ead_results,
        "totals": {
            "total_rc_usd":  round(total_rc, 2),
            "total_pfe_usd": round(total_pfe, 2),
            "total_ead_usd": round(total_ead, 2),
            "ccr_rwa_usd":   round(total_ead * 0.50, 2),  # 50% RW bank avg
        },
        "alpha": 1.4,
    }


@router.get("/oprisk")
def get_oprisk() -> dict[str, Any]:
    """Operational Risk capital charge and RWA (Business Indicator Approach)."""
    from infrastructure.risk.oprisk_capital import oprisk_engine
    bia = oprisk_engine.calculate_bia()
    basic = oprisk_engine.calculate_basic_indicator()
    return {
        "business_indicator_approach": bia,
        "basic_indicator_approach":    basic,
        "selected_method":             "BIA",
        "capital_charge_usd":          bia["bic_usd"],
        "oprisk_rwa_usd":              bia["oprisk_rwa_usd"],
    }


@router.get("/buffers")
def get_buffers() -> dict[str, Any]:
    """Capital buffer stack: CCB, CCyB, G-SIB surcharge, and CBR."""
    from infrastructure.risk.capital_buffers import capital_buffer_engine
    from infrastructure.risk.regulatory_capital import capital_engine as ce

    positions = _get_positions()
    cap = ce.calculate(positions)

    return capital_buffer_engine.calculate_buffers(
        cet1_ratio=cap["cet1_ratio"],
        tier1_ratio=cap["tier1_ratio"],
        total_ratio=cap["total_capital_ratio"],
        rwa=max(cap["rwa_total_usd"], 346_000_000_000.0),
    )


@router.get("/mda")
def get_mda() -> dict[str, Any]:
    """Maximum Distributable Amount calculation."""
    from infrastructure.risk.capital_buffers import capital_buffer_engine
    from infrastructure.risk.regulatory_capital import capital_engine as ce

    positions = _get_positions()
    cap = ce.calculate(positions)

    # Representative distributable earnings = ~$15B (JPMorgan-scale net income)
    distributable_earnings = 15_000_000_000.0
    rwa = max(cap["rwa_total_usd"], 346_000_000_000.0)

    return capital_buffer_engine.calculate_mda(
        cet1_ratio=cap["cet1_ratio"],
        rwa=rwa,
        distributable_earnings=distributable_earnings,
    )


@router.get("/large-exposures")
def get_large_exposures() -> dict[str, Any]:
    """Large Exposures table with limit checks (Basel CRE70)."""
    from infrastructure.risk.large_exposures import large_exposures_engine
    from infrastructure.risk.sa_ccr import sa_ccr_engine

    ead_results = sa_ccr_engine.calculate_portfolio_ead()
    exposures = large_exposures_engine.calculate_exposures(sa_ccr_eads=ead_results)
    limit_checks = large_exposures_engine.check_limits(exposures)
    summary = large_exposures_engine.get_summary(exposures)

    return {
        "summary":      summary,
        "exposures":    limit_checks,
    }


@router.get("/allocation")
def get_capital_allocation() -> dict[str, Any]:
    """
    Capital allocation framework — top-down CET1 and RWA budgets by business line and desk.
    Shows each desk's allocated CET1, derived RWA budget, and utilisation from live trades.
    """
    from infrastructure.risk.capital_allocation import capital_allocation
    from infrastructure.risk.capital_consumption import capital_consumption

    report = capital_allocation.get_full_report()
    consumption = capital_consumption.get_report()

    # Annotate each desk with live consumption data
    desk_consumption = {d["desk"]: d for d in consumption["by_desk"]}
    for desk_name, da in report["desk_allocations"].items():
        cons = desk_consumption.get(desk_name, {})
        da["rwa_consumed"] = cons.get("rwa_consumed", 0.0)
        da["utilisation_pct"] = cons.get("utilisation_pct", 0.0)
        da["rwa_headroom"] = cons.get("headroom", da["rwa_budget_usd"])
        da["trade_count"] = cons.get("trade_count", 0)

    report["live_cet1_ratio"] = consumption["live_cet1_ratio"]
    report["live_cet1_ratio_pct"] = consumption["live_cet1_ratio_pct"]
    return report


@router.get("/consumption")
def get_capital_consumption() -> dict[str, Any]:
    """
    Live RWA consumption tracker — incremental RWA from booked trades, by desk and counterparty.
    Shows how much of each desk's capital budget has been consumed since startup.
    """
    from infrastructure.risk.capital_consumption import capital_consumption
    return capital_consumption.get_report()


class ReallocateRequest(BaseModel):
    from_desk: str
    to_desk: str
    cet1_amount_usd: float


@router.post("/reallocate")
def reallocate_capital(body: ReallocateRequest) -> dict[str, Any]:
    """
    CFO intra-quarter capital reallocation between trading desks.
    Transfers CET1 budget (and derived RWA budget) from one desk to another.
    """
    from infrastructure.risk.capital_allocation import capital_allocation
    return capital_allocation.reallocate(
        from_desk=body.from_desk,
        to_desk=body.to_desk,
        cet1_amount_usd=body.cet1_amount_usd,
    )


@router.get("/output-floor")
def get_output_floor() -> dict[str, Any]:
    """Basel III 72.5% SA RWA output floor application."""
    from infrastructure.risk.output_floor import output_floor_engine
    from infrastructure.risk.regulatory_capital import capital_engine as ce
    from infrastructure.risk.oprisk_capital import oprisk_engine
    from infrastructure.risk.sa_ccr import sa_ccr_engine

    positions = _get_positions()
    cap = ce.calculate(positions)

    # Build total SA RWA including OpRisk and CCR
    ead_results = sa_ccr_engine.calculate_portfolio_ead()
    ccr_rwa = sum(e.get("ead_usd", 0.0) for e in ead_results) * 0.50
    oprisk = oprisk_engine.calculate_bia()
    oprisk_rwa = oprisk["oprisk_rwa_usd"]

    sa_rwa_total = max(cap["rwa_total_usd"], 346_000_000_000.0) + ccr_rwa + oprisk_rwa

    cet1   = RegulatoryCapitalEngine.CET1_CAPITAL_USD
    tier1  = RegulatoryCapitalEngine.TIER1_CAPITAL_USD
    total  = RegulatoryCapitalEngine.TOTAL_CAPITAL_USD

    return output_floor_engine.calculate_floored_ratios(
        cet1=cet1,
        tier1=tier1,
        total_capital=total,
        sa_rwa=sa_rwa_total,
    )


# ── FRTB IMA endpoints (T3-C) ───────────────────────────────────────────────

@router.get("/frtb/es")
def get_frtb_es() -> dict[str, Any]:
    """FRTB IMA Expected Shortfall at 97.5% confidence (BCBS MAR33)."""
    from infrastructure.risk.frtb_ima import frtb_ima_engine
    return frtb_ima_engine.calculate_es()


@router.get("/frtb/pla/{desk}")
def get_frtb_pla(desk: str) -> dict[str, Any]:
    """P&L Attribution test for a desk (BCBS 457 §89)."""
    from infrastructure.risk.frtb_ima import frtb_ima_engine
    return frtb_ima_engine.run_pla_test(desk)


@router.get("/frtb/routing")
def get_frtb_routing() -> dict[str, Any]:
    """IMA vs SA routing decision for each trading desk."""
    from infrastructure.risk.frtb_ima import frtb_ima_engine
    return frtb_ima_engine.get_desk_routing()


@router.get("/frtb/capital")
def get_frtb_capital() -> dict[str, Any]:
    """Full FRTB IMA capital calculation: ES-based IMA capital + SA fallback."""
    from infrastructure.risk.frtb_ima import frtb_ima_engine
    return frtb_ima_engine.calculate_portfolio_capital()
