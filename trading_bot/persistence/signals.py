"""Signal prediction and outcome repository helpers."""

import json
from typing import Any, Dict, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "get_signal_prediction",
    "insert_signal_prediction",
    "insert_signal_outcome",
    "get_signal_metrics",
    "get_signal_outcome_summary",
]


def get_signal_prediction(signal_id: str) -> Optional[dict]:
    row = get_conn().execute(
        "SELECT * FROM signal_predictions WHERE signal_id=?",
        (signal_id,),
    ).fetchone()
    return dict(row) if row else None


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
