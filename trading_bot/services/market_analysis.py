"""Market analysis interface and implementation."""

import math
import time
from typing import Callable, Dict, List, Optional, Tuple, Union

import numpy as np
import pandas as pd

from trading_bot.config import get_logger
from trading_bot.data.market_data_service import (
    SPOT_PRICE_SYMBOLS,
    SYMBOL_MAPPING,
    get_ohlcv,
    get_ohlcv_with_metadata,
)
from trading_bot.monitoring.bot_metrics import bot_metrics, classify_no_trade_reason
from trading_bot.persistence import signals as repo

logger = get_logger(__name__)

# Whitelist of allowed trading symbols
ALLOWED_SYMBOLS = {
    "XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD",
    "NZD/USD", "USD/CAD", "USD/CHF", "EUR/GBP", "EUR/JPY",
    "GBP/JPY", "BTC/USD", "ETH/USD", "US500", "US30",
    # Also add yfinance-style symbols
    "XAUUSD=X", "EURUSD=X", "GBPUSD=X", "USDJPY=X", "AUDUSD=X",
    "NZDUSD=X", "USDCAD=X", "USDCHF=X", "EURGBP=X", "EURJPY=X",
    "GBPJPY=X", "BTC-USD", "ETH-USD", "^GSPC", "^DJI",
}
# Also allow any symbol that exists in SYMBOL_MAPPING
ALLOWED_SYMBOLS.update(SYMBOL_MAPPING.keys())
ALLOWED_SYMBOLS.update(SYMBOL_MAPPING.values())

ContextBiasProvider = Callable[[str, str, str], Tuple[str, float]]
SentimentScoreProvider = Callable[[str], Optional[float]]
AnchorPerformanceProvider = Callable[[str, str, Optional[str]], Dict[str, object]]


def get_pip_size(price: float) -> float:
    """Return pip size based on instrument price magnitude."""
    if price < 10:
        return 0.0001   # Standard forex (EUR/USD ~1.08)
    elif price < 200:
        return 0.01      # JPY pairs (USD/JPY ~155)
    elif price < 5000:
        return 0.10      # Gold (~2350), Platinum (~980)
    else:
        return 1.0       # Indices (US500 ~5250, US30 ~39800), BTC (~68500)


def get_decimal_places(price: float) -> int:
    """Return appropriate decimal places based on price magnitude.
    Forex pairs (~1.16): 5 decimals (standard forex precision)
    JPY pairs (~150): 3 decimals
    Gold (~3000): 2 decimals
    Indices (~40000): 2 decimals
    """
    if price < 10:
        return 5  # EUR/USD, GBP/USD, etc.
    elif price < 200:
        return 3  # USD/JPY, etc.
    else:
        return 2  # Gold, indices, etc.


def get_shared_ohlcv(
    symbol: str,
    timeframe: str,
    trade_style: str = "swing",
) -> Optional[pd.DataFrame]:
    """Get OHLCV data from shared cache or fetch fresh.

    This is the SINGLE source of truth for market data.  All endpoints
    (analysis, candles, signals, quote) should call this instead of
    fetch_data_yf() directly.

    Now delegates to the unified MarketDataService for consistent
    fetching, caching, validation, and health tracking across all
    consumers (market, scanner, signals, backtest).
    """
    from trading_bot.data.market_data_service import get_ohlcv
    return get_ohlcv(symbol, timeframe, trade_style=trade_style)


def get_shared_ohlcv_with_metadata(
    symbol: str,
    timeframe: str,
    trade_style: str = "swing",
) -> tuple:
    """Get OHLCV data and source metadata from the unified service."""
    return get_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)


def resolve_context_trade_style(symbol: str, timeframe: str, trade_style: str) -> str:
    """Use futures context for higher-timeframe scalp views on spot-backed symbols."""
    if (
        trade_style == "scalp"
        and symbol in SPOT_PRICE_SYMBOLS
        and timeframe not in ("1m", "5m")
    ):
        return "swing"
    return trade_style


def map_symbol_to_yf(symbol: str) -> str:
    """Map our symbol format to yfinance format."""
    return SYMBOL_MAPPING.get(symbol, symbol)


def calculate_rsi(prices: pd.Series, period: int = 14) -> float:
    """Calculate RSI for the last value."""
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else 50.0


def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
    """Calculate MACD values."""
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]


def calculate_ema(prices: pd.Series, period: int = 20) -> float:
    """Calculate EMA for the last value."""
    ema = prices.ewm(span=period, adjust=False).mean()
    return ema.iloc[-1] if not ema.empty else prices.iloc[-1]


def calculate_bollinger_bands(prices: pd.Series, period: int = 20, std_dev: float = 2.0) -> tuple:
    """Calculate Bollinger Bands."""
    sma = prices.rolling(window=period).mean()
    std = prices.rolling(window=period).std()
    upper = sma + (std * std_dev)
    lower = sma - (std * std_dev)
    return upper.iloc[-1], sma.iloc[-1], lower.iloc[-1]


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> float:
    """Calculate Average True Range."""
    high_low = high - low
    high_close = np.abs(high - close.shift())
    low_close = np.abs(low - close.shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr.iloc[-1] if not atr.empty else 0.0


def _indicator_thresholds(timeframe: str, trade_style: str) -> dict:
    """Return per-timeframe thresholds tuned for lower-noise signals."""
    if trade_style == "scalp":
        if timeframe == "1m":
            return {
                "rsi_buy": 38.0,
                "rsi_sell": 62.0,
                "bb_buy": 0.18,
                "bb_sell": 0.82,
                "decision_threshold": 1.45,
                "min_directional_confidence": 60,
            }
        if timeframe == "5m":
            return {
                "rsi_buy": 40.0,
                "rsi_sell": 60.0,
                "bb_buy": 0.24,
                "bb_sell": 0.76,
                "decision_threshold": 1.35,
                "min_directional_confidence": 58,
            }
        return {
            "rsi_buy": 42.0,
            "rsi_sell": 58.0,
            "bb_buy": 0.28,
            "bb_sell": 0.72,
            "decision_threshold": 1.25,
            "min_directional_confidence": 57,
        }

    return {
        "rsi_buy": 42.0,
        "rsi_sell": 58.0,
        "bb_buy": 0.30,
        "bb_sell": 0.70,
        "decision_threshold": 1.20,
        "min_directional_confidence": 55,
    }


def _volume_signal(volume_ratio: float, price_change: float) -> Tuple[str, str]:
    """Classify volume as directional only when expansion confirms price."""
    label = "Above Avg" if volume_ratio >= 1.0 else "Below Avg"
    if volume_ratio >= 1.15:
        if price_change > 0:
            return "bullish", label
        if price_change < 0:
            return "bearish", label
    return "neutral", label


def _trend_signal(current_price: float, ema20: float, ema50: float) -> str:
    """Classify local trend using price and moving average structure."""
    if current_price > ema20 and ema20 >= ema50:
        return "bullish"
    if current_price < ema20 and ema20 <= ema50:
        return "bearish"
    return "neutral"


def _infer_trend_bias(df: Optional[pd.DataFrame]) -> Tuple[str, float]:
    """Summarize higher-timeframe trend direction for context alignment."""
    if df is None or len(df) < 50:
        return "neutral", 50.0

    closes = df["close"]
    current_price = float(closes.iloc[-1])
    ema20 = calculate_ema(closes, 20)
    ema50 = calculate_ema(closes, 50)
    rsi = calculate_rsi(closes, 14)
    macd_line, macd_signal, macd_hist = calculate_macd(closes)

    bull_score = 0.0
    bear_score = 0.0

    if current_price > ema20:
        bull_score += 1.0
    elif current_price < ema20:
        bear_score += 1.0

    if ema20 > ema50:
        bull_score += 1.0
    elif ema20 < ema50:
        bear_score += 1.0

    if macd_hist > 0 and macd_line > macd_signal:
        bull_score += 1.0
    elif macd_hist < 0 and macd_line < macd_signal:
        bear_score += 1.0

    if rsi >= 52:
        bull_score += 1.0
    elif rsi <= 48:
        bear_score += 1.0

    if bull_score >= bear_score + 1.0:
        return "bullish", round(55 + (bull_score / 4.0) * 35, 1)
    if bear_score >= bull_score + 1.0:
        return "bearish", round(55 + (bear_score / 4.0) * 35, 1)
    return "neutral", 50.0


def _context_timeframes(timeframe: str) -> List[str]:
    """Choose higher-timeframe references for directional confirmation."""
    if timeframe == "1m":
        return ["5m", "15m"]
    if timeframe == "5m":
        return ["15m", "1h"]
    if timeframe == "15m":
        return ["1h", "4h"]
    if timeframe == "1h":
        return ["4h", "1d"]
    if timeframe == "4h":
        return ["1d"]
    return []


def _get_context_bias(symbol: str, timeframe: str, trade_style: str) -> Tuple[str, float]:
    """Compute a compact higher-timeframe directional bias."""
    timeframes = _context_timeframes(timeframe)
    if not timeframes:
        return "neutral", 50.0

    weighted_bull = 0.0
    weighted_bear = 0.0
    total_weight = 0.0

    for index, tf in enumerate(timeframes):
        weight = 1.0 if index == 0 else 0.8
        context_trade_style = resolve_context_trade_style(symbol, tf, trade_style)
        df = get_shared_ohlcv(symbol, tf, trade_style=context_trade_style)
        bias, strength = _infer_trend_bias(df)
        total_weight += weight
        if bias == "bullish":
            weighted_bull += weight * strength
        elif bias == "bearish":
            weighted_bear += weight * strength

    if total_weight == 0:
        return "neutral", 50.0
    if weighted_bull >= weighted_bear + 10:
        return "bullish", round(weighted_bull / total_weight, 1)
    if weighted_bear >= weighted_bull + 10:
        return "bearish", round(weighted_bear / total_weight, 1)
    return "neutral", 50.0


def _quality_penalty(quality_flags: List[str], timeframe: str, trade_style: str) -> int:
    """Translate source quality flags into a confidence penalty."""
    penalty = 0
    if any(flag.startswith("stale_data") for flag in quality_flags):
        penalty += 24 if trade_style == "scalp" and timeframe in ("1m", "5m") else 12
    if "fallback_source" in quality_flags:
        penalty += 6
    if any(flag.startswith("price_jump") for flag in quality_flags):
        penalty += 6
    return penalty


def _should_force_hold_for_quality(
    symbol: str,
    timeframe: str,
    trade_style: str,
    quality_flags: List[str],
) -> bool:
    """Force HOLD when scalp data quality is too weak for directional trust."""
    if trade_style != "scalp" or timeframe not in ("1m", "5m"):
        return False

    if any(flag.startswith("stale_data") for flag in quality_flags):
        return True

    if "fallback_source" in quality_flags:
        return True

    if symbol.endswith("/USD") and symbol not in SPOT_PRICE_SYMBOLS and any(flag.startswith("stale_data") for flag in quality_flags):
        return True

    return False


def _classify_market_regime(
    df: pd.DataFrame,
    current_price: float,
    ema20: float,
    ema50: float,
    macd_line: float,
    macd_hist: float,
    rsi: float,
    atr: float,
) -> str:
    """Classify regime using multi-factor trend strength instead of single-bar state."""
    if df is None or len(df) < 30:
        return "ranging"

    recent = df.tail(12)
    recent_closes = recent["close"]
    recent_highs = recent["high"]
    recent_lows = recent["low"]

    ema_gap = abs(ema20 - ema50)
    ema_gap_ratio = ema_gap / max(atr, current_price * 0.0001, 1e-9)
    recent_return = (float(recent_closes.iloc[-1]) - float(recent_closes.iloc[0])) / max(current_price, 1e-9)
    net_direction = np.sign(recent_closes.diff().fillna(0)).sum()
    directional_ratio = abs(float(net_direction)) / max(len(recent_closes) - 1, 1)
    recent_range = (float(recent_highs.max()) - float(recent_lows.min())) / max(atr, current_price * 0.0001, 1e-9)

    avg_atr_series = df["close"].rolling(window=20).apply(
        lambda x: calculate_atr(df["high"].loc[x.index], df["low"].loc[x.index], df["close"].loc[x.index])
    )
    avg_atr = avg_atr_series.iloc[-1] if hasattr(avg_atr_series, "iloc") else avg_atr_series

    if avg_atr and atr > 1.65 * avg_atr and recent_range > 5.0:
        return "volatile"

    bull_checks = 0
    bear_checks = 0

    if current_price > ema20:
        bull_checks += 1
    elif current_price < ema20:
        bear_checks += 1

    if ema20 >= ema50:
        bull_checks += 1
    else:
        bear_checks += 1

    if macd_hist > 0 and macd_line > 0:
        bull_checks += 1
    elif macd_hist < 0 and macd_line < 0:
        bear_checks += 1

    if rsi >= 53:
        bull_checks += 1
    elif rsi <= 47:
        bear_checks += 1

    if recent_return > 0:
        bull_checks += 1
    elif recent_return < 0:
        bear_checks += 1

    if bull_checks >= 4 and ema_gap_ratio >= 0.35 and directional_ratio >= 0.18:
        return "trending_up"
    if bear_checks >= 4 and ema_gap_ratio >= 0.35 and directional_ratio >= 0.18:
        return "trending_down"
    return "ranging"


def _select_patterns_for_signal(
    patterns: List[dict],
    signal: str,
    context_bias: str,
) -> List[dict]:
    """Prefer patterns that reinforce the active signal or higher-timeframe context."""
    if not patterns:
        return []

    preferred_direction = None
    if signal == "buy":
        preferred_direction = "bullish"
    elif signal == "sell":
        preferred_direction = "bearish"
    elif context_bias in ("bullish", "bearish"):
        preferred_direction = context_bias

    ranked = sorted(
        patterns,
        key=lambda pattern: (
            pattern["confidence"]
            + (18 if preferred_direction and pattern["direction"] == preferred_direction else 0)
            - (16 if preferred_direction and pattern["direction"] != preferred_direction else 0)
        ),
        reverse=True,
    )

    if signal == "hold":
        if preferred_direction is None:
            return []
        return [
            pattern
            for pattern in ranked
            if pattern["direction"] == preferred_direction and pattern["confidence"] >= 80
        ][:2]

    if preferred_direction is None:
        return ranked[:3]

    matching = [pattern for pattern in ranked if pattern["direction"] == preferred_direction]
    return matching[:3] if matching else ranked[:1]


def _cap_confidence_for_quality(
    signal: str,
    confidence: int,
    top_pattern: Optional[dict],
    context_bias: str,
    alignment_hint: float,
) -> int:
    """Reduce outsized confidence when evidence is mixed or mostly contextual."""
    capped = confidence
    if signal == "hold":
        return min(capped, 58)
    if top_pattern and top_pattern["direction"] != ("bullish" if signal == "buy" else "bearish"):
        capped = min(capped, 74)
    if context_bias not in ("bullish" if signal == "buy" else "bearish", "neutral"):
        capped = min(capped, 70)
    if alignment_hint < 60:
        capped = min(capped, 76)
    return capped


def _effective_atr(current_price: float, atr: float, timeframe: str, trade_style: str) -> float:
    if trade_style == "scalp":
        if timeframe == "1m":
            floor_pct = 0.00035
        elif timeframe == "5m":
            floor_pct = 0.00045
        else:
            floor_pct = 0.00065
    else:
        floor_pct = 0.0012 if timeframe in ("1h", "4h") else 0.0018
    return max(_safe_float(atr, 0.0), current_price * floor_pct)


def _recent_structure_levels(df: pd.DataFrame, trade_style: str) -> Dict[str, float]:
    close_fallback = _safe_float(df["close"].iloc[-1], 0.0)
    primary_lookback = 12 if trade_style == "scalp" else 20
    swing_lookback = 8 if trade_style == "scalp" else 12
    recent = df.tail(primary_lookback)
    swing_window = df.tail(max(primary_lookback, swing_lookback))
    return {
        "support": _safe_float(recent["low"].min(), close_fallback),
        "resistance": _safe_float(recent["high"].max(), close_fallback),
        "swing_low": _safe_float(swing_window["low"].tail(swing_lookback).min(), close_fallback),
        "swing_high": _safe_float(swing_window["high"].tail(swing_lookback).max(), close_fallback),
    }


def _aligned_pattern_target(patterns: List[dict], signal: str) -> Optional[float]:
    desired_direction = "bullish" if signal == "buy" else "bearish"
    for pattern in patterns:
        if pattern.get("direction") != desired_direction:
            continue
        target_price = _safe_float(pattern.get("targetPrice"), 0.0)
        if target_price > 0:
            return target_price
    return None


def _trade_level_config(timeframe: str, trade_style: str, regime: str) -> Dict[str, object]:
    if trade_style == "scalp":
        if timeframe == "1m":
            config: Dict[str, object] = {
                "entry_width_mult": 0.18,
                "stop_mult": 0.75,
                "tp_multipliers": (1.0, 1.6, 2.2),
            }
        elif timeframe == "5m":
            config = {
                "entry_width_mult": 0.24,
                "stop_mult": 0.90,
                "tp_multipliers": (1.05, 1.75, 2.5),
            }
        else:
            config = {
                "entry_width_mult": 0.32,
                "stop_mult": 1.05,
                "tp_multipliers": (1.10, 1.90, 2.80),
            }
    else:
        config = {
            "entry_width_mult": 0.42,
            "stop_mult": 1.35,
            "tp_multipliers": (1.15, 2.0, 3.0),
        }

    if regime == "volatile":
        config["entry_width_mult"] = float(config["entry_width_mult"]) * 1.10
        config["stop_mult"] = float(config["stop_mult"]) * 1.15
        config["tp_multipliers"] = tuple(float(multiplier) * 1.10 for multiplier in config["tp_multipliers"])  # type: ignore[index]
    elif regime == "ranging":
        config["stop_mult"] = float(config["stop_mult"]) * 0.95
        config["tp_multipliers"] = tuple(float(multiplier) * 0.90 for multiplier in config["tp_multipliers"])  # type: ignore[index]

    return config


def _build_trade_levels(
    df: pd.DataFrame,
    signal: str,
    current_price: float,
    atr: float,
    timeframe: str,
    trade_style: str,
    regime: str,
    patterns: List[dict],
    ema20: float,
    bb_middle: float,
) -> Dict[str, float]:
    effective_atr = _effective_atr(current_price, atr, timeframe, trade_style)
    structure = _recent_structure_levels(df, trade_style)
    config = _trade_level_config(timeframe, trade_style, regime)
    entry_width_mult = float(config["entry_width_mult"])
    stop_mult = float(config["stop_mult"])
    tp1_mult, tp2_mult, tp3_mult = tuple(float(multiplier) for multiplier in config["tp_multipliers"])  # type: ignore[index]
    structure_buffer = effective_atr * (0.18 if trade_style == "scalp" else 0.25)
    min_entry_width = effective_atr * 0.12
    pattern_target = _aligned_pattern_target(patterns, signal)
    structure_conflict = 0.0

    if signal == "buy":
        pullback_candidates = [
            current_price - (entry_width_mult * effective_atr),
            min(_safe_float(ema20, current_price), current_price),
            min(_safe_float(bb_middle, current_price), current_price),
        ]
        preferred_entry = max(structure["support"] + structure_buffer, max(pullback_candidates))
        entry_min = min(preferred_entry, current_price)
        entry_max = current_price
        if (entry_max - entry_min) < min_entry_width:
            entry_min = current_price - min_entry_width

        structure_stop = min(structure["support"], structure["swing_low"]) - structure_buffer
        volatility_stop = current_price - (stop_mult * effective_atr)
        stop_loss = min(structure_stop, volatility_stop)
        if stop_loss >= entry_min:
            stop_loss = entry_min - (stop_mult * effective_atr)

        risk_distance = max(current_price - stop_loss, effective_atr * 0.55)
        room_to_resistance = max(0.0, structure["resistance"] - current_price)
        if 0 < room_to_resistance < risk_distance * 1.10 and pattern_target is None:
            structure_conflict = 1.0

        take_profit1 = current_price + (risk_distance * tp1_mult)
        if structure["resistance"] > current_price:
            take_profit1 = min(take_profit1, structure["resistance"])
        take_profit2 = current_price + (risk_distance * tp2_mult)
        take_profit3 = current_price + (risk_distance * tp3_mult)
        if pattern_target and pattern_target > current_price:
            take_profit2 = max(take_profit2, min(pattern_target, current_price + (risk_distance * 3.20)))
            take_profit3 = max(take_profit3, pattern_target)
        take_profit2 = max(take_profit2, take_profit1 + (risk_distance * 0.45))
        take_profit3 = max(take_profit3, take_profit2 + (risk_distance * 0.65))
    elif signal == "sell":
        pullback_candidates = [
            current_price + (entry_width_mult * effective_atr),
            max(_safe_float(ema20, current_price), current_price),
            max(_safe_float(bb_middle, current_price), current_price),
        ]
        preferred_entry = min(structure["resistance"] - structure_buffer, min(pullback_candidates))
        entry_min = current_price
        entry_max = max(preferred_entry, current_price)
        if (entry_max - entry_min) < min_entry_width:
            entry_max = current_price + min_entry_width

        structure_stop = max(structure["resistance"], structure["swing_high"]) + structure_buffer
        volatility_stop = current_price + (stop_mult * effective_atr)
        stop_loss = max(structure_stop, volatility_stop)
        if stop_loss <= entry_max:
            stop_loss = entry_max + (stop_mult * effective_atr)

        risk_distance = max(stop_loss - current_price, effective_atr * 0.55)
        room_to_support = max(0.0, current_price - structure["support"])
        if 0 < room_to_support < risk_distance * 1.10 and pattern_target is None:
            structure_conflict = 1.0

        take_profit1 = current_price - (risk_distance * tp1_mult)
        if structure["support"] < current_price:
            take_profit1 = max(take_profit1, structure["support"])
        take_profit2 = current_price - (risk_distance * tp2_mult)
        take_profit3 = current_price - (risk_distance * tp3_mult)
        if pattern_target and pattern_target < current_price:
            take_profit2 = min(take_profit2, max(pattern_target, current_price - (risk_distance * 3.20)))
            take_profit3 = min(take_profit3, pattern_target)
        take_profit2 = min(take_profit2, take_profit1 - (risk_distance * 0.45))
        take_profit3 = min(take_profit3, take_profit2 - (risk_distance * 0.65))
    else:
        entry_span = effective_atr * 0.15
        entry_min = current_price - entry_span
        entry_max = current_price + entry_span
        stop_loss = current_price - effective_atr
        take_profit1 = current_price + effective_atr
        take_profit2 = current_price + (effective_atr * 1.5)
        take_profit3 = current_price + (effective_atr * 2.0)
        risk_distance = effective_atr

    return {
        "entry_min": float(entry_min),
        "entry_max": float(entry_max),
        "stop_loss": float(stop_loss),
        "take_profit1": float(take_profit1),
        "take_profit2": float(take_profit2),
        "take_profit3": float(take_profit3),
        "risk_distance": float(risk_distance),
        "effective_atr": float(effective_atr),
        "support": float(structure["support"]),
        "resistance": float(structure["resistance"]),
        "structure_conflict": float(structure_conflict),
    }


def _apply_anchor_history_adjustment(
    signal: str,
    confidence: int,
    reason: str,
    anchor_summary: Dict[str, object],
) -> Tuple[str, int, str]:
    if signal == "hold":
        return signal, confidence, reason

    sample_size = int(anchor_summary.get("sampleSize") or 0)
    if sample_size < 5:
        return signal, confidence, reason

    tp_hit_rate = float(anchor_summary.get("tpHitRate") or 0.0)
    sl_hit_rate = float(anchor_summary.get("slHitRate") or 0.0)
    expired_rate = float(anchor_summary.get("expiredRate") or 0.0)
    edge_score = tp_hit_rate - sl_hit_rate

    adjusted_confidence = confidence
    adjusted_reason = reason

    if edge_score < -0.10 or sl_hit_rate >= 0.55:
        adjusted_confidence = max(44, confidence - 18)
        adjusted_reason = f"{reason}, recent anchor history shows too many stop-outs"
        if adjusted_confidence <= 55:
            return "hold", min(adjusted_confidence, 54), adjusted_reason
        return signal, adjusted_confidence, adjusted_reason

    if edge_score < 0.05 or expired_rate >= 0.45:
        adjusted_confidence = max(46, confidence - 8)
        adjusted_reason = f"{reason}, recent anchor history is only marginally favorable"

    return signal, adjusted_confidence, adjusted_reason


def fetch_data_yf(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Backward-compatible yfinance-style fetch via the unified service."""
    return get_ohlcv(symbol, timeframe, trade_style="swing")


def _get_sentiment_score(
    symbol: str,
    provider: Optional[SentimentScoreProvider] = None,
) -> Optional[float]:
    if provider is not None:
        return provider(symbol)

    try:
        from trading_bot.sentiment.analyzer import SentimentAnalyzer
        _analyzer = SentimentAnalyzer()
        import asyncio as _aio
        try:
            _loop = _aio.get_running_loop()
        except RuntimeError:
            _loop = None
        if _loop and _loop.is_running():
            # We're in a sync context called from async; use thread to avoid blocking.
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                _sentiment_data = pool.submit(lambda: _aio.run(_analyzer.get_sentiment(symbol))).result(timeout=2)
        else:
            _sentiment_data = _aio.run(_analyzer.get_sentiment(symbol))
        return _sentiment_data.get("score")  # -1..1 range
    except Exception:
        return None


def analyze_symbol(
    symbol: str,
    timeframe: str,
    trade_style: str = "swing",
    record_no_trade_reason: bool = False,
) -> Optional[dict]:
    """Perform technical analysis on a symbol."""
    df, metadata = get_shared_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
    return build_market_analysis(
        symbol,
        timeframe,
        trade_style,
        df,
        metadata,
        record_no_trade_reason=record_no_trade_reason,
    )


def build_market_analysis(
    symbol: str,
    timeframe: str,
    trade_style: str,
    df: Optional[pd.DataFrame],
    metadata: Optional[dict] = None,
    *,
    record_no_trade_reason: bool = False,
    context_bias_provider: Optional[ContextBiasProvider] = None,
    sentiment_score_provider: Optional[SentimentScoreProvider] = None,
    anchor_performance_provider: Optional[AnchorPerformanceProvider] = None,
) -> Optional[dict]:
    """Build the market-analysis payload from candle data and analysis seams."""
    if df is None or len(df) < 30:
        return None
    metadata = dict(metadata or {})
    feature_started = time.perf_counter()

    # Get current values
    current_price = df["close"].iloc[-1]
    prev_price = df["close"].iloc[-2] if len(df) > 1 else current_price
    price_change = current_price - prev_price
    price_change_pct = (price_change / prev_price) * 100 if prev_price != 0 else 0

    # Calculate indicators
    rsi = calculate_rsi(df["close"], 14)
    macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
    ema20 = calculate_ema(df["close"], 20)
    ema50 = calculate_ema(df["close"], 50)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df["close"])
    atr = calculate_atr(df["high"], df["low"], df["close"])

    # Volume analysis
    current_volume = df["volume"].iloc[-1]
    avg_volume = df["volume"].rolling(window=20).mean().iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0

    thresholds = _indicator_thresholds(timeframe, trade_style)
    bias_provider = context_bias_provider or _get_context_bias
    context_bias, context_strength = bias_provider(symbol, timeframe, trade_style)
    quality_flags = list(metadata.get("qualityFlags", []))
    quality_penalty = _quality_penalty(quality_flags, timeframe, trade_style)

    # Determine indicator signals
    indicators = []
    bullish_score = 0.0
    bearish_score = 0.0
    bullish_count = 0
    bearish_count = 0

    # RSI signal
    if rsi <= thresholds["rsi_buy"]:
        rsi_signal = "bullish"
        bullish_score += 1.15
        bullish_count += 1
    elif rsi >= thresholds["rsi_sell"]:
        rsi_signal = "bearish"
        bearish_score += 1.15
        bearish_count += 1
    else:
        rsi_signal = "neutral"
    indicators.append({
        "name": "RSI(14)",
        "value": f"{rsi:.1f}",
        "signal": rsi_signal
    })

    # MACD signal
    if macd_hist > 0 and macd_line > macd_signal:
        macd_signal_str = "bullish"
        bullish_score += 1.25
        bullish_count += 1
    elif macd_hist < 0 and macd_line < macd_signal:
        macd_signal_str = "bearish"
        bearish_score += 1.25
        bearish_count += 1
    else:
        macd_signal_str = "neutral"
    indicators.append({
        "name": "MACD",
        "value": "Bullish Cross" if macd_signal_str == "bullish" else ("Bearish Cross" if macd_signal_str == "bearish" else "Neutral"),
        "signal": macd_signal_str
    })

    # EMA signal
    ema_signal = _trend_signal(current_price, ema20, ema50)
    if ema_signal == "bullish":
        bullish_score += 1.05
        bullish_count += 1
    elif ema_signal == "bearish":
        bearish_score += 1.05
        bearish_count += 1
    decimals = get_decimal_places(current_price)
    indicators.append({
        "name": "EMA(20)",
        "value": f"{ema20:.{decimals}f}",
        "signal": ema_signal
    })

    # Bollinger Bands signal
    bb_pct = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
    if bb_pct <= thresholds["bb_buy"]:
        bb_signal = "bullish"
        bullish_score += 0.95
        bullish_count += 1
    elif bb_pct >= thresholds["bb_sell"]:
        bb_signal = "bearish"
        bearish_score += 0.95
        bearish_count += 1
    else:
        bb_signal = "neutral"
    indicators.append({
        "name": "BB Position",
        "value": "Lower Band" if bb_pct < 0.2 else ("Upper Band" if bb_pct > 0.8 else "Middle"),
        "signal": bb_signal
    })

    # Volume signal
    vol_signal, vol_value = _volume_signal(volume_ratio, price_change)
    if vol_signal == "bullish":
        bullish_score += 0.60
        bullish_count += 1
    elif vol_signal == "bearish":
        bearish_score += 0.60
        bearish_count += 1
    indicators.append({
        "name": "Volume",
        "value": vol_value,
        "signal": vol_signal
    })

    raw_patterns = detect_patterns(df)

    patterns = _select_patterns_for_signal(raw_patterns, "hold", context_bias)
    top_pattern = patterns[0] if patterns else None
    if top_pattern:
        pattern_boost = min(float(top_pattern["confidence"]) / 100.0, 0.9)
        if top_pattern["direction"] == "bullish":
            bullish_score += 0.65 * pattern_boost
        elif top_pattern["direction"] == "bearish":
            bearish_score += 0.65 * pattern_boost

    if context_bias == "bullish":
        bullish_score += 0.90
    elif context_bias == "bearish":
        bearish_score += 0.90

    total_directional = bullish_count + bearish_count
    directional_strength = abs(bullish_score - bearish_score)

    signal = "hold"
    confidence = 48
    if bullish_score >= bearish_score + thresholds["decision_threshold"]:
        signal = "buy"
    elif bearish_score >= bullish_score + thresholds["decision_threshold"]:
        signal = "sell"

    if signal != "hold":
        patterns = _select_patterns_for_signal(raw_patterns, signal, context_bias)
        top_pattern = patterns[0] if patterns else None
        winning_score = bullish_score if signal == "buy" else bearish_score
        opposing_score = bearish_score if signal == "buy" else bullish_score
        directional_ratio = winning_score / max(winning_score + opposing_score, 1e-9)
        base_conf = 45 + directional_ratio * 28 + min(directional_strength, 3.0) * 7
        if context_bias == ("bullish" if signal == "buy" else "bearish"):
            base_conf += 6
        elif context_bias in ("bullish", "bearish"):
            base_conf -= 12
        if top_pattern and ((signal == "buy" and top_pattern["direction"] == "bullish") or (signal == "sell" and top_pattern["direction"] == "bearish")):
            base_conf += min(float(top_pattern["confidence"]) / 20.0, 5.0)
        elif top_pattern:
            base_conf -= 10
        if total_directional <= 2:
            base_conf -= 8
        if directional_strength < 1.8:
            base_conf -= 6
        base_conf -= quality_penalty
        confidence = int(_clamp(base_conf, thresholds["min_directional_confidence"], 92))
        confidence = _cap_confidence_for_quality(
            signal,
            confidence,
            top_pattern,
            context_bias,
            context_strength,
        )

        if confidence < thresholds["min_directional_confidence"] + 2:
            signal = "hold"
            confidence = max(42, confidence - 4)
    else:
        patterns = _select_patterns_for_signal(raw_patterns, signal, context_bias)
        top_pattern = patterns[0] if patterns else None
        hold_conf = 52
        if directional_strength < 0.75:
            hold_conf += 4
        hold_conf -= quality_penalty // 2
        confidence = int(_clamp(hold_conf, 38, 62))

    if _should_force_hold_for_quality(symbol, timeframe, trade_style, quality_flags):
        signal = "hold"
        confidence = min(confidence, 52)
        patterns = []
        top_pattern = None

    # Generate reason text — only include reasons that AGREE with the final signal
    reasons = []
    if signal == "buy":
        if rsi < 30:
            reasons.append(f"RSI oversold at {rsi:.1f}")
        elif rsi < 45:
            reasons.append(f"RSI supportive at {rsi:.1f}")
        if macd_signal_str == "bullish":
            reasons.append("MACD bullish crossover")
        if bb_signal == "bullish":
            reasons.append("price bouncing off lower Bollinger Band")
        if ema_signal == "bullish":
            reasons.append("price above EMA(20)")
        if vol_signal == "bullish":
            reasons.append("strong volume confirmation")
        if context_bias == "bullish":
            reasons.append("higher timeframes aligned bullish")
    elif signal == "sell":
        if rsi > 70:
            reasons.append(f"RSI overbought at {rsi:.1f}")
        elif rsi > 55:
            reasons.append(f"RSI bearish at {rsi:.1f}")
        if macd_signal_str == "bearish":
            reasons.append("MACD bearish crossover")
        if bb_signal == "bearish":
            reasons.append("price near upper Bollinger Band")
        if ema_signal == "bearish":
            reasons.append("price below EMA(20)")
        if vol_signal == "bearish":
            reasons.append("weak volume")
        if context_bias == "bearish":
            reasons.append("higher timeframes aligned bearish")
    else:
        reasons.append("indicators are mixed")
        if context_bias in ("bullish", "bearish"):
            reasons.append("higher timeframe context lacks lower-timeframe confirmation")
        if quality_penalty > 0:
            reasons.append("data quality reduced conviction")
        if _should_force_hold_for_quality(symbol, timeframe, trade_style, quality_flags):
            reasons.append("directional signal suppressed due to degraded scalp data")

    reason = ", ".join(reasons) if reasons else "Mixed signals, no clear direction"

    regime = _classify_market_regime(
        df,
        float(current_price),
        float(ema20),
        float(ema50),
        float(macd_line),
        float(macd_hist),
        float(rsi),
        float(atr),
    )

    levels = _build_trade_levels(
        df,
        signal,
        float(current_price),
        float(atr),
        timeframe,
        trade_style,
        regime,
        patterns,
        float(ema20),
        float(bb_middle),
    )

    entry_min = levels["entry_min"]
    entry_max = levels["entry_max"]
    stop_loss = levels["stop_loss"]
    take_profit1 = levels["take_profit1"]
    take_profit2 = levels["take_profit2"]
    take_profit3 = levels["take_profit3"]
    risk_distance = levels["risk_distance"]
    reward_distance = abs(take_profit2 - current_price)
    risk_reward = round(reward_distance / risk_distance, 2) if risk_distance > 0 else 0.0

    if signal != "hold" and levels["structure_conflict"] > 0:
        confidence = max(45, confidence - 10)
        reason = f"{reason}, nearby structure limits target runway"

    if signal == "buy" and regime == "trending_down":
        confidence = max(42, confidence - 8)
        reason = f"{reason}, broader regime is still trending down"
    elif signal == "sell" and regime == "trending_up":
        confidence = max(42, confidence - 8)
        reason = f"{reason}, broader regime is still trending up"

    if signal != "hold" and risk_reward < 1.35:
        signal = "hold"
        confidence = min(confidence, 54)
        reason = f"{reason}, reward-to-risk is too compressed for a clean setup"
        levels = _build_trade_levels(
            df,
            signal,
            float(current_price),
            float(atr),
            timeframe,
            trade_style,
            regime,
            patterns,
            float(ema20),
            float(bb_middle),
        )
        entry_min = levels["entry_min"]
        entry_max = levels["entry_max"]
        stop_loss = levels["stop_loss"]
        take_profit1 = levels["take_profit1"]
        take_profit2 = levels["take_profit2"]
        take_profit3 = levels["take_profit3"]
        risk_distance = levels["risk_distance"]
        reward_distance = abs(take_profit2 - current_price)
        risk_reward = round(reward_distance / risk_distance, 2) if risk_distance > 0 else 0.0

    if quality_penalty >= 20 and signal != "hold":
        signal = "hold"
        confidence = min(confidence, 52)
        reason = "data quality is degraded; directional signal suppressed"
    bot_metrics.record_latency(
        "prediction.feature_generation",
        (time.perf_counter() - feature_started) * 1000,
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )

    # Round with appropriate precision based on price magnitude
    decimals = get_decimal_places(current_price)

    entry_min_rounded = round(entry_min, decimals)
    entry_max_rounded = round(entry_max, decimals)

    # Ensure entry range doesn't collapse after rounding
    if entry_min_rounded == entry_max_rounded:
        nudge = 10 ** (-decimals)
        entry_min_rounded = round(entry_min_rounded - nudge, decimals)
        entry_max_rounded = round(entry_max_rounded + nudge, decimals)

    # Ensure stop_loss doesn't equal entry price after rounding
    stop_rounded = round(stop_loss, decimals)
    current_rounded = round(current_price, decimals)
    if stop_rounded == entry_min_rounded or stop_rounded == current_rounded:
        stop_rounded = round(stop_loss - (2 * (10 ** (-decimals))), decimals)

    # Fetch sentiment for AI score (non-blocking, default to neutral on failure)
    try:
        _sentiment_score = _get_sentiment_score(symbol, sentiment_score_provider)
    except Exception:
        _sentiment_score = None

    with bot_metrics.timer(
        "prediction.scoring",
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    ):
        ai_score = compute_ai_score(
            signal, confidence, indicators, regime, patterns,
            sentiment_score=_sentiment_score,
            volume_ratio=volume_ratio,
        )
        pattern_accuracy = patterns[0]["successRate"] if patterns else None
        direction = signal.upper() if signal != "hold" else None
        if anchor_performance_provider is None:
            anchor_performance = repo.get_signal_outcome_summary(
                symbol=symbol,
                timeframe=timeframe,
                direction=direction,
                limit=100,
            )
        else:
            anchor_performance = anchor_performance_provider(symbol, timeframe, direction)
        anchor_performance = dict(anchor_performance or {})
        signal, confidence, reason = _apply_anchor_history_adjustment(
            signal,
            confidence,
            reason,
            anchor_performance,
        )
        ai_score = compute_ai_score(
            signal, confidence, indicators, regime, patterns,
            sentiment_score=_sentiment_score,
            volume_ratio=volume_ratio,
        )
    if signal == "hold" and record_no_trade_reason:
        bot_metrics.increment_counter(
            "no_trade_reason",
            label=classify_no_trade_reason(reason),
            context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
        )

    return {
        "currentPrice": current_rounded,
        "priceChange": round(price_change, decimals),
        "priceChangePercent": round(price_change_pct, 2),
        "signal": signal,
        "confidence": confidence,
        "reason": reason,
        "entryRange": {"min": entry_min_rounded, "max": entry_max_rounded},
        "stopLoss": stop_rounded,
        "takeProfit1": round(take_profit1, decimals),
        "takeProfit2": round(take_profit2, decimals),
        "takeProfit3": round(take_profit3, decimals),
        "riskReward": risk_reward,
        "timeframe": timeframe,
        "marketRegime": regime,
        "indicators": indicators,
        "patterns": patterns,
        "patternAccuracy": pattern_accuracy,
        "aiScore": ai_score,
        "atr": round(atr, decimals + 1),
        "anchorPerformance": anchor_performance,
        "anchorModel": {
            "effectiveAtr": round(levels["effective_atr"], decimals + 1),
            "support": round(levels["support"], decimals),
            "resistance": round(levels["resistance"], decimals),
            "riskDistance": round(levels["risk_distance"], decimals),
            "structureConflict": bool(levels["structure_conflict"]),
        },
        "trade_style": trade_style,
        "higherTimeframeBias": {
            "direction": context_bias,
            "strength": context_strength,
        },
        "data_fetched_at": time.time(),
        "is_mock": False,
        "source": "live",
        "sourceMetadata": metadata,
    }


def analyze_multitimeframe(
    symbol: str,
    primary_timeframe: str,
    trade_style: str = "swing",
) -> List[dict]:
    """Analyze symbol across multiple timeframes."""
    timeframes = ["1d", "4h", "1h", "15m", "5m"]
    results = []

    for tf in timeframes:
        context_trade_style = resolve_context_trade_style(symbol, tf, trade_style)
        analysis = analyze_symbol(symbol, tf, trade_style=context_trade_style)
        if analysis:
            signal_map = {"buy": "BUY", "sell": "SELL", "hold": "HOLD"}
            results.append({
                "tf": tf.upper(),
                "signal": signal_map.get(analysis["signal"], "HOLD"),
                "alignment": analysis["confidence"]
            })
        else:
            results.append({
                "tf": tf.upper(),
                "signal": "HOLD",
                "alignment": 50
            })

    return results


def calculate_sharpe_approximation(df: pd.DataFrame) -> float:
    """Calculate approximate Sharpe ratio from price data."""
    returns = df["close"].pct_change().dropna()
    if len(returns) < 10:
        return 1.0

    mean_return = returns.mean()
    std_return = returns.std()

    if std_return == 0:
        return 1.0

    # Annualized Sharpe approximation (assuming 252 trading days)
    sharpe = (mean_return / std_return) * np.sqrt(252)
    return round(sharpe, 2)


def get_volatility_level(atr: float, price: float) -> str:
    """Determine volatility level based on ATR percentage."""
    if price == 0:
        return "NORMAL"

    atr_pct = (atr / price) * 100

    if atr_pct < 0.5:
        return "LOW"
    elif atr_pct < 1.5:
        return "NORMAL"
    elif atr_pct < 3.0:
        return "HIGH"
    else:
        return "EXTREME"


def _safe_float(value: Optional[Union[float, int]], default: float = 0.0) -> float:
    """Return a finite float or a default."""
    if value is None:
        return default
    try:
        converted = float(value)
        if math.isnan(converted) or math.isinf(converted):
            return default
        return converted
    except (TypeError, ValueError):
        return default


def _clamp(value: float, minimum: float, maximum: float) -> float:
    """Clamp a float into the provided range."""
    return max(minimum, min(maximum, value))


def detect_patterns(df: pd.DataFrame) -> List[dict]:
    """Detect a small set of rule-based patterns for retail traders."""
    if df is None or len(df) < 30:
        return []

    recent = df.tail(60).copy()
    closes = recent["close"]
    highs = recent["high"]
    lows = recent["low"]
    volumes = recent["volume"]

    current_price = _safe_float(closes.iloc[-1], 0.0)
    if current_price <= 0:
        return []

    ema9 = closes.ewm(span=9, adjust=False).mean()
    slope = _safe_float((ema9.iloc[-1] - ema9.iloc[-6]) / max(abs(current_price), 1e-9), 0.0)
    resistance = _safe_float(highs.tail(20).max(), current_price)
    support = _safe_float(lows.tail(20).min(), current_price)
    avg_volume_raw = volumes.tail(20).mean()
    avg_volume = _safe_float(avg_volume_raw, 1.0)
    current_volume = _safe_float(volumes.iloc[-1], 0.0)
    if not np.isfinite(avg_volume) or avg_volume <= 0:
        volume_ratio = 1.0
    else:
        volume_ratio = _safe_float(current_volume / avg_volume, 1.0)
    narrow_range = _safe_float(highs.tail(10).max() - lows.tail(10).min(), 0.0)
    broad_range = _safe_float(highs.tail(30).max() - lows.tail(30).min(), 1.0)
    contraction_ratio = narrow_range / broad_range if broad_range > 0 else 1.0
    range_pct = _safe_float((highs.max() - lows.min()) / current_price, 0.0)

    pivot_highs = highs[(highs.shift(1) < highs) & (highs.shift(-1) < highs)].tail(5).tolist()
    pivot_lows = lows[(lows.shift(1) > lows) & (lows.shift(-1) > lows)].tail(5).tolist()

    patterns: List[dict] = []
    decimals = get_decimal_places(current_price)

    if len(pivot_highs) >= 2 and abs(pivot_highs[-1] - pivot_highs[-2]) / current_price < 0.01:
        confidence = int(_clamp(62 + volume_ratio * 10 + (1 - contraction_ratio) * 20, 55, 89))
        patterns.append({
            "name": "Resistance Breakout",
            "type": "breakout",
            "direction": "bullish",
            "confidence": confidence,
            "targetPrice": round(current_price + (current_price - support), decimals),
            "successRate": int(_clamp(confidence - 5, 50, 84)),
            "description": "Price is compressing under resistance with improving volume.",
        })

    if len(pivot_lows) >= 2 and abs(pivot_lows[-1] - pivot_lows[-2]) / current_price < 0.01 and slope < -0.0005:
        confidence = int(_clamp(60 + abs(slope) * 10000 + volume_ratio * 8, 54, 86))
        patterns.append({
            "name": "Support Breakdown",
            "type": "breakdown",
            "direction": "bearish",
            "confidence": confidence,
            "targetPrice": round(current_price - (resistance - current_price), decimals),
            "successRate": int(_clamp(confidence - 4, 50, 82)),
            "description": "Lower highs with repeated support tests suggest downside continuation.",
        })

    if slope > 0.0007 and contraction_ratio < 0.55 and volume_ratio > 0.9:
        confidence = int(_clamp(64 + slope * 12000 + (1 - contraction_ratio) * 18, 58, 88))
        patterns.append({
            "name": "Bull Flag",
            "type": "continuation",
            "direction": "bullish",
            "confidence": confidence,
            "targetPrice": round(current_price + range_pct * current_price * 0.8, decimals),
            "successRate": int(_clamp(confidence - 3, 52, 85)),
            "description": "Uptrend followed by controlled pullback and volatility contraction.",
        })

    if slope < -0.0007 and contraction_ratio < 0.55 and volume_ratio > 0.9:
        confidence = int(_clamp(64 + abs(slope) * 12000 + (1 - contraction_ratio) * 18, 58, 88))
        patterns.append({
            "name": "Bear Flag",
            "type": "continuation",
            "direction": "bearish",
            "confidence": confidence,
            "targetPrice": round(current_price - range_pct * current_price * 0.8, decimals),
            "successRate": int(_clamp(confidence - 3, 52, 85)),
            "description": "Downtrend followed by weak rebound and compression.",
        })

    if len(pivot_highs) >= 3:
        left, head, right = pivot_highs[-3], pivot_highs[-2], pivot_highs[-1]
        shoulder_symmetry = abs(left - right) / current_price
        head_margin = (head - max(left, right)) / current_price
        if shoulder_symmetry < 0.012 and head_margin > 0.006:
            confidence = int(_clamp(66 + head_margin * 2500 - shoulder_symmetry * 800, 60, 87))
            patterns.append({
                "name": "Head and Shoulders",
                "type": "reversal",
                "direction": "bearish",
                "confidence": confidence,
                "targetPrice": round(current_price - (head - support), decimals),
                "successRate": int(_clamp(confidence - 2, 55, 84)),
                "description": "Three-peak reversal structure with weakening momentum.",
            })

    if len(pivot_lows) >= 3:
        left, head, right = pivot_lows[-3], pivot_lows[-2], pivot_lows[-1]
        shoulder_symmetry = abs(left - right) / current_price
        head_margin = (min(left, right) - head) / current_price
        if shoulder_symmetry < 0.012 and head_margin > 0.006:
            confidence = int(_clamp(66 + head_margin * 2500 - shoulder_symmetry * 800, 60, 87))
            patterns.append({
                "name": "Inverse Head and Shoulders",
                "type": "reversal",
                "direction": "bullish",
                "confidence": confidence,
                "targetPrice": round(current_price + (resistance - head), decimals),
                "successRate": int(_clamp(confidence - 2, 55, 84)),
                "description": "Rounded reversal structure with higher-probability upside breakout.",
            })

    patterns.sort(key=lambda pattern: pattern["confidence"], reverse=True)
    return patterns[:3]


def compute_ai_score(
    signal: str,
    confidence: float,
    indicators: List[dict],
    market_regime: str,
    patterns: List[dict],
    sentiment_score: Optional[float] = None,
    volume_ratio: Optional[float] = None,
) -> dict:
    """Compute a 0-100 AI score with factor breakdown.

    Weights: confidence 30%, indicators 25%, regime 15%, patterns 15%,
    sentiment 10%, volume 5%.
    """
    directional_indicators = [indicator for indicator in indicators if indicator["signal"] != "neutral"]
    bullish = sum(1 for indicator in directional_indicators if indicator["signal"] == "bullish")
    bearish = sum(1 for indicator in directional_indicators if indicator["signal"] == "bearish")
    total = max(1, len(directional_indicators))

    if signal == "hold":
        consensus_balance = 1.0 - (abs(bullish - bearish) / total if total else 0.0)
        indicator_score = _clamp(consensus_balance * 100, 35, 100)
        confidence_score = _clamp(_safe_float(confidence, 50.0), 0, 65)
    else:
        indicator_score = max(bullish, bearish) / total * 100
        confidence_score = _clamp(_safe_float(confidence, 50.0), 0, 100)

    regime_map = {
        "trending_up": 82 if signal == "buy" else (68 if signal == "hold" else 46),
        "trending_down": 82 if signal == "sell" else (68 if signal == "hold" else 46),
        "ranging": 70 if signal == "hold" else 58,
        "volatile": 45 if signal == "hold" else 52,
    }
    regime_score = regime_map.get(market_regime, 55)

    top_pattern = patterns[0] if patterns else None
    if signal == "hold":
        if top_pattern:
            pattern_score = max(30, 62 - min(float(top_pattern["confidence"]) * 0.2, 22))
        else:
            pattern_score = 60
    else:
        pattern_score = top_pattern["confidence"] if top_pattern else 50
        if top_pattern:
            if (signal == "buy" and top_pattern["direction"] != "bullish") or (signal == "sell" and top_pattern["direction"] != "bearish"):
                pattern_score = max(35, pattern_score - 18)

    # Sentiment factor: convert -1..1 score to 0-100 scale; default 50 (neutral)
    if sentiment_score is not None:
        sent_normalized = _clamp((sentiment_score + 1) / 2 * 100, 0, 100)
    else:
        sent_normalized = 50.0

    # Volume momentum factor: ratio vs 20-bar MA mapped to 0-100
    if volume_ratio is not None:
        vol_momentum = _clamp(volume_ratio * 50, 0, 100)
    else:
        vol_momentum = 50.0

    if signal == "hold":
        sent_normalized = 50.0 + (sent_normalized - 50.0) * 0.35
        vol_momentum = 50.0 + (vol_momentum - 50.0) * 0.25

    total_score = round(
        confidence_score * 0.30 +
        indicator_score * 0.25 +
        regime_score * 0.15 +
        pattern_score * 0.15 +
        sent_normalized * 0.10 +
        vol_momentum * 0.05
    )

    if total_score >= 80:
        label = "Strong"
    elif total_score >= 65:
        label = "Favorable"
    elif total_score >= 50:
        label = "Neutral"
    else:
        label = "Cautious"

    if signal == "hold" and label == "Strong":
        label = "Neutral"
    elif signal == "hold" and label == "Favorable":
        label = "Neutral"

    return {
        "value": int(_clamp(total_score, 0, 100)),
        "label": label,
        "factors": {
            "modelConfidence": round(confidence_score, 1),
            "indicatorConsensus": round(indicator_score, 1),
            "marketRegimeFit": round(regime_score, 1),
            "patternStrength": round(pattern_score, 1),
            "sentimentScore": round(sent_normalized, 1),
            "volumeMomentum": round(vol_momentum, 1),
        },
    }
