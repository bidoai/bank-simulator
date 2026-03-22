"""
Risk metric models — the numbers that keep the bank solvent.

These are the outputs of the risk engine. Regulators (Basel III/IV, Dodd-Frank,
MiFID II) mandate that banks compute and report these daily. If limits are
breached, trading must be reduced or hedged. In extreme cases, positions are
forcibly unwound.

Key concepts:
- VaR (Value at Risk): "With 99% confidence, we won't lose more than $X in a day"
- CVaR (Conditional VaR / Expected Shortfall): Average loss in the worst 1% of cases
- Stress Testing: "What happens to our book in a 2008-style crash?"
- Greeks: Sensitivities that tell you HOW the portfolio will move
"""

from __future__ import annotations
from decimal import Decimal
from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


class VaRResult(BaseModel):
    """
    Value at Risk result.

    VaR is the most widely-used risk measure in banking. Basel III requires
    banks to hold capital equal to a multiple of their VaR (the multiplier
    is set by regulators and increases if backtesting shows model failures).
    """
    book_id: str
    confidence_level: Decimal = Decimal("0.99")   # 99% confidence
    horizon_days: int = 1                           # 1-day VaR
    var_amount: Decimal                              # Dollar loss at confidence level
    cvar_amount: Optional[Decimal] = None           # Expected Shortfall (ES)
    method: str = "historical"                      # historical / parametric / monte_carlo
    computed_at: datetime = Field(default_factory=datetime.utcnow)
    lookback_days: int = 252                        # 1 year of trading days


class StressTestScenario(BaseModel):
    """
    A named stress scenario with its market shocks.

    Banks must run regulatory stress tests (CCAR in the US, EBA in Europe)
    and internal stress tests. Each scenario defines how markets move.
    """
    name: str
    description: str
    equity_shock: Decimal       # e.g. -0.40 = 40% equity market crash
    rates_shock_bps: Decimal    # Basis point shift in interest rates
    fx_shock: Decimal           # FX depreciation vs USD
    vol_shock: Decimal          # Volatility spike multiplier
    credit_spread_shock_bps: Decimal = Decimal("0")
    commodity_shock: Decimal = Decimal("0")


class StressTestResult(BaseModel):
    """P&L impact under a stress scenario."""
    scenario: StressTestScenario
    book_id: str
    pnl_impact: Decimal           # Negative = loss
    delta_impact: Decimal
    gamma_impact: Decimal
    vega_impact: Decimal
    computed_at: datetime = Field(default_factory=datetime.utcnow)


class GreekSummary(BaseModel):
    """Aggregate Greeks for a book — used for hedging decisions."""
    book_id: str
    net_delta: Decimal          # $1 move in underlying → delta * $1 P&L change
    net_gamma: Decimal          # Rate of change of delta
    net_vega: Decimal           # 1% vol move → vega P&L change
    net_theta: Decimal          # P&L decay per day from time value
    net_rho: Decimal            # 1% rate move → rho P&L change
    dv01: Decimal = Decimal("0")  # Dollar value of 1bp move (rates/credit)
    cs01: Decimal = Decimal("0")  # Credit spread sensitivity


class RiskMetrics(BaseModel):
    """
    Consolidated risk snapshot for a book or the entire bank.

    The Risk Management team reviews this every morning. The CRO presents
    a summary to the board weekly. Regulators receive it daily.
    """
    entity_id: str              # book_id, desk_id, or "bank_total"
    as_of_date: date
    computed_at: datetime = Field(default_factory=datetime.utcnow)

    # P&L
    daily_pnl: Decimal
    mtd_pnl: Decimal            # Month-to-date
    ytd_pnl: Decimal            # Year-to-date

    # Market risk
    var_1d_99: Optional[Decimal] = None       # 1-day 99% VaR
    var_10d_99: Optional[Decimal] = None      # 10-day 99% VaR (Basel regulatory)
    expected_shortfall: Optional[Decimal] = None

    # Greeks summary
    greeks: Optional[GreekSummary] = None

    # Concentration
    largest_position_pct: Optional[Decimal] = None  # Largest single position as % of book
    top_5_concentration: Optional[Decimal] = None

    # Limits
    var_limit: Optional[Decimal] = None
    var_utilization_pct: Optional[Decimal] = None  # var / var_limit * 100
    is_limit_breach: bool = False

    # Liquidity
    days_to_liquidate: Optional[Decimal] = None  # How many days to unwind book


# Standard regulatory stress scenarios (based on Basel III FRTB requirements)
STANDARD_STRESS_SCENARIOS = [
    StressTestScenario(
        name="GFC_2008",
        description="2008 Global Financial Crisis replication",
        equity_shock=Decimal("-0.45"),
        rates_shock_bps=Decimal("-150"),   # Flight to quality → rates down
        fx_shock=Decimal("-0.20"),
        vol_shock=Decimal("4.0"),
        credit_spread_shock_bps=Decimal("500"),
        commodity_shock=Decimal("-0.30"),
    ),
    StressTestScenario(
        name="COVID_2020",
        description="COVID-19 March 2020 market shock",
        equity_shock=Decimal("-0.35"),
        rates_shock_bps=Decimal("-100"),
        fx_shock=Decimal("-0.15"),
        vol_shock=Decimal("5.0"),
        commodity_shock=Decimal("-0.65"),
    ),
    StressTestScenario(
        name="RATES_SHOCK_UP",
        description="Sudden 300bp rate rise (inflation shock)",
        equity_shock=Decimal("-0.20"),
        rates_shock_bps=Decimal("300"),
        fx_shock=Decimal("0.10"),
        vol_shock=Decimal("2.0"),
    ),
    StressTestScenario(
        name="GEOPOLITICAL",
        description="Severe geopolitical shock / war escalation",
        equity_shock=Decimal("-0.25"),
        rates_shock_bps=Decimal("-50"),
        fx_shock=Decimal("-0.30"),
        vol_shock=Decimal("3.0"),
        commodity_shock=Decimal("0.80"),
    ),
]
