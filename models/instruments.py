"""
Financial instrument definitions.

Instruments are the securities and contracts the bank trades. Every trade references
an instrument. Think of this as the bank's universe of tradeable assets — equities,
fixed income, FX, derivatives, and commodities.
"""

from __future__ import annotations
from enum import Enum
from decimal import Decimal
from datetime import date
from typing import Optional
from pydantic import BaseModel, Field


class AssetClass(str, Enum):
    EQUITY = "equity"
    FIXED_INCOME = "fixed_income"
    FX = "fx"
    COMMODITY = "commodity"
    CREDIT = "credit"
    RATES = "rates"
    STRUCTURED = "structured"


class InstrumentType(str, Enum):
    # Cash
    STOCK = "stock"
    BOND = "bond"
    ETF = "etf"
    FX_SPOT = "fx_spot"
    # Derivatives
    EQUITY_OPTION = "equity_option"
    INTEREST_RATE_SWAP = "interest_rate_swap"
    CREDIT_DEFAULT_SWAP = "credit_default_swap"
    FX_FORWARD = "fx_forward"
    FX_OPTION = "fx_option"
    FUTURE = "future"
    # Structured
    CDO = "cdo"
    CLO = "clo"
    MBS = "mbs"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


class Instrument(BaseModel):
    """
    Represents a tradeable financial instrument.

    In a real bank (think Bloomberg terminal), every instrument has a unique
    identifier (ISIN, CUSIP, FIGI) and a rich set of static data that drives
    pricing, risk calculations, and regulatory reporting.
    """
    isin: Optional[str] = None          # International Securities ID
    cusip: Optional[str] = None         # US identifier
    ticker: str                          # Exchange ticker / short name
    description: str
    asset_class: AssetClass
    instrument_type: InstrumentType
    currency: str = "USD"
    exchange: Optional[str] = None
    country: str = "US"

    # Fixed income specific
    maturity_date: Optional[date] = None
    coupon_rate: Optional[Decimal] = None  # e.g. 0.05 = 5%
    face_value: Optional[Decimal] = None

    # Option specific
    option_type: Optional[OptionType] = None
    strike: Optional[Decimal] = None
    underlying_ticker: Optional[str] = None
    expiry_date: Optional[date] = None

    # Risk parameters (pre-computed or updated daily)
    point_value: Decimal = Decimal("1")   # Contract multiplier
    lot_size: Decimal = Decimal("1")      # Minimum tradeable unit

    class Config:
        frozen = True


# A small universe of instruments for the simulator
INSTRUMENT_UNIVERSE: dict[str, Instrument] = {
    "AAPL": Instrument(
        isin="US0378331005", cusip="037833100", ticker="AAPL",
        description="Apple Inc", asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.STOCK, exchange="NASDAQ",
    ),
    "MSFT": Instrument(
        isin="US5949181045", cusip="594918104", ticker="MSFT",
        description="Microsoft Corp", asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.STOCK, exchange="NASDAQ",
    ),
    "SPY": Instrument(
        isin="US78462F1030", ticker="SPY",
        description="SPDR S&P 500 ETF", asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.ETF, exchange="NYSE",
    ),
    "US10Y": Instrument(
        ticker="US10Y",
        description="US Treasury 10-Year Note",
        asset_class=AssetClass.FIXED_INCOME,
        instrument_type=InstrumentType.BOND,
        currency="USD",
        maturity_date=date(2034, 2, 15),
        coupon_rate=Decimal("0.0425"),
        face_value=Decimal("1000"),
    ),
    "EURUSD": Instrument(
        ticker="EURUSD",
        description="Euro / US Dollar",
        asset_class=AssetClass.FX,
        instrument_type=InstrumentType.FX_SPOT,
        currency="USD",
    ),
    "GBPUSD": Instrument(
        ticker="GBPUSD",
        description="British Pound / US Dollar",
        asset_class=AssetClass.FX,
        instrument_type=InstrumentType.FX_SPOT,
        currency="USD",
    ),
    "AAPL_CALL_200": Instrument(
        ticker="AAPL_CALL_200",
        description="AAPL Call Option Strike 200",
        asset_class=AssetClass.EQUITY,
        instrument_type=InstrumentType.EQUITY_OPTION,
        option_type=OptionType.CALL,
        strike=Decimal("200"),
        underlying_ticker="AAPL",
        expiry_date=date(2025, 6, 20),
        point_value=Decimal("100"),  # 1 contract = 100 shares
    ),
    "USD_IRS_5Y": Instrument(
        ticker="USD_IRS_5Y",
        description="USD Interest Rate Swap 5-Year",
        asset_class=AssetClass.RATES,
        instrument_type=InstrumentType.INTEREST_RATE_SWAP,
        currency="USD",
        maturity_date=date(2030, 3, 1),
    ),
    "CRUDE_OIL": Instrument(
        ticker="CL1",
        description="WTI Crude Oil Front Month Future",
        asset_class=AssetClass.COMMODITY,
        instrument_type=InstrumentType.FUTURE,
        exchange="NYMEX",
        point_value=Decimal("1000"),  # 1000 barrels per contract
    ),
}
