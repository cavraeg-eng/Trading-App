"""Copy trading settings, position, and history repository helpers."""

import json
from typing import Any, List, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "get_copy_settings",
    "update_copy_settings",
    "insert_copy_trade",
    "get_open_copy_trades",
    "get_copy_trade",
    "get_open_copy_trade_for_signal",
    "update_copy_trade",
    "count_copy_history",
    "get_copy_history",
]


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
