
import pytest
from fastapi import HTTPException
from infrastructure.trading.oms import oms
from infrastructure.risk.risk_service import risk_service


def test_pre_trade_var_breach(oms_with_feed):
    lim = risk_service.limit_manager.get_limit("VAR_EQUITY")
    original_limit = lim.hard_limit
    lim.hard_limit = 1000.0  # $1k limit — any real trade will breach
    try:
        with pytest.raises(HTTPException) as excinfo:
            oms_with_feed.submit_order(
                desk="EQUITY",
                book_id="EQ_BOOK_TEST",
                ticker="AAPL",
                side="BUY",
                qty=1_000_000,
            )
        assert excinfo.value.status_code == 422
        assert "VaR breach" in excinfo.value.detail
    finally:
        lim.hard_limit = original_limit


def test_pre_trade_delta_breach(oms_with_feed):
    lim = risk_service.limit_manager.get_limit("EQUITY_DELTA")
    original_limit = lim.hard_limit
    lim.hard_limit = 100_000.0  # $100k delta limit
    try:
        # AAPL @ $185 × 1000 shares = $185k delta > $100k limit
        with pytest.raises(HTTPException) as excinfo:
            oms_with_feed.submit_order(
                desk="EQUITY",
                book_id="EQ_BOOK_TEST",
                ticker="AAPL",
                side="BUY",
                qty=1_000,
            )
        assert excinfo.value.status_code == 422
        assert "Equity Delta breach" in excinfo.value.detail
    finally:
        lim.hard_limit = original_limit


def test_pre_trade_dv01_breach(oms_with_feed):
    lim = risk_service.limit_manager.get_limit("DV01_FIRM")
    original_limit = lim.hard_limit
    lim.hard_limit = 10.0  # $10 DV01 limit — any real rates trade will breach
    try:
        with pytest.raises(HTTPException) as excinfo:
            oms_with_feed.submit_order(
                desk="RATES",
                book_id="RATES_BOOK_TEST",
                ticker="US10Y",
                side="BUY",
                qty=1_000,
            )
        assert excinfo.value.status_code == 422
        assert "DV01 breach" in excinfo.value.detail
    finally:
        lim.hard_limit = original_limit


def test_pre_trade_concentration_breach(oms_with_feed):
    lim = risk_service.limit_manager.get_limit("SINGLE_NAME_EQ_PCT")
    original_limit = lim.hard_limit
    lim.hard_limit = 1.0  # 1% single-name limit
    try:
        # Booking a large amount of a single stock should breach %
        with pytest.raises(HTTPException) as excinfo:
            oms_with_feed.submit_order(
                desk="EQUITY",
                book_id="EQ_BOOK_TEST",
                ticker="AAPL",
                side="BUY",
                qty=100_000,
            )
        assert excinfo.value.status_code == 422
        assert "Concentration breach" in excinfo.value.detail
    finally:
        lim.hard_limit = original_limit
