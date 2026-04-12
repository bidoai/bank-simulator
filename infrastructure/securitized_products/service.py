from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone

import structlog

log = structlog.get_logger(__name__)

# Agency MBS positions: (name, face_usd, market_price, gross_coupon, wam_months, psa_speed, seasoning)
_AGENCY_MBS_POSITIONS = [
    ("FNMA 5.5 TBA",           4_200_000_000, 0.9800, 0.055, 348, 1.0,  3),
    ("Specified Pool LLB 5.0", 1_180_000_000, 0.9881, 0.050, 312, 0.80, 18),
]


@dataclass(frozen=True)
class StructuredPosition:
    name: str
    sector: str
    notional_usd: float
    market_value_usd: float
    oas_bps: float
    effective_duration: float
    convexity: float
    funding_cost_bps: float
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


class SecuritizedProductsService:
    def __init__(self) -> None:
        self._positions = [
            StructuredPosition("FNMA 5.5 TBA", "Agency MBS", 4_200_000_000, 4_116_000_000, 71.0, 4.1, -0.85, 26.0, "GREEN"),
            StructuredPosition("Specified Pool LLB 5.0", "Agency MBS", 1_180_000_000, 1_166_000_000, 58.0, 3.4, -0.62, 24.0, "GREEN"),
            StructuredPosition("Prime Auto ABS AAA", "ABS", 860_000_000, 851_000_000, 102.0, 1.9, 0.08, 34.0, "GREEN"),
            StructuredPosition("Conduit CMBS AA", "CMBS", 640_000_000, 603_000_000, 214.0, 4.8, -0.15, 61.0, "YELLOW"),
            StructuredPosition("CLO AAA Senior", "CLO", 920_000_000, 897_000_000, 167.0, 5.2, 0.11, 74.0, "YELLOW"),
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_inventory(self) -> list[dict]:
        return [p.to_dict() for p in self._positions]

    def get_sector_mix(self) -> list[dict]:
        sector_totals: dict[str, float] = {}
        total = sum(p.market_value_usd for p in self._positions)
        for p in self._positions:
            sector_totals[p.sector] = sector_totals.get(p.sector, 0.0) + p.market_value_usd
        return [
            {"sector": sector, "market_value_usd": round(mv, 2), "weight_pct": round((mv / total * 100.0) if total else 0.0, 1)}
            for sector, mv in sorted(sector_totals.items(), key=lambda item: item[1], reverse=True)
        ]

    def get_overview(self) -> dict:
        total_notional = sum(p.notional_usd for p in self._positions)
        total_mv = sum(p.market_value_usd for p in self._positions)
        weighted_oas = sum(p.market_value_usd * p.oas_bps for p in self._positions) / total_mv
        weighted_duration = sum(p.market_value_usd * p.effective_duration for p in self._positions) / total_mv
        warnings = [p for p in self._positions if p.status != "GREEN"]
        return {
            "total_notional_usd": round(total_notional, 2),
            "market_value_usd": round(total_mv, 2),
            "weighted_oas_bps": round(weighted_oas, 1),
            "weighted_duration": round(weighted_duration, 2),
            "warning_count": len(warnings),
            "sector_mix": self.get_sector_mix(),
            "watchlist": [
                {"label": "Negative convexity core", "value": "Agency 5.5 TBA", "detail": "Largest optionality bucket; primary driver of extension/contraction hedging.", "status": "YELLOW"},
                {"label": "Credit spread pressure", "value": "CMBS + CLO", "detail": "Spread product sleeve carries most OAS and funding drag.", "status": "YELLOW"},
                {"label": "Carry anchor", "value": "Auto ABS AAA", "detail": "Shorter-duration carry sleeve stabilizes funding-adjusted return profile.", "status": "GREEN"},
            ],
            "as_of": self._now(),
        }

    def get_relative_value(self) -> dict:
        cheapest = sorted(self._positions, key=lambda p: p.oas_bps - p.funding_cost_bps, reverse=True)
        richest = sorted(self._positions, key=lambda p: p.oas_bps - p.funding_cost_bps)
        return {
            "screen": [
                {
                    "name": p.name,
                    "sector": p.sector,
                    "net_carry_bps": round(p.oas_bps - p.funding_cost_bps, 1),
                    "oas_bps": p.oas_bps,
                    "funding_cost_bps": p.funding_cost_bps,
                    "duration": p.effective_duration,
                    "convexity": p.convexity,
                    "status": p.status,
                }
                for p in self._positions
            ],
            "cheapest_risk_adjusted": cheapest[0].name if cheapest else "—",
            "richest_risk_adjusted": richest[0].name if richest else "—",
            "as_of": self._now(),
        }

    def run_stress(self) -> dict:
        return {
            "scenario": "Rates +75bp, mortgage vol +20%, credit OAS +35bp",
            "pnl_delta_usd": -143_500_000,
            "duration_shift": 0.73,
            "convexity_drag_usd": -58_000_000,
            "credit_spread_drag_usd": -41_000_000,
            "funding_drag_usd": -12_500_000,
            "largest_contributors": [
                {"name": "FNMA 5.5 TBA", "pnl_delta_usd": -67_200_000, "driver": "extension risk"},
                {"name": "Conduit CMBS AA", "pnl_delta_usd": -29_400_000, "driver": "credit widening"},
                {"name": "CLO AAA Senior", "pnl_delta_usd": -24_600_000, "driver": "funding + spread"},
            ],
            "as_of": self._now(),
        }

    def get_pipeline(self) -> dict:
        return {
            "priority_builds": [
                {"name": "Agency MBS OAS engine", "status": "LIVE", "detail": "PSA prepayment model, Ho-Lee rate paths (100 paths), OAS bisection solver, effective duration, convexity, 7-scenario analysis."},
                {"name": "Specified pool collateral analytics", "status": "NEXT", "detail": "Loan-balance, geography, and burnout segmentation on top of TBA analytics."},
                {"name": "Non-agency waterfall engine", "status": "LATER", "detail": "Loss timing, tranche allocation, and structural trigger framework."},
            ],
            "as_of": self._now(),
        }

    def get_mbs_analytics(self, r0: float | None = None) -> list[dict]:
        """
        Run live MBS analytics (OAS, effective duration, convexity, scenario analysis)
        for the agency MBS positions using the PSA prepayment model and Ho-Lee paths.

        r0: short rate (annual, decimal). If None, fetches from the live FRED curve.
        """
        from infrastructure.securitized_products.mbs_analytics import analyze_mbs_position

        if r0 is None:
            try:
                from infrastructure.market_data.fred_curve import yield_cache
                r0 = yield_cache.get(2.0, yield_cache.get(1.0, 0.0425)) / 100.0
            except Exception:
                r0 = 0.0425  # fallback: ~4.25% short rate

        results = []
        for name, face, price, coupon, wam, psa, seasoning in _AGENCY_MBS_POSITIONS:
            try:
                analytics = analyze_mbs_position(name, face, price, coupon, wam, psa, r0, seasoning)
                results.append(analytics)
            except Exception as exc:
                log.warning("mbs_analytics.failed", name=name, error=str(exc))

        return results


securitized_products_service = SecuritizedProductsService()
