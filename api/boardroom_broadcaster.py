"""
Boardroom WebSocket broadcaster.
Streams agent conversation turns to all connected browser clients.

Each agent turn is broadcast in real time: turn_start signals the agent
is about to speak, token messages stream partial text, turn_end finalises
the message, and agent_turn carries the complete text for clients that
joined late (served from history on connect).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

import structlog

from api.base_broadcaster import BaseBroadcaster

log = structlog.get_logger(__name__)

_MAX_HISTORY = 200


def _agent_color(name: str, fallback: str = "#c9d1d9") -> str:
    """Look up agent color from the single source of truth: _AGENT_REGISTRY."""
    from api.meeting_orchestrator import _AGENT_REGISTRY
    return _AGENT_REGISTRY.get(name, {}).get("color", fallback)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BoardroomBroadcaster(BaseBroadcaster):
    """
    Singleton broadcaster for the boardroom WebSocket stream.

    Extends BaseBroadcaster with rolling message history (replayed to late
    joiners) and agent-turn helpers. All history writes are guarded by an
    asyncio.Lock.
    """

    def __init__(self) -> None:
        super().__init__("boardroom")
        self.clients = self._clients   # public alias for legacy callers
        self._history: list[dict] = []
        self._lock = asyncio.Lock()

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, websocket) -> None:
        """Accept a new WebSocket connection and replay history."""
        await websocket.accept()

        # Snapshot and send history BEFORE adding to the live broadcast set.
        # This ensures the client sees history in order, with no live messages
        # interleaved before the replay completes.
        async with self._lock:
            history_snapshot = list(self._history)

        await self._safe_send(websocket, json.dumps({
            "type": "history",
            "messages": history_snapshot,
        }, default=str))

        self._clients.add(websocket)
        log.info("boardroom.ws.connected", total=len(self._clients))

    async def disconnect(self, websocket) -> None:
        """Remove a client from the active set."""
        self._clients.discard(websocket)
        log.info("boardroom.ws.disconnected", total=len(self._clients))

    # ── Broadcast helpers ─────────────────────────────────────────────────────

    async def broadcast_agent_turn(
        self,
        agent_name: str,
        agent_title: str,
        text: str,
        color: str = "#c9d1d9",
    ) -> None:
        """
        Broadcast a complete, finalised agent message.
        Also appended to history so late joiners receive it.
        """
        color = color or _agent_color(agent_name)
        message: dict[str, Any] = {
            "type":      "agent_turn",
            "agent":     agent_name,
            "title":     agent_title,
            "text":      text,
            "color":     color,
            "timestamp": _now_iso(),
        }
        async with self._lock:
            self._history.append(message)
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]

        await self._broadcast(message)

    async def broadcast_token(
        self,
        agent_name: str,
        token: str,
        color: str = "#c9d1d9",
    ) -> None:
        """Stream a single text token to all clients (not stored in history)."""
        color = color or _agent_color(agent_name)
        await self._broadcast({
            "type":  "token",
            "agent": agent_name,
            "token": token,
            "color": color,
        })

    async def broadcast_turn_start(
        self,
        agent_name: str,
        agent_title: str,
        color: str = "#c9d1d9",
    ) -> None:
        """Signal that an agent is about to speak (shows typing indicator)."""
        color = color or _agent_color(agent_name)
        await self._broadcast({
            "type":  "turn_start",
            "agent": agent_name,
            "title": agent_title,
            "color": color,
        })

    async def broadcast_turn_end(self, agent_name: str) -> None:
        """Signal that an agent has finished speaking."""
        await self._broadcast({
            "type":  "turn_end",
            "agent": agent_name,
        })

    async def broadcast_system(self, message: str) -> None:
        """Broadcast a system-level status message."""
        msg: dict[str, Any] = {
            "type":      "system",
            "message":   message,
            "timestamp": _now_iso(),
        }
        async with self._lock:
            self._history.append(msg)
            if len(self._history) > _MAX_HISTORY:
                self._history = self._history[-_MAX_HISTORY:]

        await self._broadcast(msg)

    # _broadcast and _safe_send are inherited from BaseBroadcaster.


# ── Module-level singleton ────────────────────────────────────────────────────
broadcaster = BoardroomBroadcaster()
