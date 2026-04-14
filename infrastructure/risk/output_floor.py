"""
Basel III Endgame Output Floor — CRE10.

Floor RWA = max(IMA RWA, 72.5% × SA RWA)
Reports floored and unfloored capital ratios.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger(__name__)

FLOOR_RATE: float = 0.725   # 72.5%


class OutputFloorEngine:
    """
    Applies the Basel III 72.5% SA RWA output floor.

    For banks not running IMA, the floor is informational — SA RWA is already
    the floor. When IMA RWA is provided, calculates the binding floor and
    reports the impact in basis points.
    """

    def apply_floor(
        self,
        sa_rwa: float,
        ima_rwa: float | None = None,
    ) -> dict[str, Any]:
        """
        Apply the output floor.

        Returns floored_rwa, floor_binding flag, and impact in basis points.
        """
        floor_rwa = sa_rwa * FLOOR_RATE

        if ima_rwa is None:
            # SA-only bank: floor is informational
            floored_rwa = sa_rwa
            floor_binding = False
            floor_impact_bps = 0
            ima_rwa_used = sa_rwa   # placeholder — IMA not applicable
        else:
            floored_rwa = max(ima_rwa, floor_rwa)
            floor_binding = ima_rwa < floor_rwa
            # Impact = (floored_rwa - ima_rwa) / ima_rwa in bps
            if ima_rwa > 0:
                floor_impact_bps = round((floored_rwa - ima_rwa) / ima_rwa * 10_000, 1)
            else:
                floor_impact_bps = 0
            ima_rwa_used = ima_rwa

        log.info(
            "output_floor.applied",
            sa_rwa=round(sa_rwa, 0),
            floored_rwa=round(floored_rwa, 0),
            floor_binding=floor_binding,
            floor_impact_bps=floor_impact_bps,
        )

        return {
            "floor_rate":        FLOOR_RATE,
            "sa_rwa_usd":        round(sa_rwa, 2),
            "ima_rwa_usd":       round(ima_rwa_used, 2) if ima_rwa is not None else None,
            "floor_rwa_usd":     round(floor_rwa, 2),
            "floored_rwa_usd":   round(floored_rwa, 2),
            "floor_binding":     floor_binding,
            "floor_impact_bps":  floor_impact_bps,
            "sa_only_bank":      ima_rwa is None,
        }

    def calculate_floored_ratios(
        self,
        cet1: float,
        tier1: float,
        total_capital: float,
        sa_rwa: float,
        ima_rwa: float | None = None,
    ) -> dict[str, Any]:
        """
        Compute capital ratios on both floored and unfloored RWA.
        """
        floor_result = self.apply_floor(sa_rwa, ima_rwa)
        floored_rwa = floor_result["floored_rwa_usd"]
        unfloored_rwa = ima_rwa if ima_rwa is not None else sa_rwa

        def _ratios(rwa: float) -> dict[str, float]:
            if rwa <= 0:
                return {"cet1": 0.0, "tier1": 0.0, "total": 0.0}
            return {
                "cet1":  round(cet1  / rwa, 6),
                "tier1": round(tier1 / rwa, 6),
                "total": round(total_capital / rwa, 6),
            }

        unfloored = _ratios(unfloored_rwa)
        floored   = _ratios(floored_rwa)

        log.info(
            "output_floor.ratios_calculated",
            floored_cet1=floored["cet1"],
            unfloored_cet1=unfloored["cet1"],
            floor_binding=floor_result["floor_binding"],
        )

        return {
            "floor_result":    floor_result,
            "unfloored_ratios": unfloored,
            "floored_ratios":   floored,
            "cet1_impact_bps": round(
                (unfloored["cet1"] - floored["cet1"]) * 10_000, 1
            ) if floor_result["floor_binding"] else 0,
        }


output_floor_engine = OutputFloorEngine()
