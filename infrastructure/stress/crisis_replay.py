"""
Historical Crisis Replay Engine — Apex Global Bank.

Applies pre-calibrated historical market shocks to live OMS positions,
generating position-level P&L impact, aggregate capital impact, and limit breaches.

Three scenario tapes:
  GFC_2008      — Lehman Brothers bankruptcy, September 2008 peak stress
  COVID_2020    — March 2020 pandemic market dislocation
  UK_GILT_2022  — UK mini-budget gilt crisis, September 2022

P&L methodology: shock × notional for price-sensitive instruments;
DV01-proxy for rate-sensitive instruments. See per-asset mapping below.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ── Scenario tapes ──────────────────────────────────────────────────────────

CRISIS_SCENARIOS: dict[str, dict] = {
    "GFC_2008": {
        "name":      "Global Financial Crisis — September 2008 Peak Stress",
        "date":      "2008-09-15",
        "reference": "BCBS Stress Testing Principles (2018); Basel III framework calibration",
        "shocks": {
            "EQUITY":      {"price_multiplier": 0.60,  "vol_multiplier": 3.5},
            "RATES":       {"parallel_shift_bps": -200, "vol_multiplier": 2.5},
            "CREDIT":      {"spread_widening_bps": 500, "vol_multiplier": 4.0},
            "FX":          {"usd_appreciation_pct": 0.20, "vol_multiplier": 2.0},
            "COMMODITIES": {"price_multiplier": 0.70, "vol_multiplier": 2.0},
            "DERIVATIVES": {"price_multiplier": 0.65, "vol_multiplier": 3.0},
        },
    },
    "COVID_2020": {
        "name":      "COVID-19 Pandemic — March 2020 Market Dislocation",
        "date":      "2020-03-16",
        "reference": "BIS Working Paper No. 912 (2021); ECB stress test 2020",
        "shocks": {
            "EQUITY":      {"price_multiplier": 0.65,  "vol_multiplier": 5.0},
            "RATES":       {"parallel_shift_bps": -150, "vol_multiplier": 2.0},
            "CREDIT":      {"spread_widening_bps": 300, "vol_multiplier": 3.0},
            "FX":          {"usd_appreciation_pct": 0.08, "vol_multiplier": 1.5},
            "COMMODITIES": {"price_multiplier": 0.40, "vol_multiplier": 3.5},  # crude oil -60%
            "DERIVATIVES": {"price_multiplier": 0.70, "vol_multiplier": 4.0},
        },
    },
    "UK_GILT_2022": {
        "name":      "UK Mini-Budget Gilt Crisis — September 2022",
        "date":      "2022-09-23",
        "reference": "Bank of England Financial Stability Report (Nov 2022)",
        "shocks": {
            "EQUITY":      {"price_multiplier": 0.95,  "vol_multiplier": 1.3},
            "RATES":       {"parallel_shift_bps": 200,  "vol_multiplier": 2.5},  # UK 30y +200bps
            "CREDIT":      {"spread_widening_bps": 100,  "vol_multiplier": 1.5},
            "FX":          {"usd_appreciation_pct": 0.08, "vol_multiplier": 1.8},  # GBP -8%
            "COMMODITIES": {"price_multiplier": 1.00, "vol_multiplier": 1.2},
            "DERIVATIVES": {"price_multiplier": 0.97, "vol_multiplier": 1.5},
        },
    },
}

# Duration proxy (years) by instrument keyword — for rate-sensitive instruments
_RATE_DURATIONS: dict[str, float] = {
    "US10Y": 8.0,
    "US2Y":  2.0,
    "US30Y": 18.0,
    "IRS":   7.0,
    "BOND":  5.0,
}

# Desk-to-shock-category mapping
_DESK_SHOCK_MAP: dict[str, str] = {
    "EQUITY":      "EQUITY",
    "RATES":       "RATES",
    "FX":          "FX",
    "CREDIT":      "CREDIT",
    "COMMODITIES": "COMMODITIES",
    "DERIVATIVES": "DERIVATIVES",
    # Alternative desk name formats
    "EQUITY_DERIVATIVES": "DERIVATIVES",
    "MM_RATES":    "RATES",
    "MACRO_FX":    "FX",
}


def _get_duration(instrument: str) -> float:
    for key, dur in _RATE_DURATIONS.items():
        if key in instrument.upper():
            return dur
    return 5.0  # default duration proxy


def _apply_shock(position: dict, shocks: dict[str, dict]) -> dict[str, Any]:
    """
    Apply scenario shocks to a single position.
    Returns {instrument, desk, notional, shock_applied, pnl_impact_usd}.
    """
    instrument = position.get("instrument", "")
    desk = str(position.get("desk", "EQUITY")).upper()
    notional = float(position.get("notional", 0.0))
    quantity = float(position.get("quantity", 0.0))

    shock_key = _DESK_SHOCK_MAP.get(desk, "EQUITY")
    shock = shocks.get(shock_key, shocks.get("EQUITY", {}))

    pnl_impact = 0.0
    shock_desc: dict = {}

    if shock_key in ("EQUITY", "COMMODITIES", "DERIVATIVES"):
        mult = shock.get("price_multiplier", 1.0)
        # sign(quantity) gives direction: long → loss if mult < 1
        direction = 1.0 if quantity >= 0 else -1.0
        pnl_impact = notional * (mult - 1.0) * direction
        shock_desc = {"price_multiplier": mult}

    elif shock_key == "RATES":
        shift_bps = shock.get("parallel_shift_bps", 0)
        duration = _get_duration(instrument)
        # Rate move: DV01-style. Rising rates → bond losses (negative duration)
        # parallel_shift_bps > 0 = rates rise = bond value falls
        # parallel_shift_bps < 0 = rates fall = bond value rises
        direction = 1.0 if quantity >= 0 else -1.0
        pnl_impact = notional * (-shift_bps / 10000) * duration * direction
        shock_desc = {"parallel_shift_bps": shift_bps, "duration_years": duration}

    elif shock_key == "CREDIT":
        spread_bps = shock.get("spread_widening_bps", 0)
        duration = _get_duration(instrument)
        direction = 1.0 if quantity >= 0 else -1.0
        # Spread widening → credit instrument value falls (negative impact on longs)
        pnl_impact = notional * (-spread_bps / 10000) * duration * direction
        shock_desc = {"spread_widening_bps": spread_bps, "duration_years": duration}

    elif shock_key == "FX":
        usd_appn = shock.get("usd_appreciation_pct", 0.0)
        # USD strengthens → long foreign currency positions lose value
        direction = 1.0 if quantity >= 0 else -1.0
        pnl_impact = notional * (-usd_appn) * direction
        shock_desc = {"usd_appreciation_pct": usd_appn}

    return {
        "instrument":    instrument,
        "desk":          desk,
        "notional":      notional,
        "quantity":      quantity,
        "shock_category": shock_key,
        "shock_applied": shock_desc,
        "pnl_impact_usd": round(pnl_impact, 2),
    }


class CrisisReplayEngine:
    """
    Historical crisis scenario tape replay against live OMS positions.
    Stateless: reads positions from risk_service at call time.
    """

    def get_scenarios(self) -> dict[str, Any]:
        """Return scenario definitions (no positions needed)."""
        return {
            "scenarios": {
                sid: {
                    "name":      s["name"],
                    "date":      s["date"],
                    "reference": s["reference"],
                    "shock_categories": list(s["shocks"].keys()),
                }
                for sid, s in CRISIS_SCENARIOS.items()
            },
            "count": len(CRISIS_SCENARIOS),
        }

    def run_replay(
        self,
        scenario_id: str,
        positions: list[dict] | None = None,
    ) -> dict[str, Any]:
        """
        Apply scenario shocks to positions and return full impact report.
        If positions is None, fetches live positions from risk_service.
        """
        if scenario_id not in CRISIS_SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario_id!r}. Valid: {list(CRISIS_SCENARIOS)}")

        scenario = CRISIS_SCENARIOS[scenario_id]

        if positions is None:
            try:
                from infrastructure.risk.risk_service import risk_service
                positions = risk_service.position_manager.get_all_positions()
            except Exception:
                positions = []

        shocks = scenario["shocks"]
        position_impacts = [_apply_shock(pos, shocks) for pos in positions]

        # Aggregate by desk
        by_desk: dict[str, float] = {}
        for pi in position_impacts:
            desk = pi["desk"]
            by_desk[desk] = round(by_desk.get(desk, 0.0) + pi["pnl_impact_usd"], 2)

        total_pnl = round(sum(pi["pnl_impact_usd"] for pi in position_impacts), 2)
        # RWA delta = abs(pnl_impact) × 12.5 (inverse of 8% capital requirement)
        rwa_delta = round(abs(total_pnl) * 12.5, 2)
        worst_desk = min(by_desk, key=by_desk.get) if by_desk else "N/A"

        result = {
            "scenario_id":    scenario_id,
            "scenario_name":  scenario["name"],
            "scenario_date":  scenario["date"],
            "reference":      scenario["reference"],
            "as_of":          datetime.now(timezone.utc).isoformat(),
            "position_count": len(position_impacts),
            "position_impacts": position_impacts,
            "summary": {
                "total_pnl_impact_usd": total_pnl,
                "by_desk":              by_desk,
                "rwa_delta_usd":        rwa_delta,
                "worst_desk":           worst_desk,
            },
            "limit_breaches": self.get_limit_breaches_from_summary(by_desk),
        }

        log.info("crisis_replay.completed", scenario_id=scenario_id,
                 total_pnl=total_pnl, positions=len(position_impacts))
        return result

    def get_limit_breaches(self, replay_result: dict) -> list[dict[str, Any]]:
        """Extract limit breaches from a completed replay result dict."""
        by_desk = replay_result.get("summary", {}).get("by_desk", {})
        return self.get_limit_breaches_from_summary(by_desk)

    def get_limit_breaches_from_summary(self, by_desk: dict[str, float]) -> list[dict[str, Any]]:
        """
        Compare desk-level P&L impact against VaR limits × 3.
        A breach = abs(desk_pnl) > limit × 3.
        """
        breaches = []
        try:
            from infrastructure.trading.limit_manager import limit_manager
            desk_limits = limit_manager.get_all_limits()
            limit_map = {d["desk"]: d.get("var_limit", 0.0) for d in desk_limits
                         if isinstance(d, dict)}
        except Exception:
            # Fallback: $500M default VaR limit per desk
            limit_map = {desk: 500_000_000.0 for desk in by_desk}

        for desk, impact in by_desk.items():
            var_limit = limit_map.get(desk, limit_map.get("FIRM", 500_000_000.0))
            breach_threshold = var_limit * 3
            if abs(impact) > breach_threshold:
                severity = "CRITICAL" if abs(impact) > breach_threshold * 2 else "SEVERE"
                breaches.append({
                    "desk":             desk,
                    "pnl_impact_usd":   impact,
                    "var_limit_usd":    var_limit,
                    "breach_threshold": round(breach_threshold, 2),
                    "breach_multiple":  round(abs(impact) / max(var_limit, 1), 2),
                    "severity":         severity,
                })

        return sorted(breaches, key=lambda b: abs(b["pnl_impact_usd"]), reverse=True)

    def run_all_scenarios(self) -> dict[str, Any]:
        """Run all three crisis scenarios and return comparative summary."""
        results: dict[str, dict] = {}
        for sid in CRISIS_SCENARIOS:
            try:
                results[sid] = self.run_replay(sid)
            except Exception as exc:
                results[sid] = {"error": str(exc), "scenario_id": sid}

        # Comparative summary
        pnl_by_scenario = {
            sid: r.get("summary", {}).get("total_pnl_impact_usd", 0.0)
            for sid, r in results.items()
            if "error" not in r
        }
        worst_scenario = min(pnl_by_scenario, key=pnl_by_scenario.get) if pnl_by_scenario else None

        return {
            "scenarios":      results,
            "comparative": {
                "pnl_by_scenario":  pnl_by_scenario,
                "worst_scenario":   worst_scenario,
                "worst_pnl_usd":    pnl_by_scenario.get(worst_scenario, 0.0) if worst_scenario else 0.0,
            },
        }


crisis_replay_engine = CrisisReplayEngine()
