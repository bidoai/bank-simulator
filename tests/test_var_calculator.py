"""Tests for VaRCalculator — historical, parametric, and Monte Carlo methods."""
from __future__ import annotations

import pytest
import numpy as np

from infrastructure.risk.var_calculator import VaRCalculator
from config.settings import VAR_MIN_HISTORY


# 252 days of synthetic daily P&L: mostly small losses, a few fat-tail events
_PNL_SERIES = (
    list(np.random.default_rng(42).normal(-5_000, 50_000, 252))
)


class TestHistoricalVaR:
    def test_returns_var_result_with_expected_fields(self):
        calc = VaRCalculator()
        result = calc.historical_var(_PNL_SERIES, book_id="EQUITY_BOOK_1")

        assert result.book_id == "EQUITY_BOOK_1"
        assert result.method == "historical"
        assert float(result.confidence_level) == pytest.approx(0.99, abs=1e-6)
        assert result.horizon_days == 1
        assert float(result.var_amount) >= 0
        assert float(result.cvar_amount) >= 0

    def test_cvar_geq_var(self):
        """ES (CVaR) must be at least as large as VaR by construction."""
        calc = VaRCalculator()
        result = calc.historical_var(_PNL_SERIES)
        assert float(result.cvar_amount) >= float(result.var_amount)

    def test_lookback_matches_input_length(self):
        calc = VaRCalculator()
        result = calc.historical_var(_PNL_SERIES)
        assert result.lookback_days == len(_PNL_SERIES)

    def test_raises_on_insufficient_history(self):
        calc = VaRCalculator()
        short = list(range(VAR_MIN_HISTORY - 1))
        with pytest.raises(ValueError, match=str(VAR_MIN_HISTORY)):
            calc.historical_var(short)

    def test_exact_min_history_does_not_raise(self):
        calc = VaRCalculator()
        pnl = list(np.random.default_rng(7).normal(0, 10_000, VAR_MIN_HISTORY))
        result = calc.historical_var(pnl)
        assert float(result.var_amount) >= 0

    def test_custom_confidence_level(self):
        calc_99 = VaRCalculator(confidence=0.99)
        calc_95 = VaRCalculator(confidence=0.95)
        r99 = calc_99.historical_var(_PNL_SERIES)
        r95 = calc_95.historical_var(_PNL_SERIES)
        # 99% VaR should be at least as large as 95% VaR
        assert float(r99.var_amount) >= float(r95.var_amount)


class TestParametricVaR:
    def test_returns_non_negative_var(self):
        calc = VaRCalculator()
        result = calc.parametric_var(portfolio_value=10_000_000, portfolio_volatility=0.20)
        assert float(result.var_amount) > 0

    def test_higher_vol_gives_higher_var(self):
        calc = VaRCalculator()
        r_low  = calc.parametric_var(10_000_000, portfolio_volatility=0.10)
        r_high = calc.parametric_var(10_000_000, portfolio_volatility=0.40)
        assert float(r_high.var_amount) > float(r_low.var_amount)

    def test_method_label(self):
        calc = VaRCalculator()
        result = calc.parametric_var(1_000_000, 0.15)
        assert result.method == "parametric"

    def test_cvar_geq_var(self):
        calc = VaRCalculator()
        result = calc.parametric_var(5_000_000, 0.25)
        assert float(result.cvar_amount) >= float(result.var_amount)


class TestMonteCarloVaR:
    _POSITIONS = {"AAPL": 500_000.0, "MSFT": 300_000.0, "GOOGL": 200_000.0}
    _VOLS = {"AAPL": 0.30, "MSFT": 0.25, "GOOGL": 0.28}

    def test_returns_non_negative_var(self):
        calc = VaRCalculator()
        result = calc.monte_carlo_var(self._POSITIONS, self._VOLS, n_simulations=1_000)
        assert float(result.var_amount) >= 0

    def test_method_label(self):
        calc = VaRCalculator()
        result = calc.monte_carlo_var(self._POSITIONS, self._VOLS, n_simulations=500)
        assert result.method == "monte_carlo"

    def test_cvar_geq_var(self):
        calc = VaRCalculator()
        result = calc.monte_carlo_var(self._POSITIONS, self._VOLS, n_simulations=1_000)
        assert float(result.cvar_amount) >= float(result.var_amount)

    def test_larger_portfolio_gives_larger_var(self):
        calc = VaRCalculator()
        small = {"AAPL": 100_000.0}
        large = {"AAPL": 10_000_000.0}
        vols  = {"AAPL": 0.30}
        r_small = calc.monte_carlo_var(small, vols, n_simulations=500)
        r_large = calc.monte_carlo_var(large, vols, n_simulations=500)
        assert float(r_large.var_amount) > float(r_small.var_amount)
