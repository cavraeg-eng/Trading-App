from datetime import datetime, timezone

import pandas as pd

from trading_bot.features.market_features import (
    MarketFeatureRequest,
    MarketQuote,
    build_market_features,
    build_market_features_batch,
)


def _candles(
    symbol_type: str = "forex",
    *,
    periods: int = 80,
    freq: str = "1h",
    start: str = "2026-01-01T00:00:00Z",
) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq=freq, tz="UTC")
    base = {"forex": 1.08, "crypto": 67000.0, "metals": 2350.0}[symbol_type]
    step = {"forex": 0.0004, "crypto": 120.0, "metals": 1.7}[symbol_type]
    closes = [base + step * idx for idx in range(periods)]
    return pd.DataFrame(
        {
            "open": [price - step * 0.25 for price in closes],
            "high": [price + abs(step) * 0.8 for price in closes],
            "low": [price - abs(step) * 0.9 for price in closes],
            "close": closes,
            "volume": [1000.0 + idx * 10 for idx in range(periods)],
        },
        index=index,
    )


def test_market_features_are_deterministic_for_forex_quote():
    candles = _candles("forex")
    reference_time = datetime(2026, 1, 4, 8, tzinfo=timezone.utc)
    quote = MarketQuote(bid=1.1115, ask=1.1118, last=1.11165, timestamp=reference_time)

    first = build_market_features(
        symbol="EUR/USD",
        timeframe="1h",
        candles=candles,
        quote=quote,
        reference_time=reference_time,
    )
    second = build_market_features(
        symbol="EUR/USD",
        timeframe="1h",
        candles=candles,
        quote=quote,
        reference_time=reference_time,
    )

    assert first.as_dict() == second.as_dict()
    assert first.status == "ok"
    assert first.features["trend_direction"] == "up"
    assert first.indicators["rsi_14"] == 100.0
    assert first.features["quote"]["spread"] == 0.0003


def test_crypto_features_include_stale_and_missing_quote_warnings():
    candles = _candles("crypto", start="2026-01-01T00:00:00Z")

    payload = build_market_features(
        symbol="BTC/USD",
        timeframe="1h",
        candles=candles,
        reference_time=datetime(2026, 1, 8, tzinfo=timezone.utc),
    )

    assert payload.status == "warning"
    assert "stale_data" in payload.quality["flags"]
    assert "missing_quote" in payload.quality["flags"]
    assert payload.features["quote"]["spread"] is None


def test_metals_features_report_multi_timeframe_context():
    primary = _candles("metals", periods=80, freq="15min", start="2026-01-03T12:00:00Z")
    higher = _candles("metals", periods=80, freq="1h")
    reference_time = datetime(2026, 1, 4, 8, tzinfo=timezone.utc)

    payload = build_market_features(
        symbol="XAU/USD",
        timeframe="15m",
        candles=primary,
        quote={"bid": 2483.1, "ask": 2483.8, "last": 2483.45},
        higher_timeframes={"1h": higher},
        reference_time=reference_time,
    )

    assert payload.status == "ok"
    assert payload.multi_timeframe["1h"]["trend_direction"] == "up"
    assert payload.market_structure["support"] is not None
    assert payload.market_structure["resistance"] is not None


def test_insufficient_and_inconsistent_data_emit_quality_flags():
    candles = _candles("forex", periods=10)
    candles = candles.drop(candles.index[3])

    payload = build_market_features(
        symbol="GBP/USD",
        timeframe="1h",
        candles=candles,
        reference_time=datetime(2026, 1, 1, 12, tzinfo=timezone.utc),
    )

    assert payload.status == "warning"
    assert "insufficient_history" in payload.quality["flags"]
    assert "missing_intervals" in payload.quality["flags"]


def test_unsorted_duplicate_candles_emit_inconsistent_timestamp_flag():
    candles = _candles("forex", periods=35).reset_index(names="timestamp")
    duplicate = candles.iloc[[5]].copy()
    duplicate["open"] = duplicate["open"] + 0.001
    duplicate["high"] = duplicate["high"] + 0.001
    duplicate["low"] = duplicate["low"] + 0.001
    duplicate["close"] = duplicate["close"] + 0.001
    candles = pd.concat([candles.iloc[10:], duplicate, candles.iloc[:10]], ignore_index=True)

    payload = build_market_features(
        symbol="EUR/USD",
        timeframe="1h",
        candles=candles,
        quote={"bid": 1.09, "ask": 1.0902},
        reference_time=datetime(2026, 1, 2, 12, tzinfo=timezone.utc),
    )

    assert payload.status == "warning"
    assert "inconsistent_timestamps" in payload.quality["flags"]


def test_batch_isolates_bad_symbol_errors():
    good = MarketFeatureRequest(
        symbol="XAU/USD",
        timeframe="1h",
        candles=_candles("metals"),
        quote={"bid": 2483.1, "ask": 2483.8},
    )
    bad = {"symbol": "BROKEN", "timeframe": "1h", "candles": object()}

    results = build_market_features_batch(
        [good, bad],
        reference_time=datetime(2026, 1, 4, 8, tzinfo=timezone.utc),
    )

    assert results["XAU/USD:1h"].status == "ok"
    assert results["BROKEN:1h"].status == "error"
    assert "feature_generation_error" in results["BROKEN:1h"].quality["flags"]