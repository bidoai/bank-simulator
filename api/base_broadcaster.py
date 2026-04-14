"""
Base WebSocket broadcaster.

Provides the shared connection management and broadcast mechanics used by
BoardroomBroadcaster and TradingBroadcaster.
"""
from __future__ import annotations

import json
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class BaseBroadcaster:
    """
    Manages a set of live WebSocket clients and provides reliable broadcast.

    Subclasses add domain-specific message helpers on top of this foundation.
    """

    def __init__(self, name: str) -> None:
        self._name = name
        self._clients: set = set()

    # ── Connection management ─────────────────────────────────────────────────

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        log.info(f"{self._name}.ws.connected", total=len(self._clients))

    async def disconnect(self, websocket) -> None:
        self._clients.discard(websocket)
        log.info(f"{self._name}.ws.disconnected", total=len(self._clients))

    # ── Internal broadcast ────────────────────────────────────────────────────

    async def _broadcast(self, data: dict[str, Any]) -> None:
        """Send a message to every connected client; prune dead ones."""
        dead: set = set()
        payload = json.dumps(data, default=str)
        for ws in list(self._clients):
            if not await self._safe_send(ws, payload):
                dead.add(ws)
        self._clients -= dead

    async def _safe_send(self, ws, payload: str) -> bool:
        """Send pre-serialised JSON to one client. Returns False if the client is dead."""
        try:
            await ws.send_text(payload)
            return True
        except Exception as exc:
            log.debug(f"{self._name}.ws.dead_client", error=str(exc))
            self._clients.discard(ws)
            return False
