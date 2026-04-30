"""Repository helpers for SQLite persistence."""

import json
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from trading_bot.persistence.db import get_conn


# ── App Settings ─────────────────────────────────────────────────────────────

def get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    row = get_conn().execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    get_conn().execute(
        "INSERT INTO app_settings (key, value, updated_at) VALUES (?,?,datetime('now')) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
        (key, value),
    )
    get_conn().commit()


def get_all_settings() -> Dict[str, str]:
    rows = get_conn().execute("SELECT key, value FROM app_settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def delete_setting(key: str) -> None:
    get_conn().execute("DELETE FROM app_settings WHERE key=?", (key,))
    get_conn().commit()


# ── Saved Scanners ───────────────────────────────────────────────────────────

def save_scanner(name: str, config: dict) -> int:
    cur = get_conn().execute(
        "INSERT INTO saved_scanners (name, config_json) VALUES (?,?)",
        (name, json.dumps(config)),
    )
    get_conn().commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_saved_scanners() -> List[dict]:
    rows = get_conn().execute(
        "SELECT id, name, config_json, created_at, updated_at FROM saved_scanners ORDER BY updated_at DESC, created_at DESC"
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "config": json.loads(r["config_json"]),
             "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows]


def update_scanner(scanner_id: int, name: str, config: dict) -> bool:
    cur = get_conn().execute(
        "UPDATE saved_scanners SET name=?, config_json=?, updated_at=datetime('now') WHERE id=?",
        (name, json.dumps(config), scanner_id),
    )
    get_conn().commit()
    return cur.rowcount > 0


def delete_scanner(scanner_id: int) -> bool:
    cur = get_conn().execute("DELETE FROM saved_scanners WHERE id=?", (scanner_id,))
    get_conn().commit()
    return cur.rowcount > 0


# ── Paper Trading ────────────────────────────────────────────────────────────

def get_paper_account() -> dict:
    row = get_conn().execute("SELECT * FROM paper_account WHERE id=1").fetchone()
    return dict(row) if row else {"balance": 10000.0, "equity": 10000.0, "initial_balance": 10000.0}


def update_paper_balance(balance: float, equity: float) -> None:
    get_conn().execute(
        "UPDATE paper_account SET balance=?, equity=?, updated_at=datetime('now') WHERE id=1",
        (balance, equity),
    )
    get_conn().commit()


def insert_paper_order(trade: dict) -> None:
    payload = {
        "strategy_id": None,
        "confidence": None,
        **trade,
    }
    get_conn().execute(
        """INSERT INTO paper_orders
        (trade_id, symbol, side, quantity, entry_price, stop_loss,
         take_profit_1, take_profit_2, take_profit_3, status, pnl,
         risk_percent, trade_style, strategy_id, confidence, opened_at)
        VALUES (:trade_id, :symbol, :side, :quantity, :entry_price, :stop_loss,
                :take_profit_1, :take_profit_2, :take_profit_3, :status, :pnl,
                :risk_percent, :trade_style, :strategy_id, :confidence, :opened_at)""",
        payload,
    )
    get_conn().commit()


def save_strategy_performance_snapshot(strategy_id: str, payload: dict) -> None:
    set_setting(f"strategy:{strategy_id}:performance_snapshot", json.dumps(payload))


def get_strategy_performance_snapshot(strategy_id: str) -> Optional[dict]:
    raw = get_setting(f"strategy:{strategy_id}:performance_snapshot")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def get_paper_positions() -> List[dict]:
    rows = get_conn().execute(
        "SELECT * FROM paper_orders WHERE status='filled' AND closed_at IS NULL ORDER BY opened_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_paper_history() -> List[dict]:
    rows = get_conn().execute(
        "SELECT * FROM paper_orders ORDER BY opened_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def reset_paper_account() -> None:
    conn = get_conn()
    conn.execute("DELETE FROM paper_orders")
    conn.execute("UPDATE paper_account SET balance=10000.0, equity=10000.0, updated_at=datetime('now') WHERE id=1")
    conn.commit()


# ── Copy Trading ─────────────────────────────────────────────────────────────

def get_copy_settings() -> dict:
    row = get_conn().execute("SELECT * FROM copy_settings WHERE id=1").fetchone()
    d = dict(row)
    d["enabled"] = bool(d["enabled"])
    d["auto_close_on_signal_expire"] = bool(d["auto_close_on_signal_expire"])
    d["allowed_symbols"] = json.loads(d.pop("allowed_symbols_json"))
    d.pop("id", None)
    d.pop("updated_at", None)
    return d


def update_copy_settings(**kwargs: Any) -> None:
    allowed = {
        "enabled", "max_position_size_lots", "max_risk_percent",
        "max_concurrent_positions", "lot_size_scale",
        "auto_close_on_signal_expire", "allowed_symbols", "min_confidence",
    }
    sets = []
    vals: list = []
    for k, v in kwargs.items():
        if k not in allowed or v is None:
            continue
        if k == "allowed_symbols":
            sets.append("allowed_symbols_json=?")
            vals.append(json.dumps(v))
        elif k in ("enabled", "auto_close_on_signal_expire"):
            sets.append(f"{k}=?")
            vals.append(int(v))
        else:
            sets.append(f"{k}=?")
            vals.append(v)
    if sets:
        sets.append("updated_at=datetime('now')")
        get_conn().execute(f"UPDATE copy_settings SET {','.join(sets)} WHERE id=1", vals)
        get_conn().commit()


def insert_copy_trade(trade: dict) -> None:
    get_conn().execute(
        """INSERT INTO copy_trades
        (copy_trade_id, signal_id, symbol, direction, quantity, remaining_quantity,
         entry_price, current_price, initial_stop_loss, stop_loss, take_profit1,
         take_profit2, take_profit3, confidence, risk_percent, status,
         unrealized_pnl, realized_pnl, realized_pnl_tp1, realized_pnl_tp2,
         partial_exit_count, tp1_hit, tp2_hit, tp3_hit, stop_moved_to_breakeven,
         trailing_stop_active, max_favorable_price, max_adverse_price,
         trade_style, timeframe, signal_source, created_at, closed_at)
        VALUES (:copy_trade_id, :signal_id, :symbol, :direction, :quantity, :remaining_quantity,
                :entry_price, :current_price, :initial_stop_loss, :stop_loss, :take_profit1,
                :take_profit2, :take_profit3, :confidence, :risk_percent, :status,
                :unrealized_pnl, :realized_pnl, :realized_pnl_tp1, :realized_pnl_tp2,
                :partial_exit_count, :tp1_hit, :tp2_hit, :tp3_hit, :stop_moved_to_breakeven,
                :trailing_stop_active, :max_favorable_price, :max_adverse_price,
                :trade_style, :timeframe, :signal_source, :created_at, :closed_at)""",
        trade,
    )
    get_conn().commit()


def get_open_copy_trades() -> List[dict]:
    rows = get_conn().execute(
        "SELECT * FROM copy_trades WHERE status IN ('open', 'partial_tp1', 'partial_tp2') ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_copy_trade(copy_trade_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM copy_trades WHERE copy_trade_id=?", (copy_trade_id,)
    ).fetchone()
    return dict(row) if row else None


def get_signal_prediction(signal_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM signal_predictions WHERE signal_id=?",
        (signal_id,),
    ).fetchone()
    return dict(row) if row else None


def get_open_copy_trade_for_signal(signal_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM copy_trades WHERE signal_id=? AND status IN ('open', 'partial_tp1', 'partial_tp2') ORDER BY created_at DESC LIMIT 1",
        (signal_id,),
    ).fetchone()
    return dict(row) if row else None


def update_copy_trade(copy_trade_id: str, **kwargs: Any) -> None:
    allowed = {
        "current_price",
        "unrealized_pnl",
        "realized_pnl",
        "realized_pnl_tp1",
        "realized_pnl_tp2",
        "status",
        "closed_at",
        "remaining_quantity",
        "partial_exit_count",
        "tp1_hit",
        "tp2_hit",
        "tp3_hit",
        "stop_loss",
        "stop_moved_to_breakeven",
        "trailing_stop_active",
        "max_favorable_price",
        "max_adverse_price",
    }
    sets = []
    vals: list = []
    for k, v in kwargs.items():
        if k not in allowed:
            continue
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        vals.append(copy_trade_id)
        get_conn().execute(
            f"UPDATE copy_trades SET {','.join(sets)} WHERE copy_trade_id=?", vals
        )
        get_conn().commit()


def _build_copy_history_where_clause(
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
) -> tuple[str, list]:
    where = " WHERE status NOT IN ('open', 'partial_tp1', 'partial_tp2')"
    params: list = []
    if symbol:
        where += " AND symbol=?"
        params.append(symbol)
    if status:
        where += " AND status=?"
        params.append(status)
    if direction:
        where += " AND direction=?"
        params.append(direction)
    if from_ts is not None:
        where += " AND closed_at>=?"
        params.append(from_ts)
    if to_ts is not None:
        where += " AND closed_at<=?"
        params.append(to_ts)
    return where, params


def count_copy_history(
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
) -> int:
    where, params = _build_copy_history_where_clause(
        symbol=symbol,
        status=status,
        direction=direction,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    row = get_conn().execute(
        f"SELECT COUNT(*) AS total FROM copy_trades{where}",
        params,
    ).fetchone()
    return int(row["total"]) if row else 0


def get_copy_history(
    limit: int = 20,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = None,
    from_ts: Optional[float] = None,
    to_ts: Optional[float] = None,
    offset: int = 0,
    sort_by: str = "closed_at",
    sort_dir: str = "desc",
) -> List[dict]:
    allowed_sort_columns = {
        "closed_at": "closed_at",
        "created_at": "created_at",
        "symbol": "symbol",
        "direction": "direction",
        "status": "status",
        "realized_pnl": "realized_pnl",
        "confidence": "confidence",
    }
    sort_column = allowed_sort_columns.get(sort_by, "closed_at")
    sort_direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    where, params = _build_copy_history_where_clause(
        symbol=symbol,
        status=status,
        direction=direction,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    query = (
        f"SELECT * FROM copy_trades{where} "
        f"ORDER BY {sort_column} {sort_direction}, copy_trade_id DESC LIMIT ? OFFSET ?"
    )
    rows = get_conn().execute(query, [*params, limit, offset]).fetchall()
    return [dict(r) for r in rows]


# ── Signal Predictions ───────────────────────────────────────────────────────

def insert_signal_prediction(pred: dict) -> None:
    get_conn().execute(
        """INSERT OR REPLACE INTO signal_predictions
        (signal_id, symbol, direction, confidence, entry_min, entry_max,
         stop_loss, take_profit1, take_profit2, take_profit3, timeframe,
         trade_style, source, price_source, created_at)
        VALUES (:signal_id, :symbol, :direction, :confidence, :entry_min,
                :entry_max, :stop_loss, :take_profit1, :take_profit2,
                :take_profit3, :timeframe, :trade_style, :source,
                :price_source, :created_at)""",
        pred,
    )
    get_conn().commit()


def insert_signal_outcome(outcome: dict) -> None:
    get_conn().execute(
        """INSERT OR REPLACE INTO signal_outcomes
        (signal_id, resolved_reason, resolved_at, exit_price, pnl_pips, direction_correct)
        VALUES (:signal_id, :resolved_reason, :resolved_at, :exit_price, :pnl_pips, :direction_correct)""",
        outcome,
    )
    get_conn().commit()


def get_signal_metrics(symbol: Optional[str] = None, timeframe: Optional[str] = None,
                       limit: int = 100) -> Dict[str, Any]:
    """Compute aggregate accuracy metrics from stored outcomes."""
    q = """
        SELECT p.symbol, p.direction, p.confidence, p.timeframe, p.source,
               o.resolved_reason, o.direction_correct, o.pnl_pips
        FROM signal_predictions p
        JOIN signal_outcomes o ON p.signal_id = o.signal_id
        WHERE 1=1
    """
    params: list = []
    if symbol:
        q += " AND p.symbol=?"
        params.append(symbol)
    if timeframe:
        q += " AND p.timeframe=?"
        params.append(timeframe)
    q += " ORDER BY p.created_at DESC LIMIT ?"
    params.append(limit)

    rows = get_conn().execute(q, params).fetchall()
    total = len(rows)
    if total == 0:
        return {"total": 0, "directional_accuracy": None, "avg_pnl_pips": None}

    correct = sum(1 for r in rows if r["direction_correct"])
    avg_pnl = sum(r["pnl_pips"] or 0 for r in rows) / total

    return {
        "total": total,
        "directional_accuracy": round(correct / total * 100, 1),
        "avg_pnl_pips": round(avg_pnl, 2),
        "by_source": _group_accuracy(rows, "source"),
        "by_timeframe": _group_accuracy(rows, "timeframe"),
        "by_symbol": _group_accuracy(rows, "symbol"),
        "by_direction": _group_accuracy(rows, "direction"),
        "resolved_reason_breakdown": _group_reason_counts(rows),
    }


def get_signal_outcome_summary(
    symbol: Optional[str] = None,
    timeframe: Optional[str] = None,
    direction: Optional[str] = None,
    limit: int = 50,
) -> Dict[str, Any]:
    q = """
        SELECT p.symbol, p.timeframe, p.direction,
               o.resolved_reason, o.direction_correct, o.pnl_pips
        FROM signal_predictions p
        JOIN signal_outcomes o ON p.signal_id = o.signal_id
        WHERE 1=1
    """
    params: list = []
    if symbol:
        q += " AND p.symbol=?"
        params.append(symbol)
    if timeframe:
        q += " AND p.timeframe=?"
        params.append(timeframe)
    if direction:
        q += " AND p.direction=?"
        params.append(direction.upper())
    q += " ORDER BY p.created_at DESC LIMIT ?"
    params.append(limit)

    rows = get_conn().execute(q, params).fetchall()
    total = len(rows)
    if total == 0:
        return {
            "sampleSize": 0,
            "tpHits": 0,
            "slHits": 0,
            "expired": 0,
            "replaced": 0,
            "tpHitRate": 0.0,
            "slHitRate": 0.0,
            "expiredRate": 0.0,
            "directionalAccuracy": None,
            "avgPnlPips": None,
            "resolvedReasonBreakdown": {},
        }

    tp_hits = sum(1 for row in rows if row["resolved_reason"] == "TP_HIT")
    sl_hits = sum(1 for row in rows if row["resolved_reason"] == "SL_HIT")
    expired = sum(1 for row in rows if row["resolved_reason"] == "EXPIRED")
    replaced = sum(1 for row in rows if row["resolved_reason"] in {"REPLACED", "DIVERGED"})
    correct = sum(1 for row in rows if row["direction_correct"])
    avg_pnl = sum(float(row["pnl_pips"] or 0.0) for row in rows) / total

    return {
        "sampleSize": total,
        "tpHits": tp_hits,
        "slHits": sl_hits,
        "expired": expired,
        "replaced": replaced,
        "tpHitRate": round(tp_hits / total, 3),
        "slHitRate": round(sl_hits / total, 3),
        "expiredRate": round(expired / total, 3),
        "directionalAccuracy": round(correct / total * 100, 1),
        "avgPnlPips": round(avg_pnl, 2),
        "resolvedReasonBreakdown": _group_reason_counts(rows),
    }


# ── Smart Alerts ────────────────────────────────────────────────────────────

def create_alert(
    symbol: str,
    alert_type: str,
    title: str,
    message: str,
    severity: str = "info",
    data: Optional[str] = None,
) -> int:
    """Insert a new smart alert and return its id."""
    cur = get_conn().execute(
        "INSERT INTO smart_alerts (symbol, alert_type, title, message, severity, data) "
        "VALUES (?,?,?,?,?,?)",
        (symbol, alert_type, title, message, severity, data),
    )
    get_conn().commit()
    return cur.lastrowid  # type: ignore[return-value]


def get_alerts(unread_only: bool = False, limit: int = 50) -> List[dict]:
    """Return alerts ordered newest-first."""
    q = "SELECT * FROM smart_alerts"
    params: list = []
    if unread_only:
        q += " WHERE read=0"
    q += " ORDER BY created_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(q, params).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d["read"] = bool(d["read"])
        if d.get("data"):
            try:
                d["data"] = json.loads(d["data"])
            except (json.JSONDecodeError, TypeError):
                pass
        result.append(d)
    return result


def get_unread_count() -> int:
    """Return count of unread alerts."""
    row = get_conn().execute("SELECT COUNT(*) as cnt FROM smart_alerts WHERE read=0").fetchone()
    return row["cnt"] if row else 0


def mark_read(alert_id: int) -> bool:
    """Mark a single alert as read. Returns True if a row was updated."""
    cur = get_conn().execute("UPDATE smart_alerts SET read=1 WHERE id=?", (alert_id,))
    get_conn().commit()
    return cur.rowcount > 0


def mark_all_read() -> int:
    """Mark all alerts as read. Returns number of rows updated."""
    cur = get_conn().execute("UPDATE smart_alerts SET read=1 WHERE read=0")
    get_conn().commit()
    return cur.rowcount


def get_recent_alert(symbol: str, alert_type: str, minutes: int = 5) -> Optional[dict]:
    """Return the most recent alert of given type/symbol within the last N minutes."""
    row = get_conn().execute(
        "SELECT * FROM smart_alerts WHERE symbol=? AND alert_type=? "
        "AND created_at >= datetime('now', ? || ' minutes') "
        "ORDER BY created_at DESC LIMIT 1",
        (symbol, alert_type, str(-minutes)),
    ).fetchone()
    return dict(row) if row else None


def _group_accuracy(rows: list, key: str) -> dict:
    groups: Dict[str, list] = {}
    for r in rows:
        g = r[key] or "unknown"
        groups.setdefault(g, []).append(r)
    result = {}
    for g, items in groups.items():
        correct = sum(1 for i in items if i["direction_correct"])
        result[g] = {"total": len(items), "accuracy": round(correct / len(items) * 100, 1)}
    return result


def _group_reason_counts(rows: list) -> dict:
    result: Dict[str, int] = {}
    for row in rows:
        reason = row["resolved_reason"] or "UNKNOWN"
        result[reason] = result.get(reason, 0) + 1
    return result


def insert_automation_execution(strategy_id: str, symbol: str, action: str, status: str,
                                detail: Optional[dict] = None) -> None:
    get_conn().execute(
        """INSERT INTO automation_executions
        (strategy_id, symbol, action, status, detail_json)
        VALUES (?, ?, ?, ?, ?)""",
        (strategy_id, symbol, action, status, json.dumps(detail or {})),
    )
    get_conn().commit()


def get_automation_executions(limit: int = 20, strategy_id: Optional[str] = None) -> List[dict]:
    query = "SELECT * FROM automation_executions"
    params: list = []
    if strategy_id:
        query += " WHERE strategy_id=?"
        params.append(strategy_id)
    query += " ORDER BY id DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        raw_detail = item.get("detail_json")
        if raw_detail:
            try:
                item["detail"] = json.loads(raw_detail)
            except json.JSONDecodeError:
                item["detail"] = {}
        else:
            item["detail"] = {}
        result.append(item)
    return result


def count_recent_automation_executions(strategy_id: str, window_seconds: int) -> int:
    row = get_conn().execute(
        """SELECT COUNT(*) AS count
        FROM automation_executions
        WHERE strategy_id=?
          AND action='execute'
          AND status='success'
          AND created_at >= datetime('now', ?)""",
        (strategy_id, f"-{window_seconds} seconds"),
    ).fetchone()
    return int(row["count"]) if row else 0


def upsert_trade_ledger_entry(entry: dict) -> str:
    payload = {
        "ledger_id": entry.get("ledger_id") or str(uuid.uuid4()),
        "broker_id": entry["broker_id"],
        "source_type": entry["source_type"],
        "source_id": str(entry["source_id"]),
        "signal_id": entry.get("signal_id"),
        "symbol": entry["symbol"],
        "side": entry.get("side") or "unknown",
        "status": entry.get("status") or "unknown",
        "quantity": float(entry.get("quantity") or 0.0),
        "remaining_quantity": entry.get("remaining_quantity"),
        "entry_price": entry.get("entry_price"),
        "current_price": entry.get("current_price"),
        "exit_price": entry.get("exit_price"),
        "stop_loss": entry.get("stop_loss"),
        "take_profit_1": entry.get("take_profit_1"),
        "take_profit_2": entry.get("take_profit_2"),
        "take_profit_3": entry.get("take_profit_3"),
        "unrealized_pnl": float(entry.get("unrealized_pnl") or 0.0),
        "realized_pnl": float(entry.get("realized_pnl") or 0.0),
        "max_favorable_price": entry.get("max_favorable_price"),
        "max_adverse_price": entry.get("max_adverse_price"),
        "mfe": entry.get("mfe"),
        "mae": entry.get("mae"),
        "r_multiple": entry.get("r_multiple"),
        "outcome": entry.get("outcome"),
        "opened_at": entry.get("opened_at"),
        "closed_at": entry.get("closed_at"),
        "metadata_json": json.dumps(entry.get("metadata") or {}),
    }
    existing = get_conn().execute(
        "SELECT ledger_id FROM trade_ledger_entries WHERE broker_id=? AND source_type=? AND source_id=?",
        (payload["broker_id"], payload["source_type"], payload["source_id"]),
    ).fetchone()
    if existing:
        payload["ledger_id"] = existing["ledger_id"]
    get_conn().execute(
        """INSERT INTO trade_ledger_entries
        (ledger_id, broker_id, source_type, source_id, signal_id, symbol, side, status,
         quantity, remaining_quantity, entry_price, current_price, exit_price,
         stop_loss, take_profit_1, take_profit_2, take_profit_3, unrealized_pnl,
         realized_pnl, max_favorable_price, max_adverse_price, mfe, mae, r_multiple,
         outcome, opened_at, closed_at, updated_at, metadata_json)
        VALUES (:ledger_id, :broker_id, :source_type, :source_id, :signal_id, :symbol, :side, :status,
                :quantity, :remaining_quantity, :entry_price, :current_price, :exit_price,
                :stop_loss, :take_profit_1, :take_profit_2, :take_profit_3, :unrealized_pnl,
                :realized_pnl, :max_favorable_price, :max_adverse_price, :mfe, :mae, :r_multiple,
                :outcome, :opened_at, :closed_at, datetime('now'), :metadata_json)
        ON CONFLICT(broker_id, source_type, source_id) DO UPDATE SET
            signal_id=COALESCE(excluded.signal_id, trade_ledger_entries.signal_id),
            symbol=excluded.symbol,
            side=excluded.side,
            status=excluded.status,
            quantity=excluded.quantity,
            remaining_quantity=excluded.remaining_quantity,
            entry_price=excluded.entry_price,
            current_price=excluded.current_price,
            exit_price=excluded.exit_price,
            stop_loss=excluded.stop_loss,
            take_profit_1=excluded.take_profit_1,
            take_profit_2=excluded.take_profit_2,
            take_profit_3=excluded.take_profit_3,
            unrealized_pnl=excluded.unrealized_pnl,
            realized_pnl=excluded.realized_pnl,
            max_favorable_price=COALESCE(excluded.max_favorable_price, trade_ledger_entries.max_favorable_price),
            max_adverse_price=COALESCE(excluded.max_adverse_price, trade_ledger_entries.max_adverse_price),
            mfe=COALESCE(excluded.mfe, trade_ledger_entries.mfe),
            mae=COALESCE(excluded.mae, trade_ledger_entries.mae),
            r_multiple=COALESCE(excluded.r_multiple, trade_ledger_entries.r_multiple),
            outcome=COALESCE(excluded.outcome, trade_ledger_entries.outcome),
            opened_at=COALESCE(trade_ledger_entries.opened_at, excluded.opened_at),
            closed_at=excluded.closed_at,
            updated_at=excluded.updated_at,
            metadata_json=excluded.metadata_json""",
        payload,
    )
    get_conn().commit()
    return payload["ledger_id"]


def update_trade_ledger_status(
    broker_id: str,
    source_type: str,
    source_id: str,
    status: str,
    metadata: Optional[dict] = None,
) -> bool:
    cur = get_conn().execute(
        """UPDATE trade_ledger_entries
        SET status=?, updated_at=datetime('now'), metadata_json=COALESCE(?, metadata_json)
        WHERE broker_id=? AND source_type=? AND source_id=?""",
        (
            status,
            json.dumps(metadata) if metadata is not None else None,
            broker_id,
            source_type,
            str(source_id),
        ),
    )
    get_conn().commit()
    return cur.rowcount > 0


def get_trade_ledger_entries(
    broker_id: Optional[str] = None,
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    side: Optional[str] = None,
    outcome: Optional[str] = None,
    limit: int = 100,
) -> List[dict]:
    query = "SELECT * FROM trade_ledger_entries WHERE 1=1"
    params: list = []
    if broker_id:
        query += " AND broker_id=?"
        params.append(broker_id)
    if symbol:
        query += " AND symbol=?"
        params.append(symbol)
    if status:
        query += " AND status=?"
        params.append(status)
    if side:
        query += " AND side=?"
        params.append(side)
    if outcome:
        query += " AND outcome=?"
        params.append(outcome)
    query += " ORDER BY updated_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(query, params).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        raw = item.pop("metadata_json", None)
        try:
            item["metadata"] = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            item["metadata"] = {}
        result.append(item)
    return result


def get_trade_ledger_metrics(
    broker_id: Optional[str] = None,
    symbol: Optional[str] = None,
    limit: int = 500,
) -> Dict[str, Any]:
    entries = get_trade_ledger_entries(broker_id=broker_id, symbol=symbol, limit=limit)
    closed_entries = [
        entry for entry in entries
        if entry.get("closed_at") or entry.get("status") in {"closed", "filled", "cancelled", "rejected"}
    ]
    open_entries = [
        entry for entry in entries
        if entry.get("status") in {"open", "pending", "partially_filled"}
    ]
    wins = [entry for entry in closed_entries if float(entry.get("realized_pnl") or 0.0) > 0]
    losses = [entry for entry in closed_entries if float(entry.get("realized_pnl") or 0.0) < 0]
    gross_profit = sum(float(entry.get("realized_pnl") or 0.0) for entry in wins)
    gross_loss = abs(sum(float(entry.get("realized_pnl") or 0.0) for entry in losses))
    r_values = [float(entry["r_multiple"]) for entry in closed_entries if entry.get("r_multiple") is not None]
    mfe_values = [float(entry["mfe"]) for entry in closed_entries if entry.get("mfe") is not None]
    mae_values = [float(entry["mae"]) for entry in closed_entries if entry.get("mae") is not None]

    by_symbol: Dict[str, Dict[str, Any]] = {}
    for entry in closed_entries:
        bucket = by_symbol.setdefault(entry["symbol"], {"symbol": entry["symbol"], "total": 0, "wins": 0, "pnl": 0.0})
        bucket["total"] += 1
        bucket["wins"] += 1 if float(entry.get("realized_pnl") or 0.0) > 0 else 0
        bucket["pnl"] += float(entry.get("realized_pnl") or 0.0)

    return {
        "total_entries": len(entries),
        "open_entries": len(open_entries),
        "closed_entries": len(closed_entries),
        "realized_pnl": round(sum(float(entry.get("realized_pnl") or 0.0) for entry in closed_entries), 2),
        "unrealized_pnl": round(sum(float(entry.get("unrealized_pnl") or 0.0) for entry in open_entries), 2),
        "win_rate": round(len(wins) / len(closed_entries) * 100, 1) if closed_entries else 0.0,
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "avg_r_multiple": round(sum(r_values) / len(r_values), 2) if r_values else None,
        "avg_mfe": round(sum(mfe_values) / len(mfe_values), 5) if mfe_values else None,
        "avg_mae": round(sum(mae_values) / len(mae_values), 5) if mae_values else None,
        "by_symbol": [
            {
                "symbol": bucket["symbol"],
                "total": bucket["total"],
                "win_rate": round(bucket["wins"] / bucket["total"] * 100, 1) if bucket["total"] else 0.0,
                "realized_pnl": round(bucket["pnl"], 2),
            }
            for bucket in sorted(by_symbol.values(), key=lambda item: item["pnl"], reverse=True)
        ],
    }
