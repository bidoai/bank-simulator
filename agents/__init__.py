from .base_agent import BankAgent

# Executive
from .executive.ceo import create_ceo
from .executive.cto import create_cto
from .executive.cro import create_cro
from .executive.cfo import create_cfo
from .executive.cco_credit import create_chief_credit_officer
from .executive.head_of_treasury import create_head_of_treasury

# Markets
from .markets.lead_trader import create_lead_trader
from .markets.trading_desk import create_trading_desk
from .markets.quant_researcher import create_quant_researcher

# Risk Desk
from .risk_desk.market_risk_officer import create_market_risk_officer
from .risk_desk.credit_risk_officer import create_credit_risk_officer
from .risk_desk.model_risk_officer import create_model_risk_officer
from .risk_desk.liquidity_risk_officer import create_liquidity_risk_officer

# Control
from .compliance.compliance_officer import create_compliance_officer

# Operations
from .operations.head_of_operations import create_head_of_operations

# Technology
from .technology.cdo import create_cdo
from .technology.ciso import create_ciso

# Investment Banking
from .investment_banking.head_of_ibd import create_head_of_ibd

# Wealth Management
from .wealth.head_of_wealth import create_head_of_wealth

# Narrator
from .narrator.observer import create_observer

__all__ = [
    "BankAgent",
    # Executive
    "create_ceo", "create_cto", "create_cro", "create_cfo",
    "create_chief_credit_officer", "create_head_of_treasury",
    # Markets
    "create_lead_trader", "create_trading_desk", "create_quant_researcher",
    # Risk Desk
    "create_market_risk_officer", "create_credit_risk_officer",
    "create_model_risk_officer", "create_liquidity_risk_officer",
    # Control
    "create_compliance_officer",
    # Operations
    "create_head_of_operations",
    # Technology
    "create_cdo", "create_ciso",
    # Investment Banking
    "create_head_of_ibd",
    # Wealth
    "create_head_of_wealth",
    # Narrator
    "create_observer",
]
