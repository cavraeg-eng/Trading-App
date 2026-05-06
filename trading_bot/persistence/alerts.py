"""Smart alert repository helpers."""

import json
from typing import List, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "create_alert",
    "get_alerts",
    "get_unread_count",
    "mark_read",
    "mark_all_read",
    "get_recent_alert",
]


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
    return cur.lastrowid


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
