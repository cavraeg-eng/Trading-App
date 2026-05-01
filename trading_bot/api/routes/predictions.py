"""AI prediction and suggestion contract endpoints."""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from trading_bot.api.models import (
    PredictionAssetClass,
    PredictionChartOverlay,
    PredictionConfidenceBand,
    PredictionFreshnessMetadata,
    PredictionLatencyMetadata,
    PredictionNoTradeReason,
    PredictionPriceZone,
    PredictionRationale,
    PredictionRationaleCategory,
    PredictionRationaleFactor,
    PredictionRationaleStance,
    PredictionRationaleStrength,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionStrategyMode,
    PredictionSuggestionCard,
    PredictionTarget,
    PredictionWarning,
    PredictionWarningCode,
    confidence_band_for_score,
)
from trading_bot.api.routes.market import ALLOWED_SYMBOLS, analyze_symbol, map_symbol_to_yf
from trading_bot.config import get_logger
from trading_bot.data.market_data_service import get_ohlcv_with_metadata

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


def _recommendation_from_signal(signal: object, confidence: float) -> PredictionRecommendation:
    normalized = str(signal or "").lower()
    if normalized == "buy":
        return PredictionRecommendation.BUY
    if normalized == "sell":
        return PredictionRecommendation.SELL
    if confidence < 45:
        return PredictionRecommendation.NO_TRADE
    return PredictionRecommendation.HOLD


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


def _targets(analysis: dict[str, Any]) -> list[PredictionTarget]:
    targets: list[PredictionTarget] = []
    risk_reward = analysis.get("riskReward")
    for index, key in enumerate(("takeProfit1", "takeProfit2", "takeProfit3"), start=1):
        price = analysis.get(key)
        if price is None:
            continue
        targets.append(PredictionTarget(
            label=f"TP{index}",
            price=float(price),
            reward_risk=float(risk_reward) if index == 2 and risk_reward is not None else None,
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
    trade_style = "scalp" if request.strategy_mode == PredictionStrategyMode.SCALP else "swing"
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
    elif analysis:
        entry, stop_loss, targets, invalidation, risk_reward = _trade_setup_levels(analysis)

    if (
        recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}
        and (entry is None or stop_loss is None or not targets or risk_reward is None)
    ):
        recommendation = PredictionRecommendation.NO_TRADE
        no_trade_reason = PredictionNoTradeReason.INSUFFICIENT_DATA
        entry = None
        stop_loss = None
        invalidation = None
        risk_reward = None

    current_price = (analysis or {}).get("currentPrice")
    chart = PredictionChartOverlay(
        current_price=float(current_price) if current_price is not None else None,
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
        rationale=_structured_rationale(analysis, recommendation, confidence, warnings, no_trade_reason, request),
        warnings=warnings,
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
        rationale=PredictionRationale(
            summary=f"No trade: {request.symbol} is not supported by the prediction contract.",
            confidence_label=PredictionConfidenceBand.LOW.value,
            blockers=[blocker],
            next_conditions=next_conditions,
        ),
        warnings=[],
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
        "rationaleShape": {
            "summary": "Trader-readable explanation text.",
            "confidence_label": "Bucketed confidence label for UI copy.",
            "primary_reasons": "Supportive, weak, or neutral factors the UI can render directly.",
            "conflicts": "Structured evidence that reduces conviction.",
            "blockers": "Hard blockers for no-trade states.",
            "next_conditions": "Conditions that must remain true or improve before action.",
        },
    }


@router.post("/suggestion", response_model=PredictionResponse)
async def create_prediction_suggestion(request: PredictionRequest) -> PredictionResponse:
    """Create a contract-compliant AI prediction/suggestion response."""
    try:
        return build_prediction_response(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/suggestion/{symbol:path}", response_model=PredictionResponse)
async def get_prediction_suggestion(
    symbol: str,
    timeframe: str = "1h",
    strategy_mode: PredictionStrategyMode = PredictionStrategyMode.SWING,
) -> PredictionResponse:
    """Convenience GET endpoint for scanner and workspace consumers."""
    request = PredictionRequest(
        symbol=symbol,
        asset_class=_asset_class_for_symbol(symbol),
        timeframe=timeframe,
        strategy_mode=strategy_mode,
    )
    try:
        return build_prediction_response(request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
