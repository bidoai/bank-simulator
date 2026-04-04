"""
NSFR (Net Stable Funding Ratio) Engine — Basel III

NSFR = ASF / RSF >= 100%
"""
from __future__ import annotations

from typing import Any


# ---------------------------------------------------------------------------
# Balance sheet (Apex Global Bank, consistent with LCR engine)
# ---------------------------------------------------------------------------

_BS = {
    # Liabilities / funding (ASF inputs, $B)
    "tier1_capital": 220.0,
    "tier2_capital": 45.0,
    "preferred_stock_gt1yr": 15.0,
    "other_liabilities_gt1yr": 380.0,
    "retail_stable_deposits_lt1yr": 800.0,
    "retail_less_stable_deposits_lt1yr": 400.0,
    "wholesale_op_nonfin_lt1yr": 300.0,
    "wholesale_non_op_fin_6m_to_1yr": 150.0,
    "wholesale_non_op_fin_lt6m": 200.0,
    "other_liabilities_lt6m": 120.0,
    "derivatives_liabilities_net": 18.0,
    # Assets (RSF inputs, $B)
    "cash_reserves": 45.0,
    "hqla_l1_unencumbered": 280.0,
    "hqla_l2a_unencumbered": 95.0,
    "hqla_l2b_unencumbered": 45.0,
    "loans_fin_lt6m": 80.0,
    "loans_fin_6m_to_1yr": 60.0,
    "retail_sme_loans_lt1yr": 200.0,
    "retail_sme_loans_gt1yr": 450.0,
    "corporate_loans_lt1yr": 160.0,
    "corporate_loans_gt1yr": 280.0,
    "residential_mortgages": 320.0,
    "other_assets": 248.0,  # brings total assets close to $3.2T
    # Off-balance-sheet
    "undrawn_credit_liquidity_facilities": 260.0,  # 180B + 80B from LCR
}

# ASF factors
_ASF_FACTORS = {
    "tier1_capital": 1.00,
    "tier2_capital": 1.00,
    "preferred_stock_gt1yr": 1.00,
    "other_liabilities_gt1yr": 1.00,
    "retail_stable_deposits_lt1yr": 0.95,
    "retail_less_stable_deposits_lt1yr": 0.90,
    "wholesale_op_nonfin_lt1yr": 0.50,
    "wholesale_non_op_fin_6m_to_1yr": 0.50,
    "wholesale_non_op_fin_lt6m": 0.00,
    "other_liabilities_lt6m": 0.00,
    "derivatives_liabilities_net": 0.00,
}

# RSF factors
_RSF_FACTORS = {
    "cash_reserves": 0.00,
    "hqla_l1_unencumbered": 0.05,
    "hqla_l2a_unencumbered": 0.15,
    "hqla_l2b_unencumbered": 0.50,
    "loans_fin_lt6m": 0.10,
    "loans_fin_6m_to_1yr": 0.15,
    "retail_sme_loans_lt1yr": 0.50,
    "retail_sme_loans_gt1yr": 0.85,
    "corporate_loans_lt1yr": 0.65,
    "corporate_loans_gt1yr": 0.65,
    "residential_mortgages": 0.65,
    "other_assets": 1.00,
    "undrawn_credit_liquidity_facilities": 0.05,
}


class NSFREngine:
    def __init__(self) -> None:
        self._bs = dict(_BS)

    def calculate(self) -> dict[str, Any]:
        return self._compute(self._bs, asf_stress=0.0, rsf_stress=0.0)

    def calculate_stress(self, scenario: str) -> dict[str, Any]:
        asf_stress = 0.0
        rsf_stress = 0.0

        if scenario == "idiosyncratic":
            asf_stress = -0.05  # reduce ASF factors (deposit outflows)
            rsf_stress = 0.05   # increase RSF requirement
        elif scenario == "market_wide":
            rsf_stress = 0.10
        elif scenario == "combined":
            asf_stress = -0.05
            rsf_stress = 0.10

        result = self._compute(self._bs, asf_stress, rsf_stress)
        result["scenario"] = scenario
        return result

    def _compute(
        self,
        bs: dict[str, float],
        asf_stress: float,
        rsf_stress: float,
    ) -> dict[str, Any]:
        # ── ASF ───────────────────────────────────────────────────────────────
        asf_components = {}
        total_asf = 0.0
        for key, factor in _ASF_FACTORS.items():
            amount = bs.get(key, 0.0)
            stressed_factor = max(0.0, min(1.0, factor + asf_stress if factor > 0 else factor))
            contribution = amount * stressed_factor
            total_asf += contribution
            asf_components[key] = {
                "amount_bn": amount,
                "factor": round(stressed_factor, 2),
                "contribution_bn": round(contribution, 2),
            }

        # ── RSF ───────────────────────────────────────────────────────────────
        rsf_components = {}
        total_rsf = 0.0
        for key, factor in _RSF_FACTORS.items():
            amount = bs.get(key, 0.0)
            stressed_factor = min(1.0, factor + rsf_stress) if factor > 0 else factor
            requirement = amount * stressed_factor
            total_rsf += requirement
            rsf_components[key] = {
                "amount_bn": amount,
                "factor": round(stressed_factor, 2),
                "requirement_bn": round(requirement, 2),
            }

        nsfr_ratio = (total_asf / total_rsf * 100) if total_rsf > 0 else float("inf")

        if nsfr_ratio >= 110:
            compliance_status = "COMPLIANT"
        elif nsfr_ratio >= 100:
            compliance_status = "MARGINAL"
        else:
            compliance_status = "BREACH"

        # Top 5 RSF contributors
        top_rsf = sorted(
            [(k, v["requirement_bn"]) for k, v in rsf_components.items()],
            key=lambda x: x[1],
            reverse=True,
        )[:5]

        return {
            "asf_components": asf_components,
            "rsf_components": rsf_components,
            "total_asf_bn": round(total_asf, 2),
            "total_rsf_bn": round(total_rsf, 2),
            "nsfr_ratio": round(nsfr_ratio, 2),
            "nsfr_minimum": 100.0,
            "compliance_status": compliance_status,
            "surplus_deficit_bn": round(total_asf - total_rsf, 2),
            "top_rsf_contributors": [
                {"item": k, "requirement_bn": round(v, 2)} for k, v in top_rsf
            ],
        }
