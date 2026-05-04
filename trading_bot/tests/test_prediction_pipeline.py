from trading_bot.api.models import (
    PredictionAssetClass,
    PredictionBrokerContext,
    PredictionNoTradeReason,
    PredictionPositionContext,
    PredictionRecommendation,
    PredictionRequest,
    PredictionRiskConstraints,
    PredictionStrategyMode,
    PredictionWarningCode,
)
from trading_bot.services import prediction_pipeline


def setup_function():
    prediction_pipeline.clear_prediction_cache()


def _request(**overrides) -> PredictionRequest:
    base = {
        "symbol": "EUR/USD",
        "asset_class": PredictionAssetClass.FOREX,
        "timeframe": "1h",
        "strategy_mode": PredictionStrategyMode.SWING,
    }
    base.update(overrides)
    return PredictionRequest(**base)


def _analysis(**overrides):
    base = {
        "currentPrice": 1.1,
        "signal": "buy",
        "confidence": 76,
        "reason": "bullish continuation",
        "entryRange": {"min": 1.0988, "max": 1.1},
        "stopLoss": 1.096,
        "takeProfit1": 1.104,
        "takeProfit2": 1.108,
        "takeProfit3": 1.112,
        "riskReward": 2.0,
        "atr": 0.002,
        "indicators": [
            {"name": "RSI", "value": 42, "signal": "bullish"},
            {"name": "MACD", "value": 0.001, "signal": "bullish"},
        ],
        "higherTimeframeBias": {"direction": "bullish", "strength": 0.8},
        "anchorModel": {"support": 1.097, "resistance": 1.11},
    }
    base.update(overrides)
    return base


def _metadata(**overrides):
    base = {
        "sourceName": "test",
        "sourceType": "fixture",
        "priceSource": "fixture",
        "isFallback": False,
        "freshnessSeconds": 1,
        "qualityFlags": [],
        "marketStatus": "open",
        "lastBarTimestamp": 1_700_000_000,
    }
    base.update(overrides)
    return base


def test_pipeline_cache_returns_initial_miss_then_hit():
    calls = {"analysis": 0}

    def analysis_provider(symbol, timeframe, trade_style="swing"):
        calls["analysis"] += 1
        return _analysis(signal="hold", confidence=52, reason="mixed indicators")

    def metadata_provider(symbol, timeframe, trade_style="swing"):
        return None, _metadata()

    first = prediction_pipeline.build_prediction_response(
        _request(),
        analysis_provider=analysis_provider,
        metadata_provider=metadata_provider,
    )
    second = prediction_pipeline.build_prediction_response(
        _request(),
        analysis_provider=analysis_provider,
        metadata_provider=metadata_provider,
    )

    assert calls["analysis"] == 1
    assert first.freshness.cache_status == "miss"
    assert second.freshness.cache_status == "hit"
    assert second.freshness.cache_key == first.freshness.cache_key


def test_pipeline_unsupported_asset_returns_no_trade_without_provider_calls():
    def fail_analysis(symbol, timeframe, trade_style="swing"):
        raise AssertionError("analysis provider should not be called")

    def fail_metadata(symbol, timeframe, trade_style="swing"):
        raise AssertionError("metadata provider should not be called")

    response = prediction_pipeline.build_prediction_response(
        _request(symbol="NOTSUPPORTED", asset_class=PredictionAssetClass.UNKNOWN),
        analysis_provider=fail_analysis,
        metadata_provider=fail_metadata,
    )

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.UNSUPPORTED_ASSET
    assert response.trade_allowed is False
    assert any(warning.code == PredictionWarningCode.UNSUPPORTED_ASSET for warning in response.warnings)


def test_pipeline_quality_gate_converts_weak_actionable_signal_to_no_trade():
    response = prediction_pipeline.build_prediction_response(
        _request(),
        analysis_provider=lambda symbol, timeframe, trade_style="swing": _analysis(confidence=41),
        metadata_provider=lambda symbol, timeframe, trade_style="swing": (None, _metadata()),
    )

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.LOW_CONFIDENCE
    assert response.entry is None
    assert any(detail.code == PredictionNoTradeReason.LOW_CONFIDENCE for detail in response.no_trade_reasons)


def test_pipeline_account_risk_block_withholds_conflicting_position_setup():
    request = _request(
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
        )
    )

    response = prediction_pipeline.build_prediction_response(
        request,
        analysis_provider=lambda symbol, timeframe, trade_style="swing": _analysis(),
        metadata_provider=lambda symbol, timeframe, trade_style="swing": (None, _metadata()),
    )

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.RISK_LIMITS
    assert response.trade_allowed is False
    assert any(
        warning.code == PredictionWarningCode.OPEN_POSITION_CONFLICT
        for warning in response.account_risk_warnings
    )
