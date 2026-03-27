from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class SecFinBook:
    name: str
    business: str
    secured_funding_usd: float
    matched_book_spread_bps: float
    avg_tenor_days: int
    utilization_pct: float
    margin_excess_usd: float
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InventoryLine:
    asset: str
    asset_class: str
    long_inventory_usd: float
    lendable_pct: float
    haircut_pct: float
    internal_funding_rate_pct: float
    specials_bps: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ClientFinancingLine:
    client: str
    segment: str
    gross_exposure_usd: float
    net_exposure_usd: float
    margin_utilization_pct: float
    stock_borrow_demand: str
    financing_spread_bps: float
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


class SecuritiesFinanceService:
    def __init__(self) -> None:
        self._books = [
            SecFinBook("Matched Repo", "Treasury-backed secured funding", 18_600_000_000, 18.4, 21, 71.0, 245_000_000, "GREEN"),
            SecFinBook("Equity Finance", "Stock loan and client short financing", 9_450_000_000, 42.0, 9, 83.0, 118_000_000, "YELLOW"),
            SecFinBook("Prime Brokerage", "Hedge fund leverage and synthetic financing", 12_100_000_000, 56.0, 14, 79.0, 162_000_000, "YELLOW"),
            SecFinBook("Collateral Upgrade", "Transformation and optimization trades", 4_250_000_000, 23.0, 31, 64.0, 91_000_000, "GREEN"),
        ]
        self._inventory = [
            InventoryLine("UST 2Y/5Y/10Y", "Government Bonds", 8_400_000_000, 0.96, 1.0, 4.88, -3.0),
            InventoryLine("SPX Single Names", "Equities", 3_850_000_000, 0.74, 8.0, 5.25, 46.0),
            InventoryLine("HY Credit ETF Basket", "Credit", 1_320_000_000, 0.62, 12.0, 5.48, 18.0),
            InventoryLine("Agency MBS Collateral", "Securitized", 2_650_000_000, 0.81, 4.0, 5.05, 9.0),
        ]
        self._clients = [
            ClientFinancingLine("Aster Capital", "Multi-Strategy HF", 3_200_000_000, 1_140_000_000, 67.0, "HIGH", 95.0, "GREEN"),
            ClientFinancingLine("Northlight Partners", "Equity L/S HF", 2_450_000_000, 890_000_000, 84.0, "VERY_HIGH", 118.0, "YELLOW"),
            ClientFinancingLine("Meridian Macro", "Global Macro HF", 1_980_000_000, 720_000_000, 61.0, "MEDIUM", 88.0, "GREEN"),
            ClientFinancingLine("Atlas Event Driven", "Event-Driven HF", 1_720_000_000, 760_000_000, 91.0, "HIGH", 126.0, "RED"),
        ]

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_books(self) -> list[dict]:
        return [b.to_dict() for b in self._books]

    def get_inventory(self) -> list[dict]:
        return [i.to_dict() for i in self._inventory]

    def get_client_financing(self) -> list[dict]:
        return [c.to_dict() for c in self._clients]

    def get_overview(self) -> dict:
        total_secured = sum(b.secured_funding_usd for b in self._books)
        weighted_spread = sum(b.secured_funding_usd * b.matched_book_spread_bps for b in self._books) / total_secured
        warnings = [b for b in self._books if b.status != "GREEN"]
        client_red = [c for c in self._clients if c.status == "RED"]
        specials = sorted(self._inventory, key=lambda i: i.specials_bps, reverse=True)
        return {
            "total_secured_funding_usd": round(total_secured, 2),
            "blended_matched_book_spread_bps": round(weighted_spread, 2),
            "avg_utilization_pct": round(sum(b.utilization_pct for b in self._books) / len(self._books), 1),
            "warning_count": len(warnings),
            "red_client_count": len(client_red),
            "top_special": specials[0].asset if specials else "—",
            "watchlist": [
                {"label": "Funding concentration", "value": "Prime Brokerage + Equity Finance", "detail": "Short-tenor client financing is driving most balance-sheet consumption.", "status": "YELLOW"},
                {"label": "Margin stress", "value": "$162.0M buffer", "detail": "Prime financing margin excess remains healthy but should be watched against vol spikes.", "status": "GREEN"},
                {"label": "Client escalation", "value": "Atlas Event Driven", "detail": "Highest utilization and financing spread; candidate for tighter terms or lower limits.", "status": "RED"},
            ],
            "as_of": self._now(),
        }

    def run_stress(self) -> dict:
        base_secured = sum(b.secured_funding_usd for b in self._books)
        margin_excess = sum(b.margin_excess_usd for b in self._books)
        return {
            "scenario": "Equity short squeeze + repo haircut widening",
            "secured_funding_outflow_usd": round(base_secured * 0.041, 2),
            "additional_margin_required_usd": round(margin_excess * 0.36, 2),
            "specials_revenue_uplift_usd": 24_500_000,
            "net_liquidity_impact_usd": round(base_secured * 0.041 - 24_500_000, 2),
            "weakest_books": [
                {"book": "Equity Finance", "utilization_pct": 92.0, "status": "RED"},
                {"book": "Prime Brokerage", "utilization_pct": 88.0, "status": "YELLOW"},
            ],
            "as_of": self._now(),
        }


securities_finance_service = SecuritiesFinanceService()
