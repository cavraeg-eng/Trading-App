"""SQLite database connection and initialization."""

import os
import sqlite3
import threading
from pathlib import Path
from typing import Optional, Union

from trading_bot.persistence.schema import SCHEMA_SQL

_db_path: Optional[Path] = None
_local = threading.local()
_DEFAULT_DB_PATH = Path("./data/trading_bot.db")
_REQUIRED_TABLES = {
    "app_settings",
    "paper_account",
    "paper_orders",
    "copy_settings",
    "copy_trades",
    "signal_predictions",
    "trade_ledger_entries",
}


class PersistenceError(RuntimeError):
    """Actionable persistence-layer failure."""


class ActionableConnection(sqlite3.Connection):
    """SQLite connection that raises persistence errors with recovery context."""

    persistence_path: str

    def _wrap_sqlite_error(self, operation: str) -> PersistenceError:
        path = getattr(self, "persistence_path", "unknown")
        return PersistenceError(
            f"SQLite operation '{operation}' failed for database '{path}'. "
            "Check database initialization, local file permissions, and schema compatibility."
        )

    def execute(self, sql: str, parameters=(), /):  # type: ignore[override]
        try:
            return super().execute(sql, parameters)
        except sqlite3.Error as exc:
            raise self._wrap_sqlite_error("execute") from exc

    def executemany(self, sql: str, parameters, /):  # type: ignore[override]
        try:
            return super().executemany(sql, parameters)
        except sqlite3.Error as exc:
            raise self._wrap_sqlite_error("executemany") from exc

    def executescript(self, sql_script: str, /):  # type: ignore[override]
        try:
            return super().executescript(sql_script)
        except sqlite3.Error as exc:
            raise self._wrap_sqlite_error("executescript") from exc

    def commit(self) -> None:
        try:
            return super().commit()
        except sqlite3.Error as exc:
            raise self._wrap_sqlite_error("commit") from exc


def get_default_db_path() -> Path:
    """Return the configured default database path."""
    return Path(os.getenv("TRADING_BOT_DB_PATH") or _DEFAULT_DB_PATH).expanduser()


def _coerce_path(path: Union[Path, str]) -> Path:
    return Path(path).expanduser()


def _close_thread_connection() -> None:
    existing_conn = getattr(_local, "conn", None)
    if existing_conn is not None:
        existing_conn.close()
        _local.conn = None


def _prepare_parent_directory(path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise PersistenceError(
            f"Could not create parent directory for SQLite database at '{path}'. "
            "Check TRADING_BOT_DB_PATH and local filesystem permissions."
        ) from exc


def _open_sqlite_connection(path: Path, *, check_same_thread: bool = True) -> sqlite3.Connection:
    _prepare_parent_directory(path)
    try:
        conn = sqlite3.connect(
            str(path),
            check_same_thread=check_same_thread,
            factory=ActionableConnection,
        )
        conn.persistence_path = str(path)
        return conn
    except sqlite3.Error as exc:
        raise PersistenceError(
            f"Could not open SQLite database at '{path}'. "
            "Check TRADING_BOT_DB_PATH, ensure the parent directory exists, and verify the file is writable."
        ) from exc


def _table_columns(conn: sqlite3.Connection, table_name: str) -> list[str]:
    return [row[1] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]


def _ensure_trade_ledger_schema(conn: sqlite3.Connection) -> None:
    ledger_cols = _table_columns(conn, "trade_ledger_entries")
    if not ledger_cols:
        return

    ledger_migrations = {
        "signal_id": "ALTER TABLE trade_ledger_entries ADD COLUMN signal_id TEXT",
        "max_favorable_price": "ALTER TABLE trade_ledger_entries ADD COLUMN max_favorable_price REAL",
        "max_adverse_price": "ALTER TABLE trade_ledger_entries ADD COLUMN max_adverse_price REAL",
        "mfe": "ALTER TABLE trade_ledger_entries ADD COLUMN mfe REAL",
        "mae": "ALTER TABLE trade_ledger_entries ADD COLUMN mae REAL",
        "r_multiple": "ALTER TABLE trade_ledger_entries ADD COLUMN r_multiple REAL",
        "outcome": "ALTER TABLE trade_ledger_entries ADD COLUMN outcome TEXT",
    }
    for col, sql in ledger_migrations.items():
        if col not in ledger_cols:
            conn.execute(sql)

    conn.execute(
        """DELETE FROM trade_ledger_entries
        WHERE rowid NOT IN (
            SELECT MAX(rowid)
            FROM trade_ledger_entries
            GROUP BY broker_id, source_type, source_id
        )"""
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_ledger_unique_source "
        "ON trade_ledger_entries(broker_id, source_type, source_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_ledger_broker_symbol "
        "ON trade_ledger_entries(broker_id, symbol, updated_at DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_trade_ledger_status "
        "ON trade_ledger_entries(status, updated_at DESC)"
    )


def _apply_schema(conn: sqlite3.Connection, path: Path) -> None:
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA_SQL)
        cols = _table_columns(conn, "paper_orders")
        if "strategy_id" not in cols:
            conn.execute("ALTER TABLE paper_orders ADD COLUMN strategy_id TEXT")
        copy_trade_cols = _table_columns(conn, "copy_trades")
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
        _ensure_trade_ledger_schema(conn)
        conn.commit()
    except (sqlite3.Error, PersistenceError) as exc:
        conn.rollback()
        raise PersistenceError(
            f"Failed to initialize SQLite schema at '{path}'. "
            "Delete the local runtime database to recreate it, or inspect the schema migration error."
        ) from exc


def _database_file_missing(path: Path) -> bool:
    return not path.exists()


def _missing_required_tables(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    existing = {row[0] for row in rows}
    return _REQUIRED_TABLES - existing


def init_db(path: Union[Path, str]) -> None:
    """Set the global DB path and ensure schema exists."""
    global _db_path
    db_path = _coerce_path(path)
    _close_thread_connection()
    conn = _open_sqlite_connection(db_path)
    try:
        _apply_schema(conn, db_path)
    finally:
        conn.close()
    _db_path = db_path


def get_conn() -> sqlite3.Connection:
    """Return a thread-local SQLite connection (reused within the same thread)."""
    if _db_path is None:
        init_db(get_default_db_path())
    db_path = _db_path
    conn = getattr(_local, "conn", None)
    if conn is not None and db_path is not None and _database_file_missing(db_path):
        _close_thread_connection()
        init_db(db_path)
        conn = None
    if conn is None:
        if db_path is None:
            raise PersistenceError("SQLite database path is not configured. Call init_db() first.")
        if _database_file_missing(db_path):
            init_db(db_path)
        conn = _open_sqlite_connection(db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            if _missing_required_tables(conn):
                _apply_schema(conn, db_path)
        except (sqlite3.Error, PersistenceError) as exc:
            conn.close()
            raise PersistenceError(
                f"Failed to verify SQLite schema at '{db_path}'. "
                "Re-run database initialization or remove the local runtime database so it can be recreated."
            ) from exc
        _local.conn = conn
    return conn
