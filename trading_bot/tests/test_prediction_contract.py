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
    PredictionRationale,
    PredictionRationaleFactor,
    PredictionRationaleItem,
    PredictionRationaleStance,
    PredictionRationaleStrength,
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
    rationale = PredictionRationale(
        summary="Contract validation test.",
        confidence_label=PredictionConfidenceBand.HIGH.value,
        primary_reasons=[
            PredictionRationaleFactor(
                category="trend",
                stance=PredictionRationaleStance.SUPPORTIVE,
                strength=PredictionRationaleStrength.STRONG,
                message="Trend supports the setup.",
            )
        ],
    )
    if recommendation == PredictionRecommendation.NO_TRADE:
        rationale = PredictionRationale(
            summary="No trade: confidence is too low.",
            confidence_label=PredictionConfidenceBand.LOW.value,
            blockers=[
                PredictionRationaleFactor(
                    category="confidence",
                    stance=PredictionRationaleStance.BLOCKING,
                    strength=PredictionRationaleStrength.MEDIUM,
                    message="Confidence is too low for a trade.",
                )
            ],
            next_conditions=["Wait for stronger confirmation."],
        )

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
        "rationale": rationale,
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


def test_legacy_rationale_items_are_normalized_for_existing_callers():
    payload = _base_response(PredictionRecommendation.BUY)
    payload.update({
        "entry": PredictionPriceZone(min=1.1, max=1.101, label="Entry zone"),
        "stop_loss": 1.095,
        "take_profit_targets": [PredictionTarget(label="TP1", price=1.11, reward_risk=2.0)],
        "invalidation_level": 1.095,
        "risk_reward": 2.0,
        "rationale": [PredictionRationaleItem(category="summary", summary="Legacy rationale.")],
    })

    response = PredictionResponse(**payload)

    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.summary == "Legacy rationale."
    assert response.rationale.primary_reasons[0].source == "legacy_rationale"


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
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.summary.startswith("Hold:")
    assert response.rationale.primary_reasons
    assert response.rationale.next_conditions


@pytest.mark.parametrize(
    ("signal", "recommendation"),
    [
        ("buy", PredictionRecommendation.BUY),
        ("sell", PredictionRecommendation.SELL),
    ],
)
def test_actionable_predictions_include_structured_rationale(monkeypatch, signal, recommendation):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": signal,
            "confidence": 78,
            "reason": "trend and momentum agree",
            "entryRange": {"min": 1.1, "max": 1.101},
            "stopLoss": 1.095,
            "takeProfit1": 1.105,
            "takeProfit2": 1.11,
            "takeProfit3": 1.115,
            "riskReward": 2.0,
            "indicators": [
                {
                    "name": "EMA(20)",
                    "value": "1.09900",
                    "signal": "bullish" if signal == "buy" else "bearish",
                },
                {
                    "name": "MACD",
                    "value": "Bullish Cross" if signal == "buy" else "Bearish Cross",
                    "signal": "bullish" if signal == "buy" else "bearish",
                },
            ],
            "anchorModel": {"support": 1.09, "resistance": 1.12, "structureConflict": False},
            "higherTimeframeBias": {
                "direction": "bullish" if signal == "buy" else "bearish",
                "strength": 0.7,
            },
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

    assert response.recommendation == recommendation
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.primary_reasons
    assert response.rationale.next_conditions
    assert response.rationale.blockers == []


def test_no_trade_prediction_explains_blockers_and_next_conditions(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "hold",
            "confidence": 31,
            "reason": "mixed and conflicting indicators",
            "indicators": [
                {"name": "RSI(14)", "value": "49.1", "signal": "neutral"},
                {"name": "MACD", "value": "Neutral", "signal": "neutral"},
            ],
            "anchorModel": {"support": 1.09, "resistance": 1.12, "structureConflict": False},
            "higherTimeframeBias": {"direction": "neutral", "strength": 0.0},
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
    assert response.no_trade_reason == PredictionNoTradeReason.CONFLICTING_SIGNALS
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.blockers
    assert response.rationale.next_conditions
