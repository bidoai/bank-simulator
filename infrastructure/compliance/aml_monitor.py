"""AML Transaction Monitor — rule-based screening engine."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional
import uuid

import structlog

log = structlog.get_logger(__name__)


class AlertSeverity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class AlertType(Enum):
    LARGE_TRANSACTION = "large_transaction"
    RAPID_MOVEMENT = "rapid_movement"
    STRUCTURING = "structuring"
    SANCTIONS_MATCH = "sanctions_match"
    UNUSUAL_PATTERN = "unusual_pattern"
    ROUND_NUMBER = "round_number"


class AMLAlert:
    def __init__(
        self,
        alert_type: AlertType,
        severity: AlertSeverity,
        counterparty: str,
        amount_usd: float,
        description: str,
    ) -> None:
        self.alert_id = str(uuid.uuid4())
        self.alert_type = alert_type
        self.severity = severity
        self.counterparty = counterparty
        self.amount_usd = amount_usd
        self.description = description
        self.triggered_at = datetime.now(timezone.utc).isoformat()
        self.status = "open"

    def to_dict(self) -> dict:
        return {
            "alert_id": self.alert_id,
            "alert_type": self.alert_type.value,
            "severity": self.severity.value,
            "counterparty": self.counterparty,
            "amount_usd": self.amount_usd,
            "description": self.description,
            "triggered_at": self.triggered_at,
            "status": self.status,
        }


class AMLTransactionMonitor:
    LARGE_TX_THRESHOLD_USD = 10_000_000
    CTR_THRESHOLD_USD = 10_000
    STRUCTURING_WINDOW_HOURS = 24
    STRUCTURING_COUNT = 3
    VELOCITY_LIMIT_1H = 5
    ROUND_NUMBER_TOLERANCE = 0.001

    SANCTIONS_WATCHLIST = [
        "Volkov Trading Ltd",
        "Eastern Phoenix Capital",
        "Meridian Shell Holdings",
        "Northwest Commodity Group",
        "Atlas Financial Services BVI",
    ]

    def __init__(self) -> None:
        self._alerts: list[AMLAlert] = []
        # In-memory tx log: counterparty -> list of (timestamp, amount)
        self._tx_log: dict[str, list[tuple[datetime, float]]] = defaultdict(list)

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _is_round_number(self, amount: float) -> bool:
        if amount <= 0:
            return False
        for magnitude in [1_000_000, 500_000, 100_000, 50_000, 10_000]:
            if magnitude < amount * 0.01:
                continue
            ratio = amount / magnitude
            nearest = round(ratio)
            if nearest > 0 and abs(ratio - nearest) / nearest < self.ROUND_NUMBER_TOLERANCE:
                return True
        return False

    def _check_structuring(self, counterparty: str, ts: datetime) -> bool:
        window_start = ts - timedelta(hours=self.STRUCTURING_WINDOW_HOURS)
        recent = [
            amt for t, amt in self._tx_log[counterparty]
            if t >= window_start
            and self.CTR_THRESHOLD_USD * 0.70 <= amt < self.CTR_THRESHOLD_USD
        ]
        return len(recent) >= self.STRUCTURING_COUNT

    def _check_velocity(self, counterparty: str, ts: datetime) -> bool:
        window_start = ts - timedelta(hours=1)
        recent = [t for t, _ in self._tx_log[counterparty] if t >= window_start]
        return len(recent) >= self.VELOCITY_LIMIT_1H

    def screen_transaction(
        self,
        tx_id: str,
        counterparty: str,
        amount_usd: float,
        tx_type: str,
        timestamp: Optional[str] = None,
    ) -> list[AMLAlert]:
        ts = datetime.fromisoformat(timestamp) if timestamp else self._now()
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)

        alerts: list[AMLAlert] = []

        # Sanctions check (highest priority)
        for name in self.SANCTIONS_WATCHLIST:
            if name.lower() in counterparty.lower() or counterparty.lower() in name.lower():
                alert = AMLAlert(
                    alert_type=AlertType.SANCTIONS_MATCH,
                    severity=AlertSeverity.CRITICAL,
                    counterparty=counterparty,
                    amount_usd=amount_usd,
                    description=f"Counterparty '{counterparty}' matches sanctions watchlist entry '{name}'.",
                )
                alerts.append(alert)
                self._alerts.append(alert)
                log.warning("aml.sanctions_match", counterparty=counterparty, tx_id=tx_id)
                break

        # Large transaction
        if amount_usd >= self.LARGE_TX_THRESHOLD_USD:
            severity = AlertSeverity.HIGH if amount_usd < 50_000_000 else AlertSeverity.CRITICAL
            alert = AMLAlert(
                alert_type=AlertType.LARGE_TRANSACTION,
                severity=severity,
                counterparty=counterparty,
                amount_usd=amount_usd,
                description=(
                    f"Single transaction of ${amount_usd:,.0f} exceeds large-tx threshold "
                    f"(${self.LARGE_TX_THRESHOLD_USD:,.0f})."
                ),
            )
            alerts.append(alert)
            self._alerts.append(alert)

        # Round number detection
        if amount_usd >= self.CTR_THRESHOLD_USD and self._is_round_number(amount_usd):
            alert = AMLAlert(
                alert_type=AlertType.ROUND_NUMBER,
                severity=AlertSeverity.LOW,
                counterparty=counterparty,
                amount_usd=amount_usd,
                description=f"Transaction amount ${amount_usd:,.0f} is suspiciously round.",
            )
            alerts.append(alert)
            self._alerts.append(alert)

        # Record transaction before velocity/structuring checks
        self._tx_log[counterparty].append((ts, amount_usd))

        # Velocity check
        if self._check_velocity(counterparty, ts):
            alert = AMLAlert(
                alert_type=AlertType.RAPID_MOVEMENT,
                severity=AlertSeverity.MEDIUM,
                counterparty=counterparty,
                amount_usd=amount_usd,
                description=(
                    f"Counterparty '{counterparty}' exceeded {self.VELOCITY_LIMIT_1H} "
                    "transactions in a 1-hour window."
                ),
            )
            alerts.append(alert)
            self._alerts.append(alert)

        # Structuring check
        if self._check_structuring(counterparty, ts):
            alert = AMLAlert(
                alert_type=AlertType.STRUCTURING,
                severity=AlertSeverity.HIGH,
                counterparty=counterparty,
                amount_usd=amount_usd,
                description=(
                    f"Potential structuring: {self.STRUCTURING_COUNT}+ transactions "
                    f"between 70%-100% of CTR threshold (${self.CTR_THRESHOLD_USD:,.0f}) "
                    f"in {self.STRUCTURING_WINDOW_HOURS}h window."
                ),
            )
            alerts.append(alert)
            self._alerts.append(alert)

        log.info("aml.transaction_screened",
                 tx_id=tx_id, counterparty=counterparty,
                 amount_usd=amount_usd, alerts_raised=len(alerts))
        return alerts

    def get_open_alerts(self) -> list[dict]:
        return [a.to_dict() for a in self._alerts if a.status == "open"]

    def get_alert_stats(self) -> dict:
        open_alerts = [a for a in self._alerts if a.status == "open"]
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)

        by_severity: dict[str, int] = {"critical": 0, "high": 0, "medium": 0, "low": 0}
        by_type: dict[str, int] = {}
        escalated_today = 0

        for a in open_alerts:
            by_severity[a.severity.value] = by_severity.get(a.severity.value, 0) + 1
            by_type[a.alert_type.value] = by_type.get(a.alert_type.value, 0) + 1

        for a in self._alerts:
            if a.status == "escalated":
                ts = datetime.fromisoformat(a.triggered_at)
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                if ts >= today_start:
                    escalated_today += 1

        return {
            "total_open": len(open_alerts),
            "by_severity": by_severity,
            "by_type": by_type,
            "escalated_today": escalated_today,
        }

    def update_alert_status(self, alert_id: str, status: str) -> bool:
        for a in self._alerts:
            if a.alert_id == alert_id:
                a.status = status
                log.info("aml.alert_status_updated", alert_id=alert_id, status=status)
                return True
        return False

    def generate_sample_alerts(self) -> None:
        samples = [
            ("wire", "Meridian Shell Holdings", 25_000_000, "2026-03-24T09:15:00+00:00"),
            ("wire", "Pinnacle Global Trade LLC", 18_500_000, "2026-03-24T11:30:00+00:00"),
            ("payment", "Sunrise Commodity Exports", 9_800, "2026-03-24T14:00:00+00:00"),
            ("payment", "Sunrise Commodity Exports", 9_750, "2026-03-24T14:45:00+00:00"),
            ("payment", "Sunrise Commodity Exports", 9_900, "2026-03-24T15:30:00+00:00"),
            ("fx", "Blue Ridge Holdings Corp", 50_000_000, "2026-03-25T08:00:00+00:00"),
        ]
        for tx_type, counterparty, amount, ts in samples:
            self.screen_transaction(
                tx_id=str(uuid.uuid4()),
                counterparty=counterparty,
                amount_usd=amount,
                tx_type=tx_type,
                timestamp=ts,
            )
        log.info("aml.sample_alerts_generated", total_alerts=len(self._alerts))


aml_monitor = AMLTransactionMonitor()
aml_monitor.generate_sample_alerts()
