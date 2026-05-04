"""Backend automation worker for strategy-driven execution (paper & live)."""

import asyncio
import time
from typing import Dict, Optional

from trading_bot.api.routes.paper_trading import PaperOrderRequest, place_paper_order
from trading_bot.config import get_logger
from trading_bot.execution.broker_base import OrderSide, OrderType
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager
from trading_bot.persistence import repositories as repo
from trading_bot.services.automation_safety import (
    validate_live_execution_gate,
    validate_live_risk_constraints,
    validate_signal_quality,
)
from trading_bot.services.market_analysis import analyze_symbol
from trading_bot.services.strategy_registry import get_strategy

logger = get_logger(__name__)

_worker_task: Optional[asyncio.Task] = None
_worker_mode: str = "paper"  # "paper" or "live"
_worker_broker_id: Optional[str] = None
_worker_status: Dict[str, object] = {
    "running": False,
    "lastRun": None,
    "lastExecution": None,
    "lastError": None,
    "mode": "paper",
    "brokerId": None,
    "lastAnalysis": None,
}
_last_signal_key: Optional[str] = None
_last_strategy_execution_at: Dict[str, float] = {}


def _get_pip_size(symbol: str, current_price: float) -> float:
    if "JPY" in symbol:
        return 0.01
    if current_price >= 1000:
        return 0.1
    return 0.0001


def _normalize_entry_zone(analysis: dict, fallback_price: float) -> tuple[float, float]:
    entry_range = analysis.get("entryRange") or {}
    entry_min = float(entry_range.get("min") or fallback_price)
    entry_max = float(entry_range.get("max") or fallback_price)
    lower = min(entry_min, entry_max)
    upper = max(entry_min, entry_max)
    return lower, upper


def _price_within_entry_zone(current_price: float, entry_min: float, entry_max: float, pip_size: float) -> bool:
    tolerance = pip_size * 5
    return (entry_min - tolerance) <= current_price <= (entry_max + tolerance)


def _calculate_live_units(
    symbol: str,
    account_balance: float,
    allocation_percent: float,
    current_price: float,
    stop_loss: float,
) -> int:
    risk_amount = account_balance * (allocation_percent / 100.0)
    stop_distance = abs(current_price - stop_loss)
    if stop_distance <= 0:
        return 1

    pip_size = _get_pip_size(symbol, current_price)
    stop_pips = stop_distance / pip_size
    if stop_pips <= 0:
        return 1

    pip_value_per_unit = pip_size
    units = risk_amount / (stop_pips * pip_value_per_unit)
    return max(1, int(round(units)))


def get_worker_status() -> Dict[str, object]:
    return dict(_worker_status)


def get_worker_mode() -> Dict[str, object]:
    return {"mode": _worker_mode, "brokerId": _worker_broker_id}


async def _automation_loop() -> None:
    global _last_signal_key
    try:
        while _worker_status["running"]:
            active_id = repo.get_setting("active_strategy_id", "")
            active_mode = repo.get_setting("active_strategy_mode", "paper")
            if not active_id or active_mode not in ("paper", "live"):
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            live_gate = validate_live_execution_gate(
                mode=_worker_mode,
                active_mode=active_mode,
                broker_id=_worker_broker_id,
                broker_manager=broker_manager,
            )
            if not live_gate.allowed:
                repo.insert_automation_execution(
                    active_id,
                    "unknown",
                    "execute",
                    "skipped",
                    {"reason": live_gate.reason, **live_gate.detail},
                )
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            strategy = get_strategy(active_id)
            if not strategy:
                repo.insert_automation_execution(active_id or "unknown", "unknown", "analyze", "skipped", {"reason": "strategy_not_found"})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            enabled = repo.get_setting(f"strategy:{active_id}:enabled", "0") == "1"
            allocation_percent = float(repo.get_setting(f"strategy:{active_id}:allocation_percent", "2.0"))
            max_positions = int(repo.get_setting(f"strategy:{active_id}:max_positions", "1"))
            cooldown_seconds = int(repo.get_setting(f"strategy:{active_id}:cooldown_seconds", "120"))
            max_executions_per_hour = int(repo.get_setting(f"strategy:{active_id}:max_executions_per_hour", "2"))

            if not enabled:
                repo.insert_automation_execution(active_id, strategy["symbol"], "analyze", "skipped", {"reason": "template_disabled"})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            if _worker_mode == "live" and _worker_broker_id:
                try:
                    broker_positions = await broker_manager.get_positions(_worker_broker_id)
                except BrokerOperationError as exc:
                    repo.insert_automation_execution(active_id, strategy["symbol"], "analyze", "error", {
                        "reason": "broker_positions_failed",
                        "detail": exc.detail,
                        "category": exc.category,
                    })
                    _worker_status["lastError"] = exc.detail
                    _worker_status["lastRun"] = time.time()
                    await asyncio.sleep(5)
                    continue
                open_positions = [p for p in broker_positions if p.symbol == strategy["symbol"]]
            else:
                broker_positions = []
                open_positions = [p for p in repo.get_paper_positions() if p.get("strategy_id") == active_id]
            if len(open_positions) >= max_positions:
                repo.insert_automation_execution(active_id, strategy["symbol"], "analyze", "skipped", {"reason": "max_positions_reached", "openPositions": len(open_positions)})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            last_exec = _last_strategy_execution_at.get(active_id)
            if last_exec and (time.time() - last_exec) < cooldown_seconds:
                repo.insert_automation_execution(active_id, strategy["symbol"], "analyze", "skipped", {
                    "reason": "strategy_cooldown",
                    "cooldownSeconds": cooldown_seconds,
                    "remainingSeconds": round(cooldown_seconds - (time.time() - last_exec), 1),
                })
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            hourly_executions = repo.count_recent_automation_executions(active_id, 3600)
            if hourly_executions >= max_executions_per_hour:
                repo.insert_automation_execution(active_id, strategy["symbol"], "analyze", "skipped", {
                    "reason": "hourly_rate_limit",
                    "maxExecutionsPerHour": max_executions_per_hour,
                    "executionsLastHour": hourly_executions,
                })
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            symbol = strategy["symbol"]
            timeframe = strategy["bestTimeframes"][0]
            trade_style = strategy["tradeStyle"]
            analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
            if not analysis:
                repo.insert_automation_execution(active_id, symbol, "analyze", "skipped", {"reason": "analysis_unavailable"})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            signal = str(analysis.get("signal", "hold")).lower()
            confidence = float(analysis.get("confidence", 0))
            signal_quality = validate_signal_quality(analysis)
            if not signal_quality.allowed:
                repo.insert_automation_execution(active_id, symbol, "analyze", "skipped", {"reason": signal_quality.reason, **signal_quality.detail})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            side = signal_quality.detail["side"]
            current_price = float(analysis.get("currentPrice", 0))

            signal_key = f"{active_id}:{symbol}:{trade_style}:{signal}:{round(current_price, 2)}"
            if _last_signal_key == signal_key:
                repo.insert_automation_execution(active_id, symbol, "execute", "skipped", {"reason": "duplicate_signal", "signalKey": signal_key})
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            # Store latest analysis for frontend polling
            _worker_status["lastAnalysis"] = {
                "signal": signal,
                "confidence": confidence,
                "reason": analysis.get("reason", ""),
                "marketRegime": analysis.get("marketRegime", "unknown"),
                "entryRange": analysis.get("entryRange"),
                "stopLoss": analysis.get("stopLoss"),
                "takeProfit1": analysis.get("takeProfit1"),
                "takeProfit2": analysis.get("takeProfit2"),
                "takeProfit3": analysis.get("takeProfit3"),
                "currentPrice": current_price,
                "symbol": symbol,
                "timeframe": timeframe,
                "tradeStyle": trade_style,
                "timestamp": time.time(),
            }

            stop_loss = float(analysis.get("stopLoss", current_price))
            entry_min, entry_max = _normalize_entry_zone(analysis, current_price)
            pip_size = _get_pip_size(symbol, current_price)

            if not _price_within_entry_zone(current_price, entry_min, entry_max, pip_size):
                repo.insert_automation_execution(active_id, symbol, "analyze", "skipped", {
                    "reason": "entry_zone_miss",
                    "currentPrice": current_price,
                    "entryMin": entry_min,
                    "entryMax": entry_max,
                })
                _worker_status["lastRun"] = time.time()
                await asyncio.sleep(5)
                continue

            # Branch on mode: live broker vs paper
            if _worker_mode == "live" and _worker_broker_id:
                # Live mode: use real broker balance and place real order
                try:
                    balance_obj = await broker_manager.get_balance(_worker_broker_id)
                except BrokerOperationError as exc:
                    repo.insert_automation_execution(active_id, symbol, "execute", "error", {
                        "reason": "broker_balance_failed",
                        "detail": exc.detail,
                        "category": exc.category,
                    })
                    _worker_status["lastError"] = exc.detail
                    _worker_status["lastRun"] = time.time()
                    await asyncio.sleep(5)
                    continue
                account_balance = balance_obj.available_margin if balance_obj else 0.0
                if account_balance <= 0:
                    repo.insert_automation_execution(active_id, symbol, "execute", "skipped", {"reason": "no_broker_balance"})
                    _worker_status["lastRun"] = time.time()
                    await asyncio.sleep(5)
                    continue
                quantity = _calculate_live_units(symbol, account_balance, allocation_percent, current_price, stop_loss)
                risk_gate = validate_live_risk_constraints(
                    symbol=symbol,
                    side=side,
                    quantity=quantity,
                    current_price=current_price,
                    stop_loss=stop_loss,
                    balance=balance_obj,
                    positions=broker_positions,
                    allocation_percent=allocation_percent,
                    max_positions=max_positions,
                )
                if not risk_gate.allowed:
                    repo.insert_automation_execution(active_id, symbol, "execute", "skipped", {"reason": risk_gate.reason, **risk_gate.detail})
                    _worker_status["lastRun"] = time.time()
                    await asyncio.sleep(5)
                    continue
                order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
                try:
                    broker_order = await broker_manager.place_order(
                        broker_id=_worker_broker_id,
                        symbol=symbol,
                        side=order_side,
                        quantity=quantity,
                        order_type=OrderType.MARKET,
                        stop_loss=stop_loss,
                        take_profit_1=analysis.get("takeProfit1"),
                        take_profit_2=analysis.get("takeProfit2"),
                        take_profit_3=analysis.get("takeProfit3"),
                    )
                except BrokerOperationError as exc:
                    repo.insert_automation_execution(active_id, symbol, "execute", "error", {
                        "reason": "broker_order_failed",
                        "detail": exc.detail,
                        "category": exc.category,
                    })
                    _worker_status["lastError"] = exc.detail
                    _worker_status["lastRun"] = time.time()
                    await asyncio.sleep(5)
                    continue
                exec_detail = {
                    "signal": signal,
                    "confidence": confidence,
                    "side": side,
                    "price": current_price,
                    "quantity": quantity,
                    "mode": "live",
                    "broker_id": _worker_broker_id,
                    "order_id": broker_order.order_id,
                    "riskCheck": risk_gate.detail,
                    "entryMin": entry_min,
                    "entryMax": entry_max,
                    "stopLoss": stop_loss,
                    "takeProfit1": analysis.get("takeProfit1"),
                    "takeProfit2": analysis.get("takeProfit2"),
                    "takeProfit3": analysis.get("takeProfit3"),
                }
            else:
                # Paper mode: use paper balance
                stop_distance = abs(current_price - stop_loss)
                risk_amount = repo.get_paper_account().get("balance", 10000.0) * (allocation_percent / 100.0)
                quantity = max(0.01, risk_amount / stop_distance) if stop_distance > 0 else 0.01
                await place_paper_order(PaperOrderRequest(
                    symbol=symbol,
                    side=side,
                    quantity=round(quantity, 2),
                    price=current_price,
                    stop_loss=stop_loss,
                    take_profit_1=analysis.get("takeProfit1"),
                    take_profit_2=analysis.get("takeProfit2"),
                    take_profit_3=analysis.get("takeProfit3"),
                    risk_percent=allocation_percent,
                    trade_style=trade_style,
                    confidence=confidence,
                    strategy_id=active_id,
                ))
                exec_detail = {
                    "signal": signal,
                    "confidence": confidence,
                    "side": side,
                    "price": current_price,
                    "quantity": round(quantity, 2),
                    "mode": "paper",
                    "entryMin": entry_min,
                    "entryMax": entry_max,
                    "stopLoss": stop_loss,
                    "takeProfit1": analysis.get("takeProfit1"),
                    "takeProfit2": analysis.get("takeProfit2"),
                    "takeProfit3": analysis.get("takeProfit3"),
                }

            repo.insert_automation_execution(active_id, symbol, "execute", "success", exec_detail)
            _last_signal_key = signal_key
            _last_strategy_execution_at[active_id] = time.time()
            _worker_status["lastExecution"] = time.time()
            _worker_status["lastRun"] = time.time()
            _worker_status["lastError"] = None
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        _worker_status["lastRun"] = time.time()
        raise
    except Exception as exc:
        logger.warning("Automation worker error: %s", exc)
        if active_id:
            repo.insert_automation_execution(active_id, strategy["symbol"] if 'strategy' in locals() and strategy else "unknown", "execute", "error", {"error": str(exc)})
        _worker_status["lastError"] = str(exc)
        _worker_status["lastRun"] = time.time()


def start_worker(mode: str = "paper", broker_id: Optional[str] = None) -> None:
    global _worker_task, _worker_mode, _worker_broker_id
    if _worker_status["running"]:
        return
    _worker_mode = mode
    _worker_broker_id = broker_id
    _worker_status["mode"] = mode
    _worker_status["brokerId"] = broker_id
    _worker_status["lastAnalysis"] = None
    repo.insert_automation_execution("system", "system", "worker", "started", {"mode": mode, "broker_id": broker_id})
    _worker_status["running"] = True
    loop = asyncio.get_event_loop()
    _worker_task = loop.create_task(_automation_loop())


async def stop_worker() -> None:
    global _worker_task, _worker_mode, _worker_broker_id
    _worker_status["running"] = False
    _worker_status["mode"] = "paper"
    _worker_status["brokerId"] = None
    repo.insert_automation_execution("system", "system", "worker", "stopped", {"mode": _worker_mode})
    _worker_mode = "paper"
    _worker_broker_id = None
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        _worker_task = None
