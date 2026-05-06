"""Trade ledger repository helpers."""

import json
import uuid
from typing import Any, Dict, List, Optional

from trading_bot.persistence.db import get_conn


__all__ = [
    "upsert_trade_ledger_entry",
    "update_trade_ledger_status",
    "get_trade_ledger_entries",
    "get_trade_ledger_metrics",
]


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
