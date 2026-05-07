"""Unified broker trade ledger reconciliation helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Union

from trading_bot.execution.broker_base import BrokerOrder, BrokerPosition, OrderStatus
from trading_bot.persistence import trade_ledger as repo


OPEN_ORDER_STATUSES = {
    OrderStatus.OPEN.value,
    OrderStatus.PENDING.value,
    OrderStatus.PARTIALLY_FILLED.value,
}
CLOSED_ORDER_STATUSES = {
    OrderStatus.FILLED.value,
    OrderStatus.CANCELLED.value,
    OrderStatus.REJECTED.value,
}


def _enum_value(value: Any) -> str:
    return getattr(value, "value", value) or "unknown"


def _position_source_id(position: BrokerPosition) -> str:
    return str(position.position_id or f"{position.symbol}:{position.side}")


def _order_source_type(order: BrokerOrder) -> str:
    return "trade" if str(order.order_id).startswith("trade:") else "order"


def _order_source_id(order: BrokerOrder) -> str:
    raw = str(order.order_id)
    return raw.split("trade:", 1)[1] if raw.startswith("trade:") else raw


def _iso(value: Any) -> Optional[str]:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _direction(side: str) -> str:
    if side in {"buy", "long", "BUY"}:
        return "buy"
    if side in {"sell", "short", "SELL"}:
        return "sell"
    return "unknown"


def _calc_outcome(
    side: str,
    entry_price: Optional[float],
    current_price: Optional[float],
    stop_loss: Optional[float],
    take_profit_1: Optional[float],
    take_profit_2: Optional[float],
    take_profit_3: Optional[float],
    status: str,
) -> Dict[str, Optional[Union[float, str]]]:
    entry = float(entry_price or 0.0)
    current = float(current_price or entry or 0.0)
    if entry <= 0 or current <= 0:
        return {"mfe": None, "mae": None, "r_multiple": None, "outcome": None}

    direction = _direction(side)
    favorable = current - entry if direction == "buy" else entry - current if direction == "sell" else 0.0
    adverse = min(favorable, 0.0)
    mfe = max(favorable, 0.0)
    mae = abs(adverse)

    risk_anchor = float(stop_loss or 0.0)
    risk = abs(entry - risk_anchor) if risk_anchor > 0 else 0.0
    r_multiple = favorable / risk if risk > 0 else None

    outcome = None
    if status in CLOSED_ORDER_STATUSES or status in {"closed", "closed_tp3", "closed_sl", "closed_manual"}:
        if stop_loss:
            stopped = current <= stop_loss if direction == "buy" else current >= stop_loss
            if stopped:
                outcome = "SL_HIT"
        for target in (take_profit_3, take_profit_2, take_profit_1):
            if target:
                reached = current >= target if direction == "buy" else current <= target
                if reached:
                    outcome = "TP_HIT"
                    break
        if outcome is None:
            outcome = "WIN" if favorable > 0 else "LOSS" if favorable < 0 else "BREAKEVEN"

    return {
        "mfe": round(mfe, 5),
        "mae": round(mae, 5),
        "r_multiple": round(r_multiple, 3) if r_multiple is not None else None,
        "outcome": outcome,
    }


def upsert_position(broker_id: str, position: BrokerPosition) -> str:
    metrics = _calc_outcome(
        position.side,
        position.entry_price,
        position.current_price,
        None,
        None,
        None,
        None,
        "open",
    )
    return repo.upsert_trade_ledger_entry({
        "broker_id": broker_id,
        "source_type": "position",
        "source_id": _position_source_id(position),
        "symbol": position.symbol,
        "side": position.side,
        "status": "open",
        "quantity": position.quantity,
        "remaining_quantity": position.quantity,
        "entry_price": position.entry_price,
        "current_price": position.current_price,
        "unrealized_pnl": position.unrealized_pnl,
        "realized_pnl": position.realized_pnl,
        "max_favorable_price": position.current_price if metrics["mfe"] else position.entry_price,
        "max_adverse_price": position.current_price if metrics["mae"] else position.entry_price,
        "mfe": metrics["mfe"],
        "mae": metrics["mae"],
        "opened_at": position.opened_at,
        "metadata": {"position_id": position.position_id},
    })


def upsert_order(broker_id: str, order: BrokerOrder) -> str:
    status = _enum_value(order.status)
    entry_price = order.avg_fill_price or order.price
    metrics = _calc_outcome(
        _enum_value(order.side),
        entry_price,
        entry_price,
        order.stop_loss,
        order.take_profit_1,
        order.take_profit_2,
        order.take_profit_3,
        status,
    )
    return repo.upsert_trade_ledger_entry({
        "broker_id": broker_id,
        "source_type": _order_source_type(order),
        "source_id": _order_source_id(order),
        "symbol": order.symbol,
        "side": _enum_value(order.side),
        "status": "open" if status in OPEN_ORDER_STATUSES else status,
        "quantity": order.quantity,
        "remaining_quantity": max(order.quantity - order.filled_quantity, 0.0),
        "entry_price": entry_price,
        "current_price": entry_price,
        "stop_loss": order.stop_loss,
        "take_profit_1": order.take_profit_1,
        "take_profit_2": order.take_profit_2,
        "take_profit_3": order.take_profit_3,
        "mfe": metrics["mfe"],
        "mae": metrics["mae"],
        "r_multiple": metrics["r_multiple"],
        "outcome": metrics["outcome"],
        "opened_at": _iso(order.created_at),
        "metadata": {
            "order_id": order.order_id,
            "order_type": _enum_value(order.order_type),
            "broker_status": status,
        },
    })


def upsert_history_trade(broker_id: str, trade: Dict[str, Any]) -> str:
    trade_id = str(trade.get("trade_id") or trade.get("id") or trade.get("order_id"))
    stop_loss = trade.get("stop_loss")
    take_profit_1 = trade.get("take_profit_1") or trade.get("take_profit1")
    take_profit_2 = trade.get("take_profit_2") or trade.get("take_profit2")
    take_profit_3 = trade.get("take_profit_3") or trade.get("take_profit3")
    metrics = _calc_outcome(
        trade.get("side") or trade.get("direction") or "unknown",
        trade.get("entry_price"),
        trade.get("exit_price") or trade.get("current_price"),
        stop_loss,
        take_profit_1,
        take_profit_2,
        take_profit_3,
        trade.get("state") or trade.get("status") or "closed",
    )
    return repo.upsert_trade_ledger_entry({
        "broker_id": broker_id,
        "source_type": "history",
        "source_id": trade_id,
        "symbol": trade.get("symbol") or "unknown",
        "side": trade.get("side") or trade.get("direction") or "unknown",
        "status": trade.get("state") or trade.get("status") or "closed",
        "quantity": trade.get("quantity") or trade.get("units") or 0.0,
        "remaining_quantity": 0.0,
        "entry_price": trade.get("entry_price"),
        "current_price": trade.get("exit_price") or trade.get("current_price"),
        "exit_price": trade.get("exit_price"),
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": take_profit_2,
        "take_profit_3": take_profit_3,
        "realized_pnl": trade.get("realized_pnl") or trade.get("pnl") or 0.0,
        "mfe": trade.get("mfe") or metrics["mfe"],
        "mae": trade.get("mae") or metrics["mae"],
        "r_multiple": trade.get("r_multiple") or metrics["r_multiple"],
        "outcome": trade.get("outcome") or metrics["outcome"],
        "opened_at": trade.get("opened_at"),
        "closed_at": trade.get("closed_at"),
        "metadata": trade,
    })


def reconcile_positions(broker_id: str, positions: Iterable[BrokerPosition]) -> List[str]:
    return [upsert_position(broker_id, position) for position in positions]


def reconcile_orders(broker_id: str, orders: Iterable[BrokerOrder]) -> List[str]:
    return [upsert_order(broker_id, order) for order in orders]


def reconcile_history(broker_id: str, trades: Iterable[Dict[str, Any]]) -> List[str]:
    return [upsert_history_trade(broker_id, trade) for trade in trades]
