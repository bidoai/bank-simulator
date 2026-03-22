"""
Position model — the bank's current holdings.

A position is the net result of all trades in a given instrument for a given book.
If you bought 1000 shares of AAPL and sold 300, your position is +700 (long).
Positions drive P&L and are the primary input into risk calculations.

"Flat" = zero position. "Long" = you own it. "Short" = you've sold something
you borrowed, expecting to buy it back cheaper.
"""

from __future__ import annotations
from decimal import Decimal
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, computed_field


class PositionType(str, Enum := __import__('enum').Enum):
    LONG = "long"
    SHORT = "short"
    FLAT = "flat"


class Position(BaseModel):
    """
    Net position in a single instrument for a single book.

    The unrealized P&L (mark-to-market) is computed daily. Realized P&L is
    locked in when positions are closed. The sum across all positions gives
    the book's total P&L.
    """
    ticker: str
    book_id: str
    desk: str

    # Position sizing
    quantity: Decimal = Decimal("0")      # Positive = long, negative = short
    avg_cost: Decimal = Decimal("0")      # Volume-weighted average entry price
    notional: Decimal = Decimal("0")      # Current market value (qty * mark_price)

    # P&L
    realized_pnl: Decimal = Decimal("0")
    unrealized_pnl: Decimal = Decimal("0")
    daily_pnl: Decimal = Decimal("0")

    # Mark prices
    mark_price: Optional[Decimal] = None  # Current market price (from EOD or live)
    prev_close: Optional[Decimal] = None  # Yesterday's closing price

    # Greeks (for derivatives)
    delta: Optional[Decimal] = None       # Sensitivity to underlying price
    gamma: Optional[Decimal] = None       # Rate of change of delta
    vega: Optional[Decimal] = None        # Sensitivity to volatility
    theta: Optional[Decimal] = None       # Time decay (per day)
    rho: Optional[Decimal] = None         # Sensitivity to interest rate

    last_updated: datetime = Field(default_factory=datetime.utcnow)

    @property
    def position_type(self) -> str:
        if self.quantity > 0:
            return "long"
        elif self.quantity < 0:
            return "short"
        return "flat"

    @property
    def total_pnl(self) -> Decimal:
        return self.realized_pnl + self.unrealized_pnl

    def update_mark(self, new_price: Decimal) -> None:
        """Recompute unrealized P&L when a new market price arrives."""
        if self.avg_cost and self.quantity != 0:
            self.unrealized_pnl = (new_price - self.avg_cost) * self.quantity
        self.mark_price = new_price
        self.notional = abs(self.quantity) * new_price
        self.last_updated = datetime.utcnow()

    def apply_trade(self, qty: Decimal, price: Decimal) -> None:
        """
        Update position when a new trade is booked.
        Uses FIFO cost basis (first-in, first-out).
        """
        old_qty = self.quantity
        new_qty = old_qty + qty

        if old_qty == 0:
            self.avg_cost = price
        elif (old_qty > 0 and qty > 0) or (old_qty < 0 and qty < 0):
            # Adding to position — update average cost
            total_cost = (abs(old_qty) * self.avg_cost) + (abs(qty) * price)
            self.avg_cost = total_cost / abs(new_qty)
        else:
            # Reducing or flipping position — realize P&L on closed portion
            closed_qty = min(abs(old_qty), abs(qty))
            if old_qty > 0:
                self.realized_pnl += (price - self.avg_cost) * closed_qty
            else:
                self.realized_pnl += (self.avg_cost - price) * closed_qty

            if abs(qty) > abs(old_qty):
                # Position flipped — new avg cost is the flip price
                self.avg_cost = price

        self.quantity = new_qty
        self.last_updated = datetime.utcnow()
