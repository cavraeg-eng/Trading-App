"""Copy trading API routes — now backed by SQLite persistence."""

import csv
import io
import time
import uuid
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from trading_bot.api.routes.signals import (
    MAX_SIGNAL_AGE_CANDLES,
    TIMEFRAME_SECONDS,
    get_base_price,
)
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
    signal_id: str
    quantity: float = Field(gt=0)
    risk_percent: float = Field(gt=0)
    entry_price: Optional[float] = Field(default=None, gt=0)


def _calc_pnl(direction: str, entry_price: float, exit_price: float, quantity: float) -> float:
    if direction == "BUY":
        return float((exit_price - entry_price) * quantity)
    return float((entry_price - exit_price) * quantity)


def _round_pnl(value: float) -> float:
    absolute = abs(float(value))
    if absolute >= 100:
        return round(float(value), 2)
    if absolute >= 1:
        return round(float(value), 4)
    return round(float(value), 6)


def _stop_triggered(trade: dict, current_price: float) -> bool:
    if trade["direction"] == "BUY":
        return current_price <= trade["stop_loss"]
    return current_price >= trade["stop_loss"]


def _target_reached(trade: dict, target_key: str, current_price: float) -> bool:
    target_price = trade[target_key]
    if trade["direction"] == "BUY":
        return current_price >= target_price
    return current_price <= target_price


def _update_excursions(trade: dict, current_price: float) -> None:
    max_favorable_price = trade.get("max_favorable_price")
    max_adverse_price = trade.get("max_adverse_price")
    if trade["direction"] == "BUY":
        trade["max_favorable_price"] = current_price if max_favorable_price is None else max(max_favorable_price, current_price)
        trade["max_adverse_price"] = current_price if max_adverse_price is None else min(max_adverse_price, current_price)
    else:
        trade["max_favorable_price"] = current_price if max_favorable_price is None else min(max_favorable_price, current_price)
        trade["max_adverse_price"] = current_price if max_adverse_price is None else max(max_adverse_price, current_price)


def _apply_partial_exit(trade: dict, current_price: float, target_level: int) -> dict:
    target_flag = f"tp{target_level}_hit"
    if trade.get(target_flag):
        return trade

    if target_level == 1:
        exit_ratio = 0.5
    elif target_level == 2:
        exit_ratio = 0.3
    else:
        exit_ratio = 1.0

    remaining_quantity = float(trade["remaining_quantity"])
    exit_quantity = remaining_quantity if target_level == 3 else round(min(remaining_quantity, trade["quantity"] * exit_ratio), 8)
    if exit_quantity <= 0:
        return trade

    pnl = _calc_pnl(trade["direction"], trade["entry_price"], current_price, exit_quantity)
    trade["realized_pnl"] = round(float(trade["realized_pnl"]) + pnl, 2)
    trade["remaining_quantity"] = round(max(0.0, remaining_quantity - exit_quantity), 8)
    trade["partial_exit_count"] = int(trade.get("partial_exit_count", 0)) + 1
    trade[target_flag] = 1
    trade["current_price"] = current_price

    updates = {
        "current_price": current_price,
        "realized_pnl": trade["realized_pnl"],
        "remaining_quantity": trade["remaining_quantity"],
        "partial_exit_count": trade["partial_exit_count"],
        target_flag: 1,
    }

    if target_level == 1:
        trade["realized_pnl_tp1"] = pnl
        trade["stop_loss"] = trade["entry_price"]
        trade["stop_moved_to_breakeven"] = 1
        updates["realized_pnl_tp1"] = pnl
        updates["stop_loss"] = trade["stop_loss"]
        updates["stop_moved_to_breakeven"] = 1
    elif target_level == 2:
        trade["realized_pnl_tp2"] = pnl
        trade["trailing_stop_active"] = 1
        if trade["direction"] == "BUY":
            trade["stop_loss"] = max(float(trade["stop_loss"]), float(trade["take_profit1"]))
        else:
            trade["stop_loss"] = min(float(trade["stop_loss"]), float(trade["take_profit1"]))
        updates["realized_pnl_tp2"] = pnl
        updates["stop_loss"] = trade["stop_loss"]
        updates["trailing_stop_active"] = 1
    else:
        trade["tp3_hit"] = 1
        trade["remaining_quantity"] = 0.0
        trade["status"] = "closed_tp3"
        trade["unrealized_pnl"] = 0.0
        trade["closed_at"] = time.time()
        updates["tp3_hit"] = 1
        updates["remaining_quantity"] = 0.0
        updates["status"] = "closed_tp3"
        updates["unrealized_pnl"] = 0.0
        updates["closed_at"] = trade["closed_at"]

    repo.update_copy_trade(trade["copy_trade_id"], **updates)
    return trade


def _maybe_trail_stop(trade: dict, current_price: float) -> None:
    if not trade.get("trailing_stop_active"):
        return
    if trade["direction"] == "BUY":
        candidate = max(float(trade["stop_loss"]), current_price - abs(float(trade["take_profit2"]) - float(trade["take_profit1"])))
        if candidate > float(trade["stop_loss"]):
            trade["stop_loss"] = candidate
            repo.update_copy_trade(trade["copy_trade_id"], stop_loss=trade["stop_loss"])
    else:
        candidate = min(float(trade["stop_loss"]), current_price + abs(float(trade["take_profit1"]) - float(trade["take_profit2"])))
        if candidate < float(trade["stop_loss"]):
            trade["stop_loss"] = candidate
            repo.update_copy_trade(trade["copy_trade_id"], stop_loss=trade["stop_loss"])


def _trade_to_dict(t: dict) -> dict:
    closed_at = t.get("closed_at")
    created_at = t["created_at"]
    holding_seconds = None
    if closed_at is not None:
        holding_seconds = max(0.0, float(closed_at) - float(created_at))
    return {
        "copy_trade_id": t["copy_trade_id"],
        "signal_id": t.get("signal_id"),
        "symbol": t["symbol"],
        "direction": t["direction"],
        "quantity": t["quantity"],
        "remaining_quantity": round(float(t.get("remaining_quantity", t["quantity"])), 4),
        "entry_price": t["entry_price"],
        "current_price": t["current_price"],
        "initial_stop_loss": t.get("initial_stop_loss", t["stop_loss"]),
        "stop_loss": t["stop_loss"],
        "take_profit1": t["take_profit1"],
        "take_profit2": t["take_profit2"],
        "take_profit3": t["take_profit3"],
        "confidence": t["confidence"],
        "risk_percent": t["risk_percent"],
        "status": t["status"],
        "unrealized_pnl": _round_pnl(float(t["unrealized_pnl"])),
        "realized_pnl": _round_pnl(float(t["realized_pnl"])),
        "realized_pnl_tp1": _round_pnl(float(t.get("realized_pnl_tp1", 0.0))),
        "realized_pnl_tp2": _round_pnl(float(t.get("realized_pnl_tp2", 0.0))),
        "partial_exit_count": int(t.get("partial_exit_count", 0)),
        "tp1_hit": bool(t.get("tp1_hit", 0)),
        "tp2_hit": bool(t.get("tp2_hit", 0)),
        "tp3_hit": bool(t.get("tp3_hit", 0)),
        "stop_moved_to_breakeven": bool(t.get("stop_moved_to_breakeven", 0)),
        "trailing_stop_active": bool(t.get("trailing_stop_active", 0)),
        "max_favorable_price": t.get("max_favorable_price"),
        "max_adverse_price": t.get("max_adverse_price"),
        "created_at": created_at,
        "closed_at": closed_at,
        "holding_seconds": round(holding_seconds, 1) if holding_seconds is not None else None,
        "trade_style": t["trade_style"],
        "timeframe": t["timeframe"],
        "signal_source": t["signal_source"],
    }


def _signal_is_expired(created_at: float, timeframe: str) -> bool:
    candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    max_age_seconds = MAX_SIGNAL_AGE_CANDLES * candle_seconds
    return (time.time() - created_at) > max_age_seconds


def _check_and_close(trade: dict, current_price: float) -> dict:
    """Check TP/SL and close if triggered; returns updated dict."""
    if trade["status"] not in {"open", "partial_tp1", "partial_tp2"}:
        return trade

    _update_excursions(trade, current_price)
    remaining_quantity = float(trade.get("remaining_quantity", trade["quantity"]))

    if _stop_triggered(trade, current_price):
        return _close(trade, current_price, "closed_sl")

    if not trade.get("tp1_hit") and _target_reached(trade, "take_profit1", current_price):
        _apply_partial_exit(trade, current_price, 1)
        trade["status"] = "partial_tp1"
    if trade.get("tp1_hit") and not trade.get("tp2_hit") and _target_reached(trade, "take_profit2", current_price):
        _apply_partial_exit(trade, current_price, 2)
        trade["status"] = "partial_tp2"
    if trade.get("tp2_hit") and _target_reached(trade, "take_profit3", current_price):
        return _apply_partial_exit(trade, current_price, 3)

    _maybe_trail_stop(trade, current_price)

    remaining_quantity = float(trade.get("remaining_quantity", trade["quantity"]))
    trade["status"] = "partial_tp2" if trade.get("tp2_hit") else "partial_tp1" if trade.get("tp1_hit") else "open"
    trade["unrealized_pnl"] = _calc_pnl(trade["direction"], trade["entry_price"], current_price, remaining_quantity)
    trade["current_price"] = current_price
    repo.update_copy_trade(trade["copy_trade_id"],
                           current_price=current_price,
                           unrealized_pnl=trade["unrealized_pnl"],
                           status=trade["status"],
                           max_favorable_price=trade.get("max_favorable_price"),
                           max_adverse_price=trade.get("max_adverse_price"))
    return trade


def _close(trade: dict, close_price: float, status: str) -> dict:
    remaining_quantity = float(trade.get("remaining_quantity", trade["quantity"]))
    trade["realized_pnl"] = round(float(trade["realized_pnl"]) + _calc_pnl(trade["direction"], trade["entry_price"], close_price, remaining_quantity), 2)
    trade["unrealized_pnl"] = 0.0
    trade["current_price"] = close_price
    trade["status"] = status
    trade["closed_at"] = time.time()
    trade["remaining_quantity"] = 0.0
    repo.update_copy_trade(trade["copy_trade_id"],
                           current_price=close_price,
                           unrealized_pnl=0.0,
                           realized_pnl=trade["realized_pnl"],
                           remaining_quantity=0.0,
                           status=status,
                           closed_at=trade["closed_at"])
    return trade


def _refresh_open_trades() -> List[dict]:
    trades = repo.get_open_copy_trades()
    for trade in trades:
        try:
            current_price, _ = get_base_price(
                trade["symbol"],
                timeframe=trade.get("timeframe") or "1h",
                trade_style=trade.get("trade_style") or "swing",
            )
            _check_and_close(trade, current_price)
        except Exception:
            continue
    return repo.get_open_copy_trades()


def _build_symbol_breakdown(trades: List[dict]) -> List[dict]:
    buckets: dict[str, dict] = {}
    for trade in trades:
        symbol = trade["symbol"]
        bucket = buckets.setdefault(symbol, {
            "symbol": symbol,
            "total_trades": 0,
            "wins": 0,
            "total_pnl": 0.0,
        })
        bucket["total_trades"] += 1
        if float(trade["realized_pnl"]) > 0:
            bucket["wins"] += 1
        bucket["total_pnl"] += float(trade["realized_pnl"])

    breakdown = []
    for bucket in buckets.values():
        total_trades = bucket["total_trades"]
        total_pnl = float(bucket["total_pnl"])
        breakdown.append({
            "symbol": bucket["symbol"],
            "total_trades": total_trades,
            "win_rate": round(bucket["wins"] / total_trades * 100, 1) if total_trades else 0.0,
            "total_pnl": round(total_pnl, 2),
            "avg_pnl": round(total_pnl / total_trades, 2) if total_trades else 0.0,
        })
    return sorted(breakdown, key=lambda item: item["total_pnl"], reverse=True)


def _build_equity_curve(closed_trades: List[dict], limit: int = 20) -> List[dict]:
    ordered = sorted(closed_trades, key=lambda trade: (trade.get("closed_at") or 0.0, trade["created_at"]))
    if limit > 0:
        ordered = ordered[-limit:]

    cumulative_pnl = 0.0
    points = []
    for trade in ordered:
        cumulative_pnl += float(trade["realized_pnl"])
        points.append({
            "copy_trade_id": trade["copy_trade_id"],
            "symbol": trade["symbol"],
            "closed_at": trade.get("closed_at"),
            "cumulative_pnl": round(cumulative_pnl, 2),
        })
    return points


def _calculate_max_drawdown(closed_trades: List[dict]) -> float:
    if not closed_trades:
        return 0.0
    running_pnl = 0.0
    peak = 0.0
    max_drawdown = 0.0
    ordered = sorted(closed_trades, key=lambda trade: (trade.get("closed_at") or 0.0, trade["created_at"]))
    for trade in ordered:
        running_pnl += float(trade["realized_pnl"])
        peak = max(peak, running_pnl)
        drawdown = running_pnl - peak
        max_drawdown = min(max_drawdown, drawdown)
    return round(max_drawdown, 2)


def _calculate_loss_streaks(closed_trades: List[dict]) -> dict:
    current_losses = 0
    max_losses = 0
    for trade in sorted(closed_trades, key=lambda item: (item.get("closed_at") or 0.0, item["created_at"])):
        if float(trade["realized_pnl"]) < 0:
            current_losses += 1
            max_losses = max(max_losses, current_losses)
        else:
            current_losses = 0
    return {
        "current_loss_streak": current_losses,
        "max_loss_streak": max_losses,
    }


def _trade_r_multiple(trade: dict) -> Optional[float]:
    initial_stop = trade.get("initial_stop_loss")
    if initial_stop is None:
        return None
    risk_per_unit = abs(float(trade["entry_price"]) - float(initial_stop))
    if risk_per_unit <= 0:
        return None
    total_risk = risk_per_unit * float(trade["quantity"])
    if total_risk <= 0:
        return None
    return round(float(trade["realized_pnl"]) / total_risk, 2)


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
    signal = repo.get_signal_prediction(body.signal_id)
    if not signal:
        raise HTTPException(status_code=404, detail=f"Signal {body.signal_id} not found.")
    if signal["direction"] == "HOLD":
        raise HTTPException(status_code=400, detail="Hold signals cannot be copied.")
    if _signal_is_expired(float(signal["created_at"]), signal["timeframe"]):
        raise HTTPException(status_code=400, detail="Signal has expired.")
    if signal["symbol"] not in settings["allowed_symbols"]:
        raise HTTPException(status_code=400, detail=f"Symbol {signal['symbol']} not allowed.")
    if int(signal["confidence"]) < settings["min_confidence"]:
        raise HTTPException(status_code=400, detail=f"Confidence {signal['confidence']} below minimum.")
    open_trades = repo.get_open_copy_trades()
    if len(open_trades) >= settings["max_concurrent_positions"]:
        raise HTTPException(status_code=400, detail="Max concurrent positions reached.")
    if repo.get_open_copy_trade_for_signal(body.signal_id):
        raise HTTPException(status_code=409, detail="An open copy trade already exists for this signal.")

    quantity = round(body.quantity * settings["lot_size_scale"], 2)
    quantity = min(quantity, settings["max_position_size_lots"])
    risk_percent = min(body.risk_percent, settings["max_risk_percent"])
    trade_style = signal.get("trade_style") or signal.get("price_source") or "swing"
    try:
        entry_price, _ = get_base_price(
            signal["symbol"],
            timeframe=signal["timeframe"],
            trade_style=trade_style,
        )
    except Exception:
        if body.entry_price is None:
            raise HTTPException(status_code=502, detail="Unable to determine current market price for this signal.")
        entry_price = body.entry_price

    copy_trade_id = f"ct_{uuid.uuid4().hex[:8]}"
    trade = {
        "copy_trade_id": copy_trade_id,
        "signal_id": body.signal_id,
        "symbol": signal["symbol"],
        "direction": signal["direction"].upper(),
        "quantity": quantity,
        "remaining_quantity": quantity,
        "entry_price": entry_price,
        "current_price": entry_price,
        "initial_stop_loss": signal["stop_loss"],
        "stop_loss": signal["stop_loss"],
        "take_profit1": signal["take_profit1"],
        "take_profit2": signal["take_profit2"],
        "take_profit3": signal["take_profit3"],
        "confidence": int(signal["confidence"]),
        "risk_percent": risk_percent,
        "status": "open",
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.0,
        "realized_pnl_tp1": 0.0,
        "realized_pnl_tp2": 0.0,
        "partial_exit_count": 0,
        "tp1_hit": 0,
        "tp2_hit": 0,
        "tp3_hit": 0,
        "stop_moved_to_breakeven": 0,
        "trailing_stop_active": 0,
        "max_favorable_price": entry_price,
        "max_adverse_price": entry_price,
        "trade_style": trade_style,
        "timeframe": signal["timeframe"],
        "signal_source": "AI",
        "created_at": time.time(),
        "closed_at": None,
    }
    repo.insert_copy_trade(trade)

    return {
        "success": True,
        "copy_trade_id": copy_trade_id,
        "signal_id": body.signal_id,
        "symbol": trade["symbol"],
        "direction": trade["direction"],
        "quantity": trade["quantity"],
        "remaining_quantity": trade["remaining_quantity"],
        "effective_quantity": trade["quantity"],
        "effective_risk_percent": trade["risk_percent"],
        "entry_price": trade["entry_price"],
        "stop_loss": trade["stop_loss"],
        "take_profit1": trade["take_profit1"],
        "status": "open",
        "message": f"Copied AI {trade['direction']} signal for {trade['symbol']} at {trade['entry_price']}",
    }


@router.get("/positions")
async def get_positions():
    open_trades = _refresh_open_trades()
    return {"positions": [_trade_to_dict(t) for t in open_trades], "count": len(open_trades)}


@router.post("/close/{copy_trade_id}")
async def close_position(copy_trade_id: str):
    trade = repo.get_copy_trade(copy_trade_id)
    if not trade or trade["status"] not in {"open", "partial_tp1", "partial_tp2"}:
        raise HTTPException(status_code=404, detail=f"No open position with id {copy_trade_id}")

    current_price, _ = get_base_price(
        trade["symbol"],
        timeframe=trade.get("timeframe") or "1h",
        trade_style=trade.get("trade_style") or "swing",
    )
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
async def get_history(
    limit: int = Query(20, ge=1, le=500),
    offset: int = Query(0, ge=0, le=5000),
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = Query(default=None, pattern="^(BUY|SELL)$"),
    from_ts: Optional[float] = Query(default=None, ge=0),
    to_ts: Optional[float] = Query(default=None, ge=0),
    sort_by: str = Query("closed_at"),
    sort_dir: str = Query("desc", pattern="^(asc|desc)$"),
):
    trades = repo.get_copy_history(
        limit=limit,
        offset=offset,
        symbol=symbol,
        status=status,
        direction=direction,
        from_ts=from_ts,
        to_ts=to_ts,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )
    total = repo.count_copy_history(
        symbol=symbol,
        status=status,
        direction=direction,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    return {
        "history": [_trade_to_dict(t) for t in trades],
        "count": len(trades),
        "total": total,
        "offset": offset,
        "limit": limit,
    }


@router.get("/history/export")
async def export_history_csv(
    limit: int = Query(200, ge=1, le=1000),
    symbol: Optional[str] = None,
    status: Optional[str] = None,
    direction: Optional[str] = Query(default=None, pattern="^(BUY|SELL)$"),
    from_ts: Optional[float] = Query(default=None, ge=0),
    to_ts: Optional[float] = Query(default=None, ge=0),
):
    trades = repo.get_copy_history(
        limit=limit,
        symbol=symbol,
        status=status,
        direction=direction,
        from_ts=from_ts,
        to_ts=to_ts,
    )
    rows = [_trade_to_dict(trade) for trade in trades]
    output = io.StringIO()
    fieldnames = [
        "copy_trade_id",
        "signal_id",
        "symbol",
        "direction",
        "quantity",
        "remaining_quantity",
        "entry_price",
        "current_price",
        "initial_stop_loss",
        "stop_loss",
        "take_profit1",
        "take_profit2",
        "take_profit3",
        "confidence",
        "risk_percent",
        "status",
        "unrealized_pnl",
        "realized_pnl",
        "partial_exit_count",
        "tp1_hit",
        "tp2_hit",
        "tp3_hit",
        "stop_moved_to_breakeven",
        "trailing_stop_active",
        "holding_seconds",
        "created_at",
        "closed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({key: row.get(key) for key in fieldnames})
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=copy_trade_history.csv"},
    )


@router.get("/stats")
async def get_stats():
    open_trades = _refresh_open_trades()
    closed_trades = repo.get_copy_history(limit=1000)
    open_count = len(open_trades)
    closed_count = len(closed_trades)
    total_count = open_count + closed_count
    total_unrealized_pnl = sum(float(trade.get("unrealized_pnl", 0.0)) for trade in open_trades)
    partial_exit_trades = sum(1 for trade in open_trades + closed_trades if int(trade.get("partial_exit_count", 0)) > 0)

    if closed_count == 0:
        return {
            "total_trades": total_count,
            "open_trades": open_count,
            "closed_trades": 0,
            "total_pnl": 0.0,
            "total_unrealized_pnl": _round_pnl(total_unrealized_pnl),
            "win_rate": 0.0,
            "avg_pnl": 0.0,
            "expectancy": 0.0,
            "profit_factor": None,
            "best_trade": 0.0,
            "worst_trade": 0.0,
            "avg_hold_seconds": 0.0,
            "partial_exit_trades": partial_exit_trades,
            "symbol_breakdown": [],
            "recent_closed": [],
            "equity_curve": [],
        }

    wins = sum(1 for t in closed_trades if t["realized_pnl"] > 0)
    total_pnl = sum(t["realized_pnl"] for t in closed_trades)
    gross_profit = sum(float(t["realized_pnl"]) for t in closed_trades if float(t["realized_pnl"]) > 0)
    gross_loss = abs(sum(float(t["realized_pnl"]) for t in closed_trades if float(t["realized_pnl"]) < 0))
    hold_durations = [
        float(t["closed_at"]) - float(t["created_at"])
        for t in closed_trades
        if t.get("closed_at") is not None
    ]
    recent_closed = [
        {
            "copy_trade_id": trade["copy_trade_id"],
            "symbol": trade["symbol"],
            "status": trade["status"],
            "realized_pnl": round(float(trade["realized_pnl"]), 2),
            "closed_at": trade.get("closed_at"),
            "holding_seconds": round(float(trade["closed_at"]) - float(trade["created_at"]), 1) if trade.get("closed_at") is not None else None,
            "r_multiple": _trade_r_multiple(trade),
        }
        for trade in closed_trades[:10]
    ]
    streaks = _calculate_loss_streaks(closed_trades)
    r_values = [value for value in (_trade_r_multiple(trade) for trade in closed_trades) if value is not None]

    return {
        "total_trades": total_count,
        "open_trades": open_count,
        "closed_trades": closed_count,
        "total_pnl": _round_pnl(total_pnl),
        "total_unrealized_pnl": _round_pnl(total_unrealized_pnl),
        "win_rate": round(wins / closed_count * 100, 1),
        "avg_pnl": _round_pnl(total_pnl / closed_count),
        "expectancy": _round_pnl(total_pnl / closed_count),
        "profit_factor": round(gross_profit / gross_loss, 2) if gross_loss > 0 else None,
        "best_trade": _round_pnl(max(float(t["realized_pnl"]) for t in closed_trades)),
        "worst_trade": _round_pnl(min(float(t["realized_pnl"]) for t in closed_trades)),
        "max_drawdown": _calculate_max_drawdown(closed_trades),
        "current_loss_streak": streaks["current_loss_streak"],
        "max_loss_streak": streaks["max_loss_streak"],
        "avg_hold_seconds": round(sum(hold_durations) / len(hold_durations), 1) if hold_durations else 0.0,
        "avg_r_multiple": round(sum(r_values) / len(r_values), 2) if r_values else None,
        "partial_exit_trades": partial_exit_trades,
        "symbol_breakdown": _build_symbol_breakdown(closed_trades),
        "recent_closed": recent_closed,
        "equity_curve": _build_equity_curve(closed_trades),
    }
