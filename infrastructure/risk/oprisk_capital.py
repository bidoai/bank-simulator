"""
Operational Risk Capital Engine — Basel III Business Indicator Approach (BIA).

Implements CRE10 Business Indicator Component (BIC) and the Basic Indicator
Approach (BIA) fallback. Uses representative 3-year average income statement
figures consistent with the bank's JPMorgan-scale balance sheet.
"""
from __future__ import annotations

from typing import Any

import structlog

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Representative 3-year average income statement (Apex Global Bank)
# Consistent with $45B CET1 / $346B RWA baseline
# ---------------------------------------------------------------------------

_INCOME_STATEMENT = {
    "net_interest_income_usd":       12_000_000_000.0,   # $12B/yr
    "net_interest_income_margin_usd": 12_500_000_000.0,  # ~$12.5B income from interest-generating assets
    "fee_income_usd":                  8_000_000_000.0,
    "fee_expense_usd":                 3_000_000_000.0,
    "other_operating_income_usd":      1_000_000_000.0,
    "other_operating_expense_usd":       400_000_000.0,
    "trading_book_pnl_abs_usd":        2_000_000_000.0,
    "banking_book_pnl_abs_usd":          500_000_000.0,
}

# RWA conversion factor: capital charge → RWA equivalent (12.5 = 1 / 8%)
CAPITAL_TO_RWA = 12.5


class OpRiskCapitalEngine:
    """
    Operational Risk Capital via Basel III Business Indicator Approach.
    Also provides Basic Indicator Approach (BIA) fallback.
    """

    def __init__(self, income_statement: dict[str, float] | None = None) -> None:
        self._income = income_statement or _INCOME_STATEMENT

    # ------------------------------------------------------------------
    # Business Indicator Approach
    # ------------------------------------------------------------------

    def calculate_bia(self) -> dict[str, Any]:
        """
        Compute Business Indicator and BIC per Basel III CRE10.

        BI = ILDC + SC + FC
        BIC (Bucket 1, BI ≤ €1B): BI × 12%
        BIC (Bucket 2, €1B < BI ≤ €30B): €0.12B + (BI - €1B) × 15%
        BIC (Bucket 3, BI > €30B): €4.47B + (BI - €30B) × 18%
        """
        # ILDC: avg(|net interest income|, |NII margin|)
        ildc = (
            abs(self._income["net_interest_income_usd"])
            + abs(self._income["net_interest_income_margin_usd"])
        ) / 2.0

        # SC: max(fee income, fee expense) + max(other op income, other op expense)
        sc = (
            max(self._income["fee_income_usd"], self._income["fee_expense_usd"])
            + max(self._income["other_operating_income_usd"],
                  self._income["other_operating_expense_usd"])
        )

        # FC: |trading book P&L| + |banking book P&L|
        fc = (
            abs(self._income["trading_book_pnl_abs_usd"])
            + abs(self._income["banking_book_pnl_abs_usd"])
        )

        bi = ildc + sc + fc

        # Tiered BIC calculation
        bucket_1_ceiling = 1_000_000_000.0    # €1B ≈ $1B (simplified)
        bucket_2_ceiling = 30_000_000_000.0   # €30B ≈ $30B

        if bi <= bucket_1_ceiling:
            bucket = 1
            multiplier = 0.12
            bic = bi * multiplier
        elif bi <= bucket_2_ceiling:
            bucket = 2
            multiplier = 0.15
            bic = (bucket_1_ceiling * 0.12) + (bi - bucket_1_ceiling) * multiplier
        else:
            bucket = 3
            multiplier = 0.18
            # €0.12B + (€30B - €1B) × 15% + (BI - €30B) × 18%
            tier1 = bucket_1_ceiling * 0.12
            tier2 = (bucket_2_ceiling - bucket_1_ceiling) * 0.15
            bic = tier1 + tier2 + (bi - bucket_2_ceiling) * multiplier

        oprisk_rwa = bic * CAPITAL_TO_RWA

        log.info(
            "oprisk.bia_calculated",
            bi_usd=round(bi, 0),
            bic_usd=round(bic, 0),
            bucket=bucket,
            rwa_usd=round(oprisk_rwa, 0),
        )

        return {
            "method": "Business Indicator Approach (BIA)",
            "components": {
                "ildc_usd": round(ildc, 2),
                "sc_usd":   round(sc, 2),
                "fc_usd":   round(fc, 2),
            },
            "bi_usd":          round(bi, 2),
            "bucket":          bucket,
            "marginal_rate":   multiplier,
            "bic_usd":         round(bic, 2),
            "oprisk_rwa_usd":  round(oprisk_rwa, 2),
            "capital_ratio_conversion": CAPITAL_TO_RWA,
        }

    # ------------------------------------------------------------------
    # Basic Indicator Approach (BIA fallback)
    # ------------------------------------------------------------------

    def calculate_basic_indicator(self) -> dict[str, Any]:
        """
        Basic Indicator Approach: 15% × 3-year average gross income.

        Gross income = net interest income + non-interest income.
        """
        nii = self._income["net_interest_income_usd"]
        non_interest = (
            self._income["fee_income_usd"]
            + self._income["other_operating_income_usd"]
            + self._income["trading_book_pnl_abs_usd"]
            + self._income["banking_book_pnl_abs_usd"]
        )
        gross_income_avg = nii + non_interest   # already 3yr avg from _INCOME_STATEMENT

        capital_charge = gross_income_avg * 0.15
        rwa = capital_charge * CAPITAL_TO_RWA

        log.info(
            "oprisk.basic_indicator_calculated",
            gross_income_usd=round(gross_income_avg, 0),
            capital_charge_usd=round(capital_charge, 0),
        )

        return {
            "method": "Basic Indicator Approach",
            "gross_income_3yr_avg_usd": round(gross_income_avg, 2),
            "alpha":                    0.15,
            "capital_charge_usd":       round(capital_charge, 2),
            "oprisk_rwa_usd":           round(rwa, 2),
            "capital_ratio_conversion": CAPITAL_TO_RWA,
        }


oprisk_engine = OpRiskCapitalEngine()
