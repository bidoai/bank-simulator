"""
Tests for BookPosition short-selling, covering, and flip accounting.

The external engineering review raised a concern that short-cover logic
was broken because lots might store negative quantities. This test suite
proves the invariant: lots always store abs(qty) regardless of direction,
and realised P&L, avg_cost, and flip handling are all correct.
"""
import pytest
from infrastructure.trading.position_manager import BookPosition


def _pos(qty: float, price: float) -> BookPosition:
    """Helper: open a position at a given qty and price."""
    p = BookPosition(
        book_id="TEST_BOOK",
        desk="EQUITY",
        instrument="AAPL",
        quantity=0,
        avg_cost=0.0,
        last_price=price,
    )
    p.apply_trade(qty, price)
    return p


class TestShortPositionAccounting:

    def test_short_open(self):
        """Selling short creates a negative quantity with a positive lot."""
        p = _pos(-100, 150.0)
        assert p.quantity == -100
        assert p.side == "SHORT"
        assert len(p._lots) == 1
        assert p._lots[0] == [100.0, 150.0]   # lot qty is ALWAYS positive
        assert p.avg_cost == 150.0

    def test_short_partial_cover(self):
        """Buying back part of a short reduces quantity and computes P&L correctly."""
        p = _pos(-100, 150.0)
        realised = p.apply_trade(+40, 140.0)   # cover 40 at $140 (profit $10/share)
        assert p.quantity == -60
        assert abs(realised - 40 * (150.0 - 140.0)) < 1e-9   # 40 × $10 = $400
        assert len(p._lots) == 1
        assert abs(p._lots[0][0] - 60.0) < 1e-9
        assert p.avg_cost == 150.0   # remaining lot unchanged

    def test_short_full_cover(self):
        """Buying back exactly the short quantity flattens the position."""
        p = _pos(-100, 150.0)
        realised = p.apply_trade(+100, 130.0)   # cover at $130 (profit $20/share)
        assert p.quantity == 0.0
        assert abs(realised - 100 * (150.0 - 130.0)) < 1e-9   # 100 × $20 = $2,000
        assert p._lots == []
        assert p.avg_cost == 0.0

    def test_short_cover_loss(self):
        """Covering at a higher price than entry produces a loss."""
        p = _pos(-100, 150.0)
        realised = p.apply_trade(+100, 160.0)   # cover at $160 (loss $10/share)
        assert p.quantity == 0.0
        assert abs(realised - (-1000.0)) < 1e-9   # 100 × ($150 - $160) = -$1,000

    def test_short_to_long_flip(self):
        """Buying more than the short flips to a long position."""
        p = _pos(-100, 150.0)
        realised = p.apply_trade(+150, 140.0)   # cover 100 + go long 50
        # Cover leg P&L: 100 × ($150 - $140) = $1,000
        assert abs(realised - 1_000.0) < 1e-9
        # After flip: long 50 at $140
        assert abs(p.quantity - 50.0) < 1e-9
        assert p.side == "LONG"
        assert len(p._lots) == 1
        assert abs(p._lots[0][0] - 50.0) < 1e-9
        assert abs(p._lots[0][1] - 140.0) < 1e-9
        assert abs(p.avg_cost - 140.0) < 1e-9

    def test_long_to_short_flip(self):
        """Selling more than the long flips to a short position."""
        p = _pos(+100, 100.0)
        realised = p.apply_trade(-150, 110.0)   # sell 100 (close) + go short 50
        # Close leg P&L: 100 × ($110 - $100) = $1,000
        assert abs(realised - 1_000.0) < 1e-9
        # After flip: short 50 at $110
        assert abs(p.quantity - (-50.0)) < 1e-9
        assert p.side == "SHORT"
        assert len(p._lots) == 1
        assert abs(p._lots[0][0] - 50.0) < 1e-9
        assert abs(p.avg_cost - 110.0) < 1e-9

    def test_fifo_ordering_on_partial_cover(self):
        """FIFO: first lot opened is the first consumed on cover."""
        p = _pos(-100, 150.0)
        p.apply_trade(-50, 155.0)   # add to short at $155 (now short 150)
        assert p.quantity == -150
        # Cover 100 → should consume the $150 lot first (FIFO)
        realised = p.apply_trade(+100, 140.0)
        # First 100 units covered at entry $150: P&L = 100 × ($150 - $140) = $1,000
        assert abs(realised - 1_000.0) < 1e-9
        assert abs(p.quantity - (-50.0)) < 1e-9
        # Remaining lot is the $155 entry
        assert abs(p._lots[0][1] - 155.0) < 1e-9
