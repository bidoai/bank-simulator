"""
DFAST/CCAR 9-Quarter Stress Engine.

Implements a simplified Fed DFAST-style 9-quarter forward capital adequacy
projection under three macroeconomic scenarios: baseline, adverse, and severely
adverse. Consistent with 12 CFR 252.54 stress testing framework (educational
demonstration — not for regulatory submission).

Imports from risk and treasury layers are done lazily (inside run_scenario) to
avoid import-order issues at startup.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional
import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Scenario definitions
# Populated from official 2025 Fed DFAST parameters + live FRED macro data.
# Hardcoded fallback is used if the fetch fails at startup.
# ---------------------------------------------------------------------------

_SCENARIOS_FALLBACK: dict[str, dict] = {
    "baseline": {
        "gdp": +0.022,
        "ur_delta": 0.0,
        "eq_shock": +0.03,
        "rate_bps": -30,
        "equity_shock_pct": +0.03,
    },
    "adverse": {
        "gdp": -0.008,
        "ur_delta": 2.5,
        "eq_shock": -0.15,
        "rate_bps": -280,
        "equity_shock_pct": -0.15,
    },
    "severely_adverse": {
        "gdp": -0.036,
        "ur_delta": 6.0,
        "eq_shock": -0.55,
        "rate_bps": -350,
        "equity_shock_pct": -0.55,
    },
}


def _load_official_scenarios() -> dict[str, dict]:
    """
    Load official 2025 Fed DFAST scenarios calibrated to live macro.
    Falls back to hardcoded parameters on any failure.
    """
    try:
        from infrastructure.market_data.dfast_scenarios import build_scenarios
        scenarios = build_scenarios()
        log.info("dfast.scenarios_loaded", source="DFAST 2025 Official / FRED")
        return scenarios
    except Exception as exc:
        log.warning("dfast.scenarios_fallback", error=str(exc))
        return _SCENARIOS_FALLBACK


SCENARIOS: dict[str, dict] = _load_official_scenarios()


@dataclass
class QuarterResult:
    quarter: int                    # 1-9
    cet1_ratio: float               # Common Equity Tier 1 ratio
    cet1_amount: float              # CET1 capital ($M)
    ppni: float                     # Pre-provision net income ($M)
    credit_losses: float            # Credit losses / ECL migration ($M)
    trading_losses: float           # Trading book losses ($M)
    rwa: float                      # Risk-weighted assets ($M)

    def to_dict(self) -> dict:
        return {
            "quarter": self.quarter,
            "cet1_ratio": round(self.cet1_ratio * 100, 2),   # as %
            "cet1_amount": round(self.cet1_amount, 1),
            "ppni": round(self.ppni, 1),
            "credit_losses": round(self.credit_losses, 1),
            "trading_losses": round(self.trading_losses, 1),
            "rwa": round(self.rwa, 1),
        }


@dataclass
class DFASTResult:
    scenario: str
    quarters: list[QuarterResult]
    min_cet1_ratio: float           # minimum CET1 across the 9 quarters
    breach_minimum: bool            # True if CET1 < 4.5% (Basel III floor)

    def to_dict(self) -> dict:
        return {
            "scenario": self.scenario,
            "min_cet1_ratio": round(self.min_cet1_ratio * 100, 2),
            "breach_minimum": self.breach_minimum,
            "quarters": [q.to_dict() for q in self.quarters],
        }


class DFASTEngine:
    """
    9-quarter capital adequacy projection engine.

    Starting balance sheet assumptions (demo scale, $M):
        CET1 capital:        $2,500M
        Risk-weighted assets: $18,000M
        Initial CET1 ratio:   13.9%
        Loan portfolio:       $12,000M
        Trading book:         $3,500M
        Net interest income:  $180M/quarter
        Non-interest income:  $45M/quarter
        Operating expenses:   $120M/quarter
    """

    # Demo balance sheet ($M)
    _CET1_INITIAL: float = 2_500.0
    _RWA_INITIAL: float = 18_000.0
    _LOAN_PORTFOLIO: float = 12_000.0
    _TRADING_BOOK: float = 3_500.0
    _NII_QUARTERLY: float = 180.0
    _NONII_QUARTERLY: float = 45.0
    _OPEX_QUARTERLY: float = 120.0

    # Basel III minimum CET1 ratio
    _MINIMUM_CET1: float = 0.045

    def run_scenario(self, scenario: str, quarters: int = 9) -> DFASTResult:
        """
        Run a 9-quarter forward projection under the given scenario.

        Income model (per quarter):
            NII:     baseline NII scaled by rate_bps / 400 (25bps ≈ 1/4 year → +1/4 of annual rate adj)
            Trading: trading revenue = -abs(eq_shock) × trading_book / 4 per quarter
            Fees:    flat non-interest income
            Opex:    flat operating expenses

        Loss model (per quarter):
            Credit losses: ECL migration — PDs scale with ur_delta per IFRS9 ECL model
                           ECL_q = loan_portfolio × base_ecl_rate × (1 + ur_delta × 0.06) / 4
            Trading losses: stressed VaR × 10 scaling factor / 4 per quarter

        Capital model (per quarter):
            CET1_t = CET1_{t-1} + PPNI_t - CreditLoss_t - TradingLoss_t
            RWA growth: +0.5% per quarter in baseline, flat in adverse, -1% in severely adverse
            CET1_ratio = CET1_t / RWA_t
        """
        if scenario not in SCENARIOS:
            raise ValueError(f"Unknown scenario: {scenario}. Must be one of {list(SCENARIOS)}")

        params = SCENARIOS[scenario]
        gdp = params["gdp"]
        ur_delta = params["ur_delta"]
        eq_shock = params["eq_shock"]
        rate_bps = params["rate_bps"]

        # Lazy imports to avoid startup import-order issues
        try:
            from infrastructure.risk.risk_service import risk_service
            pm_report = risk_service.get_position_report()
            trading_book = pm_report.get("gross_notional", self._TRADING_BOOK) / 1e6
        except Exception:
            trading_book = self._TRADING_BOOK

        try:
            from infrastructure.treasury.alm import alm_engine
            nii_base = alm_engine.get_quarterly_nii() / 1e6
        except Exception:
            nii_base = self._NII_QUARTERLY

        # RWA growth per quarter by scenario
        rwa_growth_q: float
        if scenario == "baseline":
            rwa_growth_q = 0.005   # +0.5%/q
        elif scenario == "adverse":
            rwa_growth_q = 0.0
        else:
            rwa_growth_q = -0.01   # -1%/q

        # Base ECL coverage rate — normal conditions
        base_ecl_rate = 0.018

        cet1 = self._CET1_INITIAL
        rwa = self._RWA_INITIAL
        quarter_results: list[QuarterResult] = []

        for q in range(1, quarters + 1):
            # --- Income ---
            nii_adj = nii_base * (1 + rate_bps / 10_000 * q / 4)
            trading_rev = -abs(eq_shock) * trading_book / 4 if eq_shock != 0 else 0.0
            ppni = nii_adj + self._NONII_QUARTERLY + trading_rev - self._OPEX_QUARTERLY

            # --- Credit losses (IFRS 9 macro overlay: ur_delta → PD scaling) ---
            pd_scalar = 1.0 + ur_delta * 0.06  # β_UR = 0.06 per IFRS9 MDD
            ecl_annual_rate = base_ecl_rate * pd_scalar
            credit_losses = self._LOAN_PORTFOLIO * ecl_annual_rate / 4

            # --- Trading losses (stressed VaR × 10 haircut, amortised quarterly) ---
            # Rough stressed VaR: 1% of trading book; 10-day 99% multiplied by 10-day factor
            stressed_var = trading_book * abs(eq_shock if eq_shock != 0 else 0.05) * 0.10
            trading_losses = stressed_var / 4

            # --- Capital ---
            cet1 = cet1 + ppni - credit_losses - trading_losses
            rwa = rwa * (1 + rwa_growth_q)
            cet1_ratio = cet1 / rwa if rwa > 0 else 0.0

            quarter_results.append(QuarterResult(
                quarter=q,
                cet1_ratio=cet1_ratio,
                cet1_amount=cet1,
                ppni=ppni,
                credit_losses=credit_losses,
                trading_losses=trading_losses,
                rwa=rwa,
            ))

        min_cet1 = min(r.cet1_ratio for r in quarter_results)
        log.info(
            "dfast.run_scenario",
            scenario=scenario,
            quarters=quarters,
            min_cet1_ratio=round(min_cet1 * 100, 2),
        )

        return DFASTResult(
            scenario=scenario,
            quarters=quarter_results,
            min_cet1_ratio=min_cet1,
            breach_minimum=min_cet1 < self._MINIMUM_CET1,
        )

    def run_all_scenarios(self, quarters: int = 9) -> dict[str, DFASTResult]:
        """Run all three scenarios and return results dict."""
        return {
            name: self.run_scenario(name, quarters)
            for name in SCENARIOS
        }


# Module-level singleton
dfast_engine = DFASTEngine()
