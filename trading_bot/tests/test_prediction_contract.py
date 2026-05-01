from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from trading_bot.api.models import (
    PredictionAssetClass,
    PredictionChartOverlay,
    PredictionConfidenceBand,
    PredictionNoTradeReason,
    PredictionPriceZone,
    PredictionRationaleItem,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionStrategyMode,
    PredictionSuggestionCard,
    PredictionTarget,
    confidence_band_for_score,
)
from trading_bot.api.routes import predictions
from trading_bot.api.server import app


def setup_function():
    predictions.clear_prediction_cache()


def _request() -> PredictionRequest:
    return PredictionRequest(
        symbol="EUR/USD",
        asset_class=PredictionAssetClass.FOREX,
        timeframe="1h",
        strategy_mode=PredictionStrategyMode.SWING,
    )


def _base_response(recommendation: PredictionRecommendation) -> dict:
    return {
        "prediction_id": f"test-{recommendation.value}",
        "request": _request(),
        "symbol": "EUR/USD",
        "asset_class": PredictionAssetClass.FOREX,
        "timeframe": "1h",
        "strategy_mode": PredictionStrategyMode.SWING,
        "recommendation": recommendation,
        "confidence": 76,
        "confidence_band": PredictionConfidenceBand.HIGH,
        "rationale": [PredictionRationaleItem(category="summary", summary="Contract validation test.")],
        "chart": PredictionChartOverlay(current_price=1.1),
        "suggestion_card": PredictionSuggestionCard(
            title="EUR/USD",
            badge=recommendation.value,
            summary="Contract validation test.",
        ),
        "generated_at": datetime.now(tz=timezone.utc),
    }


@pytest.mark.parametrize("recommendation", [PredictionRecommendation.BUY, PredictionRecommendation.SELL])
def test_trade_recommendations_require_actionable_levels(recommendation):
    payload = _base_response(recommendation)
    payload.update({
        "entry": PredictionPriceZone(min=1.1, max=1.101, label="Entry zone"),
        "stop_loss": 1.095,
        "take_profit_targets": [PredictionTarget(label="TP1", price=1.11, reward_risk=2.0)],
        "invalidation_level": 1.095,
        "risk_reward": 2.0,
    })

    response = PredictionResponse(**payload)

    assert response.recommendation == recommendation
    assert response.entry is not None
    assert response.take_profit_targets[0].label == "TP1"


def test_no_trade_requires_machine_readable_reason_and_no_levels():
    payload = _base_response(PredictionRecommendation.NO_TRADE)
    payload.update({"confidence": 31, "confidence_band": PredictionConfidenceBand.LOW})

    with pytest.raises(ValidationError):
        PredictionResponse(**payload)

    payload["no_trade_reason"] = PredictionNoTradeReason.LOW_CONFIDENCE
    response = PredictionResponse(**payload)

    assert response.no_trade_reason == PredictionNoTradeReason.LOW_CONFIDENCE
    assert response.entry is None


def test_no_trade_rejects_ambiguous_actionable_levels():
    payload = _base_response(PredictionRecommendation.NO_TRADE)
    payload.update({
        "confidence": 31,
        "confidence_band": PredictionConfidenceBand.LOW,
        "no_trade_reason": PredictionNoTradeReason.CONFLICTING_SIGNALS,
        "entry": PredictionPriceZone(min=1.1, max=1.101),
    })

    with pytest.raises(ValidationError):
        PredictionResponse(**payload)


def test_confidence_band_mapping_is_stable():
    assert confidence_band_for_score(20) == PredictionConfidenceBand.LOW
    assert confidence_band_for_score(55) == PredictionConfidenceBand.MEDIUM
    assert confidence_band_for_score(70) == PredictionConfidenceBand.HIGH
    assert confidence_band_for_score(91) == PredictionConfidenceBand.VERY_HIGH


def test_contract_endpoint_documents_consumers():
    client = TestClient(app)

    response = client.get("/api/predictions/contract")

    assert response.status_code == 200
    payload = response.json()
    assert "no_trade" in payload["recommendations"]
    assert "low_confidence" in payload["noTradeReasons"]
    assert "scanner" in payload["compatibility"]
    assert "freshness" in payload["requiredForEveryResponse"]
    assert "entry" in payload["requiredForBuySell"]
    assert "cache_status" in payload["freshnessMetadata"]


def test_hold_prediction_tolerates_missing_trade_levels(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "hold",
            "confidence": 52,
            "reason": "indicators are mixed",
        },
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (
            None,
            {
                "sourceName": "test",
                "sourceType": "fixture",
                "priceSource": "fixture",
                "isFallback": False,
                "freshnessSeconds": 1,
                "qualityFlags": [],
                "marketStatus": "open",
            },
        ),
    )

    response = predictions.build_prediction_response(_request())

    assert response.recommendation == PredictionRecommendation.HOLD
    assert response.entry is not None
    assert response.stop_loss is None
    assert response.risk_reward is None
    assert response.freshness.cache_status == "miss"


def test_prediction_cache_hits_for_same_latest_candle(monkeypatch):
    calls = {"analysis": 0}

    def fake_analysis(symbol, timeframe, trade_style="swing"):
        calls["analysis"] += 1
        return {
            "currentPrice": 1.1,
            "signal": "hold",
            "confidence": 52,
            "reason": "indicators are mixed",
        }

    monkeypatch.setattr(predictions, "analyze_symbol", fake_analysis)
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (
            None,
            {
                "sourceName": "test",
                "sourceType": "fixture",
                "priceSource": "fixture",
                "isFallback": False,
                "freshnessSeconds": 1,
                "lastBarTimestamp": 1_700_000_000,
                "qualityFlags": [],
                "marketStatus": "open",
            },
        ),
    )

    first = predictions.build_prediction_response(_request())
    second = predictions.build_prediction_response(_request())

    assert calls["analysis"] == 1
    assert first.freshness.cache_status == "miss"
    assert second.freshness.cache_status == "hit"
    assert second.freshness.cache_key == first.freshness.cache_key
    assert second.freshness.cache_age_seconds is not None


def test_prediction_cache_misses_when_latest_candle_changes(monkeypatch):
    calls = {"analysis": 0, "metadata": 0}

    def fake_analysis(symbol, timeframe, trade_style="swing"):
        calls["analysis"] += 1
        return {
            "currentPrice": 1.1,
            "signal": "hold",
            "confidence": 52,
            "reason": "indicators are mixed",
        }

    def fake_metadata(symbol, timeframe, trade_style="swing"):
        calls["metadata"] += 1
        return None, {
            "sourceName": "test",
            "sourceType": "fixture",
            "priceSource": "fixture",
            "isFallback": False,
            "freshnessSeconds": 1,
            "lastBarTimestamp": 1_700_000_000 + calls["metadata"],
            "qualityFlags": [],
            "marketStatus": "open",
        }

    monkeypatch.setattr(predictions, "analyze_symbol", fake_analysis)
    monkeypatch.setattr(predictions, "get_ohlcv_with_metadata", fake_metadata)

    first = predictions.build_prediction_response(_request())
    second = predictions.build_prediction_response(_request())

    assert calls["analysis"] == 2
    assert first.freshness.cache_status == "miss"
    assert second.freshness.cache_status == "miss"
    assert second.freshness.cache_key != first.freshness.cache_key


def test_prediction_warmup_is_best_effort(monkeypatch):
    def fake_response(request):
        if request.symbol == "BAD/USD":
            raise RuntimeError("provider down")
        return PredictionResponse(
            prediction_id="warm",
            request=request,
            symbol=request.symbol,
            asset_class=request.asset_class,
            timeframe=request.timeframe,
            strategy_mode=request.strategy_mode,
            recommendation=PredictionRecommendation.HOLD,
            confidence=52,
            confidence_band=PredictionConfidenceBand.MEDIUM,
            rationale=[PredictionRationaleItem(category="summary", summary="Warmup")],
            chart=PredictionChartOverlay(),
            suggestion_card=PredictionSuggestionCard(title=request.symbol, badge="Hold", summary="Warmup"),
        )

    monkeypatch.setattr(predictions, "build_prediction_response", fake_response)

    import asyncio
    result = asyncio.run(predictions.warm_prediction_cache(predictions.PredictionWarmupRequest(
        symbols=["EUR/USD", "BAD/USD"],
        timeframes=["1h"],
    )))

    assert len(result["warmed"]) == 1
    assert len(result["failed"]) == 1
    assert result["failed"][0]["symbol"] == "BAD/USD"


def test_prediction_warmup_rejects_too_many_combinations():
    client = TestClient(app)

    response = client.post(
        "/api/predictions/warmup",
        json={
            "symbols": [f"EUR/{index}" for index in range(11)],
            "timeframes": ["1m", "5m", "15m", "1h", "4h"],
        },
    )

    assert response.status_code == 400
    assert "limited" in response.json()["detail"]


def test_prediction_warmup_rejects_too_many_symbols():
    client = TestClient(app)

    response = client.post(
        "/api/predictions/warmup",
        json={
            "symbols": [f"EUR/{index}" for index in range(26)],
            "timeframes": ["1h"],
        },
    )

    assert response.status_code == 422
