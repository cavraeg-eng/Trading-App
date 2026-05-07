"""Application settings repository helpers."""

from typing import Dict, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "get_setting",
    "set_setting",
    "get_all_settings",
    "delete_setting",
]


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
