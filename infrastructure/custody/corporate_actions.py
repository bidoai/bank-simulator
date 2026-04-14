"""
Corporate Actions Processor — Apex Global Bank.

Pre-seeded with 3 sample corporate actions. Processes DIVIDEND, STOCK_SPLIT,
and SPIN_OFF events against custody holdings.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)


@dataclass
class CorporateAction:
    ca_id:       str
    ca_type:     str          # DIVIDEND | STOCK_SPLIT | SPIN_OFF
    isin:        str
    issuer:      str
    ex_date:     str
    record_date: str
    pay_date:    str
    details:     dict = field(default_factory=dict)
    status:      str = "PENDING"   # PENDING | PROCESSED | CANCELLED


# Pre-seeded corporate actions
_SEED_CAS: list[CorporateAction] = [
    CorporateAction(
        ca_id="CA-001",
        ca_type="DIVIDEND",
        isin="US4592001014",
        issuer="IBM",
        ex_date="2026-03-28",
        record_date="2026-03-29",
        pay_date="2026-04-10",
        details={"dividend_per_share": 1.67, "currency": "USD"},
    ),
    CorporateAction(
        ca_id="CA-002",
        ca_type="STOCK_SPLIT",
        isin="US0231351067",
        issuer="Amazon",
        ex_date="2026-04-01",
        record_date="2026-04-01",
        pay_date="2026-04-01",
        details={"ratio": 20.0, "description": "20-for-1 stock split"},
    ),
    CorporateAction(
        ca_id="CA-003",
        ca_type="DIVIDEND",
        isin="US5949181045",
        issuer="Microsoft",
        ex_date="2026-05-15",
        record_date="2026-05-16",
        pay_date="2026-06-12",
        details={"dividend_per_share": 0.83, "currency": "USD"},
    ),
]


class CorporateActionProcessor:
    def __init__(self) -> None:
        self._actions: list[CorporateAction] = list(_SEED_CAS)

    def get_all_actions(self) -> list[dict[str, Any]]:
        return [_ca_to_dict(ca) for ca in self._actions]

    def get_pending_actions(self) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        return [
            _ca_to_dict(ca) for ca in self._actions
            if ca.status == "PENDING" and ca.pay_date >= today
        ]

    def add_action(
        self,
        ca_type: str,
        isin: str,
        issuer: str,
        ex_date: str,
        record_date: str,
        pay_date: str,
        details: dict,
    ) -> dict[str, Any]:
        if ca_type not in ("DIVIDEND", "STOCK_SPLIT", "SPIN_OFF"):
            raise ValueError("ca_type must be DIVIDEND, STOCK_SPLIT, or SPIN_OFF")
        ca = CorporateAction(
            ca_id=f"CA-{str(uuid.uuid4())[:8].upper()}",
            ca_type=ca_type,
            isin=isin,
            issuer=issuer,
            ex_date=ex_date,
            record_date=record_date,
            pay_date=pay_date,
            details=details,
        )
        self._actions.append(ca)
        log.info("corporate_action.added", ca_id=ca.ca_id, ca_type=ca_type, isin=isin)
        return _ca_to_dict(ca)

    def process(self, ca_id: str) -> dict[str, Any]:
        """Apply a corporate action to all impacted custody holdings."""
        ca = next((c for c in self._actions if c.ca_id == ca_id), None)
        if not ca:
            raise ValueError(f"Corporate action {ca_id!r} not found")
        if ca.status == "PROCESSED":
            raise ValueError(f"Corporate action {ca_id!r} already processed")

        from infrastructure.custody.custody_accounts import custody_book
        result = custody_book.apply_corporate_action({
            "isin":               ca.isin,
            "ca_type":            ca.ca_type,
            "ratio":              ca.details.get("ratio", 2.0),
            "dividend_per_share": ca.details.get("dividend_per_share", 0.0),
        })

        ca.status = "PROCESSED"
        log.info("corporate_action.processed", ca_id=ca_id, ca_type=ca.ca_type,
                 affected=result.get("applied_to", 0))
        return {**_ca_to_dict(ca), "processing_result": result}


def _ca_to_dict(ca: CorporateAction) -> dict[str, Any]:
    return {
        "ca_id":       ca.ca_id,
        "ca_type":     ca.ca_type,
        "isin":        ca.isin,
        "issuer":      ca.issuer,
        "ex_date":     ca.ex_date,
        "record_date": ca.record_date,
        "pay_date":    ca.pay_date,
        "details":     ca.details,
        "status":      ca.status,
    }


corporate_action_processor = CorporateActionProcessor()
