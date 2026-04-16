import pandas as pd

from trading_bot.data.data_validator import validate_ohlcv


def _build_ohlcv(closes: list[float]) -> pd.DataFrame:
    index = pd.date_range("2026-01-26", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame(
        {
            "open": closes,
            "high": [price * 1.01 for price in closes],
            "low": [price * 0.99 for price in closes],
            "close": closes,
            "volume": [1000.0 for _ in closes],
        },
        index=index,
    )


def test_xau_daily_futures_roll_gap_is_classified_separately():
    df = _build_ohlcv([5301.6, 5318.4, 4713.9, 4622.5, 4903.7])

    validated, issues = validate_ohlcv(
        df,
        "XAU/USD",
        timeframe="1d",
        source_type="futures",
        trade_style="swing",
    )

    assert validated is not None
    assert any(issue.startswith("futures_roll_gap:") for issue in issues)
    assert not any(issue.startswith("price_jump:") for issue in issues)


def test_non_xau_large_jump_still_uses_price_jump_flag():
    df = _build_ohlcv([1.00, 1.01, 1.22, 1.23, 1.24])

    validated, issues = validate_ohlcv(
        df,
        "EUR/USD",
        timeframe="1d",
        source_type="futures",
        trade_style="swing",
    )

    assert validated is not None
    assert any(issue.startswith("price_jump:") for issue in issues)
    assert not any(issue.startswith("futures_roll_gap:") for issue in issues)