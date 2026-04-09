"""Market analysis routes using real data from yfinance."""

import asyncio
import math
import random
import threading
import time
import time as _time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import yfinance as yf
from fastapi import APIRouter, HTTPException, Query

from trading_bot.api.models import CandleData
from trading_bot.config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

# Simple in-memory cache with TTL
_cache: Dict[str, dict] = {}
_cache_timestamps: Dict[str, float] = {}
_cache_lock = threading.RLock()
CACHE_TTL_INTRADAY = 5  # Faster refresh for active intraday trading views
CACHE_TTL_DAILY = 300  # 300 seconds for daily timeframe

# Shared OHLCV data cache — single source of truth for all endpoints
_ohlcv_cache: Dict[str, dict] = {}  # key -> {"df": DataFrame, "timestamp": float}
_ohlcv_lock = threading.RLock()
OHLCV_CACHE_TTL = 5  # Keep intraday OHLCV responsive for dashboard signal panels

# Global semaphore to limit concurrent yfinance calls (prevents 429 rate-limit errors)
_yf_semaphore = asyncio.Semaphore(2)


async def _fetch_yf_with_retry(symbol: str, max_retries: int = 3, **kwargs) -> Optional[pd.DataFrame]:
    """Fetch data from yfinance with semaphore throttling and exponential backoff."""
    yf_symbol = map_symbol_to_yf(symbol)
    for attempt in range(max_retries):
        try:
            async with _yf_semaphore:
                ticker = await asyncio.to_thread(yf.Ticker, yf_symbol)
                df = await asyncio.to_thread(ticker.history, **kwargs)
                if df is not None and not df.empty:
                    # Rename columns to lowercase
                    df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                    required_cols = ["open", "high", "low", "close", "volume"]
                    for col in required_cols:
                        if col not in df.columns:
                            logger.error(f"Missing column {col} in data for {symbol}")
                            return None
                    return df
        except Exception as e:
            logger.warning(f"yfinance attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}")
            if attempt < max_retries - 1:
                await asyncio.sleep(2 ** attempt)  # 1s, 2s, 4s backoff
            else:
                logger.error(f"All {max_retries} yfinance attempts failed for {symbol}: {e}")
    return None


def _fetch_yf_with_retry_sync(symbol: str, max_retries: int = 3, **kwargs) -> Optional[pd.DataFrame]:
    """Synchronous wrapper: fetch data from yfinance with retries and backoff.

    Used by synchronous callers (e.g. get_shared_ohlcv) that cannot await.
    """
    yf_symbol = map_symbol_to_yf(symbol)
    for attempt in range(max_retries):
        try:
            ticker = yf.Ticker(yf_symbol)
            df = ticker.history(**kwargs)
            if df is not None and not df.empty:
                df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                required_cols = ["open", "high", "low", "close", "volume"]
                for col in required_cols:
                    if col not in df.columns:
                        logger.error(f"Missing column {col} in data for {symbol}")
                        return None
                return df
        except Exception as e:
            logger.warning(f"yfinance sync attempt {attempt + 1}/{max_retries} failed for {symbol}: {e}")
            if attempt < max_retries - 1:
                _time.sleep(2 ** attempt)
            else:
                logger.error(f"All {max_retries} sync yfinance attempts failed for {symbol}: {e}")
    return None


# Symbol mapping from our format to yfinance format
SYMBOL_MAPPING = {
    # ── Major Forex ──────────────────────────────────────────────
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CHF": "USDCHF=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "NZD/USD": "NZDUSD=X",
    # ── Minor / Cross Forex ──────────────────────────────────────
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "EUR/CHF": "EURCHF=X",
    "GBP/JPY": "GBPJPY=X",
    "GBP/CHF": "GBPCHF=X",
    "AUD/JPY": "AUDJPY=X",
    "AUD/NZD": "AUDNZD=X",
    "GBP/CAD": "GBPCAD=X",
    "NZD/JPY": "NZDJPY=X",
    "EUR/NZD": "EURNZD=X",
    "CAD/JPY": "CADJPY=X",
    "CHF/JPY": "CHFJPY=X",
    "EUR/AUD": "EURAUD=X",
    # ── Exotic Forex ─────────────────────────────────────────────
    "USD/MXN": "USDMXN=X",
    "USD/ZAR": "USDZAR=X",
    "USD/TRY": "USDTRY=X",
    "USD/BRL": "USDBRL=X",
    "USD/SGD": "USDSGD=X",
    "USD/THB": "USDTHB=X",
    "USD/CNH": "USDCNH=X",
    "USD/SEK": "USDSEK=X",
    "USD/NOK": "USDNOK=X",
    "USD/HKD": "USDHKD=X",
    "USD/PLN": "USDPLN=X",
    # ── Crypto ───────────────────────────────────────────────────
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "LTC/USD": "LTC-USD",
    "XRP/USD": "XRP-USD",
    "BCH/USD": "BCH-USD",
    "SOL/USD": "SOL-USD",
    "BNB/USD": "BNB-USD",
    "ADA/USD": "ADA-USD",
    "DOGE/USD": "DOGE-USD",
    "LINK/USD": "LINK-USD",
    "DOT/USD": "DOT-USD",
    "AVAX/USD": "AVAX-USD",
    "MATIC/USD": "MATIC-USD",  # May be delisted (Polygon rebranded to POL)
    # ── Commodities ──────────────────────────────────────────────
    # NOTE: XAU/USD maps to NYMEX gold futures (GC=F), not spot gold.
    # yfinance does not provide a reliable spot gold (XAUUSD) symbol.
    # Prices may differ from TradingView's spot gold by 0.5-2% due to
    # futures contract specifications, roll dates, and funding costs.
    "XAU/USD": "GC=F",      # Gold futures (not spot)
    "XAG/USD": "SI=F",      # Silver futures
    "WTI/USD": "CL=F",      # Crude Oil WTI
    "BRENT/USD": "BZ=F",    # Brent Crude
    "NG/USD": "NG=F",       # Natural Gas
    "XPT/USD": "PL=F",      # Platinum futures
    "COPPER/USD": "HG=F",   # Copper futures
    "COFFEE/USD": "KC=F",   # Coffee futures
    # ── Indices ──────────────────────────────────────────────────
    "US30": "^DJI",          # Dow Jones
    "US500": "^GSPC",        # S&P 500
    "US100": "^NDX",         # Nasdaq 100
    "UK100": "^FTSE",        # FTSE 100
    "DE40": "^GDAXI",        # DAX 40
    "FR40": "^FCHI",         # CAC 40
    "JP225": "^N225",        # Nikkei 225
    "AU200": "^AXJO",        # ASX 200
    "EU50": "^STOXX50E",     # Euro Stoxx 50
    "HK50": "^HSI",          # Hang Seng
    "IN50": "^NSEI",         # Nifty 50
    "ES35": "^IBEX",         # IBEX 35
    "IT40": "FTSEMIB.MI",    # FTSE MIB
    "CN50": "000016.SS",     # SSE 50 (China A50 proxy)
    "SA40": "^J200.JO",      # South Africa Top 40
}

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

# Timeframe mapping
TIMEFRAME_MAP = {
    "1m": ("1d", "1m"),  # period, interval
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("5d", "60m"),
    "4h": ("1mo", "1h"),  # yfinance doesn't have 4h, use 1h
    "1d": ("6mo", "1d"),
}

# Timeframes that need candle aggregation (yfinance doesn't support them natively)
AGGREGATE_TIMEFRAMES = {
    "4h": 4,  # Aggregate 4 x 1h candles
}


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


def get_cache_key(symbol: str, timeframe: str, endpoint: str) -> str:
    """Generate cache key."""
    return f"{endpoint}:{symbol}:{timeframe}"


def get_cached_data(key: str, timeframe: str) -> Optional[dict]:
    """Get cached data if not expired."""
    with _cache_lock:
        if key not in _cache:
            return None
        
        ttl = CACHE_TTL_DAILY if timeframe == "1d" else CACHE_TTL_INTRADAY
        if time.time() - _cache_timestamps.get(key, 0) > ttl:
            return None
        
        return _cache[key]


def set_cached_data(key: str, data: dict) -> None:
    """Cache data with timestamp."""
    with _cache_lock:
        _cache[key] = data
        _cache_timestamps[key] = time.time()


def get_shared_ohlcv(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Get OHLCV data from shared cache or fetch fresh from yfinance.
    
    This is the SINGLE source of truth for market data. All endpoints
    (analysis, candles, signals) should use this instead of calling
    fetch_data_yf() directly. This ensures data consistency across
    concurrent requests for the same symbol/timeframe.
    """
    cache_key = f"ohlcv:{symbol}:{timeframe}"
    now = time.time()
    
    # Check cache (lock only for read)
    with _ohlcv_lock:
        cached = _ohlcv_cache.get(cache_key)
        if cached and (now - cached["timestamp"]) < OHLCV_CACHE_TTL:
            return cached["df"]
    
    # Fetch outside the lock (network I/O) — uses retry + backoff
    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
    df = _fetch_yf_with_retry_sync(symbol, period=period, interval=interval)
    
    # Write back to cache (lock for write)
    if df is not None:
        with _ohlcv_lock:
            _ohlcv_cache[cache_key] = {"df": df, "timestamp": time.time()}
    
    return df


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


def aggregate_candles(candles: list, group_size: int = 4) -> list:
    """Aggregate N candles into 1 (e.g., 4x1h → 1x4h).
    
    Each group uses: first open, max high, min low, last close, sum volume.
    """
    aggregated = []
    for i in range(0, len(candles), group_size):
        group = candles[i:i + group_size]
        if not group:
            continue
        aggregated.append(CandleData(
            time=group[0].time,
            open=group[0].open,
            high=max(c.high for c in group),
            low=min(c.low for c in group),
            close=group[-1].close,
            volume=sum(c.volume for c in group),
        ))
    return aggregated


def fetch_data_yf(symbol: str, timeframe: str) -> Optional[pd.DataFrame]:
    """Fetch OHLCV data from yfinance."""
    try:
        yf_symbol = map_symbol_to_yf(symbol)
        period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
        
        ticker = yf.Ticker(yf_symbol)
        df = ticker.history(period=period, interval=interval)
        
        if df.empty:
            logger.warning(f"No data returned for {symbol} ({yf_symbol})")
            return None
        
        # Rename columns to lowercase
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        
        # Ensure required columns exist
        required_cols = ["open", "high", "low", "close", "volume"]
        for col in required_cols:
            if col not in df.columns:
                logger.error(f"Missing column {col} in data for {symbol}")
                return None
        
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {e}")
        return None


def analyze_symbol(symbol: str, timeframe: str, trade_style: str = "swing") -> Optional[dict]:
    """Perform technical analysis on a symbol."""
    df = get_shared_ohlcv(symbol, timeframe)
    if df is None or len(df) < 30:
        return None
    
    # Get current values
    current_price = df["close"].iloc[-1]
    prev_price = df["close"].iloc[-2] if len(df) > 1 else current_price
    price_change = current_price - prev_price
    price_change_pct = (price_change / prev_price) * 100 if prev_price != 0 else 0
    
    # Calculate indicators
    rsi = calculate_rsi(df["close"], 14)
    macd_line, macd_signal, macd_hist = calculate_macd(df["close"])
    ema20 = calculate_ema(df["close"], 20)
    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(df["close"])
    atr = calculate_atr(df["high"], df["low"], df["close"])
    
    # Volume analysis
    current_volume = df["volume"].iloc[-1]
    avg_volume = df["volume"].rolling(window=20).mean().iloc[-1]
    volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
    
    # Determine indicator signals
    indicators = []
    bullish_count = 0
    bearish_count = 0
    
    # RSI signal
    if rsi < 45:
        rsi_signal = "bullish"
        bullish_count += 1
    elif rsi > 55:
        rsi_signal = "bearish"
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
        bullish_count += 1
    elif macd_hist < 0 and macd_line < macd_signal:
        macd_signal_str = "bearish"
        bearish_count += 1
    else:
        macd_signal_str = "neutral"
    indicators.append({
        "name": "MACD",
        "value": "Bullish Cross" if macd_signal_str == "bullish" else ("Bearish Cross" if macd_signal_str == "bearish" else "Neutral"),
        "signal": macd_signal_str
    })
    
    # EMA signal
    if current_price > ema20:
        ema_signal = "bullish"
        bullish_count += 1
    else:
        ema_signal = "bearish"
        bearish_count += 1
    decimals = get_decimal_places(current_price)
    indicators.append({
        "name": "EMA(20)",
        "value": f"{ema20:.{decimals}f}",
        "signal": ema_signal
    })
    
    # Bollinger Bands signal
    bb_pct = (current_price - bb_lower) / (bb_upper - bb_lower) if (bb_upper - bb_lower) > 0 else 0.5
    if bb_pct < 0.45:
        bb_signal = "bullish"
        bullish_count += 1
    elif bb_pct > 0.55:
        bb_signal = "bearish"
        bearish_count += 1
    else:
        bb_signal = "neutral"
    indicators.append({
        "name": "BB Position",
        "value": "Lower Band" if bb_pct < 0.2 else ("Upper Band" if bb_pct > 0.8 else "Middle"),
        "signal": bb_signal
    })
    
    # Volume signal
    if volume_ratio > 0.8:
        vol_signal = "bullish"
        bullish_count += 1
    elif volume_ratio < 0.8:
        vol_signal = "bearish"
        bearish_count += 1
    else:
        vol_signal = "neutral"
    indicators.append({
        "name": "Volume",
        "value": "Above Avg" if volume_ratio > 1.0 else "Below Avg",
        "signal": vol_signal
    })
    
    patterns = detect_patterns(df)

    # Determine overall signal with improved confidence scoring
    total_directional = bullish_count + bearish_count
    if bullish_count > bearish_count:
        signal = "buy"
        # Base confidence from directional agreement + bonus for decisiveness
        base_conf = (bullish_count / max(total_directional, 1)) * 100
        # Scale up: even 3 out of 5 bullish should yield ~70-80% confidence
        confidence = min(95, int(base_conf * 0.7 + bullish_count * 8))
    elif bearish_count > bullish_count:
        signal = "sell"
        base_conf = (bearish_count / max(total_directional, 1)) * 100
        confidence = min(95, int(base_conf * 0.7 + bearish_count * 8))
    else:
        # Tie-break: use RSI and MACD to pick a direction instead of defaulting to hold
        if rsi < 50 and macd_hist < 0:
            signal = "sell"
            confidence = 55
        elif rsi > 50 and macd_hist > 0:
            signal = "buy"
            confidence = 55
        else:
            signal = "hold"
            confidence = 50
    
    # Generate reason text
    reasons = []
    if rsi < 30:
        reasons.append(f"RSI oversold at {rsi:.1f}")
    elif rsi > 70:
        reasons.append(f"RSI overbought at {rsi:.1f}")
    
    if macd_signal_str == "bullish":
        reasons.append("MACD bullish crossover")
    elif macd_signal_str == "bearish":
        reasons.append("MACD bearish crossover")
    
    if bb_signal == "bullish":
        reasons.append("price bouncing off lower Bollinger Band")
    elif bb_signal == "bearish":
        reasons.append("price near upper Bollinger Band")
    
    reason = ", ".join(reasons) if reasons else "Mixed signals, no clear direction"
    
    # Trade style multipliers
    if trade_style == "scalp":
        # Timeframe-specific multipliers for optimal scalp pip levels
        if timeframe == "1m":
            entry_mult = 0.05
            sl_mult = 0.35
            tp1_mult = 0.35
            tp2_mult = 0.70
            tp3_mult = 1.05
        elif timeframe == "5m":
            entry_mult = 0.08
            sl_mult = 0.30
            tp1_mult = 0.30
            tp2_mult = 0.60
            tp3_mult = 0.90
        else:
            # 15m+ timeframes: transitional scalp
            entry_mult = 0.15
            sl_mult = 0.60
            tp1_mult = 0.60
            tp2_mult = 1.20
            tp3_mult = 1.80
    else:  # swing
        entry_mult = 0.50
        sl_mult = 2.0
        tp1_mult = 2.0         # 1:1 R:R
        tp2_mult = 4.0         # 2:1 R:R
        tp3_mult = 6.0         # 3:1 R:R

    # Calculate entry range based on ATR
    entry_min = current_price - (entry_mult * atr)
    entry_max = current_price + (entry_mult * atr)

    # Ensure minimum spread to prevent collapsed range
    min_spread = current_price * 0.0005  # 0.05% minimum spread
    if (entry_max - entry_min) < min_spread:
        entry_min = current_price - (min_spread / 2)
        entry_max = current_price + (min_spread / 2)

    # Calculate SL and 3 TP levels based on signal direction
    if signal == "buy":
        stop_loss = current_price - (sl_mult * atr)
        take_profit1 = current_price + (tp1_mult * atr)
        take_profit2 = current_price + (tp2_mult * atr)
        take_profit3 = current_price + (tp3_mult * atr)
    elif signal == "sell":
        stop_loss = current_price + (sl_mult * atr)
        take_profit1 = current_price - (tp1_mult * atr)
        take_profit2 = current_price - (tp2_mult * atr)
        take_profit3 = current_price - (tp3_mult * atr)
    else:
        stop_loss = current_price - (sl_mult * atr)
        take_profit1 = current_price + (tp1_mult * atr)
        take_profit2 = current_price + (tp2_mult * atr)
        take_profit3 = current_price + (tp3_mult * atr)

    # Ensure entry range is narrower than SL distance
    entry_width = entry_max - entry_min
    sl_distance = abs(current_price - stop_loss)
    if entry_width >= sl_distance * 0.6:
        half = sl_distance * 0.25
        entry_min = current_price - half
        entry_max = current_price + half

    # Calculate actual risk/reward from entry, stop loss, and take profit
    risk_distance = abs(current_price - stop_loss)
    reward_distance = abs(take_profit2 - current_price)
    risk_reward = round(reward_distance / risk_distance, 2) if risk_distance > 0 else 2.0
    
    # Determine market regime
    avg_atr = df["close"].rolling(window=20).apply(lambda x: calculate_atr(df["high"].loc[x.index], df["low"].loc[x.index], df["close"].loc[x.index])).mean()
    avg_atr = avg_atr.iloc[-1] if hasattr(avg_atr, 'iloc') else avg_atr
    
    if current_price > ema20 and macd_line > 0 and 50 < rsi < 70:
        regime = "trending_up"
    elif current_price < ema20 and macd_line < 0 and 30 < rsi < 50:
        regime = "trending_down"
    elif atr > 1.5 * avg_atr if avg_atr else False:
        regime = "volatile"
    else:
        regime = "ranging"
    
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

    ai_score = compute_ai_score(signal, confidence, indicators, regime, patterns)
    pattern_accuracy = patterns[0]["successRate"] if patterns else None

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
        "trade_style": trade_style,
        "data_fetched_at": time.time(),
        "is_mock": False,
        "source": "live",
    }


def analyze_multitimeframe(symbol: str, primary_timeframe: str) -> List[dict]:
    """Analyze symbol across multiple timeframes."""
    timeframes = ["1d", "4h", "1h", "15m", "5m"]
    results = []
    
    for tf in timeframes:
        analysis = analyze_symbol(symbol, tf)
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


def _safe_float(value: float | int | None, default: float = 0.0) -> float:
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
    avg_volume = _safe_float(volumes.tail(20).mean(), 1.0)
    volume_ratio = _safe_float(volumes.iloc[-1] / avg_volume, 1.0)
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
) -> dict:
    """Compute a simple 0-100 AI score with factor breakdown."""
    directional_indicators = [indicator for indicator in indicators if indicator["signal"] != "neutral"]
    bullish = sum(1 for indicator in directional_indicators if indicator["signal"] == "bullish")
    bearish = sum(1 for indicator in directional_indicators if indicator["signal"] == "bearish")
    total = max(1, len(directional_indicators))

    indicator_score = max(bullish, bearish) / total * 100
    confidence_score = _clamp(_safe_float(confidence, 50.0), 0, 100)

    regime_map = {
        "trending_up": 82 if signal == "buy" else 46,
        "trending_down": 82 if signal == "sell" else 46,
        "ranging": 58,
        "volatile": 52,
    }
    regime_score = regime_map.get(market_regime, 55)

    top_pattern = patterns[0] if patterns else None
    pattern_score = top_pattern["confidence"] if top_pattern else 50
    if top_pattern:
        if (signal == "buy" and top_pattern["direction"] != "bullish") or (signal == "sell" and top_pattern["direction"] != "bearish"):
            pattern_score = max(35, pattern_score - 18)

    total_score = round(
        confidence_score * 0.4 +
        indicator_score * 0.3 +
        regime_score * 0.15 +
        pattern_score * 0.15
    )

    if total_score >= 80:
        label = "Strong"
    elif total_score >= 65:
        label = "Favorable"
    elif total_score >= 50:
        label = "Neutral"
    else:
        label = "Cautious"

    return {
        "value": int(_clamp(total_score, 0, 100)),
        "label": label,
        "factors": {
            "modelConfidence": round(confidence_score, 1),
            "indicatorConsensus": round(indicator_score, 1),
            "marketRegimeFit": round(regime_score, 1),
            "patternStrength": round(pattern_score, 1),
        },
    }


@router.get("/analysis/{symbol:path}")
async def get_market_analysis(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$")
) -> dict:
    """Get comprehensive market analysis for a symbol."""
    # Validate symbol against whitelist
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    cache_key = get_cache_key(symbol, f"{timeframe}:{trade_style}", "analysis")
    cached = get_cached_data(cache_key, timeframe)
    
    if cached:
        return cached
    
    analysis = analyze_symbol(symbol, timeframe, trade_style)
    
    if analysis is None:
        # Return fallback response
        fallback = {
            "currentPrice": 0.0,
            "priceChange": 0.0,
            "priceChangePercent": 0.0,
            "signal": "hold",
            "confidence": 50,
            "reason": "Unable to fetch market data",
            "entryRange": {"min": 0.0, "max": 0.0},
            "stopLoss": 0.0,
            "takeProfit": 0.0,
            "riskReward": 0.0,
            "timeframe": timeframe,
            "marketRegime": "unknown",
            "indicators": [],
            "multiTimeframe": [],
            "data_fetched_at": time.time(),
            "is_mock": True,
            "source": "mock",
        }
        logger.warning(f"Falling back to mock data for {symbol}")
        return fallback
    
    # Add multi-timeframe analysis
    analysis["multiTimeframe"] = analyze_multitimeframe(symbol, timeframe)
    
    set_cached_data(cache_key, analysis)
    return analysis


@router.get("/score/{symbol:path}")
async def get_ai_score(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$")
) -> dict:
    """Get AI score and detected patterns for a symbol."""
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    analysis = analyze_symbol(symbol, timeframe, trade_style)
    if analysis is None:
        raise HTTPException(status_code=503, detail=f"AI score unavailable for {symbol}")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "tradeStyle": trade_style,
        "signal": analysis["signal"],
        "confidence": analysis["confidence"],
        "aiScore": analysis.get("aiScore"),
        "patterns": analysis.get("patterns", []),
        "patternAccuracy": analysis.get("patternAccuracy"),
        "marketRegime": analysis.get("marketRegime"),
        "updatedAt": analysis.get("data_fetched_at"),
    }


@router.get("/quote/{symbol:path}")
async def get_market_quote(
    symbol: str,
    timeframe: str = Query("1m", description="Quote timeframe used for latest candle/price")
) -> dict:
    """Get a lightweight latest quote for fast UI refreshes."""
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    df = get_shared_ohlcv(symbol, timeframe)
    if df is None or len(df) < 2:
        raise HTTPException(status_code=503, detail=f"Quote unavailable for {symbol}")

    current_price = float(df["close"].iloc[-1])
    prev_price = float(df["close"].iloc[-2])
    price_change = current_price - prev_price
    price_change_pct = (price_change / prev_price) * 100 if prev_price else 0.0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "currentPrice": round(current_price, 4 if current_price < 10 else 2),
        "priceChange": round(price_change, 4 if abs(price_change) < 10 else 2),
        "priceChangePercent": round(price_change_pct, 2),
        "data_fetched_at": time.time(),
        "source": "live",
    }


@router.get("/recommendations")
async def get_recommendations(
    symbols: str = Query("EUR/USD,GBP/USD,BTC/USD", description="Comma-separated list of symbols")
) -> dict:
    """Get trading recommendations for multiple symbols."""
    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()]
    recommendations = []
    
    for symbol in symbol_list:
        cache_key = get_cache_key(symbol, "1h", "recommendation")
        cached = get_cached_data(cache_key, "1h")
        
        if cached:
            recommendations.append(cached)
            continue
        
        analysis = analyze_symbol(symbol, "1h")
        
        if analysis is None:
            # Fallback recommendation
            rec = {
                "symbol": symbol,
                "signal": "HOLD",
                "confidence": 50,
                "sharpeRatio": 1.0,
                "volatility": "NORMAL",
                "correlationRisk": "LOW"
            }
        else:
            # Calculate additional metrics
            df = get_shared_ohlcv(symbol, "1h")
            sharpe = calculate_sharpe_approximation(df) if df is not None else 1.0
            volatility = get_volatility_level(analysis.get("atr", 0), analysis["currentPrice"])
            
            rec = {
                "symbol": symbol,
                "signal": analysis["signal"].upper(),
                "confidence": analysis["confidence"],
                "sharpeRatio": sharpe,
                "volatility": volatility,
                "correlationRisk": "LOW"  # Simplified - would need correlation matrix
            }
            
            set_cached_data(cache_key, rec)
        
        recommendations.append(rec)
    
    return {"recommendations": recommendations}


# Timeframe to seconds for candle generation
_CANDLE_TF_SECONDS = {
    "1m": 60, "5m": 300, "15m": 900,
    "1h": 3600, "4h": 14400, "1d": 86400,
}

# Typical starting prices for mock candle generation (approximate 2026 levels)
_MOCK_START_PRICES: Dict[str, float] = {
    # Major Forex
    "EUR/USD": 1.17, "GBP/USD": 1.34, "USD/JPY": 158.50,
    "USD/CHF": 0.845, "AUD/USD": 0.64, "USD/CAD": 1.385,
    "NZD/USD": 0.595,
    # Minor / Cross Forex
    "EUR/GBP": 0.873, "EUR/JPY": 185.50, "EUR/CHF": 0.94,
    "GBP/JPY": 212.50, "GBP/CHF": 1.06, "AUD/JPY": 101.0,
    "AUD/NZD": 1.08, "GBP/CAD": 1.74, "NZD/JPY": 93.0,
    "EUR/NZD": 1.78, "CAD/JPY": 113.0, "CHF/JPY": 176.0,
    "EUR/AUD": 1.66,
    # Exotic Forex
    "USD/MXN": 17.5, "USD/ZAR": 18.5, "USD/TRY": 38.0,
    "USD/BRL": 5.8, "USD/SGD": 1.34, "USD/THB": 35.2,
    "USD/CNH": 7.25, "USD/SEK": 10.8, "USD/NOK": 10.9,
    "USD/HKD": 7.81, "USD/PLN": 4.05,
    # Crypto
    "BTC/USD": 71300.0, "ETH/USD": 2230.0, "SOL/USD": 150.0,
    "XRP/USD": 0.58, "BNB/USD": 580.0, "ADA/USD": 0.45,
    "DOGE/USD": 0.15, "LTC/USD": 85.0, "LINK/USD": 14.5,
    "DOT/USD": 7.2, "AVAX/USD": 35.0, "MATIC/USD": 0.72, "BCH/USD": 350.0,
    # Commodities
    "XAU/USD": 4840.0, "XAG/USD": 58.50, "WTI/USD": 78.5,
    "BRENT/USD": 82.0, "NG/USD": 2.15, "XPT/USD": 980.0,
    "COPPER/USD": 4.5, "COFFEE/USD": 200.0,
    # Indices
    "US30": 39800.0, "US500": 6620.0, "US100": 18400.0,
    "UK100": 8200.0, "DE40": 18100.0, "FR40": 8050.0,
    "JP225": 39500.0, "AU200": 7800.0, "EU50": 5000.0,
    "ES35": 11200.0, "IT40": 34000.0, "HK50": 17500.0,
    "CN50": 12800.0, "IN50": 22500.0, "SA40": 76000.0,
}


def _generate_mock_candles(symbol: str, timeframe: str, limit: int) -> List[CandleData]:
    """Generate realistic mock OHLCV candles using a random walk."""
    candle_seconds = _CANDLE_TF_SECONDS.get(timeframe, 3600)
    now_ts = int(time.time())
    start_ts = now_ts - (limit * candle_seconds)

    start_price = _MOCK_START_PRICES.get(symbol, 1.10)
    # Scale volatility to price magnitude
    volatility = start_price * 0.002  # ~0.2% per candle

    candles: List[CandleData] = []
    prev_close = start_price

    for i in range(limit):
        ts = start_ts + i * candle_seconds
        open_price = prev_close
        change = random.uniform(-volatility, volatility)
        close_price = open_price + change
        high_price = max(open_price, close_price) + random.uniform(0, volatility * 0.5)
        low_price = min(open_price, close_price) - random.uniform(0, volatility * 0.5)
        volume = random.randint(100, 10000)

        candles.append(CandleData(
            time=ts,
            open=round(open_price, 5),
            high=round(high_price, 5),
            low=round(low_price, 5),
            close=round(close_price, 5),
            volume=float(volume),
        ))
        prev_close = close_price

    return candles


@router.get("/candles/{symbol:path}")
async def get_candles(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    limit: int = Query(200, ge=1, le=1000, description="Number of candles"),
) -> dict:
    """Get OHLCV candle data for a symbol.

    Attempts to fetch real data via yfinance; falls back to realistic mock data.
    """
    # Validate symbol against whitelist
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    # Try real data first
    df = None
    try:
        df = get_shared_ohlcv(symbol, timeframe)
        if df is not None and len(df) >= 5:
            # Convert DataFrame rows to CandleData
            candles: List[CandleData] = []

            # Determine precision from first data point
            sample_price = float(df.tail(limit).iloc[0]["close"]) if len(df) > 0 else 1.0
            decimals = get_decimal_places(sample_price)

            for idx, row in df.tail(limit).iterrows():
                if isinstance(idx, pd.Timestamp):
                    ts = int(idx.timestamp())
                elif hasattr(idx, "timestamp"):
                    ts = int(idx.timestamp())
                else:
                    logger.warning(f"Unexpected index type {type(idx)} for {symbol}, using current time")
                    ts = int(time.time())
                candles.append(CandleData(
                    time=ts,
                    open=round(float(row["open"]), decimals),
                    high=round(float(row["high"]), decimals),
                    low=round(float(row["low"]), decimals),
                    close=round(float(row["close"]), decimals),
                    volume=round(float(row["volume"]), 2),
                ))

            # Aggregate candles for timeframes not natively supported by yfinance
            agg_size = AGGREGATE_TIMEFRAMES.get(timeframe)
            if agg_size:
                candles = aggregate_candles(candles, agg_size)

            logger.info(f"Returning {len(candles)} real candles for {symbol} ({timeframe})")
            return {"candles": candles, "source": "live", "fetched_at": time.time()}
    except Exception as e:
        logger.warning(f"Real candle fetch failed for {symbol}: {e}")

    # Fallback to mock data
    logger.warning(f"Falling back to mock data for {symbol}")
    if df is None:
        logger.warning(f"yfinance returned no data for {symbol} ({timeframe}); falling back to mock")
    elif len(df) < 5:
        logger.warning(f"yfinance returned only {len(df)} candles for {symbol} ({timeframe}); falling back to mock")
    else:
        logger.warning(f"Unexpected fallback to mock data for {symbol} ({timeframe})")
    mock_candles = _generate_mock_candles(symbol, timeframe, limit * (AGGREGATE_TIMEFRAMES.get(timeframe, 1)))
    agg_size = AGGREGATE_TIMEFRAMES.get(timeframe)
    if agg_size:
        mock_candles = aggregate_candles(mock_candles, agg_size)
    return {"candles": mock_candles, "source": "mock", "is_mock": True, "fetched_at": time.time()}
