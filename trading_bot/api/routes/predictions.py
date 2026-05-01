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
    PredictionNoTradeDetail,
    PredictionNoTradeReason,
    PredictionPositionSize,
    PredictionPriceZone,
    PredictionRationale,
    PredictionRationaleCategory,
    PredictionRationaleFactor,
    PredictionRationaleStance,
    PredictionRationaleStrength,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionRiskConstraints,
    PredictionStrategyMode,
    PredictionSuggestionCard,
    PredictionWarning,
    PredictionWarningCode,
    confidence_band_for_score,
)
from trading_bot.api.routes.market import ALLOWED_SYMBOLS, analyze_symbol, map_symbol_to_yf
from trading_bot.config import get_logger, get_settings
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager
from trading_bot.services.prediction_quality import NoTradeGate, evaluate_prediction_quality
from trading_bot.services.trade_suggestions import generate_trade_suggestion

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


def _recommendation_from_signal(signal: object) -> PredictionRecommendation:
    normalized = str(signal or "").lower()
    if normalized == "buy":
        return PredictionRecommendation.BUY
    if normalized == "sell":
        return PredictionRecommendation.SELL
    return PredictionRecommendation.HOLD


def _trade_style_for_strategy_mode(strategy_mode: PredictionStrategyMode) -> str:
    if strategy_mode == PredictionStrategyMode.SCALP:
        return "scalp"
    return "swing"


def _no_trade_details(gates: list[NoTradeGate]) -> list[PredictionNoTradeDetail]:
    return [
        PredictionNoTradeDetail(
            code=gate.code,
            message=gate.message,
            blocking=gate.blocking,
            context=gate.context,
        )
        for gate in gates
    ]


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


def _warnings_from_gates(gates: list[NoTradeGate]) -> list[PredictionWarning]:
    warnings: list[PredictionWarning] = []
    for gate in gates:
        if gate.code == PredictionNoTradeReason.EXCESSIVE_SPREAD:
            warnings.append(_warning(
                PredictionWarningCode.WIDE_SPREAD,
                gate.message,
            ))
        elif gate.code == PredictionNoTradeReason.HIGH_VOLATILITY_SPIKE:
            warnings.append(_warning(
                PredictionWarningCode.HIGH_VOLATILITY,
                gate.message,
            ))
        elif gate.code == PredictionNoTradeReason.RISK_LIMITS:
            warnings.append(_warning(
                PredictionWarningCode.RISK_LIMITS,
                gate.message,
                "block",
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


def _confidence_label(confidence: float) -> str:
    return confidence_band_for_score(confidence).value


def _indicator_category(name: str) -> PredictionRationaleCategory:
    normalized = name.lower()
    if "ema" in normalized:
        return PredictionRationaleCategory.TREND
    if "rsi" in normalized or "macd" in normalized:
        return PredictionRationaleCategory.MOMENTUM
    if "bb" in normalized or "bollinger" in normalized:
        return PredictionRationaleCategory.SUPPORT_RESISTANCE
    if "volume" in normalized:
        return PredictionRationaleCategory.VOLATILITY
    return PredictionRationaleCategory.MOMENTUM


def _factor_strength(indicator: dict[str, Any]) -> PredictionRationaleStrength:
    signal = str(indicator.get("signal") or "").lower()
    name = str(indicator.get("name") or "").lower()
    if signal == "neutral":
        return PredictionRationaleStrength.WEAK
    if "macd" in name or "rsi" in name:
        return PredictionRationaleStrength.STRONG
    return PredictionRationaleStrength.MEDIUM


def _factor(
    *,
    category: PredictionRationaleCategory,
    stance: PredictionRationaleStance,
    message: str,
    strength: PredictionRationaleStrength = PredictionRationaleStrength.MEDIUM,
    direction: Optional[str] = None,
    source: Optional[str] = None,
    weight: Optional[float] = None,
) -> PredictionRationaleFactor:
    return PredictionRationaleFactor(
        category=category,
        stance=stance,
        strength=strength,
        message=message,
        direction=direction,
        source=source,
        weight=weight,
    )


def _indicator_factor(
    indicator: dict[str, Any],
    recommendation: PredictionRecommendation,
) -> PredictionRationaleFactor:
    name = str(indicator.get("name") or "Indicator")
    value = str(indicator.get("value") or "n/a")
    direction = str(indicator.get("signal") or "neutral").lower()
    supportive_direction = {
        PredictionRecommendation.BUY: "bullish",
        PredictionRecommendation.SELL: "bearish",
    }.get(recommendation)

    if supportive_direction is None:
        stance = PredictionRationaleStance.SUPPORTIVE if direction == "neutral" else PredictionRationaleStance.WEAK
    elif direction == supportive_direction:
        stance = PredictionRationaleStance.SUPPORTIVE
    elif direction in {"bullish", "bearish"}:
        stance = PredictionRationaleStance.CONFLICTING
    else:
        stance = PredictionRationaleStance.WEAK

    return _factor(
        category=_indicator_category(name),
        stance=stance,
        strength=_factor_strength(indicator),
        message=f"{name} reads {value} with a {direction} signal.",
        direction=direction,
        source=name,
    )


def _no_trade_blocker(
    reason: Optional[PredictionNoTradeReason],
) -> tuple[PredictionRationaleFactor, list[str]]:
    if reason == PredictionNoTradeReason.STALE_DATA:
        return (
            _factor(
                category=PredictionRationaleCategory.DATA_QUALITY,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="Market data is stale, so the setup is not safe to action.",
            ),
            ["Refresh market data before considering a setup."],
        )
    if reason == PredictionNoTradeReason.INSUFFICIENT_DATA:
        return (
            _factor(
                category=PredictionRationaleCategory.DATA_QUALITY,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="There is not enough market data to validate a trade setup.",
            ),
            ["Wait for enough valid candles and indicators to be available."],
        )
    if reason == PredictionNoTradeReason.CONFLICTING_SIGNALS:
        return (
            _factor(
                category=PredictionRationaleCategory.MOMENTUM,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.MEDIUM,
                message="Directional signals are mixed, so there is no clean trade bias.",
            ),
            ["Momentum and trend need to align in the same direction."],
        )
    if reason == PredictionNoTradeReason.REWARD_RISK_COMPRESSED:
        return (
            _factor(
                category=PredictionRationaleCategory.SUPPORT_RESISTANCE,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.MEDIUM,
                message="Nearby structure compresses reward-to-risk below the required threshold.",
            ),
            ["Wait for more target runway or a tighter invalidation level."],
        )
    if reason == PredictionNoTradeReason.RISK_LIMITS:
        return (
            _factor(
                category=PredictionRationaleCategory.ACCOUNT_RISK,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="Account risk limits prevent opening a new trade.",
            ),
            ["Reduce exposure or wait for risk budget to become available."],
        )
    if reason == PredictionNoTradeReason.UNSUPPORTED_ASSET:
        return (
            _factor(
                category=PredictionRationaleCategory.VALIDATION,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="This symbol is not supported by the prediction contract.",
            ),
            ["Choose a supported forex, metal, crypto, or index symbol."],
        )
    if reason == PredictionNoTradeReason.EXCESSIVE_SPREAD:
        return (
            _factor(
                category=PredictionRationaleCategory.SPREAD,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="Spread is too wide for disciplined execution.",
            ),
            ["Wait for spread and execution quality to normalize."],
        )
    if reason == PredictionNoTradeReason.HIGH_VOLATILITY_SPIKE:
        return (
            _factor(
                category=PredictionRationaleCategory.VOLATILITY,
                stance=PredictionRationaleStance.BLOCKING,
                strength=PredictionRationaleStrength.STRONG,
                message="A volatility spike makes the setup unsuitable for action.",
            ),
            ["Wait for volatility to stabilize before reassessing."],
        )
    return (
        _factor(
            category=PredictionRationaleCategory.CONFIDENCE,
            stance=PredictionRationaleStance.BLOCKING,
            strength=PredictionRationaleStrength.MEDIUM,
            message="Confidence is too low for a disciplined trade decision.",
        ),
        ["Wait for stronger confirmation and a higher confidence score."],
    )


def _structured_rationale(
    analysis: Optional[dict[str, Any]],
    recommendation: PredictionRecommendation,
    confidence: float,
    warnings: list[PredictionWarning],
    no_trade_reason: Optional[PredictionNoTradeReason],
    request: PredictionRequest,
) -> PredictionRationale:
    primary_reasons: list[PredictionRationaleFactor] = []
    conflicts: list[PredictionRationaleFactor] = []
    blockers: list[PredictionRationaleFactor] = []
    next_conditions: list[str] = []

    if analysis is None:
        blocker, conditions = _no_trade_blocker(PredictionNoTradeReason.INSUFFICIENT_DATA)
        blockers.append(blocker)
        next_conditions.extend(conditions)
        return PredictionRationale(
            summary="No trade: market data was unavailable, so the system cannot validate a setup.",
            confidence_label=_confidence_label(confidence),
            blockers=blockers,
            next_conditions=next_conditions,
        )

    for indicator in analysis.get("indicators", [])[:6]:
        factor = _indicator_factor(indicator, recommendation)
        if factor.stance == PredictionRationaleStance.CONFLICTING:
            conflicts.append(factor)
        elif factor.stance in {PredictionRationaleStance.SUPPORTIVE, PredictionRationaleStance.WEAK}:
            primary_reasons.append(factor)

    anchor = analysis.get("anchorModel") or {}
    if anchor.get("structureConflict"):
        conflicts.append(_factor(
            category=PredictionRationaleCategory.SUPPORT_RESISTANCE,
            stance=PredictionRationaleStance.CONFLICTING,
            strength=PredictionRationaleStrength.MEDIUM,
            message="Nearby support or resistance limits clean target runway.",
            source="anchorModel",
        ))

    higher_timeframe = analysis.get("higherTimeframeBias") or {}
    direction = str(higher_timeframe.get("direction") or "neutral")
    if direction in {"bullish", "bearish"}:
        expected = "bullish" if recommendation == PredictionRecommendation.BUY else "bearish"
        stance = (
            PredictionRationaleStance.SUPPORTIVE
            if recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL} and direction == expected
            else PredictionRationaleStance.CONFLICTING
            if recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}
            else PredictionRationaleStance.WEAK
        )
        factor = _factor(
            category=PredictionRationaleCategory.TREND,
            stance=stance,
            strength=PredictionRationaleStrength.MEDIUM,
            message=f"Higher-timeframe context is {direction}.",
            direction=direction,
            source="higherTimeframeBias",
        )
        if stance == PredictionRationaleStance.CONFLICTING:
            conflicts.append(factor)
        else:
            primary_reasons.append(factor)

    if any(warning.code == PredictionWarningCode.STALE_DATA for warning in warnings):
        conflicts.append(_factor(
            category=PredictionRationaleCategory.DATA_QUALITY,
            stance=PredictionRationaleStance.CONFLICTING,
            strength=PredictionRationaleStrength.STRONG,
            message="Input data may be stale and should be refreshed before action.",
        ))
    if any(warning.code == PredictionWarningCode.FALLBACK_DATA for warning in warnings):
        conflicts.append(_factor(
            category=PredictionRationaleCategory.DATA_QUALITY,
            stance=PredictionRationaleStance.CONFLICTING,
            strength=PredictionRationaleStrength.MEDIUM,
            message="A fallback data source reduced evidence quality.",
        ))

    broker_context = request.broker_context
    if broker_context and broker_context.max_risk_percent is not None:
        primary_reasons.append(_factor(
            category=PredictionRationaleCategory.ACCOUNT_RISK,
            stance=PredictionRationaleStance.NEUTRAL,
            strength=PredictionRationaleStrength.MEDIUM,
            message=f"Account risk cap is {broker_context.max_risk_percent:g}% for this request.",
        ))

    if no_trade_reason is not None:
        blocker, conditions = _no_trade_blocker(no_trade_reason)
        blockers.append(blocker)
        next_conditions.extend(conditions)

    if not primary_reasons and recommendation != PredictionRecommendation.NO_TRADE:
        primary_reasons.append(_factor(
            category=PredictionRationaleCategory.CONFIDENCE,
            stance=PredictionRationaleStance.WEAK if recommendation == PredictionRecommendation.HOLD else PredictionRationaleStance.SUPPORTIVE,
            strength=PredictionRationaleStrength.WEAK,
            message=str(analysis.get("reason") or "The system generated a cautious prediction summary."),
        ))

    if recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}:
        primary_reasons.append(_factor(
            category=PredictionRationaleCategory.SPREAD,
            stance=PredictionRationaleStance.NEUTRAL,
            strength=PredictionRationaleStrength.MEDIUM,
            message="Execution quality should be checked before placing the trade.",
        ))
        next_conditions.extend([
            "Price remains inside the planned entry zone.",
            "Spread and execution quality stay within acceptable limits.",
            "Risk budget supports the planned position size.",
        ])
    elif recommendation == PredictionRecommendation.HOLD:
        next_conditions.extend([
            "Wait for trend and momentum to align before acting.",
            "Require a clean reward-to-risk setup before upgrading to a trade.",
        ])
    elif not next_conditions:
        next_conditions.append("Wait for clearer evidence before acting.")

    base_summary = str(analysis.get("reason") or "Prediction generated.").rstrip(".")
    if recommendation == PredictionRecommendation.NO_TRADE:
        summary = f"No trade: {base_summary}."
    elif recommendation == PredictionRecommendation.HOLD:
        summary = f"Hold: {base_summary}; wait for cleaner confirmation."
    else:
        action = "Long" if recommendation == PredictionRecommendation.BUY else "Short"
        summary = f"{action} setup: {base_summary}."

    return PredictionRationale(
        summary=summary,
        confidence_label=_confidence_label(confidence),
        primary_reasons=primary_reasons[:8],
        conflicts=conflicts[:5],
        blockers=blockers,
        next_conditions=next_conditions[:5],
    )


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

    quality = evaluate_prediction_quality(analysis, metadata, request.broker_context)
    confidence = quality.confidence
    recommendation = _recommendation_from_signal((analysis or {}).get("signal"))
    freshness = _freshness_metadata(metadata)
    warnings = _warnings_from_metadata(metadata) + _warnings_from_gates(quality.gates)
    trade_suggestion = generate_trade_suggestion(
        analysis,
        recommendation,
        request.timeframe,
        PredictionNoTradeReason.INSUFFICIENT_DATA,
        evaluated_at=started_at,
    )
    recommendation = trade_suggestion.recommendation
    warnings.extend(trade_suggestion.warnings)
    no_trade_reason = trade_suggestion.no_trade_reason
    no_trade_reasons: list[PredictionNoTradeDetail] = []
    if no_trade_reason is not None:
        no_trade_reasons = [PredictionNoTradeDetail(
            code=no_trade_reason,
            message="Actionable trade setup validation rejected this suggestion.",
            context={
                "warnings": [warning.message for warning in trade_suggestion.warnings],
            },
        )]
    rejected_actionable_levels = (
        str((analysis or {}).get("signal") or "").lower() in {"buy", "sell"}
        and trade_suggestion.recommendation == PredictionRecommendation.NO_TRADE
    )

    if quality.gates:
        recommendation = PredictionRecommendation.NO_TRADE
        no_trade_reason = quality.gates[0].code
        no_trade_reasons = _no_trade_details(quality.gates)
        trade_suggestion.entry = None
        trade_suggestion.stop_loss = None
        trade_suggestion.targets = []
        trade_suggestion.invalidation_level = None
        trade_suggestion.risk_reward = None
        trade_suggestion.expires_at = None

    if rejected_actionable_levels and not quality.gates and not no_trade_reasons:
        no_trade_reason = trade_suggestion.no_trade_reason or PredictionNoTradeReason.INSUFFICIENT_DATA
        no_trade_reasons = [PredictionNoTradeDetail(
            code=no_trade_reason,
            message="Actionable trade setup validation rejected this suggestion.",
            context={
                "warnings": [warning.message for warning in trade_suggestion.warnings],
            },
        )]

    current_price = (analysis or {}).get("currentPrice")
    current_price_float = float(current_price) if current_price is not None else None
    position_size, position_size_reason, sizing_warnings = _position_size_guidance(
        request,
        recommendation,
        trade_suggestion.entry,
        trade_suggestion.stop_loss,
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
        no_trade_reasons = [*no_trade_reasons, PredictionNoTradeDetail(
            code=PredictionNoTradeReason.RISK_LIMITS,
            message="Account risk checks blocked this suggestion.",
        )]
        trade_suggestion.entry = None
        trade_suggestion.stop_loss = None
        trade_suggestion.targets = []
        trade_suggestion.invalidation_level = None
        trade_suggestion.risk_reward = None
        trade_suggestion.expires_at = None
        position_size = None
        position_size_reason = "Position sizing withheld because account risk checks blocked this suggestion."

    chart = PredictionChartOverlay(
        current_price=current_price_float,
        entry_zone=trade_suggestion.entry,
        stop_loss=trade_suggestion.stop_loss,
        take_profit_targets=trade_suggestion.targets,
        invalidation_level=trade_suggestion.invalidation_level,
        expires_at=trade_suggestion.expires_at,
        support=((analysis or {}).get("anchorModel") or {}).get("support"),
        resistance=((analysis or {}).get("anchorModel") or {}).get("resistance"),
        annotations=trade_suggestion.annotations,
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
        no_trade_reasons=no_trade_reasons,
        entry=trade_suggestion.entry,
        stop_loss=trade_suggestion.stop_loss,
        take_profit_targets=trade_suggestion.targets,
        invalidation_level=trade_suggestion.invalidation_level,
        risk_reward=trade_suggestion.risk_reward,
        expires_at=trade_suggestion.expires_at,
        rationale=_structured_rationale(analysis, recommendation, confidence, warnings, no_trade_reason, request),
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
    blocker, next_conditions = _no_trade_blocker(PredictionNoTradeReason.UNSUPPORTED_ASSET)
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
        no_trade_reasons=[PredictionNoTradeDetail(
            code=PredictionNoTradeReason.UNSUPPORTED_ASSET,
            message=f"{request.symbol} is not supported.",
        )],
        rationale=PredictionRationale(
            summary=f"No trade: {request.symbol} is not supported by the prediction contract.",
            confidence_label=PredictionConfidenceBand.LOW.value,
            blockers=[blocker],
            next_conditions=next_conditions,
        ),
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
        "rationaleCategories": [item.value for item in PredictionRationaleCategory],
        "rationaleStances": [item.value for item in PredictionRationaleStance],
        "rationaleStrengths": [item.value for item in PredictionRationaleStrength],
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
        "requiredForBuySell": ["entry", "stop_loss", "take_profit_targets", "risk_reward", "invalidation_level", "expires_at"],
        "requiredForNoTrade": ["no_trade_reason", "no_trade_reasons"],
        "rationaleShape": {
            "summary": "Trader-readable explanation text.",
            "confidence_label": "Bucketed confidence label for UI copy.",
            "primary_reasons": "Supportive, weak, or neutral factors the UI can render directly.",
            "conflicts": "Structured evidence that reduces conviction.",
            "blockers": "Hard blockers for no-trade states.",
            "next_conditions": "Conditions that must remain true or improve before action.",
        },
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
