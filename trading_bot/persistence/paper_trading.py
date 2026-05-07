"""Paper trading account and order repository helpers."""

import json
from typing import List, Optional

from trading_bot.persistence.db import get_conn
from trading_bot.persistence.settings import get_setting, set_setting


__all__ = [
    "get_paper_account",
    "update_paper_balance",
    "insert_paper_order",
    "save_strategy_performance_snapshot",
    "get_strategy_performance_snapshot",
    "get_paper_positions",
    "get_paper_history",
    "reset_paper_account",
]


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
