"""
Shared SQLite connection factory.

All persistence modules should call open_db() instead of repeating the
connection setup (check_same_thread, row_factory, WAL mode, FK enforcement).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path


def open_db(path: str | Path) -> sqlite3.Connection:
    """Open a SQLite connection with standard bank-simulator settings."""
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.commit()
    return conn
