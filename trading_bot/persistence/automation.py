"""Automation execution activity repository helpers."""

import json
from typing import List, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "insert_automation_execution",
    "get_automation_executions",
    "count_recent_automation_executions",
]


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
