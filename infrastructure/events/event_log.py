from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

import structlog

from config.settings import DB_EVENTS
from infrastructure.persistence.sqlite_base import open_db

log = structlog.get_logger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS bank_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT UNIQUE NOT NULL,
    aggregate_type TEXT NOT NULL,
    aggregate_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload TEXT NOT NULL,
    sequence_number INTEGER NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_aggregate ON bank_events(aggregate_type, aggregate_id);
CREATE INDEX IF NOT EXISTS idx_event_type ON bank_events(event_type);
"""


class EventLog:
    def __init__(self, db_path: str | Path = DB_EVENTS) -> None:
        db_path = str(db_path)
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._db_path = db_path
        self._lock = Lock()
        with self._connect() as conn:
            conn.executescript(_DDL)
        log.info("event_log.ready", db=db_path)

    def _connect(self) -> sqlite3.Connection:
        return open_db(self._db_path)

    def _next_sequence(self, conn: sqlite3.Connection, aggregate_type: str, aggregate_id: str) -> int:
        row = conn.execute(
            "SELECT MAX(sequence_number) FROM bank_events WHERE aggregate_type = ? AND aggregate_id = ?",
            (aggregate_type, aggregate_id),
        ).fetchone()
        current = row[0]
        return (current + 1) if current is not None else 1

    def append(self, aggregate_type: str, aggregate_id: str, event_type: str, payload: dict) -> str:
        event_id = str(uuid.uuid4())
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            with self._connect() as conn:
                seq = self._next_sequence(conn, aggregate_type, aggregate_id)
                conn.execute(
                    """
                    INSERT INTO bank_events
                        (event_id, aggregate_type, aggregate_id, event_type, payload, sequence_number, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (event_id, aggregate_type, aggregate_id, event_type, json.dumps(payload), seq, created_at),
                )
        log.info("event_log.appended", event_type=event_type, aggregate_type=aggregate_type, aggregate_id=aggregate_id, seq=seq)
        return event_id

    def get_events(self, aggregate_type: str, aggregate_id: str) -> list[dict]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM bank_events
                WHERE aggregate_type = ? AND aggregate_id = ?
                ORDER BY sequence_number ASC
                """,
                (aggregate_type, aggregate_id),
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_recent(self, limit: int = 100, event_type: str | None = None) -> list[dict]:
        with self._connect() as conn:
            if event_type:
                rows = conn.execute(
                    "SELECT * FROM bank_events WHERE event_type = ? ORDER BY id DESC LIMIT ?",
                    (event_type, limit),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM bank_events ORDER BY id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["payload"] = json.loads(d["payload"])
        return d


event_log = EventLog()
