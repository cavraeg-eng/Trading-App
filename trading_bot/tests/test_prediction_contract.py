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
        "expires_at": datetime.now(tz=timezone.utc),
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


def test_hold_rejects_ambiguous_actionable_levels():
    payload = _base_response(PredictionRecommendation.HOLD)
    payload.update({
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
    assert "expires_at" in payload["requiredForBuySell"]


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
    assert response.entry is None
    assert response.stop_loss is None
    assert response.risk_reward is None
    assert response.chart.entry_zone is None


def test_buy_prediction_generates_valid_actionable_suggestion(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1000,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish confirmation",
            "entryRange": {"min": 1.0988, "max": 1.1000},
            "stopLoss": 1.0960,
            "takeProfit1": 1.1040,
            "takeProfit2": 1.1080,
            "takeProfit3": 1.1120,
            "riskReward": 2.0,
            "atr": 0.002,
            "anchorModel": {"support": 1.097, "resistance": 1.11},
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

    assert response.recommendation == PredictionRecommendation.BUY
    assert response.entry is not None
    assert response.stop_loss is not None
    assert response.entry.max <= response.chart.current_price
    assert response.stop_loss < response.entry.min
    assert response.take_profit_targets[0].price > response.chart.current_price
    assert response.risk_reward is not None and response.risk_reward >= 1.35
    assert response.expires_at is not None
    assert response.chart.expires_at == response.expires_at
    assert response.chart.annotations


def test_sell_prediction_generates_valid_actionable_suggestion(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1000,
            "signal": "sell",
            "confidence": 74,
            "reason": "bearish confirmation",
            "entryRange": {"min": 1.1000, "max": 1.1012},
            "stopLoss": 1.1040,
            "takeProfit1": 1.0960,
            "takeProfit2": 1.0920,
            "takeProfit3": 1.0880,
            "riskReward": 2.0,
            "atr": 0.002,
            "anchorModel": {"support": 1.09, "resistance": 1.103},
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

    assert response.recommendation == PredictionRecommendation.SELL
    assert response.entry is not None
    assert response.stop_loss is not None
    assert response.entry.min >= response.chart.current_price
    assert response.stop_loss > response.entry.max
    assert response.take_profit_targets[0].price < response.chart.current_price
    assert response.risk_reward is not None and response.risk_reward >= 1.35


def test_invalid_directional_levels_downgrade_to_no_trade(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1000,
            "signal": "buy",
            "confidence": 82,
            "reason": "bullish but invalid levels",
            "entryRange": {"min": 1.1010, "max": 1.1020},
            "stopLoss": 1.1030,
            "takeProfit1": 1.0990,
            "takeProfit2": 1.0980,
            "takeProfit3": 1.0970,
            "riskReward": 0.5,
            "atr": 0.002,
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

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.INSUFFICIENT_DATA
    assert response.entry is None
    assert response.take_profit_targets == []
    assert response.warnings


def test_compressed_reward_risk_downgrades_to_no_trade(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1000,
            "signal": "buy",
            "confidence": 82,
            "reason": "bullish but target runway is compressed",
            "entryRange": {"min": 1.0988, "max": 1.1000},
            "stopLoss": 1.0960,
            "takeProfit1": 1.1010,
            "takeProfit2": 1.1020,
            "takeProfit3": 1.1030,
            "riskReward": 0.76,
            "atr": 0.002,
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

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.REWARD_RISK_COMPRESSED
    assert response.entry is None
    assert response.stop_loss is None
