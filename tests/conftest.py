"""
Shared test fixtures for bank-simulator.

Provides a MockAnthropicClient that never hits the real API — it returns
configurable canned responses so tests run instantly and deterministically.
"""
from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import MagicMock, patch

import pytest


# ── Mock Anthropic primitives ──────────────────────────────────────────────────

class MockTextBlock:
    """Minimal stand-in for anthropic.types.TextBlock."""
    type = "text"

    def __init__(self, text: str):
        self.text = text


class MockUsage:
    output_tokens = 42
    input_tokens  = 10


class MockMessage:
    """Minimal stand-in for a completed Anthropic API response."""

    def __init__(self, text: str = "Mock response"):
        self.content = [MockTextBlock(text)]
        self.usage   = MockUsage()


class MockAnthropicClient:
    """
    Drop-in replacement for anthropic.Anthropic().

    Configuration kwargs (all optional):
        response_text  (str)  — text returned by .messages.create()
        fail_n         (int)  — raise APIError on the first N calls
        error_class    (type) — exception class to raise (default: Exception)
    """

    def __init__(
        self,
        response_text: str = "Mock response",
        fail_n: int = 0,
        error_class: type = Exception,
    ):
        self._response_text = response_text
        self._fail_n        = fail_n
        self._error_class   = error_class
        self._call_count    = 0
        self.messages       = self  # client.messages.create(...)

    def create(self, **kwargs) -> MockMessage:
        self._call_count += 1
        if self._call_count <= self._fail_n:
            raise self._error_class(f"Mock API failure #{self._call_count}")
        return MockMessage(self._response_text)


@pytest.fixture(autouse=True)
def reset_observer_singleton():
    """Reset observer module singleton before/after each test for isolation."""
    try:
        import api.observer_routes as _obs
        _obs._observer = None
    except Exception:
        pass
    yield
    try:
        import api.observer_routes as _obs
        _obs._observer = None
    except Exception:
        pass


@pytest.fixture
def mock_client() -> MockAnthropicClient:
    """A MockAnthropicClient that always succeeds."""
    return MockAnthropicClient()


@pytest.fixture
def failing_client() -> MockAnthropicClient:
    """A MockAnthropicClient that fails every call."""
    return MockAnthropicClient(fail_n=999)


# ── Mock Market Data Feed ─────────────────────────────────────────────────────

class MockQuote:
    """Minimal stand-in for a market data Quote."""
    def __init__(self, ticker: str, price: float):
        self.ticker = ticker
        self.bid = price * 0.9999
        self.ask = price * 1.0001
        self.mid = price


class MockFeed:
    """
    Stand-in MarketDataFeed for OMS tests — returns fixed prices so tests
    don't need a running GBM feed or Yahoo Finance connectivity.
    """
    _PRICES: dict[str, float] = {
        "AAPL": 185.0, "MSFT": 370.0, "GOOGL": 175.0, "NVDA": 850.0,
        "US10Y": 95.0, "US2Y": 97.0, "EURUSD": 1.08, "GBPUSD": 1.27,
        "IG_CDX": 100.0, "HYEM_ETF": 75.0, "IRS_USD_10Y": 100.0,
        "SPX_CALL_5200": 50.0, "SPY": 520.0, "CL1": 80.0,
    }

    def get_quote(self, ticker: str):
        price = self._PRICES.get(ticker)
        return MockQuote(ticker, price) if price is not None else None

    def get_all_quotes(self) -> dict:
        return {t: MockQuote(t, p) for t, p in self._PRICES.items()}


@pytest.fixture
def oms_with_feed():
    """OMS singleton with a mock feed injected. Restores original feed after test."""
    from infrastructure.trading.oms import oms
    original_feed = oms._feed
    oms.set_feed(MockFeed())
    yield oms
    oms._feed = original_feed
