"""
Stressed VaR (SVaR) — Basel 2.5 market risk capital supplement.

The stressed period is calibrated to the 2008–2009 Financial Crisis.
SVaR uses the same Monte Carlo engine as VaRCalculator but with
stressed volatility multipliers and the STRESS correlation regime.

Capital formula (Internal Models Approach):
  VaR_capital  = max(VaR_t, (1/60) × k × Σ VaR_60d)
  sVaR_capital = max(sVaR_t, (1/60) × k × Σ sVaR_60d)
  Total_MR_capital = VaR_capital + sVaR_capital
"""
from __future__ import annotations

from typing import Any

import numpy as np
import structlog

from infrastructure.risk.var_calculator import VaRCalculator
from infrastructure.risk.correlation_regime import CorrelationRegime, regime_model

log = structlog.get_logger()

# ---------------------------------------------------------------------------
# Stressed period parameters — 2008–2009 Financial Crisis calibration
# ---------------------------------------------------------------------------
STRESSED_PERIOD = {
    "name": "2008–2009 Global Financial Crisis",
    "start_date": "2008-09-01",
    "end_date": "2009-03-31",
    "equity_vol_multiplier": 3.5,
    "credit_spread_vol_multiplier": 4.0,
    "fx_vol_multiplier": 2.0,
    "rates_vol_multiplier": 2.5,
    "correlation_regime": "STRESS",
    "rationale": (
        "The 2008–2009 crisis represents the most severe stress period in recent history. "
        "VIX peaked at 89.5 (Oct 2008). Equity vols averaged 3.5× normal. IG credit spreads "
        "widened 4× vs pre-crisis levels. The STRESS correlation matrix (equity-credit ≈ -0.80) "
        "is used as the correlation input."
    ),
}

# Default annualised vols (normal regime) by asset class
_NORMAL_VOLS: dict[str, float] = {
    "AAPL": 0.20,
    "MSFT": 0.18,
    "GOOGL": 0.22,
    "US10Y": 0.04,
    "EURUSD": 0.07,
    "IG_CDX": 0.12,
}

# Stressed vols derived by applying multipliers
_STRESSED_VOLS: dict[str, float] = {
    "AAPL":   _NORMAL_VOLS["AAPL"]   * STRESSED_PERIOD["equity_vol_multiplier"],
    "MSFT":   _NORMAL_VOLS["MSFT"]   * STRESSED_PERIOD["equity_vol_multiplier"],
    "GOOGL":  _NORMAL_VOLS["GOOGL"]  * STRESSED_PERIOD["equity_vol_multiplier"],
    "US10Y":  _NORMAL_VOLS["US10Y"]  * STRESSED_PERIOD["rates_vol_multiplier"],
    "EURUSD": _NORMAL_VOLS["EURUSD"] * STRESSED_PERIOD["fx_vol_multiplier"],
    "IG_CDX": _NORMAL_VOLS["IG_CDX"] * STRESSED_PERIOD["credit_spread_vol_multiplier"],
}

# Demo portfolio for fallback
_DEMO_POSITIONS: dict[str, float] = {
    "AAPL":   50_000_000,
    "MSFT":   40_000_000,
    "GOOGL":  35_000_000,
    "US10Y":  80_000_000,
    "EURUSD": 60_000_000,
    "IG_CDX": 25_000_000,
}

# Firm-level 60-day average VaR used in the capital formula (demo constant)
_FIRM_60D_AVG_VAR_M  = 95.0    # $95M
_SVAR_MULTIPLIER     = 3.2     # sVaR is ~3.2× normal VaR (2008-calibrated)


class StressedVaREngine:
    """
    Basel 2.5 Stressed VaR calculation.

    Uses the existing VaRCalculator with stressed inputs:
    - Stressed volatilities (2008 calibration)
    - STRESS correlation regime (elevated equity-credit correlation)
    """

    def __init__(self) -> None:
        self._calc = VaRCalculator(confidence=0.99, horizon_days=1)

    def _build_positions(self, positions: dict[str, float] | None) -> dict[str, float]:
        """Resolve positions to a dict of ticker→notional, filling gaps with demo data."""
        if not positions:
            return _DEMO_POSITIONS
        # Filter to tickers with stressed vols available; fill rest from demo
        resolved: dict[str, float] = {}
        for ticker in _STRESSED_VOLS:
            if ticker in positions:
                resolved[ticker] = float(positions[ticker])
            else:
                resolved[ticker] = _DEMO_POSITIONS.get(ticker, 0.0)
        return {k: v for k, v in resolved.items() if v != 0.0}

    def calculate_stressed_var(
        self,
        positions: dict[str, float] | None = None,
        confidence: float = 0.99,
    ) -> dict[str, Any]:
        """
        Calculate normal VaR and stressed VaR for the portfolio.

        Returns:
          standard_var  — 99% VaR under normal conditions ($M)
          stressed_var  — 99% VaR under stressed conditions ($M)
          multiplier    — sVaR / VaR ratio
          regime        — "STRESS" (always for sVaR)
        """
        pos = self._build_positions(positions)
        calc = VaRCalculator(confidence=confidence, horizon_days=1)

        # Normal VaR
        normal_result = calc.monte_carlo_var(
            positions=pos,
            vols=_NORMAL_VOLS,
            regime=CorrelationRegime.NORMAL,
            book_id="FIRM_NORMAL",
        )
        standard_var_m = float(normal_result.var_amount) / 1e6

        # Stressed VaR — use stress correlation from regime_model directly
        stress_corr = regime_model.STRESS_CORR
        tickers = list(pos.keys())
        # Build sub-correlation matrix for the active tickers
        canonical = regime_model.TICKERS
        if all(t in canonical for t in tickers):
            idx = [canonical.index(t) for t in tickers]
            sub_corr = stress_corr[np.ix_(idx, idx)]
        else:
            sub_corr = None

        stressed_result = calc.monte_carlo_var(
            positions=pos,
            vols={t: _STRESSED_VOLS.get(t, _NORMAL_VOLS.get(t, 0.20) * 3.0) for t in tickers},
            correlations=sub_corr,
            regime=CorrelationRegime.STRESS,
            book_id="FIRM_STRESSED",
        )
        stressed_var_m = float(stressed_result.var_amount) / 1e6

        multiplier = round(stressed_var_m / standard_var_m, 3) if standard_var_m > 0 else _SVAR_MULTIPLIER

        log.info(
            "stressed_var.calculated",
            standard_var_m=round(standard_var_m, 2),
            stressed_var_m=round(stressed_var_m, 2),
            multiplier=multiplier,
        )

        return {
            "standard_var": round(standard_var_m, 2),
            "stressed_var": round(stressed_var_m, 2),
            "multiplier": multiplier,
            "regime": "STRESS",
            "confidence": confidence,
            "horizon_days": 1,
            "stressed_period": STRESSED_PERIOD["name"],
        }

    def calculate_capital_requirement(
        self,
        var_history_60d_avg: float | None = None,
        svar_history_60d_avg: float | None = None,
        k: float = 3.0,
    ) -> dict[str, Any]:
        """
        Compute VaR and sVaR capital requirements per Basel 2.5 IMA.

        var_history_60d_avg / svar_history_60d_avg: 60-day average in $M.
        k: capital multiplier from traffic-light zone (3.0 – 4.0).

        Returns var_capital, svar_capital, total_capital (all in $M).
        """
        if var_history_60d_avg is None:
            var_history_60d_avg = _FIRM_60D_AVG_VAR_M
        if svar_history_60d_avg is None:
            svar_history_60d_avg = var_history_60d_avg * _SVAR_MULTIPLIER

        # Latest single-day estimates (use 60d avg as proxy for today's VaR in demo)
        var_t = var_history_60d_avg
        svar_t = svar_history_60d_avg

        var_capital  = max(var_t,  (k / 60.0) * var_history_60d_avg  * 60)
        svar_capital = max(svar_t, (k / 60.0) * svar_history_60d_avg * 60)
        total_capital = var_capital + svar_capital

        # Simplified: the formula above reduces to max(VaR_t, k * avg_60d)
        var_capital  = max(var_t,  k * var_history_60d_avg)
        svar_capital = max(svar_t, k * svar_history_60d_avg)
        total_capital = var_capital + svar_capital

        log.info(
            "stressed_var.capital_calculated",
            var_capital_m=round(var_capital, 2),
            svar_capital_m=round(svar_capital, 2),
            total_m=round(total_capital, 2),
            k=k,
        )

        return {
            "var_capital_m": round(var_capital, 2),
            "svar_capital_m": round(svar_capital, 2),
            "total_market_risk_capital_m": round(total_capital, 2),
            "k_multiplier": k,
            "var_60d_avg_m": round(var_history_60d_avg, 2),
            "svar_60d_avg_m": round(svar_history_60d_avg, 2),
            "formula": "max(VaR_t, k × avg_VaR_60d) + max(sVaR_t, k × avg_sVaR_60d)",
        }

    def get_stress_period_info(self) -> dict[str, Any]:
        """Return description of the reference stressed period."""
        return STRESSED_PERIOD

    def get_full_report(
        self, positions: dict[str, float] | None = None
    ) -> dict[str, Any]:
        """Comprehensive SVaR report combining all outputs."""
        svar_result = self.calculate_stressed_var(positions)
        capital = self.calculate_capital_requirement(
            var_history_60d_avg=_FIRM_60D_AVG_VAR_M,
            svar_history_60d_avg=svar_result["stressed_var"] * 0.9,
            k=3.0,
        )
        return {
            "stressed_var": svar_result,
            "capital_requirement": capital,
            "stressed_period": self.get_stress_period_info(),
            "normal_vols": _NORMAL_VOLS,
            "stressed_vols": {k: round(v, 4) for k, v in _STRESSED_VOLS.items()},
            "regulatory_basis": "Basel 2.5 — Amendment to Basel II Market Risk Framework (July 2009)",
        }


# Module-level singleton
stressed_var_engine = StressedVaREngine()
