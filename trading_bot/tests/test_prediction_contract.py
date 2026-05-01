from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from trading_bot.api.models import (
    PredictionAccountContextStatus,
    PredictionAssetClass,
    PredictionBrokerContext,
    PredictionChartOverlay,
    PredictionConfidenceBand,
    PredictionNoTradeReason,
    PredictionPositionContext,
    PredictionPriceZone,
    PredictionRationaleItem,
    PredictionRecommendation,
    PredictionRequest,
    PredictionResponse,
    PredictionRiskConstraints,
    PredictionStrategyMode,
    PredictionSuggestionCard,
    PredictionTarget,
    PredictionWarningCode,
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
    assert "account_context_missing" in payload["warningCodes"]
    assert "unsupported_asset" in payload["warningCodes"]
    assert "account_risk_warnings" in payload["optionalAccountRiskFields"]
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
    assert response.entry is None
    assert response.chart.entry_zone is None
    assert response.stop_loss is None
    assert response.risk_reward is None


def test_contract_endpoint_documents_strategy_mode_mapping():
    client = TestClient(app)

    response = client.get("/api/predictions/contract")

    assert response.status_code == 200
    payload = response.json()
    assert payload["strategyModeTradeStyleMap"] == {
        "scalp": "scalp",
        "swing": "swing",
        "intraday": "swing",
        "position": "swing",
        "automation": "swing",
    }


def test_incomplete_buy_levels_downgrade_to_no_trade_without_targets(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 71,
            "reason": "bullish but incomplete levels",
            "entryRange": {"min": 1.1, "max": 1.101},
            "takeProfit1": 1.11,
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
    assert response.take_profit_targets == []
    assert response.chart.take_profit_targets == []


def test_account_context_adds_position_size(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish continuation",
            "entryRange": {"min": 1.1, "max": 1.1},
            "stopLoss": 1.095,
            "takeProfit1": 1.11,
            "riskReward": 2.0,
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

    request = PredictionRequest(
        symbol="EUR/USD",
        asset_class=PredictionAssetClass.FOREX,
        broker_context=PredictionBrokerContext(
            broker_id="oanda",
            base_currency="USD",
            equity=10000,
            available_margin=9000,
            risk_constraints=PredictionRiskConstraints(risk_percent=1.0),
        ),
    )

    response = predictions.build_prediction_response(request)

    assert response.account_context_status == PredictionAccountContextStatus.AVAILABLE
    assert response.position_size is not None
    assert response.position_size.risk_amount == 100
    assert response.trade_allowed is True


def test_missing_account_context_degrades_with_warning(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish continuation",
            "entryRange": {"min": 1.1, "max": 1.1},
            "stopLoss": 1.095,
            "takeProfit1": 1.11,
            "riskReward": 2.0,
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

    assert response.account_context_status == PredictionAccountContextStatus.MISSING
    assert response.position_size is None
    assert any(warning.code == PredictionWarningCode.ACCOUNT_CONTEXT_MISSING for warning in response.account_risk_warnings)
    assert any(warning.code == PredictionWarningCode.POSITION_SIZING_UNAVAILABLE for warning in response.account_risk_warnings)


def test_account_risk_blocks_conflicting_position(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish continuation",
            "entryRange": {"min": 1.1, "max": 1.1},
            "stopLoss": 1.095,
            "takeProfit1": 1.11,
            "riskReward": 2.0,
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

    request = PredictionRequest(
        symbol="EUR/USD",
        asset_class=PredictionAssetClass.FOREX,
        broker_context=PredictionBrokerContext(
            broker_id="oanda",
            base_currency="USD",
            equity=10000,
            available_margin=9000,
            positions=[
                PredictionPositionContext(
                    symbol="EUR/USD",
                    side="short",
                    quantity=1000,
                    current_price=1.1,
                )
            ],
            risk_constraints=PredictionRiskConstraints(risk_percent=1.0),
        ),
    )

    response = predictions.build_prediction_response(request)

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.RISK_LIMITS
    assert response.trade_allowed is False
    assert any(warning.code == PredictionWarningCode.OPEN_POSITION_CONFLICT for warning in response.account_risk_warnings)


def test_naive_account_context_timestamp_is_handled(monkeypatch):
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

    request = PredictionRequest(
        symbol="EUR/USD",
        asset_class=PredictionAssetClass.FOREX,
        broker_context=PredictionBrokerContext(
            equity=10000,
            available_margin=9000,
            risk_constraints=PredictionRiskConstraints(risk_percent=1.0),
            context_timestamp=datetime(2026, 5, 1, 12, 0, 0),
            max_context_age_seconds=1,
        ),
    )

    response = predictions.build_prediction_response(request)

    assert response.account_context_status == PredictionAccountContextStatus.STALE


def test_account_risk_warnings_are_not_duplicated_in_general_warnings(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish continuation",
            "entryRange": {"min": 1.1, "max": 1.1},
            "stopLoss": 1.095,
            "takeProfit1": 1.11,
            "riskReward": 2.0,
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

    assert response.account_risk_warnings
    assert all(warning not in response.warnings for warning in response.account_risk_warnings)


def test_primary_target_includes_reward_risk(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": {
            "currentPrice": 1.1,
            "signal": "buy",
            "confidence": 76,
            "reason": "bullish continuation",
            "entryRange": {"min": 1.1, "max": 1.1},
            "stopLoss": 1.095,
            "takeProfit1": 1.11,
            "riskReward": 2.0,
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

    assert response.take_profit_targets[0].reward_risk == 2.0
