"""
Concentration Risk Monitor — single-name, sector, and geography exposure limits.
"""

from __future__ import annotations

import structlog

log = structlog.get_logger(__name__)


class ConcentrationRiskMonitor:
    """
    Monitors concentration risk across the portfolio.
    Flags when single-name, sector, or geographic exposure exceeds limits.
    """

    SINGLE_NAME_LIMIT_PCT = 0.05   # 5% max single name
    SECTOR_LIMIT_PCT = 0.25        # 25% max single sector
    GEOGRAPHY_LIMIT_PCT = 0.40     # 40% max single geography

    SECTOR_MAP: dict[str, str] = {
        "AAPL":   "Technology",
        "MSFT":   "Technology",
        "GOOGL":  "Technology",
        "NVDA":   "Technology",
        "US10Y":  "Government",
        "US2Y":   "Government",
        "EURUSD": "FX",
        "GBPUSD": "FX",
        "IG_CDX": "Credit",
        "HYEM_ETF": "Credit",
        "IRS_USD_10Y": "Rates",
        "SPX_CALL_5200": "Derivatives",
    }

    GEOGRAPHY_MAP: dict[str, str] = {
        "AAPL":   "US",
        "MSFT":   "US",
        "GOOGL":  "US",
        "NVDA":   "US",
        "US10Y":  "US",
        "US2Y":   "US",
        "EURUSD": "Europe",
        "GBPUSD": "UK",
        "IG_CDX": "US",
        "HYEM_ETF": "EM",
        "IRS_USD_10Y": "US",
        "SPX_CALL_5200": "US",
    }

    def _notional(self, pos: dict) -> float:
        if "notional" in pos:
            return abs(float(pos["notional"]))
        qty = float(pos.get("quantity", pos.get("qty", 0)))
        price = float(pos.get("avg_cost", pos.get("price", 1.0)))
        return abs(qty * price)

    def analyze(self, positions: list[dict]) -> dict:
        if not positions:
            return {
                "total_notional": 0.0,
                "single_name": [],
                "sector": [],
                "geography": [],
                "breach_count": 0,
                "top_3_names": [],
            }

        # Build notional maps
        name_notional: dict[str, float] = {}
        sector_notional: dict[str, float] = {}
        geo_notional: dict[str, float] = {}

        for pos in positions:
            ticker = str(pos.get("instrument", pos.get("ticker", "UNKNOWN")))
            notional = self._notional(pos)
            name_notional[ticker] = name_notional.get(ticker, 0.0) + notional
            sector = self.SECTOR_MAP.get(ticker, "Other")
            geo = self.GEOGRAPHY_MAP.get(ticker, "Other")
            sector_notional[sector] = sector_notional.get(sector, 0.0) + notional
            geo_notional[geo] = geo_notional.get(geo, 0.0) + notional

        total = sum(name_notional.values()) or 1.0

        def make_rows(mapping: dict[str, float], limit_pct: float, key: str) -> list[dict]:
            rows = []
            for name, amount in sorted(mapping.items(), key=lambda kv: -kv[1]):
                pct = amount / total
                rows.append({
                    key: name,
                    "notional": round(amount, 2),
                    "pct": round(pct, 6),
                    "breach": pct > limit_pct,
                })
            return rows

        single_rows = make_rows(name_notional, self.SINGLE_NAME_LIMIT_PCT, "ticker")
        sector_rows = make_rows(sector_notional, self.SECTOR_LIMIT_PCT, "sector")
        geo_rows = make_rows(geo_notional, self.GEOGRAPHY_LIMIT_PCT, "geography")

        breach_count = (
            sum(1 for r in single_rows if r["breach"])
            + sum(1 for r in sector_rows if r["breach"])
            + sum(1 for r in geo_rows if r["breach"])
        )
        top_3_names = [r["ticker"] for r in single_rows[:3]]

        log.info(
            "concentration_risk.analyzed",
            total_notional=round(total, 2),
            breach_count=breach_count,
        )

        return {
            "total_notional": round(total, 2),
            "single_name": single_rows,
            "sector": sector_rows,
            "geography": geo_rows,
            "breach_count": breach_count,
            "top_3_names": top_3_names,
        }

    def get_herfindahl_index(self, positions: list[dict]) -> float:
        if not positions:
            return 0.0
        name_notional: dict[str, float] = {}
        for pos in positions:
            ticker = str(pos.get("instrument", pos.get("ticker", "UNKNOWN")))
            name_notional[ticker] = name_notional.get(ticker, 0.0) + self._notional(pos)
        total = sum(name_notional.values()) or 1.0
        return float(sum((v / total) ** 2 for v in name_notional.values()))


concentration_monitor = ConcentrationRiskMonitor()
