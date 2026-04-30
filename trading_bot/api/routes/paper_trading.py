from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime
import asyncio
import time
import uuid

from trading_bot.persistence import repositories as repo
from trading_bot.persistence.db import PersistenceError

router = APIRouter(prefix="/api/trading", tags=["paper_trading"])

# In-memory paper trading state
_paper_account = {
    "balance": 10000.0,
    "equity": 10000.0,
    "positions": [],
    "trades_history": [],
    "initial_balance": 10000.0,
}

# Lock to serialize account state mutations
_account_lock = asyncio.Lock()


def restore_paper_trading_state() -> None:
    persisted = repo.get_paper_account()
    positions = repo.get_paper_positions()
    history = repo.get_paper_history()
    _paper_account["balance"] = persisted["balance"]
    _paper_account["equity"] = persisted["equity"]
    _paper_account["initial_balance"] = persisted["initial_balance"]
    _paper_account["positions"] = positions
    _paper_account["trades_history"] = history


class PaperOrderRequest(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_percent: Optional[float] = None
    trade_style: Optional[str] = None
    confidence: Optional[float] = None
    strategy_id: Optional[str] = None

@router.post("/paper-order")
async def place_paper_order(order: PaperOrderRequest):
    """Place a simulated paper trade."""
    async with _account_lock:
        # Validate
        if order.side not in ("buy", "sell"):
            raise HTTPException(status_code=400, detail="Side must be 'buy' or 'sell'")
        if order.quantity <= 0:
            raise HTTPException(status_code=400, detail="Quantity must be positive")

        # Validate entry price — market orders must include a valid current price
        if not order.price or order.price <= 0:
            raise HTTPException(status_code=400, detail="Market orders must include a valid current price")
        entry_price = order.price
    
        # Calculate notional value
        notional = order.quantity * entry_price if entry_price > 0 else 0

        # Check balance (simplified — just check we have capital)
        if _paper_account["balance"] <= 0:
            raise HTTPException(status_code=400, detail="Insufficient paper balance")

        # Create trade record
        trade_id = str(uuid.uuid4())[:8]
        trade = {
            "trade_id": trade_id,
            "symbol": order.symbol,
            "side": order.side,
            "quantity": round(order.quantity, 2),
            "entry_price": entry_price,
            "stop_loss": order.stop_loss,
            "take_profit_1": order.take_profit_1,
            "take_profit_2": order.take_profit_2,
            "take_profit_3": order.take_profit_3,
            "status": "filled",
            "opened_at": datetime.utcnow().isoformat(),
            "risk_percent": order.risk_percent,
            "trade_style": order.trade_style,
            "confidence": order.confidence,
            "strategy_id": order.strategy_id,
            "pnl": 0.0,
        }

        # Add to positions
        _paper_account["positions"].append(trade)
        _paper_account["trades_history"].append(trade)
        try:
            repo.insert_paper_order(
                {
                    "trade_id": trade_id,
                    "symbol": order.symbol,
                    "side": order.side,
                    "quantity": round(order.quantity, 2),
                    "entry_price": entry_price,
                    "stop_loss": order.stop_loss,
                    "take_profit_1": order.take_profit_1,
                    "take_profit_2": order.take_profit_2,
                    "take_profit_3": order.take_profit_3,
                    "status": "filled",
                    "pnl": 0.0,
                    "risk_percent": order.risk_percent,
                    "trade_style": order.trade_style,
                    "strategy_id": order.strategy_id,
                    "confidence": order.confidence,
                    "opened_at": str(time.time()),
                }
            )
        except PersistenceError as exc:
            _paper_account["positions"].remove(trade)
            _paper_account["trades_history"].remove(trade)
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    
        return {
            "success": True,
            "order_id": trade_id,
            "status": "filled",
            "symbol": order.symbol,
            "side": order.side,
            "quantity": round(order.quantity, 2),
            "entry_price": entry_price,
            "stop_loss": order.stop_loss,
            "take_profit_levels": [order.take_profit_1, order.take_profit_2, order.take_profit_3],
            "message": f"Paper {order.side.upper()} order filled: {round(order.quantity, 2)} {order.symbol} at {entry_price}",
            "timestamp": datetime.utcnow().isoformat(),
        }

@router.get("/paper-positions")
async def get_paper_positions():
    """Get current paper trading positions."""
    try:
        positions = repo.get_paper_positions()
        if positions:
            return {"positions": positions}
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"positions": _paper_account["positions"]}

@router.get("/paper-account")
async def get_paper_account():
    """Get paper trading account summary."""
    try:
        persisted = repo.get_paper_account()
        total_positions = len(repo.get_paper_positions())
    except PersistenceError:
        persisted = None
        total_positions = len(_paper_account["positions"])
    return {
        "balance": round((persisted or _paper_account)["balance"], 2),
        "equity": round((persisted or _paper_account)["equity"], 2),
        "initial_balance": (persisted or _paper_account)["initial_balance"],
        "total_positions": total_positions,
        "total_trades": len(_paper_account["trades_history"]),
    }

@router.delete("/paper-reset")
async def reset_paper_account():
    """Reset paper trading account to initial state."""
    _paper_account["balance"] = 10000.0
    _paper_account["equity"] = 10000.0
    _paper_account["positions"] = []
    _paper_account["trades_history"] = []
    try:
        repo.reset_paper_account()
    except PersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "message": "Paper account reset to $10,000"}
