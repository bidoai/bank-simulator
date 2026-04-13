"""
Asset-Liability Management (ALM) engine.

Models interest rate risk in the banking book:
  - Repricing gap schedule (7 buckets)
  - NII sensitivity to rate shocks
  - EVE sensitivity to rate shocks
  - Duration gap
  - SVB-style warning if +200bps shock > 15% of equity

Silicon Valley Bank failed in March 2023 because their $120B fixed-rate
securities portfolio had no EVE sensitivity reporting. This engine ensures
that failure mode is visible.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
import numpy as np
import structlog

log = structlog.get_logger(__name__)


# ── Repricing buckets ──────────────────────────────────────────────────────

BUCKETS = ["0-1m", "1-3m", "3-6m", "6-12m", "1-3y", "3-5y", "5y+"]

# Bucket midpoint in years (used for duration / PV approximations)
BUCKET_MID_YEARS = [0.04, 0.17, 0.375, 0.75, 2.0, 4.0, 10.0]


@dataclass
class RepricePoint:
    bucket: str
    asset_notional: float
    liability_notional: float
    gap: float              # assets − liabilities
    cumulative_gap: float

    def to_dict(self) -> dict:
        return asdict(self)


# ── Apex Global Bank simplified balance sheet ($B) ──────────────────────

ASSETS = {
    "loans_fixed":        600e9,   # fixed-rate corporate / consumer loans
    "loans_floating":     400e9,   # SOFR-linked floating rate loans
    "securities_fixed":   800e9,   # AFS / HTM fixed-rate securities
    "securities_floating": 200e9,  # FRNs, SOFR-linked notes
    "cash_short":         150e9,   # cash + ST investments (reprices O/N)
    "trading_assets":     300e9,   # trading book (short duration ~0.5yr)
    "other":              750e9,   # intangibles, goodwill, other (no IR sensitivity)
}

LIABILITIES = {
    "demand_deposits":     700e9,  # non-maturity deposits (behavioral model)
    "time_deposits":       400e9,  # CDs with contractual repricing
    "wholesale_st":        500e9,  # short-term wholesale funding (<1yr)
    "wholesale_lt":        600e9,  # long-term wholesale / senior unsecured
    "other":               700e9,  # other liabilities (no IR sensitivity)
}

# Capital = ~$300B implied (assets $3.2T − liabilities $2.9T)
EQUITY_USD = 300e9

# Baseline annual NII (JPMorgan-scale estimate, %)
BASE_NII_YIELD_PCT = 0.0175   # ~1.75% NIM on $3.2T assets → ~$56B NII


class BehavioralAssumptions:
    """
    Non-maturity deposit behavioral model.

    Demand deposits are contractually repayable on demand but empirically
    behave as long-dated, stable funding. Parameters are now driven by the
    NMD model; these values are retained as fallback for the repricing schedule.
    """
    CORE_PCT: float
    NON_CORE_PCT: float

    def __init__(self) -> None:
        try:
            from infrastructure.treasury.nmd_model import nmd_model as _nmd
            profile = _nmd.get_core_duration_profile()
            total_bal = sum(v["balance_usd"] for v in profile.values())
            total_core = sum(v["core_amount_usd"] for v in profile.values())
            self.CORE_PCT = total_core / total_bal if total_bal else 0.70
            self.NON_CORE_PCT = 1.0 - self.CORE_PCT
        except Exception:
            self.CORE_PCT = 0.70
            self.NON_CORE_PCT = 0.30


def _build_repricing_schedule() -> list[RepricePoint]:
    """
    Distribute assets and liabilities across the 7 repricing buckets.
    Applies behavioral assumptions to non-maturity deposits.
    """
    ba = BehavioralAssumptions()   # now reads from NMDModel

    # Asset allocation per bucket (index 0-6 → 0-1m, 1-3m, 3-6m, 6-12m, 1-3y, 3-5y, 5y+)
    asset_alloc = [0.0] * 7
    # Cash / short-term → overnight (bucket 0)
    asset_alloc[0] += ASSETS["cash_short"]
    # Floating loans → 3-6m reset (bucket 2)
    asset_alloc[2] += ASSETS["loans_floating"]
    # Securities floating → 6-12m (bucket 3)
    asset_alloc[3] += ASSETS["securities_floating"]
    # Trading assets → 0-6m (split 0-1m, 1-3m)
    asset_alloc[0] += ASSETS["trading_assets"] * 0.40
    asset_alloc[1] += ASSETS["trading_assets"] * 0.60
    # Fixed-rate loans → long-dated: 1-3y, 3-5y, 5y+ (equal thirds)
    for i in [4, 5, 6]:
        asset_alloc[i] += ASSETS["loans_fixed"] / 3.0
    # Fixed-rate securities → 3-5y and 5y+ (40/60 split, heavy long end)
    asset_alloc[5] += ASSETS["securities_fixed"] * 0.40
    asset_alloc[6] += ASSETS["securities_fixed"] * 0.60

    # Liability allocation
    liab_alloc = [0.0] * 7
    # Demand deposits — behavioral split
    demand = LIABILITIES["demand_deposits"]
    non_core = demand * ba.NON_CORE_PCT
    core = demand * ba.CORE_PCT
    # Non-core: spread evenly across 0-12m buckets (0,1,2,3)
    for i in range(4):
        liab_alloc[i] += non_core / 4.0
    # Core: 5yr+ bucket
    liab_alloc[6] += core

    # Time deposits — distributed across 1-3y and 3-5y
    liab_alloc[4] += LIABILITIES["time_deposits"] * 0.50
    liab_alloc[5] += LIABILITIES["time_deposits"] * 0.50

    # Short-term wholesale → 0-12m (heavier near end)
    liab_alloc[0] += LIABILITIES["wholesale_st"] * 0.20
    liab_alloc[1] += LIABILITIES["wholesale_st"] * 0.25
    liab_alloc[2] += LIABILITIES["wholesale_st"] * 0.30
    liab_alloc[3] += LIABILITIES["wholesale_st"] * 0.25

    # Long-term wholesale → 3-5y and 5y+
    liab_alloc[5] += LIABILITIES["wholesale_lt"] * 0.45
    liab_alloc[6] += LIABILITIES["wholesale_lt"] * 0.55

    points: list[RepricePoint] = []
    cumulative = 0.0
    for i, bucket in enumerate(BUCKETS):
        gap = asset_alloc[i] - liab_alloc[i]
        cumulative += gap
        points.append(RepricePoint(
            bucket=bucket,
            asset_notional=round(asset_alloc[i], 0),
            liability_notional=round(liab_alloc[i], 0),
            gap=round(gap, 0),
            cumulative_gap=round(cumulative, 0),
        ))
    return points


class ALMEngine:
    """
    Asset-Liability Management engine for Apex Global Bank.

    Shock scenarios: -200, -100, -50, +50, +100, +200, +300 bps.
    """

    RATE_SHOCKS_BPS: list[int] = [-200, -100, -50, +50, +100, +200, +300]

    def get_repricing_gap_schedule(self) -> list[RepricePoint]:
        return _build_repricing_schedule()

    def nii_sensitivity(self) -> dict:
        """
        NII sensitivity using a simplified 1-year repricing gap approach.

        Assets repricing within 12 months earn more when rates rise.
        Liabilities repricing within 12 months cost more when rates rise.
        Net 12m repricing gap × rate shock ≈ NII impact over the next year.
        """
        schedule = _build_repricing_schedule()
        # Sum assets and liabilities repricing within 1 year (buckets 0-3)
        asset_1yr = sum(p.asset_notional for p in schedule[:4])
        liab_1yr = sum(p.liability_notional for p in schedule[:4])
        gap_1yr = asset_1yr - liab_1yr   # positive = asset-sensitive

        total_assets = sum(ASSETS.values())
        base_nii = total_assets * BASE_NII_YIELD_PCT

        shocks = []
        for shock_bps in self.RATE_SHOCKS_BPS:
            delta = gap_1yr * (shock_bps / 10_000.0)
            shocks.append({
                "shock_bps": shock_bps,
                "delta_nii_usd": round(delta, 0),
                "delta_nii_pct": round(delta / base_nii * 100.0, 2),
            })

        return {
            "base_nii_usd": round(base_nii, 0),
            "one_year_repricing_gap_usd": round(gap_1yr, 0),
            "asset_sensitive": gap_1yr > 0,
            "shocks": shocks,
            "as_of": datetime.utcnow().isoformat(),
        }

    def eve_sensitivity(self) -> dict:
        """
        EVE sensitivity using duration-gap approximation.

        ΔEVE ≈ −Duration_gap × Δrate × Total_assets

        Duration_gap = Duration_assets − (Liabilities/Assets) × Duration_liabilities

        Fixed-rate asset duration ≈ 5.5yr (weighted avg of loans+securities)
        Floating asset duration ≈ 0.3yr
        Liability duration ≈ 2.5yr (mix of deposits + wholesale)

        SVB warning: if +200bps shock drops EVE by >15% of equity, flag it.
        """
        total_assets = sum(ASSETS.values())
        total_liabs = sum(LIABILITIES.values())

        # Weighted average asset duration
        dur_a = (
            ASSETS["loans_fixed"] * 4.5
            + ASSETS["loans_floating"] * 0.3
            + ASSETS["securities_fixed"] * 7.0
            + ASSETS["securities_floating"] * 0.5
            + ASSETS["cash_short"] * 0.04
            + ASSETS["trading_assets"] * 0.5
            + ASSETS["other"] * 0.0
        ) / total_assets

        # Weighted average liability duration
        dur_l = (
            LIABILITIES["demand_deposits"] * (0.3 * 0.30 + 5.0 * 0.70)   # behavioral
            + LIABILITIES["time_deposits"] * 2.5
            + LIABILITIES["wholesale_st"] * 0.5
            + LIABILITIES["wholesale_lt"] * 6.0
            + LIABILITIES["other"] * 0.0
        ) / total_liabs

        duration_gap = dur_a - (total_liabs / total_assets) * dur_l
        base_eve = total_assets - total_liabs   # ≈ equity book value

        shocks = []
        svb_warning = False
        for shock_bps in self.RATE_SHOCKS_BPS:
            delta = -duration_gap * (shock_bps / 10_000.0) * total_assets
            delta_pct_equity = delta / EQUITY_USD * 100.0
            if shock_bps == 200 and delta < -0.15 * EQUITY_USD:
                svb_warning = True
            shocks.append({
                "shock_bps": shock_bps,
                "delta_eve_usd": round(delta, 0),
                "delta_eve_pct_equity": round(delta_pct_equity, 2),
            })

        return {
            "base_eve_usd": round(base_eve, 0),
            "duration_gap_years": round(duration_gap, 3),
            "asset_duration_years": round(dur_a, 3),
            "liability_duration_years": round(dur_l, 3),
            "svb_warning": svb_warning,
            "svb_warning_detail": (
                "⚠ +200bps shock reduces EVE by >15% of equity — review fixed-rate securities position"
                if svb_warning else None
            ),
            "shocks": shocks,
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_full_alm_report(self) -> dict:
        nii = self.nii_sensitivity()
        eve = self.eve_sensitivity()
        gap = [p.to_dict() for p in self.get_repricing_gap_schedule()]
        ba = BehavioralAssumptions()

        nmd_analysis: dict = {}
        try:
            from infrastructure.treasury.nmd_model import nmd_model as _nmd
            nmd_analysis = _nmd.get_full_report()
        except Exception:
            pass

        return {
            "nii_sensitivity": nii,
            "eve_sensitivity": eve,
            "repricing_gap_schedule": gap,
            "behavioral_assumptions": {
                "core_deposit_pct": round(ba.CORE_PCT * 100, 1),
                "non_core_deposit_pct": round(ba.NON_CORE_PCT * 100, 1),
                "core_deposit_assumed_tenor_years": 5.0,
                "mortgage_prepayment_cpr": 8.0,
                "source": "NMDModel (segment-level behavioral model)",
            },
            "nmd_analysis": nmd_analysis,
            "as_of": datetime.utcnow().isoformat(),
        }


alm_engine = ALMEngine()
