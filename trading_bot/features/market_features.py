"""Normalized AI-ready market feature pipeline."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Optional

import numpy as np
import pandas as pd


TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


@dataclass(frozen=True)
class NormalizedCandle:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: Optional[float] = None


@dataclass(frozen=True)
class MarketQuote:
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    timestamp: Optional[datetime] = None


@dataclass(frozen=True)
class MarketFeatureRequest:
    symbol: str
    timeframe: str
    candles: Any
    quote: Optional[MarketQuote | Mapping[str, Any]] = None
    higher_timeframes: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class MarketFeaturePayload:
    symbol: str
    timeframe: str
    as_of: Optional[str]
    latest_price: Optional[float]
    status: str
    quality: dict[str, Any]
    features: dict[str, Any]
    indicators: dict[str, float]
    market_structure: dict[str, Any]
    multi_timeframe: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def build_market_features(
    *,
    symbol: str,
    timeframe: str,
    candles: Any,
    quote: Optional[MarketQuote | Mapping[str, Any]] = None,
    higher_timeframes: Optional[Mapping[str, Any]] = None,
    reference_time: Optional[datetime] = None,
    minimum_candles: int = 30,
    stale_after_seconds: Optional[int] = None,
) -> MarketFeaturePayload:
    warnings: list[str] = []
    errors: list[str] = []
    flags: list[str] = []
    higher_timeframes = higher_timeframes or {}

    df = _normalize_candles(candles, warnings, errors, flags)
    if df.empty:
        return _empty_payload(symbol, timeframe, "error", warnings, errors, flags)

    if len(df) < minimum_candles:
        _add_issue(flags, warnings, "insufficient_history")

    _validate_time_index(df, timeframe, warnings, flags)
    _validate_price_consistency(df, warnings, errors, flags)

    latest_timestamp = _timestamp_to_utc(df.index[-1])
    reference_time = _timestamp_to_utc(reference_time or datetime.now(timezone.utc))
    stale_seconds = stale_after_seconds or TIMEFRAME_SECONDS.get(timeframe, 3600) * 3
    age_seconds = max(0.0, (reference_time - latest_timestamp).total_seconds())
    if age_seconds > stale_seconds:
        _add_issue(flags, warnings, "stale_data")

    quote_features = _quote_features(quote, df["close"].iloc[-1], warnings, flags)
    indicators = _indicator_snapshot(df)
    features = _core_features(df, indicators, quote_features, len(df), age_seconds)
    market_structure = _market_structure(df)
    multi_timeframe = _multi_timeframe_summary(
        higher_timeframes,
        symbol,
        reference_time,
        minimum_candles,
    )

    quality_score = _quality_score(flags, errors)
    status = "error" if errors else "warning" if warnings else "ok"
    quality = {
        "score": quality_score,
        "flags": sorted(flags),
        "warnings": warnings,
        "errors": errors,
        "rows": int(len(df)),
        "ageSeconds": round(age_seconds, 3),
    }

    return MarketFeaturePayload(
        symbol=symbol,
        timeframe=timeframe,
        as_of=latest_timestamp.isoformat(),
        latest_price=_safe_round(df["close"].iloc[-1]),
        status=status,
        quality=quality,
        features=features,
        indicators=indicators,
        market_structure=market_structure,
        multi_timeframe=multi_timeframe,
    )


def build_market_features_batch(
    requests: Iterable[MarketFeatureRequest | Mapping[str, Any]],
    *,
    reference_time: Optional[datetime] = None,
    minimum_candles: int = 30,
) -> dict[str, MarketFeaturePayload]:
    results: dict[str, MarketFeaturePayload] = {}
    for request in requests:
        try:
            normalized = _request_from_any(request)
            key = f"{normalized.symbol}:{normalized.timeframe}"
            results[key] = build_market_features(
                symbol=normalized.symbol,
                timeframe=normalized.timeframe,
                candles=normalized.candles,
                quote=normalized.quote,
                higher_timeframes=normalized.higher_timeframes,
                reference_time=reference_time,
                minimum_candles=minimum_candles,
            )
        except Exception as exc:
            symbol = str(_mapping_get(request, "symbol", "unknown"))
            timeframe = str(_mapping_get(request, "timeframe", "unknown"))
            results[f"{symbol}:{timeframe}"] = _empty_payload(
                symbol,
                timeframe,
                "error",
                [],
                [f"feature_generation_error:{type(exc).__name__}:{exc}"],
                ["feature_generation_error"],
            )
    return results


def _request_from_any(request: MarketFeatureRequest | Mapping[str, Any]) -> MarketFeatureRequest:
    if isinstance(request, MarketFeatureRequest):
        return request
    return MarketFeatureRequest(
        symbol=str(request["symbol"]),
        timeframe=str(request["timeframe"]),
        candles=request["candles"],
        quote=request.get("quote"),
        higher_timeframes=request.get("higher_timeframes") or request.get("higherTimeframes") or {},
    )


def _mapping_get(source: Any, key: str, default: Any) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _normalize_candles(
    candles: Any,
    warnings: list[str],
    errors: list[str],
    flags: list[str],
) -> pd.DataFrame:
    if candles is None:
        errors.append("missing_candles")
        flags.append("missing_candles")
        return pd.DataFrame()

    if isinstance(candles, pd.DataFrame):
        df = candles.copy()
    else:
        rows = [_candle_to_mapping(candle) for candle in candles]
        df = pd.DataFrame(rows)

    rename_map = {
        "time": "timestamp",
        "date": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(
        columns={source: target for source, target in rename_map.items() if source in df}
    )

    missing = [column for column in ("open", "high", "low", "close") if column not in df]
    if missing:
        errors.append(f"missing_fields:{','.join(missing)}")
        flags.append("missing_fields")
        return pd.DataFrame()

    if "timestamp" in df:
        timestamps = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
        df = df.drop(columns=["timestamp"])
        df.index = timestamps
    elif not isinstance(df.index, pd.DatetimeIndex):
        errors.append("missing_timestamp")
        flags.append("missing_timestamp")
        return pd.DataFrame()
    else:
        df.index = pd.to_datetime(df.index, utc=True, errors="coerce")

    for column in ("open", "high", "low", "close", "volume"):
        if column in df:
            df[column] = pd.to_numeric(df[column], errors="coerce")
    if "volume" not in df:
        df["volume"] = np.nan
        _add_issue(flags, warnings, "missing_volume")

    initial_rows = len(df)
    df = df[~df.index.isna()].sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df.dropna(subset=["open", "high", "low", "close"])
    if len(df) < initial_rows:
        _add_issue(flags, warnings, "partial_candles")

    return df[["open", "high", "low", "close", "volume"]]


def _candle_to_mapping(candle: Any) -> Mapping[str, Any]:
    if isinstance(candle, NormalizedCandle):
        return asdict(candle)
    if isinstance(candle, Mapping):
        return candle
    return {
        "timestamp": getattr(candle, "timestamp", None),
        "open": getattr(candle, "open", None),
        "high": getattr(candle, "high", None),
        "low": getattr(candle, "low", None),
        "close": getattr(candle, "close", None),
        "volume": getattr(candle, "volume", None),
    }


def _validate_time_index(
    df: pd.DataFrame,
    timeframe: str,
    warnings: list[str],
    flags: list[str],
) -> None:
    if len(df) < 3:
        return
    expected_seconds = TIMEFRAME_SECONDS.get(timeframe)
    if not expected_seconds:
        _add_issue(flags, warnings, "unknown_timeframe")
        return
    deltas = df.index.to_series().diff().dropna().dt.total_seconds()
    if (deltas <= 0).any():
        _add_issue(flags, warnings, "inconsistent_timestamps")
    if (deltas > expected_seconds * 1.5).any():
        _add_issue(flags, warnings, "missing_intervals")


def _validate_price_consistency(
    df: pd.DataFrame,
    warnings: list[str],
    errors: list[str],
    flags: list[str],
) -> None:
    invalid_price = (
        (df[["open", "high", "low", "close"]] <= 0).any(axis=1)
        | (df["high"] < df[["open", "close", "low"]].max(axis=1))
        | (df["low"] > df[["open", "close", "high"]].min(axis=1))
    )
    if invalid_price.any():
        errors.append("invalid_prices")
        flags.append("invalid_prices")
    if df["volume"].notna().any() and (df["volume"].dropna() < 0).any():
        _add_issue(flags, warnings, "invalid_volume")


def _quote_features(
    quote: Optional[MarketQuote | Mapping[str, Any]],
    latest_close: float,
    warnings: list[str],
    flags: list[str],
) -> dict[str, Optional[float]]:
    if quote is None:
        _add_issue(flags, warnings, "missing_quote")
        return {
            "bid": None,
            "ask": None,
            "last": None,
            "mid": None,
            "spread": None,
            "spread_pct": None,
            "quote_price_distance_pct": None,
        }

    bid = _safe_optional_float(_mapping_get(quote, "bid", None))
    ask = _safe_optional_float(_mapping_get(quote, "ask", None))
    last = _safe_optional_float(_mapping_get(quote, "last", None))
    mid = (bid + ask) / 2 if bid is not None and ask is not None else last
    spread = ask - bid if bid is not None and ask is not None else None

    if bid is not None and ask is not None and (bid <= 0 or ask <= 0 or ask < bid):
        _add_issue(flags, warnings, "invalid_quote")
    if spread is None:
        _add_issue(flags, warnings, "missing_spread")

    spread_pct = spread / mid if spread is not None and mid and mid > 0 else None
    distance = (mid - latest_close) / latest_close if mid and latest_close > 0 else None
    return {
        "bid": _safe_round(bid),
        "ask": _safe_round(ask),
        "last": _safe_round(last),
        "mid": _safe_round(mid),
        "spread": _safe_round(spread),
        "spread_pct": _safe_round(spread_pct),
        "quote_price_distance_pct": _safe_round(distance),
    }


def _indicator_snapshot(df: pd.DataFrame) -> dict[str, float]:
    close = df["close"].astype(float)
    high = df["high"].astype(float)
    low = df["low"].astype(float)
    volume = df["volume"].astype(float)

    ema_9 = _ema(close, 9)
    ema_12 = _ema(close, 12)
    ema_21 = _ema(close, 21)
    ema_26 = _ema(close, 26)
    ema_50 = _ema(close, 50)
    sma_20 = close.rolling(window=20).mean()
    sma_50 = close.rolling(window=50).mean()
    macd = ema_12 - ema_26
    macd_signal = _ema(macd, 9)
    atr_14 = _atr(high, low, close, 14)
    returns = close.pct_change()
    volume_sma_20 = volume.rolling(window=20).mean()

    values = {
        "rsi_14": _rsi(close, 14).iloc[-1],
        "macd": macd.iloc[-1],
        "macd_signal": macd_signal.iloc[-1],
        "macd_histogram": (macd - macd_signal).iloc[-1],
        "ema_9": ema_9.iloc[-1],
        "ema_21": ema_21.iloc[-1],
        "ema_50": ema_50.iloc[-1],
        "sma_20": sma_20.iloc[-1],
        "sma_50": sma_50.iloc[-1],
        "atr_14": atr_14.iloc[-1],
        "volatility_20": returns.rolling(window=20).std().iloc[-1],
        "momentum_5": close.pct_change(5).iloc[-1],
        "momentum_10": close.pct_change(10).iloc[-1],
        "momentum_20": close.pct_change(20).iloc[-1],
        "volume_ratio_20": (volume / volume_sma_20).iloc[-1],
    }
    return {key: _safe_round(value) for key, value in values.items()}


def _core_features(
    df: pd.DataFrame,
    indicators: dict[str, float],
    quote_features: dict[str, Optional[float]],
    row_count: int,
    age_seconds: float,
) -> dict[str, Any]:
    latest_close = float(df["close"].iloc[-1])
    ema_21 = indicators["ema_21"]
    ema_50 = indicators["ema_50"]
    atr_14 = indicators["atr_14"]
    trend_direction = "up" if ema_21 > ema_50 else "down" if ema_21 < ema_50 else "flat"
    trend_strength = abs((ema_21 - ema_50) / latest_close) if latest_close > 0 else 0.0

    return {
        "trend_direction": trend_direction,
        "trend_strength": _safe_round(trend_strength),
        "price_vs_ema_21": _safe_round((latest_close - ema_21) / ema_21 if ema_21 else None),
        "price_vs_ema_50": _safe_round((latest_close - ema_50) / ema_50 if ema_50 else None),
        "atr_pct": _safe_round(atr_14 / latest_close if latest_close > 0 else None),
        "row_count": row_count,
        "age_seconds": _safe_round(age_seconds, 3),
        "quote": quote_features,
    }


def _market_structure(df: pd.DataFrame) -> dict[str, Any]:
    lookback = min(20, len(df))
    close = float(df["close"].iloc[-1])
    recent = df.tail(lookback)
    support = float(recent["low"].min())
    resistance = float(recent["high"].max())
    swing_window = min(5, len(df))
    swing_highs = df["high"].rolling(window=swing_window).max()
    swing_lows = df["low"].rolling(window=swing_window).min()
    previous_high = swing_highs.iloc[-2] if len(swing_highs) >= 2 else np.nan
    previous_low = swing_lows.iloc[-2] if len(swing_lows) >= 2 else np.nan

    return {
        "support": _safe_round(support),
        "resistance": _safe_round(resistance),
        "support_distance_pct": _safe_round((close - support) / close if close > 0 else None),
        "resistance_distance_pct": _safe_round((resistance - close) / close if close > 0 else None),
        "recent_swing_high": _safe_round(swing_highs.iloc[-1]),
        "recent_swing_low": _safe_round(swing_lows.iloc[-1]),
        "higher_high": bool(np.isfinite(previous_high) and swing_highs.iloc[-1] > previous_high),
        "lower_low": bool(np.isfinite(previous_low) and swing_lows.iloc[-1] < previous_low),
    }


def _multi_timeframe_summary(
    higher_timeframes: Mapping[str, Any],
    symbol: str,
    reference_time: datetime,
    minimum_candles: int,
) -> dict[str, Any]:
    summaries: dict[str, Any] = {}
    for timeframe, candles in higher_timeframes.items():
        payload = build_market_features(
            symbol=symbol,
            timeframe=str(timeframe),
            candles=candles,
            reference_time=reference_time,
            minimum_candles=minimum_candles,
        )
        summaries[str(timeframe)] = {
            "status": payload.status,
            "trend_direction": payload.features.get("trend_direction"),
            "trend_strength": payload.features.get("trend_strength"),
            "latest_price": payload.latest_price,
            "quality_flags": payload.quality.get("flags", []),
        }
    return summaries


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=period).mean().replace(0, np.nan)
    rs = gain / loss
    return (100 - (100 / (1 + rs))).fillna(50.0)


def _ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    high_low = high - low
    high_close = (high - close.shift()).abs()
    low_close = (low - close.shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(window=period).mean().fillna(0.0)


def _safe_optional_float(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if np.isfinite(parsed) else None


def _safe_round(value: Any, digits: int = 8) -> Optional[float]:
    parsed = _safe_optional_float(value)
    return round(parsed, digits) if parsed is not None else None


def _timestamp_to_utc(value: datetime | pd.Timestamp) -> datetime:
    timestamp = pd.Timestamp(value)
    if timestamp.tzinfo is None:
        timestamp = timestamp.tz_localize(timezone.utc)
    return timestamp.tz_convert(timezone.utc).to_pydatetime()


def _add_issue(flags: list[str], warnings: list[str], issue: str) -> None:
    if issue not in flags:
        flags.append(issue)
    if issue not in warnings:
        warnings.append(issue)


def _quality_score(flags: list[str], errors: list[str]) -> float:
    score = 1.0 - (len(set(flags)) * 0.08) - (len(errors) * 0.25)
    return round(max(0.0, min(1.0, score)), 4)


def _empty_payload(
    symbol: str,
    timeframe: str,
    status: str,
    warnings: list[str],
    errors: list[str],
    flags: list[str],
) -> MarketFeaturePayload:
    return MarketFeaturePayload(
        symbol=symbol,
        timeframe=timeframe,
        as_of=None,
        latest_price=None,
        status=status,
        quality={
            "score": _quality_score(flags, errors),
            "flags": sorted(set(flags)),
            "warnings": warnings,
            "errors": errors,
            "rows": 0,
            "ageSeconds": None,
        },
        features={},
        indicators={},
        market_structure={},
    )