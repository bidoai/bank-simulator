"""
Liquidity Stress Scenarios — Basel-aligned

Three scenarios:
  - idiosyncratic:   3-notch rating downgrade
  - market_wide:     systemic market disruption
  - combined:        both (Basel primary scenario)
"""
from __future__ import annotations

from typing import Any

from infrastructure.liquidity.lcr import LCREngine
from infrastructure.liquidity.nsfr import NSFREngine


_SCENARIOS = {
    "idiosyncratic": {
        "description": "3-notch rating downgrade stress: retail deposit flight, derivatives collateral calls double, facility drawdowns increase",
        "lcr_outflow_rate_add": 0.5,      # outflow rates * 1.5
        "lcr_haircut_add": 0.00,
        "nsfr_asf_stress": -0.05,
        "nsfr_rsf_stress": 0.05,
        "additional_collateral_call_bn": 25.0,   # deriv calls * 2
        "survival_period_days": 22,
    },
    "market_wide": {
        "description": "Market-wide liquidity disruption: HQLA haircuts +10pp, secured funding dislocated, derivatives +$10B cash call",
        "lcr_outflow_rate_add": 0.0,
        "lcr_haircut_add": 0.10,
        "nsfr_asf_stress": 0.0,
        "nsfr_rsf_stress": 0.10,
        "additional_collateral_call_bn": 10.0,
        "survival_period_days": 28,
    },
    "combined": {
        "description": "Combined idiosyncratic and market-wide stress (Basel primary scenario)",
        "lcr_outflow_rate_add": 0.5,
        "lcr_haircut_add": 0.10,
        "nsfr_asf_stress": -0.05,
        "nsfr_rsf_stress": 0.10,
        "additional_collateral_call_bn": 35.0,
        "survival_period_days": 15,
    },
}


class LiquidityStressEngine:
    def __init__(self) -> None:
        self._lcr = LCREngine()
        self._nsfr = NSFREngine()

    def run_scenario(self, scenario_name: str) -> dict[str, Any]:
        if scenario_name not in _SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_name}. Choose from {list(_SCENARIOS)}")

        params = _SCENARIOS[scenario_name]

        base_lcr = self._lcr.calculate()
        stressed_lcr = self._lcr.calculate_stress(scenario_name)

        base_nsfr = self._nsfr.calculate()
        stressed_nsfr = self._nsfr.calculate_stress(scenario_name)

        lcr_impact = stressed_lcr["lcr_ratio"] - base_lcr["lcr_ratio"]
        nsfr_impact = stressed_nsfr["nsfr_ratio"] - base_nsfr["nsfr_ratio"]

        # Shortfall = max(0, NCO - HQLA) under stress
        stressed_hqla = stressed_lcr["hqla_components"]["total_hqla_bn"]
        stressed_ncof = stressed_lcr["ncof_bn"]
        shortfall_bn = max(0.0, stressed_ncof - stressed_hqla)

        return {
            "scenario": scenario_name,
            "description": params["description"],
            "base_lcr": base_lcr["lcr_ratio"],
            "stressed_lcr": stressed_lcr["lcr_ratio"],
            "lcr_impact_pp": round(lcr_impact, 2),
            "lcr_compliance": stressed_lcr["compliance_status"],
            "base_nsfr": base_nsfr["nsfr_ratio"],
            "stressed_nsfr": stressed_nsfr["nsfr_ratio"],
            "nsfr_impact_pp": round(nsfr_impact, 2),
            "nsfr_compliance": stressed_nsfr["compliance_status"],
            "shortfall_bn": round(shortfall_bn, 2),
            "survival_period_days": params["survival_period_days"],
            "additional_collateral_call_bn": params["additional_collateral_call_bn"],
            "stressed_hqla_bn": round(stressed_hqla, 2),
            "stressed_ncof_bn": round(stressed_ncof, 2),
        }

    def run_all_scenarios(self) -> list[dict[str, Any]]:
        return [self.run_scenario(name) for name in _SCENARIOS]
