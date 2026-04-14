"""
Trading WebSocket broadcaster.

Pushes three message types to /ws/trading clients:
  {"type": "fill",      "data": TradeConfirmation dict}
  {"type": "tick",      "prices": {ticker: mid_price}}   (throttled, max 1/2s)
  {"type": "positions", "data": firm_report dict}          (throttled, max 1/2s)
"""
from __future__ import annotations

import time

import structlog

from api.base_broadcaster import BaseBroadcaster

log = structlog.get_logger(__name__)

_TICK_THROTTLE_S = 2.0   # minimum seconds between tick broadcasts


class TradingBroadcaster(BaseBroadcaster):

    def __init__(self) -> None:
        super().__init__("trading")
        self._last_tick: float = 0.0
        self._last_positions: float = 0.0

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
        """Broadcast a full positions update, throttled independently from ticks."""
        now = time.monotonic()
        if now - self._last_positions < _TICK_THROTTLE_S:
            return
        self._last_positions = now
        await self._broadcast({"type": "positions", "data": report})

    # _broadcast and _safe_send are inherited from BaseBroadcaster.


trading_broadcaster = TradingBroadcaster()
