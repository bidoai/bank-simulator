"""
Limit Action Engine — escalation and desk suspension on limit breaches.

Registers callbacks on every LimitManager limit (lazily, on first use).
When a limit crosses a status threshold the engine takes proportional action:

  YELLOW  → desk head alerted (log + action_log)
  ORANGE  → Head of Trading alerted
  RED     → desk suspended; CRO alerted. OMS gate blocks new orders.
  BREACH  → CEO and Board Risk Committee alerted. Firm-wide review required.

Suspension state is in-memory. Production would persist to an audit DB with
CRO-approval-to-lift workflow; here, the risk officer can lift via API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog

from infrastructure.trading.limit_manager import LimitStatus

log = structlog.get_logger()

# Maps LimitManager limit name → logical OMS desk name (None = firm-wide)
_LIMIT_TO_DESK: dict[str, str | None] = {
    "VAR_FIRM":                None,
    "VAR_EQUITY":              "EQUITY",
    "VAR_RATES":               "RATES",
    "VAR_FX":                  "FX",
    "VAR_CREDIT":              "CREDIT",
    "VAR_DERIV":               "DERIVATIVES",
    "DV01_FIRM":               None,
    "EQUITY_DELTA":            "EQUITY",
    "VEGA_FIRM":               "DERIVATIVES",
    "SINGLE_NAME_EQ_PCT":      "EQUITY",
    "SINGLE_NAME_EQ_NOTIONAL": "EQUITY",
    "SINGLE_ISSUER_CS01":      "CREDIT",
    "COUNTRY_FX":              "FX",
    "STRESS_GFC":              None,
    "STRESS_COVID":            None,
    "STRESS_RATES_UP":         None,
    "NOTIONAL_SECFIN":         "SECURITIES_FINANCE",
    "NOTIONAL_SECURITIZED":    "SECURITIZED",
}

# All trading desks (for firm-wide suspension on None-mapped limits at BREACH)
_ALL_DESKS = {"EQUITY", "RATES", "FX", "CREDIT", "DERIVATIVES",
              "COMMODITIES", "SECURITIES_FINANCE", "SECURITIZED"}

_ESCALATION_MATRIX = {
    LimitStatus.YELLOW: "Desk Head",
    LimitStatus.ORANGE: "Head of Trading",
    LimitStatus.RED:    "CRO",
    LimitStatus.BREACH: "CEO + Board Risk Committee",
}


class LimitActionEngine:
    """
    Enforces escalation actions on limit status changes.
    Registered lazily on first call to avoid circular imports at module load.
    """

    def __init__(self) -> None:
        self._suspended_desks: set[str] = set()
        self._action_log: list[dict[str, Any]] = []
        self._registered = False

    # ── Lazy registration ─────────────────────────────────────────────────────

    def _ensure_registered(self) -> None:
        if self._registered:
            return
        try:
            from infrastructure.risk.risk_service import risk_service
            for name in list(risk_service.limit_manager._limits.keys()):
                risk_service.limit_manager.register_callback(name, self._on_status_change)
            self._registered = True
            log.info("limit_actions.registered", limit_count=len(risk_service.limit_manager._limits))
        except Exception as exc:
            log.warning("limit_actions.registration_failed", error=str(exc))

    # ── Callback ──────────────────────────────────────────────────────────────

    def _on_status_change(self, lim, prev_status, new_status) -> None:
        desk = _LIMIT_TO_DESK.get(lim.name)  # None = firm-wide
        escalation_target = _ESCALATION_MATRIX.get(new_status, "")
        now = datetime.now(timezone.utc).isoformat()

        action = {
            "ts":            now,
            "limit":         lim.name,
            "desk":          desk or "FIRM",
            "prev_status":   prev_status.value,
            "new_status":    new_status.value,
            "utilisation":   round(lim.utilisation_pct, 1),
            "escalated_to":  escalation_target,
            "suspended":     False,
        }

        if new_status == LimitStatus.RED:
            targets = {desk} if desk else _ALL_DESKS
            for d in targets:
                self._suspended_desks.add(d)
            action["suspended"] = True
            action["suspended_desks"] = list(targets)
            log.warning(
                "limit_actions.desk_suspended",
                limit=lim.name,
                desks=list(targets),
                utilisation=lim.utilisation_pct,
            )

        elif new_status == LimitStatus.BREACH:
            # Breach is worse than RED — ensure suspension is in place
            targets = {desk} if desk else _ALL_DESKS
            for d in targets:
                self._suspended_desks.add(d)
            action["suspended"] = True
            action["suspended_desks"] = list(targets)
            log.error(
                "limit_actions.breach_alert",
                limit=lim.name,
                desks=list(targets),
                escalated_to=escalation_target,
            )

        elif new_status in (LimitStatus.GREEN, LimitStatus.YELLOW, LimitStatus.ORANGE):
            # Status improved — auto-lift suspension if returning from RED/BREACH
            if prev_status in (LimitStatus.RED, LimitStatus.BREACH):
                targets = {desk} if desk else _ALL_DESKS
                for d in targets:
                    self._suspended_desks.discard(d)
                action["suspension_lifted"] = True
                log.info(
                    "limit_actions.suspension_auto_lifted",
                    limit=lim.name,
                    desks=list(targets),
                )

        if escalation_target:
            log.info(
                "limit_actions.escalation",
                limit=lim.name,
                desk=desk or "FIRM",
                status=new_status.value,
                escalated_to=escalation_target,
                utilisation=round(lim.utilisation_pct, 1),
            )

        self._action_log.append(action)
        if len(self._action_log) > 500:
            self._action_log = self._action_log[-500:]

    # ── Public API ────────────────────────────────────────────────────────────

    def is_desk_suspended(self, desk: str) -> bool:
        self._ensure_registered()
        return desk in self._suspended_desks

    def get_suspended_desks(self) -> list[str]:
        self._ensure_registered()
        return sorted(self._suspended_desks)

    def lift_suspension(self, desk: str, lifted_by: str = "risk_officer") -> dict[str, Any]:
        """
        Manually lift a desk suspension (CRO / risk officer action).
        In production this would require a 4-eyes approval workflow.
        """
        self._ensure_registered()
        if desk not in self._suspended_desks:
            return {"success": False, "error": f"{desk} is not suspended."}

        self._suspended_desks.discard(desk)
        action = {
            "ts":           datetime.now(timezone.utc).isoformat(),
            "limit":        "MANUAL_LIFT",
            "desk":         desk,
            "prev_status":  "RED",
            "new_status":   "GREEN",
            "utilisation":  None,
            "escalated_to": "",
            "suspended":    False,
            "lifted_by":    lifted_by,
        }
        self._action_log.append(action)
        log.warning("limit_actions.suspension_manually_lifted", desk=desk, lifted_by=lifted_by)
        return {"success": True, "desk": desk, "lifted_by": lifted_by}

    def get_action_log(self, limit: int = 50) -> list[dict[str, Any]]:
        self._ensure_registered()
        return list(reversed(self._action_log))[:limit]

    def get_summary(self) -> dict[str, Any]:
        self._ensure_registered()
        return {
            "suspended_desks":   self.get_suspended_desks(),
            "suspension_count":  len(self._suspended_desks),
            "total_actions":     len(self._action_log),
            "recent_actions":    self.get_action_log(10),
        }


limit_action_engine = LimitActionEngine()
