"""Copy trading API routes — now backed by SQLite persistence."""

import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trading_bot.api.routes.signals import get_base_price
from trading_bot.persistence import repositories as repo

router = APIRouter(prefix="/api/copy-trading", tags=["copy_trading"])


class UpdateSettingsRequest(BaseModel):
    enabled: Optional[bool] = None
    max_position_size_lots: Optional[float] = None
    max_risk_percent: Optional[float] = None
    max_concurrent_positions: Optional[int] = None
    lot_size_scale: Optional[float] = None
    auto_close_on_signal_expire: Optional[bool] = None
    allowed_symbols: Optional[List[str]] = None
    min_confidence: Optional[int] = None


class CopySignalRequest(BaseModel):
    symbol: str
    direction: str
    quantity: float
    entry_price: float
    stop_loss: float
    take_profit1: float
    take_profit2: float
    take_profit3: float
    confidence: int
    risk_percent: float
    trade_style: str = "swing"
    timeframe: str = "1h"


def _trade_to_dict(t: dict) -> dict:
    return {
        "copy_trade_id": t["copy_trade_id"],
        "symbol": t["symbol"],
        "direction": t["direction"],
        "quantity": t["quantity"],
        "entry_price": t["entry_price"],
        "current_price": t["current_price"],
        "stop_loss": t["stop_loss"],
        "take_profit1": t["take_profit1"],
        "take_profit2": t["take_profit2"],
        "take_profit3": t["take_profit3"],
        "confidence": t["confidence"],
        "risk_percent": t["risk_percent"],
        "status": t["status"],
        "unrealized_pnl": round(t["unrealized_pnl"], 2),
        "realized_pnl": round(t["realized_pnl"], 2),
        "created_at": t["created_at"],
        "closed_at": t["closed_at"],
        "trade_style": t["trade_style"],
        "timeframe": t["timeframe"],
        "signal_source": t["signal_source"],
    }


def _check_and_close(trade: dict, current_price: float) -> dict:
    """Check TP/SL and close if triggered; returns updated dict."""
    if trade["status"] != "open":
        return trade

    direction = trade["direction"]
    if direction == "BUY":
        trade["unrealized_pnl"] = round((current_price - trade["entry_price"]) * trade["quantity"], 2)
        if current_price >= trade["take_profit1"]:
            return _close(trade, current_price, "closed_tp")
        if current_price <= trade["stop_loss"]:
            return _close(trade, current_price, "closed_sl")
    else:
        trade["unrealized_pnl"] = round((trade["entry_price"] - current_price) * trade["quantity"], 2)
        if current_price <= trade["take_profit1"]:
            return _close(trade, current_price, "closed_tp")
        if current_price >= trade["stop_loss"]:
            return _close(trade, current_price, "closed_sl")

    trade["current_price"] = current_price
    repo.update_copy_trade(trade["copy_trade_id"],
                           current_price=current_price,
                           unrealized_pnl=trade["unrealized_pnl"])
    return trade


def _close(trade: dict, close_price: float, status: str) -> dict:
    if trade["direction"] == "BUY":
        trade["realized_pnl"] = round((close_price - trade["entry_price"]) * trade["quantity"], 2)
    else:
        trade["realized_pnl"] = round((trade["entry_price"] - close_price) * trade["quantity"], 2)
    trade["unrealized_pnl"] = 0.0
    trade["current_price"] = close_price
    trade["status"] = status
    trade["closed_at"] = time.time()
    repo.update_copy_trade(trade["copy_trade_id"],
                           current_price=close_price,
                           unrealized_pnl=0.0,
                           realized_pnl=trade["realized_pnl"],
                           status=status,
                           closed_at=trade["closed_at"])
    return trade


@router.get("/settings")
async def get_settings():
    return repo.get_copy_settings()


@router.post("/settings")
async def update_settings(body: UpdateSettingsRequest):
    repo.update_copy_settings(**body.dict(exclude_none=True))
    return repo.get_copy_settings()


@router.post("/copy-signal")
async def copy_signal(body: CopySignalRequest):
    settings = repo.get_copy_settings()

    if not settings["enabled"]:
        raise HTTPException(status_code=400, detail="Copy trading is not enabled.")
    if body.symbol not in settings["allowed_symbols"]:
        raise HTTPException(status_code=400, detail=f"Symbol {body.symbol} not allowed.")
    if body.confidence < settings["min_confidence"]:
        raise HTTPException(status_code=400, detail=f"Confidence {body.confidence} below minimum.")
    open_trades = repo.get_open_copy_trades()
    if len(open_trades) >= settings["max_concurrent_positions"]:
        raise HTTPException(status_code=400, detail="Max concurrent positions reached.")

    quantity = round(body.quantity * settings["lot_size_scale"], 2)
    quantity = min(quantity, settings["max_position_size_lots"])
    risk_percent = min(body.risk_percent, settings["max_risk_percent"])

    copy_trade_id = f"ct_{uuid.uuid4().hex[:8]}"
    trade = {
        "copy_trade_id": copy_trade_id,
        "symbol": body.symbol,
        "direction": body.direction.upper(),
        "quantity": quantity,
        "entry_price": body.entry_price,
        "current_price": body.entry_price,
        "stop_loss": body.stop_loss,
        "take_profit1": body.take_profit1,
        "take_profit2": body.take_profit2,
        "take_profit3": body.take_profit3,
        "confidence": body.confidence,
        "risk_percent": risk_percent,
        "status": "open",
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "trade_style": body.trade_style,
        "timeframe": body.timeframe,
        "signal_source": "AI",
        "created_at": time.time(),
        "closed_at": None,
    }
    repo.insert_copy_trade(trade)

    return {
        "success": True,
        "copy_trade_id": copy_trade_id,
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "quantity": trade["quantity"],
        "entry_price": trade["entry_price"],
        "stop_loss": trade["stop_loss"],
        "take_profit1": trade["take_profit1"],
        "status": "open",
        "message": f"Copied AI {trade['direction']} signal for {trade['symbol']} at {trade['entry_price']}",
    }


@router.get("/positions")
async def get_positions():
    trades = repo.get_open_copy_trades()
    for t in trades:
        current_price, _ = get_base_price(t["symbol"])
        _check_and_close(t, current_price)

    open_trades = repo.get_open_copy_trades()
    return {"positions": [_trade_to_dict(t) for t in open_trades], "count": len(open_trades)}


@router.post("/close/{copy_trade_id}")
async def close_position(copy_trade_id: str):
    trade = repo.get_copy_trade(copy_trade_id)
    if not trade or trade["status"] != "open":
        raise HTTPException(status_code=404, detail=f"No open position with id {copy_trade_id}")

    current_price, _ = get_base_price(trade["symbol"])
    trade = dict(trade)
    _close(trade, current_price, "closed_manual")

    return {
        "success": True,
        "copy_trade_id": trade["copy_trade_id"],
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "entry_price": trade["entry_price"],
        "close_price": trade["current_price"],
        "realized_pnl": trade["realized_pnl"],
        "status": trade["status"],
        "message": f"Manually closed {trade['direction']} {trade['symbol']} — P&L: {trade['realized_pnl']}",
    }


@router.get("/history")
async def get_history(limit: int = Query(20, ge=1), symbol: Optional[str] = None):
    trades = repo.get_copy_history(limit=limit, symbol=symbol)
    return {"history": [_trade_to_dict(t) for t in trades], "count": len(trades)}


@router.get("/stats")
async def get_stats():
    open_trades = repo.get_open_copy_trades()
    closed_trades = repo.get_copy_history(limit=1000)
    open_count = len(open_trades)
    closed_count = len(closed_trades)
    total_count = open_count + closed_count

    if closed_count == 0:
        return {
            "total_trades": total_count,
            "open_trades": open_count,
            "closed_trades": 0,
            "total_pnl": 0.0,
            "win_rate": 0.0,
            "avg_pnl": 0.0,
        }

    wins = sum(1 for t in closed_trades if t["realized_pnl"] > 0)
    total_pnl = sum(t["realized_pnl"] for t in closed_trades)

    return {
        "total_trades": total_count,
        "open_trades": open_count,
        "closed_trades": closed_count,
        "total_pnl": round(total_pnl, 2),
        "win_rate": round(wins / closed_count * 100, 1),
        "avg_pnl": round(total_pnl / closed_count, 2),
    }
