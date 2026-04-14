"""
Market data feed handler — polls real prices from Yahoo Finance.

In production, this connects to Bloomberg B-PIPE, Refinitiv Elektron,
or direct exchange feeds (CME, ICE, NASDAQ). For simulation, we poll
Yahoo Finance every few seconds and dispatch real prices to subscribers.
"""

from __future__ import annotations
import asyncio
from decimal import Decimal
from typing import Callable, Optional
import structlog

from models.market_data import Quote

log = structlog.get_logger(__name__)

# Spread and vol parameters (vol used only for Greeks/VaR estimates, not price generation).
# Prices are fetched live; these are never used to generate prices.
SEED_PRICES: dict[str, dict] = {
    "AAPL":          {"price": 185.50,  "vol": 0.22,  "spread_bps": 1.5},
    "MSFT":          {"price": 415.20,  "vol": 0.20,  "spread_bps": 1.2},
    "SPY":           {"price": 510.80,  "vol": 0.15,  "spread_bps": 0.5},
    "US10Y":         {"price": 97.50,   "vol": 0.05,  "spread_bps": 2.0},
    "EURUSD":        {"price": 1.0845,  "vol": 0.07,  "spread_bps": 0.8},
    "GBPUSD":        {"price": 1.2650,  "vol": 0.09,  "spread_bps": 1.0},
    "AAPL_CALL_200": {"price": 3.50,    "vol": 0.50,  "spread_bps": 50.0},
    "USD_IRS_5Y":    {"price": 100.00,  "vol": 0.02,  "spread_bps": 5.0},
    "CL1":           {"price": 78.40,   "vol": 0.30,  "spread_bps": 3.0},
    "NVDA":          {"price": 875.00,  "vol": 0.35,  "spread_bps": 2.0},
    "US2Y":          {"price": 99.10,   "vol": 0.02,  "spread_bps": 1.5},
    "GOOGL":         {"price": 175.0,   "vol": 0.24,  "spread_bps": 1.5},
    "USD_IRS_1Y":    {"price": 100.0,   "vol": 0.008, "spread_bps": 3.0},
    "USD_IRS_2Y":    {"price": 100.0,   "vol": 0.012, "spread_bps": 3.0},
    "USD_IRS_10Y":   {"price": 100.0,   "vol": 0.025, "spread_bps": 5.0},
    "USD_IRS_30Y":   {"price": 100.0,   "vol": 0.030, "spread_bps": 6.0},
    "IG_CDX":        {"price": 100.0,   "vol": 0.090, "spread_bps": 10.0},
    "HY_CDX":        {"price": 100.0,   "vol": 0.180, "spread_bps": 20.0},
    "XAUUSD":        {"price": 2350.0,  "vol": 0.14,  "spread_bps": 4.0},
    "NG1":           {"price": 2.20,    "vol": 0.50,  "spread_bps": 15.0},
}


class MarketDataFeed:
    """
    Live market data feed — polls Yahoo Finance on a configurable interval
    and dispatches real prices to subscribers.

    Tickers without a Yahoo Finance mapping (IRS, CDX) hold their last known
    price (initially the SEED_PRICES fallback) and are dispatched unchanged
    on every tick so subscribers always receive a full snapshot.

    Subscribers register callbacks that fire on every price update — exactly
    how real market data middleware works (e.g., TIBCO Rendezvous, Solace).
    """

    def __init__(self, tick_interval_ms: int = 5_000):
        self.tick_interval_ms = tick_interval_ms

        # Start from static fallbacks; overwritten by live fetch at start().
        self._prices: dict[str, float] = {
            k: v["price"] for k, v in SEED_PRICES.items()
        }
        self._apply_live_seeds()

        self._subscribers: dict[str, list[Callable]] = {}
        self._running = False
        self._history: dict[str, list[Quote]] = {k: [] for k in SEED_PRICES}

    def _apply_live_seeds(self) -> None:
        """Overwrite static seed prices with live Yahoo Finance quotes."""
        try:
            from infrastructure.market_data.live_seed import fetch_live_seeds
            live = fetch_live_seeds()
            for ticker, price in live.items():
                if ticker in self._prices:
                    old = self._prices[ticker]
                    self._prices[ticker] = price
                    log.info(
                        "market_data.live_seed",
                        ticker=ticker,
                        old=round(old, 4),
                        live=round(price, 4),
                    )
        except Exception as exc:
            log.warning("market_data.live_seed_failed", error=str(exc))

    def subscribe(self, ticker: str, callback: Callable[[Quote], None]) -> None:
        """Register a callback to receive quotes for a ticker."""
        if ticker not in self._subscribers:
            self._subscribers[ticker] = []
        self._subscribers[ticker].append(callback)
        log.debug("market_data.subscribed", ticker=ticker)

    def get_quote(self, ticker: str) -> Optional[Quote]:
        """Synchronous snapshot of latest price."""
        if ticker not in self._prices:
            return None
        price = self._prices[ticker]
        params = SEED_PRICES.get(ticker, {"spread_bps": 5.0})
        half_spread = price * params["spread_bps"] / 20000
        return Quote(
            ticker=ticker,
            bid=Decimal(str(round(price - half_spread, 6))),
            ask=Decimal(str(round(price + half_spread, 6))),
        )

    def get_all_quotes(self) -> dict[str, Quote]:
        return {t: q for t in self._prices if (q := self.get_quote(t))}

    async def _fetch_and_dispatch(self) -> None:
        """Fetch real prices from Yahoo Finance and push to subscribers."""
        try:
            from infrastructure.market_data.live_seed import fetch_live_seeds
            live = await asyncio.get_event_loop().run_in_executor(None, fetch_live_seeds)
            updated = 0
            for ticker, price in live.items():
                if ticker in self._prices:
                    self._prices[ticker] = price
                    updated += 1
            if updated:
                log.debug("market_data.refreshed", updated=updated)
        except Exception as exc:
            log.warning("market_data.refresh_failed", error=str(exc))

        # Dispatch current prices for all tickers (including non-YF ones at last known price)
        for ticker in list(self._prices.keys()):
            price = self._prices[ticker]
            params = SEED_PRICES.get(ticker, {"spread_bps": 5.0})
            half_spread = price * params["spread_bps"] / 20000
            quote = Quote(
                ticker=ticker,
                bid=Decimal(str(round(price - half_spread, 6))),
                ask=Decimal(str(round(price + half_spread, 6))),
            )
            self._history[ticker].append(quote)
            for cb in self._subscribers.get(ticker, []):
                try:
                    cb(quote)
                except Exception as e:
                    log.error("market_data.callback_error", ticker=ticker, error=str(e))

    async def start(self) -> None:
        """Begin polling real prices and notifying subscribers."""
        self._running = True
        log.info(
            "market_data.feed_started",
            tickers=list(self._prices.keys()),
            poll_interval_s=self.tick_interval_ms / 1000,
        )
        while self._running:
            await self._fetch_and_dispatch()
            await asyncio.sleep(self.tick_interval_ms / 1000)

    async def stop(self) -> None:
        self._running = False
        log.info("market_data.feed_stopped")

    def get_history(self, ticker: str, n: int = 252) -> list[Quote]:
        return self._history.get(ticker, [])[-n:]
