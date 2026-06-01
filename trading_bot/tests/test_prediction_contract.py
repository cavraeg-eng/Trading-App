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
    PredictionNoTradeDetail,
    PredictionNoTradeReason,
    PredictionPositionContext,
    PredictionPriceZone,
    PredictionRationale,
    PredictionRationaleCategory,
    PredictionRationaleFactor,
    PredictionRationaleItem,
    PredictionRationaleStance,
    PredictionRationaleStrength,
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
from trading_bot.services.prediction_quality import PredictionQualityConfig, evaluate_prediction_quality


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
    rationale = PredictionRationale(
        summary="Contract validation test.",
        confidence_label=PredictionConfidenceBand.HIGH.value,
        primary_reasons=[
            PredictionRationaleFactor(
                category=PredictionRationaleCategory.TREND,
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
                    category=PredictionRationaleCategory.CONFIDENCE,
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
    payload["no_trade_reasons"] = [
        PredictionNoTradeDetail(
            code=PredictionNoTradeReason.LOW_CONFIDENCE,
            message="Confidence is below the actionable threshold.",
        )
    ]
    response = PredictionResponse(**payload)

    assert response.no_trade_reason == PredictionNoTradeReason.LOW_CONFIDENCE
    assert response.entry is None


def test_no_trade_rejects_ambiguous_actionable_levels():
    payload = _base_response(PredictionRecommendation.NO_TRADE)
    payload.update({
        "confidence": 31,
        "confidence_band": PredictionConfidenceBand.LOW,
        "no_trade_reason": PredictionNoTradeReason.CONFLICTING_SIGNALS,
        "no_trade_reasons": [
            PredictionNoTradeDetail(
                code=PredictionNoTradeReason.CONFLICTING_SIGNALS,
                message="Signals conflict.",
            )
        ],
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
        "expires_at": datetime.now(tz=timezone.utc),
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
    assert "account_context_missing" in payload["warningCodes"]
    assert "unsupported_asset" in payload["warningCodes"]
    assert "account_risk_warnings" in payload["optionalAccountRiskFields"]
    assert "low_confidence" in payload["noTradeReasons"]
    assert "scanner" in payload["compatibility"]
    assert "freshness" in payload["requiredForEveryResponse"]
    assert "entry" in payload["requiredForBuySell"]
    assert "expires_at" in payload["requiredForBuySell"]
    assert "spread" in payload["rationaleCategories"]
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
    assert response.entry is None
    assert response.chart.entry_zone is None
    assert response.stop_loss is None
    assert response.risk_reward is None
    assert response.freshness.cache_status == "miss"
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.summary.startswith("Hold:")
    assert response.rationale.primary_reasons
    assert response.rationale.next_conditions


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
    assert response.no_trade_reason == PredictionNoTradeReason.REWARD_RISK_COMPRESSED
    assert response.take_profit_targets == []
    assert response.chart.take_profit_targets == []
    assert response.no_trade_reasons


def test_buy_prediction_generates_valid_actionable_suggestion(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="buy",
            confidence=76,
            reason="bullish confirmation",
            entryRange={"min": 1.0988, "max": 1.1000},
            stopLoss=1.0960,
            takeProfit1=1.1040,
            takeProfit2=1.1080,
            takeProfit3=1.1120,
            riskReward=2.0,
            atr=0.002,
            anchorModel={"support": 1.097, "resistance": 1.11},
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
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
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.primary_reasons
    assert response.rationale.next_conditions
    assert response.rationale.blockers == []
    assert PredictionRationaleCategory.SPREAD in {
        factor.category for factor in response.rationale.primary_reasons
    }


def test_sell_prediction_generates_valid_actionable_suggestion(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="sell",
            confidence=74,
            reason="bearish confirmation",
            entryRange={"min": 1.1000, "max": 1.1012},
            stopLoss=1.1040,
            takeProfit1=1.0960,
            takeProfit2=1.0920,
            takeProfit3=1.0880,
            riskReward=2.0,
            atr=0.002,
            indicators=[
                {"name": "RSI", "value": 62, "signal": "bearish"},
                {"name": "MACD", "value": -0.001, "signal": "bearish"},
                {"name": "EMA", "value": 1.102, "signal": "bearish"},
            ],
            higherTimeframeBias={"direction": "bearish", "strength": 0.8},
            anchorModel={"support": 1.09, "resistance": 1.103},
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
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
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="buy",
            confidence=82,
            reason="bullish but invalid levels",
            entryRange={"min": 1.1010, "max": 1.1020},
            stopLoss=1.1030,
            takeProfit1=1.0990,
            takeProfit2=1.0980,
            takeProfit3=1.0970,
            riskReward=2.0,
            atr=0.002,
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
    )

    response = predictions.build_prediction_response(_request())

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.INSUFFICIENT_DATA
    assert response.entry is None
    assert response.take_profit_targets == []
    assert len(response.warnings) >= 2


def test_compressed_targets_reward_risk_downgrades_to_no_trade(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="buy",
            confidence=82,
            reason="bullish but target runway is compressed",
            entryRange={"min": 1.0988, "max": 1.1000},
            stopLoss=1.0960,
            takeProfit1=1.1010,
            takeProfit2=1.1015,
            takeProfit3=1.1020,
            riskReward=2.0,
            atr=0.002,
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
    )

    response = predictions.build_prediction_response(_request())

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.REWARD_RISK_COMPRESSED
    assert response.entry is None
    assert response.stop_loss is None
    assert response.no_trade_reasons
    assert isinstance(response.rationale, PredictionRationale)
    assert response.rationale.blockers
    assert response.rationale.next_conditions


def test_conservative_primary_target_allows_later_reward_risk(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="buy",
            confidence=82,
            reason="bullish continuation with scaled targets",
            entryRange={"min": 1.0988, "max": 1.1000},
            stopLoss=1.0960,
            takeProfit1=1.1010,
            takeProfit2=1.1080,
            takeProfit3=1.1120,
            riskReward=2.0,
            atr=0.002,
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
    )

    response = predictions.build_prediction_response(_request())

    assert response.recommendation == PredictionRecommendation.BUY
    assert response.risk_reward is not None and response.risk_reward >= 1.35
    assert response.take_profit_targets[0].reward_risk is not None
    assert response.take_profit_targets[0].reward_risk < 1.35
    assert response.take_profit_targets[1].reward_risk is not None
    assert response.take_profit_targets[1].reward_risk >= 1.35


def _analysis(**overrides):
    base = {
        "currentPrice": 1.1,
        "signal": "buy",
        "confidence": 74,
        "reason": "MACD bullish crossover, higher timeframes aligned bullish",
        "entryRange": {"min": 1.099, "max": 1.101},
        "stopLoss": 1.094,
        "takeProfit1": 1.108,
        "takeProfit2": 1.112,
        "riskReward": 2.0,
        "atr": 0.004,
        "indicators": [
            {"name": "RSI", "value": 42, "signal": "bullish"},
            {"name": "MACD", "value": 0.001, "signal": "bullish"},
            {"name": "EMA", "value": 1.098, "signal": "bullish"},
        ],
        "higherTimeframeBias": {"direction": "bullish", "strength": 0.8},
        "anchorModel": {"support": 1.096, "resistance": 1.118},
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
        "marketStatus": "live",
    }
    base.update(overrides)
    return base


def test_prediction_quality_allows_good_signal():
    result = evaluate_prediction_quality(
        _analysis(),
        _metadata(),
        config=PredictionQualityConfig(),
    )

    assert result.gates == []
    assert result.confidence >= 74


def test_prediction_quality_blocks_weak_signal():
    result = evaluate_prediction_quality(
        _analysis(confidence=41),
        _metadata(),
        config=PredictionQualityConfig(min_actionable_confidence=62),
    )

    assert any(gate.code == PredictionNoTradeReason.LOW_CONFIDENCE for gate in result.gates)


def test_prediction_quality_blocks_stale_data():
    result = evaluate_prediction_quality(
        _analysis(),
        _metadata(freshnessSeconds=1200, marketStatus="stale", qualityFlags=["stale_data"]),
        config=PredictionQualityConfig(stale_data_seconds=900),
    )

    assert result.gates[0].code == PredictionNoTradeReason.STALE_DATA


def test_prediction_quality_blocks_delayed_scalp_data():
    result = evaluate_prediction_quality(
        _analysis(),
        _metadata(
            freshnessSeconds=650,
            marketStatus="delayed",
            tradeStyle="scalp",
            timeframe="1m",
        ),
        config=PredictionQualityConfig(stale_data_seconds=900),
    )

    assert result.gates[0].code == PredictionNoTradeReason.STALE_DATA
    assert "delayed" in result.gates[0].message


def test_prediction_quality_uses_timeframe_aware_freshness_for_live_swing_data():
    result = evaluate_prediction_quality(
        _analysis(),
        _metadata(
            freshnessSeconds=3700,
            marketStatus="live",
            tradeStyle="swing",
            timeframe="1h",
        ),
        config=PredictionQualityConfig(stale_data_seconds=900),
    )

    assert not any(gate.code == PredictionNoTradeReason.STALE_DATA for gate in result.gates)


def test_prediction_quality_blocks_high_spread():
    result = evaluate_prediction_quality(
        _analysis(spreadBps=18),
        _metadata(),
        config=PredictionQualityConfig(max_spread_bps=8),
    )

    assert any(gate.code == PredictionNoTradeReason.EXCESSIVE_SPREAD for gate in result.gates)


def test_prediction_response_no_trade_includes_reason_details(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(confidence=41),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata()),
    )

    response = predictions.build_prediction_response(_request())

    assert response.recommendation == PredictionRecommendation.NO_TRADE
    assert response.no_trade_reason == PredictionNoTradeReason.LOW_CONFIDENCE
    assert response.no_trade_reasons
    assert response.entry is None


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
    assert response.no_trade_reasons
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


def test_structured_rationale_uses_contract_categories_and_clean_summary(monkeypatch):
    monkeypatch.setattr(
        predictions,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style="swing": _analysis(
            currentPrice=1.1000,
            signal="buy",
            confidence=80,
            reason="Trend alignment is clean.",
            entryRange={"min": 1.0988, "max": 1.1000},
            stopLoss=1.0960,
            takeProfit1=1.1040,
            takeProfit2=1.1080,
            takeProfit3=1.1120,
            riskReward=2.0,
            atr=0.002,
            indicators=[
                {"name": f"Custom{i}", "value": str(i), "signal": "bullish"}
                for i in range(7)
            ],
            higherTimeframeBias={"direction": "bullish", "strength": 0.8},
            anchorModel={"support": 1.097, "resistance": 1.11},
        ),
    )
    monkeypatch.setattr(
        predictions,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (None, _metadata(marketStatus="open")),
    )

    response = predictions.build_prediction_response(_request())

    assert response.rationale.summary == "Long setup: Trend alignment is clean."
    assert PredictionRationaleCategory.SPREAD in {
        factor.category for factor in response.rationale.primary_reasons
    }
    assert all(
        isinstance(factor.category, PredictionRationaleCategory)
        for factor in response.rationale.primary_reasons
    )


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
            _metadata(lastBarTimestamp=1_700_000_000),
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
        return None, _metadata(lastBarTimestamp=1_700_000_000 + calls["metadata"])

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
            rationale=PredictionRationale(
                summary="Warmup",
                confidence_label=PredictionConfidenceBand.MEDIUM.value,
            ),
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
