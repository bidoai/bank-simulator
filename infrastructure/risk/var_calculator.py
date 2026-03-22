"""
Value at Risk (VaR) calculator.

VaR answers the question: "What's the most we can lose in a day with 99%
confidence?" It's the central metric of market risk management and a
regulatory requirement under Basel III.

Three methods are implemented:
1. Historical Simulation — uses actual historical P&L distribution (non-parametric)
2. Parametric (variance-covariance) — assumes normal returns, uses sigma
3. Monte Carlo — generates thousands of random scenarios

Regulators currently prefer Expected Shortfall (ES/CVaR) over VaR because VaR
doesn't tell you HOW BAD the worst days are — only that they happen less than 1%
of the time. ES is the average loss in those worst days.
"""

from __future__ import annotations
import numpy as np
from decimal import Decimal
from datetime import datetime, date
from typing import Optional
import structlog

from models.risk_metrics import VaRResult

log = structlog.get_logger()


class VaRCalculator:
    """
    Multi-method VaR engine.

    In production banks (e.g., Goldman's SecDB, JPM's Athena), this runs
    on a compute grid overnight and produces results for every book, desk,
    and the total bank. The process typically takes hours for a complex portfolio.
    """

    def __init__(self, confidence: float = 0.99, horizon_days: int = 1):
        self.confidence = confidence
        self.horizon_days = horizon_days

    def historical_var(
        self,
        pnl_series: list[float],
        book_id: str = "default",
    ) -> VaRResult:
        """
        Historical Simulation VaR.

        Uses the actual distribution of past P&L. The key advantage: it captures
        fat tails, non-normality, and correlations that were present in history.
        The disadvantage: it's backward-looking and misses new risk regimes.

        Basel III requires at least 250 trading days of history.
        """
        if len(pnl_series) < 30:
            raise ValueError(f"Need at least 30 observations, got {len(pnl_series)}")

        arr = np.array(pnl_series)
        # VaR = the loss exceeded only (1-confidence)% of the time
        var = float(np.percentile(arr, (1 - self.confidence) * 100))
        # ES = average of all losses worse than VaR
        tail_losses = arr[arr <= var]
        es = float(np.mean(tail_losses)) if len(tail_losses) > 0 else var

        # Scale to horizon (sqrt of time rule — valid for i.i.d. returns)
        scale = np.sqrt(self.horizon_days)
        var_scaled = var * scale
        es_scaled = es * scale

        result = VaRResult(
            book_id=book_id,
            confidence_level=Decimal(str(self.confidence)),
            horizon_days=self.horizon_days,
            var_amount=Decimal(str(round(abs(var_scaled), 2))),
            cvar_amount=Decimal(str(round(abs(es_scaled), 2))),
            method="historical",
            lookback_days=len(pnl_series),
        )
        log.info(
            "risk.var_computed",
            method="historical",
            book_id=book_id,
            var=str(result.var_amount),
            es=str(result.cvar_amount),
        )
        return result

    def parametric_var(
        self,
        portfolio_value: float,
        portfolio_volatility: float,  # annualized
        book_id: str = "default",
    ) -> VaRResult:
        """
        Parametric (Delta-Normal) VaR.

        Assumes portfolio returns are normally distributed. Fast to compute
        but dangerously wrong for non-linear instruments (options) or
        fat-tailed distributions. Still used widely for simple books.

        VaR = Portfolio_Value * Daily_Vol * Z_score
        where daily_vol = annual_vol / sqrt(252)
        """
        from scipy import stats
        z_score = abs(stats.norm.ppf(1 - self.confidence))
        daily_vol = portfolio_volatility / np.sqrt(252)
        var_1d = portfolio_value * daily_vol * z_score
        es_1d = portfolio_value * daily_vol * stats.norm.pdf(stats.norm.ppf(self.confidence)) / (1 - self.confidence)

        var_scaled = var_1d * np.sqrt(self.horizon_days)
        es_scaled = es_1d * np.sqrt(self.horizon_days)

        return VaRResult(
            book_id=book_id,
            confidence_level=Decimal(str(self.confidence)),
            horizon_days=self.horizon_days,
            var_amount=Decimal(str(round(var_scaled, 2))),
            cvar_amount=Decimal(str(round(es_scaled, 2))),
            method="parametric",
        )

    def monte_carlo_var(
        self,
        positions: dict[str, float],       # ticker → dollar notional
        vols: dict[str, float],             # ticker → annualized vol
        correlations: Optional[np.ndarray] = None,
        n_simulations: int = 10_000,
        book_id: str = "default",
    ) -> VaRResult:
        """
        Monte Carlo VaR.

        Generates thousands of correlated random scenarios and computes
        P&L for each. Most flexible method — handles non-linear payoffs
        and complex correlations. Used for derivatives-heavy books.

        In production, banks run 250,000+ simulations on GPU clusters.
        """
        tickers = list(positions.keys())
        n = len(tickers)
        daily_vols = np.array([vols.get(t, 0.20) / np.sqrt(252) for t in tickers])

        if correlations is None:
            # Default to a moderate positive correlation (typical equity book)
            corr = np.full((n, n), 0.5)
            np.fill_diagonal(corr, 1.0)
        else:
            corr = correlations

        # Cholesky decomposition for correlated random numbers
        try:
            L = np.linalg.cholesky(corr)
        except np.linalg.LinAlgError:
            # If matrix not positive definite, use diagonal
            L = np.diag(daily_vols)

        # Generate correlated returns
        rng = np.random.default_rng(42)
        Z = rng.standard_normal((n_simulations, n))
        correlated_returns = Z @ L.T * daily_vols

        # Compute P&L for each simulation
        notionals = np.array([positions[t] for t in tickers])
        pnl_scenarios = (correlated_returns * notionals).sum(axis=1)

        var = float(np.percentile(pnl_scenarios, (1 - self.confidence) * 100))
        tail = pnl_scenarios[pnl_scenarios <= var]
        es = float(np.mean(tail)) if len(tail) > 0 else var

        scale = np.sqrt(self.horizon_days)
        return VaRResult(
            book_id=book_id,
            confidence_level=Decimal(str(self.confidence)),
            horizon_days=self.horizon_days,
            var_amount=Decimal(str(round(abs(var) * scale, 2))),
            cvar_amount=Decimal(str(round(abs(es) * scale, 2))),
            method="monte_carlo",
        )
