import pandas as pd

from trading_bot.data.market_data_service import build_source_metadata


def _ohlcv_with_last_bar(last_timestamp: float) -> pd.DataFrame:
    index = pd.to_datetime(
        [last_timestamp - 120, last_timestamp - 60, last_timestamp],
        unit="s",
        utc=True,
    )
    return pd.DataFrame(
        {
            "open": [100.0, 100.5, 101.0],
            "high": [101.0, 101.5, 102.0],
            "low": [99.5, 100.0, 100.5],
            "close": [100.5, 101.0, 101.5],
            "volume": [1000.0, 1000.0, 1000.0],
        },
        index=index,
    )


def test_synthetic_spot_metadata_uses_base_bar_age_for_freshness(monkeypatch):
    now = 1_800_000_000.0
    last_bar = now - (11 * 60)
    monkeypatch.setattr("trading_bot.data.market_data_service.time.time", lambda: now)

    metadata = build_source_metadata(
        "XAU/USD",
        "1m",
        "scalp",
        _ohlcv_with_last_bar(last_bar),
        "gold-api.com",
        "synthetic_spot_from_futures",
        reference_timestamp=now,
    )

    assert metadata["freshnessSeconds"] == 660.0
    assert metadata["barAgeSeconds"] == 660.0
    assert metadata["baseBarAgeSeconds"] == 660.0
    assert metadata["quoteAgeSeconds"] == 0.0
    assert metadata["marketStatus"] == "delayed"
    assert metadata["qualityFlags"] == ["synthetic_spot"]


def test_synthetic_spot_metadata_flags_stale_base_candle(monkeypatch):
    now = 1_800_000_000.0
    last_bar = now - (40 * 60)
    monkeypatch.setattr("trading_bot.data.market_data_service.time.time", lambda: now)

    metadata = build_source_metadata(
        "XAU/USD",
        "1m",
        "scalp",
        _ohlcv_with_last_bar(last_bar),
        "gold-api.com",
        "synthetic_spot_from_futures",
        reference_timestamp=now,
    )

    assert metadata["freshnessSeconds"] == 2400.0
    assert metadata["marketStatus"] == "stale"
    assert "synthetic_spot" in metadata["qualityFlags"]
    assert "stale_data" in metadata["qualityFlags"]
