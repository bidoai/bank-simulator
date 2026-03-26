"""
RiskPositionReader — Second-Line Independent Position View (3LoD CQRS).

This reader rebuilds position state exclusively from TradeBooked events in the
EventLog. It does NOT read from PositionManager directly, ensuring second-line
independence: the risk function reconstructs positions from the same audit trail
the event sourcing system maintains, not from the same in-memory store the trading
desk uses.

Used only for the independence-check endpoint. Not called on every snapshot
(O(n) over all TradeBooked events is too expensive at high trade volume).
"""

from __future__ import annotations

from infrastructure.events.event_log import event_log
import structlog

log = structlog.get_logger(__name__)


class RiskPositionReader:
    """Rebuilds firm-wide positions from EventLog TradeBooked events only."""

    def rebuild(self) -> dict[str, dict[str, float]]:
        """
        Replay all TradeBooked events.

        Returns:
            {desk: {instrument: net_qty}}
        """
        events = event_log.get_recent(limit=100_000, event_type="TradeBooked")
        positions: dict[str, dict[str, float]] = {}

        for evt in reversed(events):  # get_recent returns DESC; replay in ASC order
            payload = evt.get("payload", {})
            desk = payload.get("desk", "UNKNOWN")
            instrument = payload.get("instrument", "UNKNOWN")
            qty = float(payload.get("qty", 0))

            if desk not in positions:
                positions[desk] = {}
            positions[desk][instrument] = positions[desk].get(instrument, 0.0) + qty

        log.info("risk_position_reader.rebuild", event_count=len(events))
        return positions

    def total_notional(self) -> float:
        """
        Sum absolute notional across all positions.
        Uses last_price from EventLog payload as a price proxy (trade price).
        """
        events = event_log.get_recent(limit=100_000, event_type="TradeBooked")
        qty_price: dict[tuple[str, str], list[float]] = {}

        for evt in reversed(events):
            payload = evt.get("payload", {})
            desk = payload.get("desk", "UNKNOWN")
            instrument = payload.get("instrument", "UNKNOWN")
            qty = float(payload.get("qty", 0))
            price = float(payload.get("price", 0))
            key = (desk, instrument)
            if key not in qty_price:
                qty_price[key] = [0.0, price]
            qty_price[key][0] += qty
            qty_price[key][1] = price  # latest trade price as proxy

        total = sum(abs(net_qty) * price for (net_qty, price) in qty_price.values())
        return round(total, 2)
