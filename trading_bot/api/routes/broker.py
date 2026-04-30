"""Broker routes for the trading bot API."""

import csv
import io
import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from trading_bot.api.models import OrderRequest
from trading_bot.execution.broker_base import OrderSide, OrderType
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager
from trading_bot.persistence import repositories as repo

router = APIRouter(prefix="/api/broker", tags=["broker"])


class ConnectRequest(BaseModel):
    """Broker connection request."""
    api_key: Optional[str] = None
    api_secret: Optional[str] = None
    api_token: Optional[str] = None
    account_id: Optional[str] = None
    environment: Optional[str] = "sandbox"


class ConnectResponse(BaseModel):
    """Broker connection response."""
    status: str
    broker_id: str
    message: str
    timestamp: str


class ModifyTradeRequest(BaseModel):
    """Request to modify SL/TP on an open trade."""
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


async def _safe_refresh_broker_ledger(
    broker_id: str,
    symbol: Optional[str],
    count: int,
) -> bool:
    try:
        await broker_manager.get_positions(broker_id)
        await broker_manager.get_orders(broker_id, count=count, symbol=symbol)
        await broker_manager.get_trade_history(broker_id, count=count, symbol=symbol)
        return True
    except BrokerOperationError:
        return False


def _serialize_order(order) -> dict:
    created_at = order.created_at.isoformat() if getattr(order, "created_at", None) else None
    updated_at = order.updated_at.isoformat() if getattr(order, "updated_at", None) else created_at

    return {
        "order_id": order.order_id,
        "symbol": order.symbol,
        "side": order.side.value,
        "order_type": order.order_type.value,
        "quantity": order.quantity,
        "price": order.price,
        "status": order.status.value,
        "filled_quantity": order.filled_quantity,
        "avg_fill_price": order.avg_fill_price,
        "stop_loss": getattr(order, "stop_loss", None),
        "take_profit_1": getattr(order, "take_profit_1", None),
        "take_profit_2": getattr(order, "take_profit_2", None),
        "take_profit_3": getattr(order, "take_profit_3", None),
        "broker_id": order.broker_id,
        "created_at": created_at,
        "updated_at": updated_at,
    }


async def _refresh_trade_ledger_sources(
    broker_id: Optional[str],
    symbol: Optional[str],
    count: int,
) -> List[str]:
    connected_brokers: List[str] = []
    if broker_id:
        status_info = broker_manager.get_broker_status(broker_id)
        if status_info["exists"] and status_info["connected"]:
            if await _safe_refresh_broker_ledger(broker_id, symbol, count):
                connected_brokers.append(broker_id)
        return connected_brokers

    for broker_info in broker_manager.list_brokers():
        if not broker_info["connected"]:
            continue
        current_broker_id = broker_info["id"]
        if await _safe_refresh_broker_ledger(current_broker_id, symbol, count):
            connected_brokers.append(current_broker_id)
    return connected_brokers


def _ledger_summary(entries: List[dict], connected_brokers: List[str]) -> dict:
    open_entries = [entry for entry in entries if entry["status"] in {"open", "pending", "partially_filled"}]
    total_unrealized = sum(float(entry.get("unrealized_pnl") or 0.0) for entry in open_entries)
    total_realized = sum(float(entry.get("realized_pnl") or 0.0) for entry in entries)
    return {
        "total_entries": len(entries),
        "open_entries": len(open_entries),
        "realized_pnl": round(total_realized, 2),
        "unrealized_pnl": round(total_unrealized, 2),
        "connected_brokers": connected_brokers,
    }


def _raise_broker_error(exc: BrokerOperationError) -> None:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail)


@router.get("/list")
async def get_broker_list() -> List[dict]:
    """Get list of available brokers."""
    return broker_manager.list_brokers()


@router.post("/connect/{broker_id}", response_model=ConnectResponse)
async def connect_broker(broker_id: str, request: ConnectRequest) -> dict:
    """Connect to a broker with credentials."""
    credentials: Dict[str, Any] = {
        key: value
        for key, value in request.model_dump().items()
        if value is not None and value != ""
    }

    try:
        success = await broker_manager.connect(broker_id, credentials)
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    if success:
        return {
            "status": "connected",
            "broker_id": broker_id,
            "message": f"Successfully connected to {broker_id}",
            "timestamp": datetime.now().isoformat()
        }
    else:
        raise HTTPException(
            status_code=400,
            detail=f"Failed to connect to {broker_id}. Check your credentials."
        )


@router.post("/disconnect/{broker_id}")
async def disconnect_broker(broker_id: str) -> dict:
    """Disconnect from a broker."""
    try:
        success = await broker_manager.disconnect(broker_id)
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    return {
        "status": "disconnected" if success else "error",
        "broker_id": broker_id,
        "message": f"Disconnected from {broker_id}" if success else f"Failed to disconnect from {broker_id}",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/status/{broker_id}")
async def get_broker_status(broker_id: str) -> dict:
    """Get connection status for a broker."""
    status = broker_manager.get_broker_status(broker_id)

    if not status["exists"]:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")

    is_connected = status["connected"]

    return {
        "broker_id": broker_id,
        "connected": is_connected,
        "is_active": status["is_active"],
        "latency_ms": 45.0 if is_connected else None,
        "last_ping": datetime.now().isoformat() if is_connected else None,
        "api_version": "v3" if is_connected else None,
        "rate_limit_remaining": 1000 if is_connected else 0
    }


@router.get("/active")
async def get_active_broker() -> Optional[dict]:
    """Get the currently active broker."""
    return broker_manager.get_active_broker_info()


@router.post("/active/{broker_id}")
async def set_active_broker(broker_id: str) -> dict:
    """Set the active broker."""
    try:
        broker_manager.set_active_broker(broker_id)
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    return {
        "status": "success",
        "broker_id": broker_id,
        "message": f"{broker_id} is now the active broker",
        "timestamp": datetime.now().isoformat()
    }


@router.post("/order")
async def place_order(order: OrderRequest) -> dict:
    """Place a new order."""
    # Validate broker exists and is connected
    status = broker_manager.get_broker_status(order.broker_id)
    if not status["exists"]:
        raise HTTPException(status_code=404, detail=f"Broker '{order.broker_id}' not found")

    if not status["connected"]:
        raise HTTPException(
            status_code=400,
            detail=f"Broker '{order.broker_id}' is not connected"
        )

    # Map order side and type
    try:
        side = OrderSide(order.side.lower())
        order_type = OrderType(order.order_type.lower())
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid side '{order.side}' or order_type '{order.order_type}'"
        )

    # Place order
    try:
        broker_order = await broker_manager.place_order(
            broker_id=order.broker_id,
            symbol=order.symbol,
            side=side,
            quantity=order.quantity,
            order_type=order_type,
            price=order.price,
            stop_loss=order.stop_loss,
            take_profit_1=order.take_profit_1,
            take_profit_2=order.take_profit_2,
            take_profit_3=order.take_profit_3,
        )
        if order.signal_id:
            repo.upsert_trade_ledger_entry({
                "broker_id": order.broker_id,
                "source_type": "trade" if str(broker_order.order_id).startswith("trade:") else "order",
                "source_id": str(broker_order.order_id).split("trade:", 1)[1] if str(broker_order.order_id).startswith("trade:") else broker_order.order_id,
                "signal_id": order.signal_id,
                "symbol": broker_order.symbol,
                "side": broker_order.side.value,
                "status": broker_order.status.value,
                "quantity": broker_order.quantity,
                "remaining_quantity": max(broker_order.quantity - broker_order.filled_quantity, 0.0),
                "entry_price": broker_order.avg_fill_price or broker_order.price,
                "current_price": broker_order.avg_fill_price or broker_order.price,
                "stop_loss": broker_order.stop_loss,
                "take_profit_1": broker_order.take_profit_1,
                "take_profit_2": broker_order.take_profit_2,
                "take_profit_3": broker_order.take_profit_3,
                "metadata": {"event": "signal_linked_order", "order_id": broker_order.order_id},
            })
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    return {
        "success": True,
        "order_id": broker_order.order_id,
        "status": broker_order.status.value,
        "symbol": broker_order.symbol,
        "side": broker_order.side.value,
        "quantity": broker_order.quantity,
        "price": broker_order.price,
        "stop_loss": broker_order.stop_loss,
        "take_profit_1": broker_order.take_profit_1,
        "take_profit_2": broker_order.take_profit_2,
        "take_profit_3": broker_order.take_profit_3,
        "message": f"{broker_order.side.value.upper()} order placed for {broker_order.quantity} {broker_order.symbol}",
        "timestamp": datetime.now().isoformat()
    }


@router.get("/positions")
async def get_positions(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    symbol: Optional[str] = Query(None, description="Filter by symbol")
) -> List[dict]:
    """Get current positions."""
    positions = []

    # If broker_id specified, get positions from that broker
    if broker_id:
        try:
            broker_positions = await broker_manager.get_positions(broker_id)
        except BrokerOperationError as exc:
            _raise_broker_error(exc)
        for pos in broker_positions:
            if symbol and pos.symbol != symbol:
                continue
            positions.append({
                "position_id": pos.position_id,
                "symbol": pos.symbol,
                "broker_id": pos.broker_id,
                "quantity": pos.quantity,
                "side": pos.side,
                "avg_entry": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": pos.unrealized_pnl,
                "unrealized_pnl_pct": round(
                    (pos.unrealized_pnl / denom) * 100, 2
                ) if (denom := pos.entry_price * pos.quantity) > 0 else 0.0,
                "opened_at": pos.opened_at,
                "last_updated": datetime.now().isoformat(),
            })
    else:
        # Get positions from all connected brokers
        for broker_info in broker_manager.list_brokers():
            if broker_info["connected"]:
                try:
                    broker_positions = await broker_manager.get_positions(broker_info["id"])
                except BrokerOperationError:
                    continue
                for pos in broker_positions:
                    if symbol and pos.symbol != symbol:
                        continue
                    positions.append({
                        "position_id": pos.position_id,
                        "symbol": pos.symbol,
                        "broker_id": pos.broker_id,
                        "quantity": pos.quantity,
                        "side": pos.side,
                        "avg_entry": pos.entry_price,
                        "current_price": pos.current_price,
                        "unrealized_pnl": pos.unrealized_pnl,
                        "unrealized_pnl_pct": round(
                            (pos.unrealized_pnl / denom) * 100, 2
                        ) if (denom := pos.entry_price * pos.quantity) > 0 else 0.0,
                        "opened_at": pos.opened_at,
                        "last_updated": datetime.now().isoformat(),
                    })

    # Return actual positions only — no mock data
    return positions


@router.get("/orders")
async def get_orders(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by status: pending, open, filled, partially_filled, cancelled, rejected"),
    count: int = Query(20, description="Number of orders to fetch", ge=1, le=200),
) -> List[dict]:
    """Get recent orders and their statuses."""
    orders = []

    if broker_id:
        status_info = broker_manager.get_broker_status(broker_id)
        if not status_info["exists"]:
            raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")
        if status_info["connected"]:
            try:
                broker_orders = await broker_manager.get_orders(
                    broker_id,
                    count=count,
                    symbol=symbol,
                    status=status,
                )
            except BrokerOperationError as exc:
                _raise_broker_error(exc)
            orders.extend(_serialize_order(order) for order in broker_orders)
    else:
        for broker_info in broker_manager.list_brokers():
            if broker_info["connected"]:
                try:
                    broker_orders = await broker_manager.get_orders(
                        broker_info["id"],
                        count=count,
                        symbol=symbol,
                        status=status,
                    )
                except BrokerOperationError:
                    continue
                orders.extend(_serialize_order(order) for order in broker_orders)

    return orders


@router.get("/balance/{broker_id}")
async def get_balance(broker_id: str) -> dict:
    """Get account balance for a broker."""
    status = broker_manager.get_broker_status(broker_id)

    if not status["exists"]:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")

    if not status["connected"]:
        return {
            "broker_id": broker_id,
            "connected": False,
            "balances": []
        }

    try:
        balance = await broker_manager.get_balance(broker_id)
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    if not balance:
        # Return unavailable state instead of mock data
        return {
            "broker_id": broker_id,
            "connected": True,
            "status": "balance_unavailable",
            "total_equity": None,
            "available_margin": None,
            "used_margin": None,
            "currency": "USD",
            "balances": []
        }

    return {
        "broker_id": broker_id,
        "connected": True,
        "total_equity": balance.total_equity,
        "available_margin": balance.available_margin,
        "used_margin": balance.used_margin,
        "currency": balance.currency,
        "balances": [
            {"asset": balance.currency, "free": balance.available_margin, "locked": balance.used_margin}
        ]
    }


@router.delete("/order/{broker_id}/{order_id}")
async def cancel_order_endpoint(broker_id: str, order_id: str) -> dict:
    """Cancel an order."""
    try:
        success = await broker_manager.cancel_order(broker_id, order_id)
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    if success:
        return {
            "success": True,
            "message": f"Order {order_id} cancelled",
            "timestamp": datetime.now().isoformat()
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to cancel order {order_id}")


@router.post("/close-position/{broker_id}")
async def close_position(
    broker_id: str,
    symbol: str = Query(..., description="Symbol to close"),
    position_id: Optional[str] = Query(None, description="Specific trade or position identifier to close"),
) -> dict:
    """Close an open position."""
    status = broker_manager.get_broker_status(broker_id)
    if not status["exists"]:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")
    if not status["connected"]:
        raise HTTPException(status_code=400, detail=f"Broker '{broker_id}' is not connected")

    try:
        success = await broker_manager.close_position(
            broker_id,
            symbol,
            position_id=position_id,
        )
    except BrokerOperationError as exc:
        _raise_broker_error(exc)
    if success:
        message = (
            f"Position {position_id} closed for {symbol}"
            if position_id
            else f"Position closed for {symbol}"
        )
        return {
            "success": True,
            "message": message,
            "timestamp": datetime.now().isoformat()
        }
    else:
        detail = (
            f"Failed to close position {position_id} for {symbol}"
            if position_id
            else f"Failed to close position for {symbol}"
        )
        raise HTTPException(status_code=400, detail=detail)


@router.put("/trade/{broker_id}/{trade_id}")
async def modify_trade_endpoint(
    broker_id: str,
    trade_id: str,
    body: ModifyTradeRequest,
) -> dict:
    """Modify stop loss and/or take profit on an open trade."""
    status = broker_manager.get_broker_status(broker_id)
    if not status["exists"]:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")
    if not status["connected"]:
        raise HTTPException(status_code=400, detail=f"Broker '{broker_id}' is not connected")

    try:
        success = await broker_manager.modify_trade(
            broker_id=broker_id,
            trade_id=trade_id,
            stop_loss=body.stop_loss,
            take_profit=body.take_profit,
        )
    except BrokerOperationError as exc:
        _raise_broker_error(exc)

    if success:
        return {
            "success": True,
            "trade_id": trade_id,
            "stop_loss": body.stop_loss,
            "take_profit": body.take_profit,
            "message": f"Trade {trade_id} modified",
            "timestamp": datetime.now().isoformat(),
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to modify trade {trade_id}")


@router.get("/trade-history")
async def get_trade_history(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    count: int = Query(50, description="Number of trades to fetch", ge=1, le=200),
) -> List[dict]:
    """Get closed trade history from broker."""
    trades: List[dict] = []

    if broker_id:
        status_info = broker_manager.get_broker_status(broker_id)
        if not status_info["exists"]:
            raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")
        if status_info["connected"]:
            try:
                trades = await broker_manager.get_trade_history(broker_id, count=count, symbol=symbol)
            except BrokerOperationError as exc:
                _raise_broker_error(exc)
    else:
        for broker_info in broker_manager.list_brokers():
            if broker_info["connected"]:
                try:
                    history = await broker_manager.get_trade_history(
                        broker_info["id"], count=count, symbol=symbol
                    )
                except BrokerOperationError:
                    continue
                trades.extend(history)

    return trades


@router.get("/ledger")
async def get_trade_ledger(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by ledger status"),
    count: int = Query(100, description="Number of entries to fetch", ge=1, le=500),
) -> dict:
    """Get the unified trade ledger reconciled from positions, orders, and history."""
    connected_brokers = await _refresh_trade_ledger_sources(broker_id, symbol, count)

    entries = repo.get_trade_ledger_entries(
        broker_id=broker_id,
        symbol=symbol,
        status=status,
        limit=count,
    )

    return {
        "entries": entries,
        "summary": _ledger_summary(entries, connected_brokers),
    }


@router.get("/ledger/export")
async def export_trade_ledger_csv(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    status: Optional[str] = Query(None, description="Filter by ledger status"),
    count: int = Query(500, description="Number of entries to export", ge=1, le=2000),
) -> StreamingResponse:
    """Export the unified trade ledger as CSV."""
    await _refresh_trade_ledger_sources(broker_id, symbol, min(count, 500))
    entries = repo.get_trade_ledger_entries(
        broker_id=broker_id,
        symbol=symbol,
        status=status,
        limit=count,
    )
    output = io.StringIO()
    fieldnames = [
        "ledger_id",
        "broker_id",
        "source_type",
        "source_id",
        "signal_id",
        "symbol",
        "side",
        "status",
        "outcome",
        "quantity",
        "remaining_quantity",
        "entry_price",
        "current_price",
        "exit_price",
        "stop_loss",
        "take_profit_1",
        "take_profit_2",
        "take_profit_3",
        "realized_pnl",
        "unrealized_pnl",
        "r_multiple",
        "mfe",
        "mae",
        "opened_at",
        "closed_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for entry in entries:
        writer.writerow({key: entry.get(key) for key in fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=live_trade_ledger.csv"},
    )
