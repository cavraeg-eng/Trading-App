"""AI prediction and suggestion contract endpoints."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from trading_bot.api.models import (
    PredictionAccountContextStatus,
    PredictionAssetClass,
    PredictionBrokerContext,
    PredictionChartOverlay,
    PredictionConfidenceBand,
    PredictionFreshnessMetadata,
    PredictionLatencyMetadata,
    PredictionNoTradeReason,
    PredictionPositionSize,
    PredictionPriceZone,
    PredictionRationaleItem,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionRiskConstraints,
    PredictionStrategyMode,
    PredictionSuggestionCard,
    PredictionTarget,
    PredictionWarning,
    PredictionWarningCode,
    confidence_band_for_score,
)
from trading_bot.api.routes.market import ALLOWED_SYMBOLS, analyze_symbol, map_symbol_to_yf
from trading_bot.config import get_logger, get_settings
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager

logger = get_logger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


def _asset_class_for_symbol(symbol: str) -> PredictionAssetClass:
    normalized = symbol.upper()
    if normalized in {"XAU/USD", "XAG/USD"}:
        return PredictionAssetClass.METAL
    if normalized in {"BTC/USD", "ETH/USD", "BTC-USD", "ETH-USD"}:
        return PredictionAssetClass.CRYPTO
    if normalized in {"US500", "US30", "US100", "^GSPC", "^DJI"}:
        return PredictionAssetClass.INDEX
    if "/" in normalized or normalized.endswith("=X"):
        return PredictionAssetClass.FOREX
    return PredictionAssetClass.UNKNOWN


def _broker_environment(broker_info: dict[str, Any]) -> Optional[str]:
    info = broker_info.get("info") or {}
    environment = info.get("environment") or broker_info.get("environment")
    return str(environment).lower() if environment else None


async def _account_context_from_broker(broker_id: Optional[str], symbol: str) -> Optional[PredictionBrokerContext]:
    selected_broker_id = broker_id
    broker_info = None
    if selected_broker_id:
        broker_info = broker_manager.get_broker_status(selected_broker_id)
    else:
        broker_info = broker_manager.get_active_broker_info()
        selected_broker_id = broker_info.get("id") if broker_info else None

    if not selected_broker_id or not broker_info or not broker_info.get("exists") or not broker_info.get("connected"):
        return None

    settings = get_settings()
    balance = None
    try:
        balance = await broker_manager.get_balance(selected_broker_id)
    except BrokerOperationError as exc:
        logger.warning(f"Prediction account balance context unavailable: {exc.category}")
    try:
        broker_positions = await broker_manager.get_positions(selected_broker_id)
    except BrokerOperationError as exc:
        logger.warning(f"Prediction account position context unavailable: {exc.category}")
        broker_positions = []

    positions = []
    for position in broker_positions:
        current_price = float(position.current_price or 0.0)
        quantity = float(position.quantity or 0.0)
        positions.append({
            "symbol": position.symbol,
            "side": position.side,
            "quantity": quantity,
            "average_price": position.entry_price,
            "current_price": position.current_price,
            "unrealized_pnl": position.unrealized_pnl,
            "notional_exposure": abs(quantity * current_price) if current_price > 0 else None,
        })

    equity = float(balance.total_equity) if balance else None
    return PredictionBrokerContext(
        broker_id=selected_broker_id,
        account_mode=_broker_environment(broker_info) or settings.trading_mode.value,
        base_currency=balance.currency if balance else None,
        balance=equity,
        equity=equity,
        available_margin=float(balance.available_margin) if balance else None,
        used_margin=float(balance.used_margin) if balance else None,
        open_positions=len(broker_positions),
        positions=positions,
        max_risk_percent=float(settings.risk_per_trade) * 100,
        risk_constraints=PredictionRiskConstraints(
            risk_percent=float(settings.risk_per_trade) * 100,
            daily_loss_limit=float(settings.max_daily_drawdown),
            max_position_size=float(settings.max_position_size),
            max_open_positions=int(settings.max_positions),
            max_total_exposure=float(settings.max_total_exposure),
            trading_mode=settings.trading_mode.value,
        ),
        context_timestamp=datetime.now(tz=timezone.utc),
    )


async def _request_with_account_context(
    request: PredictionRequest,
    broker_id: Optional[str] = None,
) -> PredictionRequest:
    if request.broker_context is not None:
        return request
    context = await _account_context_from_broker(broker_id, request.symbol)
    if context is None:
        return request
    return request.model_copy(update={"broker_context": context})


def _recommendation_from_signal(signal: object, confidence: float) -> PredictionRecommendation:
    normalized = str(signal or "").lower()
    if normalized == "buy":
        return PredictionRecommendation.BUY
    if normalized == "sell":
        return PredictionRecommendation.SELL
    if confidence < 45:
        return PredictionRecommendation.NO_TRADE
    return PredictionRecommendation.HOLD


def _trade_style_for_strategy_mode(strategy_mode: PredictionStrategyMode) -> str:
    if strategy_mode == PredictionStrategyMode.SCALP:
        return "scalp"
    return "swing"


def _no_trade_reason(analysis: Optional[dict[str, Any]], metadata: dict[str, Any]) -> PredictionNoTradeReason:
    quality_flags = list(metadata.get("qualityFlags") or [])
    if analysis is None:
        return PredictionNoTradeReason.INSUFFICIENT_DATA
    if any(str(flag).startswith("stale_data") for flag in quality_flags):
        return PredictionNoTradeReason.STALE_DATA
    reason = str(analysis.get("reason") or "").lower()
    if "reward-to-risk" in reason or "reward-to-risk is too compressed" in reason:
        return PredictionNoTradeReason.REWARD_RISK_COMPRESSED
    if "mixed" in reason or "conflicting" in reason:
        return PredictionNoTradeReason.CONFLICTING_SIGNALS
    return PredictionNoTradeReason.LOW_CONFIDENCE


def _freshness_metadata(metadata: dict[str, Any]) -> PredictionFreshnessMetadata:
    last_bar = metadata.get("lastBarTimestamp")
    if isinstance(last_bar, (int, float)):
        last_bar_timestamp = datetime.fromtimestamp(float(last_bar), tz=timezone.utc)
    elif isinstance(last_bar, str):
        try:
            last_bar_timestamp = datetime.fromisoformat(last_bar.replace("Z", "+00:00"))
        except ValueError:
            last_bar_timestamp = None
    else:
        last_bar_timestamp = None

    return PredictionFreshnessMetadata(
        source_name=metadata.get("sourceName"),
        source_type=metadata.get("sourceType"),
        price_source=metadata.get("priceSource"),
        is_fallback=bool(metadata.get("isFallback", False)),
        freshness_seconds=metadata.get("freshnessSeconds"),
        last_bar_timestamp=last_bar_timestamp,
        market_status=metadata.get("marketStatus"),
        quality_flags=list(metadata.get("qualityFlags") or []),
    )


def _warnings_from_metadata(metadata: dict[str, Any]) -> list[PredictionWarning]:
    warnings: list[PredictionWarning] = []
    quality_flags = [str(flag) for flag in metadata.get("qualityFlags") or []]
    if metadata.get("isFallback") or "fallback_source" in quality_flags:
        warnings.append(PredictionWarning(
            code=PredictionWarningCode.FALLBACK_DATA,
            severity="warning",
            message="Prediction used a fallback market data source.",
        ))
    if any(flag.startswith("stale_data") for flag in quality_flags):
        warnings.append(PredictionWarning(
            code=PredictionWarningCode.STALE_DATA,
            severity="warning",
            message="Prediction input data may be stale.",
        ))
    return warnings


def _warning(code: PredictionWarningCode, message: str, severity: str = "warning") -> PredictionWarning:
    return PredictionWarning(code=code, severity=severity, message=message)


def _entry_midpoint(entry: Optional[PredictionPriceZone], current_price: Optional[float]) -> Optional[float]:
    if entry:
        return (entry.min + entry.max) / 2
    return current_price


def _context_status(request: PredictionRequest, now: datetime) -> PredictionAccountContextStatus:
    context = request.broker_context
    if context is None:
        return PredictionAccountContextStatus.MISSING
    if context.context_timestamp and context.max_context_age_seconds is not None:
        context_timestamp = context.context_timestamp
        if context_timestamp.tzinfo is None or context_timestamp.tzinfo.utcoffset(context_timestamp) is None:
            context_timestamp = context_timestamp.replace(tzinfo=timezone.utc)
        age = (now - context_timestamp).total_seconds()
        if age > context.max_context_age_seconds:
            return PredictionAccountContextStatus.STALE
    has_balance = context.equity is not None or context.balance is not None
    has_margin = context.available_margin is not None
    has_positions = bool(context.positions) or context.open_positions > 0
    has_risk = bool(context.max_risk_percent or context.risk_constraints)
    if has_balance and has_margin and has_risk:
        return PredictionAccountContextStatus.AVAILABLE
    if has_balance or has_margin or has_positions or has_risk:
        return PredictionAccountContextStatus.PARTIAL
    return PredictionAccountContextStatus.MISSING


def _constraint_amount(limit: Optional[float], equity: Optional[float]) -> Optional[float]:
    if limit is None or limit <= 0:
        return None
    if equity and 0 < limit <= 1:
        return equity * limit
    return limit


def _risk_percent(request: PredictionRequest) -> Optional[float]:
    context = request.broker_context
    if context:
        constraints = context.risk_constraints
        if constraints and constraints.risk_percent is not None:
            return constraints.risk_percent
        if context.max_risk_percent is not None:
            return context.max_risk_percent
    settings = get_settings()
    return float(settings.risk_per_trade) * 100


def _position_exposure(position: Any) -> float:
    if position.notional_exposure is not None:
        return abs(float(position.notional_exposure))
    if position.quantity is not None and position.current_price is not None:
        return abs(float(position.quantity) * float(position.current_price))
    if position.quantity is not None and position.average_price is not None:
        return abs(float(position.quantity) * float(position.average_price))
    return 0.0


def _side_matches_recommendation(side: Optional[str], recommendation: PredictionRecommendation) -> bool:
    normalized = str(side or "").lower()
    if recommendation == PredictionRecommendation.BUY:
        return normalized in {"long", "buy"}
    if recommendation == PredictionRecommendation.SELL:
        return normalized in {"short", "sell"}
    return False


def _opposes_recommendation(side: Optional[str], recommendation: PredictionRecommendation) -> bool:
    normalized = str(side or "").lower()
    if recommendation == PredictionRecommendation.BUY:
        return normalized in {"short", "sell"}
    if recommendation == PredictionRecommendation.SELL:
        return normalized in {"long", "buy"}
    return False


def _position_size_guidance(
    request: PredictionRequest,
    recommendation: PredictionRecommendation,
    entry: Optional[PredictionPriceZone],
    stop_loss: Optional[float],
    current_price: Optional[float],
) -> tuple[Optional[PredictionPositionSize], str, list[PredictionWarning]]:
    if recommendation not in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}:
        return None, "Position sizing is not applicable for non-actionable recommendations.", []

    context = request.broker_context
    if context is None:
        return None, "Position sizing unavailable because account context is missing.", [
            _warning(
                PredictionWarningCode.POSITION_SIZING_UNAVAILABLE,
                "Position sizing unavailable because account context is missing.",
            )
        ]

    equity = context.equity if context.equity is not None else context.balance
    if equity is None or equity <= 0:
        return None, "Position sizing unavailable because account equity or balance is missing.", [
            _warning(
                PredictionWarningCode.POSITION_SIZING_UNAVAILABLE,
                "Position sizing unavailable because account equity or balance is missing.",
            )
        ]

    risk_percent = _risk_percent(request)
    if risk_percent is None or risk_percent <= 0:
        return None, "Position sizing unavailable because risk percent is not configured.", [
            _warning(
                PredictionWarningCode.POSITION_SIZING_UNAVAILABLE,
                "Position sizing unavailable because risk percent is not configured.",
            )
        ]

    entry_price = _entry_midpoint(entry, current_price)
    if entry_price is None or stop_loss is None:
        return None, "Position sizing unavailable because entry or stop loss is missing.", [
            _warning(
                PredictionWarningCode.POSITION_SIZING_UNAVAILABLE,
                "Position sizing unavailable because entry or stop loss is missing.",
            )
        ]

    stop_distance = abs(entry_price - stop_loss)
    if stop_distance <= 0:
        return None, "Position sizing unavailable because stop distance is invalid.", [
            _warning(
                PredictionWarningCode.POSITION_SIZING_UNAVAILABLE,
                "Position sizing unavailable because stop distance is invalid.",
            )
        ]

    risk_amount = float(equity) * (risk_percent / 100)
    quantity = risk_amount / stop_distance
    return (
        PredictionPositionSize(
            quantity=round(quantity, 6),
            risk_amount=round(risk_amount, 2),
            risk_percent=round(risk_percent, 4),
            stop_distance=round(stop_distance, 8),
            notional=round(quantity * entry_price, 2),
        ),
        (
            f"Risking {risk_percent:.2f}% of {context.base_currency or 'account'} equity "
            f"with a {stop_distance:.5f} stop distance."
        ),
        [],
    )


def _account_risk_warnings(
    request: PredictionRequest,
    recommendation: PredictionRecommendation,
    account_context_status: PredictionAccountContextStatus,
    position_size: Optional[PredictionPositionSize],
) -> list[PredictionWarning]:
    context = request.broker_context
    warnings: list[PredictionWarning] = []
    if account_context_status == PredictionAccountContextStatus.MISSING:
        warnings.append(_warning(
            PredictionWarningCode.ACCOUNT_CONTEXT_MISSING,
            "Account context is missing; suggestion does not include account-aware risk checks.",
        ))
        return warnings
    if account_context_status == PredictionAccountContextStatus.PARTIAL:
        warnings.append(_warning(
            PredictionWarningCode.ACCOUNT_CONTEXT_PARTIAL,
            "Account context is partial; some risk checks may be unavailable.",
        ))
    elif account_context_status == PredictionAccountContextStatus.STALE:
        warnings.append(_warning(
            PredictionWarningCode.ACCOUNT_CONTEXT_STALE,
            "Account context is stale; refresh broker data before acting on this suggestion.",
            "block",
        ))

    if context is None:
        return warnings

    constraints = context.risk_constraints
    equity = context.equity if context.equity is not None else context.balance
    actionable = recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}
    trading_mode = str(
        (constraints.trading_mode if constraints else None) or context.account_mode or ""
    ).lower()
    if trading_mode in {"disabled", "read_only", "readonly", "monitor", "view_only"} and actionable:
        warnings.append(_warning(
            PredictionWarningCode.TRADING_MODE_BLOCKED,
            f"Trading mode '{trading_mode}' does not allow new trade suggestions.",
            "block",
        ))

    if constraints and constraints.daily_pnl is not None:
        daily_limit = _constraint_amount(constraints.daily_loss_limit, equity)
        if daily_limit is not None and constraints.daily_pnl <= -daily_limit and actionable:
            warnings.append(_warning(
                PredictionWarningCode.DAILY_LOSS_LIMIT,
                "Daily loss limit has been reached; new trade suggestions are blocked.",
                "block",
            ))

    if context.available_margin is not None:
        if context.available_margin <= 0 and actionable:
            warnings.append(_warning(
                PredictionWarningCode.MARGIN_PRESSURE,
                "No available margin remains for a new position.",
                "block",
            ))
        elif equity and context.available_margin / equity < 0.1:
            warnings.append(_warning(
                PredictionWarningCode.MARGIN_PRESSURE,
                "Available margin is below 10% of equity.",
            ))

    same_symbol_positions = [
        position for position in context.positions
        if position.symbol.upper() == request.symbol.upper()
    ]
    if actionable and any(_opposes_recommendation(position.side, recommendation) for position in same_symbol_positions):
        warnings.append(_warning(
            PredictionWarningCode.OPEN_POSITION_CONFLICT,
            "An existing open position conflicts with the suggested direction.",
            "block",
        ))

    open_position_count = len(context.positions) if context.positions else context.open_positions
    if constraints and constraints.max_open_positions is not None and actionable:
        if open_position_count >= constraints.max_open_positions:
            warnings.append(_warning(
                PredictionWarningCode.EXPOSURE_LIMIT,
                "Maximum open position count has already been reached.",
                "block",
            ))

    existing_symbol_exposure = sum(_position_exposure(position) for position in same_symbol_positions)
    existing_total_exposure = sum(_position_exposure(position) for position in context.positions)
    new_notional = position_size.notional if position_size else None
    if constraints:
        max_symbol_exposure = _constraint_amount(constraints.max_symbol_exposure, equity)
        if max_symbol_exposure is not None and actionable:
            projected_symbol_exposure = existing_symbol_exposure + (new_notional or 0)
            if projected_symbol_exposure >= max_symbol_exposure:
                warnings.append(_warning(
                    PredictionWarningCode.EXPOSURE_LIMIT,
                    "Projected symbol exposure exceeds the configured limit.",
                    "block",
                ))

        max_total_exposure = _constraint_amount(constraints.max_total_exposure, equity)
        if max_total_exposure is not None and actionable:
            projected_total_exposure = existing_total_exposure + (new_notional or 0)
            if projected_total_exposure >= max_total_exposure:
                warnings.append(_warning(
                    PredictionWarningCode.EXPOSURE_LIMIT,
                    "Projected total exposure exceeds the configured limit.",
                    "block",
                ))

        max_position_notional = _constraint_amount(
            constraints.max_position_notional or constraints.max_position_size,
            equity,
        )
        if max_position_notional is not None and new_notional is not None and new_notional > max_position_notional:
            warnings.append(_warning(
                PredictionWarningCode.RISK_LIMITS,
                "Recommended position size exceeds the configured per-position limit.",
                "block",
            ))

    if actionable and same_symbol_positions and all(
        _side_matches_recommendation(position.side, recommendation) for position in same_symbol_positions
    ):
        warnings.append(_warning(
            PredictionWarningCode.OPEN_POSITION_CONFLICT,
            "There is already an open position in the suggested direction.",
        ))

    return warnings


def _rationale(analysis: Optional[dict[str, Any]]) -> list[PredictionRationaleItem]:
    if analysis is None:
        return [PredictionRationaleItem(category="data", summary="Market data was unavailable.")]

    items = [PredictionRationaleItem(category="summary", summary=str(analysis.get("reason") or "Prediction generated."))]
    for indicator in analysis.get("indicators", [])[:5]:
        items.append(PredictionRationaleItem(
            category="indicator",
            summary=f"{indicator.get('name')}: {indicator.get('value')}",
            direction=indicator.get("signal"),
        ))
    return items


def _targets(analysis: dict[str, Any]) -> list[PredictionTarget]:
    targets: list[PredictionTarget] = []
    risk_reward = analysis.get("riskReward")
    target_risk_reward = float(risk_reward) if risk_reward is not None else None
    for index, key in enumerate(("takeProfit1", "takeProfit2", "takeProfit3"), start=1):
        price = analysis.get(key)
        if price is None:
            continue
        targets.append(PredictionTarget(
            label=f"TP{index}",
            price=float(price),
            reward_risk=target_risk_reward,
        ))
    return targets


def _trade_setup_levels(
    analysis: dict[str, Any],
) -> tuple[
    Optional[PredictionPriceZone],
    Optional[float],
    list[PredictionTarget],
    Optional[float],
    Optional[float],
]:
    entry_range = analysis.get("entryRange") or {}
    current_price = analysis.get("currentPrice", 0)
    entry = PredictionPriceZone(
        min=float(entry_range.get("min", current_price)),
        max=float(entry_range.get("max", current_price)),
        label="Entry zone",
    )
    stop_loss_raw = analysis.get("stopLoss")
    risk_reward_raw = analysis.get("riskReward")
    stop_loss = float(stop_loss_raw) if stop_loss_raw is not None else None
    risk_reward = float(risk_reward_raw) if risk_reward_raw is not None else None
    targets = _targets(analysis)
    invalidation = stop_loss
    return entry, stop_loss, targets, invalidation, risk_reward


def build_prediction_response(request: PredictionRequest) -> PredictionResponse:
    """Build a contract-compliant prediction response from current analysis."""
    if request.symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(request.symbol) not in ALLOWED_SYMBOLS:
        return _unsupported_asset_response(request)

    started_at = datetime.now(tz=timezone.utc)
    account_context_status = _context_status(request, started_at)
    trade_style = _trade_style_for_strategy_mode(request.strategy_mode)
    analysis = analyze_symbol(request.symbol, request.timeframe, trade_style=trade_style)
    _, metadata = get_ohlcv_with_metadata(request.symbol, request.timeframe, trade_style=trade_style)
    elapsed_ms = (datetime.now(tz=timezone.utc) - started_at).total_seconds() * 1000

    confidence = float((analysis or {}).get("confidence", 0))
    recommendation = _recommendation_from_signal((analysis or {}).get("signal"), confidence)
    freshness = _freshness_metadata(metadata)
    warnings = _warnings_from_metadata(metadata)
    entry = None
    targets: list[PredictionTarget] = []
    stop_loss = None
    invalidation = None
    risk_reward = None
    no_trade_reason = None

    if recommendation == PredictionRecommendation.NO_TRADE:
        no_trade_reason = _no_trade_reason(analysis, metadata)
    elif analysis and recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}:
        entry, stop_loss, targets, invalidation, risk_reward = _trade_setup_levels(analysis)

    if (
        recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}
        and (entry is None or stop_loss is None or not targets or risk_reward is None)
    ):
        recommendation = PredictionRecommendation.NO_TRADE
        no_trade_reason = PredictionNoTradeReason.INSUFFICIENT_DATA
        entry = None
        stop_loss = None
        targets = []
        invalidation = None
        risk_reward = None

    current_price = (analysis or {}).get("currentPrice")
    current_price_float = float(current_price) if current_price is not None else None
    position_size, position_size_reason, sizing_warnings = _position_size_guidance(
        request,
        recommendation,
        entry,
        stop_loss,
        current_price_float,
    )
    account_risk_warnings = [
        *sizing_warnings,
        *_account_risk_warnings(request, recommendation, account_context_status, position_size),
    ]
    trade_allowed = not any(warning.severity == "block" for warning in account_risk_warnings)
    if recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL} and not trade_allowed:
        recommendation = PredictionRecommendation.NO_TRADE
        no_trade_reason = PredictionNoTradeReason.RISK_LIMITS
        entry = None
        stop_loss = None
        targets = []
        invalidation = None
        risk_reward = None
        position_size = None
        position_size_reason = "Position sizing withheld because account risk checks blocked this suggestion."

    chart = PredictionChartOverlay(
        current_price=current_price_float,
        entry_zone=entry,
        stop_loss=stop_loss,
        take_profit_targets=targets,
        invalidation_level=invalidation,
        support=((analysis or {}).get("anchorModel") or {}).get("support"),
        resistance=((analysis or {}).get("anchorModel") or {}).get("resistance"),
    )
    badge = recommendation.value.replace("_", " ").title()
    suggestion = PredictionSuggestionCard(
        title=f"{request.symbol} {badge}",
        subtitle=f"{request.timeframe} · {request.strategy_mode.value}",
        badge=badge,
        summary=str((analysis or {}).get("reason") or no_trade_reason or "Prediction generated."),
        primary_metric_label="Confidence",
        primary_metric_value=f"{confidence:.0f}%",
        action_label="Review setup" if recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL} else "Stand aside",
    )

    return PredictionResponse(
        prediction_id=f"pred_{uuid4().hex}",
        request=request,
        symbol=request.symbol,
        asset_class=request.asset_class if request.asset_class != PredictionAssetClass.UNKNOWN else _asset_class_for_symbol(request.symbol),
        timeframe=request.timeframe,
        strategy_mode=request.strategy_mode,
        recommendation=recommendation,
        confidence=confidence,
        confidence_band=confidence_band_for_score(confidence),
        no_trade_reason=no_trade_reason,
        entry=entry,
        stop_loss=stop_loss,
        take_profit_targets=targets,
        invalidation_level=invalidation,
        risk_reward=risk_reward,
        rationale=_rationale(analysis),
        warnings=warnings,
        account_risk_warnings=account_risk_warnings,
        account_context_status=account_context_status,
        position_size=position_size,
        position_size_reason=position_size_reason,
        trade_allowed=trade_allowed,
        freshness=freshness,
        latency=PredictionLatencyMetadata(total_latency_ms=round(elapsed_ms, 2), model_name="heuristic_analysis", model_version="1.0"),
        chart=chart,
        suggestion_card=suggestion,
    )


def _unsupported_asset_response(request: PredictionRequest) -> PredictionResponse:
    return PredictionResponse(
        prediction_id=f"pred_{uuid4().hex}",
        request=request,
        symbol=request.symbol,
        asset_class=request.asset_class,
        timeframe=request.timeframe,
        strategy_mode=request.strategy_mode,
        recommendation=PredictionRecommendation.NO_TRADE,
        confidence=0,
        confidence_band=PredictionConfidenceBand.LOW,
        no_trade_reason=PredictionNoTradeReason.UNSUPPORTED_ASSET,
        rationale=[PredictionRationaleItem(category="validation", summary=f"{request.symbol} is not supported.")],
        warnings=[_warning(
            PredictionWarningCode.UNSUPPORTED_ASSET,
            "Prediction is unavailable because the asset is unsupported.",
        )],
        account_risk_warnings=[],
        account_context_status=_context_status(request, datetime.now(tz=timezone.utc)),
        position_size_reason="Position sizing is unavailable for unsupported assets.",
        trade_allowed=False,
        chart=PredictionChartOverlay(),
        suggestion_card=PredictionSuggestionCard(
            title=f"{request.symbol} unsupported",
            badge="No Trade",
            summary="Unsupported asset for prediction contract.",
            action_label="Choose another symbol",
        ),
    )


@router.get("/contract")
async def get_prediction_contract() -> dict:
    """Return machine-readable enums and compatibility guidance for consumers."""
    return {
        "schema": "PredictionRequest -> PredictionResponse",
        "recommendations": [item.value for item in PredictionRecommendation],
        "noTradeReasons": [item.value for item in PredictionNoTradeReason],
        "confidenceBands": [item.value for item in PredictionConfidenceBand],
        "warningCodes": [item.value for item in PredictionWarningCode],
        "accountContextStatuses": [item.value for item in PredictionAccountContextStatus],
        "compatibility": PredictionResponse.model_fields["compatibility"].default,
        "requiredForEveryResponse": [
            "prediction_id",
            "request",
            "symbol",
            "asset_class",
            "timeframe",
            "strategy_mode",
            "recommendation",
            "confidence",
            "confidence_band",
            "rationale",
            "freshness",
            "latency",
            "chart",
            "suggestion_card",
            "generated_at",
        ],
        "requiredForBuySell": ["entry", "stop_loss", "take_profit_targets", "risk_reward", "invalidation_level"],
        "requiredForNoTrade": ["no_trade_reason"],
        "optionalAccountRiskFields": [
            "account_context_status",
            "account_risk_warnings",
            "position_size",
            "position_size_reason",
            "trade_allowed",
        ],
        "strategyModeTradeStyleMap": {
            "scalp": "scalp",
            "swing": "swing",
            "intraday": "swing",
            "position": "swing",
            "automation": "swing",
        },
    }


@router.post("/suggestion", response_model=PredictionResponse)
async def create_prediction_suggestion(request: PredictionRequest) -> PredictionResponse:
    """Create a contract-compliant AI prediction/suggestion response."""
    try:
        enriched_request = await _request_with_account_context(request)
        return build_prediction_response(enriched_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/suggestion/{symbol:path}", response_model=PredictionResponse)
async def get_prediction_suggestion(
    symbol: str,
    timeframe: str = "1h",
    strategy_mode: PredictionStrategyMode = PredictionStrategyMode.SWING,
    broker_id: Optional[str] = None,
) -> PredictionResponse:
    """Convenience GET endpoint for scanner and workspace consumers."""
    request = PredictionRequest(
        symbol=symbol,
        asset_class=_asset_class_for_symbol(symbol),
        timeframe=timeframe,
        strategy_mode=strategy_mode,
    )
    try:
        enriched_request = await _request_with_account_context(request, broker_id=broker_id)
        return build_prediction_response(enriched_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
