"""
Balance Sheet Optimizer.

Sizes the HQLA buffer, ranks business lines by RWA efficiency (RoRWA),
and identifies optimization actions for below-hurdle businesses.
"""
from __future__ import annotations

from datetime import datetime


# ── HQLA Parameters ────────────────────────────────────────────────────────

# Apex Global Bank LCR inputs
NET_CASH_OUTFLOWS_USD = 180e9          # 30-day stressed NCO
REGULATORY_LCR_FLOOR = 1.00           # 100% minimum
MANAGEMENT_BUFFER_PCT = 0.10          # 10% above regulatory minimum
CURRENT_HQLA_USD = 220e9             # current HQLA stock

# HQLA yield vs displaced high-yield assets (opportunity cost)
HQLA_YIELD_PCT = 4.95                  # ~SOFR (HQLA earns near risk-free)
DISPLACED_ASSET_YIELD_PCT = 6.80       # yield on assets we'd hold instead

# ── Business Line RWA Density Parameters ───────────────────────────────────

BUSINESS_LINES = [
    {
        "business": "Equity Derivatives",
        "rwa_usd": 12_000e6,
        "revenue_usd": 800e6,
        "status": "BELOW_HURDLE",
        "optimization": "Move to CCP clearing",
        "rwa_saving_usd": 3_000e6,
        "revenue_impact_usd": -50e6,
        "strategy": "Central clearing reduces counterparty RWA by ~25%",
    },
    {
        "business": "IG Credit",
        "rwa_usd": 22_000e6,
        "revenue_usd": 2_100e6,
        "status": "BELOW_HURDLE",
        "optimization": "Novation to clearing counterparties",
        "rwa_saving_usd": 5_000e6,
        "revenue_impact_usd": -80e6,
        "strategy": "CCP novation reduces standardised RWA for investment-grade credit",
    },
    {
        "business": "FX Spot/Forward",
        "rwa_usd": 8_000e6,
        "revenue_usd": 1_400e6,
        "status": "ABOVE_HURDLE",
        "optimization": None,
        "rwa_saving_usd": 0.0,
        "revenue_impact_usd": 0.0,
        "strategy": None,
    },
    {
        "business": "Rates IRS (Cleared)",
        "rwa_usd": 15_000e6,
        "revenue_usd": 2_800e6,
        "status": "ABOVE_HURDLE",
        "optimization": None,
        "rwa_saving_usd": 0.0,
        "revenue_impact_usd": 0.0,
        "strategy": None,
    },
    {
        "business": "Prime Brokerage",
        "rwa_usd": 18_000e6,
        "revenue_usd": 1_600e6,
        "status": "BELOW_HURDLE",
        "optimization": "Collateral upgrade trades",
        "rwa_saving_usd": 4_000e6,
        "revenue_impact_usd": -60e6,
        "strategy": "Upgrade client collateral from equities to sovereigns; reduces SFT RWA",
    },
    {
        "business": "Structured Credit",
        "rwa_usd": 25_000e6,
        "revenue_usd": 3_200e6,
        "status": "ABOVE_HURDLE",
        "optimization": None,
        "rwa_saving_usd": 0.0,
        "revenue_impact_usd": 0.0,
        "strategy": None,
    },
    {
        "business": "Commodities",
        "rwa_usd": 10_000e6,
        "revenue_usd": 900e6,
        "status": "BELOW_HURDLE",
        "optimization": "Portfolio compression & de-risking",
        "rwa_saving_usd": 2_500e6,
        "revenue_impact_usd": -40e6,
        "strategy": "TriOptima/Quantile compression reduces gross notional and RWA",
    },
]

HURDLE_RORWA = 0.12   # 12% — same as RAROC hurdle


class BalanceSheetOptimizer:
    """Balance sheet optimization engine."""

    def get_hqla_buffer_analysis(self) -> dict:
        required_min = NET_CASH_OUTFLOWS_USD * REGULATORY_LCR_FLOOR
        target_buffer = required_min * (1.0 + MANAGEMENT_BUFFER_PCT)
        surplus_deficit = CURRENT_HQLA_USD - target_buffer

        # Cost of excess HQLA = opportunity cost on surplus above regulatory minimum
        excess_above_min = max(CURRENT_HQLA_USD - required_min, 0.0)
        opportunity_spread_pct = DISPLACED_ASSET_YIELD_PCT - HQLA_YIELD_PCT
        annual_cost_of_excess = excess_above_min * opportunity_spread_pct / 100.0

        current_lcr = CURRENT_HQLA_USD / NET_CASH_OUTFLOWS_USD

        return {
            "current_hqla_usd": round(CURRENT_HQLA_USD, 0),
            "net_cash_outflows_30d_usd": round(NET_CASH_OUTFLOWS_USD, 0),
            "current_lcr_ratio": round(current_lcr, 4),
            "current_lcr_pct": round(current_lcr * 100.0, 1),
            "regulatory_minimum_hqla_usd": round(required_min, 0),
            "target_hqla_with_buffer_usd": round(target_buffer, 0),
            "management_buffer_pct": round(MANAGEMENT_BUFFER_PCT * 100.0, 1),
            "surplus_deficit_usd": round(surplus_deficit, 0),
            "is_surplus": surplus_deficit >= 0.0,
            "excess_above_regulatory_min_usd": round(excess_above_min, 0),
            "annual_cost_of_excess_hqla_usd": round(annual_cost_of_excess, 0),
            "hqla_yield_pct": HQLA_YIELD_PCT,
            "displaced_asset_yield_pct": DISPLACED_ASSET_YIELD_PCT,
            "opportunity_spread_bps": round(opportunity_spread_pct * 100.0, 1),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_rwa_density_by_business(self) -> dict:
        """RWA density table: revenue per RWA dollar and RoRWA by business line."""
        rows = []
        total_rwa = 0.0
        total_revenue = 0.0

        for bl in BUSINESS_LINES:
            rwa = bl["rwa_usd"]
            rev = bl["revenue_usd"]
            rorwa = rev / rwa if rwa > 0 else 0.0
            rev_per_rwa = rev / rwa if rwa > 0 else 0.0
            above_hurdle = rorwa >= HURDLE_RORWA

            rows.append({
                "business": bl["business"],
                "rwa_usd": round(rwa, 0),
                "revenue_usd": round(rev, 0),
                "rorwa_pct": round(rorwa * 100.0, 1),
                "revenue_per_rwa_dollar": round(rev_per_rwa, 4),
                "status": "ABOVE_HURDLE" if above_hurdle else "BELOW_HURDLE",
                "hurdle_pct": round(HURDLE_RORWA * 100.0, 1),
            })

            total_rwa += rwa
            total_revenue += rev

        rows.sort(key=lambda r: r["rorwa_pct"], reverse=True)
        firm_rorwa = total_revenue / total_rwa if total_rwa > 0 else 0.0

        return {
            "by_business": rows,
            "firm_total_rwa_usd": round(total_rwa, 0),
            "firm_total_revenue_usd": round(total_revenue, 0),
            "firm_rorwa_pct": round(firm_rorwa * 100.0, 1),
            "hurdle_pct": round(HURDLE_RORWA * 100.0, 1),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_optimization_recommendations(self) -> list[dict]:
        """
        Actions for below-hurdle businesses: estimated RWA savings and net P&L benefit.
        """
        recs = []
        for bl in BUSINESS_LINES:
            if bl["status"] != "BELOW_HURDLE" or bl["optimization"] is None:
                continue

            rwa = bl["rwa_usd"]
            rev = bl["revenue_usd"]
            saving = bl["rwa_saving_usd"]
            rev_impact = bl["revenue_impact_usd"]

            post_rwa = rwa - saving
            post_rorwa = (rev + rev_impact) / post_rwa if post_rwa > 0 else 0.0
            current_rorwa = rev / rwa if rwa > 0 else 0.0

            recs.append({
                "business": bl["business"],
                "current_rwa_usd": round(rwa, 0),
                "current_rorwa_pct": round(current_rorwa * 100.0, 1),
                "action": bl["optimization"],
                "strategy_detail": bl["strategy"],
                "estimated_rwa_saving_usd": round(saving, 0),
                "estimated_revenue_impact_usd": round(rev_impact, 0),
                "post_action_rwa_usd": round(post_rwa, 0),
                "post_action_rorwa_pct": round(post_rorwa * 100.0, 1),
                "above_hurdle_post_action": post_rorwa >= HURDLE_RORWA,
                "net_benefit_usd": round(-rev_impact + saving * HURDLE_RORWA, 0),
            })

        recs.sort(key=lambda r: r["estimated_rwa_saving_usd"], reverse=True)
        return recs

    def get_full_optimization_report(self) -> dict:
        hqla = self.get_hqla_buffer_analysis()
        rwa_density = self.get_rwa_density_by_business()
        recs = self.get_optimization_recommendations()

        total_rwa_saving = sum(r["estimated_rwa_saving_usd"] for r in recs)
        total_rev_impact = sum(r["estimated_revenue_impact_usd"] for r in recs)

        return {
            "hqla_buffer": hqla,
            "rwa_density_by_business": rwa_density,
            "optimization_recommendations": recs,
            "summary": {
                "total_potential_rwa_saving_usd": round(total_rwa_saving, 0),
                "total_revenue_impact_usd": round(total_rev_impact, 0),
                "below_hurdle_count": len(recs),
                "above_hurdle_count": len([
                    bl for bl in BUSINESS_LINES if bl["status"] == "ABOVE_HURDLE"
                ]),
            },
            "as_of": datetime.utcnow().isoformat(),
        }


balance_sheet_optimizer = BalanceSheetOptimizer()
