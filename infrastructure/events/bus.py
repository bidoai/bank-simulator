"""
In-process Event Bus — asyncio.Queue-backed pub/sub for intraday risk events.

Event types:
  TickEvent         — market data tick (ticker, price, timestamp)
  TradeBookedEvent  — OMS fill (desk, ticker, qty, notional)
  RiskSnapshotEvent — risk service snapshot complete (var_by_desk, limit_summary)
  LimitBreachEvent  — limit breach detected (limit_name, desk, utilisation_pct, status)

Usage:
  from infrastructure.events.bus import event_bus

  # Publish (from MarketDataFeed tick callback or OMS fill)
  await event_bus.publish(TickEvent(ticker="AAPL", price=256.0))

  # Subscribe (start a listener coroutine)
  async for event in event_bus.subscribe("tick"):
      handle(event)

The bus is non-blocking: publish() puts to a bounded queue and returns immediately.
Slow consumers are protected by a per-type queue size limit (1,000 events).
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator

import structlog

log = structlog.get_logger(__name__)

_QUEUE_MAXSIZE = 1_000


# ---------------------------------------------------------------------------
# Event dataclasses
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TickEvent:
    event_type: str = field(default="tick", init=False)
    ticker: str = ""
    price: float = 0.0
    timestamp: str = field(default_factory=_now)


@dataclass
class TradeBookedEvent:
    event_type: str = field(default="trade_booked", init=False)
    desk: str = ""
    book_id: str = ""
    ticker: str = ""
    side: str = ""
    qty: float = 0.0
    notional: float = 0.0
    trade_id: str = ""
    timestamp: str = field(default_factory=_now)


@dataclass
class RiskSnapshotEvent:
    event_type: str = field(default="risk_snapshot", init=False)
    var_by_desk: dict = field(default_factory=dict)
    limit_summary: dict = field(default_factory=dict)
    n_breaches: int = 0
    timestamp: str = field(default_factory=_now)


@dataclass
class LimitBreachEvent:
    event_type: str = field(default="limit_breach", init=False)
    limit_name: str = ""
    desk: str = ""
    utilisation_pct: float = 0.0
    status: str = ""       # "AMBER", "RED"
    var_usd: float = 0.0
    hard_limit_usd: float = 0.0
    timestamp: str = field(default_factory=_now)


AnyEvent = TickEvent | TradeBookedEvent | RiskSnapshotEvent | LimitBreachEvent


# ---------------------------------------------------------------------------
# Event Bus
# ---------------------------------------------------------------------------

class EventBus:
    """
    Lightweight in-process pub/sub.

    One asyncio.Queue per event type. Subscribers call `subscribe(event_type)`
    to get an async generator that yields events as they arrive.
    Multiple subscribers to the same event_type each get their own queue
    (fan-out).
    """

    def __init__(self) -> None:
        # event_type → list of subscriber queues
        self._queues: dict[str, list[asyncio.Queue]] = {}
        self._published: int = 0

    # ------------------------------------------------------------------
    # Publish
    # ------------------------------------------------------------------

    async def publish(self, event: AnyEvent) -> None:
        """Put an event on all subscriber queues for its type."""
        etype = event.event_type
        queues = self._queues.get(etype, [])
        for q in queues:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:
                # Slow consumer — drop oldest to make room
                try:
                    q.get_nowait()
                    q.put_nowait(event)
                except Exception:
                    pass
        self._published += 1
        # Tick events are high-frequency and flood the terminal in dev.
        # Keep debug logs for lower-volume event types only.
        if len(queues) > 0 and etype != "tick":
            log.debug("event_bus.published", event_type=etype, subscribers=len(queues))

    def publish_sync(self, event: AnyEvent) -> None:
        """
        Thread-safe synchronous publish — schedules publish() on the running loop.
        Use from sync callbacks (e.g., MarketDataFeed tick subscriber).
        """
        try:
            loop = asyncio.get_running_loop()
            loop.call_soon_threadsafe(
                loop.create_task,
                self.publish(event),
            )
        except RuntimeError:
            pass  # no running loop (e.g., test context) — silently drop

    # ------------------------------------------------------------------
    # Subscribe
    # ------------------------------------------------------------------

    def subscribe(self, event_type: str) -> "EventBusSubscription":
        """
        Returns an async context manager / iterator.

        Usage:
            async with event_bus.subscribe("tick") as sub:
                async for event in sub:
                    ...
        """
        q: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAXSIZE)
        if event_type not in self._queues:
            self._queues[event_type] = []
        self._queues[event_type].append(q)
        return EventBusSubscription(event_type, q, self)

    def unsubscribe(self, event_type: str, q: asyncio.Queue) -> None:
        if event_type in self._queues:
            try:
                self._queues[event_type].remove(q)
            except ValueError:
                pass

    def stats(self) -> dict:
        return {
            "total_published": self._published,
            "subscriptions": {k: len(v) for k, v in self._queues.items()},
        }


class EventBusSubscription:
    """Async context manager + async iterator for a single bus subscription."""

    def __init__(self, event_type: str, q: asyncio.Queue, bus: EventBus) -> None:
        self._event_type = event_type
        self._q = q
        self._bus = bus

    async def __aenter__(self) -> "EventBusSubscription":
        return self

    async def __aexit__(self, *_: Any) -> None:
        self._bus.unsubscribe(self._event_type, self._q)

    def __aiter__(self) -> AsyncIterator[AnyEvent]:
        return self._iter()

    async def _iter(self) -> AsyncIterator[AnyEvent]:
        while True:
            event = await self._q.get()
            yield event


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

event_bus = EventBus()
