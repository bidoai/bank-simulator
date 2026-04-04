"""
Large Exposures Framework — Basel LE Standard (CRE70).

Single counterparty limit: 25% of Tier 1 capital.
G-SIB to G-SIB limit: 15% of Tier 1 capital.
Early warning: 10% of Tier 1 capital.
"""
from __future__ import annotations

from typing import Any

import structlog

from infrastructure.risk.counterparty_registry import counterparty_registry

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Apex Global Bank Tier 1 capital (from regulatory_capital.py)
# ---------------------------------------------------------------------------

TIER1_CAPITAL_USD: float = 52_000_000_000.0  # $52B

# G-SIBs in the counterparty registry
GSIB_COUNTERPARTY_IDS: set[str] = {
    "Goldman_Sachs",
    "JPMorgan_Chase",
    "Deutsche_Bank",
    "BNP_Paribas",
    "HSBC",
}

# Limit thresholds (as % of Tier 1)
SINGLE_CP_LIMIT_RATE:  float = 0.25   # 25%
GSIB_TO_GSIB_LIMIT:    float = 0.15   # 15%
EARLY_WARNING_RATE:    float = 0.10   # 10%


# ---------------------------------------------------------------------------
# Sample on-balance-sheet exposures (loans, bonds, repos) to supplement
# derivative EAD. Representative balances — not from live positions.
# ---------------------------------------------------------------------------

SAMPLE_OBS_EXPOSURES: dict[str, float] = {
    "Goldman_Sachs":  3_500_000_000.0,   # $3.5B (repos + bonds)
    "JPMorgan_Chase": 4_200_000_000.0,   # $4.2B
    "Deutsche_Bank":  2_100_000_000.0,   # $2.1B
    "BNP_Paribas":    1_800_000_000.0,   # $1.8B
    "HSBC":           2_600_000_000.0,   # $2.6B
}


class LargeExposuresEngine:
    """
    Calculates and monitors large exposures against CRE70 limits.
    """

    def __init__(self, tier1_capital: float = TIER1_CAPITAL_USD) -> None:
        self.tier1_capital = tier1_capital

    def calculate_exposures(
        self,
        positions: list[dict[str, Any]] | None = None,
        sa_ccr_eads: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Compute total large exposure per counterparty.

        Exposure = on-balance-sheet + SA-CCR EAD (derivatives) + off-BS commitments.
        Uses sample on-balance-sheet balances plus registry current_ead as proxy
        when sa_ccr_eads is not provided.
        """
        # Build SA-CCR EAD map
        ead_map: dict[str, float] = {}
        if sa_ccr_eads:
            for entry in sa_ccr_eads:
                cp_id = entry.get("counterparty_id", "")
                ead_map[cp_id] = float(entry.get("ead_usd", 0.0))
        else:
            # Fall back to registry current_ead
            for cp in counterparty_registry.get_all():
                ead_map[cp.id] = cp.current_ead

        results: list[dict[str, Any]] = []
        for cp in counterparty_registry.get_all():
            obs = SAMPLE_OBS_EXPOSURES.get(cp.id, 0.0)
            deriv_ead = ead_map.get(cp.id, 0.0)
            total = obs + deriv_ead

            is_gsib = cp.id in GSIB_COUNTERPARTY_IDS
            limit_rate = GSIB_TO_GSIB_LIMIT if is_gsib else SINGLE_CP_LIMIT_RATE
            limit_usd = self.tier1_capital * limit_rate
            warning_usd = self.tier1_capital * EARLY_WARNING_RATE

            utilization = total / limit_usd if limit_usd > 0 else 0.0

            results.append({
                "counterparty_id":    cp.id,
                "counterparty_name":  cp.name,
                "rating":             cp.rating,
                "is_gsib":            is_gsib,
                "obs_exposure_usd":   round(obs, 2),
                "derivative_ead_usd": round(deriv_ead, 2),
                "total_exposure_usd": round(total, 2),
                "limit_rate":         limit_rate,
                "limit_usd":          round(limit_usd, 2),
                "warning_usd":        round(warning_usd, 2),
                "utilization_pct":    round(utilization * 100.0, 2),
            })

        return sorted(results, key=lambda x: x["total_exposure_usd"], reverse=True)

    def check_limits(
        self,
        exposures: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        """
        Check each counterparty exposure against CRE70 limits.

        Status: OK / WARNING (>10% T1) / BREACH (>limit)
        """
        if exposures is None:
            exposures = self.calculate_exposures()

        results = []
        for exp in exposures:
            total  = exp["total_exposure_usd"]
            limit  = exp["limit_usd"]
            warn   = exp["warning_usd"]

            if total > limit:
                status = "BREACH"
            elif total > warn:
                status = "WARNING"
            else:
                status = "OK"

            results.append({
                **exp,
                "status": status,
                "excess_usd": round(max(0.0, total - limit), 2),
            })

        return results

    def get_summary(
        self,
        exposures: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Aggregate summary of large exposure position."""
        if exposures is None:
            exposures = self.calculate_exposures()

        limit_checks = self.check_limits(exposures)

        total_exposure = sum(e["total_exposure_usd"] for e in exposures)
        n_breach  = sum(1 for e in limit_checks if e["status"] == "BREACH")
        n_warning = sum(1 for e in limit_checks if e["status"] == "WARNING")
        n_ok      = sum(1 for e in limit_checks if e["status"] == "OK")

        log.info(
            "large_exposures.summary",
            total_exposure_usd=round(total_exposure, 0),
            n_breach=n_breach,
            n_warning=n_warning,
        )

        return {
            "tier1_capital_usd":     round(self.tier1_capital, 2),
            "single_cp_limit_rate":  SINGLE_CP_LIMIT_RATE,
            "gsib_limit_rate":       GSIB_TO_GSIB_LIMIT,
            "early_warning_rate":    EARLY_WARNING_RATE,
            "single_cp_limit_usd":   round(self.tier1_capital * SINGLE_CP_LIMIT_RATE, 2),
            "gsib_limit_usd":        round(self.tier1_capital * GSIB_TO_GSIB_LIMIT, 2),
            "total_exposure_usd":    round(total_exposure, 2),
            "counterparty_count":    len(exposures),
            "status_ok":             n_ok,
            "status_warning":        n_warning,
            "status_breach":         n_breach,
            "compliant":             n_breach == 0,
        }


large_exposures_engine = LargeExposuresEngine()
