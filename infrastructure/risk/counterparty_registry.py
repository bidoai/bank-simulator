"""
Counterparty Registry — formalised counterparty credit data and PFE limit monitoring.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import structlog

log = structlog.get_logger(__name__)


# Credit spread by rating band (fraction, e.g. 0.010 = 100bps)
_RATING_SPREAD: dict[str, float] = {
    "AAA": 0.005, "AA+": 0.005, "AA": 0.005, "AA-": 0.005,
    "A+":  0.010, "A":   0.010, "A-": 0.010,
    "BBB+": 0.020, "BBB": 0.020, "BBB-": 0.020,
    "BB+": 0.035, "BB":  0.035, "BB-": 0.035,
}
_SPREAD_DEFAULT = 0.020


@dataclass
class Counterparty:
    id: str
    name: str
    rating: str
    rating_numeric: int
    isda_master: bool
    csa_threshold: float
    mta: float
    pfe_limit: float
    credit_spread: float = 0.015   # annual hazard proxy (fraction)
    current_pfe: float = 0.0
    current_ead: float = 0.0

    @property
    def pfe_utilization_pct(self) -> float:
        if self.pfe_limit == 0:
            return 0.0
        return self.current_pfe / self.pfe_limit * 100.0

    @property
    def limit_status(self) -> str:
        u = self.pfe_utilization_pct
        if u >= 120:
            return "BREACH"
        elif u >= 100:
            return "RED"
        elif u >= 90:
            return "ORANGE"
        elif u >= 80:
            return "YELLOW"
        return "GREEN"

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "rating": self.rating,
            "rating_numeric": self.rating_numeric,
            "isda_master": self.isda_master,
            "csa_threshold": self.csa_threshold,
            "mta": self.mta,
            "pfe_limit": self.pfe_limit,
            "credit_spread": self.credit_spread,
            "credit_spread_bps": round(self.credit_spread * 10_000, 1),
            "current_pfe": self.current_pfe,
            "current_ead": self.current_ead,
            "pfe_utilization_pct": round(self.pfe_utilization_pct, 2),
            "limit_status": self.limit_status,
        }


_DEFAULT_COUNTERPARTIES: list[Counterparty] = [
    Counterparty(
        id="Goldman_Sachs",
        name="Goldman Sachs",
        rating="A+",
        rating_numeric=3,
        isda_master=True,
        csa_threshold=0,
        mta=10_000,
        pfe_limit=2_000_000_000,
        credit_spread=_RATING_SPREAD["A+"],
        current_ead=8_400_000,
        current_pfe=7_200_000,
    ),
    Counterparty(
        id="JPMorgan_Chase",
        name="JPMorgan Chase",
        rating="A+",
        rating_numeric=3,
        isda_master=True,
        csa_threshold=50_000,
        mta=25_000,
        pfe_limit=2_000_000_000,
        credit_spread=_RATING_SPREAD["A+"],
        current_ead=11_200_000,
        current_pfe=10_080_000,
    ),
    Counterparty(
        id="Deutsche_Bank",
        name="Deutsche Bank",
        rating="BBB+",
        rating_numeric=6,
        isda_master=True,
        csa_threshold=100_000,
        mta=50_000,
        pfe_limit=800_000_000,
        credit_spread=_RATING_SPREAD["BBB+"],
        current_ead=7_100_000,
        current_pfe=5_992_000,
    ),
    Counterparty(
        id="BNP_Paribas",
        name="BNP Paribas",
        rating="A",
        rating_numeric=4,
        isda_master=True,
        csa_threshold=0,
        mta=20_000,
        pfe_limit=2_000_000_000,
        credit_spread=_RATING_SPREAD["A"],
        current_ead=5_300_000,
        current_pfe=3_780_000,
    ),
    Counterparty(
        id="HSBC",
        name="HSBC",
        rating="A+",
        rating_numeric=3,
        isda_master=True,
        csa_threshold=0,
        mta=15_000,
        pfe_limit=2_000_000_000,
        credit_spread=_RATING_SPREAD["A+"],
        current_ead=6_000_000,
        current_pfe=4_500_000,
    ),
]


class CounterpartyRegistry:
    def __init__(self):
        self._counterparties: dict[str, Counterparty] = {
            cp.id: cp for cp in _DEFAULT_COUNTERPARTIES
        }

    def get(self, id: str) -> Counterparty | None:
        return self._counterparties.get(id)

    def get_all(self) -> list[Counterparty]:
        return list(self._counterparties.values())

    def get_report(self) -> list[dict]:
        return sorted(
            [cp.to_dict() for cp in self._counterparties.values()],
            key=lambda x: x["pfe_utilization_pct"],
            reverse=True,
        )

    def get_summary(self) -> dict:
        all_cp = list(self._counterparties.values())
        breaches = [cp.id for cp in all_cp if cp.limit_status in ("RED", "BREACH")]
        warnings = [cp.id for cp in all_cp if cp.limit_status in ("YELLOW", "ORANGE")]
        return {
            "total":  len(all_cp),
            "green":  sum(1 for cp in all_cp if cp.limit_status == "GREEN"),
            "yellow": sum(1 for cp in all_cp if cp.limit_status == "YELLOW"),
            "orange": sum(1 for cp in all_cp if cp.limit_status == "ORANGE"),
            "red":    sum(1 for cp in all_cp if cp.limit_status == "RED"),
            "breach": sum(1 for cp in all_cp if cp.limit_status == "BREACH"),
            "warnings": warnings,
            "breaches": breaches,
        }

    def update_exposure(self, id: str, pfe: float, ead: float) -> None:
        cp = self._counterparties.get(id)
        if cp is None:
            raise KeyError(f"Unknown counterparty: {id}")
        cp.current_pfe = pfe
        cp.current_ead = ead
        log.info("counterparty.exposure_updated", id=id, pfe=pfe, ead=ead, status=cp.limit_status)


counterparty_registry = CounterpartyRegistry()
