"""SQLite database connection and initialization."""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from trading_bot.persistence.schema import SCHEMA_SQL

_db_path: Optional[Path] = None
_local = threading.local()


def init_db(path: Path) -> None:
    """Set the global DB path and ensure schema exists."""
    global _db_path
    _db_path = path
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_SQL)
    conn.close()


def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (reused within the same thread)."""
    if _db_path is None:
        raise RuntimeError("Database not initialized. Call init_db() first.")
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn
