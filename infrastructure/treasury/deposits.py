"""
Deposit Account Model — Apex Global Bank.

CHECKING, SAVINGS, and TERM accounts for RETAIL, SME, and CORPORATE segments.
Wired to ALM repricing via get_repricing_buckets() — ALM falls back to static
buckets when this book is empty.

NMD behavioral parameters:
  - Retail CHECKING: 70% core stable (5yr tenor), 20% core less-stable (1yr), 10% non-core
  - Retail SAVINGS:  60% core stable (3yr tenor), 30% core less-stable (6mo), 10% non-core
  - SME/CORPORATE:   50% core stable (2yr tenor), 30% core less-stable (6mo), 20% non-core
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_DEPOSITS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS deposit_accounts (
    account_id       TEXT PRIMARY KEY,
    account_type     TEXT NOT NULL,   -- CHECKING | SAVINGS | TERM
    customer_segment TEXT NOT NULL,   -- RETAIL | SME | CORPORATE
    customer_name    TEXT NOT NULL,
    balance_usd      REAL NOT NULL DEFAULT 0.0,
    rate_pct         REAL NOT NULL DEFAULT 0.0,
    tenor_days       INTEGER,         -- NULL for demand deposits
    open_date        TEXT NOT NULL,
    maturity_date    TEXT,            -- NULL for demand deposits
    status           TEXT NOT NULL DEFAULT 'ACTIVE',  -- ACTIVE | CLOSED | MATURED
    created_at       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS deposit_transactions (
    txn_id       TEXT PRIMARY KEY,
    account_id   TEXT NOT NULL REFERENCES deposit_accounts(account_id),
    txn_type     TEXT NOT NULL,   -- DEPOSIT | WITHDRAWAL | INTEREST | MATURITY
    amount_usd   REAL NOT NULL,
    txn_date     TEXT NOT NULL,
    recorded_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_da_status   ON deposit_accounts(status, account_type);
CREATE INDEX IF NOT EXISTS idx_dt_account  ON deposit_transactions(account_id, txn_date DESC);
"""

# Seed deposit accounts — representative retail/commercial banking book
_SEED_ACCOUNTS = [
    # (account_type, segment, name,              balance,           rate,  tenor_days)
    ("CHECKING", "RETAIL",    "Retail Demand Pool A",  4_200_000_000.0, 0.10, None),
    ("CHECKING", "RETAIL",    "Retail Demand Pool B",  3_800_000_000.0, 0.10, None),
    ("SAVINGS",  "RETAIL",    "Retail Savings Pool",   8_500_000_000.0, 1.50, None),
    ("CHECKING", "SME",       "SME Operating Accounts", 2_100_000_000.0, 0.25, None),
    ("SAVINGS",  "SME",       "SME Reserve Accounts",  1_600_000_000.0, 2.00, None),
    ("CHECKING", "CORPORATE", "Corporate Cash Mgmt",   5_300_000_000.0, 0.50, None),
    ("TERM",     "RETAIL",    "Retail CD Pool 12mo",   1_200_000_000.0, 4.50, 365),
    ("TERM",     "RETAIL",    "Retail CD Pool 24mo",     900_000_000.0, 4.75, 730),
    ("TERM",     "CORPORATE", "Corp Time Deposit 6mo", 2_500_000_000.0, 5.00, 180),
    ("TERM",     "CORPORATE", "Corp Time Deposit 12mo",1_800_000_000.0, 5.25, 365),
]

# NMD behavioural parameters — core/non-core split + behavioural tenor (years)
_NMD_PARAMS: dict[tuple[str, str], dict] = {
    ("CHECKING", "RETAIL"):    {"core_stable": 0.70, "core_less_stable": 0.20, "non_core": 0.10,
                                "core_stable_tenor": 5.0, "core_less_stable_tenor": 1.0},
    ("SAVINGS",  "RETAIL"):    {"core_stable": 0.60, "core_less_stable": 0.30, "non_core": 0.10,
                                "core_stable_tenor": 3.0, "core_less_stable_tenor": 0.5},
    ("CHECKING", "SME"):       {"core_stable": 0.50, "core_less_stable": 0.30, "non_core": 0.20,
                                "core_stable_tenor": 2.0, "core_less_stable_tenor": 0.5},
    ("SAVINGS",  "SME"):       {"core_stable": 0.50, "core_less_stable": 0.30, "non_core": 0.20,
                                "core_stable_tenor": 2.0, "core_less_stable_tenor": 0.5},
    ("CHECKING", "CORPORATE"): {"core_stable": 0.40, "core_less_stable": 0.35, "non_core": 0.25,
                                "core_stable_tenor": 1.5, "core_less_stable_tenor": 0.25},
}


@dataclass
class DepositAccount:
    account_id:       str
    account_type:     str
    customer_segment: str
    customer_name:    str
    balance_usd:      float
    rate_pct:         float
    tenor_days:       int | None
    open_date:        str
    maturity_date:    str | None
    status:           str
    created_at:       str

    def to_dict(self) -> dict:
        return {
            "account_id":       self.account_id,
            "account_type":     self.account_type,
            "customer_segment": self.customer_segment,
            "customer_name":    self.customer_name,
            "balance_usd":      round(self.balance_usd, 2),
            "rate_pct":         self.rate_pct,
            "tenor_days":       self.tenor_days,
            "open_date":        self.open_date,
            "maturity_date":    self.maturity_date,
            "status":           self.status,
            "created_at":       self.created_at,
            "annual_interest_expense_usd": round(self.balance_usd * self.rate_pct / 100, 2),
        }


class DepositBook:
    """SQLite-backed deposit account origination and servicing."""

    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def _connect(self):
        return open_db(DB_DEPOSITS)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM deposit_accounts").fetchone()[0]
        if count > 0:
            return
        now = _now()
        open_d = "2024-01-15"
        for acct_type, segment, name, balance, rate, tenor in _SEED_ACCOUNTS:
            aid = f"DEP-{str(uuid.uuid4())[:8].upper()}"
            maturity = None
            if tenor:
                from datetime import date as _date
                d = _date.fromisoformat(open_d)
                from dateutil.relativedelta import relativedelta
                m = d + relativedelta(days=tenor)
                maturity = m.isoformat()
            conn.execute(
                "INSERT INTO deposit_accounts "
                "(account_id, account_type, customer_segment, customer_name, balance_usd, "
                "rate_pct, tenor_days, open_date, maturity_date, status, created_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?)",
                (aid, acct_type, segment, name, balance, rate, tenor, open_d, maturity, now),
            )
        conn.commit()
        log.info("deposit_book.seeded", count=len(_SEED_ACCOUNTS))

    def open_account(
        self,
        account_type: str,
        customer_segment: str,
        customer_name: str,
        initial_deposit: float,
        rate_pct: float,
        tenor_days: int | None = None,
    ) -> dict[str, Any]:
        if account_type not in ("CHECKING", "SAVINGS", "TERM"):
            raise ValueError("account_type must be CHECKING, SAVINGS, or TERM")
        if customer_segment not in ("RETAIL", "SME", "CORPORATE"):
            raise ValueError("customer_segment must be RETAIL, SME, or CORPORATE")
        if account_type == "TERM" and not tenor_days:
            raise ValueError("TERM accounts require tenor_days")

        aid = f"DEP-{str(uuid.uuid4())[:8].upper()}"
        open_d = date.today().isoformat()
        maturity = None
        if tenor_days:
            from dateutil.relativedelta import relativedelta
            d = date.today()
            maturity = (d + relativedelta(days=tenor_days)).isoformat()
        now = _now()

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO deposit_accounts "
                    "(account_id, account_type, customer_segment, customer_name, balance_usd, "
                    "rate_pct, tenor_days, open_date, maturity_date, status, created_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,'ACTIVE',?)",
                    (aid, account_type, customer_segment, customer_name,
                     initial_deposit, rate_pct, tenor_days, open_d, maturity, now),
                )
                if initial_deposit > 0:
                    conn.execute(
                        "INSERT INTO deposit_transactions (txn_id, account_id, txn_type, amount_usd, txn_date, recorded_at) "
                        "VALUES (?,?,?,?,?,?)",
                        (str(uuid.uuid4()), aid, "DEPOSIT", initial_deposit, open_d, now),
                    )
                conn.commit()

        log.info("deposit_book.opened", account_id=aid, segment=customer_segment, balance=initial_deposit)
        return self.get_account(aid)

    def deposit(self, account_id: str, amount_usd: float) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT balance_usd, account_type FROM deposit_accounts WHERE account_id=? AND status='ACTIVE'",
                    (account_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Account {account_id!r} not found or not active")
                new_bal = float(row["balance_usd"]) + amount_usd
                conn.execute("UPDATE deposit_accounts SET balance_usd=? WHERE account_id=?", (new_bal, account_id))
                conn.execute(
                    "INSERT INTO deposit_transactions (txn_id, account_id, txn_type, amount_usd, txn_date, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), account_id, "DEPOSIT", amount_usd, date.today().isoformat(), _now()),
                )
                conn.commit()
        return self.get_account(account_id)

    def withdraw(self, account_id: str, amount_usd: float) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT balance_usd, account_type FROM deposit_accounts WHERE account_id=? AND status='ACTIVE'",
                    (account_id,),
                ).fetchone()
                if not row:
                    raise ValueError(f"Account {account_id!r} not found or not active")
                if row["account_type"] == "TERM":
                    raise ValueError("Early withdrawal not permitted on TERM accounts")
                balance = float(row["balance_usd"])
                if amount_usd > balance:
                    raise ValueError(f"Insufficient balance: {balance:.2f} < {amount_usd:.2f}")
                new_bal = balance - amount_usd
                conn.execute("UPDATE deposit_accounts SET balance_usd=? WHERE account_id=?", (new_bal, account_id))
                conn.execute(
                    "INSERT INTO deposit_transactions (txn_id, account_id, txn_type, amount_usd, txn_date, recorded_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (str(uuid.uuid4()), account_id, "WITHDRAWAL", amount_usd, date.today().isoformat(), _now()),
                )
                conn.commit()
        return self.get_account(account_id)

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM deposit_accounts WHERE account_id=?", (account_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["annual_interest_expense_usd"] = round(d["balance_usd"] * d["rate_pct"] / 100, 2)
        return d

    def get_portfolio(self) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM deposit_accounts WHERE status='ACTIVE' ORDER BY customer_segment, account_type"
            ).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            d["annual_interest_expense_usd"] = round(d["balance_usd"] * d["rate_pct"] / 100, 2)
            result.append(d)
        return result

    def get_portfolio_summary(self) -> dict[str, Any]:
        accounts = self.get_portfolio()
        total_bal = sum(a["balance_usd"] for a in accounts)
        total_int = sum(a["annual_interest_expense_usd"] for a in accounts)

        by_type: dict[str, float] = {}
        by_segment: dict[str, float] = {}
        for a in accounts:
            t, s = a["account_type"], a["customer_segment"]
            by_type[t] = round(by_type.get(t, 0.0) + a["balance_usd"], 2)
            by_segment[s] = round(by_segment.get(s, 0.0) + a["balance_usd"], 2)

        return {
            "account_count":             len(accounts),
            "total_deposits_usd":        round(total_bal, 2),
            "annual_interest_expense_usd": round(total_int, 2),
            "cost_of_funds_pct":         round(total_int / total_bal * 100, 4) if total_bal else 0.0,
            "by_type":                   by_type,
            "by_segment":                by_segment,
        }

    def get_nmd_profile(self) -> dict[str, Any]:
        """Behavioural split of non-maturity deposits into core stable / core less-stable / non-core."""
        accounts = self.get_portfolio()
        nmd_accounts = [a for a in accounts if a["account_type"] in ("CHECKING", "SAVINGS")]
        total_nmd = sum(a["balance_usd"] for a in nmd_accounts)

        core_stable = 0.0
        core_less_stable = 0.0
        non_core = 0.0
        weighted_tenor_stable = 0.0
        weighted_tenor_less_stable = 0.0

        for a in nmd_accounts:
            key = (a["account_type"], a["customer_segment"])
            params = _NMD_PARAMS.get(key, _NMD_PARAMS[("CHECKING", "SME")])
            bal = a["balance_usd"]
            cs = bal * params["core_stable"]
            cls = bal * params["core_less_stable"]
            nc = bal * params["non_core"]
            core_stable += cs
            core_less_stable += cls
            non_core += nc
            weighted_tenor_stable += cs * params["core_stable_tenor"]
            weighted_tenor_less_stable += cls * params["core_less_stable_tenor"]

        avg_tenor_stable = weighted_tenor_stable / core_stable if core_stable else 0.0
        avg_tenor_less_stable = weighted_tenor_less_stable / core_less_stable if core_less_stable else 0.0

        return {
            "total_nmd_usd":              round(total_nmd, 2),
            "core_stable_usd":            round(core_stable, 2),
            "core_less_stable_usd":       round(core_less_stable, 2),
            "non_core_usd":               round(non_core, 2),
            "core_stable_pct":            round(core_stable / total_nmd, 4) if total_nmd else 0.0,
            "avg_behavioral_tenor_stable_yrs": round(avg_tenor_stable, 2),
            "avg_behavioral_tenor_less_stable_yrs": round(avg_tenor_less_stable, 2),
            "nmd_account_count":          len(nmd_accounts),
        }

    def get_interest_expense(self) -> dict[str, Any]:
        """Daily and annual interest expense across all active accounts."""
        accounts = self.get_portfolio()
        annual = sum(a["annual_interest_expense_usd"] for a in accounts)
        return {
            "annual_interest_expense_usd": round(annual, 2),
            "daily_interest_expense_usd":  round(annual / 365, 2),
            "quarterly_interest_expense_usd": round(annual / 4, 2),
        }

    def get_repricing_buckets(self) -> dict[str, float]:
        """
        Returns deposit balance by repricing bucket — same format as ALM._DEPOSIT_BUCKETS.
        Called by ALM to substitute live deposit data for static estimates.
        """
        accounts = self.get_portfolio()
        if not accounts:
            return {}

        buckets: dict[str, float] = {
            "overnight":   0.0,
            "1w":          0.0,
            "1m":          0.0,
            "3m":          0.0,
            "6m":          0.0,
            "1y":          0.0,
            "2y":          0.0,
            "5y":          0.0,
            "10y":         0.0,
        }

        for a in accounts:
            bal = a["balance_usd"]
            atype = a["account_type"]
            segment = a["customer_segment"]

            if atype == "TERM":
                tenor_days = a.get("tenor_days") or 365
                if tenor_days <= 180:
                    buckets["6m"] += bal
                elif tenor_days <= 365:
                    buckets["1y"] += bal
                else:
                    buckets["2y"] += bal
            else:
                # Behavioural split for NMD
                key = (atype, segment)
                params = _NMD_PARAMS.get(key, _NMD_PARAMS[("CHECKING", "SME")])
                cs = bal * params["core_stable"]
                cls_ = bal * params["core_less_stable"]
                nc = bal * params["non_core"]
                # Non-core → overnight; less-stable → 1m-1y; stable → 2y-5y
                buckets["overnight"] += nc * 0.5
                buckets["1w"] += nc * 0.5
                buckets["1m"] += cls_ * 0.5
                buckets["6m"] += cls_ * 0.5
                cs_tenor = params["core_stable_tenor"]
                if cs_tenor >= 4.0:
                    buckets["5y"] += cs
                elif cs_tenor >= 2.0:
                    buckets["2y"] += cs
                else:
                    buckets["1y"] += cs

        return {k: round(v, 2) for k, v in buckets.items()}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


deposit_book = DepositBook()
