"""Tests for GreeksCalculator — per-instrument compute() and aggregate()."""
from __future__ import annotations

import pytest

from infrastructure.trading.greeks import GreeksCalculator

_GREEK_KEYS = ("delta", "gamma", "vega", "theta", "rho", "dv01")

# Convenience: verify all expected keys are present
def _has_all_keys(g: dict) -> bool:
    return all(k in g for k in _GREEK_KEYS)


class TestComputeByInstrumentType:

    def test_equity_has_nonzero_delta(self):
        g = GreeksCalculator.compute("AAPL", qty=100, price=185.0)
        assert _has_all_keys(g)
        assert g["delta"] == pytest.approx(100 * 185.0)
        assert g["dv01"] == 0.0

    def test_equity_zero_qty_gives_all_zeros(self):
        g = GreeksCalculator.compute("AAPL", qty=0, price=185.0)
        assert all(v == 0.0 for v in g.values())

    def test_bond_has_nonzero_dv01(self):
        g = GreeksCalculator.compute("US10Y", qty=10, price=95.0)
        assert _has_all_keys(g)
        assert g["dv01"] > 0
        assert g["delta"] == 0.0

    def test_bond_dv01_sign_flips_for_short(self):
        g_long  = GreeksCalculator.compute("US10Y", qty=+10, price=95.0)
        g_short = GreeksCalculator.compute("US10Y", qty=-10, price=95.0)
        assert g_long["dv01"] > 0
        assert g_short["dv01"] < 0
        assert g_long["dv01"] == pytest.approx(-g_short["dv01"])

    def test_irs_has_nonzero_dv01(self):
        g = GreeksCalculator.compute("USD_IRS_5Y", qty=1_000_000, price=100.0)
        assert _has_all_keys(g)
        assert g["dv01"] > 0
        assert g["delta"] == 0.0

    def test_fx_has_nonzero_delta(self):
        g = GreeksCalculator.compute("EURUSD", qty=500_000, price=1.08)
        assert _has_all_keys(g)
        assert g["delta"] == pytest.approx(500_000 * 1.08)
        assert g["dv01"] == 0.0

    def test_call_option_has_positive_delta(self):
        prices = {"AAPL": 185.0}
        g = GreeksCalculator.compute("AAPL_CALL_200", qty=10, price=5.0, prices=prices)
        assert _has_all_keys(g)
        assert g["delta"] > 0       # long call → positive delta

    def test_put_option_has_negative_delta(self):
        prices = {"AAPL": 185.0}
        g = GreeksCalculator.compute("AAPL_PUT_200", qty=10, price=5.0, prices=prices)
        assert _has_all_keys(g)
        assert g["delta"] < 0       # long put → negative delta

    def test_commodity_treated_as_equity_delta(self):
        g = GreeksCalculator.compute("CL1", qty=50, price=80.0)
        assert _has_all_keys(g)
        assert g["delta"] == pytest.approx(50 * 80.0)


class TestAggregate:

    def _make_positions(self):
        return [
            {"book_id": "EQ_BOOK_1",   "desk": "EQUITY", "instrument": "AAPL",    "quantity": 100.0,  "last_price": 185.0, "avg_cost": 180.0},
            {"book_id": "EQ_BOOK_1",   "desk": "EQUITY", "instrument": "MSFT",    "quantity": 50.0,   "last_price": 370.0, "avg_cost": 360.0},
            {"book_id": "RATES_BOOK_1","desk": "RATES",  "instrument": "US10Y",   "quantity": 10.0,   "last_price": 95.0,  "avg_cost": 96.0},
            {"book_id": "RATES_BOOK_1","desk": "RATES",  "instrument": "USD_IRS_5Y","quantity": 1_000_000.0,"last_price": 100.0,"avg_cost": 100.0},
        ]

    def test_returns_portfolio_and_by_book_keys(self):
        result = GreeksCalculator.aggregate(self._make_positions())
        assert "portfolio" in result
        assert "by_book" in result

    def test_portfolio_has_all_greek_keys(self):
        result = GreeksCalculator.aggregate(self._make_positions())
        assert _has_all_keys(result["portfolio"])

    def test_by_book_contains_correct_book_ids(self):
        result = GreeksCalculator.aggregate(self._make_positions())
        assert "EQ_BOOK_1" in result["by_book"]
        assert "RATES_BOOK_1" in result["by_book"]

    def test_portfolio_delta_equals_sum_of_book_deltas(self):
        result = GreeksCalculator.aggregate(self._make_positions())
        book_delta_sum = sum(b["delta"] for b in result["by_book"].values())
        assert result["portfolio"]["delta"] == pytest.approx(book_delta_sum)

    def test_portfolio_dv01_equals_sum_of_book_dv01s(self):
        result = GreeksCalculator.aggregate(self._make_positions())
        book_dv01_sum = sum(b["dv01"] for b in result["by_book"].values())
        assert result["portfolio"]["dv01"] == pytest.approx(book_dv01_sum)

    def test_zero_quantity_positions_are_skipped(self):
        positions = [
            {"book_id": "EQ_BOOK_1", "desk": "EQUITY", "instrument": "AAPL", "quantity": 0.0, "last_price": 185.0, "avg_cost": 185.0},
        ]
        result = GreeksCalculator.aggregate(positions)
        assert result["portfolio"]["delta"] == 0.0
        assert len(result["by_book"]) == 0

    def test_empty_positions_returns_zero_portfolio(self):
        result = GreeksCalculator.aggregate([])
        assert result["portfolio"]["delta"] == 0.0
        assert result["by_book"] == {}
