from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import structlog

from config.settings import DB_POSITIONS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    instrument TEXT NOT NULL,
    book_id TEXT NOT NULL,
    quantity REAL NOT NULL,
    avg_cost REAL NOT NULL,
    realised_pnl REAL NOT NULL DEFAULT 0,
    unrealised_pnl REAL NOT NULL DEFAULT 0,
    snapshot_time TEXT NOT NULL,
    UNIQUE(instrument, book_id)
);
"""


class PositionSnapshotStore:
    def __init__(self, db_path: str | Path = DB_POSITIONS) -> None:
        db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
        log.info("position_snapshot_store.ready", db=db_path)

    def _connect(self) -> sqlite3.Connection:
        return open_db(self._db_path)

    def save_snapshot(self, position_dict: dict) -> None:
        snapshot_time = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO position_snapshots
                        (instrument, book_id, quantity, avg_cost, realised_pnl, unrealised_pnl, snapshot_time)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(instrument, book_id) DO UPDATE SET
                        quantity = excluded.quantity,
                        avg_cost = excluded.avg_cost,
                        realised_pnl = excluded.realised_pnl,
                        unrealised_pnl = excluded.unrealised_pnl,
                        snapshot_time = excluded.snapshot_time
                    """,
                    (
                        position_dict["instrument"],
                        position_dict["book_id"],
                        position_dict["quantity"],
                        position_dict["avg_cost"],
                        position_dict.get("realised_pnl", 0.0),
                        position_dict.get("unrealised_pnl", 0.0),
                        snapshot_time,
                    ),
                )

    def save_all(self, positions: list[dict]) -> None:
        snapshot_time = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                for pos in positions:
                    conn.execute(
                        """
                        INSERT INTO position_snapshots
                            (instrument, book_id, quantity, avg_cost, realised_pnl, unrealised_pnl, snapshot_time)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        ON CONFLICT(instrument, book_id) DO UPDATE SET
                            quantity = excluded.quantity,
                            avg_cost = excluded.avg_cost,
                            realised_pnl = excluded.realised_pnl,
                            unrealised_pnl = excluded.unrealised_pnl,
                            snapshot_time = excluded.snapshot_time
                        """,
                        (
                            pos["instrument"],
                            pos["book_id"],
                            pos["quantity"],
                            pos["avg_cost"],
                            pos.get("realised_pnl", 0.0),
                            pos.get("unrealised_pnl", 0.0),
                            snapshot_time,
                        ),
                    )
        log.info("position_snapshot_store.saved_all", count=len(positions))

    def load_all(self) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM position_snapshots ORDER BY instrument, book_id"
            ).fetchall()
        return [dict(r) for r in rows]


snapshot_store = PositionSnapshotStore()
