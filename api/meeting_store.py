"""
Persistent meeting store — SQLite-backed log of all boardroom sessions.

Schema
------
meetings     : one row per session (id, title, topic, status, timestamps)
meeting_turns: one row per agent turn  (meeting_id FK, agent_name, text, …)

WAL mode is enabled at schema init time (persists on disk). Each write
operation opens its own short-lived connection so the sync store can be
called safely from the FastAPI thread pool without shared-connection races.
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

import structlog

log = structlog.get_logger(__name__)

_DB_PATH = Path(__file__).parent.parent / "data" / "meetings.db"

_DDL = """
CREATE TABLE IF NOT EXISTS meetings (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    topic       TEXT NOT NULL,
    status      TEXT NOT NULL DEFAULT 'running',   -- running | completed | error
    started_at  TEXT NOT NULL,
    ended_at    TEXT,
    agent_names TEXT NOT NULL DEFAULT '[]',        -- JSON array
    turn_count  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS meeting_turns (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    meeting_id  TEXT NOT NULL REFERENCES meetings(id),
    seq         INTEGER NOT NULL,
    agent_name  TEXT NOT NULL,
    agent_title TEXT NOT NULL,
    text        TEXT NOT NULL,
    color       TEXT NOT NULL DEFAULT '#c9d1d9',
    timestamp   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_turns_meeting ON meeting_turns(meeting_id, seq);
CREATE INDEX IF NOT EXISTS idx_meetings_started ON meetings(started_at DESC);
"""


class MeetingStore:
    def __init__(self, db_path: Path = _DB_PATH) -> None:
        self.db_path = db_path

    def _connect(self) -> sqlite3.Connection:
        """Open a fresh connection. Caller must close it."""
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def initialize(self) -> None:
        """Create the data directory and apply the DDL schema. Call once at startup."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = self._connect()
        try:
            conn.executescript(_DDL)
            conn.commit()
        finally:
            conn.close()
        log.info("meeting_store.initialized", path=str(self.db_path))

    # ── Write — each method opens and closes its own connection ───────────────

    def create_meeting(self, title: str, topic: str, agent_names: list[str]) -> str:
        meeting_id = str(uuid.uuid4())
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO meetings (id, title, topic, status, started_at, agent_names) "
                "VALUES (?, ?, ?, 'running', ?, ?)",
                (meeting_id, title, topic, _now(), json.dumps(agent_names)),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("meeting_store.created", meeting_id=meeting_id, title=title)
        return meeting_id

    def add_turn(
        self,
        meeting_id: str,
        agent_name: str,
        agent_title: str,
        text: str,
        color: str = "#c9d1d9",
    ) -> None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COALESCE(MAX(seq), 0) FROM meeting_turns WHERE meeting_id = ?",
                (meeting_id,),
            ).fetchone()
            next_seq = (row[0] or 0) + 1
            conn.execute(
                "INSERT INTO meeting_turns (meeting_id, seq, agent_name, agent_title, text, color, timestamp) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (meeting_id, next_seq, agent_name, agent_title, text, color, _now()),
            )
            conn.execute(
                "UPDATE meetings SET turn_count = turn_count + 1 WHERE id = ?",
                (meeting_id,),
            )
            conn.commit()
        finally:
            conn.close()

    def complete_meeting(self, meeting_id: str, status: str = "completed") -> None:
        conn = self._connect()
        try:
            conn.execute(
                "UPDATE meetings SET status = ?, ended_at = ? WHERE id = ?",
                (status, _now(), meeting_id),
            )
            conn.commit()
        finally:
            conn.close()
        log.info("meeting_store.completed", meeting_id=meeting_id, status=status)

    # ── Read ───────────────────────────────────────────────────────────────────

    def list_meetings(self, limit: int = 50) -> list[dict]:
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, title, topic, status, started_at, ended_at, agent_names, turn_count "
                "FROM meetings ORDER BY started_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [_row_to_meeting(r) for r in rows]
        finally:
            conn.close()

    def get_meeting(self, meeting_id: str) -> dict | None:
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, title, topic, status, started_at, ended_at, agent_names, turn_count "
                "FROM meetings WHERE id = ?",
                (meeting_id,),
            ).fetchone()
            return _row_to_meeting(row) if row else None
        finally:
            conn.close()

    def get_turns(
        self,
        meeting_id: str,
        limit: int = 200,
        after_seq: int = 0,
    ) -> list[dict]:
        """
        Return up to `limit` turns with seq > after_seq, ordered by seq ASC.
        Use after_seq as a cursor for pagination: pass the last returned seq
        to fetch the next page.
        """
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT seq, agent_name, agent_title, text, color, timestamp "
                "FROM meeting_turns WHERE meeting_id = ? AND seq > ? "
                "ORDER BY seq ASC LIMIT ?",
                (meeting_id, after_seq, limit),
            ).fetchall()
            return [
                {
                    "type":      "agent_turn",
                    "seq":       r["seq"],
                    "agent":     r["agent_name"],
                    "title":     r["agent_title"],
                    "text":      r["text"],
                    "color":     r["color"],
                    "timestamp": r["timestamp"],
                }
                for r in rows
            ]
        finally:
            conn.close()


# ── Helpers ────────────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_meeting(row: sqlite3.Row) -> dict:
    return {
        "id":          row["id"],
        "title":       row["title"],
        "topic":       row["topic"],
        "status":      row["status"],
        "started_at":  row["started_at"],
        "ended_at":    row["ended_at"],
        "agent_names": json.loads(row["agent_names"] or "[]"),
        "turn_count":  row["turn_count"],
    }


# ── Module-level singleton ─────────────────────────────────────────────────────
# initialize() is called by the FastAPI startup hook in api/main.py
store = MeetingStore()
