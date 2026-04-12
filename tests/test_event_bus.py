"""Tests for the in-process event bus."""
from __future__ import annotations

import asyncio
import pytest

from infrastructure.events.bus import (
    EventBus,
    TickEvent,
    TradeBookedEvent,
    RiskSnapshotEvent,
    LimitBreachEvent,
)

# ---------------------------------------------------------------------------
# Basic publish / subscribe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_delivers_to_subscriber():
    bus = EventBus()
    received = []

    async def consume():
        async with bus.subscribe("tick") as sub:
            async for event in sub:
                received.append(event)
                break  # take one and stop

    task = asyncio.create_task(consume())
    await asyncio.sleep(0)  # let consumer register
    await bus.publish(TickEvent(ticker="AAPL", price=256.0))
    await asyncio.wait_for(task, timeout=1.0)

    assert len(received) == 1
    assert received[0].ticker == "AAPL"
    assert received[0].price == 256.0


@pytest.mark.asyncio
async def test_publish_fan_out_to_multiple_subscribers():
    bus = EventBus()
    received_a: list = []
    received_b: list = []

    async def consume(store):
        async with bus.subscribe("tick") as sub:
            async for event in sub:
                store.append(event)
                break

    task_a = asyncio.create_task(consume(received_a))
    task_b = asyncio.create_task(consume(received_b))
    await asyncio.sleep(0)
    await bus.publish(TickEvent(ticker="MSFT", price=400.0))
    await asyncio.gather(
        asyncio.wait_for(task_a, timeout=1.0),
        asyncio.wait_for(task_b, timeout=1.0),
    )

    assert len(received_a) == 1
    assert len(received_b) == 1
    assert received_a[0].ticker == "MSFT"
    assert received_b[0].ticker == "MSFT"


@pytest.mark.asyncio
async def test_event_types_are_isolated():
    """Tick subscriber should not receive TradeBooked events."""
    bus = EventBus()
    tick_received = []
    trade_received = []

    async def consume_tick():
        async with bus.subscribe("tick") as sub:
            async for event in sub:
                tick_received.append(event)
                break

    async def consume_trade():
        async with bus.subscribe("trade_booked") as sub:
            async for event in sub:
                trade_received.append(event)
                break

    t1 = asyncio.create_task(consume_tick())
    t2 = asyncio.create_task(consume_trade())
    await asyncio.sleep(0)

    await bus.publish(TradeBookedEvent(desk="EQUITY", ticker="AAPL"))
    await bus.publish(TickEvent(ticker="AAPL", price=256.0))

    await asyncio.wait_for(t1, timeout=1.0)
    await asyncio.wait_for(t2, timeout=1.0)

    assert len(tick_received) == 1
    assert isinstance(tick_received[0], TickEvent)
    assert len(trade_received) == 1
    assert isinstance(trade_received[0], TradeBookedEvent)


# ---------------------------------------------------------------------------
# Event dataclass fields
# ---------------------------------------------------------------------------

def test_tick_event_fields():
    e = TickEvent(ticker="AAPL", price=256.0)
    assert e.event_type == "tick"
    assert e.ticker == "AAPL"
    assert e.price == 256.0
    assert e.timestamp  # non-empty ISO string


def test_trade_booked_event_fields():
    e = TradeBookedEvent(desk="EQUITY", ticker="AAPL", qty=1000, notional=256_000)
    assert e.event_type == "trade_booked"
    assert e.desk == "EQUITY"


def test_risk_snapshot_event_fields():
    e = RiskSnapshotEvent(var_by_desk={"EQUITY": 1.2}, n_breaches=0)
    assert e.event_type == "risk_snapshot"
    assert e.var_by_desk["EQUITY"] == 1.2


def test_limit_breach_event_fields():
    e = LimitBreachEvent(limit_name="VAR_EQUITY", desk="EQUITY", status="RED", utilisation_pct=110.0)
    assert e.event_type == "limit_breach"
    assert e.status == "RED"


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stats_tracks_published():
    bus = EventBus()
    assert bus.stats()["total_published"] == 0
    await bus.publish(TickEvent(ticker="X", price=1.0))
    assert bus.stats()["total_published"] == 1


@pytest.mark.asyncio
async def test_stats_tracks_subscriptions():
    bus = EventBus()

    async def consume():
        async with bus.subscribe("tick") as sub:
            async for _ in sub:
                break

    t = asyncio.create_task(consume())
    await asyncio.sleep(0)
    stats = bus.stats()
    assert stats["subscriptions"].get("tick", 0) >= 1
    await bus.publish(TickEvent(ticker="Y", price=2.0))
    await asyncio.wait_for(t, timeout=1.0)


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unsubscribe_removes_queue():
    bus = EventBus()
    received = []

    async def consume():
        async with bus.subscribe("tick") as sub:
            # context manager exit triggers unsubscribe
            pass

    await consume()
    # After context exit, publishing should not deliver to the (now removed) subscriber
    await bus.publish(TickEvent(ticker="Z", price=3.0))
    await asyncio.sleep(0)
    assert len(received) == 0  # nothing subscribed anymore
    assert bus.stats()["subscriptions"].get("tick", 0) == 0


# ---------------------------------------------------------------------------
# No-subscriber publish is safe
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_publish_with_no_subscribers_is_safe():
    bus = EventBus()
    # Should not raise even with no subscribers
    await bus.publish(TickEvent(ticker="NVDA", price=178.0))
    assert bus.stats()["total_published"] == 1
