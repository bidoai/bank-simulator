"""
Market data feed handler — simulates a live price feed.

In production, this connects to Bloomberg B-PIPE, Refinitiv Elektron,
or direct exchange feeds (CME, ICE, NASDAQ). For simulation, we generate
realistic price paths using geometric Brownian motion (the same math
behind Black-Scholes option pricing).
"""

from __future__ import annotations
import asyncio
import random
import math
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime
from typing import Callable, Optional
import structlog

from models.market_data import Quote, OHLCV

log = structlog.get_logger()

# Static fallback prices and vol/spread parameters.
# Prices are overwritten at startup by fetch_live_seeds() where available.
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
    Simulates a live market data feed using GBM (Geometric Brownian Motion).

    GBM formula: S(t+dt) = S(t) * exp((mu - 0.5*sigma²)*dt + sigma*sqrt(dt)*Z)
    where Z ~ N(0,1). This is the same model used in Black-Scholes.

    Subscribers register callbacks that fire on every price update — exactly
    how real market data middleware works (e.g., TIBCO Rendezvous, Solace).
    """

    def __init__(self, tick_interval_ms: int = 500):
        self.tick_interval_ms = tick_interval_ms

        # Start from static fallbacks, then overwrite with live prices where available.
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

    def _next_price(self, ticker: str) -> float:
        """Generate next price using GBM with dt = tick interval."""
        params = SEED_PRICES[ticker]
        sigma = params["vol"]
        dt = self.tick_interval_ms / (252 * 6.5 * 3600 * 1000)  # fraction of trading year
        mu = 0.0  # zero drift for simulation (risk-neutral measure)
        z = random.gauss(0, 1)
        current = self._prices[ticker]
        return current * math.exp((mu - 0.5 * sigma**2) * dt + sigma * math.sqrt(dt) * z)

    async def start(self) -> None:
        """Begin ticking prices and notifying subscribers."""
        self._running = True
        log.info("market_data.feed_started", tickers=list(self._prices.keys()))
        while self._running:
            for ticker in list(self._prices.keys()):
                new_price = self._next_price(ticker)
                self._prices[ticker] = new_price
                params = SEED_PRICES[ticker]
                half_spread = new_price * params["spread_bps"] / 20000
                quote = Quote(
                    ticker=ticker,
                    bid=Decimal(str(round(new_price - half_spread, 6))),
                    ask=Decimal(str(round(new_price + half_spread, 6))),
                )
                self._history[ticker].append(quote)
                # Fire all subscriber callbacks
                for cb in self._subscribers.get(ticker, []):
                    try:
                        cb(quote)
                    except Exception as e:
                        log.error("market_data.callback_error", ticker=ticker, error=str(e))
            await asyncio.sleep(self.tick_interval_ms / 1000)

    async def stop(self) -> None:
        self._running = False
        log.info("market_data.feed_stopped")

    def get_history(self, ticker: str, n: int = 252) -> list[Quote]:
        return self._history.get(ticker, [])[-n:]
