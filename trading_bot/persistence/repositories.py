"""Repository helpers for SQLite persistence."""

import json
import time
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
        "SELECT id, name, config_json, created_at FROM saved_scanners ORDER BY created_at DESC"
    ).fetchall()
    return [{"id": r["id"], "name": r["name"], "config": json.loads(r["config_json"]),
             "created_at": r["created_at"]} for r in rows]


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
    get_conn().execute(
        """INSERT INTO paper_orders
        (trade_id, symbol, side, quantity, entry_price, stop_loss,
         take_profit_1, take_profit_2, take_profit_3, status, pnl,
         risk_percent, trade_style, confidence, opened_at)
        VALUES (:trade_id, :symbol, :side, :quantity, :entry_price, :stop_loss,
                :take_profit_1, :take_profit_2, :take_profit_3, :status, :pnl,
                :risk_percent, :trade_style, :confidence, :opened_at)""",
        trade,
    )
    get_conn().commit()


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
        (copy_trade_id, symbol, direction, quantity, entry_price, current_price,
         stop_loss, take_profit1, take_profit2, take_profit3, confidence,
         risk_percent, status, unrealized_pnl, realized_pnl, trade_style,
         timeframe, signal_source, created_at, closed_at)
        VALUES (:copy_trade_id, :symbol, :direction, :quantity, :entry_price,
                :current_price, :stop_loss, :take_profit1, :take_profit2,
                :take_profit3, :confidence, :risk_percent, :status,
                :unrealized_pnl, :realized_pnl, :trade_style, :timeframe,
                :signal_source, :created_at, :closed_at)""",
        trade,
    )
    get_conn().commit()


def get_open_copy_trades() -> List[dict]:
    rows = get_conn().execute(
        "SELECT * FROM copy_trades WHERE status='open' ORDER BY created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_copy_trade(copy_trade_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM copy_trades WHERE copy_trade_id=?", (copy_trade_id,)
    ).fetchone()
    return dict(row) if row else None


def update_copy_trade(copy_trade_id: str, **kwargs: Any) -> None:
    sets = []
    vals: list = []
    for k, v in kwargs.items():
        sets.append(f"{k}=?")
        vals.append(v)
    if sets:
        vals.append(copy_trade_id)
        get_conn().execute(
            f"UPDATE copy_trades SET {','.join(sets)} WHERE copy_trade_id=?", vals
        )
        get_conn().commit()


def get_copy_history(limit: int = 20, symbol: Optional[str] = None) -> List[dict]:
    q = "SELECT * FROM copy_trades WHERE status != 'open'"
    params: list = []
    if symbol:
        q += " AND symbol=?"
        params.append(symbol)
    q += " ORDER BY closed_at DESC LIMIT ?"
    params.append(limit)
    rows = get_conn().execute(q, params).fetchall()
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
    }


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
