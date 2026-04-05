"""
LCR (Liquidity Coverage Ratio) Engine — Basel III

LCR = HQLA / Net Cash Outflows (30-day stress) >= 100%
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Balance sheet (Apex Global Bank, $3.2T total assets)
# ---------------------------------------------------------------------------

_BS = {
    # HQLA positions ($B)
    "hqla_l1_sovereign": 280.0,
    "hqla_l2a_agency": 95.0,
    "hqla_l2b_corp_bbb": 45.0,
    # Deposit funding ($B)
    "retail_stable_deposits": 800.0,
    "retail_less_stable_deposits": 400.0,
    "wholesale_operational": 600.0,
    "wholesale_non_operational": 350.0,
    "wholesale_financial": 200.0,
    # Secured funding ($B)
    "secured_l1_collateral": 120.0,
    "secured_l2a_collateral": 60.0,
    "secured_l2b_collateral": 30.0,
    # Facilities ($B)
    "committed_facilities_non_financial": 180.0,
    "committed_facilities_financial": 80.0,
    # Derivatives ($B)
    "derivatives_potential_call": 25.0,
    # Inflows ($B)
    "retail_loan_inflows": 40.0,
    "wholesale_financial_inflows": 30.0,
    "secured_lending_l1_inflows": 50.0,
    "secured_lending_l2a_inflows": 25.0,
}

# Outflow rates (Basel III LCR standard)
_OUTFLOW_RATES = {
    "retail_stable_deposits": 0.03,
    "retail_less_stable_deposits": 0.10,
    "wholesale_operational": 0.25,
    "wholesale_non_operational": 0.40,
    "wholesale_financial": 1.00,
    "secured_l1_collateral": 0.00,
    "secured_l2a_collateral": 0.15,
    "secured_l2b_collateral": 0.25,
    "committed_facilities_non_financial": 0.10,
    "committed_facilities_financial": 0.40,
}

# Inflow rates
_INFLOW_RATES = {
    "retail_loan_inflows": 0.50,
    "wholesale_financial_inflows": 1.00,
    "secured_lending_l1_inflows": 0.00,
    "secured_lending_l2a_inflows": 0.15,
}

# HQLA haircuts
_HAIRCUTS = {
    "l1": 0.00,
    "l2a": 0.15,
    "l2b_rmbs": 0.25,
    "l2b_corp": 0.50,
    "l2b_equity": 0.50,
}


class LCREngine:
    def __init__(self) -> None:
        self._bs = dict(_BS)

    def calculate(self) -> dict[str, Any]:
        return self._compute(self._bs, 0.0, 0.0)

    def calculate_stress(self, scenario: str) -> dict[str, Any]:
        outflow_multiplier = 1.0
        haircut_addition = 0.0

        if scenario == "idiosyncratic":
            outflow_multiplier = 1.5
        elif scenario == "market_wide":
            haircut_addition = 0.10
        elif scenario == "combined":
            outflow_multiplier = 1.5
            haircut_addition = 0.10

        result = self._compute(self._bs, outflow_multiplier - 1.0, haircut_addition)
        result["scenario"] = scenario
        return result

    def _compute(
        self,
        bs: dict[str, float],
        outflow_rate_add: float,
        haircut_add: float,
    ) -> dict[str, Any]:
        # ── HQLA ──────────────────────────────────────────────────────────────
        l1_raw = bs["hqla_l1_sovereign"]
        l2a_raw = bs["hqla_l2a_agency"]
        l2b_raw = bs["hqla_l2b_corp_bbb"]

        l1_haircut = max(0.0, _HAIRCUTS["l1"] + haircut_add)
        l2a_haircut = max(0.0, _HAIRCUTS["l2a"] + haircut_add)
        l2b_haircut = max(0.0, _HAIRCUTS["l2b_corp"] + haircut_add)

        l1_adjusted = l1_raw * (1 - l1_haircut)
        l2a_adjusted = l2a_raw * (1 - l2a_haircut)
        l2b_adjusted = l2b_raw * (1 - l2b_haircut)

        total_raw = l1_adjusted + l2a_adjusted + l2b_adjusted

        # Apply compositional caps
        # Level 2 cap: L2A + L2B <= 40% of adjusted HQLA
        # Level 2B cap: L2B <= 15% of adjusted HQLA
        l2_cap = 0.40 * total_raw
        l2b_cap = 0.15 * total_raw

        l2b_capped = min(l2b_adjusted, l2b_cap)
        l2a_capped = min(l2a_adjusted, l2_cap - l2b_capped)
        l2a_capped = max(0.0, l2a_capped)

        total_hqla = l1_adjusted + l2a_capped + l2b_capped

        # ── Outflows ──────────────────────────────────────────────────────────
        def out_rate(key: str) -> float:
            base = _OUTFLOW_RATES[key]
            return min(1.0, base * (1 + outflow_rate_add))

        retail_stable_out = bs["retail_stable_deposits"] * out_rate("retail_stable_deposits")
        retail_less_stable_out = bs["retail_less_stable_deposits"] * out_rate("retail_less_stable_deposits")
        wholesale_op_out = bs["wholesale_operational"] * out_rate("wholesale_operational")
        wholesale_non_op_out = bs["wholesale_non_operational"] * out_rate("wholesale_non_operational")
        wholesale_fin_out = bs["wholesale_financial"] * min(1.0, out_rate("wholesale_financial"))
        secured_l1_out = bs["secured_l1_collateral"] * out_rate("secured_l1_collateral")
        secured_l2a_out = bs["secured_l2a_collateral"] * out_rate("secured_l2a_collateral")
        secured_l2b_out = bs["secured_l2b_collateral"] * out_rate("secured_l2b_collateral")
        facilities_nonfin_out = bs["committed_facilities_non_financial"] * out_rate("committed_facilities_non_financial")
        facilities_fin_out = bs["committed_facilities_financial"] * out_rate("committed_facilities_financial")
        deriv_out = bs["derivatives_potential_call"] * (1 + outflow_rate_add)

        total_outflows = (
            retail_stable_out + retail_less_stable_out
            + wholesale_op_out + wholesale_non_op_out + wholesale_fin_out
            + secured_l1_out + secured_l2a_out + secured_l2b_out
            + facilities_nonfin_out + facilities_fin_out
            + deriv_out
        )

        # ── Inflows ───────────────────────────────────────────────────────────
        retail_in = bs["retail_loan_inflows"] * _INFLOW_RATES["retail_loan_inflows"]
        wholesale_fin_in = bs["wholesale_financial_inflows"] * _INFLOW_RATES["wholesale_financial_inflows"]
        secured_l1_in = bs["secured_lending_l1_inflows"] * _INFLOW_RATES["secured_lending_l1_inflows"]
        secured_l2a_in = bs["secured_lending_l2a_inflows"] * _INFLOW_RATES["secured_lending_l2a_inflows"]

        total_inflows = retail_in + wholesale_fin_in + secured_l1_in + secured_l2a_in
        capped_inflows = min(total_inflows, 0.75 * total_outflows)

        ncof = total_outflows - capped_inflows

        lcr_ratio = (total_hqla / ncof * 100) if ncof > 0 else float("inf")

        if lcr_ratio >= 110:
            compliance_status = "COMPLIANT"
        elif lcr_ratio >= 100:
            compliance_status = "MARGINAL"
        else:
            compliance_status = "BREACH"

        return {
            "hqla_components": {
                "l1_sovereign": {
                    "raw_amount_bn": l1_raw,
                    "haircut_pct": round(l1_haircut * 100, 1),
                    "adjusted_amount_bn": round(l1_adjusted, 2),
                },
                "l2a_agency": {
                    "raw_amount_bn": l2a_raw,
                    "haircut_pct": round(l2a_haircut * 100, 1),
                    "adjusted_amount_bn": round(l2a_adjusted, 2),
                    "capped_amount_bn": round(l2a_capped, 2),
                    "cap_utilization_pct": round(l2a_capped / l2_cap * 100, 1) if l2_cap > 0 else 0.0,
                },
                "l2b_corp_bbb": {
                    "raw_amount_bn": l2b_raw,
                    "haircut_pct": round(l2b_haircut * 100, 1),
                    "adjusted_amount_bn": round(l2b_adjusted, 2),
                    "capped_amount_bn": round(l2b_capped, 2),
                    "cap_utilization_pct": round(l2b_capped / l2b_cap * 100, 1) if l2b_cap > 0 else 0.0,
                },
                "total_hqla_bn": round(total_hqla, 2),
                "l2_cap_bn": round(l2_cap, 2),
                "l2b_cap_bn": round(l2b_cap, 2),
            },
            "outflows": {
                "retail_stable_bn": round(retail_stable_out, 2),
                "retail_less_stable_bn": round(retail_less_stable_out, 2),
                "wholesale_operational_bn": round(wholesale_op_out, 2),
                "wholesale_non_operational_bn": round(wholesale_non_op_out, 2),
                "wholesale_financial_bn": round(wholesale_fin_out, 2),
                "secured_l1_bn": round(secured_l1_out, 2),
                "secured_l2a_bn": round(secured_l2a_out, 2),
                "secured_l2b_bn": round(secured_l2b_out, 2),
                "facilities_non_financial_bn": round(facilities_nonfin_out, 2),
                "facilities_financial_bn": round(facilities_fin_out, 2),
                "derivatives_bn": round(deriv_out, 2),
                "total_outflows_bn": round(total_outflows, 2),
            },
            "inflows": {
                "retail_loans_bn": round(retail_in, 2),
                "wholesale_financial_bn": round(wholesale_fin_in, 2),
                "secured_l1_bn": round(secured_l1_in, 2),
                "secured_l2a_bn": round(secured_l2a_in, 2),
                "total_inflows_bn": round(total_inflows, 2),
                "capped_inflows_bn": round(capped_inflows, 2),
                "inflow_cap_applied": total_inflows > capped_inflows,
            },
            "ncof_bn": round(ncof, 2),
            "lcr_ratio": round(lcr_ratio, 2),
            "lcr_minimum": 100.0,
            "compliance_status": compliance_status,
            "surplus_deficit_bn": round(total_hqla - ncof, 2),
        }


lcr_engine = LCREngine()
