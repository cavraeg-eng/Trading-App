"""Saved scanner repository helpers."""

import json
from typing import List

from trading_bot.persistence.db import get_conn


__all__ = [
    "save_scanner",
    "get_saved_scanners",
    "update_scanner",
    "delete_scanner",
]


def save_scanner(name: str, config: dict) -> int:
    cur = get_conn().execute(
        "INSERT INTO saved_scanners (name, config_json) VALUES (?,?)",
        (name, json.dumps(config)),
    )
    get_conn().commit()
    return cur.lastrowid


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
