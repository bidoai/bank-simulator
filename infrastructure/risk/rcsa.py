"""
Risk and Control Self-Assessment (RCSA) Framework.

In-memory risk/control register aligned to Basel III operational risk
categories (CRE20 business lines). Each control has an inherent risk score,
effectiveness rating, and derived residual risk score.

Used by Internal Audit and Operational Risk teams to evidence 3LoD oversight.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import structlog

log = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Risk ratings: 1 (low) → 5 (critical)
# ---------------------------------------------------------------------------
RISK_LABELS = {1: "Low", 2: "Low-Medium", 3: "Medium", 4: "High", 5: "Critical"}
EFFECTIVENESS_LABELS = {1: "Ineffective", 2: "Needs Improvement", 3: "Adequate", 4: "Effective", 5: "Strong"}


@dataclass
class RiskControl:
    control_id:            str
    business_line:         str
    risk_category:         str        # maps to Basel CRE20 event type
    control_description:   str
    control_type:          str        # PREVENTIVE | DETECTIVE | CORRECTIVE
    inherent_risk_score:   int        # 1–5
    control_effectiveness: int        # 1–5  (higher = more effective)
    owner:                 str
    last_assessed:         str        # ISO date
    notes:                 str = ""

    @property
    def residual_risk_score(self) -> float:
        """residual = inherent × (1 - effectiveness/5)"""
        return round(self.inherent_risk_score * (1.0 - self.control_effectiveness / 5.0), 2)

    @property
    def residual_risk_label(self) -> str:
        r = self.residual_risk_score
        if r < 1.0:  return "Low"
        if r < 2.0:  return "Low-Medium"
        if r < 3.0:  return "Medium"
        if r < 4.0:  return "High"
        return "Critical"

    def to_dict(self) -> dict[str, Any]:
        return {
            "control_id":            self.control_id,
            "business_line":         self.business_line,
            "risk_category":         self.risk_category,
            "control_description":   self.control_description,
            "control_type":          self.control_type,
            "inherent_risk_score":   self.inherent_risk_score,
            "inherent_risk_label":   RISK_LABELS.get(self.inherent_risk_score, "?"),
            "control_effectiveness": self.control_effectiveness,
            "effectiveness_label":   EFFECTIVENESS_LABELS.get(self.control_effectiveness, "?"),
            "residual_risk_score":   self.residual_risk_score,
            "residual_risk_label":   self.residual_risk_label,
            "control_type_str":      self.control_type,
            "owner":                 self.owner,
            "last_assessed":         self.last_assessed,
            "notes":                 self.notes,
        }


# ---------------------------------------------------------------------------
# Seed controls — 18 controls across 6 business lines
# ---------------------------------------------------------------------------

_SEED_CONTROLS: list[RiskControl] = [
    # ── Trading & Sales ──────────────────────────────────────────────────────
    RiskControl("RC-TS-001", "TRADING_AND_SALES", "EXECUTION_DELIVERY",
                "Pre-trade VaR and limit checks enforced in OMS before order submission",
                "PREVENTIVE", 4, 5, "Head of Market Risk", "2026-01-15"),
    RiskControl("RC-TS-002", "TRADING_AND_SALES", "INTERNAL_FRAUD",
                "Four-eyes approval for trades >$100M notional",
                "PREVENTIVE", 4, 4, "Head of Global Markets", "2026-01-15"),
    RiskControl("RC-TS-003", "TRADING_AND_SALES", "EXECUTION_DELIVERY",
                "EOD position reconciliation between front-office and risk systems",
                "DETECTIVE", 3, 4, "Head of Operations", "2026-02-01"),
    RiskControl("RC-TS-004", "TRADING_AND_SALES", "CLIENTS_PRODUCTS",
                "MiFID II suitability assessment for structured product clients",
                "PREVENTIVE", 3, 3, "Chief Compliance Officer", "2026-01-20"),

    # ── Payment & Settlement ─────────────────────────────────────────────────
    RiskControl("RC-PS-001", "PAYMENT_AND_SETTLEMENT", "EXECUTION_DELIVERY",
                "Dual-authorisation for SWIFT payments >$10M",
                "PREVENTIVE", 4, 5, "Head of Operations", "2026-01-10"),
    RiskControl("RC-PS-002", "PAYMENT_AND_SETTLEMENT", "EXTERNAL_FRAUD",
                "Real-time SWIFT anomaly detection and callback verification",
                "DETECTIVE", 5, 4, "Chief Information Security Officer", "2026-02-05"),
    RiskControl("RC-PS-003", "PAYMENT_AND_SETTLEMENT", "BUSINESS_DISRUPTION",
                "Hot-standby payment processing infrastructure with <15min RTO",
                "CORRECTIVE", 4, 4, "Chief Technology Officer", "2026-01-25"),

    # ── Retail Banking ───────────────────────────────────────────────────────
    RiskControl("RC-RB-001", "RETAIL_BANKING", "EXTERNAL_FRAUD",
                "Card transaction fraud scoring model (ML-based, 99.2% precision)",
                "DETECTIVE", 4, 4, "Head of Retail Banking", "2026-01-30"),
    RiskControl("RC-RB-002", "RETAIL_BANKING", "EXTERNAL_FRAUD",
                "Identity verification at account opening (biometric + document check)",
                "PREVENTIVE", 3, 4, "Chief Compliance Officer", "2026-02-10"),
    RiskControl("RC-RB-003", "RETAIL_BANKING", "EMPLOYMENT_PRACTICES",
                "Annual mandatory HR policy training and attestation",
                "PREVENTIVE", 2, 4, "Chief Human Resources Officer", "2026-01-05"),

    # ── Commercial Banking ───────────────────────────────────────────────────
    RiskControl("RC-CB-001", "COMMERCIAL_BANKING", "CLIENTS_PRODUCTS",
                "Product suitability review by independent credit committee for structured loans",
                "PREVENTIVE", 4, 3, "Chief Credit Officer", "2026-02-15"),
    RiskControl("RC-CB-002", "COMMERCIAL_BANKING", "EXECUTION_DELIVERY",
                "Loan documentation checklist and legal sign-off before drawdown",
                "PREVENTIVE", 3, 4, "General Counsel", "2026-01-18"),

    # ── Asset Management ─────────────────────────────────────────────────────
    RiskControl("RC-AM-001", "ASSET_MANAGEMENT", "EXECUTION_DELIVERY",
                "Order management system with auto-allocation controls and audit trail",
                "PREVENTIVE", 3, 4, "Head of Asset Management", "2026-02-08"),
    RiskControl("RC-AM-002", "ASSET_MANAGEMENT", "CLIENTS_PRODUCTS",
                "Independent pricing and NAV verification by fund administrator",
                "DETECTIVE", 3, 5, "Head of Model Validation", "2026-01-22"),

    # ── Corporate Finance ────────────────────────────────────────────────────
    RiskControl("RC-CF-001", "CORPORATE_FINANCE", "CLIENTS_PRODUCTS",
                "Conflicts committee review for all M&A mandates with potential information barriers",
                "PREVENTIVE", 4, 3, "General Counsel", "2026-02-20"),
    RiskControl("RC-CF-002", "CORPORATE_FINANCE", "INTERNAL_FRAUD",
                "Chinese wall enforcement — automated wall-crossing log and approval workflow",
                "PREVENTIVE", 4, 4, "Chief Compliance Officer", "2026-01-28"),

    # ── Agency Services ──────────────────────────────────────────────────────
    RiskControl("RC-AS-001", "AGENCY_SERVICES", "EXECUTION_DELIVERY",
                "Corporate actions processing checklist with T-5 deadline monitoring",
                "PREVENTIVE", 3, 3, "Head of Custody Operations", "2026-02-12"),
    RiskControl("RC-AS-002", "AGENCY_SERVICES", "EXECUTION_DELIVERY",
                "Settlement fail monitoring dashboard with automatic escalation at T+2",
                "DETECTIVE", 3, 4, "Head of Custody Operations", "2026-02-12"),
]


class RCSAFramework:
    """In-memory Risk and Control Self-Assessment register."""

    def __init__(self) -> None:
        self._controls: dict[str, RiskControl] = {c.control_id: c for c in _SEED_CONTROLS}

    def get_controls(self, business_line: str | None = None) -> list[dict[str, Any]]:
        controls = list(self._controls.values())
        if business_line:
            controls = [c for c in controls if c.business_line == business_line]
        return [c.to_dict() for c in sorted(controls, key=lambda c: c.control_id)]

    def get_control(self, control_id: str) -> dict[str, Any] | None:
        c = self._controls.get(control_id)
        return c.to_dict() if c else None

    def update_effectiveness(self, control_id: str, effectiveness: int, notes: str = "") -> dict[str, Any]:
        """Update a control's effectiveness score (1–5). Returns updated control."""
        if control_id not in self._controls:
            raise KeyError(f"Control {control_id!r} not found")
        if not 1 <= effectiveness <= 5:
            raise ValueError("effectiveness must be 1–5")
        c = self._controls[control_id]
        c.control_effectiveness = effectiveness
        c.last_assessed = datetime.now(timezone.utc).date().isoformat()
        if notes:
            c.notes = notes
        log.info("rcsa.effectiveness_updated", control_id=control_id, effectiveness=effectiveness)
        return c.to_dict()

    def get_heat_map(self) -> dict[str, Any]:
        """
        Return a heat-map view: residual risk distribution by business line.
        Each cell = avg residual risk score (1–5).
        """
        lines: dict[str, list[float]] = {}
        for c in self._controls.values():
            lines.setdefault(c.business_line, []).append(c.residual_risk_score)

        heat_map = {
            bl: {
                "avg_residual_risk":  round(sum(scores) / len(scores), 2),
                "max_residual_risk":  round(max(scores), 2),
                "control_count":      len(scores),
                "risk_label":         _residual_label(sum(scores) / len(scores)),
            }
            for bl, scores in lines.items()
        }

        high_risk = [
            c.to_dict() for c in self._controls.values()
            if c.residual_risk_score >= 3.0
        ]

        return {
            "heat_map":           heat_map,
            "high_residual_risk": sorted(high_risk, key=lambda x: x["residual_risk_score"], reverse=True),
            "total_controls":     len(self._controls),
            "as_of":              datetime.now(timezone.utc).isoformat(),
        }

    def get_summary_stats(self) -> dict[str, Any]:
        controls = list(self._controls.values())
        residuals = [c.residual_risk_score for c in controls]
        return {
            "total_controls": len(controls),
            "avg_inherent_risk":  round(sum(c.inherent_risk_score for c in controls) / len(controls), 2),
            "avg_effectiveness":  round(sum(c.control_effectiveness for c in controls) / len(controls), 2),
            "avg_residual_risk":  round(sum(residuals) / len(residuals), 2),
            "controls_high_risk": sum(1 for r in residuals if r >= 3.0),
            "controls_low_risk":  sum(1 for r in residuals if r < 1.5),
        }


def _residual_label(score: float) -> str:
    if score < 1.0:  return "Low"
    if score < 2.0:  return "Low-Medium"
    if score < 3.0:  return "Medium"
    if score < 4.0:  return "High"
    return "Critical"


rcsa_framework = RCSAFramework()
