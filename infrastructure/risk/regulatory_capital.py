"""
Regulatory Capital Engine — Basel III Standardised Approach (SA) RWA and capital ratios.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger()


class RegulatoryCapitalEngine:
    """
    Basel III Standardised Approach regulatory capital calculator.

    Computes Risk-Weighted Assets (RWA) by asset class, CET1/Tier1/Total
    capital ratios, leverage ratio, and capital buffer analysis.
    """

    # SA risk weights by product type
    RISK_WEIGHTS: dict[str, float] = {
        "equity":        1.00,   # 100% RW for listed equities
        "govt_bond":     0.00,   # 0% RW for AAA-AA sovereign (US Treasuries)
        "corp_bond":     0.50,   # 50% RW IG corporates (simplified)
        "fx_spot":       0.08,   # 8% RW (FX capital charge proxy)
        "rates_swap":    0.20,   # 20% RW (SA-CCR simplified)
        "cds":           1.00,   # 100% RW (credit derivatives)
        "equity_option": 1.00,   # 100% RW
    }

    # Ticker → product type mapping
    PRODUCT_TYPE_MAP: dict[str, str] = {
        "AAPL":           "equity",
        "MSFT":           "equity",
        "GOOGL":          "equity",
        "NVDA":           "equity",
        "US10Y":          "govt_bond",
        "US2Y":           "govt_bond",
        "EURUSD":         "fx_spot",
        "GBPUSD":         "fx_spot",
        "IG_CDX":         "cds",
        "HYEM_ETF":       "corp_bond",
        "IRS_USD_10Y":    "rates_swap",
        "SPX_CALL_5200":  "equity_option",
    }

    # Apex Global Bank capital structure (JPMorgan-scale)
    CET1_CAPITAL_USD:    float = 45_000_000_000.0   # $45B CET1
    TIER1_CAPITAL_USD:   float = 52_000_000_000.0   # $52B Tier 1
    TOTAL_CAPITAL_USD:   float = 60_000_000_000.0   # $60B total capital
    TOTAL_EXPOSURE_USD:  float = 900_000_000_000.0   # $900B trading-book leverage exposure

    # Capital ratio targets / minimums
    CET1_MIN            = 0.045   # Basel III minimum 4.5%
    CET1_TARGET         = 0.130   # 13% internal target
    TIER1_MIN           = 0.060   # 6% minimum
    TIER1_TARGET        = 0.145   # 14.5% target
    TOTAL_CAPITAL_MIN   = 0.080   # 8% minimum
    TOTAL_CAPITAL_TARGET= 0.165   # 16.5% target
    LEVERAGE_RATIO_MIN  = 0.030   # 3% minimum

    def _notional(self, pos: dict) -> float:
        if "notional" in pos:
            return abs(float(pos["notional"]))
        qty = float(pos.get("quantity", pos.get("qty", 0)))
        price = float(pos.get("avg_cost", pos.get("price", 1.0)))
        return abs(qty * price)

    def _product_type(self, ticker: str) -> str:
        return self.PRODUCT_TYPE_MAP.get(ticker, "equity")  # conservative default

    def calculate(self, positions: list[dict]) -> dict[str, Any]:
        rwa_by_asset_class: dict[str, float] = {pt: 0.0 for pt in self.RISK_WEIGHTS}

        for pos in positions:
            ticker = str(pos.get("instrument", pos.get("ticker", "UNKNOWN")))
            notional = self._notional(pos)
            product_type = self._product_type(ticker)
            rw = self.RISK_WEIGHTS.get(product_type, 1.00)
            rwa_by_asset_class[product_type] = rwa_by_asset_class.get(product_type, 0.0) + notional * rw

        rwa_total = sum(rwa_by_asset_class.values())

        # When simulation positions are empty, use a baseline RWA that produces the
        # bank's 13% CET1 target: $45B / 13% = ~$346B. This is the trading-book
        # RWA slice; full balance-sheet RWA would be ~$1.28T but we only model the
        # trading book in the simulation.
        BASELINE_RWA = 346_000_000_000.0  # $346B → 13% CET1 at $45B capital
        rwa_floor = max(rwa_total, BASELINE_RWA)

        cet1_ratio    = self.CET1_CAPITAL_USD   / rwa_floor
        tier1_ratio   = self.TIER1_CAPITAL_USD  / rwa_floor
        total_ratio   = self.TOTAL_CAPITAL_USD  / rwa_floor
        leverage_ratio= self.CET1_CAPITAL_USD   / self.TOTAL_EXPOSURE_USD

        breaches: list[str] = []
        if cet1_ratio  < self.CET1_MIN:
            breaches.append(f"CET1 {cet1_ratio:.2%} < minimum {self.CET1_MIN:.1%}")
        if tier1_ratio < self.TIER1_MIN:
            breaches.append(f"Tier1 {tier1_ratio:.2%} < minimum {self.TIER1_MIN:.1%}")
        if total_ratio < self.TOTAL_CAPITAL_MIN:
            breaches.append(f"Total capital {total_ratio:.2%} < minimum {self.TOTAL_CAPITAL_MIN:.1%}")
        if leverage_ratio < self.LEVERAGE_RATIO_MIN:
            breaches.append(f"Leverage ratio {leverage_ratio:.2%} < minimum {self.LEVERAGE_RATIO_MIN:.1%}")

        log.info(
            "regulatory_capital.calculated",
            rwa_total=round(rwa_total, 0),
            cet1_ratio=round(cet1_ratio, 4),
            breaches=len(breaches),
        )

        return {
            "rwa_total_usd":       round(rwa_total, 2),
            "rwa_by_asset_class":  {k: round(v, 2) for k, v in rwa_by_asset_class.items()},
            "cet1_ratio":          round(cet1_ratio, 6),
            "tier1_ratio":         round(tier1_ratio, 6),
            "total_capital_ratio": round(total_ratio, 6),
            "leverage_ratio":      round(leverage_ratio, 6),
            "cet1_buffer":         round(cet1_ratio - self.CET1_MIN, 6),
            "cet1_vs_target":      round(cet1_ratio - self.CET1_TARGET, 6),
            "capital_adequate":    len(breaches) == 0,
            "breaches":            breaches,
            "as_of":               datetime.now(timezone.utc).isoformat(),
        }

    def get_minimum_capital_requirement(self, rwa: float) -> dict[str, float]:
        return {
            "cet1_min":    round(rwa * self.CET1_MIN, 2),
            "tier1_min":   round(rwa * self.TIER1_MIN, 2),
            "total_min":   round(rwa * self.TOTAL_CAPITAL_MIN, 2),
        }


capital_engine = RegulatoryCapitalEngine()
