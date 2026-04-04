"""
Dynamic FTP (Fund Transfer Pricing) engine.

Builds a bank-specific funding curve from:
  1. SOFR OIS base curve (current market levels)
  2. Bank credit spread by tenor (AA-rated Apex Global Bank)
  3. Liquidity premium by instrument type

FTP rate = SOFR_OIS(tenor) + bank_spread(tenor) + liquidity_premium(instrument_type)

Stress scenarios: idiosyncratic (3-notch downgrade, spreads ×2.5) and
market-wide (systemic event, spreads ×1.5).
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np


# ── SOFR OIS base curve (current market levels, %) ────────────────────────

SOFR_OIS: dict[float, float] = {
    0.003: 5.33,   # O/N
    0.083: 5.31,   # 1M
    0.25:  5.28,   # 3M
    0.50:  5.15,   # 6M
    1.00:  4.95,   # 1Y
    2.00:  4.60,   # 2Y
    3.00:  4.40,   # 3Y
    5.00:  4.25,   # 5Y
    7.00:  4.20,   # 7Y
    10.00: 4.18,   # 10Y
    20.00: 4.30,   # 20Y
    30.00: 4.35,   # 30Y
}

# Bank credit spread above SOFR OIS (bps) for AA-rated Apex Global Bank
# Keys are approximate tenors in years
BANK_SPREAD_BPS: dict[float, float] = {
    0.25:  15.0,   # short-term
    1.00:  25.0,   # 1Y
    3.00:  40.0,   # 3Y
    5.00:  60.0,   # 5Y
    10.00: 80.0,   # 10Y
}

# Stress multipliers applied to bank credit spread
STRESS_MULTIPLIERS: dict[str, float] = {
    "idiosyncratic": 2.5,    # 3-notch downgrade scenario
    "market_wide":   1.5,    # systemic market stress
}

# Liquidity premium by instrument / funding type (bps)
LIQUIDITY_PREMIUM_BPS: dict[str, float] = {
    "demand_deposit":       0.0,    # O/N funding
    "term_deposit_lt_3m":   5.0,
    "term_deposit_3m_12m": 10.0,
    "term_deposit_1y_3y":  20.0,
    "wholesale_cd_gt_3y":  30.0,
    "covered_bond":        15.0,
    "fhlb_advance":         8.0,
    "senior_unsecured":    35.0,
    "default":             20.0,
}

# Instrument type → default tenor (years) for curve lookup
INSTRUMENT_TENOR: dict[str, float] = {
    "demand_deposit":       0.003,
    "term_deposit_lt_3m":   0.17,
    "term_deposit_3m_12m":  0.50,
    "term_deposit_1y_3y":   2.00,
    "wholesale_cd_gt_3y":   5.00,
    "covered_bond":         5.00,
    "fhlb_advance":         1.00,
    "senior_unsecured":     7.00,
}


def _interp(x: float, xs: list[float], ys: list[float]) -> float:
    x_arr = np.array(xs, dtype=float)
    y_arr = np.array(ys, dtype=float)
    x_clamp = float(np.clip(x, x_arr[0], x_arr[-1]))
    return float(np.interp(x_clamp, x_arr, y_arr))


class DynamicFTPEngine:
    """Dynamic FTP engine for Apex Global Bank."""

    def _sofr_rate(self, tenor_years: float) -> float:
        tenors = sorted(SOFR_OIS.keys())
        rates = [SOFR_OIS[t] for t in tenors]
        return _interp(tenor_years, tenors, rates)

    def _bank_spread_bps(self, tenor_years: float, stress_scenario: Optional[str] = None) -> float:
        tenors = sorted(BANK_SPREAD_BPS.keys())
        spreads = [BANK_SPREAD_BPS[t] for t in tenors]
        base = _interp(tenor_years, tenors, spreads)
        if stress_scenario:
            multiplier = STRESS_MULTIPLIERS.get(stress_scenario, 1.0)
            base *= multiplier
        return base

    def get_funding_curve(self, stress_scenario: Optional[str] = None) -> dict[str, float]:
        """
        Full funding curve: tenor → all-in FTP rate (%).

        Returns rates at key tenors (SOFR + bank spread, before liquidity premium).
        """
        key_tenors = [0.003, 0.083, 0.25, 0.50, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]
        curve: dict[str, float] = {}
        for t in key_tenors:
            sofr = self._sofr_rate(t)
            spread_bps = self._bank_spread_bps(t, stress_scenario)
            all_in = sofr + spread_bps / 100.0
            label = (
                "O/N" if t < 0.01
                else f"{int(round(t * 12))}M" if t < 1.0
                else f"{int(round(t))}Y"
            )
            curve[label] = round(all_in, 4)
        return curve

    def get_ftp_rate(
        self,
        tenor_years: float,
        instrument_type: str = "default",
        stress_scenario: Optional[str] = None,
    ) -> float:
        """
        All-in FTP rate for a given tenor and instrument type.

        Returns rate in basis points.
        """
        sofr_pct = self._sofr_rate(tenor_years)
        spread_bps = self._bank_spread_bps(tenor_years, stress_scenario)
        liq_bps = LIQUIDITY_PREMIUM_BPS.get(instrument_type, LIQUIDITY_PREMIUM_BPS["default"])
        all_in_pct = sofr_pct + spread_bps / 100.0 + liq_bps / 100.0
        return round(all_in_pct * 100.0, 2)

    def calculate_desk_ftp(self, positions: list[dict]) -> dict:
        """
        Calculate FTP charges for a list of positions using the dynamic curve.

        Mirrors the structure of FTPEngine.get_ftp_summary() for drop-in compatibility.
        """
        from collections import defaultdict

        desks: dict[str, dict] = defaultdict(lambda: {"notional": 0.0, "tenor_weighted": 0.0, "product_type": "default"})

        for pos in positions:
            desk = pos.get("desk") or "UNKNOWN"
            notional = abs(float(pos.get("notional") or 0.0))
            if notional == 0.0:
                qty = abs(float(pos.get("quantity", 0.0)))
                price = abs(float(pos.get("avg_cost", 0.0)))
                notional = qty * price

            instrument = pos.get("instrument", "").upper()
            product_type = _PRODUCT_TYPE_MAP.get(instrument, "default")
            tenor = _PRODUCT_TENOR_MAP.get(product_type, 1.0)

            desks[desk]["notional"] += notional
            desks[desk]["tenor_weighted"] += notional * tenor

        by_desk = []
        total_notional = total_daily = total_annual = 0.0
        now = datetime.utcnow().isoformat()

        for desk, data in desks.items():
            notional = data["notional"]
            if notional == 0.0:
                continue
            avg_tenor = data["tenor_weighted"] / notional
            ftp_rate_bps = self.get_ftp_rate(avg_tenor, "default")
            ftp_rate_pct = ftp_rate_bps / 100.0
            daily = notional * (ftp_rate_pct / 100.0) / 365.0
            annual = notional * ftp_rate_pct / 100.0
            by_desk.append({
                "desk": desk,
                "notional_funded_usd": round(notional, 2),
                "avg_tenor_years": round(avg_tenor, 4),
                "ftp_rate_bps": round(ftp_rate_bps, 2),
                "ftp_rate_pct": round(ftp_rate_pct, 4),
                "daily_charge_usd": round(daily, 2),
                "annual_charge_usd": round(annual, 2),
                "as_of": now,
            })
            total_notional += notional
            total_daily += daily
            total_annual += annual

        by_desk.sort(key=lambda d: d["annual_charge_usd"], reverse=True)
        blended_bps = (total_annual / total_notional * 10000.0) if total_notional else 0.0

        return {
            "total_funded_notional_usd": round(total_notional, 2),
            "total_daily_charge_usd": round(total_daily, 2),
            "total_annual_charge_usd": round(total_annual, 2),
            "blended_ftp_rate_bps": round(blended_bps, 2),
            "by_desk": by_desk,
            "curve_snapshot": self.get_funding_curve(),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_stress_ftp_impact(self, positions: list[dict]) -> dict:
        """
        Incremental FTP cost under each stress scenario vs base.
        """
        base = self.calculate_desk_ftp(positions)
        results: dict[str, dict] = {}

        for scenario in STRESS_MULTIPLIERS:
            stressed_annual = 0.0
            for pos in positions:
                notional = abs(float(pos.get("notional") or 0.0))
                if notional == 0.0:
                    qty = abs(float(pos.get("quantity", 0.0)))
                    price = abs(float(pos.get("avg_cost", 0.0)))
                    notional = qty * price
                ftp_bps = self.get_ftp_rate(1.0, "default", stress_scenario=scenario)
                stressed_annual += notional * (ftp_bps / 100.0) / 100.0

            incremental = stressed_annual - base["total_annual_charge_usd"]
            results[scenario] = {
                "stressed_annual_charge_usd": round(stressed_annual, 2),
                "incremental_vs_base_usd": round(incremental, 2),
                "stress_multiplier": STRESS_MULTIPLIERS[scenario],
            }

        return {
            "base_annual_charge_usd": base["total_annual_charge_usd"],
            "stress_scenarios": results,
            "as_of": datetime.utcnow().isoformat(),
        }


# Shared product mappings (mirror from ftp.py for self-contained operation)
_PRODUCT_TYPE_MAP: dict[str, str] = {
    "AAPL": "equity",
    "MSFT": "equity",
    "GOOGL": "equity",
    "US10Y": "govt_bond",
    "US2Y": "govt_bond",
    "EURUSD": "fx_spot",
    "GBPUSD": "fx_spot",
    "IG_CDX": "cds",
    "IRS_USD_10Y": "rates_swap",
}

_PRODUCT_TENOR_MAP: dict[str, float] = {
    "equity":      0.25,
    "govt_bond":   2.00,
    "corp_bond":   5.00,
    "fx_spot":     0.08,
    "rates_swap":  7.00,
    "cds":         5.00,
    "default":     1.00,
}


dynamic_ftp_engine = DynamicFTPEngine()
