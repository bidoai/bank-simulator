"""
Securities Custody — Apex Global Bank.

Manages client custody accounts (omnibus and segregated), holdings, and
assets under custody (AuC). Settlement instructions and corporate actions
are handled by sibling modules.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from threading import Lock
from typing import Any

import structlog

from config.settings import DB_CUSTODY
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS custody_accounts (
    account_id   TEXT PRIMARY KEY,
    client_id    TEXT NOT NULL,
    client_name  TEXT NOT NULL,
    account_type TEXT NOT NULL,   -- OMNIBUS | SEGREGATED
    status       TEXT NOT NULL DEFAULT 'ACTIVE',
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS custody_holdings (
    holding_id       TEXT PRIMARY KEY,
    account_id       TEXT NOT NULL REFERENCES custody_accounts(account_id),
    isin             TEXT NOT NULL,
    description      TEXT NOT NULL,
    quantity         REAL NOT NULL DEFAULT 0.0,
    market_value_usd REAL NOT NULL DEFAULT 0.0,
    cost_basis_usd   REAL NOT NULL DEFAULT 0.0,
    settlement_date  TEXT NOT NULL,
    updated_at       TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_holding_acct_isin ON custody_holdings(account_id, isin);
CREATE INDEX IF NOT EXISTS idx_holdings_account ON custody_holdings(account_id);
"""

# Seed custody clients with representative holdings
_SEED_ACCOUNTS = [
    ("CLT-001", "Apex Pension Fund",       "OMNIBUS"),
    ("CLT-002", "Meridian Family Office",  "SEGREGATED"),
    ("CLT-003", "Pacific Asset Management","OMNIBUS"),
    ("CLT-004", "Summit Insurance Co.",    "SEGREGATED"),
]

_SEED_HOLDINGS = [
    # (client_id, isin, description, quantity, price_usd)
    ("CLT-001", "US912810TM80", "UST 4.375% 2043",       50_000_000, 96.50),
    ("CLT-001", "US38141GXZ20", "Goldman Sachs Bond",    25_000_000, 98.20),
    ("CLT-001", "US4592001014", "IBM Common Stock",          500_000, 183.25),
    ("CLT-002", "US0231351067", "Amazon Common Stock",        50_000, 185.40),
    ("CLT-002", "US5949181045", "Microsoft Common Stock",    120_000, 415.00),
    ("CLT-002", "US02079K3059", "Alphabet Class A",           30_000, 175.80),
    ("CLT-003", "US912810TM80", "UST 4.375% 2043",       80_000_000, 96.50),
    ("CLT-003", "US9311421039", "Walmart Common Stock",      200_000, 96.80),
    ("CLT-004", "US38141GXZ20", "Goldman Sachs Bond",    40_000_000, 98.20),
    ("CLT-004", "US06738E2046", "Barrick Gold Stock",        300_000, 17.50),
]


class CustodyBook:
    def __init__(self) -> None:
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
            self._seed_if_empty(conn)

    def _connect(self):
        return open_db(DB_CUSTODY)

    def _seed_if_empty(self, conn) -> None:
        count = conn.execute("SELECT COUNT(*) FROM custody_accounts").fetchone()[0]
        if count > 0:
            return
        now = _now()
        today = date.today().isoformat()

        # Map client_id to account_id for holding insertion
        acct_map: dict[str, str] = {}
        for cid, name, atype in _SEED_ACCOUNTS:
            aid = f"CUST-{cid}"
            acct_map[cid] = aid
            conn.execute(
                "INSERT INTO custody_accounts (account_id, client_id, client_name, account_type, created_at) "
                "VALUES (?,?,?,?,?)",
                (aid, cid, name, atype, now),
            )

        for cid, isin, desc, qty, price in _SEED_HOLDINGS:
            aid = acct_map[cid]
            hid = f"HLD-{str(uuid.uuid4())[:8].upper()}"
            mv = qty * price
            cb = mv  # cost basis = market value at seed time
            conn.execute(
                "INSERT INTO custody_holdings (holding_id, account_id, isin, description, "
                "quantity, market_value_usd, cost_basis_usd, settlement_date, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (hid, aid, isin, desc, qty, mv, cb, today, now),
            )

        conn.commit()
        log.info("custody_book.seeded", accounts=len(_SEED_ACCOUNTS), holdings=len(_SEED_HOLDINGS))

    def open_account(self, client_id: str, client_name: str, account_type: str) -> dict[str, Any]:
        if account_type not in ("OMNIBUS", "SEGREGATED"):
            raise ValueError("account_type must be OMNIBUS or SEGREGATED")
        aid = f"CUST-{str(uuid.uuid4())[:8].upper()}"
        now = _now()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "INSERT INTO custody_accounts (account_id, client_id, client_name, account_type, created_at) "
                    "VALUES (?,?,?,?,?)",
                    (aid, client_id, client_name, account_type, now),
                )
                conn.commit()
        log.info("custody.account_opened", account_id=aid, client=client_name)
        return self.get_account(aid)

    def book_holding(
        self,
        account_id: str,
        isin: str,
        description: str,
        quantity: float,
        price_usd: float,
    ) -> dict[str, Any]:
        """Add or update a holding. Upserts by (account_id, isin)."""
        mv = quantity * price_usd
        today = date.today().isoformat()
        now = _now()

        with self._lock:
            with self._connect() as conn:
                existing = conn.execute(
                    "SELECT holding_id, quantity, cost_basis_usd FROM custody_holdings "
                    "WHERE account_id=? AND isin=?",
                    (account_id, isin),
                ).fetchone()

                if existing:
                    new_qty = float(existing["quantity"]) + quantity
                    new_cb = float(existing["cost_basis_usd"]) + mv
                    new_mv = new_qty * price_usd
                    conn.execute(
                        "UPDATE custody_holdings SET quantity=?, market_value_usd=?, cost_basis_usd=?, "
                        "settlement_date=?, updated_at=? WHERE holding_id=?",
                        (new_qty, new_mv, new_cb, today, now, existing["holding_id"]),
                    )
                    hid = existing["holding_id"]
                else:
                    hid = f"HLD-{str(uuid.uuid4())[:8].upper()}"
                    conn.execute(
                        "INSERT INTO custody_holdings (holding_id, account_id, isin, description, "
                        "quantity, market_value_usd, cost_basis_usd, settlement_date, updated_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?)",
                        (hid, account_id, isin, description, quantity, mv, mv, today, now),
                    )
                conn.commit()

        return self._get_holding(hid)

    def get_account(self, account_id: str) -> dict[str, Any] | None:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM custody_accounts WHERE account_id=?", (account_id,)).fetchone()
        return dict(row) if row else None

    def get_holdings(self, account_id: str) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM custody_holdings WHERE account_id=? ORDER BY market_value_usd DESC",
                (account_id,),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_total_auc(self) -> dict[str, Any]:
        """Total assets under custody across all accounts."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT ca.account_id, ca.client_name, ca.account_type, "
                "SUM(ch.market_value_usd) as auc_usd, COUNT(ch.holding_id) as holding_count "
                "FROM custody_accounts ca "
                "LEFT JOIN custody_holdings ch ON ca.account_id = ch.account_id "
                "WHERE ca.status='ACTIVE' "
                "GROUP BY ca.account_id",
            ).fetchall()

        accounts = [dict(r) for r in rows]
        total_auc = sum(a.get("auc_usd") or 0.0 for a in accounts)

        return {
            "total_auc_usd": round(total_auc, 2),
            "account_count": len(accounts),
            "by_account": [
                {
                    "account_id":    a["account_id"],
                    "client_name":   a["client_name"],
                    "account_type":  a["account_type"],
                    "auc_usd":       round(a.get("auc_usd") or 0.0, 2),
                    "holding_count": a.get("holding_count") or 0,
                }
                for a in accounts
            ],
        }

    def apply_corporate_action(self, ca: dict) -> dict[str, Any]:
        """Apply a corporate action to all holdings of the affected ISIN."""
        isin = ca["isin"]
        ca_type = ca["ca_type"]
        results = []

        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM custody_holdings WHERE isin=?", (isin,)
            ).fetchall()

        for row in rows:
            h = dict(row)
            if ca_type == "STOCK_SPLIT":
                ratio = float(ca.get("ratio", 2.0))
                new_qty = h["quantity"] * ratio
                new_cb = h["cost_basis_usd"]  # cost basis unchanged
                new_mv = new_qty * (h["market_value_usd"] / h["quantity"])
                with self._connect() as conn:
                    conn.execute(
                        "UPDATE custody_holdings SET quantity=?, market_value_usd=?, updated_at=? WHERE holding_id=?",
                        (new_qty, new_mv, _now(), h["holding_id"]),
                    )
                    conn.commit()
                results.append({"holding_id": h["holding_id"], "action": "SPLIT", "new_quantity": new_qty})

            elif ca_type == "DIVIDEND":
                # Cash dividend — just log (no cash account in custody for now)
                dps = float(ca.get("dividend_per_share", 0.0))
                cash = h["quantity"] * dps
                results.append({"holding_id": h["holding_id"], "action": "DIVIDEND", "cash_usd": round(cash, 2)})

        return {"isin": isin, "ca_type": ca_type, "applied_to": len(results), "results": results}

    def _get_holding(self, holding_id: str) -> dict[str, Any]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM custody_holdings WHERE holding_id=?", (holding_id,)).fetchone()
        return dict(row) if row else {}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


custody_book = CustodyBook()
