"""
Model Governance Registry — SR 11-7 compliant model lifecycle management.

Lifecycle states: DEVELOPMENT → VALIDATION → PRODUCTION → RETIRED

Rules:
- capital_approved can only be True if status == "production" AND sign_off_by is not None
- Any model with status != "production" raises a governance warning when used for capital
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import structlog

log = structlog.get_logger(__name__)

_DB_PATH = Path(__file__).parent.parent.parent / "data" / "model_registry.db"

_DDL = """
CREATE TABLE IF NOT EXISTS model_registry (
    model_id              TEXT PRIMARY KEY,
    name                  TEXT NOT NULL,
    owner                 TEXT NOT NULL,
    asset_class           TEXT NOT NULL DEFAULT '',
    use_case              TEXT NOT NULL,
    status                TEXT NOT NULL,
    version               TEXT NOT NULL,
    implementation_date   TEXT,
    last_validation_date  TEXT,
    next_validation_date  TEXT,
    last_backtest_date    TEXT,
    validator             TEXT,
    sign_off_by           TEXT,
    limitations           TEXT NOT NULL DEFAULT '[]',
    capital_approved      INTEGER NOT NULL DEFAULT 0,
    materiality           TEXT NOT NULL DEFAULT 'MEDIUM',
    model_risk_rating     TEXT NOT NULL DEFAULT '3',
    notes                 TEXT NOT NULL DEFAULT '',
    updated_at            TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

VALID_STATUSES = {"development", "validation", "production", "retired"}
STATUS_ORDER = {"development": 0, "validation": 1, "production": 2, "retired": 3}


@dataclass
class ModelRecord:
    model_id: str
    name: str
    owner: str
    use_case: str                        # capital_calculation | risk_management | pricing | reporting
    status: str                          # development | validation | production | retired
    version: str
    asset_class: str = ""
    implementation_date: str | None = None
    last_validation_date: str | None = None
    next_validation_date: str | None = None
    last_backtest_date: str | None = None
    validator: str | None = None
    sign_off_by: str | None = None
    limitations: list[str] = field(default_factory=list)
    capital_approved: bool = False
    materiality: str = "MEDIUM"          # HIGH | MEDIUM | LOW
    model_risk_rating: str = "3"         # 1 (lowest) to 5 (highest)
    notes: str = ""

    def __post_init__(self) -> None:
        # Enforce validation gate
        if self.capital_approved:
            if self.status != "production" or self.sign_off_by is None:
                raise ValueError(
                    f"Model {self.model_id}: capital_approved requires status='production' "
                    f"and a sign_off_by value (got status='{self.status}', sign_off_by={self.sign_off_by!r})"
                )


# ---------------------------------------------------------------------------
# Initial registry — all models in the bank simulator
# ---------------------------------------------------------------------------

INITIAL_REGISTRY: list[ModelRecord] = [
    ModelRecord(
        model_id="MOD-001",
        name="Monte Carlo VaR",
        owner="Dr. Marcus Webb",
        use_case="capital_calculation",
        status="production",
        version="2.1",
        capital_approved=True,
        materiality="HIGH",
        model_risk_rating="2",
        limitations=[
            "10,000 paths insufficient for tail risk beyond 99.5%",
            "Normal distribution assumption underestimates fat tails",
        ],
        last_validation_date="2025-09-15",
        next_validation_date="2026-09-15",
        sign_off_by="Dr. Rebecca Chen",
    ),
    ModelRecord(
        model_id="MOD-002",
        name="SIMM 2.6 (Approximation)",
        owner="Dr. Marcus Webb",
        use_case="risk_management",
        status="validation",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="3",
        limitations=[
            "APPROXIMATION ONLY — does not include vega risk class",
            "APPROXIMATION ONLY — does not include curvature risk class",
            "APPROXIMATION ONLY — cross-gamma terms not modelled",
            "NOT VALIDATED for regulatory IM calculation — for indicative purposes only",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-003",
        name="IFRS 9 ECL Engine",
        owner="Elena Vasquez",
        use_case="reporting",
        status="production",
        version="1.5",
        capital_approved=True,
        materiality="HIGH",
        model_risk_rating="2",
        limitations=[
            "No forward-looking macro overlay — point-in-time PD only",
            "50-obligor portfolio is representative sample only",
        ],
        last_validation_date="2025-11-01",
        sign_off_by="Dr. Samuel Achebe",
    ),
    ModelRecord(
        model_id="MOD-004",
        name="Regulatory Capital Engine (SA)",
        owner="Dr. Priya Nair",
        use_case="capital_calculation",
        status="production",
        version="3.0",
        capital_approved=True,
        materiality="HIGH",
        model_risk_rating="1",
        limitations=[
            "Standardised Approach only — no IMA",
            "SA-CCR add-ons use simplified supervisory factors",
        ],
        last_validation_date="2026-01-10",
        sign_off_by="Dr. Rebecca Chen",
    ),
    ModelRecord(
        model_id="MOD-005",
        name="DFAST Stress Engine",
        owner="Dr. Priya Nair",
        use_case="risk_management",
        status="production",
        version="2.0",
        capital_approved=True,
        materiality="HIGH",
        model_risk_rating="2",
        limitations=[
            "Deterministic scenarios — no stochastic rate path generation",
            "No feedback loop between credit losses and deposit behaviour",
        ],
        last_validation_date="2025-12-01",
        sign_off_by="Dr. Rebecca Chen",
    ),
    ModelRecord(
        model_id="MOD-006",
        name="ALM Engine (NII/EVE)",
        owner="Amara Diallo",
        use_case="risk_management",
        status="production",
        version="2.1",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="2",
        limitations=[
            "NMD model recently updated — full re-validation pending",
        ],
        last_validation_date="2025-08-20",
        sign_off_by="Dr. Rebecca Chen",
    ),
    ModelRecord(
        model_id="MOD-007",
        name="XVA Engine (CVA/DVA/FVA)",
        owner="Dr. Yuki Tanaka",
        use_case="pricing",
        status="validation",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="4",
        limitations=[
            "Dependent on external pyxva library",
            "Collateral-CVA integration not yet complete",
            "No counterparty CDS term structure — flat spread assumption",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-008",
        name="SA-CCR Engine",
        owner="Dr. Priya Nair",
        use_case="capital_calculation",
        status="development",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="2",
        limitations=[
            "First implementation — pending independent validation",
            "Supervisory delta for complex options not yet implemented",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-009",
        name="OpRisk BIA Engine",
        owner="Dr. Priya Nair",
        use_case="capital_calculation",
        status="development",
        version="1.0",
        capital_approved=False,
        materiality="MEDIUM",
        model_risk_rating="1",
        limitations=[
            "Business Indicator components are management estimates — not audited P&L",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-010",
        name="Stressed VaR Engine",
        owner="Dr. Marcus Webb",
        use_case="capital_calculation",
        status="development",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="3",
        limitations=[
            "Stressed period calibrated to 2008 crisis — may not represent current regime",
            "No historical time series — using volatility multiplier approximation",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-011",
        name="LCR Engine",
        owner="Thomas Nakamura",
        use_case="capital_calculation",
        status="development",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="1",
        limitations=[
            "Balance sheet inputs are representative estimates — not reconciled to general ledger",
        ],
        sign_off_by=None,
    ),
    ModelRecord(
        model_id="MOD-012",
        name="NSFR Engine",
        owner="Thomas Nakamura",
        use_case="capital_calculation",
        status="development",
        version="1.0",
        capital_approved=False,
        materiality="HIGH",
        model_risk_rating="1",
        limitations=[
            "ASF/RSF factors use standard Basel weights — no jurisdiction-specific adjustments",
        ],
        sign_off_by=None,
    ),
]


def _record_to_row(m: ModelRecord) -> dict[str, Any]:
    d = asdict(m)
    d["limitations"] = json.dumps(d["limitations"])
    d["capital_approved"] = 1 if d["capital_approved"] else 0
    return d


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    d = dict(row)
    d["limitations"] = json.loads(d.get("limitations") or "[]")
    d["capital_approved"] = bool(d.get("capital_approved", 0))
    return d


class ModelRegistry:
    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or _DB_PATH

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def initialize(self) -> None:
        """Create table and seed initial models (idempotent)."""
        with self._connect() as conn:
            conn.execute(_DDL)
            for model in INITIAL_REGISTRY:
                row = _record_to_row(model)
                cols = ", ".join(row.keys())
                placeholders = ", ".join(f":{k}" for k in row.keys())
                conn.execute(
                    f"INSERT OR IGNORE INTO model_registry ({cols}) VALUES ({placeholders})",
                    row,
                )
        log.info("model_registry.initialized", models=len(INITIAL_REGISTRY))

    # ------------------------------------------------------------------
    # Read methods
    # ------------------------------------------------------------------

    def get_all_models(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM model_registry ORDER BY model_id"
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_model(self, model_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM model_registry WHERE model_id = ?", (model_id,)
            ).fetchone()
        return _row_to_dict(row) if row else None

    def get_capital_approved_models(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM model_registry
                WHERE status = 'production' AND capital_approved = 1
                ORDER BY model_id
                """
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_models_by_status(self, status: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM model_registry WHERE status = ? ORDER BY model_id",
                (status.lower(),),
            ).fetchall()
        return [_row_to_dict(r) for r in rows]

    def get_limitation_disclosures(self, model_id: str) -> list[str]:
        model = self.get_model(model_id)
        if not model:
            return []
        return model.get("limitations", [])

    def get_risk_rating_summary(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT model_risk_rating, COUNT(*) as cnt FROM model_registry GROUP BY model_risk_rating"
            ).fetchall()
        return {r["model_risk_rating"]: r["cnt"] for r in rows}

    def is_capital_approved(self, model_id: str) -> dict[str, Any]:
        model = self.get_model(model_id)
        if not model:
            return {"approved": False, "reason": f"Model '{model_id}' not found in registry"}
        if model["capital_approved"] and model["status"] == "production":
            return {"approved": True, "reason": f"Production model signed off by {model['sign_off_by']}"}
        reasons = []
        if model["status"] != "production":
            reasons.append(f"status is '{model['status']}' — must be 'production'")
        if not model["capital_approved"]:
            reasons.append("capital_approved flag is False")
        if not model["sign_off_by"]:
            reasons.append("no sign_off_by recorded")
        return {"approved": False, "reason": "; ".join(reasons)}

    # ------------------------------------------------------------------
    # Write methods
    # ------------------------------------------------------------------

    def update_model_status(
        self,
        model_id: str,
        new_status: str,
        validator: str | None = None,
        sign_off: str | None = None,
    ) -> dict[str, Any]:
        if new_status not in VALID_STATUSES:
            return {"success": False, "error": f"Invalid status '{new_status}'. Must be one of {sorted(VALID_STATUSES)}"}

        model = self.get_model(model_id)
        if not model:
            return {"success": False, "error": f"Model '{model_id}' not found"}

        updates: dict[str, Any] = {
            "status": new_status,
            "updated_at": "datetime('now')",
        }
        if validator:
            updates["validator"] = validator
        if sign_off:
            updates["sign_off_by"] = sign_off

        # If moving to production with sign-off, check if capital can be approved
        set_clauses = ", ".join(
            f"{k} = ?" for k in updates if k != "updated_at"
        ) + ", updated_at = datetime('now')"
        values = [v for k, v in updates.items() if k != "updated_at"]
        values.append(model_id)

        with self._connect() as conn:
            conn.execute(
                f"UPDATE model_registry SET {set_clauses} WHERE model_id = ?",
                values,
            )

        log.info("model_registry.status_updated", model_id=model_id, new_status=new_status)
        return {"success": True, "model_id": model_id, "new_status": new_status}

    def validate_model(
        self,
        model_id: str,
        validator: str,
        findings: str,
        approved: bool,
    ) -> dict[str, Any]:
        """
        Advance a model through the validation gate.

        If approved=True and current status is 'validation', advances to 'production'.
        Records the validator and today's date as last_validation_date.
        """
        model = self.get_model(model_id)
        if not model:
            return {"success": False, "error": f"Model '{model_id}' not found"}

        today = date.today().isoformat()
        current_status = model["status"]

        if current_status == "development":
            new_status = "validation"
        elif current_status == "validation" and approved:
            new_status = "production"
        elif current_status == "validation" and not approved:
            new_status = "validation"  # remains in validation with findings
        else:
            return {
                "success": False,
                "error": f"Cannot validate model with status '{current_status}'",
            }

        with self._connect() as conn:
            conn.execute(
                """
                UPDATE model_registry SET
                    status = ?,
                    validator = ?,
                    last_validation_date = ?,
                    notes = ?,
                    updated_at = datetime('now')
                WHERE model_id = ?
                """,
                (new_status, validator, today, findings, model_id),
            )

        log.info(
            "model_registry.validated",
            model_id=model_id,
            validator=validator,
            new_status=new_status,
            approved=approved,
        )
        return {
            "success": True,
            "model_id": model_id,
            "previous_status": current_status,
            "new_status": new_status,
            "validator": validator,
            "validation_date": today,
            "approved": approved,
        }


# Module-level singleton (initialised in api/main.py lifespan)
model_registry = ModelRegistry()
