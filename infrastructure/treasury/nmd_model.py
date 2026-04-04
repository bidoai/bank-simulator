"""
Non-Maturity Deposit (NMD) Model.

Replaces the hardcoded 70/30 core/non-core split in the ALM engine with
a segment-level behavioral model that captures rate sensitivity, runoff
dynamics, and stable core fractions for each deposit category.

Segments: retail checking, retail savings, commercial operating, commercial non-operating.
"""
from __future__ import annotations

from datetime import datetime
from dataclasses import dataclass, asdict


@dataclass
class NMDSegment:
    name: str
    balance_usd: float
    beta: float
    decay_rate_monthly: float
    rate_shock_multiplier: float
    stable_core_pct: float
    core_duration_years: float

    def to_dict(self) -> dict:
        return asdict(self)


_SEGMENTS: list[NMDSegment] = [
    NMDSegment(
        name="retail_checking",
        balance_usd=450e9,
        beta=0.15,
        decay_rate_monthly=0.02,
        rate_shock_multiplier=0.005,
        stable_core_pct=0.80,
        core_duration_years=4.0,
    ),
    NMDSegment(
        name="retail_savings",
        balance_usd=380e9,
        beta=0.45,
        decay_rate_monthly=0.03,
        rate_shock_multiplier=0.010,
        stable_core_pct=0.65,
        core_duration_years=3.0,
    ),
    NMDSegment(
        name="commercial_operating",
        balance_usd=320e9,
        beta=0.30,
        decay_rate_monthly=0.025,
        rate_shock_multiplier=0.008,
        stable_core_pct=0.70,
        core_duration_years=3.5,
    ),
    NMDSegment(
        name="commercial_non_operating",
        balance_usd=250e9,
        beta=0.75,
        decay_rate_monthly=0.08,
        rate_shock_multiplier=0.030,
        stable_core_pct=0.20,
        core_duration_years=1.0,
    ),
]


class NMDModel:
    """
    Behavioral model for non-maturity deposits.

    Provides core/non-core splits with segment-level duration assignments,
    runoff projections under rate shock, and weighted average duration
    of the full NMD book.
    """

    def __init__(self) -> None:
        self.segments = {s.name: s for s in _SEGMENTS}

    @property
    def total_balance(self) -> float:
        return sum(s.balance_usd for s in self.segments.values())

    def get_core_duration_profile(self) -> dict[str, dict]:
        """
        Core amount and average duration per segment.

        Returns dict: segment_name → {core_amount, non_core_amount, core_pct, duration_years}
        """
        profile: dict[str, dict] = {}
        for name, seg in self.segments.items():
            core = seg.balance_usd * seg.stable_core_pct
            non_core = seg.balance_usd * (1.0 - seg.stable_core_pct)
            profile[name] = {
                "balance_usd": round(seg.balance_usd, 0),
                "core_amount_usd": round(core, 0),
                "non_core_amount_usd": round(non_core, 0),
                "core_pct": round(seg.stable_core_pct * 100.0, 1),
                "duration_years": seg.core_duration_years,
                "beta": seg.beta,
            }
        return profile

    def get_runoff_under_shock(self, rate_shock_bps: float) -> dict:
        """
        Project monthly deposit runoff under a given rate shock.

        Base runoff = balance × decay_rate_monthly
        Shock-driven additional runoff = balance × rate_shock_multiplier × (shock_bps / 100)

        Returns total runoff by segment and in aggregate.
        """
        by_segment: dict[str, dict] = {}
        total_base = 0.0
        total_shock_additional = 0.0

        for name, seg in self.segments.items():
            base = seg.balance_usd * seg.decay_rate_monthly
            shock_add = seg.balance_usd * seg.rate_shock_multiplier * (rate_shock_bps / 100.0)
            total_runoff = base + max(shock_add, 0.0)
            by_segment[name] = {
                "balance_usd": round(seg.balance_usd, 0),
                "base_runoff_usd": round(base, 0),
                "shock_additional_usd": round(max(shock_add, 0.0), 0),
                "total_monthly_runoff_usd": round(total_runoff, 0),
                "runoff_pct_of_balance": round(total_runoff / seg.balance_usd * 100.0, 2),
            }
            total_base += base
            total_shock_additional += max(shock_add, 0.0)

        total_balance = self.total_balance
        total_runoff = total_base + total_shock_additional
        return {
            "rate_shock_bps": rate_shock_bps,
            "by_segment": by_segment,
            "total_base_runoff_usd": round(total_base, 0),
            "total_shock_additional_usd": round(total_shock_additional, 0),
            "total_monthly_runoff_usd": round(total_runoff, 0),
            "total_runoff_pct": round(total_runoff / total_balance * 100.0, 2),
            "as_of": datetime.utcnow().isoformat(),
        }

    def get_effective_duration(self) -> float:
        """
        Weighted average duration of the entire NMD book (years).

        Only core balances carry the stated duration; non-core is treated as short-term (0.25yr).
        """
        total = 0.0
        weighted_dur = 0.0
        for seg in self.segments.values():
            core = seg.balance_usd * seg.stable_core_pct
            non_core = seg.balance_usd * (1.0 - seg.stable_core_pct)
            weighted_dur += core * seg.core_duration_years + non_core * 0.25
            total += seg.balance_usd
        return round(weighted_dur / total, 4) if total else 0.0

    def get_full_report(self) -> dict:
        profile = self.get_core_duration_profile()
        runoff_100 = self.get_runoff_under_shock(100)
        runoff_200 = self.get_runoff_under_shock(200)
        runoff_300 = self.get_runoff_under_shock(300)
        eff_dur = self.get_effective_duration()

        total_core = sum(
            seg.balance_usd * seg.stable_core_pct for seg in self.segments.values()
        )
        total_non_core = self.total_balance - total_core

        return {
            "total_nmd_balance_usd": round(self.total_balance, 0),
            "total_core_usd": round(total_core, 0),
            "total_non_core_usd": round(total_non_core, 0),
            "core_pct_of_total": round(total_core / self.total_balance * 100.0, 1),
            "effective_duration_years": eff_dur,
            "core_duration_profile": profile,
            "runoff_scenarios": {
                "shock_100bps": runoff_100,
                "shock_200bps": runoff_200,
                "shock_300bps": runoff_300,
            },
            "as_of": datetime.utcnow().isoformat(),
        }


nmd_model = NMDModel()
