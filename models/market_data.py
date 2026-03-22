"""
Market data models — the real-time price feed that everything depends on.

In a real bank, market data flows in from Bloomberg, Refinitiv, and direct
exchange connections. It drives everything: P&L marks, risk calculations,
algo triggers, and client pricing. Latency here is measured in microseconds
for HFT desks, milliseconds for most others.
"""

from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class Quote(BaseModel):
    """Live two-sided quote — the heartbeat of market data."""
    ticker: str
    bid: Decimal
    ask: Decimal
    bid_size: Decimal = Decimal("0")
    ask_size: Decimal = Decimal("0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    source: str = "simulated"

    @property
    def mid(self) -> Decimal:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        return self.ask - self.bid

    @property
    def spread_bps(self) -> Decimal:
        if self.mid > 0:
            return (self.spread / self.mid) * Decimal("10000")
        return Decimal("0")


class OHLCV(BaseModel):
    """Open-High-Low-Close-Volume bar — used for backtesting and charting."""
    ticker: str
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal
    bar_time: datetime
    interval: str = "1d"  # 1m, 5m, 1h, 1d, etc.


class MarketDepth(BaseModel):
    """
    Level 2 order book depth — full bid/ask stack.

    Market makers need this to understand where liquidity sits. A 'thin'
    book means large orders will move the market (high market impact).
    """
    ticker: str
    bids: list[tuple[Decimal, Decimal]] = Field(default_factory=list)  # [(price, size)]
    asks: list[tuple[Decimal, Decimal]] = Field(default_factory=list)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0][0] if self.asks else None

    def total_bid_liquidity(self, depth: int = 5) -> Decimal:
        return sum(s for _, s in self.bids[:depth])

    def total_ask_liquidity(self, depth: int = 5) -> Decimal:
        return sum(s for _, s in self.asks[:depth])
