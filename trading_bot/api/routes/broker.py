"""Broker routes for the trading bot API."""

import random
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trading_bot.api.models import BrokerInfo, OrderRequest
from trading_bot.execution.broker_base import OrderSide, OrderType
from trading_bot.execution.broker_manager import broker_manager

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


@router.get("/list")
async def get_broker_list() -> List[dict]:
    """Get list of available brokers."""
    return broker_manager.list_brokers()


@router.post("/connect/{broker_id}", response_model=ConnectResponse)
async def connect_broker(broker_id: str, request: ConnectRequest) -> dict:
    """Connect to a broker with credentials."""
    # Build credentials dict based on broker type
    credentials: Dict[str, str] = {}

    if broker_id in ["binance", "bybit", "okx", "kraken"]:
        # CCXT brokers need api_key and api_secret
        if not request.api_key or not request.api_secret:
            raise HTTPException(
                status_code=400,
                detail=f"Broker '{broker_id}' requires api_key and api_secret"
            )
        credentials = {
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "sandbox": "true" if request.environment in ["sandbox", "practice", "paper"] else "false"
        }
    elif broker_id == "oanda":
        # OANDA needs api_token and account_id
        if not request.api_token or not request.account_id:
            raise HTTPException(
                status_code=400,
                detail="OANDA requires api_token and account_id"
            )
        credentials = {
            "api_token": request.api_token,
            "account_id": request.account_id,
            "environment": request.environment if request.environment in ["practice", "live"] else "practice"
        }
    elif broker_id == "alpaca":
        # Alpaca needs api_key and api_secret
        if not request.api_key or not request.api_secret:
            raise HTTPException(
                status_code=400,
                detail="Alpaca requires api_key and api_secret"
            )
        credentials = {
            "api_key": request.api_key,
            "api_secret": request.api_secret,
            "environment": request.environment if request.environment in ["paper", "live"] else "paper"
        }
    else:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")

    # Attempt connection
    success = await broker_manager.connect(broker_id, credentials)

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
    success = await broker_manager.disconnect(broker_id)

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
    active = broker_manager.get_active_broker()
    if active:
        return active.get_info()
    return None


@router.post("/active/{broker_id}")
async def set_active_broker(broker_id: str) -> dict:
    """Set the active broker."""
    success = broker_manager.set_active_broker(broker_id)

    if not success:
        raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")

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
    broker_order = await broker_manager.place_order(
        broker_id=order.broker_id,
        symbol=order.symbol,
        side=side,
        quantity=order.quantity,
        order_type=order_type,
        price=order.price,
    )

    if not broker_order:
        raise HTTPException(status_code=500, detail="Failed to place order")

    return {
        "success": True,
        "order_id": broker_order.order_id,
        "status": broker_order.status.value,
        "symbol": broker_order.symbol,
        "side": broker_order.side.value,
        "quantity": broker_order.quantity,
        "price": broker_order.price,
        "message": f"{order.side.upper()} order placed for {order.quantity} {order.symbol}",
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
        broker_positions = await broker_manager.get_positions(broker_id)
        for pos in broker_positions:
            if symbol and pos.symbol != symbol:
                continue
            positions.append({
                "symbol": pos.symbol,
                "broker_id": pos.broker_id,
                "quantity": pos.quantity,
                "side": pos.side,
                "avg_entry": pos.entry_price,
                "current_price": pos.current_price,
                "unrealized_pnl": round(pos.unrealized_pnl, 2),
                "unrealized_pnl_pct": round(
                    (pos.unrealized_pnl / denom) * 100, 2
                ) if (denom := pos.entry_price * pos.quantity) > 0 else 0.0,
            })
    else:
        # Get positions from all connected brokers
        for broker_info in broker_manager.list_brokers():
            if broker_info["connected"]:
                broker_positions = await broker_manager.get_positions(broker_info["id"])
                for pos in broker_positions:
                    if symbol and pos.symbol != symbol:
                        continue
                    positions.append({
                        "symbol": pos.symbol,
                        "broker_id": pos.broker_id,
                        "quantity": pos.quantity,
                        "side": pos.side,
                        "avg_entry": pos.entry_price,
                        "current_price": pos.current_price,
                        "unrealized_pnl": round(pos.unrealized_pnl, 2),
                        "unrealized_pnl_pct": round(
                            (pos.unrealized_pnl / denom) * 100, 2
                        ) if (denom := pos.entry_price * pos.quantity) > 0 else 0.0,
                    })

    # Return actual positions only — no mock data
    return positions


@router.get("/orders")
async def get_orders(
    broker_id: Optional[str] = Query(None, description="Filter by broker"),
    status: Optional[str] = Query(None, description="Filter by status: open, filled, cancelled")
) -> List[dict]:
    """Get order history."""
    # Return empty list when no persistent order storage is configured
    orders = []

    if broker_id:
        # Query from broker if connected
        status_info = broker_manager.get_broker_status(broker_id)
        if status_info["connected"]:
            pass  # TODO: fetch real orders from broker API

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

    balance = await broker_manager.get_balance(broker_id)

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
    success = await broker_manager.cancel_order(broker_id, order_id)

    if success:
        return {
            "success": True,
            "message": f"Order {order_id} cancelled",
            "timestamp": datetime.now().isoformat()
        }
    else:
        raise HTTPException(status_code=400, detail=f"Failed to cancel order {order_id}")
