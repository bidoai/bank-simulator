"""
Intraday Risk Cycle — subscribes to TickEvents and re-runs RiskService
every 15 seconds (not on every tick). Publishes RiskSnapshotEvents and
LimitBreachEvents back onto the bus.

Keeps a rolling timeline of the last 60 snapshots (~15 minutes of history)
for the GET /api/risk/intraday-timeline endpoint.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone

import structlog

from infrastructure.events.bus import event_bus, TickEvent, RiskSnapshotEvent, LimitBreachEvent

log = structlog.get_logger(__name__)

_CYCLE_SECONDS = 15          # risk re-compute interval
_TIMELINE_SIZE = 60          # max snapshots in the rolling window


class IntradayRiskCycle:
    """
    Background asyncio task that periodically refreshes risk and publishes events.

    Flow:
      tick → (ignored individually, just marks price dirty)
      every 15s → run_snapshot() → publish RiskSnapshotEvent
      if any limit AMBER/RED → publish LimitBreachEvent per breach
    """

    def __init__(self) -> None:
        self._timeline: deque[dict] = deque(maxlen=_TIMELINE_SIZE)
        self._running = False
        self._task: asyncio.Task | None = None
        self._last_tick_ts: str | None = None
        self._cycle_count = 0

    def start(self) -> None:
        """Start the background cycle task. Call from lifespan."""
        if self._running:
            return
        self._running = True
        self._task = asyncio.ensure_future(self._cycle_loop())
        log.info("intraday_cycle.started", interval_s=_CYCLE_SECONDS)

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        log.info("intraday_cycle.stopped")

    async def _cycle_loop(self) -> None:
        # Subscribe to ticks so we can record last-tick timestamp
        async with event_bus.subscribe("tick") as tick_sub:
            tick_queue = tick_sub._q  # direct queue access for non-blocking drain

            while self._running:
                # Wait one cycle period, draining ticks in the background
                try:
                    await asyncio.wait_for(self._drain_ticks(tick_queue), timeout=_CYCLE_SECONDS)
                except asyncio.TimeoutError:
                    pass  # expected — we use timeout as our cycle clock

                if not self._running:
                    break

                await self._run_and_publish()

    async def _drain_ticks(self, q: asyncio.Queue) -> None:
        """Consume tick events, recording the last seen timestamp."""
        while True:
            event: TickEvent = await q.get()
            self._last_tick_ts = event.timestamp

    async def _run_and_publish(self) -> None:
        """Run risk snapshot and publish results onto the bus."""
        try:
            from infrastructure.risk.risk_service import risk_service
            snap = await asyncio.get_event_loop().run_in_executor(
                None, risk_service.run_snapshot
            )

            limit_report = snap.get("limits", {}).get("limits", [])
            breaches = [l for l in limit_report if l.get("status") in ("AMBER", "RED")]

            # Build timeline entry
            entry = {
                "timestamp":      datetime.now(timezone.utc).isoformat(),
                "cycle":          self._cycle_count,
                "var_by_desk":    {
                    d: round(v.get("var_amount", 0) / 1e6, 3)
                    for d, v in snap.get("var_by_desk", {}).items()
                },
                "firm_var_mm":    round(snap.get("firm_var", {}).get("var_amount", 0) / 1e6, 3),
                "n_breaches":     len(breaches),
                "last_tick_ts":   self._last_tick_ts,
            }
            self._timeline.append(entry)
            self._cycle_count += 1

            # Publish snapshot event
            await event_bus.publish(RiskSnapshotEvent(
                var_by_desk   = entry["var_by_desk"],
                limit_summary = snap.get("limits", {}),
                n_breaches    = len(breaches),
            ))

            # Publish individual breach events
            for b in breaches:
                await event_bus.publish(LimitBreachEvent(
                    limit_name      = b.get("name", ""),
                    desk            = b.get("desk", ""),
                    utilisation_pct = b.get("utilisation_pct", 0),
                    status          = b.get("status", ""),
                    var_usd         = b.get("current_value", 0),
                    hard_limit_usd  = b.get("hard_limit", 0),
                ))

            log.debug("intraday_cycle.snapshot",
                      cycle=self._cycle_count,
                      firm_var_mm=entry["firm_var_mm"],
                      breaches=len(breaches))

        except Exception as exc:
            log.warning("intraday_cycle.snapshot_failed", error=str(exc))

    def get_timeline(self) -> list[dict]:
        """Return most recent snapshots, newest first."""
        return list(reversed(self._timeline))

    def stats(self) -> dict:
        return {
            "running":        self._running,
            "cycle_count":    self._cycle_count,
            "timeline_size":  len(self._timeline),
            "last_tick_ts":   self._last_tick_ts,
            "interval_s":     _CYCLE_SECONDS,
        }


# Module-level singleton
intraday_cycle = IntradayRiskCycle()
