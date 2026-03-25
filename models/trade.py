"""
Trade model — the atomic unit of the bank's activity.

Every trade the bank executes is captured as an immutable record here. In
production, this would be persisted to a trade repository (often a relational
DB like Oracle or a purpose-built system like Murex or Calypso). The FIX
protocol fields are included because FIX is the industry standard for
electronic order routing.
"""

from __future__ import annotations
from enum import Enum
from decimal import Decimal
from datetime import datetime
from typing import Optional
import uuid
from pydantic import BaseModel, Field


class Side(str, Enum):
    BUY = "buy"
    SELL = "sell"


class TradeStatus(str, Enum):
    PENDING = "pending"       # Submitted, not yet executed
    PARTIAL = "partial"       # Partially filled
    FILLED = "filled"         # Fully executed
    CANCELLED = "cancelled"   # Cancelled before fill
    REJECTED = "rejected"     # Rejected by exchange or risk


class OrderType(str, Enum):
    MARKET = "market"         # Execute at best available price
    LIMIT = "limit"           # Execute only at specified price or better
    STOP = "stop"             # Trigger market order at stop price
    STOP_LIMIT = "stop_limit"
    TWAP = "twap"             # Time-weighted average price (algo)
    VWAP = "vwap"             # Volume-weighted average price (algo)


class Counterparty(str, Enum):
    """Who sits on the other side of the trade."""
    MARKET = "market"          # Exchange/lit market
    DARK_POOL = "dark_pool"    # ATS / dark pool
    DEALER = "dealer"          # Bilateral OTC dealer
    CLIENT = "client"          # Bank's own client
    INTERBANK = "interbank"    # Another bank in the interbank market
    INTERNAL = "internal"      # Internal transfer/book


class Trade(BaseModel):
    """
    Immutable record of an executed trade.

    The trade_id follows FIX tag 37 (OrderID) convention. The allocation of
    trades to books is critical — each book has its own P&L and risk limits.
    """
    trade_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_id: Optional[str] = None      # Parent order if algo-split
    ticker: str
    side: Side
    quantity: Decimal
    price: Decimal                       # Executed price
    notional: Decimal                    # quantity * price * point_value
    currency: str = "USD"
    order_type: OrderType = OrderType.MARKET
    status: TradeStatus = TradeStatus.FILLED
    counterparty: Counterparty = Counterparty.MARKET

    # Book allocation — where this trade lives in the bank's structure
    desk: str = "prop"                  # e.g. "equity_arb", "rates", "fx_mm"
    book_id: str = "default"            # The trading book
    trader_id: str = "system"

    # Timestamps
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    executed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None

    # Settlement
    settlement_date: Optional[str] = None   # T+2 for equities, T+1 for FX spot
    settlement_currency: Optional[str] = None

    # Fees
    commission: Decimal = Decimal("0")
    exchange_fee: Decimal = Decimal("0")

    # Regulatory
    lei: Optional[str] = None           # Legal Entity Identifier (MiFID II)
    uti: Optional[str] = None           # Unique Trade ID (EMIR reporting)
    algo_id: Optional[str] = None       # Algo strategy if applicable

    class Config:
        frozen = True

    @property
    def net_cash_flow(self) -> Decimal:
        """Cash impact: negative for buys (cash out), positive for sells."""
        multiplier = Decimal("-1") if self.side == Side.BUY else Decimal("1")
        return multiplier * self.notional


class TradeConfirmation(BaseModel):
    """Response DTO returned by the OMS after a successful order fill."""
    trade_id: str
    uti: str
    ticker: str
    side: str
    quantity: float
    fill_price: float
    notional: float
    desk: str
    book_id: str
    executed_at: datetime
    greeks: dict               # {delta, gamma, vega, theta, rho, dv01}
    var_before: float
    var_after: float
    limit_headroom_pct: float
    limit_status: str          # GREEN / YELLOW / ORANGE / RED
    pre_trade_approved: bool
    pre_trade_message: str


class OrderBook(BaseModel):
    """
    The live order book for a single instrument — bids and asks.

    In HFT and market-making, this structure is maintained in memory and
    updated in microseconds. The spread (best ask - best bid) is where the
    market maker earns revenue.
    """
    ticker: str
    bids: list[tuple[Decimal, Decimal]] = Field(default_factory=list)  # (price, qty)
    asks: list[tuple[Decimal, Decimal]] = Field(default_factory=list)  # (price, qty)
    timestamp: datetime = Field(default_factory=datetime.utcnow)

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self.bids[0][0] if self.bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self.asks[0][0] if self.asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    @property
    def spread(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return self.best_ask - self.best_bid
        return None

    @property
    def spread_bps(self) -> Optional[Decimal]:
        """Spread in basis points — the key metric for market-making profitability."""
        if self.spread and self.mid_price and self.mid_price > 0:
            return (self.spread / self.mid_price) * Decimal("10000")
        return None
