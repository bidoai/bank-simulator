"""
Securities Finance Lifecycle Engine.

Event-driven repo/stock-borrow state computed from live market conditions:
  - Repo ladder: O/N, 1W, 1M, 3M rates derived from live FRED yield curve
  - Margin engine: collateral value changes trigger margin calls
  - Term repricing: repo terms repriced when rate moves exceed threshold

All monetary amounts in USD. Rates in decimal (0.045 = 4.5%).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Rate curve helpers
# ---------------------------------------------------------------------------

def _get_live_rates() -> dict[str, float]:
    """
    Pull the latest UST/SOFR rates from the cached FRED yield curve.
    Returns a dict of tenor label → annual rate (decimal).
    Falls back to hardcoded defaults on any failure.
    """
    defaults = {
        "overnight": 0.0430,
        "1w":        0.0432,
        "1m":        0.0435,
        "3m":        0.0440,
        "6m":        0.0445,
        "1y":        0.0450,
    }
    try:
        from infrastructure.market_data.fred_curve import yield_cache
        if not yield_cache:
            return defaults
        # Map tenor keys (years) to labels
        tenor_map = {0.003: "overnight", 0.083: "1m", 0.25: "3m", 0.50: "6m", 1.00: "1y"}
        live = {}
        for tenor_yr, label in tenor_map.items():
            # Find nearest tenor in cache
            closest = min(yield_cache.keys(), key=lambda k: abs(k - tenor_yr))
            if abs(closest - tenor_yr) < 0.2:
                live[label] = yield_cache[closest] / 100.0
        # Interpolate 1W: between O/N and 1M
        if "overnight" in live and "1m" in live:
            live["1w"] = live["overnight"] * 0.7 + live["1m"] * 0.3
        return {**defaults, **live}
    except Exception as exc:
        log.debug("secfin.lifecycle.rate_fallback", error=str(exc))
        return defaults


# ---------------------------------------------------------------------------
# Repo ladder
# ---------------------------------------------------------------------------

@dataclass
class RepoLeg:
    tenor: str           # "overnight", "1w", "1m", "3m"
    collateral: str      # collateral type
    notional_usd: float
    rate: float          # current annual rate (decimal)
    haircut: float       # fraction (0.02 = 2%)
    last_repriced_at: str

    @property
    def daily_interest_usd(self) -> float:
        return self.notional_usd * self.rate / 360.0

    @property
    def collateral_required_usd(self) -> float:
        return self.notional_usd / (1.0 - self.haircut)

    def to_dict(self) -> dict:
        return {
            "tenor": self.tenor,
            "collateral": self.collateral,
            "notional_usd": self.notional_usd,
            "rate_pct": round(self.rate * 100, 4),
            "haircut_pct": round(self.haircut * 100, 1),
            "daily_interest_usd": round(self.daily_interest_usd, 2),
            "collateral_required_usd": round(self.collateral_required_usd, 2),
            "last_repriced_at": self.last_repriced_at,
        }


class RepoLadder:
    """Tracks and manages the repo book across tenors."""

    def __init__(self) -> None:
        self._legs: list[RepoLeg] = []
        self._rates: dict[str, float] = {}
        self._refresh_rates()
        self._seed()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _refresh_rates(self) -> None:
        self._rates = _get_live_rates()

    def _seed(self) -> None:
        rates = self._rates
        seed_legs = [
            RepoLeg("overnight", "UST",         12_000_000_000, rates.get("overnight", 0.0430), 0.010, self._now()),
            RepoLeg("1w",        "Agency MBS",   4_500_000_000, rates.get("1w",        0.0432), 0.020, self._now()),
            RepoLeg("1m",        "Corp Bond IG", 2_800_000_000, rates.get("1m",        0.0435), 0.050, self._now()),
            RepoLeg("3m",        "Equity",       1_200_000_000, rates.get("3m",        0.0440), 0.080, self._now()),
        ]
        self._legs = seed_legs

    def reprice(self) -> list[dict]:
        """Reprice all legs against current FRED rates. Returns legs that changed > 2bps."""
        self._refresh_rates()
        repriced = []
        for leg in self._legs:
            new_rate = self._rates.get(leg.tenor, leg.rate)
            move_bps = abs(new_rate - leg.rate) * 10_000
            if move_bps > 2.0:
                old_rate = leg.rate
                leg.rate = new_rate
                leg.last_repriced_at = self._now()
                repriced.append({
                    "tenor": leg.tenor,
                    "old_rate_pct": round(old_rate * 100, 4),
                    "new_rate_pct": round(new_rate * 100, 4),
                    "move_bps": round(move_bps, 1),
                })
        return repriced

    def get_ladder(self) -> dict:
        total_notional = sum(l.notional_usd for l in self._legs)
        total_daily_interest = sum(l.daily_interest_usd for l in self._legs)
        weighted_rate = sum(l.notional_usd * l.rate for l in self._legs) / total_notional if total_notional > 0 else 0
        return {
            "legs": [l.to_dict() for l in self._legs],
            "summary": {
                "total_notional_usd": total_notional,
                "weighted_avg_rate_pct": round(weighted_rate * 100, 4),
                "total_daily_interest_usd": round(total_daily_interest, 2),
                "annual_funding_cost_usd": round(total_daily_interest * 360, 0),
            },
            "live_rates": {k: round(v * 100, 4) for k, v in self._rates.items()},
            "as_of": self._now(),
        }


# ---------------------------------------------------------------------------
# Margin engine
# ---------------------------------------------------------------------------

@dataclass
class MarginAccount:
    counterparty: str
    collateral_asset: str
    face_value_usd: float
    current_price: float       # fraction of par
    initial_margin_usd: float  # IM posted
    variation_margin_usd: float
    threshold_usd: float       # MTA threshold
    status: str = "IN_ORDER"

    @property
    def market_value_usd(self) -> float:
        return self.face_value_usd * self.current_price

    @property
    def margin_call_usd(self) -> float:
        """Positive = we must post more; negative = excess."""
        return max(0.0, self.initial_margin_usd - self.variation_margin_usd)

    def to_dict(self) -> dict:
        return {
            "counterparty": self.counterparty,
            "collateral_asset": self.collateral_asset,
            "face_value_usd": self.face_value_usd,
            "market_value_usd": round(self.market_value_usd, 0),
            "current_price": round(self.current_price, 4),
            "initial_margin_usd": round(self.initial_margin_usd, 0),
            "variation_margin_usd": round(self.variation_margin_usd, 0),
            "margin_call_usd": round(self.margin_call_usd, 0),
            "threshold_usd": round(self.threshold_usd, 0),
            "status": self.status,
        }


class MarginEngine:
    """Simulates daily margin call lifecycle for repo/financing counterparties."""

    def __init__(self) -> None:
        self._accounts: list[MarginAccount] = [
            MarginAccount("Goldman Sachs",    "UST 10Y",   8_000_000_000, 0.9850, 220_000_000,  195_000_000, 500_000),
            MarginAccount("JPMorgan",         "Agency MBS", 4_500_000_000, 0.9780, 140_000_000, 128_000_000, 500_000),
            MarginAccount("Deutsche Bank",    "Corp IG",    2_200_000_000, 0.9650,  95_000_000,  88_000_000, 250_000),
            MarginAccount("Meridian Capital", "Equity",     1_100_000_000, 0.9400,  75_000_000,  61_000_000, 100_000),
        ]

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def apply_price_move(self, asset: str, price_change_pct: float) -> list[dict]:
        """
        Apply a price change to all accounts holding the given asset.
        Returns list of triggered margin calls (above MTA threshold).
        """
        calls = []
        for acct in self._accounts:
            if asset.lower() not in acct.collateral_asset.lower():
                continue
            old_price = acct.current_price
            acct.current_price = max(0.01, acct.current_price * (1 + price_change_pct))
            # VM changes by notional × price move
            vm_change = acct.face_value_usd * (acct.current_price - old_price)
            acct.variation_margin_usd += vm_change
            call = acct.margin_call_usd
            if call > acct.threshold_usd:
                acct.status = "MARGIN_CALL"
                calls.append({
                    "counterparty": acct.counterparty,
                    "asset": acct.collateral_asset,
                    "margin_call_usd": round(call, 0),
                    "threshold_usd": acct.threshold_usd,
                    "trigger": "price_move",
                    "price_change_pct": round(price_change_pct * 100, 2),
                })
            else:
                acct.status = "IN_ORDER"
        return calls

    def get_margin_summary(self) -> dict:
        total_im = sum(a.initial_margin_usd for a in self._accounts)
        total_vm = sum(a.variation_margin_usd for a in self._accounts)
        open_calls = [a for a in self._accounts if a.status == "MARGIN_CALL"]
        return {
            "accounts": [a.to_dict() for a in self._accounts],
            "summary": {
                "total_initial_margin_usd": round(total_im, 0),
                "total_variation_margin_usd": round(total_vm, 0),
                "net_margin_balance_usd": round(total_vm - total_im, 0),
                "open_margin_calls": len(open_calls),
                "total_call_amount_usd": round(sum(a.margin_call_usd for a in open_calls), 0),
            },
            "as_of": self._now(),
        }


# ---------------------------------------------------------------------------
# Module-level singletons
# ---------------------------------------------------------------------------

repo_ladder = RepoLadder()
margin_engine = MarginEngine()
