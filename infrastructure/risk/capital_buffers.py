"""
Capital Buffer Stack — Basel III Combined Buffer Requirement and MDA.

Implements CCB, CCyB, G-SIB surcharge, Pillar 2 add-on, and MDA restriction
per Basel III CRE40 and CRD IV/V.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Apex Global Bank — capital structure (consistent with regulatory_capital.py)
# ---------------------------------------------------------------------------

CET1_CAPITAL_USD:   float = 45_000_000_000.0   # $45B
TIER1_CAPITAL_USD:  float = 52_000_000_000.0   # $52B
TOTAL_CAPITAL_USD:  float = 60_000_000_000.0   # $60B
BASELINE_RWA_USD:   float = 346_000_000_000.0  # $346B

# Minimum capital ratios (Basel III Pillar 1)
CET1_MIN:         float = 0.045
TIER1_MIN:        float = 0.060
TOTAL_CAPITAL_MIN: float = 0.080

# G-SIB bucket surcharges (% of RWA)
GSIB_BUCKET_SURCHARGES: dict[int, float] = {
    1: 0.010,
    2: 0.015,
    3: 0.020,
    4: 0.025,
    5: 0.035,
}

# Apex Global Bank is a Bucket 2 G-SIB
APEX_GSIB_BUCKET: int = 2


class CapitalBufferEngine:
    """
    Compute buffer stack, CBR, and Maximum Distributable Amount (MDA).
    """

    def __init__(
        self,
        ccb: float = 0.025,
        ccyb: float = 0.0,
        gsib_bucket: int = APEX_GSIB_BUCKET,
        pillar2_addon: float = 0.010,
    ) -> None:
        self.ccb           = ccb
        self.ccyb          = ccyb
        self.gsib_surcharge = GSIB_BUCKET_SURCHARGES[gsib_bucket]
        self.gsib_bucket   = gsib_bucket
        self.pillar2_addon = pillar2_addon

    def calculate_buffers(
        self,
        cet1_ratio: float,
        tier1_ratio: float,
        total_ratio: float,
        rwa: float,
    ) -> dict[str, Any]:
        """
        Full buffer stack analysis.

        Returns buffer amounts (in USD), CBR, and breach status.
        """
        cbr = self.ccb + self.ccyb + self.gsib_surcharge

        # Buffer amounts in USD
        ccb_usd   = rwa * self.ccb
        ccyb_usd  = rwa * self.ccyb
        gsib_usd  = rwa * self.gsib_surcharge
        p2_usd    = rwa * self.pillar2_addon
        cbr_usd   = rwa * cbr

        # Overall CET1 requirement = min CET1 + CBR
        total_cet1_req = CET1_MIN + cbr

        # Headroom
        cet1_headroom = cet1_ratio - total_cet1_req
        cet1_over_cbr = cet1_ratio - (CET1_MIN + cbr)

        breaches: list[str] = []
        warnings: list[str] = []

        if cet1_ratio < CET1_MIN:
            breaches.append(f"CET1 {cet1_ratio:.2%} < minimum {CET1_MIN:.1%}")
        elif cet1_ratio < total_cet1_req:
            breaches.append(
                f"CET1 {cet1_ratio:.2%} < minimum + CBR requirement {total_cet1_req:.2%} — MDA restrictions apply"
            )
        elif cet1_over_cbr < 0.005:
            warnings.append(f"CET1 within 50bps of combined buffer ({cbr:.2%} CBR)")

        if tier1_ratio < TIER1_MIN:
            breaches.append(f"Tier1 {tier1_ratio:.2%} < minimum {TIER1_MIN:.1%}")
        if total_ratio < TOTAL_CAPITAL_MIN:
            breaches.append(f"Total capital {total_ratio:.2%} < minimum {TOTAL_CAPITAL_MIN:.1%}")

        log.info(
            "capital_buffers.calculated",
            cbr=round(cbr, 4),
            cet1_ratio=round(cet1_ratio, 4),
            total_cet1_req=round(total_cet1_req, 4),
            breaches=len(breaches),
        )

        return {
            "ccb_rate":     self.ccb,
            "ccyb_rate":    self.ccyb,
            "gsib_rate":    self.gsib_surcharge,
            "gsib_bucket":  self.gsib_bucket,
            "pillar2_rate": self.pillar2_addon,
            "cbr_rate":     round(cbr, 6),
            "total_cet1_requirement_rate": round(total_cet1_req, 6),
            "ccb_usd":          round(ccb_usd, 2),
            "ccyb_usd":         round(ccyb_usd, 2),
            "gsib_surcharge_usd": round(gsib_usd, 2),
            "pillar2_usd":      round(p2_usd, 2),
            "cbr_usd":          round(cbr_usd, 2),
            "cet1_ratio":       round(cet1_ratio, 6),
            "tier1_ratio":      round(tier1_ratio, 6),
            "total_capital_ratio": round(total_ratio, 6),
            "cet1_over_cbr":    round(cet1_over_cbr, 6),
            "rwa_usd":          round(rwa, 2),
            "breaches":         breaches,
            "warnings":         warnings,
            "buffer_adequate":  len(breaches) == 0,
        }

    def calculate_mda(
        self,
        cet1_ratio: float,
        rwa: float,
        distributable_earnings: float,
    ) -> dict[str, Any]:
        """
        Maximum Distributable Amount (MDA) calculation.

        MDA restrictions apply when CET1 < CET1_min + CBR.
        Restriction factor is based on quartile position within the CBR.
        """
        cbr = self.ccb + self.ccyb + self.gsib_surcharge
        floor = CET1_MIN           # CET1 minimum below which the buffer is fully consumed
        ceiling = CET1_MIN + cbr   # Full CBR satisfied above this

        if cet1_ratio >= ceiling:
            restriction_factor = 1.0
            distribution_status = "UNRESTRICTED"
        elif cet1_ratio < floor:
            restriction_factor = 0.0
            distribution_status = "SUSPENDED"
        else:
            # Position within the CBR (0 = at floor, 1 = at ceiling)
            position = (cet1_ratio - floor) / cbr  # 0 to 1

            # Quartile thresholds
            if position < 0.25:
                restriction_factor = 0.0
                distribution_status = "SUSPENDED"
            elif position < 0.50:
                restriction_factor = 0.20
                distribution_status = "RESTRICTED_Q2"
            elif position < 0.75:
                restriction_factor = 0.40
                distribution_status = "RESTRICTED_Q3"
            else:
                restriction_factor = 0.60
                distribution_status = "RESTRICTED_Q4"

        mda_amount = max(0.0, distributable_earnings * restriction_factor)
        cet1_usd = rwa * cet1_ratio

        log.info(
            "capital_buffers.mda_calculated",
            cet1_ratio=round(cet1_ratio, 4),
            restriction_factor=restriction_factor,
            mda_amount=round(mda_amount, 0),
            status=distribution_status,
        )

        return {
            "cet1_ratio":            round(cet1_ratio, 6),
            "cbr_rate":              round(cbr, 6),
            "cet1_min_rate":         CET1_MIN,
            "full_requirement_rate": round(ceiling, 6),
            "distributable_earnings_usd": round(distributable_earnings, 2),
            "restriction_factor":    round(restriction_factor, 4),
            "mda_usd":               round(mda_amount, 2),
            "cet1_usd":              round(cet1_usd, 2),
            "distribution_status":   distribution_status,
            "mda_restricted":        restriction_factor < 1.0,
        }


capital_buffer_engine = CapitalBufferEngine()
