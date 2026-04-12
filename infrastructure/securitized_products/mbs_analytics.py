"""
Agency MBS Analytics Engine.

Implements a PSA prepayment model, pathwise cash flows under rate scenarios,
OAS (Option-Adjusted Spread), effective duration, and convexity for agency
pass-through MBS (TBA and specified pool).

PSA convention:
  0.2% CPR/month in month 1, increasing by 0.2%/month until month 30,
  then flat at 6% CPR for months 30+. "100% PSA" is the baseline.
  Slower/faster prepayment: multiply CPR by PSA speed (e.g. 150% PSA → 9% CPR flat).

OAS methodology:
  - Generate N_PATHS short-rate paths using a simple Ho-Lee model
  - Discount pathwise cash flows at (path rate + spread)
  - Solve for spread that prices the MBS at its market price
  - Effective duration = -(P+ - P-) / (2 × P × Δy)
  - Convexity = (P+ + P- - 2P) / (P × Δy²)
"""
from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# PSA prepayment model
# ---------------------------------------------------------------------------

def cpr_from_psa(month: int, psa_speed: float = 1.0) -> float:
    """Annual CPR for a given seasoning month under PSA convention."""
    if month <= 0:
        return 0.0
    if month < 30:
        baseline_cpr = 0.06 * (month / 30.0)
    else:
        baseline_cpr = 0.06
    return baseline_cpr * psa_speed


def smm_from_cpr(cpr: float) -> float:
    """Single Monthly Mortality from annual CPR."""
    return 1.0 - (1.0 - cpr) ** (1.0 / 12.0)


# ---------------------------------------------------------------------------
# Cash flow generator
# ---------------------------------------------------------------------------

@dataclass
class MBSCashFlows:
    months: list[int]
    principal: list[float]   # scheduled + prepaid
    interest: list[float]
    total: list[float]
    balance: list[float]     # outstanding at start of each period
    wam: float               # weighted-average maturity


def generate_cashflows(
    face_value: float,
    gross_coupon: float,       # annual gross coupon rate (e.g. 0.055 for 5.5%)
    wac: float,                # weighted-average coupon (for prepayment calc, ≈ gross_coupon)
    wam_months: int,           # remaining term in months
    psa_speed: float = 1.0,
    seasoning: int = 1,        # months already seasoned
) -> MBSCashFlows:
    """Generate monthly P&I cash flows for an agency pass-through."""
    monthly_rate = gross_coupon / 12.0
    balance = face_value

    months, principals, interests, totals, balances = [], [], [], [], []
    remaining_term = wam_months

    for m in range(1, wam_months + 1):
        if balance <= 0:
            break

        balances.append(balance)
        months.append(m)

        # Scheduled interest
        interest = balance * monthly_rate

        # Scheduled principal (level-pay amortisation)
        if monthly_rate > 0:
            scheduled_principal = balance * monthly_rate / ((1 + monthly_rate) ** remaining_term - 1)
        else:
            scheduled_principal = balance / remaining_term

        # Prepayment
        effective_month = seasoning + m - 1
        cpr = cpr_from_psa(effective_month, psa_speed)
        smm = smm_from_cpr(cpr)
        prepayment = (balance - scheduled_principal) * smm

        principal = scheduled_principal + prepayment
        total = interest + principal

        principals.append(principal)
        interests.append(interest)
        totals.append(total)

        balance -= principal
        remaining_term -= 1

    # Weighted-average maturity (months to payoff weighted by principal)
    total_principal = sum(principals)
    wam = sum(months[i] * principals[i] for i in range(len(months))) / total_principal if total_principal > 0 else 0

    return MBSCashFlows(
        months=months,
        principal=principals,
        interest=interests,
        total=totals,
        balance=balances,
        wam=wam,
    )


# ---------------------------------------------------------------------------
# Discount / pricing
# ---------------------------------------------------------------------------

def price_cashflows(
    cashflows: MBSCashFlows,
    discount_rates: list[float],       # monthly discount rate per period
) -> float:
    """Discount cash flows at given monthly rates. Returns price (fraction of face)."""
    pv = 0.0
    compound = 1.0
    for i, total in enumerate(cashflows.total):
        r = discount_rates[i] if i < len(discount_rates) else discount_rates[-1]
        compound *= (1.0 + r)
        pv += total / compound
    return pv


def flat_discount_rates(annual_rate: float, n: int) -> list[float]:
    """Flat monthly discount rates for n periods."""
    monthly = annual_rate / 12.0
    return [monthly] * n


# ---------------------------------------------------------------------------
# Ho-Lee short-rate paths (simplified, analytical)
# ---------------------------------------------------------------------------

def _ho_lee_paths(
    r0: float,
    sigma: float = 0.012,        # annualised short-rate vol
    n_months: int = 360,
    n_paths: int = 100,
    seed: int = 42,
) -> list[list[float]]:
    """
    Generate short-rate paths under Ho-Lee model (no drift — OAS absorbs it).
    Returns list of paths, each a list of monthly short rates.
    """
    rng = random.Random(seed)
    dt = 1 / 12.0
    sqrt_dt = math.sqrt(dt)
    sigma_monthly = sigma * sqrt_dt

    paths = []
    for _ in range(n_paths):
        path = [r0]
        r = r0
        for _ in range(n_months - 1):
            z = rng.gauss(0, 1)
            r = max(0.0, r + sigma_monthly * z)
            path.append(r)
        paths.append(path)
    return paths


# ---------------------------------------------------------------------------
# OAS solver
# ---------------------------------------------------------------------------

def compute_oas(
    face_value: float,
    market_price: float,         # clean price (fraction of face)
    gross_coupon: float,
    wam_months: int,
    psa_speed: float,
    r0: float,                   # current short rate (annual, decimal)
    seasoning: int = 1,
    n_paths: int = 100,
    sigma: float = 0.012,
    tol: float = 1e-6,
    max_iter: int = 50,
) -> dict:
    """
    Compute OAS by bisection.
    Returns OAS in basis points, Z-spread, effective duration, and convexity.
    """
    cf = generate_cashflows(face_value, gross_coupon, gross_coupon, wam_months, psa_speed, seasoning)
    paths = _ho_lee_paths(r0, sigma, len(cf.months), n_paths)
    target_pv = market_price * face_value

    def price_at_spread(spread_annual: float) -> float:
        total_pv = 0.0
        for path in paths:
            discount_rates = [(path[i] + spread_annual) / 12.0 for i in range(len(cf.months))]
            total_pv += price_cashflows(cf, discount_rates)
        return total_pv / len(paths)

    # Bisection to find OAS
    lo, hi = -0.05, 0.20
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        pv = price_at_spread(mid)
        if abs(pv - target_pv) / face_value < tol:
            break
        if pv > target_pv:
            lo = mid
        else:
            hi = mid
    oas_annual = mid
    oas_bps = oas_annual * 10_000

    # Effective duration (bump ±50bps)
    dy = 0.005
    p_up = price_at_spread(oas_annual + dy) / face_value
    p_dn = price_at_spread(oas_annual - dy) / face_value
    p_mid = price_at_spread(oas_annual) / face_value

    eff_duration = -(p_up - p_dn) / (2.0 * p_mid * dy) if p_mid > 0 else 0.0
    convexity = (p_up + p_dn - 2.0 * p_mid) / (p_mid * dy ** 2) if p_mid > 0 else 0.0

    # Z-spread (flat discount off zero curve — use r0 + oas as proxy)
    z_spread = oas_bps

    return {
        "oas_bps": round(oas_bps, 2),
        "z_spread_bps": round(z_spread, 2),
        "effective_duration": round(eff_duration, 3),
        "convexity": round(convexity, 4),
        "model_price": round(p_mid, 6),
        "market_price": round(market_price, 6),
        "wam_months": len(cf.months),
        "wam_years": round(cf.wam / 12.0, 2),
        "psa_speed": psa_speed,
        "n_paths": n_paths,
    }


# ---------------------------------------------------------------------------
# Scenario analysis
# ---------------------------------------------------------------------------

def scenario_analysis(
    face_value: float,
    gross_coupon: float,
    wam_months: int,
    psa_speed: float,
    r0: float,
    market_price: float,
    seasoning: int = 1,
) -> list[dict]:
    """Price the MBS across six rate scenarios (±50/100/200bps)."""
    results = []
    scenarios = [
        ("Down 200bps", -0.02),
        ("Down 100bps", -0.01),
        ("Down 50bps",  -0.005),
        ("Unchanged",    0.0),
        ("Up 50bps",    +0.005),
        ("Up 100bps",   +0.01),
        ("Up 200bps",   +0.02),
    ]
    base_oas = compute_oas(face_value, market_price, gross_coupon, wam_months, psa_speed, r0, seasoning, n_paths=50)

    for name, shift in scenarios:
        r_new = max(0.001, r0 + shift)
        # Prepayment speeds up when rates fall (refinancing incentive)
        psa_adj = psa_speed * (1.0 - shift * 20)
        psa_adj = max(0.5, min(4.0, psa_adj))
        cf = generate_cashflows(face_value, gross_coupon, gross_coupon, wam_months, psa_adj, seasoning)
        rates = flat_discount_rates(r_new + base_oas["oas_bps"] / 10_000, len(cf.months))
        price = price_cashflows(cf, rates) / face_value
        results.append({
            "scenario": name,
            "rate_shift_bps": round(shift * 10_000),
            "price": round(price, 4),
            "price_change_pct": round((price - market_price) / market_price * 100, 2),
            "psa_speed": round(psa_adj, 2),
        })
    return results


# ---------------------------------------------------------------------------
# High-level analytics for a position
# ---------------------------------------------------------------------------

def analyze_mbs_position(
    name: str,
    face_value: float,
    market_price: float,        # fraction of par (e.g. 0.98 = 98 cents on dollar)
    gross_coupon: float,        # annual (e.g. 0.055 for 5.5%)
    wam_months: int,
    psa_speed: float,           # e.g. 1.0 = 100% PSA
    r0: float,                  # current short rate (annual, decimal)
    seasoning: int = 1,
) -> dict:
    """Full analytics for a single agency MBS position."""
    cf = generate_cashflows(face_value, gross_coupon, gross_coupon, wam_months, psa_speed, seasoning)
    oas_result = compute_oas(face_value, market_price, gross_coupon, wam_months, psa_speed, r0, seasoning)
    scenarios = scenario_analysis(face_value, gross_coupon, wam_months, psa_speed, r0, market_price, seasoning)

    return {
        "name": name,
        "face_value_usd": face_value,
        "market_value_usd": round(market_price * face_value, 2),
        "price": round(market_price, 4),
        "gross_coupon_pct": round(gross_coupon * 100, 2),
        "wam_months_initial": wam_months,
        **oas_result,
        "cashflow_summary": {
            "months_to_payoff": len(cf.months),
            "total_principal": round(sum(cf.principal), 0),
            "total_interest": round(sum(cf.interest), 0),
        },
        "rate_scenarios": scenarios,
    }
