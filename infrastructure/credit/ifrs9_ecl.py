"""IFRS 9 Expected Credit Loss engine — Stage 1/2/3 provisioning."""
from __future__ import annotations

from datetime import datetime, timezone
from dataclasses import dataclass
from enum import Enum

import numpy as np
import structlog

log = structlog.get_logger(__name__)


class IFRSStage(Enum):
    STAGE_1 = 1
    STAGE_2 = 2
    STAGE_3 = 3


@dataclass
class Obligor:
    obligor_id: str
    name: str
    notional_usd: float
    pd_1yr: float
    lgd: float
    ead: float
    rating: str
    stage: IFRSStage
    maturity_years: float


class IFRS9ECLEngine:
    RATING_PD_MAP: dict[str, float] = {
        "AAA": 0.0001,
        "AA":  0.0003,
        "A":   0.0008,
        "BBB": 0.0020,
        "BB":  0.0110,
        "B":   0.0450,
        "CCC": 0.2600,
        "D":   1.0,
    }

    STAGE_2_PD_THRESHOLD = 0.02
    STAGE_2_PD_RELATIVE_CHANGE = 2.0

    def _pd_lifetime(self, pd_1yr: float, maturity_years: float) -> float:
        return 1.0 - (1.0 - pd_1yr) ** maturity_years

    def calculate_ecl(self, obligor: Obligor) -> dict:
        stage = obligor.stage
        pd_1yr = obligor.pd_1yr
        lgd = obligor.lgd
        ead = obligor.ead

        if stage == IFRSStage.STAGE_1:
            pd_used = pd_1yr
            horizon = "12-month"
            ecl_usd = pd_used * lgd * ead
        elif stage == IFRSStage.STAGE_2:
            pd_used = self._pd_lifetime(pd_1yr, obligor.maturity_years)
            horizon = "lifetime"
            ecl_usd = pd_used * lgd * ead
        else:
            pd_used = 1.0
            horizon = "lifetime"
            ecl_usd = lgd * ead

        ecl_pct = ecl_usd / obligor.notional_usd if obligor.notional_usd > 0 else 0.0

        return {
            "obligor_id": obligor.obligor_id,
            "stage": stage.name,
            "ecl_usd": round(ecl_usd, 2),
            "ecl_pct": round(ecl_pct, 6),
            "pd_used": round(pd_used, 6),
            "lgd": lgd,
            "ead": ead,
            "horizon": horizon,
        }

    def portfolio_ecl(self, obligors: list[Obligor]) -> dict:
        by_stage: dict[str, dict] = {
            "stage_1": {"count": 0, "notional": 0.0, "ecl": 0.0},
            "stage_2": {"count": 0, "notional": 0.0, "ecl": 0.0},
            "stage_3": {"count": 0, "notional": 0.0, "ecl": 0.0},
        }
        by_rating: dict[str, dict] = {}
        total_ecl = 0.0
        total_notional = 0.0

        for ob in obligors:
            result = self.calculate_ecl(ob)
            ecl = result["ecl_usd"]
            notional = ob.notional_usd
            stage_key = ob.stage.name.lower().replace(" ", "_")

            by_stage[stage_key]["count"] += 1
            by_stage[stage_key]["notional"] += notional
            by_stage[stage_key]["ecl"] += ecl

            rating = ob.rating
            if rating not in by_rating:
                by_rating[rating] = {"count": 0, "notional": 0.0, "ecl": 0.0}
            by_rating[rating]["count"] += 1
            by_rating[rating]["notional"] += notional
            by_rating[rating]["ecl"] += ecl

            total_ecl += ecl
            total_notional += notional

        coverage = total_ecl / total_notional if total_notional > 0 else 0.0

        # Round nested values
        for s in by_stage.values():
            s["notional"] = round(s["notional"], 2)
            s["ecl"] = round(s["ecl"], 2)
        for r in by_rating.values():
            r["notional"] = round(r["notional"], 2)
            r["ecl"] = round(r["ecl"], 2)

        log.info("ifrs9.portfolio_ecl_complete",
                 obligors=len(obligors),
                 total_ecl_usd=round(total_ecl, 2),
                 coverage_pct=round(coverage * 100, 3))

        return {
            "total_ecl_usd": round(total_ecl, 2),
            "total_notional_usd": round(total_notional, 2),
            "ecl_coverage_ratio": round(coverage, 6),
            "by_stage": by_stage,
            "by_rating": by_rating,
            "as_of": datetime.now(timezone.utc).isoformat(),
        }

    def generate_sample_portfolio(self, seed: int = 42) -> list[Obligor]:
        rng = np.random.default_rng(seed)

        # Rating distribution: AAA 3%, AA 10%, A 25%, BBB 40%, BB 15%, B 5%, CCC 2%
        # ~50 obligors, ~$50B total notional
        rating_specs = [
            ("AAA",  2,  [2.0, 3.5]),
            ("AA",   5,  [1.5, 2.5]),
            ("A",   12,  [0.8, 2.0]),
            ("BBB", 19,  [0.5, 1.8]),
            ("BB",   7,  [0.3, 1.2]),
            ("B",    3,  [0.2, 0.8]),
            ("CCC",  2,  [0.1, 0.5]),
        ]

        # Sector names for diversity
        sectors = [
            "Automotive", "Energy", "Technology", "Healthcare", "Retail",
            "Real Estate", "Utilities", "Industrials", "Financials", "Telecom",
        ]

        obligors: list[Obligor] = []
        idx = 0

        for rating, count, notional_range_bn in rating_specs:
            pd_base = self.RATING_PD_MAP[rating]
            for i in range(count):
                notional = float(rng.uniform(notional_range_bn[0], notional_range_bn[1]) * 1e9)
                lgd = float(rng.uniform(0.40, 0.65))
                ead = notional
                maturity = float(rng.uniform(1.0, 10.0))
                sector = sectors[idx % len(sectors)]

                # Add small random noise to PD (~±20%)
                pd_1yr = float(np.clip(pd_base * rng.uniform(0.8, 1.2), 0.0001, 0.999))

                # Stage assignment: Stage 3 ~3% of portfolio, Stage 2 ~15%, rest Stage 1
                roll = rng.random()
                if rating == "CCC" or roll < 0.03:
                    stage = IFRSStage.STAGE_3
                elif rating in ("B", "BB") and roll < 0.18:
                    stage = IFRSStage.STAGE_2
                elif pd_1yr >= self.STAGE_2_PD_THRESHOLD:
                    stage = IFRSStage.STAGE_2
                else:
                    stage = IFRSStage.STAGE_1

                obligors.append(Obligor(
                    obligor_id=f"OBL-{idx+1:04d}",
                    name=f"{sector} Corp {chr(65 + i)}",
                    notional_usd=round(notional, 2),
                    pd_1yr=round(pd_1yr, 6),
                    lgd=round(lgd, 4),
                    ead=round(ead, 2),
                    rating=rating,
                    stage=stage,
                    maturity_years=round(maturity, 2),
                ))
                idx += 1

        log.info("ifrs9.portfolio_generated", obligors=len(obligors))
        return obligors


ecl_engine = IFRS9ECLEngine()
_sample_portfolio: list[Obligor] = ecl_engine.generate_sample_portfolio()
