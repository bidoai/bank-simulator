from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import structlog

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS instruments (
    isin TEXT PRIMARY KEY,
    cusip TEXT,
    ticker TEXT NOT NULL,
    name TEXT NOT NULL,
    product_type TEXT NOT NULL,
    currency TEXT NOT NULL DEFAULT 'USD',
    exchange TEXT,
    day_count TEXT DEFAULT 'ACT/360',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_ticker ON instruments(ticker);
"""

_DEFAULTS = [
    # (isin, cusip, ticker, name, product_type, currency, exchange)
    ("US0378331005",  "037833100", "AAPL",       "Apple Inc.",                     "equity",       "USD", "NASDAQ"),
    ("US5949181045",  "594918104", "MSFT",       "Microsoft Corporation",          "equity",       "USD", "NASDAQ"),
    ("US02079K3059",  "02079K305", "GOOGL",      "Alphabet Inc. Class A",          "equity",       "USD", "NASDAQ"),
    ("US912810TM96",  "912810TM9", "US10Y",      "US Treasury 10yr",               "govt_bond",    "USD", None),
    ("US91282CKN78",  "91282CKN7", "US2Y",       "US Treasury 2yr",                "govt_bond",    "USD", None),
    ("EURUSD_FX_SPOT", None,       "EURUSD",     "Euro / US Dollar Spot",          "fx_spot",      "USD", None),
    ("GBPUSD_FX_SPOT", None,       "GBPUSD",     "British Pound / US Dollar Spot", "fx_spot",      "USD", None),
    ("CDX_IG_FX_SPOT", None,       "IG_CDX",     "CDX Investment Grade Index",     "cds",          "USD", None),
    ("IRS_USD_10Y_SW", None,       "IRS_USD_10Y","USD Interest Rate Swap 10yr",    "rates_swap",   "USD", None),
]


class InstrumentMaster:
    def __init__(self, db_path: str = "data/instruments.db") -> None:
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
        log.info("instrument_master.ready", db=db_path)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def register(
        self,
        isin: str,
        ticker: str,
        name: str,
        product_type: str,
        currency: str,
        cusip: str | None = None,
        exchange: str | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO instruments
                        (isin, cusip, ticker, name, product_type, currency, exchange, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (isin, cusip, ticker, name, product_type, currency, exchange, created_at),
                )
        log.info("instrument_master.registered", ticker=ticker, isin=isin)

    def lookup_by_ticker(self, ticker: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM instruments WHERE ticker = ? AND is_active = 1",
                (ticker,),
            ).fetchone()
        return dict(row) if row else None

    def lookup_by_isin(self, isin: str) -> dict | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM instruments WHERE isin = ? AND is_active = 1",
                (isin,),
            ).fetchone()
        return dict(row) if row else None

    def seed_defaults(self) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                for isin, cusip, ticker, name, product_type, currency, exchange in _DEFAULTS:
                    conn.execute(
                        """
                        INSERT OR IGNORE INTO instruments
                            (isin, cusip, ticker, name, product_type, currency, exchange, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (isin, cusip, ticker, name, product_type, currency, exchange, created_at),
                    )
        log.info("instrument_master.seeded", count=len(_DEFAULTS))


instrument_master = InstrumentMaster()
