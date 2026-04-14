"""
FRTB Internal Models Approach (IMA) Capital Engine — Apex Global Bank.

Implements BCBS MAR33 / BCBS 457:
  - Expected Shortfall at 97.5% confidence (ES97.5) — reuses VaRCalculator
  - P&L Attribution (PLA) test: Spearman correlation ≥ 0.80 + mean ratio 0.80–1.20
  - Desk-level IMA vs SA routing based on backtesting zone + PLA pass/fail
  - IMA capital = 1.5 × ES97.5 scaled to 10-day horizon (BCBS 457 MRF multiplier)

ES97.5 is computed via VaRCalculator(confidence=0.975).monte_carlo_var() —
the existing cvar_amount field IS the Expected Shortfall at the given confidence.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import structlog

log = structlog.get_logger(__name__)

# BCBS 457 IMA multiplier (modellable risk factors, no add-on)
_IMA_MULTIPLIER = 1.5
_SQRT_10 = 10 ** 0.5

# Desks mapped to FRTB risk factor buckets
_DESKS = ["EQUITY", "RATES", "FX", "CREDIT", "COMMODITIES", "DERIVATIVES"]

# PLA test pass thresholds (BCBS 457 §89)
_PLA_SPEARMAN_MIN = 0.80
_PLA_MEAN_RATIO_MIN = 0.80
_PLA_MEAN_RATIO_MAX = 1.20

# Demo positions for ES calculation when no live positions available
_DEMO_POSITIONS = {
    "AAPL": 5_000_000.0,
    "MSFT": 8_000_000.0,
    "GOOGL": 3_000_000.0,
    "US10Y": 50_000_000.0,
    "EURUSD": 10_000_000.0,
}

_DEMO_VOLS = {
    "AAPL":   0.28,
    "MSFT":   0.26,
    "GOOGL":  0.30,
    "US10Y":  0.05,
    "EURUSD": 0.08,
}


class FRTBIMAEngine:
    """
    FRTB IMA engine. Stateless — reads from VaRCalculator and VaRBacktestStore.
    """

    def calculate_es(
        self,
        positions: dict[str, float] | None = None,
        vols: dict[str, float] | None = None,
        confidence: float = 0.975,
        n_simulations: int = 10_000,
        book_id: str = "FIRM",
    ) -> dict[str, Any]:
        """
        Expected Shortfall at confidence (default 97.5%).
        Delegates to VaRCalculator(confidence=confidence).monte_carlo_var()
        and reads cvar_amount (which is the ES/CVaR).
        """
        from infrastructure.risk.var_calculator import VaRCalculator

        pos = positions or _DEMO_POSITIONS
        v = vols or _DEMO_VOLS

        calc = VaRCalculator(confidence=confidence)
        result = calc.monte_carlo_var(
            positions=pos,
            vols=v,
            n_simulations=n_simulations,
        )

        es_1d = float(result.cvar_amount)
        var_1d = float(result.var_amount)
        es_10d = es_1d * _SQRT_10

        log.info("frtb.es_calculated", book_id=book_id, es_1d_usd=round(es_1d, 2),
                 es_10d_usd=round(es_10d, 2), confidence=confidence)

        return {
            "book_id":       book_id,
            "confidence":    confidence,
            "es_97_5_1d_usd":  round(es_1d, 2),
            "es_97_5_10d_usd": round(es_10d, 2),
            "var_97_5_1d_usd": round(var_1d, 2),
            "method":        "monte_carlo",
            "n_simulations": n_simulations,
            "regulatory_basis": "BCBS MAR33.4 / BCBS 457",
        }

    def run_pla_test(self, desk: str) -> dict[str, Any]:
        """
        P&L Attribution test for a desk per BCBS 457 §89.

        Uses 250-day backtest history from VaRBacktestStore.
        HPL = realized_pnl series.
        RTPL = risk-theoretical P&L synthesised from var_99 with ±5% noise
               (RTPL ≈ var_99 × (0.975/0.99); negative because VaR is a loss threshold).

        Pass criteria: Spearman ρ ≥ 0.80 AND mean ratio 0.80 ≤ (μ_RTPL / μ_HPL) ≤ 1.20.
        Falls back to FIRM history if desk-specific history is unavailable.
        """
        from infrastructure.risk.var_backtest_store import backtest_store as var_backtest_store

        history = var_backtest_store.get_history(desk, 250)
        if not history:
            history = var_backtest_store.get_history("FIRM", 250)

        if not history:
            return {
                "desk": desk,
                "pla_pass": False,
                "spearman_corr": None,
                "mean_ratio": None,
                "n_obs": 0,
                "zone": "RED",
                "note": "No backtest history available",
            }

        hpl = np.array([float(r["realized_pnl"]) for r in history])
        var_99 = np.array([float(r["var_99"]) for r in history])

        # RTPL: scale var_99 to 97.5% confidence level + inject 5% random noise
        rng = np.random.default_rng(42)
        scale = 0.975 / 0.99
        rtpl = -(var_99 * scale) + rng.normal(0, 0.05 * np.abs(var_99))

        # Spearman rank correlation
        from scipy.stats import spearmanr
        corr_result = spearmanr(hpl, rtpl)
        spearman_corr = float(corr_result.statistic)

        # Mean ratio
        hpl_mean = float(np.mean(hpl))
        rtpl_mean = float(np.mean(rtpl))
        mean_ratio = (rtpl_mean / hpl_mean) if abs(hpl_mean) > 1e-6 else float("nan")

        pla_pass = (
            spearman_corr >= _PLA_SPEARMAN_MIN
            and _PLA_MEAN_RATIO_MIN <= mean_ratio <= _PLA_MEAN_RATIO_MAX
        )

        # Zone mapping (BCBS 457 §89): Green/Amber/Red
        if spearman_corr >= 0.80 and _PLA_MEAN_RATIO_MIN <= mean_ratio <= _PLA_MEAN_RATIO_MAX:
            zone = "GREEN"
        elif spearman_corr >= 0.70 or (0.70 <= mean_ratio <= 1.30):
            zone = "AMBER"
        else:
            zone = "RED"

        return {
            "desk":          desk,
            "pla_pass":      pla_pass,
            "spearman_corr": round(spearman_corr, 4),
            "mean_ratio":    round(mean_ratio, 4) if not np.isnan(mean_ratio) else None,
            "n_obs":         len(history),
            "zone":          zone,
            "thresholds": {
                "spearman_min":    _PLA_SPEARMAN_MIN,
                "mean_ratio_min":  _PLA_MEAN_RATIO_MIN,
                "mean_ratio_max":  _PLA_MEAN_RATIO_MAX,
            },
            "regulatory_basis": "BCBS 457 §89",
        }

    def get_desk_routing(self) -> dict[str, Any]:
        """
        IMA vs SA routing for each desk.
        IMA: backtesting zone GREEN AND PLA passes.
        SA:  zone YELLOW/RED OR PLA fails.
        """
        from infrastructure.risk.var_backtest_store import backtest_store as var_backtest_store

        routing: dict[str, str] = {}
        details: dict[str, dict] = {}
        for desk in _DESKS:
            zone = var_backtest_store.get_traffic_light_zone("FIRM")  # per-desk falls back to FIRM
            pla = self.run_pla_test(desk)
            uses_ima = (zone == "GREEN") and pla["pla_pass"]
            routing[desk] = "IMA" if uses_ima else "SA"
            details[desk] = {
                "routing":        routing[desk],
                "backtesting_zone": zone,
                "pla_pass":       pla["pla_pass"],
                "spearman_corr":  pla["spearman_corr"],
            }

        ima_desks = [d for d, r in routing.items() if r == "IMA"]
        sa_desks  = [d for d, r in routing.items() if r == "SA"]

        return {
            "routing":    routing,
            "details":    details,
            "ima_desks":  ima_desks,
            "sa_desks":   sa_desks,
            "ima_count":  len(ima_desks),
            "sa_count":   len(sa_desks),
            "regulatory_basis": "BCBS MAR33 / BCBS 457 §87-89",
        }

    def calculate_ima_capital(
        self,
        positions: dict[str, float] | None = None,
        vols: dict[str, float] | None = None,
    ) -> dict[str, Any]:
        """
        IMA market risk capital for the firm.
        ES_10d = ES_1d × √10 (BCBS MAR33.2)
        IMA capital = multiplier × ES_10d (multiplier = 1.5 for GREEN backtesting)
        """
        es_result = self.calculate_es(positions=positions, vols=vols)
        es_10d = es_result["es_97_5_10d_usd"]
        ima_capital = _IMA_MULTIPLIER * es_10d

        return {
            "es_97_5_1d_usd":   es_result["es_97_5_1d_usd"],
            "es_97_5_10d_usd":  es_10d,
            "multiplier":        _IMA_MULTIPLIER,
            "ima_capital_usd":   round(ima_capital, 2),
            "regulatory_basis":  "BCBS MAR33.4",
        }

    def calculate_sa_capital(self) -> float:
        """SA capital proxy from the existing regulatory capital engine."""
        try:
            from infrastructure.risk.risk_service import risk_service
            from infrastructure.risk.regulatory_capital import capital_engine
            positions = risk_service.position_manager.get_all_positions()
            result = capital_engine.calculate(positions)
            return float(result.get("rwa_usd", 0.0)) * 0.08
        except Exception:
            return 5_000_000_000.0  # $5B fallback

    def calculate_portfolio_capital(self) -> dict[str, Any]:
        """
        Full FRTB capital report: IMA desks use ES-based capital,
        SA desks use SA-derived capital.
        """
        routing_result = self.get_desk_routing()
        ima_result = self.calculate_ima_capital()
        sa_capital = self.calculate_sa_capital()

        # IMA capital applied to IMA desks; SA split equally across SA desks
        n_sa = len(routing_result["sa_desks"])
        n_ima = len(routing_result["ima_desks"])
        ima_capital = ima_result["ima_capital_usd"] if n_ima > 0 else 0.0
        total_capital = ima_capital + sa_capital

        return {
            "desk_routing":          routing_result["routing"],
            "ima_desks":             routing_result["ima_desks"],
            "sa_desks":              routing_result["sa_desks"],
            "es_97_5_1d_usd":        ima_result["es_97_5_1d_usd"],
            "es_97_5_10d_usd":       ima_result["es_97_5_10d_usd"],
            "multiplier":            _IMA_MULTIPLIER,
            "ima_capital_usd":       round(ima_capital, 2),
            "sa_capital_usd":        round(sa_capital, 2),
            "total_frtb_capital_usd": round(total_capital, 2),
            "regulatory_basis":      "BCBS MAR33 / BCBS 457",
        }


frtb_ima_engine = FRTBIMAEngine()
