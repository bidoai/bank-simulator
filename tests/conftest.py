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
