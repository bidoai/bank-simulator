"""
Liquidity Ladder — maturity-bucketed funding gap analysis.

Cumulative gap = sum of net gaps from Overnight through each bucket.
"""
from __future__ import annotations

from typing import Any


_LADDER_DATA = [
    {"bucket": "Overnight", "days_max": 1,    "assets_bn": 85.0,   "liabilities_bn": -120.0},
    {"bucket": "1W",        "days_max": 7,    "assets_bn": 45.0,   "liabilities_bn": -65.0},
    {"bucket": "2W",        "days_max": 14,   "assets_bn": 30.0,   "liabilities_bn": -40.0},
    {"bucket": "1M",        "days_max": 30,   "assets_bn": 95.0,   "liabilities_bn": -110.0},
    {"bucket": "3M",        "days_max": 90,   "assets_bn": 180.0,  "liabilities_bn": -160.0},
    {"bucket": "6M",        "days_max": 180,  "assets_bn": 220.0,  "liabilities_bn": -190.0},
    {"bucket": "1Y",        "days_max": 365,  "assets_bn": 350.0,  "liabilities_bn": -280.0},
    {"bucket": "1-3Y",      "days_max": 1095, "assets_bn": 480.0,  "liabilities_bn": -420.0},
    {"bucket": "3Y+",       "days_max": 99999,"assets_bn": 1200.0, "liabilities_bn": -1000.0},
]

# Behavioral overlays: deposits are stickier than contractual; loans prepay
_BEHAVIORAL_ADJUSTMENTS = {
    "Overnight": {"assets_adj": 0.0,   "liabilities_adj": 35.0},   # 35% of ON deposits are sticky
    "1W":        {"assets_adj": 0.0,   "liabilities_adj": 12.0},
    "2W":        {"assets_adj": 0.0,   "liabilities_adj": 5.0},
    "1M":        {"assets_adj": -5.0,  "liabilities_adj": 8.0},    # prepayment offset
    "3M":        {"assets_adj": -8.0,  "liabilities_adj": 5.0},
    "6M":        {"assets_adj": -10.0, "liabilities_adj": 3.0},
    "1Y":        {"assets_adj": -12.0, "liabilities_adj": 0.0},
    "1-3Y":      {"assets_adj": -15.0, "liabilities_adj": 0.0},
    "3Y+":       {"assets_adj": -20.0, "liabilities_adj": 0.0},
}


class LiquidityLadder:
    def __init__(self) -> None:
        self._data = _LADDER_DATA
        self._behavioral = _BEHAVIORAL_ADJUSTMENTS

    def get_ladder(self) -> list[dict[str, Any]]:
        result = []
        cumulative_gap = 0.0
        for row in self._data:
            bucket = row["bucket"]
            beh = self._behavioral.get(bucket, {"assets_adj": 0.0, "liabilities_adj": 0.0})
            assets = row["assets_bn"] + beh["assets_adj"]
            liabilities = row["liabilities_bn"] + beh["liabilities_adj"]
            net = assets + liabilities  # liabilities are negative
            cumulative_gap += net
            result.append({
                "bucket": bucket,
                "assets_bn": round(assets, 2),
                "liabilities_bn": round(liabilities, 2),
                "net_bn": round(net, 2),
                "cumulative_gap_bn": round(cumulative_gap, 2),
                "is_surplus": net >= 0,
                "behavioral_assets_adj_bn": beh["assets_adj"],
                "behavioral_liabilities_adj_bn": beh["liabilities_adj"],
            })
        return result

    def get_survival_horizon(self) -> dict[str, Any]:
        """Return the bucket at which cumulative gap first turns positive (surplus onset)."""
        ladder = self.get_ladder()
        # The early buckets are net negative — find when cumulative gap first goes strictly positive
        for row in ladder:
            if row["cumulative_gap_bn"] > 0:
                return {
                    "first_surplus_bucket": row["bucket"],
                    "cumulative_gap_at_bucket_bn": row["cumulative_gap_bn"],
                    "survival_horizon_days": self._bucket_days(row["bucket"]),
                }
        last = ladder[-1]
        return {
            "first_surplus_bucket": None,
            "cumulative_gap_at_bucket_bn": last["cumulative_gap_bn"],
            "survival_horizon_days": None,
        }

    def get_funding_gap_at(self, bucket: str) -> dict[str, Any]:
        ladder = self.get_ladder()
        for row in ladder:
            if row["bucket"] == bucket:
                return row
        valid = [r["bucket"] for r in ladder]
        raise ValueError(f"Unknown bucket '{bucket}'. Valid: {valid}")

    def get_survival_horizon_days(self) -> int:
        """Return days until cumulative gap first goes positive (structural surplus onset)."""
        horizon = self.get_survival_horizon()
        days = horizon.get("survival_horizon_days")
        return days if days is not None else 9999

    def get_summary(self) -> dict[str, Any]:
        ladder = self.get_ladder()
        total_assets = sum(r["assets_bn"] for r in ladder)
        total_liabilities = sum(r["liabilities_bn"] for r in ladder)
        # Short-term gap = sum of nets for buckets up to and including 1M
        short_term_buckets = {"Overnight", "1W", "2W", "1M"}
        short_term_gap = sum(
            r["net_bn"] for r in ladder if r["bucket"] in short_term_buckets
        )
        return {
            "total_assets_bn": round(total_assets, 2),
            "total_liabilities_bn": round(total_liabilities, 2),
            "net_structural_bn": round(total_assets + total_liabilities, 2),
            "survival_horizon_days": self.get_survival_horizon_days(),
            "short_term_gap_bn": round(short_term_gap, 2),
        }

    @staticmethod
    def _bucket_days(bucket: str) -> int:
        mapping = {
            "Overnight": 1,
            "1W": 7,
            "2W": 14,
            "1M": 30,
            "3M": 90,
            "6M": 180,
            "1Y": 365,
            "1-3Y": 1095,
            "3Y+": 9999,
        }
        return mapping.get(bucket, 0)


liquidity_ladder = LiquidityLadder()
