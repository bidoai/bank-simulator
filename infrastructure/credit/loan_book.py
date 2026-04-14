"""
Loan Origination Engine — Apex Global Bank.

Supports term loans, revolving credit facilities, and bullet loans.
Each originated loan is registered as an Obligor in the IFRS9 ECL engine
so provisions are computed automatically.

Amortization: TERM = equal principal + interest; BULLET = interest-only + principal at maturity.
Stage assessment: based on grade and days-past-due.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_LOANS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS loans (
    loan_id         TEXT PRIMARY KEY,
    borrower_id     TEXT NOT NULL,
    borrower_name   TEXT NOT NULL,
    facility_type   TEXT NOT NULL,   -- TERM | REVOLVER | BULLET
    notional_usd    REAL NOT NULL,
    outstanding_usd REAL NOT NULL,
    rate_pct        REAL NOT NULL,   -- annual interest rate as %
    tenor_years     REAL NOT NULL,
    origination_date TEXT NOT NULL,
    maturity_date   TEXT NOT NULL,
    sector          TEXT NOT NULL DEFAULT 'CORPORATE',
    collateral_type TEXT NOT NULL DEFAULT 'UNSECURED',
    grade           TEXT NOT NULL DEFAULT 'BBB',
    stage           INTEGER NOT NULL DEFAULT 1,
    days_past_due   INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | REPAID | DEFAULT
    created_at      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS loan_payments (
    payment_id   TEXT PRIMARY KEY,
    loan_id      TEXT NOT NULL REFERENCES loans(loan_id),
    amount_usd   REAL NOT NULL,
    payment_type TEXT NOT NULL,   -- PRINCIPAL | INTEREST | FULL_REPAYMENT
    payment_date TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_loans_status ON loans(status);
CREATE INDEX IF NOT EXISTS idx_lp_loan ON loan_payments(loan_id, payment_date DESC);
"""

# Grade → 1-year PD and LGD mapping (consistent with IFRS9 engine)
GRADE_PARAMS: dict[str, dict[str, float]] = {
    "AAA": {"pd_1yr": 0.0001, "lgd": 0.30},
    "AA":  {"pd_1yr": 0.0003, "lgd": 0.35},
    "A":   {"pd_1yr": 0.0008, "lgd": 0.40},
    "BBB": {"pd_1yr": 0.0020, "lgd": 0.45},
    "BB":  {"pd_1yr": 0.0110, "lgd": 0.50},
    "B":   {"pd_1yr": 0.0450, "lgd": 0.55},
    "CCC": {"pd_1yr": 0.2600, "lgd": 0.65},
}

# Seed loans — representative commercial banking book
_SEED_LOANS = [
    ("BRW-001", "Apex Energy Holdings",  "TERM",    500_000_000, 4.75, 5.0, "ENERGY",      "ASSET_SECURED", "A"),
    ("BRW-002", "Meridian Retail Group", "REVOLVER", 300_000_000, 5.25, 3.0, "RETAIL",      "UNSECURED",     "BBB"),
    ("BRW-003", "Pacific Tech Corp",     "BULLET",  250_000_000, 4.50, 7.0, "TECHNOLOGY",  "UNSECURED",     "A"),
    ("BRW-004", "Coastal Real Estate",   "TERM",    800_000_000, 5.80, 10.0,"REAL_ESTATE",  "PROPERTY",      "BBB"),
    ("BRW-005", "Atlas Healthcare",      "TERM",    400_000_000, 4.25, 5.0, "HEALTHCARE",  "UNSECURED",     "AA"),
    ("BRW-006", "Summit Industrials",    "REVOLVER", 200_000_000, 5.50, 2.0, "INDUSTRIALS", "ASSET_SECURED", "BB"),
    ("BRW-007", "Horizon Automotive",    "TERM",    350_000_000, 5.00, 5.0, "AUTOMOTIVE",  "ASSET_SECURED", "BBB"),
    ("BRW-008", "National Utilities",    "BULLET",  600_000_000, 3.95, 10.0,"UTILITIES",   "UNSECURED",     "AA"),
]


@dataclass
class AmortizationPayment:
    period:          int
    date:            str
    opening_balance: float
    principal:       float
    interest:        float
    total_payment:   float
    closing_balance: float

    def to_dict(self) -> dict:
        return {
            "period":          self.period,
            "date":            self.date,
            "opening_balance": round(self.opening_balance, 2),
            "principal":       round(self.principal, 2),
            "interest":        round(self.interest, 2),
            "total_payment":   round(self.total_payment, 2),
            "closing_balance": round(self.closing_balance, 2),
        }


class LoanBook:
    """SQLite-backed commercial loan origination and servicing engine."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def _connect(self):
        return open_db(DB_LOANS)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM loans").fetchone()[0]
        if count > 0:
            return
        now = _now()
        for bid, bname, ftype, notional, rate, tenor, sector, collateral, grade in _SEED_LOANS:
            loan_id = f"LN-{bid}"
            orig = "2024-01-15"
            maturity = _add_years(orig, tenor)
            stage = _evaluate_stage(grade, 0)
            conn.execute(
                "INSERT INTO loans (loan_id, borrower_id, borrower_name, facility_type, "
                "notional_usd, outstanding_usd, rate_pct, tenor_years, origination_date, "
                "maturity_date, sector, collateral_type, grade, stage, days_past_due, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'ACTIVE',?)",
                (loan_id, bid, bname, ftype, notional, notional, rate, tenor,
                 orig, maturity, sector, collateral, grade, stage, now),
            )
        conn.commit()
        # Register seed loans as IFRS9 obligors
        self._sync_ifrs9(conn)
        log.info("loan_book.seeded", count=len(_SEED_LOANS))

    def originate(
        self,
        borrower_id: str,
        borrower_name: str,
        facility_type: str,
        notional_usd: float,
        rate_pct: float,
        tenor_years: float,
        sector: str = "CORPORATE",
        collateral_type: str = "UNSECURED",
        grade: str = "BBB",
    ) -> dict[str, Any]:
        """Originate a new loan and register it in the IFRS9 ECL engine."""
        if facility_type not in ("TERM", "REVOLVER", "BULLET"):
            raise ValueError(f"facility_type must be TERM, REVOLVER, or BULLET")
        if grade not in GRADE_PARAMS:
            raise ValueError(f"grade must be one of {list(GRADE_PARAMS)}")

        loan_id = f"LN-{str(uuid.uuid4())[:8].upper()}"
        orig = date.today().isoformat()
        maturity = _add_years(orig, tenor_years)
        stage = _evaluate_stage(grade, 0)
        now = _now()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO loans (loan_id, borrower_id, borrower_name, facility_type, "
                    "notional_usd, outstanding_usd, rate_pct, tenor_years, origination_date, "
                    "maturity_date, sector, collateral_type, grade, stage, days_past_due, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,0,'ACTIVE',?)",
                    (loan_id, borrower_id, borrower_name, facility_type,
                     notional_usd, notional_usd, rate_pct, tenor_years,
                     orig, maturity, sector, collateral_type, grade, stage, now),
                )
                conn.commit()

        # Register as IFRS9 obligor
        self._register_ifrs9_obligor(loan_id, borrower_name, notional_usd, grade, tenor_years, stage)

        # Fire event
        try:
            from infrastructure.events.event_log import event_log
            event_log.append("Loan", loan_id, "LoanOriginated", {
                "borrower": borrower_name, "notional": notional_usd, "grade": grade,
            })
        except Exception:
            pass

        log.info("loan.originated", loan_id=loan_id, borrower=borrower_name, notional=notional_usd)
        return self.get_loan(loan_id)

    def repay(self, loan_id: str, amount_usd: float) -> dict[str, Any]:
        """Record a principal repayment. Returns updated loan."""
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT outstanding_usd FROM loans WHERE loan_id = ? AND status = 'ACTIVE'",
                    (loan_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Loan {loan_id!r} not found or not active")
                outstanding = float(row[0])
                new_outstanding = max(0.0, outstanding - amount_usd)
                new_status = "REPAID" if new_outstanding == 0.0 else "ACTIVE"
                conn.execute(
                    "UPDATE loans SET outstanding_usd=?, status=? WHERE loan_id=?",
                    (new_outstanding, new_status, loan_id),
                )
                conn.execute(
                    "INSERT INTO loan_payments (payment_id, loan_id, amount_usd, payment_type, payment_date, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), loan_id, amount_usd,
                     "FULL_REPAYMENT" if new_status == "REPAID" else "PRINCIPAL",
                     date.today().isoformat(), _now()),
                )
                conn.commit()

        if new_status == "REPAID":
            try:
                from infrastructure.credit.ifrs9_ecl import ecl_engine
                ecl_engine.remove_obligor(loan_id)
            except Exception:
                pass

        return self.get_loan(loan_id)

    def get_loan(self, loan_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM loans WHERE loan_id=?", (loan_id,)).fetchone()
        return dict(row) if row else None

    def get_portfolio(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM loans ORDER BY origination_date DESC"
            ).fetchall()
        loans = [dict(r) for r in rows]
        # Annotate with ECL
        for loan in loans:
            params = GRADE_PARAMS.get(loan["grade"], GRADE_PARAMS["BBB"])
            notional = loan["outstanding_usd"]
            stage = loan["stage"]
            pd = params["pd_1yr"]
            lgd = params["lgd"]
            tenor = loan["tenor_years"]
            if stage == 1:
                ecl = pd * lgd * notional
            elif stage == 2:
                pd_life = 1.0 - (1.0 - pd) ** tenor
                ecl = pd_life * lgd * notional
            else:
                ecl = lgd * notional
            loan["ecl_usd"] = round(ecl, 2)
            loan["annual_interest_income_usd"] = round(notional * loan["rate_pct"] / 100, 2)
        return loans

    def get_portfolio_summary(self) -> dict[str, Any]:
        loans = self.get_portfolio()
        active = [l for l in loans if l["status"] == "ACTIVE"]
        total_outstanding = sum(l["outstanding_usd"] for l in active)
        total_ecl = sum(l["ecl_usd"] for l in active)
        total_nii = sum(l["annual_interest_income_usd"] for l in active)
        return {
            "loan_count":             len(active),
            "total_outstanding_usd":  round(total_outstanding, 2),
            "total_ecl_usd":          round(total_ecl, 2),
            "ecl_coverage_ratio":     round(total_ecl / total_outstanding, 4) if total_outstanding else 0.0,
            "annual_nii_usd":         round(total_nii, 2),
            "by_grade":               _group_by(active, "grade", "outstanding_usd"),
            "by_sector":              _group_by(active, "sector", "outstanding_usd"),
            "by_stage":               _group_by(active, "stage", "outstanding_usd"),
        }

    def get_amortization(self, loan_id: str) -> list[dict]:
        """Generate amortization schedule for a loan."""
        loan = self.get_loan(loan_id)
        if not loan:
            raise ValueError(f"Loan {loan_id!r} not found")
        return _build_schedule(
            notional=loan["notional_usd"],
            rate_pct=loan["rate_pct"],
            tenor_years=loan["tenor_years"],
            facility_type=loan["facility_type"],
            origination_date=loan["origination_date"],
        )

    # ── Private helpers ──────────────────────────────────────────────────────

    def _register_ifrs9_obligor(
        self, loan_id: str, name: str, notional: float, grade: str, tenor: float, stage: int
    ) -> None:
        try:
            from infrastructure.credit.ifrs9_ecl import ecl_engine, IFRSStage, Obligor
            params = GRADE_PARAMS.get(grade, GRADE_PARAMS["BBB"])
            obligor = Obligor(
                obligor_id=loan_id,
                name=name,
                notional_usd=notional,
                pd_1yr=params["pd_1yr"],
                lgd=params["lgd"],
                ead=notional,
                rating=grade,
                stage=IFRSStage(stage),
                maturity_years=tenor,
            )
            ecl_engine.add_obligor(obligor)
        except Exception as exc:
            log.warning("loan_book.ifrs9_register_failed", error=str(exc))

    def _sync_ifrs9(self, conn) -> None:
        """Register all active seed loans in the IFRS9 engine."""
        rows = conn.execute(
            "SELECT loan_id, borrower_name, outstanding_usd, grade, tenor_years, stage "
            "FROM loans WHERE status='ACTIVE'"
        ).fetchall()
        for row in rows:
            self._register_ifrs9_obligor(
                row["loan_id"], row["borrower_name"], row["outstanding_usd"],
                row["grade"], row["tenor_years"], row["stage"],
            )


# ── Module-level helpers ──────────────────────────────────────────────────────

def _evaluate_stage(grade: str, days_past_due: int) -> int:
    if days_past_due >= 90 or grade == "CCC":
        return 3
    if days_past_due >= 30 or grade in ("B", "BB"):
        return 2
    return 1


def _add_years(iso_date: str, years: float) -> str:
    from datetime import date as _date
    d = _date.fromisoformat(iso_date)
    return _date(d.year + int(years), d.month, d.day).isoformat()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _group_by(loans: list[dict], key: str, value_key: str) -> dict[str, float]:
    result: dict[str, float] = {}
    for loan in loans:
        k = str(loan.get(key, "UNKNOWN"))
        result[k] = round(result.get(k, 0.0) + loan.get(value_key, 0.0), 2)
    return result


def _build_schedule(
    notional: float,
    rate_pct: float,
    tenor_years: float,
    facility_type: str,
    origination_date: str,
) -> list[dict]:
    from datetime import date as _date
    from dateutil.relativedelta import relativedelta  # type: ignore

    periods = int(tenor_years * 12)  # monthly
    monthly_rate = rate_pct / 100 / 12
    balance = notional
    orig = _date.fromisoformat(origination_date)
    schedule = []

    for i in range(1, periods + 1):
        pay_date = orig + relativedelta(months=i)
        interest = balance * monthly_rate

        if facility_type == "BULLET":
            principal = notional if i == periods else 0.0
        else:  # TERM or REVOLVER — equal principal
            principal = notional / periods

        payment = principal + interest
        closing = max(0.0, balance - principal)

        schedule.append(AmortizationPayment(
            period=i,
            date=pay_date.isoformat(),
            opening_balance=balance,
            principal=principal,
            interest=interest,
            total_payment=payment,
            closing_balance=closing,
        ).to_dict())

        balance = closing

    return schedule


loan_book = LoanBook()
