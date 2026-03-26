"""
Tests for BoardroomBroadcaster — covers connection management, history cap,
color resolution from the agent registry, and dead client pruning.

No real WebSocket connections are used: we pass a lightweight mock that
captures sent messages and can be configured to fail.
"""
import asyncio
import json
import pytest

from api.boardroom_broadcaster import BoardroomBroadcaster, _MAX_HISTORY, _agent_color


# ── Mock WebSocket ─────────────────────────────────────────────────────────────

class MockWebSocket:
    def __init__(self, fail_after: int = 0):
        """
        fail_after=0 → always succeed.
        fail_after=N → succeed for the first N sends, then raise.
        """
        self.accepted = False
        self.sent: list[dict] = []
        self._send_count = 0
        self._fail_after = fail_after

    async def accept(self):
        self.accepted = True

    async def send_text(self, text: str):
        self._send_count += 1
        if self._fail_after and self._send_count > self._fail_after:
            raise RuntimeError("connection closed")
        self.sent.append(json.loads(text))


# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def broadcaster():
    return BoardroomBroadcaster()


# ── connect / disconnect ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_connect_accepts_websocket(broadcaster):
    ws = MockWebSocket()
    await broadcaster.connect(ws)
    assert ws.accepted
    assert ws in broadcaster.clients


@pytest.mark.asyncio
async def test_connect_sends_history(broadcaster):
    # Pre-populate history
    broadcaster._history = [{"type": "agent_turn", "agent": "Alexandra Chen", "text": "Hi"}]
    ws = MockWebSocket()
    await broadcaster.connect(ws)
    # First message should be the history replay
    assert ws.sent[0]["type"] == "history"
    assert len(ws.sent[0]["messages"]) == 1


@pytest.mark.asyncio
async def test_disconnect_removes_client(broadcaster):
    ws = MockWebSocket()
    await broadcaster.connect(ws)
    await broadcaster.disconnect(ws)
    assert ws not in broadcaster.clients


# ── broadcast_agent_turn ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_agent_turn_stored_in_history(broadcaster):
    ws = MockWebSocket()
    await broadcaster.connect(ws)
    await broadcaster.broadcast_agent_turn("Alexandra Chen", "CEO", "Hello board.")
    assert any(m["type"] == "agent_turn" for m in broadcaster._history)


@pytest.mark.asyncio
async def test_broadcast_agent_turn_sent_to_client(broadcaster):
    ws = MockWebSocket()
    await broadcaster.connect(ws)
    await broadcaster.broadcast_agent_turn("Marcus Rivera", "CTO", "Tech update.")
    # ws.sent[0] is the history replay on connect; ws.sent[1] is the new message
    agent_turns = [m for m in ws.sent if m.get("type") == "agent_turn"]
    assert len(agent_turns) == 1
    assert agent_turns[0]["agent"] == "Marcus Rivera"
    assert agent_turns[0]["text"] == "Tech update."


# ── history cap ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_history_capped_at_max(broadcaster):
    for i in range(_MAX_HISTORY + 10):
        await broadcaster.broadcast_agent_turn("Alexandra Chen", "CEO", f"Turn {i}")
    assert len(broadcaster._history) == _MAX_HISTORY


# ── dead client pruning ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_dead_client_pruned_on_broadcast(broadcaster):
    good = MockWebSocket()
    # fail_after=1: succeeds on connect history send, then fails on next broadcast
    dead = MockWebSocket(fail_after=1)
    await broadcaster.connect(good)
    await broadcaster.connect(dead)
    assert len(broadcaster.clients) == 2  # both connected, history send succeeded

    # This broadcast will fail for dead — it should be pruned
    await broadcaster.broadcast_system("test message")
    assert dead not in broadcaster.clients
    assert good in broadcaster.clients


# ── broadcast_token ───────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_token_not_stored_in_history(broadcaster):
    await broadcaster.broadcast_token("Dr. Yuki Tanaka", "delta is 0.42")
    token_msgs = [m for m in broadcaster._history if m.get("type") == "token"]
    assert token_msgs == []  # tokens are ephemeral, not stored


# ── broadcast_system ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_broadcast_system_stored_in_history(broadcaster):
    await broadcaster.broadcast_system("Meeting started")
    assert broadcaster._history[-1]["type"] == "system"
    assert broadcaster._history[-1]["message"] == "Meeting started"


# ── _agent_color ──────────────────────────────────────────────────────────────

def test_agent_color_known_agent():
    # Alexandra Chen is the CEO — should have the gold color
    color = _agent_color("Alexandra Chen")
    assert color == "#e3b341"


def test_agent_color_unknown_agent():
    color = _agent_color("Unknown Person")
    assert color == "#c9d1d9"  # default fallback


def test_agent_color_custom_fallback():
    color = _agent_color("Nobody", fallback="#ff0000")
    assert color == "#ff0000"


def test_agent_color_all_registry_agents():
    """Every agent in the registry must resolve a non-empty color."""
    from api.meeting_orchestrator import _AGENT_REGISTRY
    for name in _AGENT_REGISTRY:
        c = _agent_color(name)
        assert c.startswith("#"), f"{name} resolved to non-hex color: {c!r}"
        assert len(c) == 7, f"{name} has invalid color length: {c!r}"
