"""
Correlation Regime Model — two-regime Cholesky for Monte Carlo VaR.

Normal regime: moderate historical correlations from calm markets.
Stress regime: correlations spike toward 1.0 (2008/2020-style).
Regime detection: simple vol-of-vol threshold proxy for HMM.
"""

from __future__ import annotations

from enum import Enum
from typing import Optional

import numpy as np
import structlog

log = structlog.get_logger()


class CorrelationRegime(Enum):
    NORMAL = "normal"
    STRESS = "stress"


class CorrelationRegimeModel:
    """
    Two-regime correlation model with HMM-based regime detection.

    Normal regime: historical sample correlations from calm periods.
    Stress regime: correlations spike toward 1.0 (as observed in 2008, 2020).

    Regime detection: simple volatility-based HMM proxy
    (realized vol of vol > threshold → stress regime).
    """

    TICKERS = ["AAPL", "MSFT", "GOOGL", "US10Y", "EURUSD", "IG_CDX"]

    # Vol-of-vol threshold: if cross-asset vol exceeds this, declare stress
    STRESS_VOL_THRESHOLD = 0.035  # ~3.5% daily vol-of-vol

    # Normal regime: realistic correlations for calm markets
    # Order: AAPL, MSFT, GOOGL, US10Y, EURUSD, IG_CDX
    #
    # Equity-equity: ~0.65-0.75
    # Equity-bond (US10Y): ~-0.20 (flight-to-safety)
    # Equity-FX (EURUSD): ~0.15
    # Equity-credit (IG_CDX): ~-0.45 (spreads widen when stocks fall)
    # Bond-FX: ~0.10
    # Bond-credit: ~0.35
    NORMAL_CORR = np.array([
        # AAPL   MSFT   GOOGL  US10Y  EURUSD IG_CDX
        [ 1.00,  0.72,  0.70, -0.20,  0.15, -0.45],  # AAPL
        [ 0.72,  1.00,  0.68, -0.22,  0.14, -0.43],  # MSFT
        [ 0.70,  0.68,  1.00, -0.18,  0.13, -0.42],  # GOOGL
        [-0.20, -0.22, -0.18,  1.00,  0.10,  0.35],  # US10Y
        [ 0.15,  0.14,  0.13,  0.10,  1.00, -0.12],  # EURUSD
        [-0.45, -0.43, -0.42,  0.35, -0.12,  1.00],  # IG_CDX
    ], dtype=float)

    # Stress regime: 2008/2020-style correlation spikes
    # Equity-equity: ~0.90 (everything falls together)
    # Equity-bond: ~-0.10 (reduced flight-to-safety, sometimes breaks down)
    # Equity-credit: ~-0.80 (credit spreads spike hard when equities crash)
    # FX volatility increases, correlations spike
    STRESS_CORR = np.array([
        # AAPL   MSFT   GOOGL  US10Y  EURUSD IG_CDX
        [ 1.00,  0.92,  0.91, -0.10,  0.35, -0.80],  # AAPL
        [ 0.92,  1.00,  0.90, -0.12,  0.33, -0.78],  # MSFT
        [ 0.91,  0.90,  1.00, -0.08,  0.32, -0.77],  # GOOGL
        [-0.10, -0.12, -0.08,  1.00,  0.08,  0.20],  # US10Y
        [ 0.35,  0.33,  0.32,  0.08,  1.00, -0.30],  # EURUSD
        [-0.80, -0.78, -0.77,  0.20, -0.30,  1.00],  # IG_CDX
    ], dtype=float)

    def __init__(self) -> None:
        self._normal_chol = np.linalg.cholesky(self.NORMAL_CORR)
        self._stress_chol = np.linalg.cholesky(self.STRESS_CORR)
        log.info(
            "correlation_regime_model.initialized",
            normal_shape=self._normal_chol.shape,
            stress_shape=self._stress_chol.shape,
        )

    def detect_regime(self, recent_returns: np.ndarray) -> CorrelationRegime:
        """
        Returns STRESS if cross-asset realized vol-of-vol exceeds threshold.
        recent_returns: shape (T, N) — T time steps, N assets.
        """
        if recent_returns.ndim == 1:
            recent_returns = recent_returns.reshape(-1, 1)

        if recent_returns.shape[0] < 5:
            return CorrelationRegime.NORMAL

        # Realized vol per asset, then vol-of-vol across assets
        rolling_vols = np.std(recent_returns, axis=0)
        cross_asset_vol = float(np.mean(rolling_vols))

        regime = (
            CorrelationRegime.STRESS
            if cross_asset_vol > self.STRESS_VOL_THRESHOLD
            else CorrelationRegime.NORMAL
        )
        log.debug(
            "correlation_regime_model.regime_detected",
            cross_asset_vol=round(cross_asset_vol, 5),
            threshold=self.STRESS_VOL_THRESHOLD,
            regime=regime.value,
        )
        return regime

    def get_cholesky(self, regime: CorrelationRegime) -> np.ndarray:
        if regime == CorrelationRegime.STRESS:
            return self._stress_chol
        return self._normal_chol

    def get_current_regime(
        self, recent_returns: Optional[np.ndarray] = None
    ) -> CorrelationRegime:
        if recent_returns is None:
            return CorrelationRegime.NORMAL
        return self.detect_regime(recent_returns)


regime_model = CorrelationRegimeModel()
