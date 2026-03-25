"""
Trading WebSocket broadcaster.

Pushes three message types to /ws/trading clients:
  {"type": "fill",      "data": TradeConfirmation dict}
  {"type": "tick",      "prices": {ticker: mid_price}}   (throttled, max 1/2s)
  {"type": "positions", "data": firm_report dict}          (throttled, max 1/2s)
"""
from __future__ import annotations

import json
import time
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_TICK_THROTTLE_S = 2.0   # minimum seconds between tick broadcasts


class TradingBroadcaster:

    def __init__(self) -> None:
        self._clients: set = set()
        self._last_tick: float = 0.0

    # ── Connection ─────────────────────────────────────────────────────────────

    async def connect(self, websocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)
        log.info("trading.ws.connected", total=len(self._clients))

    async def disconnect(self, websocket) -> None:
        self._clients.discard(websocket)
        log.info("trading.ws.disconnected", total=len(self._clients))

    # ── Broadcast methods ──────────────────────────────────────────────────────

    async def broadcast_fill(self, confirmation: dict) -> None:
        """Broadcast a trade fill immediately (no throttle)."""
        await self._broadcast({"type": "fill", "data": confirmation})

    async def broadcast_tick(self, prices: dict[str, float]) -> None:
        """Broadcast a price tick, throttled to _TICK_THROTTLE_S."""
        now = time.monotonic()
        if now - self._last_tick < _TICK_THROTTLE_S:
            return
        self._last_tick = now
        await self._broadcast({"type": "tick", "prices": prices})

    async def broadcast_positions(self, report: dict) -> None:
        """Broadcast a full positions update, throttled."""
        now = time.monotonic()
        if now - self._last_tick < _TICK_THROTTLE_S:
            return
        self._last_tick = now
        await self._broadcast({"type": "positions", "data": report})

    # ── Internal ──────────────────────────────────────────────────────────────

    async def _broadcast(self, data: dict[str, Any]) -> None:
        dead: set = set()
        payload = json.dumps(data, default=str)
        for ws in list(self._clients):
            try:
                await ws.send_text(payload)
            except Exception as exc:
                log.debug("trading.ws.dead_client", error=str(exc))
                dead.add(ws)
        self._clients -= dead


trading_broadcaster = TradingBroadcaster()
