"""
Tests for POST /api/observer/chat

Verifies:
  - 422 on empty question
  - Happy path returns answer/agent/title
  - 502 when the agent raises
  - With meeting_id: context is loaded from MeetingStore
  - With meeting_id but no turns: no crash, still answers
  - With invalid meeting_id: silently skipped, still answers
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient


# ── App fixture ───────────────────────────────────────────────────────────────

@pytest.fixture
def client(tmp_path, monkeypatch):
    """
    Return a TestClient wrapping the full FastAPI app.

    Patches out anthropic.Anthropic and create_observer so no real API
    calls are made. The observer agent's speak() returns a fixed string.
    """
    # Ensure an API key env var is set so the route doesn't try dotenv
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    # Patch anthropic.Anthropic at the source
    mock_anthropic_cls = MagicMock()
    mock_client        = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    # Patch create_observer to return an agent whose speak() is controllable
    mock_agent        = MagicMock()
    mock_agent.speak  = MagicMock(return_value="The Observer's answer.")
    mock_create       = MagicMock(return_value=mock_agent)

    with (
        patch("api.observer_routes.anthropic", create=True),
        patch("anthropic.Anthropic", mock_anthropic_cls),
        patch("agents.narrator.observer.create_observer", mock_create),
    ):
        from api.main import app
        yield TestClient(app), mock_agent


# ── Helpers ───────────────────────────────────────────────────────────────────

def post_chat(tc, **kwargs):
    return tc.post("/api/observer/chat", json=kwargs)


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_empty_question_returns_422(client):
    tc, _ = client
    r = post_chat(tc, question="")
    assert r.status_code == 422


def test_missing_question_key_returns_422(client):
    tc, _ = client
    r = tc.post("/api/observer/chat", json={})
    assert r.status_code == 422


def test_happy_path_returns_answer(client, monkeypatch):
    tc, mock_agent = client
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    mock_agent.speak.return_value = "VaR stands for Value at Risk."

    r = post_chat(tc, question="What is VaR?")
    assert r.status_code == 200
    body = r.json()
    assert body["answer"] == "VaR stands for Value at Risk."
    assert body["agent"]  == "The Observer"
    assert body["title"]  == "Independent Narrator"


def test_agent_speak_receives_question(client, monkeypatch):
    """The question text should appear somewhere in the prompt passed to speak()."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tc, mock_agent = client

    post_chat(tc, question="Explain the yield curve")

    call_args = mock_agent.speak.call_args
    prompt = call_args[0][0]  # first positional arg
    assert "yield curve" in prompt.lower()


def test_502_when_agent_raises(monkeypatch):
    """If speak() raises, the route should return 502, not 500."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")

    mock_agent       = MagicMock()
    mock_agent.speak = MagicMock(side_effect=RuntimeError("API down"))
    mock_create      = MagicMock(return_value=mock_agent)

    with patch("agents.narrator.observer.create_observer", mock_create):
        from api.main import app
        tc = TestClient(app)
        r  = tc.post("/api/observer/chat", json={"question": "What's the VaR?"})
    assert r.status_code == 502


def test_with_valid_meeting_id_loads_context(client, monkeypatch, tmp_path):
    """When a valid meeting_id is provided, context block is prepended."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tc, mock_agent = client

    # Use an isolated store so tests never write to the production DB
    from api.meeting_store import MeetingStore
    test_store = MeetingStore(tmp_path / "test.db")
    test_store.initialize()
    monkeypatch.setattr("api.meeting_store.store", test_store)

    mid = test_store.create_meeting("Test", "test topic", ["Alexandra Chen"])
    test_store.add_turn(mid, "Alexandra Chen", "CEO", "The balance sheet looks fine.", "#e3b341")

    mock_agent.speak.return_value = "Context-aware answer."

    r = post_chat(tc, question="How does the CEO feel?", meeting_id=mid)
    assert r.status_code == 200
    # The prompt passed to speak() should include the turn text
    prompt = mock_agent.speak.call_args[0][0]
    assert "balance sheet" in prompt.lower()


def test_invalid_meeting_id_does_not_crash(client, monkeypatch):
    """An unknown meeting_id should be silently ignored, not raise a 500."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    tc, mock_agent = client
    mock_agent.speak.return_value = "Still answers."

    r = post_chat(tc, question="Tell me something", meeting_id="00000000-0000-0000-0000-000000000000")
    assert r.status_code == 200
    assert r.json()["answer"] == "Still answers."
