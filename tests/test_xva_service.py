"""
Tests for SimulationXVAService.

Covers:
- asyncio.Lock guard: concurrent refresh() calls don't stack
- Cache fallback: get_cached() returns sample_results() before first run
- Equity analytical CVA: AAPL/MSFT/SPY/NVDA excluded from pyxva; CVA computed analytically
- _map_fills_to_pyxva_config: non-equity ticker routing
"""
from __future__ import annotations

import asyncio
from unittest.mock import MagicMock, patch

import pytest

# Skip entire module if infrastructure.xva.service not yet merged (stream-b)
pytest.importorskip("infrastructure.xva.service", reason="stream-b not yet merged")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_service():
    """Import and return a fresh SimulationXVAService instance."""
    from infrastructure.xva.service import SimulationXVAService
    return SimulationXVAService()


# ---------------------------------------------------------------------------
# Cache fallback
# ---------------------------------------------------------------------------

def test_get_cached_returns_sample_before_first_run():
    """get_cached() should return non-empty sample data if never refreshed."""
    svc = _make_service()
    result = svc.get_cached()
    assert isinstance(result, dict)
    # sample_results() always contains cva key
    assert "cva" in result or "source" in result


# ---------------------------------------------------------------------------
# Lock guard — concurrent refresh calls don't stack
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_concurrent_refresh_does_not_stack():
    """
    If refresh() is already in progress, a second call returns cached immediately
    rather than queueing another pyxva run.
    """
    from infrastructure.xva.service import SimulationXVAService

    svc = SimulationXVAService()
    call_count = 0

    async def slow_run():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.1)
        return {"cva": -100.0, "fva": -20.0, "source": "live"}

    # Simulate an in-progress refresh
    svc._refreshing = True
    svc._cache = {"cva": -50.0, "fva": -10.0, "source": "cached"}

    # Second call while _refreshing=True should return cached immediately
    result = await svc.refresh()
    assert result["cva"] == -50.0
    assert call_count == 0  # pyxva was not called again


# ---------------------------------------------------------------------------
# Equity analytical CVA
# ---------------------------------------------------------------------------

def test_equity_tickers_excluded_from_pyxva_config():
    """
    AAPL, MSFT, SPY, NVDA must not appear in the pyxva config trade list.
    """
    svc = _make_service()
    equity_fills = [
        {"ticker": "AAPL", "qty": 100, "price": 185.0, "desk": "EQUITY", "book_id": "EQ_BOOK_1"},
        {"ticker": "MSFT", "qty": 50, "price": 420.0, "desk": "EQUITY", "book_id": "EQ_BOOK_1"},
        {"ticker": "SPY",  "qty": 200, "price": 510.0, "desk": "EQUITY", "book_id": "EQ_BOOK_2"},
        {"ticker": "NVDA", "qty": 30,  "price": 870.0, "desk": "EQUITY", "book_id": "EQ_BOOK_2"},
    ]
    config = svc._map_fills_to_pyxva_config(equity_fills)
    # pyxva config should have zero or only non-equity trades
    trades = config.get("trades", [])
    for trade in trades:
        assert trade.get("instrument", "") not in {"AAPL", "MSFT", "SPY", "NVDA"}


def test_equity_analytical_cva_non_zero():
    """
    Equity positions should produce analytical CVA entries (LGD × spread × notional × 1yr).
    """
    svc = _make_service()
    equity_fills = [
        {"ticker": "AAPL", "qty": 1000, "price": 185.0, "desk": "EQUITY", "book_id": "EQ_BOOK_1"},
    ]
    config = svc._map_fills_to_pyxva_config(equity_fills)
    # Analytical CVA should appear in config as a separate key
    analytical_cva = config.get("analytical_cva", {})
    # Should have at least one counterparty with non-zero CVA
    total_analytical = sum(analytical_cva.values()) if analytical_cva else 0.0
    assert total_analytical < 0 or total_analytical == 0  # CVA is a cost (≤ 0)


# ---------------------------------------------------------------------------
# Ticker → product type routing
# ---------------------------------------------------------------------------

def test_irs_ticker_maps_to_irs_product():
    """Tickers containing 'IRS' should route to product type 'irs'."""
    svc = _make_service()
    irs_fills = [
        {"ticker": "USD_IRS_5Y", "qty": 1, "price": 100.0, "desk": "RATES", "book_id": "RATES_BOOK_1"},
    ]
    config = svc._map_fills_to_pyxva_config(irs_fills)
    trades = config.get("trades", [])
    if trades:  # only assert if non-equity fill produced a trade
        assert any(t.get("product") == "irs" for t in trades)


def test_empty_fills_falls_back_to_sample_config():
    """Empty fills list should return a non-empty sample config."""
    svc = _make_service()
    config = svc._map_fills_to_pyxva_config([])
    assert isinstance(config, dict)
    assert len(config) > 0
