"""SQLite database connection and initialization."""

import sqlite3
import threading
from pathlib import Path
from typing import Optional

from trading_bot.persistence.schema import SCHEMA_SQL

_db_path: Optional[Path] = None
_local = threading.local()
_DEFAULT_DB_PATH = Path("./data/trading_bot.db")


def init_db(path: Path) -> None:
    """Set the global DB path and ensure schema exists."""
    global _db_path
    _db_path = path
    existing_conn = getattr(_local, "conn", None)
    if existing_conn is not None:
        existing_conn.close()
        _local.conn = None
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.executescript(SCHEMA_SQL)
    cols = [row[1] for row in conn.execute("PRAGMA table_info(paper_orders)").fetchall()]
    if "strategy_id" not in cols:
        conn.execute("ALTER TABLE paper_orders ADD COLUMN strategy_id TEXT")
    copy_trade_cols = [row[1] for row in conn.execute("PRAGMA table_info(copy_trades)").fetchall()]
    if copy_trade_cols and "signal_id" not in copy_trade_cols:
        conn.execute("ALTER TABLE copy_trades ADD COLUMN signal_id TEXT REFERENCES signal_predictions(signal_id)")
    copy_trade_migrations = {
        "remaining_quantity": "ALTER TABLE copy_trades ADD COLUMN remaining_quantity REAL NOT NULL DEFAULT 0.0",
        "initial_stop_loss": "ALTER TABLE copy_trades ADD COLUMN initial_stop_loss REAL NOT NULL DEFAULT 0.0",
        "realized_pnl_tp1": "ALTER TABLE copy_trades ADD COLUMN realized_pnl_tp1 REAL NOT NULL DEFAULT 0.0",
        "realized_pnl_tp2": "ALTER TABLE copy_trades ADD COLUMN realized_pnl_tp2 REAL NOT NULL DEFAULT 0.0",
        "partial_exit_count": "ALTER TABLE copy_trades ADD COLUMN partial_exit_count INTEGER NOT NULL DEFAULT 0",
        "tp1_hit": "ALTER TABLE copy_trades ADD COLUMN tp1_hit INTEGER NOT NULL DEFAULT 0",
        "tp2_hit": "ALTER TABLE copy_trades ADD COLUMN tp2_hit INTEGER NOT NULL DEFAULT 0",
        "tp3_hit": "ALTER TABLE copy_trades ADD COLUMN tp3_hit INTEGER NOT NULL DEFAULT 0",
        "stop_moved_to_breakeven": "ALTER TABLE copy_trades ADD COLUMN stop_moved_to_breakeven INTEGER NOT NULL DEFAULT 0",
        "trailing_stop_active": "ALTER TABLE copy_trades ADD COLUMN trailing_stop_active INTEGER NOT NULL DEFAULT 0",
        "max_favorable_price": "ALTER TABLE copy_trades ADD COLUMN max_favorable_price REAL",
        "max_adverse_price": "ALTER TABLE copy_trades ADD COLUMN max_adverse_price REAL",
    }
    for col, sql in copy_trade_migrations.items():
        if copy_trade_cols and col not in copy_trade_cols:
            conn.execute(sql)
    if copy_trade_cols:
        conn.execute(
            "UPDATE copy_trades SET remaining_quantity=quantity "
            "WHERE COALESCE(remaining_quantity, 0) <= 0"
        )
        conn.execute(
            "UPDATE copy_trades SET remaining_quantity=0.0 "
            "WHERE status NOT IN ('open', 'partial_tp1', 'partial_tp2')"
        )
        conn.execute(
            "UPDATE copy_trades SET initial_stop_loss=stop_loss "
            "WHERE COALESCE(initial_stop_loss, 0) <= 0"
        )
        conn.execute(
            "UPDATE copy_trades SET max_favorable_price=entry_price "
            "WHERE max_favorable_price IS NULL"
        )
        conn.execute(
            "UPDATE copy_trades SET max_adverse_price=entry_price "
            "WHERE max_adverse_price IS NULL"
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_copy_trades_status_created_at "
        "ON copy_trades(status, created_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_copy_trades_signal_status "
        "ON copy_trades(signal_id, status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_copy_trades_closed_at "
        "ON copy_trades(closed_at DESC)"
    )
    conn.commit()
    conn.close()


def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (reused within the same thread)."""
    if _db_path is None:
        init_db(_DEFAULT_DB_PATH)
    conn = getattr(_local, "conn", None)
    if conn is None:
        conn = sqlite3.connect(str(_db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        _local.conn = conn
    return conn
