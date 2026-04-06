"""Tests for the P&L attribution engine."""
from __future__ import annotations

import pytest
from infrastructure.trading.pnl_explain import PnLExplainEngine


_EQUITY_POS = {
    "instrument": "AAPL",
    "quantity": 1000.0,
    "desk": "EQUITY",
    "book_id": "EQ_BOOK_01",
    "avg_cost": 200.0,
    "last_price": 220.0,
    "unrealised_pnl": 20_000.0,
    "realised_pnl": 0.0,
}

_BOND_POS = {
    "instrument": "US10Y",
    "quantity": 10_000.0,
    "desk": "RATES",
    "book_id": "IR_BOOK_01",
    "avg_cost": 98.0,
    "last_price": 97.0,
    "unrealised_pnl": -10_000.0,
    "realised_pnl": 0.0,
}

_OPTION_POS = {
    "instrument": "AAPL_CALL_200",
    "quantity": 10.0,
    "desk": "DERIVATIVES",
    "book_id": "DERIV_01",
    "avg_cost": 40.0,
    "last_price": 50.0,
    "unrealised_pnl": 10_000.0,
    "realised_pnl": 0.0,
}


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------

def test_sod_snapshot_stores_prices():
    engine = PnLExplainEngine()
    prices = {"AAPL": 200.0, "MSFT": 400.0}
    engine.take_sod_snapshot([_EQUITY_POS], prices)
    assert engine._sod_prices["AAPL"] == 200.0
    assert engine._sod_ts is not None


# ---------------------------------------------------------------------------
# Explain structure
# ---------------------------------------------------------------------------

def test_explain_returns_portfolio_and_by_desk():
    engine = PnLExplainEngine()
    prices_sod = {"AAPL": 200.0}
    engine.take_sod_snapshot([_EQUITY_POS], prices_sod)

    prices_eod = {"AAPL": 220.0}
    result = engine.explain([_EQUITY_POS], prices_eod)

    assert "portfolio" in result
    assert "by_desk" in result
    assert "EQUITY" in result["by_desk"]
    assert result["as_of"] is not None


def test_explain_portfolio_keys():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([_EQUITY_POS], {"AAPL": 200.0})
    result = engine.explain([_EQUITY_POS], {"AAPL": 220.0})
    port = result["portfolio"]
    for key in ("delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl", "unexplained", "total_actual_pnl"):
        assert key in port, f"missing key: {key}"


# ---------------------------------------------------------------------------
# Equity attribution
# ---------------------------------------------------------------------------

def test_equity_delta_pnl_uses_unrealised():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([_EQUITY_POS], {"AAPL": 200.0})
    result = engine.explain([_EQUITY_POS], {"AAPL": 220.0})
    port = result["portfolio"]
    # Actual P&L comes from unrealised_pnl field = 20,000
    assert port["total_actual_pnl"] == pytest.approx(20_000.0, abs=1.0)
    # Delta should carry most of the P&L (equity is delta-1)
    assert port["delta_pnl"] == pytest.approx(20_000.0, abs=200.0)
    assert port["gamma_pnl"] == 0.0
    assert port["theta_pnl"] == 0.0
    assert port["vega_pnl"] == 0.0


def test_equity_unexplained_is_small():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([_EQUITY_POS], {"AAPL": 200.0})
    result = engine.explain([_EQUITY_POS], {"AAPL": 220.0})
    port = result["portfolio"]
    # Unexplained should be near zero for a delta-1 position
    assert abs(port["unexplained"]) < 200.0


# ---------------------------------------------------------------------------
# Bond attribution
# ---------------------------------------------------------------------------

def test_bond_delta_pnl_nonzero():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([_BOND_POS], {"US10Y": 98.0})
    result = engine.explain([_BOND_POS], {"US10Y": 97.0})
    port = result["portfolio"]
    # Bond fell → negative delta P&L
    assert port["delta_pnl"] < 0
    assert port["gamma_pnl"] == 0.0
    assert port["theta_pnl"] == 0.0


# ---------------------------------------------------------------------------
# Option attribution
# ---------------------------------------------------------------------------

def test_option_has_greeks():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([_OPTION_POS], {"AAPL": 190.0, "AAPL_CALL_200": 40.0})
    result = engine.explain([_OPTION_POS], {"AAPL": 210.0, "AAPL_CALL_200": 50.0})
    port = result["portfolio"]
    # Options have non-trivial gamma and theta
    assert port["delta_pnl"] != 0.0
    assert "gamma_pnl" in port


# ---------------------------------------------------------------------------
# Multi-desk aggregation
# ---------------------------------------------------------------------------

def test_multi_desk_aggregation():
    engine = PnLExplainEngine()
    positions = [_EQUITY_POS, _BOND_POS]
    prices_sod = {"AAPL": 200.0, "US10Y": 98.0}
    engine.take_sod_snapshot(positions, prices_sod)
    prices_eod = {"AAPL": 220.0, "US10Y": 97.0}
    result = engine.explain(positions, prices_eod)

    assert "EQUITY" in result["by_desk"]
    assert "RATES" in result["by_desk"]
    # Portfolio totals = sum of desks
    port = result["portfolio"]
    desk_total = sum(d["total_actual_pnl"] for d in result["by_desk"].values())
    assert port["total_actual_pnl"] == pytest.approx(desk_total, abs=1.0)


# ---------------------------------------------------------------------------
# Empty positions
# ---------------------------------------------------------------------------

def test_empty_positions_returns_zero_portfolio():
    engine = PnLExplainEngine()
    engine.take_sod_snapshot([], {})
    result = engine.explain([], {})
    port = result["portfolio"]
    for key in ("delta_pnl", "gamma_pnl", "theta_pnl", "vega_pnl", "unexplained", "total_actual_pnl"):
        assert port[key] == 0.0


# ---------------------------------------------------------------------------
# Missing SOD snapshot falls back to avg_cost
# ---------------------------------------------------------------------------

def test_explain_without_sod_snapshot_uses_avg_cost():
    engine = PnLExplainEngine()  # no SOD snapshot taken
    result = engine.explain([_EQUITY_POS], {"AAPL": 220.0})
    # Should not raise; falls back to avg_cost as SOD price
    assert "portfolio" in result
    port = result["portfolio"]
    # Actual P&L from unrealised_pnl field
    assert port["total_actual_pnl"] == pytest.approx(20_000.0, abs=1.0)
