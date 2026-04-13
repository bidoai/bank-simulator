"""
Limit Manager — Real-time risk limit monitoring and breach detection.

Stores the bank's official limit framework, tracks current utilization
against each limit, fires breach events at configurable thresholds.

Limits mirror the Market Risk Officer's mandate:
- VaR limits by desk and firm-wide
- Sensitivity limits (DV01, equity delta, vega)
- Concentration limits (single-name, country)
- Stress test limits
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import structlog

from config.settings import LIMIT_YELLOW_PCT, LIMIT_ORANGE_PCT, LIMIT_RED_PCT, LIMIT_BREACH_PCT

log = structlog.get_logger(__name__)


class LimitStatus(str, Enum):
    GREEN  = "GREEN"   # < 80% utilisation
    YELLOW = "YELLOW"  # 80-89% — notify desk head
    ORANGE = "ORANGE"  # 90-99% — notify desk head + Head of Trading
    RED    = "RED"     # ≥ 100% — escalate to CRO, suspend trading
    BREACH = "BREACH"  # > 120% — notify CEO and Board Risk Committee


@dataclass
class Limit:
    name: str
    description: str
    hard_limit: float          # the actual limit value (in native units)
    unit: str                  # e.g. "USD", "bp", "%"
    desk: str                  # "FIRM" or specific desk name
    current_value: float = 0.0
    breach_callbacks: list[Callable] = field(default_factory=list)

    @property
    def utilisation_pct(self) -> float:
        if self.hard_limit == 0:
            return 0.0
        return abs(self.current_value) / self.hard_limit * 100.0

    @property
    def status(self) -> LimitStatus:
        u = self.utilisation_pct
        if u >= LIMIT_BREACH_PCT:
            return LimitStatus.BREACH
        elif u >= LIMIT_RED_PCT:
            return LimitStatus.RED
        elif u >= LIMIT_ORANGE_PCT:
            return LimitStatus.ORANGE
        elif u >= LIMIT_YELLOW_PCT:
            return LimitStatus.YELLOW
        return LimitStatus.GREEN

    @property
    def headroom(self) -> float:
        """Remaining capacity before limit is hit."""
        return max(0.0, self.hard_limit - abs(self.current_value))

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "desk": self.desk,
            "current": self.current_value,
            "limit": self.hard_limit,
            "unit": self.unit,
            "utilisation_pct": round(self.utilisation_pct, 1),
            "status": self.status.value,
            "headroom": round(self.headroom, 2),
        }


# ──────────────────────────────────────────────────────────────────────────────
# Default limit framework — mirrors Market Risk Officer's mandate
# ──────────────────────────────────────────────────────────────────────────────

DEFAULT_LIMITS: list[dict] = [
    # ── VaR Limits (99%, 1-day) ────────────────────────────────────────────────
    dict(name="VAR_FIRM",        description="Firm-wide VaR (99%, 1-day)",
         hard_limit=450_000_000, unit="USD", desk="FIRM"),
    dict(name="VAR_EQUITY",      description="Equity desk VaR",
         hard_limit=85_000_000,  unit="USD", desk="APEX_EQ_MM"),
    dict(name="VAR_RATES",       description="Rates desk VaR",
         hard_limit=120_000_000, unit="USD", desk="APEX_RATES"),
    dict(name="VAR_FX",          description="FX desk VaR",
         hard_limit=55_000_000,  unit="USD", desk="APEX_FX"),
    dict(name="VAR_CREDIT",      description="Credit desk VaR",
         hard_limit=75_000_000,  unit="USD", desk="APEX_CREDIT"),
    dict(name="VAR_DERIV",       description="Derivatives desk VaR",
         hard_limit=95_000_000,  unit="USD", desk="APEX_DERIV"),

    # ── Sensitivity Limits ─────────────────────────────────────────────────────
    dict(name="DV01_FIRM",       description="Firm DV01 (per basis point)",
         hard_limit=25_000_000,  unit="USD/bp", desk="FIRM"),
    dict(name="EQUITY_DELTA",    description="Net equity delta (long or short)",
         hard_limit=2_000_000_000, unit="USD", desk="APEX_EQ_MM"),
    dict(name="VEGA_FIRM",       description="Firm vega (per 1% vol move)",
         hard_limit=15_000_000,  unit="USD/%vol", desk="APEX_DERIV"),

    # ── Concentration Limits ───────────────────────────────────────────────────
    dict(name="SINGLE_NAME_EQ_PCT", description="Single-name equity as % of book",
         hard_limit=20.0,        unit="%", desk="APEX_EQ_MM"),
    dict(name="SINGLE_NAME_EQ_NOTIONAL", description="Single-name equity notional",
         hard_limit=500_000_000, unit="USD", desk="APEX_EQ_MM"),
    dict(name="SINGLE_ISSUER_CS01",      description="Single-issuer credit CS01",
         hard_limit=300_000_000, unit="USD/bp", desk="APEX_CREDIT"),
    dict(name="COUNTRY_FX",      description="Country FX net notional",
         hard_limit=800_000_000, unit="USD", desk="APEX_FX"),

    # ── Stress Test Limits ────────────────────────────────────────────────────
    dict(name="STRESS_GFC",      description="Max loss in GFC 2008 scenario",
         hard_limit=2_100_000_000, unit="USD", desk="FIRM"),
    dict(name="STRESS_COVID",    description="Max loss in COVID March 2020 scenario",
         hard_limit=1_800_000_000, unit="USD", desk="FIRM"),
    dict(name="STRESS_RATES_UP", description="Max loss in +200bp rates shock",
         hard_limit=1_400_000_000, unit="USD", desk="FIRM"),

    # ── SecFin / Securitized Notional Limits ─────────────────────────────────
    dict(name="NOTIONAL_SECFIN",       description="Securities Finance total booked notional",
         hard_limit=50_000_000_000,  unit="USD", desk="SECURITIES_FINANCE"),
    dict(name="NOTIONAL_SECURITIZED",  description="Securitized Products total booked notional",
         hard_limit=10_000_000_000,  unit="USD", desk="SECURITIZED"),
]


class LimitManager:
    """
    Central limit registry and monitoring engine.

    Usage:
        lm = LimitManager()
        lm.update("VAR_EQUITY", 72_000_000)   # update current value
        status = lm.check("VAR_EQUITY")        # returns LimitStatus
        report = lm.get_report()               # full dashboard data
    """

    def __init__(self, limits: Optional[list[dict]] = None):
        self._limits: dict[str, Limit] = {}
        raw = limits if limits is not None else DEFAULT_LIMITS
        for cfg in raw:
            cfg = dict(cfg)
            name = cfg.pop("name")
            self._limits[name] = Limit(name=name, **cfg)

    # ── Write ──────────────────────────────────────────────────────────────────

    def update(self, limit_name: str, value: float) -> LimitStatus:
        """
        Update the current value for a limit and return its new status.
        Fires any registered callbacks if status changed.
        """
        lim = self._limits.get(limit_name)
        if lim is None:
            raise KeyError(f"Unknown limit: {limit_name}")

        prev_status = lim.status
        lim.current_value = value
        new_status = lim.status

        if new_status != prev_status:
            log.info(
                "limit.status_change",
                limit=limit_name,
                desk=lim.desk,
                utilisation=lim.utilisation_pct,
                prev=prev_status.value,
                new=new_status.value,
            )
            for cb in lim.breach_callbacks:
                try:
                    cb(lim, prev_status, new_status)
                except Exception as exc:
                    log.error("limit.callback_error", limit=limit_name, error=str(exc))

        return new_status

    def register_callback(self, limit_name: str, callback: Callable) -> None:
        """Register a function to be called on status changes for a limit."""
        self._limits[limit_name].breach_callbacks.append(callback)

    # ── Read ───────────────────────────────────────────────────────────────────

    def check(self, limit_name: str) -> LimitStatus:
        return self._limits[limit_name].status

    def get_limit(self, limit_name: str) -> Limit:
        return self._limits[limit_name]

    def get_breaches(self) -> list[Limit]:
        """Return all limits currently at RED or BREACH status."""
        return [l for l in self._limits.values()
                if l.status in (LimitStatus.RED, LimitStatus.BREACH)]

    def get_warnings(self) -> list[Limit]:
        """Return all limits currently at YELLOW or ORANGE status."""
        return [l for l in self._limits.values()
                if l.status in (LimitStatus.YELLOW, LimitStatus.ORANGE)]

    def get_report(self, desk: Optional[str] = None) -> list[dict]:
        """
        Full limit report as list of dicts, optionally filtered by desk.
        Sorted by utilisation descending.
        """
        limits = self._limits.values()
        if desk:
            limits = [l for l in limits if l.desk == desk or l.desk == "FIRM"]
        return sorted(
            [l.to_dict() for l in limits],
            key=lambda x: x["utilisation_pct"],
            reverse=True,
        )

    def get_summary(self) -> dict:
        """Top-level health summary for dashboard headers."""
        all_limits = list(self._limits.values())
        return {
            "total": len(all_limits),
            "green":  sum(1 for l in all_limits if l.status == LimitStatus.GREEN),
            "yellow": sum(1 for l in all_limits if l.status == LimitStatus.YELLOW),
            "orange": sum(1 for l in all_limits if l.status == LimitStatus.ORANGE),
            "red":    sum(1 for l in all_limits if l.status == LimitStatus.RED),
            "breach": sum(1 for l in all_limits if l.status == LimitStatus.BREACH),
            "breaches": [l.name for l in self.get_breaches()],
            "warnings": [l.name for l in self.get_warnings()],
        }
