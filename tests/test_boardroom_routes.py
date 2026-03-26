"""
Tests for /api/boardroom/* routes.

Covers:
  - GET  /meetings           list with participant_count / date / title transforms
  - GET  /meetings/{id}      transcript found + 404
  - GET  /history            in-memory history snapshot
  - POST /start              creates meeting with defaults or provided values
  - POST /system             broadcasts or skips on empty text
  - POST /inject             broadcasts "[Board asked]: ..." or skips on empty
  - GET  /agents             returns agent registry
  - _auto_title              ≤6 words vs >6 words truncation
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from api.meeting_store import MeetingStore


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def isolated_store(tmp_path):
    """Fresh SQLite store per test — does not share state with the global singleton."""
    s = MeetingStore(db_path=tmp_path / "test_boardroom_routes.db")
    s.initialize()
    return s


@pytest.fixture
def client(monkeypatch, isolated_store):
    """
    TestClient with:
      - ANTHROPIC_API_KEY set (prevents .env load errors)
      - run_live_meeting patched out (no real agent calls)
      - boardroom_routes.meeting_store replaced with isolated_store
    """
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    with (
        patch("api.boardroom_routes.meeting_store", isolated_store),
        patch("api.boardroom_routes.run_live_meeting", new_callable=AsyncMock),
    ):
        from api.main import app
        yield TestClient(app), isolated_store


# ── GET /api/boardroom/meetings ────────────────────────────────────────────────

def test_list_meetings_empty(client):
    c, _ = client
    resp = c.get("/api/boardroom/meetings")
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_meetings_transforms(client):
    """participant_count / date / title fields are injected into each row."""
    c, store = client
    mid = store.create_meeting(
        title="Q1 Review",
        topic="Quarterly review",
        agent_names=["Alice", "Bob"],
    )
    resp = c.get("/api/boardroom/meetings")
    assert resp.status_code == 200
    meetings = resp.json()
    assert len(meetings) == 1
    m = meetings[0]
    assert m["participant_count"] == 2
    assert m["title"] == "Q1 Review"
    assert "date" in m


def test_list_meetings_no_agents_defaults_zero(client):
    c, store = client
    store.create_meeting(title="Empty", topic="t", agent_names=None)
    resp = c.get("/api/boardroom/meetings")
    assert resp.status_code == 200
    meetings = resp.json()
    assert meetings[0]["participant_count"] == 0


# ── GET /api/boardroom/meetings/{id} ──────────────────────────────────────────

def test_get_transcript_found(client):
    c, store = client
    mid = store.create_meeting(title="T", topic="t", agent_names=[])
    resp = c.get(f"/api/boardroom/meetings/{mid}")
    assert resp.status_code == 200
    data = resp.json()
    assert "meeting" in data
    assert "turns" in data
    assert data["meeting"]["id"] == mid


def test_get_transcript_not_found(client):
    c, _ = client
    resp = c.get("/api/boardroom/meetings/nonexistent-id")
    assert resp.status_code == 404


# ── GET /api/boardroom/history ─────────────────────────────────────────────────

def test_get_history_empty(client):
    c, _ = client
    from api.boardroom_broadcaster import broadcaster
    broadcaster._history.clear()
    resp = c.get("/api/boardroom/history")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_history_returns_snapshot(client):
    c, _ = client
    from api.boardroom_broadcaster import broadcaster
    broadcaster._history.clear()
    broadcaster._history.append({"type": "system", "message": "hello"})
    resp = c.get("/api/boardroom/history")
    assert resp.status_code == 200
    items = resp.json()
    assert len(items) == 1
    assert items[0]["message"] == "hello"
    broadcaster._history.clear()


# ── POST /api/boardroom/start ──────────────────────────────────────────────────

def test_start_meeting_defaults(client):
    c, _ = client
    resp = c.post("/api/boardroom/start", json={})
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "started"
    assert "meeting_id" in data
    assert data["topic"] == "Strategic review — open agenda"


def test_start_meeting_custom_values(client):
    c, _ = client
    resp = c.post("/api/boardroom/start", json={
        "topic": "Regulatory capital review",
        "title": "Basel IV",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["title"] == "Basel IV"
    assert data["topic"] == "Regulatory capital review"


def test_start_meeting_no_body(client):
    c, _ = client
    resp = c.post("/api/boardroom/start")
    assert resp.status_code == 200
    assert resp.json()["status"] == "started"


# ── POST /api/boardroom/system ─────────────────────────────────────────────────

def test_system_message_broadcasts(client):
    c, _ = client
    with patch("api.boardroom_routes.broadcaster") as mock_bc:
        mock_bc.broadcast_system = AsyncMock()
        resp = c.post("/api/boardroom/system", json={"text": "Meeting starting"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"
    mock_bc.broadcast_system.assert_called_once_with("Meeting starting")


def test_system_message_empty_skips_broadcast(client):
    c, _ = client
    with patch("api.boardroom_routes.broadcaster") as mock_bc:
        mock_bc.broadcast_system = AsyncMock()
        resp = c.post("/api/boardroom/system", json={"text": ""})
    assert resp.status_code == 200
    mock_bc.broadcast_system.assert_not_called()


# ── POST /api/boardroom/inject ─────────────────────────────────────────────────

def test_inject_broadcasts_formatted(client):
    c, _ = client
    with patch("api.boardroom_routes.broadcaster") as mock_bc:
        mock_bc.broadcast_system = AsyncMock()
        resp = c.post("/api/boardroom/inject", json={"text": "What is our CVA?"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "received"
    call_arg = mock_bc.broadcast_system.call_args[0][0]
    assert "What is our CVA?" in call_arg
    assert "[Board asked]" in call_arg


def test_inject_empty_skips_broadcast(client):
    c, _ = client
    with patch("api.boardroom_routes.broadcaster") as mock_bc:
        mock_bc.broadcast_system = AsyncMock()
        resp = c.post("/api/boardroom/inject", json={"text": "   "})
    assert resp.status_code == 200
    mock_bc.broadcast_system.assert_not_called()


# ── GET /api/boardroom/agents ──────────────────────────────────────────────────

def test_list_agents_returns_registry(client):
    c, _ = client
    resp = c.get("/api/boardroom/agents")
    assert resp.status_code == 200
    agents = resp.json()
    assert len(agents) > 0
    for a in agents:
        assert "name" in a
        assert "title" in a
        assert "color" in a


# ── _auto_title() ─────────────────────────────────────────────────────────────

def test_auto_title_short():
    from api.boardroom_routes import _auto_title
    assert _auto_title("capital review") == "Capital Review"


def test_auto_title_exactly_six_words():
    from api.boardroom_routes import _auto_title
    title = _auto_title("one two three four five six")
    assert "…" not in title
    assert title == "One Two Three Four Five Six"


def test_auto_title_truncates_long():
    from api.boardroom_routes import _auto_title
    title = _auto_title("one two three four five six seven eight")
    assert title.endswith("…")
    # The "…" is appended directly to the 6th word (no space)
    assert "One Two Three Four Five Six…" == title
