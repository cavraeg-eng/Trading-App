"""Shared scanner indicator metadata and evaluation helpers."""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

SUPPORTED_TIMEFRAMES = ("1m", "5m", "15m", "1h", "4h", "1d")
SUPPORTED_TRADE_STYLES = ("scalp", "swing")

INDICATOR_ALIASES = {
    "BB": "BB",
    "Bollinger Bands": "BB",
}

SCANNER_INDICATORS: List[Dict[str, Any]] = [
    {
        "key": "RSI",
        "label": "RSI",
        "description": "Relative Strength Index oscillator.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 100, "step": 1},
        "defaultValue": 30,
    },
    {
        "key": "MACD",
        "label": "MACD",
        "description": "MACD line for momentum and crossover scans.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": -1000, "max": 1000, "step": 0.01},
        "defaultValue": 0,
    },
    {
        "key": "MACD Signal",
        "label": "MACD Signal",
        "description": "Signal line of MACD.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": -1000, "max": 1000, "step": 0.01},
        "defaultValue": 0,
    },
    {
        "key": "MACD Histogram",
        "label": "MACD Histogram",
        "description": "MACD histogram strength and polarity.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": -1000, "max": 1000, "step": 0.01},
        "defaultValue": 0,
    },
    {
        "key": "Price",
        "label": "Price",
        "description": "Latest close price.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1_000_000, "step": 0.0001},
        "defaultValue": 0,
    },
    {
        "key": "EMA",
        "label": "EMA(20)",
        "description": "20-period exponential moving average.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1_000_000, "step": 0.0001},
        "defaultValue": 0,
    },
    {
        "key": "BB",
        "label": "Bollinger Position",
        "description": "Normalized position within Bollinger Bands (-1 to 1).",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": -1, "max": 1, "step": 0.01},
        "defaultValue": 0,
    },
    {
        "key": "BB Upper",
        "label": "Bollinger Upper",
        "description": "Upper Bollinger Band.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1_000_000, "step": 0.0001},
        "defaultValue": 0,
    },
    {
        "key": "BB Middle",
        "label": "Bollinger Middle",
        "description": "Middle Bollinger Band.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1_000_000, "step": 0.0001},
        "defaultValue": 0,
    },
    {
        "key": "BB Lower",
        "label": "Bollinger Lower",
        "description": "Lower Bollinger Band.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1_000_000, "step": 0.0001},
        "defaultValue": 0,
    },
    {
        "key": "ATR",
        "label": "ATR",
        "description": "14-period Average True Range.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 100_000, "step": 0.01},
        "defaultValue": 1,
    },
    {
        "key": "Volume",
        "label": "Volume Ratio",
        "description": "Current volume divided by 20-period average volume.",
        "supported": True,
        "supportsCompareIndicator": True,
        "operators": [">", "<", ">=", "<=", "=", "between", "crosses_above", "crosses_below"],
        "range": {"min": 0, "max": 1000, "step": 0.01},
        "defaultValue": 1,
    },
    {
        "key": "Stochastic",
        "label": "Stochastic",
        "description": "Planned oscillator support.",
        "supported": False,
        "supportsCompareIndicator": False,
        "operators": [],
        "range": {"min": 0, "max": 100, "step": 1},
        "defaultValue": 20,
    },
    {
        "key": "OBV",
        "label": "OBV",
        "description": "Planned on-balance volume support.",
        "supported": False,
        "supportsCompareIndicator": False,
        "operators": [],
        "range": {"min": -1_000_000_000, "max": 1_000_000_000, "step": 1},
        "defaultValue": 0,
    },
    {
        "key": "Williams %R",
        "label": "Williams %R",
        "description": "Planned Williams %R support.",
        "supported": False,
        "supportsCompareIndicator": False,
        "operators": [],
        "range": {"min": -100, "max": 0, "step": 1},
        "defaultValue": -50,
    },
]

INDICATOR_DEFINITION_MAP = {item["key"]: item for item in SCANNER_INDICATORS}
SUPPORTED_INDICATORS = {item["key"] for item in SCANNER_INDICATORS if item["supported"]}
ALLOWED_OPERATORS = sorted({op for item in SCANNER_INDICATORS for op in item["operators"]})


def resolve_indicator_name(name: str) -> str:
    return INDICATOR_ALIASES.get(name, name)


def indicator_definition(name: str) -> Optional[Dict[str, Any]]:
    return INDICATOR_DEFINITION_MAP.get(resolve_indicator_name(name))


def supported_indicator_names() -> List[str]:
    return [item["key"] for item in SCANNER_INDICATORS if item["supported"]]


def safe_float(val: Any, default: float = 0.0) -> float:
    try:
        cast_val = float(val)
        return cast_val if np.isfinite(cast_val) else default
    except (TypeError, ValueError):
        return default


def _series_or_default(source: pd.Series, default: float = 0.0) -> pd.Series:
    return source.replace([np.inf, -np.inf], np.nan).fillna(default)


def build_indicator_series(data: pd.DataFrame) -> Dict[str, pd.Series]:
    close = data["close"].astype(float)
    high = data["high"].astype(float)
    low = data["low"].astype(float)
    volume = data["volume"].astype(float)

    delta = close.diff()
    gain = delta.where(delta > 0, 0.0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0.0)).rolling(window=14).mean()
    loss = loss.replace(0, np.nan)
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    ema_fast = close.ewm(span=12, adjust=False).mean()
    ema_slow = close.ewm(span=26, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=9, adjust=False).mean()
    histogram = macd_line - signal_line

    ema20 = close.ewm(span=20, adjust=False).mean()

    sma = close.rolling(window=20).mean()
    std = close.rolling(window=20).std()
    bb_upper = sma + (2.0 * std)
    bb_lower = sma - (2.0 * std)
    band_width = (bb_upper - bb_lower).replace(0, np.nan)
    bb_position = ((close - bb_lower) / band_width * 2.0) - 1.0

    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=14).mean()

    avg_volume = volume.rolling(window=20).mean().replace(0, np.nan)
    volume_ratio = volume / avg_volume

    return {
        "RSI": _series_or_default(rsi, 50.0),
        "MACD": _series_or_default(macd_line, 0.0),
        "MACD Signal": _series_or_default(signal_line, 0.0),
        "MACD Histogram": _series_or_default(histogram, 0.0),
        "Price": _series_or_default(close, 0.0),
        "EMA": _series_or_default(ema20, 0.0),
        "BB": _series_or_default(bb_position, 0.0),
        "BB Upper": _series_or_default(bb_upper, 0.0),
        "BB Middle": _series_or_default(sma, 0.0),
        "BB Lower": _series_or_default(bb_lower, 0.0),
        "ATR": _series_or_default(atr, 0.0),
        "Volume": _series_or_default(volume_ratio, 1.0),
    }


def build_indicator_snapshot(data: pd.DataFrame, offset: int = -1) -> Dict[str, float]:
    series_map = build_indicator_series(data)
    snapshot: Dict[str, float] = {}
    for key, series in series_map.items():
        try:
            snapshot[key] = safe_float(series.iloc[offset])
        except Exception:
            snapshot[key] = 0.0
    return snapshot


def get_indicator_value_at(indicator_name: str, data: pd.DataFrame, offset: int) -> float:
    resolved = resolve_indicator_name(indicator_name)
    series_map = build_indicator_series(data)
    series = series_map.get(resolved)
    if series is None:
        return 0.0
    try:
        return safe_float(series.iloc[offset])
    except Exception:
        return 0.0


def evaluate_condition(
    operator: str,
    current_left: float,
    current_right: float,
    previous_left: Optional[float] = None,
    previous_right: Optional[float] = None,
    secondary_value: Optional[float] = None,
) -> bool:
    if operator == ">":
        return current_left > current_right
    if operator == "<":
        return current_left < current_right
    if operator == ">=":
        return current_left >= current_right
    if operator == "<=":
        return current_left <= current_right
    if operator in {"=", "==", "equals"}:
        return abs(current_left - current_right) < 0.01
    if operator == "between":
        if secondary_value is None:
            return False
        low = min(current_right, secondary_value)
        high = max(current_right, secondary_value)
        return low <= current_left <= high
    if operator == "crosses_above":
        if previous_left is None:
            return False
        previous_boundary = previous_right if previous_right is not None else current_right
        return previous_left <= previous_boundary and current_left > current_right
    if operator == "crosses_below":
        if previous_left is None:
            return False
        previous_boundary = previous_right if previous_right is not None else current_right
        return previous_left >= previous_boundary and current_left < current_right
    return False


def metadata_payload(categories: Iterable[str]) -> Dict[str, Any]:
    return {
        "indicators": SCANNER_INDICATORS,
        "operators": [{"value": op, "label": op.replace("_", " ")} for op in ALLOWED_OPERATORS],
        "supportedTimeframes": list(SUPPORTED_TIMEFRAMES),
        "supportedTradeStyles": list(SUPPORTED_TRADE_STYLES),
        "supportedCategories": list(categories),
    }