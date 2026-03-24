"""
Tests for MeetingStore — covers all write paths, read paths, and pagination.

Uses a temporary SQLite database so tests are fully isolated and leave no
state behind. No mocking of the Anthropic SDK needed here — MeetingStore
is pure SQLite logic.
"""
import pytest

from api.meeting_store import MeetingStore


@pytest.fixture()
def store(tmp_path):
    """Fresh in-memory store per test."""
    s = MeetingStore(db_path=tmp_path / "test_meetings.db")
    s.initialize()
    return s


# ── create_meeting ─────────────────────────────────────────────────────────────

def test_create_meeting_returns_uuid(store):
    mid = store.create_meeting("Q1 Review", "Capital allocation", ["Alexandra Chen"])
    assert len(mid) == 36  # UUID format


def test_create_meeting_persists(store):
    mid = store.create_meeting("Q1 Review", "Capital allocation", ["Alexandra Chen"])
    meeting = store.get_meeting(mid)
    assert meeting is not None
    assert meeting["title"] == "Q1 Review"
    assert meeting["topic"] == "Capital allocation"
    assert meeting["status"] == "running"
    assert meeting["agent_names"] == ["Alexandra Chen"]
    assert meeting["turn_count"] == 0


def test_create_multiple_meetings(store):
    id1 = store.create_meeting("Meeting A", "Topic A", [])
    id2 = store.create_meeting("Meeting B", "Topic B", [])
    assert id1 != id2
    meetings = store.list_meetings()
    assert len(meetings) == 2


# ── add_turn ───────────────────────────────────────────────────────────────────

def test_add_turn_increments_count(store):
    mid = store.create_meeting("Risk Review", "VaR limits", ["Dr. Priya Nair"])
    store.add_turn(mid, "Dr. Priya Nair", "Chief Risk Officer", "VaR is elevated.", "#f85149")
    meeting = store.get_meeting(mid)
    assert meeting["turn_count"] == 1


def test_add_turn_sequence_order(store):
    mid = store.create_meeting("Strategy", "Q2 plan", ["Alexandra Chen", "Marcus Rivera"])
    store.add_turn(mid, "Alexandra Chen", "CEO", "Let's open.", "#e3b341")
    store.add_turn(mid, "Marcus Rivera", "CTO", "Tech is ready.", "#79c0ff")
    turns = store.get_turns(mid)
    assert len(turns) == 2
    assert turns[0]["agent"] == "Alexandra Chen"
    assert turns[0]["seq"] == 1
    assert turns[1]["agent"] == "Marcus Rivera"
    assert turns[1]["seq"] == 2


def test_add_turn_stores_all_fields(store):
    mid = store.create_meeting("Board", "Rates", [])
    store.add_turn(mid, "James Okafor", "Head of Global Markets", "Rates up 25bp.", "#3fb950")
    turns = store.get_turns(mid)
    t = turns[0]
    assert t["agent"] == "James Okafor"
    assert t["title"] == "Head of Global Markets"
    assert t["text"] == "Rates up 25bp."
    assert t["color"] == "#3fb950"
    assert t["type"] == "agent_turn"


# ── complete_meeting ───────────────────────────────────────────────────────────

def test_complete_meeting_sets_status(store):
    mid = store.create_meeting("Emergency", "Liquidity", [])
    store.complete_meeting(mid, status="completed")
    meeting = store.get_meeting(mid)
    assert meeting["status"] == "completed"
    assert meeting["ended_at"] is not None


def test_complete_meeting_error_status(store):
    mid = store.create_meeting("Failing session", "N/A", [])
    store.complete_meeting(mid, status="error")
    assert store.get_meeting(mid)["status"] == "error"


# ── get_meeting ────────────────────────────────────────────────────────────────

def test_get_meeting_not_found(store):
    assert store.get_meeting("00000000-0000-0000-0000-000000000000") is None


# ── list_meetings ──────────────────────────────────────────────────────────────

def test_list_meetings_ordered_by_start_desc(store):
    store.create_meeting("First", "a", [])
    store.create_meeting("Second", "b", [])
    store.create_meeting("Third", "c", [])
    meetings = store.list_meetings(limit=10)
    titles = [m["title"] for m in meetings]
    # Most recent first — SQLite insert order gives ascending, so Third is last inserted
    assert titles[0] == "Third"


def test_list_meetings_limit(store):
    for i in range(5):
        store.create_meeting(f"M{i}", f"t{i}", [])
    assert len(store.list_meetings(limit=3)) == 3


# ── get_turns pagination ───────────────────────────────────────────────────────

def test_get_turns_pagination_basic(store):
    mid = store.create_meeting("Long session", "Many speakers", [])
    for i in range(10):
        store.add_turn(mid, "Alexandra Chen", "CEO", f"Point {i+1}.", "#e3b341")

    page1 = store.get_turns(mid, limit=4, after_seq=0)
    assert len(page1) == 4
    assert page1[0]["seq"] == 1
    assert page1[-1]["seq"] == 4

    page2 = store.get_turns(mid, limit=4, after_seq=page1[-1]["seq"])
    assert len(page2) == 4
    assert page2[0]["seq"] == 5

    page3 = store.get_turns(mid, limit=4, after_seq=page2[-1]["seq"])
    assert len(page3) == 2  # only 2 remaining


def test_get_turns_default_limit(store):
    mid = store.create_meeting("Session", "Topic", [])
    for i in range(5):
        store.add_turn(mid, "The Observer", "Narrator", f"Observation {i}.", "#8b949e")
    turns = store.get_turns(mid)
    assert len(turns) == 5


def test_get_turns_empty_meeting(store):
    mid = store.create_meeting("Empty", "Nothing yet", [])
    assert store.get_turns(mid) == []


# ── isolation: each write uses its own connection ─────────────────────────────

def test_concurrent_writes_do_not_corrupt(store):
    """
    Simulate rapid sequential writes (the pattern from the orchestrator) and
    verify all turns land correctly.
    """
    mid = store.create_meeting("Rapid", "Sequential writes", [])
    agents = ["Alexandra Chen", "Dr. Priya Nair", "Marcus Rivera"]
    for a in agents:
        store.add_turn(mid, a, "Title", f"{a} spoke.", "#ffffff")

    turns = store.get_turns(mid)
    assert len(turns) == 3
    assert store.get_meeting(mid)["turn_count"] == 3
