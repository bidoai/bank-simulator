"""
Order book and execution engine.

The order book is one of the most performance-critical components in any bank's
technology stack. Top-tier banks run their matching engines in co-located servers
at exchanges, with custom FPGA hardware achieving sub-microsecond latency.

This simulation uses Python with asyncio — conceptually identical to production,
just slower. The key data structures (price-sorted bid/ask queues with FIFO
priority within price levels) are the same.

Price-time priority: orders are matched by best price first, then oldest order
wins at the same price. This is how all major exchanges work.
"""

from __future__ import annotations
import asyncio
from collections import deque
from decimal import Decimal
from datetime import datetime
from typing import Optional, Callable
import uuid
import structlog

from models.trade import Trade, Side, OrderType, TradeStatus, Counterparty

log = structlog.get_logger(__name__)


class Order:
    """A pending order waiting to be filled."""
    __slots__ = [
        "order_id", "ticker", "side", "quantity", "remaining_qty",
        "price", "order_type", "book_id", "trader_id", "desk",
        "submitted_at", "status", "fills",
    ]

    def __init__(
        self,
        ticker: str,
        side: Side,
        quantity: Decimal,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[Decimal] = None,
        book_id: str = "default",
        trader_id: str = "system",
        desk: str = "prop",
    ):
        self.order_id = str(uuid.uuid4())
        self.ticker = ticker
        self.side = side
        self.quantity = quantity
        self.remaining_qty = quantity
        self.price = price
        self.order_type = order_type
        self.book_id = book_id
        self.trader_id = trader_id
        self.desk = desk
        self.submitted_at = datetime.utcnow()
        self.status = TradeStatus.PENDING
        self.fills: list[Trade] = []


class PriceLevel:
    """All orders at a single price level — FIFO queue."""
    def __init__(self, price: Decimal):
        self.price = price
        self.orders: deque[Order] = deque()

    def total_quantity(self) -> Decimal:
        return sum(o.remaining_qty for o in self.orders)


class OrderBook:
    """
    Central limit order book (CLOB) for a single instrument.

    Bids are sorted descending (highest bid first).
    Asks are sorted ascending (lowest ask first).
    Matching happens when bid >= ask.
    """

    def __init__(self, ticker: str, on_trade: Optional[Callable[[Trade], None]] = None):
        self.ticker = ticker
        self._bids: dict[Decimal, PriceLevel] = {}   # price → level
        self._asks: dict[Decimal, PriceLevel] = {}
        self._sorted_bids: list[Decimal] = []         # descending
        self._sorted_asks: list[Decimal] = []         # ascending
        self._on_trade = on_trade

    @property
    def best_bid(self) -> Optional[Decimal]:
        return self._sorted_bids[0] if self._sorted_bids else None

    @property
    def best_ask(self) -> Optional[Decimal]:
        return self._sorted_asks[0] if self._sorted_asks else None

    @property
    def mid_price(self) -> Optional[Decimal]:
        if self.best_bid and self.best_ask:
            return (self.best_bid + self.best_ask) / 2
        return None

    def submit_order(self, order: Order) -> list[Trade]:
        """
        Submit an order to the book. Returns list of trades generated.
        Market orders execute immediately against the opposite side.
        Limit orders rest in the book if no match is available.
        """
        trades = []

        if order.order_type == OrderType.MARKET:
            trades = self._match_market(order)
        elif order.order_type == OrderType.LIMIT:
            trades = self._match_limit(order)
            if order.remaining_qty > 0:
                self._add_to_book(order)

        if trades:
            log.info(
                "order_book.trades_executed",
                ticker=self.ticker,
                count=len(trades),
                total_qty=sum(t.quantity for t in trades),
            )

        return trades

    def _match_market(self, order: Order) -> list[Trade]:
        """Execute a market order — fill at whatever price is available."""
        trades = []
        levels = self._sorted_asks if order.side == Side.BUY else self._sorted_bids
        book = self._asks if order.side == Side.BUY else self._bids

        while order.remaining_qty > 0 and levels:
            best_price = levels[0]
            level = book[best_price]

            while order.remaining_qty > 0 and level.orders:
                passive_order = level.orders[0]
                fill_qty = min(order.remaining_qty, passive_order.remaining_qty)
                trade = self._create_trade(order, passive_order, best_price, fill_qty)
                trades.append(trade)
                order.remaining_qty -= fill_qty
                passive_order.remaining_qty -= fill_qty

                if passive_order.remaining_qty == 0:
                    level.orders.popleft()

            if not level.orders:
                del book[best_price]
                levels.pop(0)

        order.status = TradeStatus.FILLED if order.remaining_qty == 0 else TradeStatus.PARTIAL
        return trades

    def _match_limit(self, order: Order) -> list[Trade]:
        """Try to match a limit order against resting orders."""
        trades = []
        if order.side == Side.BUY:
            while (order.remaining_qty > 0 and self._sorted_asks
                   and order.price >= self._sorted_asks[0]):
                trades.extend(self._fill_against_level(order, self._asks, self._sorted_asks))
        else:
            while (order.remaining_qty > 0 and self._sorted_bids
                   and order.price <= self._sorted_bids[0]):
                trades.extend(self._fill_against_level(order, self._bids, self._sorted_bids))
        return trades

    def _fill_against_level(self, order: Order, book: dict, sorted_prices: list) -> list[Trade]:
        trades = []
        level_price = sorted_prices[0]
        level = book[level_price]

        while order.remaining_qty > 0 and level.orders:
            passive = level.orders[0]
            fill_qty = min(order.remaining_qty, passive.remaining_qty)
            trade = self._create_trade(order, passive, level_price, fill_qty)
            trades.append(trade)
            order.remaining_qty -= fill_qty
            passive.remaining_qty -= fill_qty
            if passive.remaining_qty == 0:
                level.orders.popleft()

        if not level.orders:
            del book[level_price]
            sorted_prices.pop(0)

        return trades

    def _add_to_book(self, order: Order) -> None:
        if order.side == Side.BUY:
            if order.price not in self._bids:
                self._bids[order.price] = PriceLevel(order.price)
                self._sorted_bids.append(order.price)
                self._sorted_bids.sort(reverse=True)
            self._bids[order.price].orders.append(order)
        else:
            if order.price not in self._asks:
                self._asks[order.price] = PriceLevel(order.price)
                self._sorted_asks.append(order.price)
                self._sorted_asks.sort()
            self._asks[order.price].orders.append(order)

    def _create_trade(self, aggressor: Order, passive: Order, price: Decimal, qty: Decimal) -> Trade:
        notional = price * qty
        trade = Trade(
            ticker=self.ticker,
            side=aggressor.side,
            quantity=qty,
            price=price,
            notional=notional,
            book_id=aggressor.book_id,
            trader_id=aggressor.trader_id,
            desk=aggressor.desk,
            order_id=aggressor.order_id,
            executed_at=datetime.utcnow(),
            counterparty=Counterparty.MARKET,
        )
        if self._on_trade:
            self._on_trade(trade)
        return trade

    def snapshot(self) -> dict:
        """Human-readable order book snapshot (top 5 levels)."""
        return {
            "ticker": self.ticker,
            "best_bid": str(self.best_bid),
            "best_ask": str(self.best_ask),
            "mid": str(self.mid_price),
            "bids": [(str(p), str(self._bids[p].total_quantity())) for p in self._sorted_bids[:5]],
            "asks": [(str(p), str(self._asks[p].total_quantity())) for p in self._sorted_asks[:5]],
        }
