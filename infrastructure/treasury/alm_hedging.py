"""
ALM Hedging Engine.

Computes key rate durations (KRD) across 10 rate points, duration gap,
hedge recommendations (receive-fixed IRS), and NII at Risk.

Key rate duration methodology:
  - Shock each of 10 key rates +1bp, all others flat
  - ΔEVE per bucket = -modified_duration × notional × 0.0001
  - KRD[i] = sum of asset ΔEVE minus liability ΔEVE at that key rate
  - DV01 is KRD expressed in dollar terms
"""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, asdict
from typing import Optional


# ── Key rate points ────────────────────────────────────────────────────────

KEY_RATES_YEARS = [0.25, 0.50, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]

KEY_RATE_LABELS = ["3M", "6M", "1Y", "2Y", "3Y", "5Y", "7Y", "10Y", "20Y", "30Y"]

# ── Apex Global Bank representative balance sheet ($B) ────────────────────

# For each balance sheet item: (notional_$B, modified_duration_years, primary_krd_bucket_index)
# Allocation weights across KRD buckets (indices 0-9).
# Weights sum to 1.0 per item.

BS_ITEMS = {
    # Assets
    "loans": {
        "notional": 800e9,
        "type": "asset",
        "krd_weights": {2: 0.30, 3: 0.35, 4: 0.20, 5: 0.15},   # 3Y, 5Y, 7Y, 10Y
    },
    "mortgages": {
        "notional": 400e9,
        "type": "asset",
        "krd_weights": {4: 0.20, 5: 0.40, 6: 0.25, 7: 0.15},   # 5Y prepay-adj, 7Y, 10Y, 20Y
    },
    "securities": {
        "notional": 420e9,
        "type": "asset",
        "krd_weights": {3: 0.25, 4: 0.30, 5: 0.30, 6: 0.15},   # 2Y-7Y range
    },
    # Liabilities — NMD book (from NMD model core profile)
    "deposits_nmd": {
        "notional": 1_400e9,
        "type": "liability",
        "krd_weights": {2: 0.30, 3: 0.35, 4: 0.25, 7: 0.10},   # 1Y-5Y range (behavioral)
    },
    "wholesale_funding": {
        "notional": 480e9,
        "type": "liability",
        "krd_weights": {0: 0.20, 1: 0.30, 2: 0.35, 3: 0.15},   # 0-2Y
    },
    "sub_debt": {
        "notional": 60e9,
        "type": "liability",
        "krd_weights": {5: 0.40, 6: 0.35, 7: 0.25},            # 7Y-10Y
    },
}

# Duration per KRD bucket (used to convert notional weights → effective duration)
# These are the effective durations at each key rate point (years)
KRD_BUCKET_DURATIONS = [0.25, 0.5, 1.0, 2.0, 3.0, 5.0, 7.0, 10.0, 20.0, 30.0]

# Aggregate asset/liability durations for duration gap calculation
ASSET_DURATION_YEARS = 4.8
LIABILITY_DURATION_YEARS = 2.6   # NMD model effective duration drives this

TOTAL_ASSETS = sum(
    v["notional"] for v in BS_ITEMS.values() if v["type"] == "asset"
)
TOTAL_LIABILITIES = sum(
    v["notional"] for v in BS_ITEMS.values() if v["type"] == "liability"
)
EQUITY_USD = 300e9

# NII at Risk parameters
NII_UNHEDGED_PER_100BPS = -450e6    # $-450M (rising rates hurt NII via deposit repricing)
NII_HEDGED_PER_100BPS = -180e6      # $-180M after swap hedging


@dataclass
class KRDPoint:
    key_rate: str
    tenor_years: float
    krd_years: float          # contribution to portfolio modified duration
    dv01_mm: float            # DV01 in $M per 1bp

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class HedgeRecommendation:
    instrument: str
    tenor: str
    notional_bn: float
    rationale: str
    priority: str             # HIGH / MEDIUM / LOW

    def to_dict(self) -> dict:
        return asdict(self)


def _build_krd_profile() -> list[KRDPoint]:
    """
    Compute KRD by shocking each key rate bucket +1bp.

    ΔEVE at bucket i ≈ Σ_item ( sign × notional × weight_i × bucket_dur_i × 0.0001 )
    KRD_i = ΔEVE_i / (total_assets × 0.0001) expressed as duration contribution
    """
    krd_points = []

    for i, (label, tenor) in enumerate(zip(KEY_RATE_LABELS, KEY_RATES_YEARS)):
        delta_eve = 0.0
        for item in BS_ITEMS.values():
            weight = item["krd_weights"].get(i, 0.0)
            if weight == 0.0:
                continue
            notional = item["notional"]
            dur = KRD_BUCKET_DURATIONS[i]
            sign = 1.0 if item["type"] == "asset" else -1.0
            # ΔEVE = -sign × notional × weight × dur × 0.0001
            delta_eve += -sign * notional * weight * dur * 0.0001

        # KRD expressed as duration contribution (years)
        krd_years = abs(delta_eve) / (TOTAL_ASSETS * 0.0001)
        dv01_mm = abs(delta_eve) / 1e6

        krd_points.append(KRDPoint(
            key_rate=label,
            tenor_years=tenor,
            krd_years=round(krd_years, 4),
            dv01_mm=round(dv01_mm, 2),
        ))

    return krd_points


class ALMHedgingEngine:
    """ALM hedging engine: KRD, duration gap, hedge recommendations, NII at Risk."""

    def get_key_rate_durations(self) -> list[dict]:
        return [p.to_dict() for p in _build_krd_profile()]

    def get_duration_gap(self) -> dict:
        """
        Duration gap analysis.

        equity_duration_gap = asset_dur - (liabilities/assets) × liability_dur
        Positive gap = assets are longer → exposed to rate rises (EVE falls).
        """
        from infrastructure.treasury.nmd_model import nmd_model
        nmd_dur = nmd_model.get_effective_duration()

        # Weighted avg liability duration (NMD drives deposit piece)
        nmd_total = 1_400e9
        wholesale_dur = 1.2
        sub_debt_dur = 7.5
        total_liabs = TOTAL_LIABILITIES

        liability_dur = (
            nmd_total * nmd_dur
            + 480e9 * wholesale_dur
            + 60e9 * sub_debt_dur
        ) / total_liabs

        equity_dur = ASSET_DURATION_YEARS - (total_liabs / TOTAL_ASSETS) * liability_dur

        return {
            "asset_duration_years": round(ASSET_DURATION_YEARS, 3),
            "liability_duration_years": round(liability_dur, 3),
            "nmd_effective_duration_years": round(nmd_dur, 3),
            "equity_duration_gap_years": round(equity_dur, 3),
            "duration_gap_raw": round(ASSET_DURATION_YEARS - liability_dur, 3),
            "is_asset_sensitive": ASSET_DURATION_YEARS > liability_dur,
            "total_assets_usd": round(TOTAL_ASSETS, 0),
            "total_liabilities_usd": round(total_liabs, 0),
            "equity_usd": round(EQUITY_USD, 0),
        }

    def get_hedge_recommendations(self) -> list[dict]:
        """
        Recommend receive-fixed IRS when duration gap exceeds 0.5 years.

        Hedge notional = EVE_sensitivity / DV01_of_swap
        Target: reduce gap to ≤0.25 years.
        """
        gap_info = self.get_duration_gap()
        equity_gap = gap_info["equity_duration_gap_years"]
        raw_gap = gap_info["duration_gap_raw"]
        recommendations: list[HedgeRecommendation] = []

        if raw_gap > 0.5:
            # 5Y receiver IRS: DV01 ≈ $4,500/bp per $10M notional → $0.045% per $
            # Hedge ratio: target reducing gap to 0.25yr
            gap_to_close = raw_gap - 0.25
            eve_sensitivity = TOTAL_ASSETS * gap_to_close * 0.0001   # per 1bp
            dv01_per_bn_5y = 4.5e6    # $M per bn notional for 5Y IRS
            notional_5y = eve_sensitivity / (dv01_per_bn_5y / 1e9) / 1e9

            recommendations.append(HedgeRecommendation(
                instrument="Receive-Fixed Interest Rate Swap",
                tenor="5Y",
                notional_bn=round(min(notional_5y, 200.0), 1),
                rationale=(
                    f"Duration gap {raw_gap:.2f}yr exceeds 0.5yr target. "
                    "Receive-fixed at 5Y to shorten asset duration and reduce EVE sensitivity."
                ),
                priority="HIGH",
            ))

            if raw_gap > 1.0:
                notional_10y = notional_5y * 0.40
                recommendations.append(HedgeRecommendation(
                    instrument="Receive-Fixed Interest Rate Swap",
                    tenor="10Y",
                    notional_bn=round(min(notional_10y, 100.0), 1),
                    rationale=(
                        "Additional 10Y receiver to hedge long-end securities duration. "
                        "Protects EVE against +200bps SVB-style scenario."
                    ),
                    priority="MEDIUM",
                ))

        # Always recommend interest rate cap to protect NII floor
        recommendations.append(HedgeRecommendation(
            instrument="Interest Rate Cap (SOFR)",
            tenor="2Y",
            notional_bn=50.0,
            rationale=(
                "Cap on SOFR at 6.50% to protect against further rate rises "
                "hurting NII via deposit repricing above cap strike."
            ),
            priority="LOW",
        ))

        return [r.to_dict() for r in recommendations]

    def get_nii_at_risk(self, rate_shock_bps: int = 100) -> dict:
        """
        NII impact under rate shock, before and after hedging.
        """
        scale = rate_shock_bps / 100.0
        unhedged = NII_UNHEDGED_PER_100BPS * scale
        hedged = NII_HEDGED_PER_100BPS * scale
        benefit = hedged - unhedged   # positive = hedging helps

        return {
            "rate_shock_bps": rate_shock_bps,
            "unhedged_nii_impact_usd": round(unhedged, 0),
            "hedged_nii_impact_usd": round(hedged, 0),
            "hedge_benefit_usd": round(benefit, 0),
            "hedge_benefit_pct": round(benefit / abs(unhedged) * 100.0, 1) if unhedged else 0.0,
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_full_report(self) -> dict:
        return {
            "key_rate_durations": self.get_key_rate_durations(),
            "duration_gap": self.get_duration_gap(),
            "hedge_recommendations": self.get_hedge_recommendations(),
            "nii_at_risk_100bps": self.get_nii_at_risk(100),
            "nii_at_risk_200bps": self.get_nii_at_risk(200),
            "as_of": datetime.utcnow().isoformat(),
        }


alm_hedging_engine = ALMHedgingEngine()
