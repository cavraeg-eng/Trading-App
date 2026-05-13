import asyncio
from types import SimpleNamespace

import pandas as pd

from trading_bot.api.models import IndicatorCondition, ScannerConditionGroup, ScannerConfig
from trading_bot.services import scanner_run


def _sample_ohlcv() -> pd.DataFrame:
    close = [100 + (index * 0.5) for index in range(35)]
    return pd.DataFrame(
        {
            "open": [price - 0.2 for price in close],
            "high": [price + 0.4 for price in close],
            "low": [price - 0.4 for price in close],
            "close": close,
            "volume": [1000 + index for index in range(35)],
        }
    )


def _prediction_stub():
    return SimpleNamespace(
        prediction_id="pred_test",
        freshness=SimpleNamespace(
            cache_status="miss",
            cache_key="prediction:test",
            cache_age_seconds=0.0,
            feature_version="test",
        ),
        latency=SimpleNamespace(total_latency_ms=1.5),
    )


def test_market_focus_for_crypto_and_metals_symbols():
    assert scanner_run.market_focus_for_symbol("SOL/USD") == "crypto"
    assert scanner_run.market_focus_for_symbol("XAG/USD") == "metals"
    assert scanner_run.market_focus_for_symbol("US500") == "indices"


def test_evaluate_single_pair_returns_grouped_condition_results(monkeypatch):
    monkeypatch.setattr(
        scanner_run,
        "get_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style: (
            _sample_ohlcv(),
            {"sourceName": "test", "qualityFlags": [], "marketStatus": "open"},
        ),
    )
    monkeypatch.setattr(
        scanner_run,
        "analyze_symbol",
        lambda symbol, timeframe, trade_style: {
            "signal": "buy",
            "confidence": 72,
            "marketRegime": "trending_up",
            "currentPrice": 117,
            "stopLoss": 115,
            "takeProfit1": 120,
            "riskReward": 1.5,
            "atr": 1.2,
            "aiScore": {"value": 70},
            "reason": "test analysis",
        },
    )
    monkeypatch.setattr(
        scanner_run,
        "build_prediction_response",
        lambda *args, **kwargs: _prediction_stub(),
    )

    config = ScannerConfig(
        name="Grouped direct test",
        logic="OR",
        groups=[
            ScannerConditionGroup(
                id="price",
                name="Price pass",
                logic="AND",
                conditions=[IndicatorCondition(indicator="Price", operator=">", value=0)],
            ),
            ScannerConditionGroup(
                id="rsi",
                name="RSI miss",
                logic="AND",
                conditions=[IndicatorCondition(indicator="RSI", operator="<", value=0)],
            ),
        ],
        pairs=["EUR/USD"],
        trade_style="swing",
        timeframe="1h",
    )

    result = scanner_run.evaluate_single_pair(
        "EUR/USD",
        scanner_run.flatten_conditions(config),
        config.logic,
        config.trade_style,
        config.timeframe,
        scanner_run.group_descriptors(config),
    )

    assert result is not None
    assert result["symbol"] == "EUR/USD"
    assert result["score"] == 0.5
    assert result["group_results"][0]["name"] == "Price pass"
    assert result["group_results"][0]["passed"] is True
    assert result["group_results"][1]["name"] == "RSI miss"
    assert result["group_results"][1]["passed"] is False
    assert result["matching_conditions"] == ["Price > 0.0"]
    assert result["confidence_band"] == "high"
    assert result["market_context"]["asset_class"] == "forex"
    assert result["action"]["label"] == "Trade-ready setup"
    assert result["action"]["trade_allowed"] is True
    assert "test analysis" in result["rationale"][0]


def test_scan_symbols_keeps_partial_errors_and_sorting(monkeypatch):
    def fake_evaluate(symbol, conditions, logic, trade_style, timeframe, groups):
        if symbol == "FAIL/USD":
            raise RuntimeError("market data unavailable")
        if symbol == "NONE/USD":
            return None
        return {
            "symbol": symbol,
            "signal": "BUY",
            "score": 1.0,
            "matching_conditions": ["RSI < 100"],
            "indicator_values": {"RSI": 50},
            "confidence": 80,
            "trade_style": trade_style,
            "timeframe": timeframe,
            "opportunity_score": 90 if symbol == "GBP/USD" else 70,
            "reason": "Matched scanner conditions.",
            "group_results": groups,
        }

    monkeypatch.setattr(scanner_run, "evaluate_single_pair", fake_evaluate)
    monkeypatch.setattr(scanner_run, "get_scanner_concurrency_limit", lambda total_symbols=None: 2)

    config = ScannerConfig(
        name="Partial direct test",
        conditions=[IndicatorCondition(indicator="RSI", operator="<", value=100)],
        logic="AND",
        pairs=["EUR/USD", "NONE/USD", "FAIL/USD", "GBP/USD"],
        trade_style="swing",
        timeframe="1h",
    )

    results, total_scanned, meta = asyncio.run(scanner_run.scan_symbols(config))

    assert total_scanned == 4
    assert meta["concurrency_limit"] == 2
    assert meta["succeeded"] == 2
    assert meta["failed"] == 1
    assert meta["unmatched"] == 1
    assert [item["symbol"] for item in results] == ["GBP/USD", "EUR/USD", "FAIL/USD"]
    assert results[-1]["scan_status"] == "error"
    assert results[-1]["error_message"] == "market data unavailable"
