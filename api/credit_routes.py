"""FastAPI routes for the IFRS 9 ECL credit portfolio engine and credit VaR model."""
from __future__ import annotations

import dataclasses
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from infrastructure.credit.ifrs9_ecl import ecl_engine, _sample_portfolio, IFRSStage, Obligor
from infrastructure.credit.portfolio_model import credit_portfolio_model

router = APIRouter(prefix="/credit", tags=["credit"])


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/ecl/portfolio")
def get_portfolio_ecl() -> dict:
    return ecl_engine.portfolio_ecl(_sample_portfolio)


@router.get("/ecl/obligors")
def get_obligors() -> list[dict]:
    results = []
    for ob in _sample_portfolio:
        ecl = ecl_engine.calculate_ecl(ob)
        results.append({
            "obligor_id": ob.obligor_id,
            "name": ob.name,
            "rating": ob.rating,
            "notional_usd": ob.notional_usd,
            "maturity_years": ob.maturity_years,
            **ecl,
        })
    return results


class ScenarioRequest(BaseModel):
    pd_multiplier: float = 1.0
    lgd_override: Optional[float] = None


@router.post("/ecl/scenario")
def run_ecl_scenario(body: ScenarioRequest) -> dict:
    if body.pd_multiplier <= 0:
        raise HTTPException(status_code=422, detail="pd_multiplier must be positive")
    if body.lgd_override is not None and not (0.0 < body.lgd_override <= 1.0):
        raise HTTPException(status_code=422, detail="lgd_override must be between 0 and 1")

    stressed: list[Obligor] = []
    for ob in _sample_portfolio:
        stressed_pd = min(ob.pd_1yr * body.pd_multiplier, 0.9999)
        stressed_lgd = body.lgd_override if body.lgd_override is not None else ob.lgd
        stressed.append(dataclasses.replace(ob, pd_1yr=stressed_pd, lgd=stressed_lgd))

    result = ecl_engine.portfolio_ecl(stressed)
    baseline = ecl_engine.portfolio_ecl(_sample_portfolio)

    result["scenario"] = {
        "pd_multiplier": body.pd_multiplier,
        "lgd_override": body.lgd_override,
        "baseline_ecl_usd": baseline["total_ecl_usd"],
        "stress_ecl_usd": result["total_ecl_usd"],
        "incremental_ecl_usd": round(result["total_ecl_usd"] - baseline["total_ecl_usd"], 2),
    }
    return result


@router.get("/ecl/stage/{stage}")
def get_obligors_by_stage(stage: int) -> list[dict]:
    if stage not in (1, 2, 3):
        raise HTTPException(status_code=422, detail="stage must be 1, 2, or 3")
    target = IFRSStage(stage)
    results = []
    for ob in _sample_portfolio:
        if ob.stage == target:
            ecl = ecl_engine.calculate_ecl(ob)
            results.append({
                "obligor_id": ob.obligor_id,
                "name": ob.name,
                "rating": ob.rating,
                "notional_usd": ob.notional_usd,
                "maturity_years": ob.maturity_years,
                **ecl,
            })
    return results


# ---------------------------------------------------------------------------
# Credit Portfolio VaR (Gaussian copula)
# ---------------------------------------------------------------------------

@router.get("/portfolio-var")
def get_portfolio_var() -> dict:
    """
    Single-factor Gaussian copula credit VaR.
    Returns EL, VaR 99%, VaR 99.9% (EC), CVaR, and EC ratio vs notional.
    10,000 Monte Carlo scenarios over the 50-obligor sample portfolio.
    """
    result = credit_portfolio_model.simulate(_sample_portfolio)
    # Also include IFRS 9 ECL for comparison
    ecl_result = ecl_engine.portfolio_ecl(_sample_portfolio)
    return {
        **result.to_dict(),
        "ifrs9_ecl_usd":        ecl_result["total_ecl_usd"],
        "ifrs9_notional_usd":   ecl_result["total_notional_usd"],
        "ifrs9_coverage_ratio": ecl_result["ecl_coverage_ratio"],
        "model": "single_factor_gaussian_copula",
    }


@router.get("/marginal-contribution")
def get_marginal_contribution() -> dict:
    """
    Marginal EC contribution per obligor via indicator method.
    MRC_i = E[LGD_i × EAD_i | portfolio loss > VaR_99].
    Sorted descending by MRC.
    """
    contributions = credit_portfolio_model.marginal_contributions(_sample_portfolio)
    total_mrc = sum(c["mrc_usd"] for c in contributions)
    return {
        "obligors": contributions,
        "total_mrc_usd": round(total_mrc, 0),
        "n_obligors": len(contributions),
    }


@router.get("/loss-distribution")
def get_loss_distribution() -> dict:
    """Bucketed loss distribution for charting (50 buckets)."""
    return credit_portfolio_model.loss_distribution(_sample_portfolio)


@router.post("/portfolio-var/scenario")
def run_portfolio_var_scenario(body: ScenarioRequest) -> dict:
    """
    Stressed credit VaR — apply PD multiplier and optional LGD override.
    """
    if body.pd_multiplier <= 0:
        raise HTTPException(status_code=422, detail="pd_multiplier must be positive")
    stressed = []
    for ob in _sample_portfolio:
        stressed_pd = min(ob.pd_1yr * body.pd_multiplier, 0.9999)
        stressed_lgd = body.lgd_override if body.lgd_override is not None else ob.lgd
        stressed.append(dataclasses.replace(ob, pd_1yr=stressed_pd, lgd=stressed_lgd))
    base = credit_portfolio_model.simulate(_sample_portfolio)
    stressed_result = credit_portfolio_model.simulate(stressed)
    return {
        "baseline": base.to_dict(),
        "stressed": stressed_result.to_dict(),
        "scenario": {
            "pd_multiplier":    body.pd_multiplier,
            "lgd_override":     body.lgd_override,
            "ec_increase_usd":  round(stressed_result.ec_usd - base.ec_usd, 0),
            "var99_increase_usd": round(stressed_result.var_99_usd - base.var_99_usd, 0),
        },
    }
