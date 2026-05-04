"""AI prediction and suggestion contract endpoints."""

from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, Field as PydanticField

from trading_bot.api.models import (
    PredictionAccountContextStatus,
    PredictionAssetClass,
    PredictionConfidenceBand,
    PredictionNoTradeReason,
    PredictionRationaleCategory,
    PredictionRationaleStance,
    PredictionRationaleStrength,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionStrategyMode,
    PredictionWarningCode,
)
from trading_bot.config import get_logger
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.services.market_analysis import analyze_symbol
from trading_bot.services.prediction_pipeline import (
    PREDICTION_CACHE_MAX_ENTRIES,
    PREDICTION_CACHE_TTL_SECONDS,
    PREDICTION_FEATURE_VERSION,
    PREDICTION_WARMUP_MAX_COMBINATIONS,
    PREDICTION_WARMUP_MAX_SYMBOLS,
    PREDICTION_WARMUP_MAX_TIMEFRAMES,
    _UNSET,
    asset_class_for_symbol,
    build_prediction_response as build_pipeline_prediction_response,
    clear_prediction_cache,
    get_prediction_cache_info,
    request_with_account_context,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/predictions", tags=["predictions"])


class PredictionWarmupRequest(BaseModel):
    symbols: list[str] = PydanticField(min_length=1, max_length=PREDICTION_WARMUP_MAX_SYMBOLS)
    timeframes: list[str] = PydanticField(
        default_factory=lambda: ["1h"],
        min_length=1,
        max_length=PREDICTION_WARMUP_MAX_TIMEFRAMES,
    )
    strategy_mode: PredictionStrategyMode = PredictionStrategyMode.SWING


def _asset_class_for_symbol(symbol: str) -> PredictionAssetClass:
    """Compatibility adapter for older route-level callers."""
    return asset_class_for_symbol(symbol)


async def _request_with_account_context(
    request: PredictionRequest,
    broker_id: Optional[str] = None,
) -> PredictionRequest:
    """Compatibility adapter for older route-level callers."""
    return await request_with_account_context(request, broker_id=broker_id)


def build_prediction_response(
    request: PredictionRequest,
    analysis_override: Any = _UNSET,
    metadata_override: Optional[dict[str, Any]] = None,
) -> PredictionResponse:
    """Adapter-only wrapper around the prediction pipeline seam.

    Tests and older integrations patch route-level providers, so this wrapper
    injects those aliases while keeping construction logic in the service module.
    """
    return build_pipeline_prediction_response(
        request,
        analysis_override=analysis_override,
        metadata_override=metadata_override,
        analysis_provider=analyze_symbol,
        metadata_provider=get_ohlcv_with_metadata,
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
        "requiredForBuySell": [
            "entry",
            "stop_loss",
            "take_profit_targets",
            "risk_reward",
            "invalidation_level",
            "expires_at",
        ],
        "requiredForNoTrade": ["no_trade_reason", "no_trade_reasons"],
        "freshnessMetadata": [
            "cache_status",
            "cache_key",
            "cache_age_seconds",
            "feature_version",
            "freshness_seconds",
            "quality_flags",
        ],
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


@router.get("/cache")
async def get_prediction_cache() -> dict[str, Any]:
    return get_prediction_cache_info()


@router.post("/warmup")
async def warm_prediction_cache(request: PredictionWarmupRequest) -> dict[str, Any]:
    total_requests = len(request.symbols) * len(request.timeframes)
    if total_requests > PREDICTION_WARMUP_MAX_COMBINATIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Warmup is limited to {PREDICTION_WARMUP_MAX_COMBINATIONS} symbol/timeframe combinations.",
        )

    warmed: list[dict[str, str]] = []
    failed: list[dict[str, str]] = []
    for symbol in request.symbols:
        for timeframe in request.timeframes:
            prediction_request = PredictionRequest(
                symbol=symbol,
                asset_class=asset_class_for_symbol(symbol),
                timeframe=timeframe,
                strategy_mode=request.strategy_mode,
            )
            try:
                response = await run_in_threadpool(build_prediction_response, prediction_request)
                warmed.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "cacheStatus": response.freshness.cache_status or "unknown",
                })
            except Exception as exc:
                failed.append({
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "error": str(exc),
                })
                logger.warning(f"Prediction warmup failed for {symbol}/{timeframe}: {exc}")
    return {
        "warmed": warmed,
        "failed": failed,
        "cache": get_prediction_cache_info(),
    }


@router.post("/suggestion", response_model=PredictionResponse)
async def create_prediction_suggestion(request: PredictionRequest) -> PredictionResponse:
    """Create a contract-compliant AI prediction/suggestion response."""
    try:
        enriched_request = await request_with_account_context(request)
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
        asset_class=asset_class_for_symbol(symbol),
        timeframe=timeframe,
        strategy_mode=strategy_mode,
    )
    try:
        enriched_request = await request_with_account_context(request, broker_id=broker_id)
        return build_prediction_response(enriched_request)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
