from typing import Optional

import pandas as pd

from trading_bot.services import market_analysis


def _fixture_candles() -> pd.DataFrame:
    rows = []
    for index in range(80):
        close = 1.10 + index * 0.0007
        rows.append({
            "open": close - 0.0002,
            "high": close + 0.0005,
            "low": close - 0.0006,
            "close": close,
            "volume": 1000 + index * 5,
        })
    return pd.DataFrame(
        rows,
        index=pd.date_range("2026-01-01", periods=len(rows), freq="h"),
    )


def _anchor_history(_symbol: str, _timeframe: str, _direction: Optional[str]) -> dict:
    return {
        "sampleSize": 0,
        "tpHitRate": 0.0,
        "slHitRate": 0.0,
        "expiredRate": 0.0,
    }


def test_build_market_analysis_preserves_contract_shape_with_fixture_data():
    analysis = market_analysis.build_market_analysis(
        "EUR/USD",
        "1h",
        "swing",
        _fixture_candles(),
        {"qualityFlags": [], "sourceName": "fixture"},
        context_bias_provider=lambda symbol, timeframe, trade_style: ("bullish", 72.5),
        sentiment_score_provider=lambda symbol: 0.1,
        anchor_performance_provider=_anchor_history,
    )

    assert analysis is not None
    assert analysis["signal"] == "buy"
    assert analysis["confidence"] == 79
    assert analysis["currentPrice"] == 1.1553
    assert analysis["marketRegime"] == "trending_up"
    assert analysis["higherTimeframeBias"] == {"direction": "bullish", "strength": 72.5}
    assert analysis["entryRange"] == {"min": 1.15472, "max": 1.1553}
    assert analysis["stopLoss"] == 1.14105
    assert analysis["takeProfit1"] == 1.1558
    assert analysis["riskReward"] == 2.38
    assert analysis["anchorModel"]["support"] == 1.1414
    assert analysis["anchorModel"]["resistance"] == 1.1558
    assert analysis["is_mock"] is False
    assert analysis["source"] == "live"
    assert {indicator["name"] for indicator in analysis["indicators"]} == {
        "RSI(14)",
        "MACD",
        "EMA(20)",
        "BB Position",
        "Volume",
    }


def test_analyze_symbol_fetches_data_then_uses_market_analysis_module(monkeypatch):
    monkeypatch.setattr(
        market_analysis,
        "get_shared_ohlcv_with_metadata",
        lambda symbol, timeframe, trade_style="swing": (
            _fixture_candles(),
            {"qualityFlags": [], "sourceName": "fixture"},
        ),
    )
    monkeypatch.setattr(
        market_analysis,
        "_get_context_bias",
        lambda symbol, timeframe, trade_style: ("bullish", 72.5),
    )
    monkeypatch.setattr(
        market_analysis,
        "_get_sentiment_score",
        lambda symbol, provider=None: 0.1,
    )
    monkeypatch.setattr(
        market_analysis.repo,
        "get_signal_outcome_summary",
        lambda **kwargs: _anchor_history(
            kwargs["symbol"],
            kwargs["timeframe"],
            kwargs["direction"],
        ),
    )

    analysis = market_analysis.analyze_symbol("EUR/USD", "1h", trade_style="swing")

    assert analysis is not None
    assert analysis["signal"] == "buy"
    assert analysis["higherTimeframeBias"]["direction"] == "bullish"
