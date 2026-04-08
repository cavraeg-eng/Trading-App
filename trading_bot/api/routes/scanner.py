"""Scanner routes for the trading bot API."""

from typing import List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
from fastapi import APIRouter

from trading_bot.api.models import ScanResult, ScannerConfig
from trading_bot.api.routes.market import (
    fetch_data_yf, calculate_rsi, calculate_macd,
    calculate_ema, calculate_bollinger_bands, calculate_atr
)
from trading_bot.config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "XAU/USD", "BTC/USD", "US500", "EUR/GBP"
]

# Map frontend/preset indicator names to internal indicator_map keys
INDICATOR_ALIASES = {
    "BB": "BB",              # special: maps to bb_position logic
    "Bollinger Bands": "BB", # frontend builder name
    "Stochastic": None,      # not implemented yet
    "OBV": None,             # not implemented yet
    "Williams %R": None,     # not implemented yet
}


def safe_float(val, default=0.0) -> float:
    """Convert a value to a finite Python float, replacing NaN/Inf with default."""
    try:
        v = float(val)
        return v if np.isfinite(v) else default
    except (TypeError, ValueError):
        return default


@router.get("/presets")
async def get_presets():
    """Get built-in scanner presets."""
    presets = [
        {
            "id": "trendwave",
            "name": "TrendWave",
            "description": "Identifies strong trending pairs using EMA crossovers and ADX",
            "icon": "trending-up",
            "conditions": [
                {"indicator": "EMA", "operator": "crosses_above", "value": 50},
                {"indicator": "RSI", "operator": ">", "value": 50}
            ]
        },
        {
            "id": "momentum_pro",
            "name": "MomentumPro",
            "description": "Finds pairs with strong momentum using RSI and MACD",
            "icon": "zap",
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 30},
                {"indicator": "MACD", "operator": "crosses_above", "value": 0}
            ]
        },
        {
            "id": "volatility_break",
            "name": "VolatilityBreak",
            "description": "Detects volatility breakouts using Bollinger Bands",
            "icon": "activity",
            "conditions": [
                {"indicator": "BB", "operator": ">", "value": 0},
                {"indicator": "ATR", "operator": ">", "value": 1.5}
            ]
        },
        {
            "id": "volume_spike",
            "name": "VolumeSpike",
            "description": "Catches unusual volume activity",
            "icon": "bar-chart",
            "conditions": [
                {"indicator": "Volume", "operator": ">", "value": 2.0}
            ]
        },
        {
            "id": "mean_reversion",
            "name": "MeanReversion",
            "description": "Finds oversold pairs ready to bounce",
            "icon": "refresh-cw",
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 25},
                {"indicator": "BB", "operator": "<", "value": -1}
            ]
        },
    ]
    return {"presets": presets}


def _get_indicator_value_at(indicator_name: str, data: pd.DataFrame, offset: int) -> float:
    """Get an indicator value at a specific offset from the end (-1 = last, -2 = prev)."""
    try:
        if len(data) < abs(offset):
            return 0.0

        close = data["close"]
        if indicator_name == "RSI":
            series = close.diff()
            gain = (series.where(series > 0, 0)).rolling(window=14).mean()
            loss = (-series.where(series < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            return safe_float(rsi.iloc[offset])
        elif indicator_name == "MACD":
            ema_fast = close.ewm(span=12, adjust=False).mean()
            ema_slow = close.ewm(span=26, adjust=False).mean()
            return safe_float((ema_fast - ema_slow).iloc[offset])
        elif indicator_name == "MACD Signal":
            ema_fast = close.ewm(span=12, adjust=False).mean()
            ema_slow = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            return safe_float(macd_line.ewm(span=9, adjust=False).mean().iloc[offset])
        elif indicator_name == "MACD Histogram":
            ema_fast = close.ewm(span=12, adjust=False).mean()
            ema_slow = close.ewm(span=26, adjust=False).mean()
            macd_line = ema_fast - ema_slow
            signal_line = macd_line.ewm(span=9, adjust=False).mean()
            return safe_float((macd_line - signal_line).iloc[offset])
        elif indicator_name == "EMA":
            return safe_float(close.ewm(span=20, adjust=False).mean().iloc[offset])
        elif indicator_name == "Price":
            return safe_float(close.iloc[offset])
        elif indicator_name in ("BB", "BB Upper", "BB Middle", "BB Lower"):
            sma = close.rolling(window=20).mean()
            std = close.rolling(window=20).std()
            upper = sma + 2.0 * std
            lower = sma - 2.0 * std
            if indicator_name == "BB Upper":
                return safe_float(upper.iloc[offset])
            elif indicator_name == "BB Lower":
                return safe_float(lower.iloc[offset])
            elif indicator_name == "BB":
                # BB position: (price - lower) / (upper - lower) scaled to -1..1
                u = safe_float(upper.iloc[offset])
                l = safe_float(lower.iloc[offset])
                p = safe_float(close.iloc[offset])
                band_width = u - l
                if band_width > 0:
                    return (p - l) / band_width * 2.0 - 1.0  # -1 to 1
                return 0.0
            else:
                return safe_float(sma.iloc[offset])
        elif indicator_name == "ATR":
            high_low = data["high"] - data["low"]
            high_close = np.abs(data["high"] - data["close"].shift())
            low_close = np.abs(data["low"] - data["close"].shift())
            tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
            return safe_float(tr.rolling(window=14).mean().iloc[offset])
        elif indicator_name == "Volume":
            vol = data["volume"]
            avg = vol.rolling(20).mean()
            avg_val = safe_float(avg.iloc[offset])
            return safe_float(vol.iloc[offset] / avg_val) if avg_val > 0 else 1.0
    except Exception:
        return 0.0
    return 0.0


def _resolve_indicator_name(name: str) -> str:
    """Resolve frontend/preset indicator names to internal names."""
    if name in INDICATOR_ALIASES:
        resolved = INDICATOR_ALIASES[name]
        return resolved if resolved is not None else name
    return name


def evaluate_single_pair(symbol: str, conditions: list, logic: str) -> Optional[dict]:
    """Evaluate a single pair against scanner conditions using real indicator data."""
    try:
        data = fetch_data_yf(symbol, "1h")
        if data is None or len(data) < 30:
            return None

        # Calculate current indicator values using market.py functions
        rsi = safe_float(calculate_rsi(data["close"], 14))
        macd_vals = calculate_macd(data["close"])
        macd_line = safe_float(macd_vals[0])
        signal_line = safe_float(macd_vals[1])
        histogram = safe_float(macd_vals[2])
        ema20 = safe_float(calculate_ema(data["close"], 20))
        bb_vals = calculate_bollinger_bands(data["close"])
        upper_band = safe_float(bb_vals[0])
        middle_band = safe_float(bb_vals[1])
        lower_band = safe_float(bb_vals[2])
        atr = safe_float(calculate_atr(data["high"], data["low"], data["close"], 14))
        price = safe_float(data["close"].iloc[-1])

        # BB position: scaled -1 to 1 (below lower = -1, above upper = +1)
        band_width = upper_band - lower_band
        if band_width > 0:
            bb_position = (price - lower_band) / band_width * 2.0 - 1.0
        else:
            bb_position = 0.0

        # Volume ratio
        try:
            vol_avg = safe_float(data["volume"].rolling(20).mean().iloc[-1])
            vol_current = safe_float(data["volume"].iloc[-1])
            volume_ratio = vol_current / vol_avg if vol_avg > 0 else 1.0
        except Exception:
            volume_ratio = 1.0

        indicator_map = {
            "RSI": rsi,
            "MACD": macd_line,
            "MACD Signal": signal_line,
            "MACD Histogram": histogram,
            "EMA": ema20,
            "Price": price,
            "BB": bb_position,
            "BB Upper": upper_band,
            "BB Lower": lower_band,
            "BB Middle": middle_band,
            "ATR": atr,
            "Volume": volume_ratio,
        }

        # Evaluate conditions
        matched_count = 0
        matching_conditions = []
        total_count = len(conditions) if conditions else 1

        for cond in conditions:
            raw_name = cond.indicator
            ind_name = _resolve_indicator_name(raw_name)
            op = cond.operator
            threshold = cond.value

            current_val = indicator_map.get(ind_name)
            if current_val is None:
                # Indicator not supported — skip gracefully
                logger.debug(f"Scanner: unknown indicator '{raw_name}' for {symbol}, skipping")
                continue

            met = False
            try:
                if op == ">":
                    met = current_val > threshold
                elif op == "<":
                    met = current_val < threshold
                elif op == ">=":
                    met = current_val >= threshold
                elif op == "<=":
                    met = current_val <= threshold
                elif op == "=":
                    met = abs(current_val - threshold) < 0.01
                elif op == "between":
                    threshold2 = cond.value2 if cond.value2 is not None else threshold * 1.5
                    lo, hi = min(threshold, threshold2), max(threshold, threshold2)
                    met = lo <= current_val <= hi
                elif op == "crosses_above":
                    if len(data) >= 2:
                        prev_val = _get_indicator_value_at(ind_name, data, -2)
                        met = prev_val <= threshold and current_val > threshold
                elif op == "crosses_below":
                    if len(data) >= 2:
                        prev_val = _get_indicator_value_at(ind_name, data, -2)
                        met = prev_val >= threshold and current_val < threshold
            except Exception:
                met = False

            if met:
                matched_count += 1
                matching_conditions.append(f"{raw_name} {op} {threshold}")

        # Score calculation
        if total_count == 0:
            score = 0.0
        elif logic == "AND":
            score = 1.0 if matched_count == total_count else matched_count / total_count
        else:  # OR
            score = matched_count / total_count if total_count > 0 else 0.0

        # Determine signal based on RSI
        rsi_val = indicator_map.get("RSI", 50.0)
        if rsi_val < 40:
            signal = "BUY"
        elif rsi_val > 60:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        # Only return if at least one condition matched
        if matched_count == 0:
            return None

        # Build safe indicator_values dict — all native Python floats
        safe_indicators = {}
        for k, v in indicator_map.items():
            safe_indicators[k] = round(safe_float(v), 4)

        return {
            "symbol": symbol,
            "signal": signal,
            "score": round(safe_float(score), 4),
            "matching_conditions": matching_conditions,
            "indicator_values": safe_indicators,
        }

    except Exception as e:
        logger.warning(f"Scanner: failed to evaluate {symbol}: {e}")
        return None


def scan_symbols(config: ScannerConfig) -> tuple:
    """Scan symbols using real indicator evaluation with parallel execution."""
    pairs = config.pairs if config.pairs else DEFAULT_PAIRS
    logic = getattr(config, "logic", "AND") or "AND"
    conditions = config.conditions or []

    if not conditions:
        return [], len(pairs)

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(evaluate_single_pair, symbol, conditions, logic): symbol
            for symbol in pairs
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Scanner thread error for {futures[future]}: {e}")

    results.sort(key=lambda x: x["score"], reverse=True)
    return results, len(pairs)


@router.post("/scan")
async def run_scan(config: ScannerConfig):
    """Run a scan with the given configuration."""
    results, total_scanned = scan_symbols(config)
    return {
        "results": results,
        "total_scanned": total_scanned,
        "total_matches": len(results),
    }


@router.post("/save")
async def save_scanner(config: ScannerConfig):
    """Save a scanner configuration."""
    return {"status": "saved", "name": config.name}
