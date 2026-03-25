"""
Position Manager — Aggregates and tracks positions across all trading books.

The PositionManager is the source of truth for what the bank owns right now.
Every trade flows through here: it updates the book, desk, and firm-level
positions, and marks them to the latest market prices.

Real banks use a system called the Position Management System (PMS) — often
an in-house build or a vendor system like Murex or Calypso. This class
models the key functions.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import structlog

log = structlog.get_logger()


@dataclass
class BookPosition:
    """A single position: one instrument in one trading book."""
    book_id: str
    desk: str
    instrument: str          # ticker / ID
    quantity: float          # positive = long, negative = short
    avg_cost: float          # weighted-average of remaining FIFO lots
    last_price: float        # current market price
    currency: str = "USD"

    def __post_init__(self):
        # FIFO lot queue: list of [qty, price] pairs in arrival order.
        # Seeded from (quantity, avg_cost) when constructed with a non-zero position.
        self._lots: list[list[float]] = (
            [[abs(self.quantity), self.avg_cost]] if self.quantity != 0 else []
        )

    @property
    def notional(self) -> float:
        return abs(self.quantity * self.last_price)

    @property
    def unrealised_pnl(self) -> float:
        return self.quantity * (self.last_price - self.avg_cost)

    @property
    def side(self) -> str:
        if self.quantity > 0:
            return "LONG"
        elif self.quantity < 0:
            return "SHORT"
        return "FLAT"

    def mark_to_market(self, new_price: float) -> float:
        """Update mark price, return the P&L change."""
        old_pnl = self.unrealised_pnl
        self.last_price = new_price
        return self.unrealised_pnl - old_pnl

    def _update_avg_cost(self) -> None:
        """Recompute avg_cost from remaining FIFO lots."""
        if not self._lots or self.quantity == 0:
            self.avg_cost = 0.0
        else:
            total_cost = sum(q * p for q, p in self._lots)
            total_qty = sum(q for q, _ in self._lots)
            self.avg_cost = total_cost / total_qty if total_qty else 0.0

    def apply_trade(self, qty: float, price: float) -> float:
        """
        Apply a new trade. Returns realised P&L from any closing trades.
        Uses true FIFO cost basis: oldest lot is consumed first when closing.
        """
        realised = 0.0

        if self.quantity != 0 and (self.quantity * qty < 0):
            # Closing (and possibly flipping) trade
            closing_long = self.quantity > 0   # True → we're long, trade is a sell
            remaining = abs(qty)

            while remaining > 1e-10 and self._lots:
                lot_qty, lot_price = self._lots[0]
                consumed = min(remaining, lot_qty)
                if closing_long:
                    realised += consumed * (price - lot_price)
                else:
                    realised += consumed * (lot_price - price)
                remaining -= consumed
                lot_qty -= consumed
                if lot_qty < 1e-10:
                    self._lots.pop(0)
                else:
                    self._lots[0] = [lot_qty, lot_price]

            self.quantity += qty

            if abs(self.quantity) < 1e-10:
                self.quantity = 0.0
                self._lots.clear()
            elif remaining > 1e-10:
                # Position flipped; open a new lot for the excess
                self._lots = [[remaining, price]]

            self._update_avg_cost()
            return realised

        # Opening or adding to existing position
        self.quantity += qty
        self._lots.append([qty, price])
        self._update_avg_cost()
        return 0.0

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "desk": self.desk,
            "instrument": self.instrument,
            "quantity": self.quantity,
            "side": self.side,
            "avg_cost": round(self.avg_cost, 4),
            "last_price": round(self.last_price, 4),
            "unrealised_pnl": round(self.unrealised_pnl, 2),
            "notional": round(self.notional, 2),
            "currency": self.currency,
        }


@dataclass
class BookSummary:
    """Aggregated view of a single trading book."""
    book_id: str
    desk: str
    positions: dict[str, BookPosition] = field(default_factory=dict)
    realised_pnl: float = 0.0

    @property
    def unrealised_pnl(self) -> float:
        return sum(p.unrealised_pnl for p in self.positions.values())

    @property
    def total_pnl(self) -> float:
        return self.realised_pnl + self.unrealised_pnl

    @property
    def gross_notional(self) -> float:
        return sum(p.notional for p in self.positions.values())

    @property
    def net_notional(self) -> float:
        return sum(p.quantity * p.last_price for p in self.positions.values())

    def to_dict(self) -> dict:
        return {
            "book_id": self.book_id,
            "desk": self.desk,
            "realised_pnl": round(self.realised_pnl, 2),
            "unrealised_pnl": round(self.unrealised_pnl, 2),
            "total_pnl": round(self.total_pnl, 2),
            "gross_notional": round(self.gross_notional, 2),
            "net_notional": round(self.net_notional, 2),
            "position_count": len([p for p in self.positions.values() if p.quantity != 0]),
        }


class PositionManager:
    """
    Central position store for the entire bank.

    Aggregation hierarchy:
        BookPosition (instrument × book)
            → BookSummary (book level)
                → desk level aggregation
                    → firm level aggregation

    Usage:
        pm = PositionManager()
        pm.add_trade("APEX_EQ_MM", "EQ_BOOK_1", "AAPL", qty=1000, price=185.50)
        pm.mark_to_market("AAPL", 186.20)
        report = pm.get_book_report("EQ_BOOK_1")
    """

    # Canonical desk → book mapping
    DESK_BOOKS: dict[str, list[str]] = {
        "EQUITY":      ["EQ_BOOK_1", "EQ_BOOK_2", "EQ_BOOK_3"],
        "RATES":       ["RATES_BOOK_1", "RATES_BOOK_2"],
        "FX":          ["FX_BOOK_1", "FX_BOOK_2"],
        "CREDIT":      ["CREDIT_BOOK_1", "CREDIT_BOOK_2"],
        "COMMODITIES": ["COMM_BOOK_1"],
        "DERIVATIVES": ["DERIV_BOOK_1", "DERIV_BOOK_2"],
    }

    # Reverse map: book → desk
    BOOK_DESK: dict[str, str] = {
        book: desk
        for desk, books in DESK_BOOKS.items()
        for book in books
    }

    def __init__(self):
        self._books: dict[str, BookSummary] = {}

    def _get_or_create_book(self, book_id: str) -> BookSummary:
        if book_id not in self._books:
            desk = self.BOOK_DESK.get(book_id, "UNKNOWN")
            self._books[book_id] = BookSummary(book_id=book_id, desk=desk)
        return self._books[book_id]

    # ── Writes ─────────────────────────────────────────────────────────────────

    def add_trade(
        self,
        desk: str,
        book_id: str,
        instrument: str,
        qty: float,
        price: float,
        currency: str = "USD",
    ) -> float:
        """
        Record a trade. Returns realised P&L from any position close.
        """
        book = self._get_or_create_book(book_id)
        if instrument not in book.positions:
            book.positions[instrument] = BookPosition(
                book_id=book_id,
                desk=desk,
                instrument=instrument,
                quantity=0,
                avg_cost=price,
                last_price=price,
                currency=currency,
            )
        pos = book.positions[instrument]
        realised = pos.apply_trade(qty, price)
        book.realised_pnl += realised
        log.info(
            "position.trade",
            book=book_id,
            instrument=instrument,
            qty=qty,
            price=price,
            realised_pnl=realised,
        )
        return realised

    def mark_to_market(self, instrument: str, new_price: float) -> dict[str, float]:
        """
        Update mark price for an instrument across ALL books.
        Returns dict of book_id → MTM P&L change.
        """
        changes = {}
        for book_id, book in self._books.items():
            if instrument in book.positions:
                pnl_delta = book.positions[instrument].mark_to_market(new_price)
                changes[book_id] = pnl_delta
        return changes

    # ── Reads ──────────────────────────────────────────────────────────────────

    def get_position(self, book_id: str, instrument: str) -> Optional[BookPosition]:
        book = self._books.get(book_id)
        if book:
            return book.positions.get(instrument)
        return None

    def get_book_report(self, book_id: str) -> dict:
        """Full position blotter for one book."""
        book = self._books.get(book_id)
        if not book:
            return {"book_id": book_id, "error": "Book not found"}
        return {
            **book.to_dict(),
            "positions": [
                p.to_dict() for p in book.positions.values()
                if p.quantity != 0
            ],
        }

    def get_desk_report(self, desk: str) -> dict:
        """Aggregated P&L and notional for all books in a desk."""
        books = [b for b in self._books.values() if b.desk == desk]
        if not books:
            return {"desk": desk, "error": "No books found"}

        total_realised = sum(b.realised_pnl for b in books)
        total_unrealised = sum(b.unrealised_pnl for b in books)
        total_gross = sum(b.gross_notional for b in books)
        total_net = sum(b.net_notional for b in books)

        return {
            "desk": desk,
            "book_count": len(books),
            "realised_pnl": round(total_realised, 2),
            "unrealised_pnl": round(total_unrealised, 2),
            "total_pnl": round(total_realised + total_unrealised, 2),
            "gross_notional": round(total_gross, 2),
            "net_notional": round(total_net, 2),
            "books": [b.to_dict() for b in books],
        }

    def get_firm_report(self) -> dict:
        """Firm-wide P&L and notional summary."""
        all_books = list(self._books.values())
        if not all_books:
            return {"firm": "APEX", "total_pnl": 0.0, "message": "No positions"}

        by_desk: dict[str, dict] = {}
        all_desks = sorted({b.desk for b in all_books})
        for desk in all_desks:
            report = self.get_desk_report(desk)
            if "error" not in report:
                by_desk[desk] = report

        total_realised   = sum(b.realised_pnl   for b in all_books)
        total_unrealised = sum(b.unrealised_pnl for b in all_books)
        total_gross      = sum(b.gross_notional for b in all_books)

        return {
            "firm": "APEX",
            "realised_pnl":   round(total_realised, 2),
            "unrealised_pnl": round(total_unrealised, 2),
            "total_pnl":      round(total_realised + total_unrealised, 2),
            "gross_notional": round(total_gross, 2),
            "book_count": len(all_books),
            "position_count": sum(
                len([p for p in b.positions.values() if p.quantity != 0])
                for b in all_books
            ),
            "by_desk": by_desk,
        }

    def get_all_positions(self) -> list[dict]:
        """Flat list of all non-zero positions across all books."""
        result = []
        for book in self._books.values():
            for pos in book.positions.values():
                if pos.quantity != 0:
                    result.append(pos.to_dict())
        return result

    def get_instrument_exposure(self, instrument: str) -> dict:
        """Cross-book exposure to a single instrument."""
        positions = []
        total_qty = 0.0
        total_notional = 0.0

        for book in self._books.values():
            pos = book.positions.get(instrument)
            if pos and pos.quantity != 0:
                positions.append(pos.to_dict())
                total_qty += pos.quantity
                total_notional += pos.notional

        return {
            "instrument": instrument,
            "total_quantity": total_qty,
            "total_notional": round(total_notional, 2),
            "net_side": "LONG" if total_qty > 0 else "SHORT" if total_qty < 0 else "FLAT",
            "positions": positions,
        }
