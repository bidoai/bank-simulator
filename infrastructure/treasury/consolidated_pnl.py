"""
Consolidated Income Statement — Apex Global Bank.

Aggregates all revenue streams into a single firm-wide income statement:
  - Net Interest Income (from ALM engine)
  - Trading Revenue (from PositionManager, FTP-adjusted)
  - Fee Revenue (stub — IBD, Wealth, Cards; will be replaced by T3-A live pipelines)
  - Provisions (ECL from IFRS9 engine)
  - Operational Risk Charge (BIA capital charge)

Retained earnings are tracked separately in RetainedEarningsLedger.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Fee revenue stubs (annual, will be replaced by live IBD/Wealth pipelines)
# Consistent with JPMorgan-scale $12B fee income in oprisk_capital._INCOME_STATEMENT
# ---------------------------------------------------------------------------
_FEE_REVENUE_STUBS: dict[str, float] = {
    "investment_banking":   800_000_000.0,   # M&A advisory, ECM, DCM
    "wealth_management":    600_000_000.0,   # AUM fees, advisory
    "card_services":        400_000_000.0,   # interchange, annual fees
    "trade_finance":        350_000_000.0,   # LCs, guarantees
    "custody_fees":         280_000_000.0,   # securities custody
    "agency_services":      220_000_000.0,   # trustee, paying agent
    "fx_commissions":       190_000_000.0,   # client FX execution
    "other_fees":           160_000_000.0,   # miscellaneous
}

# Annual operating expenses — simplified (staff, tech, premises)
_OPERATING_EXPENSES: dict[str, float] = {
    "staff_costs":         18_000_000_000.0,
    "technology":           4_200_000_000.0,
    "premises":             1_800_000_000.0,
    "legal_regulatory":     1_100_000_000.0,
    "other_admin":            900_000_000.0,
}

_ANNUAL_OPEX = sum(_OPERATING_EXPENSES.values())  # ~$26B

# Scaling factor: express annual figures as quarterly or daily
_QUARTERS_PER_YEAR = 4
_DAYS_PER_YEAR = 252


class ConsolidatedIncomeStatement:
    """
    Computes a firm-wide income statement by aggregating all revenue engines.
    All figures returned are on the requested period basis (annual / quarterly / daily).
    """

    def get_statement(self, period: str = "annual") -> dict[str, Any]:
        """
        Build the consolidated income statement.

        period: 'annual' | 'quarterly' | 'daily'
        """
        scale = self._scale(period)

        nii         = self._get_nii() * scale
        trading_pnl = self._get_trading_pnl()          # already current period
        fee_data    = self._get_fee_revenue()
        fee_revenue = fee_data["total"] * scale
        total_revenue = nii + trading_pnl + fee_revenue

        provisions       = self._get_provisions() * scale
        oprisk_charge    = self._get_oprisk_charge() * scale
        operating_expenses = _ANNUAL_OPEX * scale

        pre_tax_income = total_revenue - provisions - oprisk_charge - operating_expenses
        tax_rate = 0.21  # US statutory rate
        taxes = max(0.0, pre_tax_income * tax_rate)
        net_income = pre_tax_income - taxes

        fee_breakdown = {
            "investment_banking_usd": round(fee_data["investment_banking"] * scale, 0),
            "wealth_management_usd":  round(fee_data["wealth_management"] * scale, 0),
            **{k: round(v * scale, 0) for k, v in fee_data["other_stubs"].items()},
        }

        return {
            "period":              period,
            "as_of":               datetime.now(timezone.utc).isoformat(),
            "revenue": {
                "net_interest_income_usd":   round(nii, 0),
                "trading_revenue_usd":       round(trading_pnl, 0),
                "fee_revenue_usd":           round(fee_revenue, 0),
                "fee_revenue_breakdown":     fee_breakdown,
                "total_revenue_usd":         round(total_revenue, 0),
            },
            "expenses": {
                "provisions_ecl_usd":        round(provisions, 0),
                "oprisk_capital_charge_usd": round(oprisk_charge, 0),
                "operating_expenses_usd":    round(operating_expenses, 0),
                "opex_breakdown":            {k: round(v * scale, 0) for k, v in _OPERATING_EXPENSES.items()},
                "total_expenses_usd":        round(provisions + oprisk_charge + operating_expenses, 0),
            },
            "income": {
                "pre_tax_income_usd":        round(pre_tax_income, 0),
                "taxes_usd":                 round(taxes, 0),
                "effective_tax_rate":        tax_rate,
                "net_income_usd":            round(net_income, 0),
            },
            "ratios": {
                "return_on_equity":   round(net_income / 300e9, 4),     # $300B book equity
                "efficiency_ratio":   round(operating_expenses / max(total_revenue, 1), 4),
                "net_interest_margin": round(nii / (2_200e9 * scale) * (1 / scale), 4) if scale > 0 else 0.0,
            },
            "fee_sources": {
                "investment_banking": "live" if fee_data["ibd_live"] else "stub",
                "wealth_management":  "live" if fee_data["wealth_live"] else "stub",
                "other":              "stub",
            },
            "fee_revenue_is_stub": not (fee_data["ibd_live"] or fee_data["wealth_live"]),
        }

    # ── Component getters ────────────────────────────────────────────────────

    def _get_nii(self) -> float:
        """Annual NII from ALM engine balance sheet ($B)."""
        try:
            from infrastructure.treasury.alm import alm_engine
            report = alm_engine.get_balance_sheet()
            return float(report.get("net_interest_income_usd", 56_000_000_000.0))
        except Exception:
            return 56_000_000_000.0  # fallback: ALM static estimate

    def _get_trading_pnl(self) -> float:
        """Current live trading P&L (realised + unrealised) from PositionManager."""
        try:
            from infrastructure.risk.risk_service import risk_service
            firm = risk_service.get_position_report()
            total = sum(
                d.get("total_pnl", 0.0)
                for d in firm.get("by_desk", {}).values()
                if "error" not in d
            )
            return float(total)
        except Exception:
            return 0.0

    def _get_fee_revenue(self) -> dict:
        """
        Annual fee revenue: live IBD (T3-A) + live Wealth (T3-B) + remaining stubs.
        Returns dict with total and per-source breakdown.
        """
        # T3-A: IBD live revenue
        try:
            from infrastructure.ibd.deal_pipeline import deal_pipeline
            ibd_revenue = deal_pipeline.get_annual_fee_revenue()
            ibd_live = True
        except Exception:
            ibd_revenue = _FEE_REVENUE_STUBS["investment_banking"]
            ibd_live = False

        # T3-B: Wealth live revenue
        try:
            from infrastructure.wealth.client_book import client_book
            wealth_revenue = client_book.calculate_annual_fees()
            wealth_live = True
        except Exception:
            wealth_revenue = _FEE_REVENUE_STUBS["wealth_management"]
            wealth_live = False

        other_stubs = {
            k: v for k, v in _FEE_REVENUE_STUBS.items()
            if k not in ("investment_banking", "wealth_management")
        }
        other_total = sum(other_stubs.values())

        return {
            "total": ibd_revenue + wealth_revenue + other_total,
            "investment_banking": ibd_revenue,
            "wealth_management":  wealth_revenue,
            "other_stubs":        other_stubs,
            "ibd_live":           ibd_live,
            "wealth_live":        wealth_live,
        }

    def _get_provisions(self) -> float:
        """Annual ECL provisions from IFRS9 engine."""
        try:
            from infrastructure.credit.ifrs9_ecl import ecl_engine, _sample_portfolio
            portfolio = ecl_engine.portfolio_ecl(_sample_portfolio)
            return float(portfolio.get("total_ecl_usd", 0.0))
        except Exception:
            return 1_500_000_000.0  # fallback: 1.5% of $100B loan book

    def _get_oprisk_charge(self) -> float:
        """Annual op risk BIC (capital charge, not RWA)."""
        try:
            from infrastructure.risk.oprisk_capital import oprisk_engine
            return float(oprisk_engine.calculate_bia()["bic_usd"])
        except Exception:
            return 4_680_000_000.0  # fallback

    @staticmethod
    def _scale(period: str) -> float:
        if period == "quarterly":
            return 1.0 / _QUARTERS_PER_YEAR
        if period == "daily":
            return 1.0 / _DAYS_PER_YEAR
        return 1.0  # annual


income_statement = ConsolidatedIncomeStatement()
