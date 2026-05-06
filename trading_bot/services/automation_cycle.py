"""Deterministic automation cycle orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Dict, Optional

from trading_bot.api.models import (
    PredictionRequest,
    PredictionRecommendation,
    PredictionSourceContext,
    PredictionSourceType,
    PredictionStrategyMode,
)
from trading_bot.execution.broker_base import OrderSide, OrderType
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager
from trading_bot.execution.paper import PaperOrderCommand, place_paper_order
from trading_bot.persistence import repositories as repo
from trading_bot.services.automation_safety import (
    AutomationGateResult,
    validate_live_execution_gate,
    validate_live_risk_constraints,
    validate_signal_quality,
)
from trading_bot.services.market_analysis import analyze_symbol
from trading_bot.services.prediction_pipeline import (
    asset_class_for_symbol,
    build_prediction_response,
)
from trading_bot.services.strategy_registry import get_strategy


@dataclass(frozen=True)
class AutomationCycleContext:
    mode: str = "paper"
    broker_id: Optional[str] = None
    last_signal_key: Optional[str] = None
    last_strategy_execution_at: Dict[str, float] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationExecutionEvent:
    strategy_id: str
    symbol: str
    action: str
    status: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AutomationSkip:
    strategy_id: str
    symbol: str
    reason: str
    detail: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AutomationCycleResult:
    analyzed_symbols: list[str] = field(default_factory=list)
    skipped_symbols: list[AutomationSkip] = field(default_factory=list)
    attempted_trades: list[dict[str, Any]] = field(default_factory=list)
    executed_trades: list[dict[str, Any]] = field(default_factory=list)
    warnings: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    events: list[AutomationExecutionEvent] = field(default_factory=list)
    last_analysis: Optional[dict[str, Any]] = None
    last_error: Optional[str] = None
    last_execution_at: Optional[float] = None
    last_signal_key: Optional[str] = None
    strategy_execution_updates: dict[str, float] = field(default_factory=dict)


PaperOrderExecutor = Callable[[PaperOrderCommand], Awaitable[dict[str, Any]]]
PredictionProvider = Callable[[PredictionRequest, dict[str, Any]], Any]


@dataclass(frozen=True)
class AutomationCycleDependencies:
    repository: Any = repo
    broker_manager: Any = broker_manager
    strategy_provider: Callable[[str], Optional[dict[str, Any]]] = get_strategy
    analysis_provider: Callable[[str, str, str], Optional[dict[str, Any]]] = analyze_symbol
    prediction_provider: PredictionProvider = field(
        default=lambda request, analysis: _build_prediction(request, analysis)
    )
    paper_order_executor: PaperOrderExecutor = place_paper_order
    live_gate_validator: Callable[..., AutomationGateResult] = validate_live_execution_gate
    signal_quality_validator: Callable[..., AutomationGateResult] = validate_signal_quality
    live_risk_validator: Callable[..., AutomationGateResult] = validate_live_risk_constraints
    clock: Callable[[], float] = time.time


def _get_pip_size(symbol: str, current_price: float) -> float:
    if "JPY" in symbol:
        return 0.01
    if current_price >= 1000:
        return 0.1
    return 0.0001


def _normalize_entry_zone(analysis: dict[str, Any], fallback_price: float) -> tuple[float, float]:
    entry_range = analysis.get("entryRange") or {}
    entry_min = float(entry_range.get("min") or fallback_price)
    entry_max = float(entry_range.get("max") or fallback_price)
    lower = min(entry_min, entry_max)
    upper = max(entry_min, entry_max)
    return lower, upper


def _price_within_entry_zone(
    current_price: float,
    entry_min: float,
    entry_max: float,
    pip_size: float,
) -> bool:
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


def _strategy_mode(trade_style: str) -> PredictionStrategyMode:
    if trade_style == "scalp":
        return PredictionStrategyMode.SCALP
    return PredictionStrategyMode.SWING


def _build_prediction(request: PredictionRequest, analysis: dict[str, Any]) -> Any:
    metadata = {
        "sourceName": "automation_cycle",
        "sourceType": "service",
        "priceSource": "analysis",
        "isFallback": bool(analysis.get("is_mock", False)),
        "freshnessSeconds": 0,
        "qualityFlags": [],
        "marketStatus": "open",
        "lastBarTimestamp": analysis.get("data_fetched_at") or time.time(),
    }
    return build_prediction_response(
        request,
        analysis_override=analysis,
        metadata_override=metadata,
    )


def _prediction_blocks_trade(prediction: Any) -> bool:
    recommendation = getattr(prediction, "recommendation", None)
    if recommendation not in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}:
        return True
    return getattr(prediction, "trade_allowed", True) is False


def _prediction_skip_detail(prediction: Any) -> dict[str, Any]:
    no_trade_reasons = []
    for detail in getattr(prediction, "no_trade_reasons", []) or []:
        code = getattr(detail, "code", detail)
        no_trade_reasons.append(getattr(code, "value", str(code)))
    primary = getattr(prediction, "no_trade_reason", None)
    recommendation = getattr(prediction, "recommendation", None)
    reason = (
        "prediction_no_trade"
        if recommendation == PredictionRecommendation.NO_TRADE
        else "prediction_not_actionable"
    )
    return {
        "reason": reason,
        "recommendation": getattr(recommendation, "value", str(recommendation)),
        "noTradeReason": getattr(primary, "value", str(primary)) if primary else None,
        "noTradeReasons": no_trade_reasons,
        "tradeAllowed": getattr(prediction, "trade_allowed", None),
    }


def _last_analysis_payload(
    *,
    analysis: dict[str, Any],
    symbol: str,
    timeframe: str,
    trade_style: str,
    signal: str,
    confidence: float,
    current_price: float,
    timestamp: float,
) -> dict[str, Any]:
    return {
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
        "timestamp": timestamp,
    }


def _skip(
    result: AutomationCycleResult,
    *,
    strategy_id: str,
    symbol: str,
    action: str,
    reason: str,
    detail: Optional[dict[str, Any]] = None,
) -> AutomationCycleResult:
    payload = {"reason": reason, **(detail or {})}
    result.skipped_symbols.append(AutomationSkip(strategy_id, symbol, reason, payload))
    result.events.append(AutomationExecutionEvent(strategy_id, symbol, action, "skipped", payload))
    return result


def _error(
    result: AutomationCycleResult,
    *,
    strategy_id: str,
    symbol: str,
    action: str,
    reason: str,
    message: str,
    detail: Optional[dict[str, Any]] = None,
) -> AutomationCycleResult:
    payload = {"reason": reason, **(detail or {})}
    result.errors.append({"strategy_id": strategy_id, "symbol": symbol, **payload})
    result.events.append(AutomationExecutionEvent(strategy_id, symbol, action, "error", payload))
    result.last_error = message
    return result


async def run_automation_cycle(
    context: AutomationCycleContext,
    dependencies: AutomationCycleDependencies = AutomationCycleDependencies(),
) -> AutomationCycleResult:
    """Run one automation decision cycle without owning worker lifecycle or sleep."""
    result = AutomationCycleResult(last_signal_key=context.last_signal_key)
    repository = dependencies.repository
    now = dependencies.clock

    active_id = repository.get_setting("active_strategy_id", "")
    active_mode = repository.get_setting("active_strategy_mode", "paper")
    if not active_id or active_mode not in ("paper", "live"):
        result.skipped_symbols.append(
            AutomationSkip(
                active_id or "unknown",
                "unknown",
                "automation_inactive",
                {"reason": "automation_inactive", "activeMode": active_mode},
            )
        )
        return result

    live_gate = dependencies.live_gate_validator(
        mode=context.mode,
        active_mode=active_mode,
        broker_id=context.broker_id,
        broker_manager=dependencies.broker_manager,
    )
    if not live_gate.allowed:
        return _skip(
            result,
            strategy_id=active_id,
            symbol="unknown",
            action="execute",
            reason=live_gate.reason,
            detail=live_gate.detail,
        )

    strategy = dependencies.strategy_provider(active_id)
    if not strategy:
        return _skip(
            result,
            strategy_id=active_id or "unknown",
            symbol="unknown",
            action="analyze",
            reason="strategy_not_found",
        )

    symbol = strategy["symbol"]
    enabled = repository.get_setting(f"strategy:{active_id}:enabled", "0") == "1"
    allocation_percent = float(
        repository.get_setting(f"strategy:{active_id}:allocation_percent", "2.0")
    )
    max_positions = int(repository.get_setting(f"strategy:{active_id}:max_positions", "1"))
    cooldown_seconds = int(repository.get_setting(f"strategy:{active_id}:cooldown_seconds", "120"))
    max_executions_per_hour = int(
        repository.get_setting(f"strategy:{active_id}:max_executions_per_hour", "2")
    )

    if not enabled:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="template_disabled",
        )

    if context.mode == "live" and context.broker_id:
        try:
            broker_positions = await dependencies.broker_manager.get_positions(context.broker_id)
        except BrokerOperationError as exc:
            return _error(
                result,
                strategy_id=active_id,
                symbol=symbol,
                action="analyze",
                reason="broker_positions_failed",
                message=exc.detail,
                detail={"detail": exc.detail, "category": exc.category},
            )
        open_positions = [position for position in broker_positions if position.symbol == symbol]
    else:
        broker_positions = []
        open_positions = [
            position
            for position in repository.get_paper_positions()
            if position.get("strategy_id") == active_id
        ]
    if len(open_positions) >= max_positions:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="max_positions_reached",
            detail={"openPositions": len(open_positions), "maxPositions": max_positions},
        )

    last_exec = context.last_strategy_execution_at.get(active_id)
    if last_exec and (now() - last_exec) < cooldown_seconds:
        remaining = cooldown_seconds - (now() - last_exec)
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="strategy_cooldown",
            detail={
                "cooldownSeconds": cooldown_seconds,
                "remainingSeconds": round(remaining, 1),
            },
        )

    hourly_executions = repository.count_recent_automation_executions(active_id, 3600)
    if hourly_executions >= max_executions_per_hour:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="hourly_rate_limit",
            detail={
                "maxExecutionsPerHour": max_executions_per_hour,
                "executionsLastHour": hourly_executions,
            },
        )

    timeframe = strategy["bestTimeframes"][0]
    trade_style = strategy["tradeStyle"]
    analysis = dependencies.analysis_provider(symbol, timeframe, trade_style)
    if not analysis:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="analysis_unavailable",
        )

    result.analyzed_symbols.append(symbol)
    signal = str(analysis.get("signal", "hold")).lower()
    confidence = float(analysis.get("confidence", 0))
    signal_quality = dependencies.signal_quality_validator(analysis)
    if not signal_quality.allowed:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason=signal_quality.reason,
            detail=signal_quality.detail,
        )

    side = signal_quality.detail["side"]
    current_price = float(analysis.get("currentPrice", 0))
    signal_key = f"{active_id}:{symbol}:{trade_style}:{signal}:{round(current_price, 2)}"
    if context.last_signal_key == signal_key:
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason="duplicate_signal",
            detail={"signalKey": signal_key},
        )

    cycle_time = now()
    result.last_analysis = _last_analysis_payload(
        analysis=analysis,
        symbol=symbol,
        timeframe=timeframe,
        trade_style=trade_style,
        signal=signal,
        confidence=confidence,
        current_price=current_price,
        timestamp=cycle_time,
    )

    prediction_request = PredictionRequest(
        symbol=symbol,
        asset_class=asset_class_for_symbol(symbol),
        timeframe=timeframe,
        strategy_mode=_strategy_mode(trade_style),
        source_context=PredictionSourceContext(
            source_type=PredictionSourceType.AUTOMATION,
            source_id=active_id,
            source_name=strategy.get("name"),
            automation_template_id=active_id,
        ),
    )
    prediction = dependencies.prediction_provider(prediction_request, analysis)
    if _prediction_blocks_trade(prediction):
        detail = _prediction_skip_detail(prediction)
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason=detail["reason"],
            detail={key: value for key, value in detail.items() if key != "reason"},
        )

    stop_loss = float(analysis.get("stopLoss", current_price))
    entry_min, entry_max = _normalize_entry_zone(analysis, current_price)
    pip_size = _get_pip_size(symbol, current_price)

    if not _price_within_entry_zone(current_price, entry_min, entry_max, pip_size):
        return _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="analyze",
            reason="entry_zone_miss",
            detail={
                "currentPrice": current_price,
                "entryMin": entry_min,
                "entryMax": entry_max,
            },
        )

    if context.mode == "live" and context.broker_id:
        exec_detail = await _execute_live_trade(
            context=context,
            dependencies=dependencies,
            result=result,
            active_id=active_id,
            symbol=symbol,
            side=side,
            signal=signal,
            confidence=confidence,
            current_price=current_price,
            stop_loss=stop_loss,
            allocation_percent=allocation_percent,
            max_positions=max_positions,
            broker_positions=broker_positions,
            analysis=analysis,
            entry_min=entry_min,
            entry_max=entry_max,
        )
        if exec_detail is None:
            return result
    else:
        exec_detail = await _execute_paper_trade(
            dependencies=dependencies,
            active_id=active_id,
            symbol=symbol,
            side=side,
            signal=signal,
            confidence=confidence,
            current_price=current_price,
            stop_loss=stop_loss,
            allocation_percent=allocation_percent,
            trade_style=trade_style,
            analysis=analysis,
            entry_min=entry_min,
            entry_max=entry_max,
        )

    result.events.append(
        AutomationExecutionEvent(active_id, symbol, "execute", "success", exec_detail)
    )
    result.last_signal_key = signal_key
    result.last_execution_at = now()
    result.strategy_execution_updates[active_id] = result.last_execution_at
    result.executed_trades.append(exec_detail)
    return result


async def _execute_live_trade(
    *,
    context: AutomationCycleContext,
    dependencies: AutomationCycleDependencies,
    result: AutomationCycleResult,
    active_id: str,
    symbol: str,
    side: str,
    signal: str,
    confidence: float,
    current_price: float,
    stop_loss: float,
    allocation_percent: float,
    max_positions: int,
    broker_positions: list[Any],
    analysis: dict[str, Any],
    entry_min: float,
    entry_max: float,
) -> Optional[dict[str, Any]]:
    try:
        balance_obj = await dependencies.broker_manager.get_balance(context.broker_id)
    except BrokerOperationError as exc:
        _error(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason="broker_balance_failed",
            message=exc.detail,
            detail={"detail": exc.detail, "category": exc.category},
        )
        return None

    account_balance = balance_obj.available_margin if balance_obj else 0.0
    if account_balance <= 0:
        _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason="no_broker_balance",
        )
        return None

    quantity = _calculate_live_units(
        symbol,
        account_balance,
        allocation_percent,
        current_price,
        stop_loss,
    )
    risk_gate = dependencies.live_risk_validator(
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
        _skip(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason=risk_gate.reason,
            detail=risk_gate.detail,
        )
        return None

    order_side = OrderSide.BUY if side == "buy" else OrderSide.SELL
    result.attempted_trades.append({
        "strategy_id": active_id,
        "symbol": symbol,
        "side": side,
        "quantity": quantity,
        "mode": "live",
    })
    try:
        broker_order = await dependencies.broker_manager.place_order(
            broker_id=context.broker_id,
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
        _error(
            result,
            strategy_id=active_id,
            symbol=symbol,
            action="execute",
            reason="broker_order_failed",
            message=exc.detail,
            detail={"detail": exc.detail, "category": exc.category},
        )
        return None

    return {
        "signal": signal,
        "confidence": confidence,
        "side": side,
        "price": current_price,
        "quantity": quantity,
        "mode": "live",
        "broker_id": context.broker_id,
        "order_id": broker_order.order_id,
        "riskCheck": risk_gate.detail,
        "entryMin": entry_min,
        "entryMax": entry_max,
        "stopLoss": stop_loss,
        "takeProfit1": analysis.get("takeProfit1"),
        "takeProfit2": analysis.get("takeProfit2"),
        "takeProfit3": analysis.get("takeProfit3"),
    }


async def _execute_paper_trade(
    *,
    dependencies: AutomationCycleDependencies,
    active_id: str,
    symbol: str,
    side: str,
    signal: str,
    confidence: float,
    current_price: float,
    stop_loss: float,
    allocation_percent: float,
    trade_style: str,
    analysis: dict[str, Any],
    entry_min: float,
    entry_max: float,
) -> dict[str, Any]:
    stop_distance = abs(current_price - stop_loss)
    risk_amount = dependencies.repository.get_paper_account().get("balance", 10000.0) * (
        allocation_percent / 100.0
    )
    quantity = max(0.01, risk_amount / stop_distance) if stop_distance > 0 else 0.01
    rounded_quantity = round(quantity, 2)
    await dependencies.paper_order_executor(
        PaperOrderCommand(
            symbol=symbol,
            side=side,
            quantity=rounded_quantity,
            price=current_price,
            stop_loss=stop_loss,
            take_profit_1=analysis.get("takeProfit1"),
            take_profit_2=analysis.get("takeProfit2"),
            take_profit_3=analysis.get("takeProfit3"),
            risk_percent=allocation_percent,
            trade_style=trade_style,
            confidence=confidence,
            strategy_id=active_id,
        )
    )
    return {
        "signal": signal,
        "confidence": confidence,
        "side": side,
        "price": current_price,
        "quantity": rounded_quantity,
        "mode": "paper",
        "entryMin": entry_min,
        "entryMax": entry_max,
        "stopLoss": stop_loss,
        "takeProfit1": analysis.get("takeProfit1"),
        "takeProfit2": analysis.get("takeProfit2"),
        "takeProfit3": analysis.get("takeProfit3"),
    }
