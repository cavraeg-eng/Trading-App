"""Market analysis routes using real data from yfinance."""

import random
import time
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
CACHE_TTL_INTRADAY = 60  # 60 seconds for intraday timeframes
CACHE_TTL_DAILY = 300  # 5 minutes for daily timeframe

# Symbol mapping from our format to yfinance format
SYMBOL_MAPPING = {
    # Forex
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "USD/CHF": "CHFUSD=X",
    "AUD/USD": "AUDUSD=X",
    "USD/CAD": "CAD=X",
    "NZD/USD": "NZDUSD=X",
    "EUR/GBP": "EURGBP=X",
    "EUR/JPY": "EURJPY=X",
    "GBP/JPY": "GBPJPY=X",
    # Crypto
    "BTC/USD": "BTC-USD",
    "ETH/USD": "ETH-USD",
    "LTC/USD": "LTC-USD",
    "XRP/USD": "XRP-USD",
    "BCH/USD": "BCH-USD",
    # Commodities
    "XAU/USD": "GC=F",  # Gold futures
    "XAG/USD": "SI=F",  # Silver futures
    "WTI/USD": "CL=F",  # Crude Oil
    "BRENT/USD": "BZ=F",  # Brent Oil
    "NG/USD": "NG=F",  # Natural Gas
    # Indices
    "US30": "^DJI",  # Dow Jones
    "US500": "^GSPC",  # S&P 500
    "US100": "^NDX",  # Nasdaq 100
    "UK100": "^FTSE",  # FTSE 100
    "DE40": "^GDAXI",  # DAX
    "FR40": "^FCHI",  # CAC 40
    "JP225": "^N225",  # Nikkei 225
    "AU200": "^AXJO",  # ASX 200
    "EU50": "^STOXX50E",  # Euro Stoxx 50
    "HK50": "^HSI",  # Hang Seng
    "IN50": "^NSEI",  # Nifty 50
}

# Timeframe mapping
TIMEFRAME_MAP = {
    "1m": ("1d", "1m"),  # period, interval
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("5d", "60m"),
    "4h": ("1mo", "1h"),  # yfinance doesn't have 4h, use 1h
    "1d": ("6mo", "1d"),
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
    if key not in _cache:
        return None
    
    ttl = CACHE_TTL_DAILY if timeframe == "1d" else CACHE_TTL_INTRADAY
    if time.time() - _cache_timestamps.get(key, 0) > ttl:
        return None
    
    return _cache[key]


def set_cached_data(key: str, data: dict) -> None:
    """Cache data with timestamp."""
    _cache[key] = data
    _cache_timestamps[key] = time.time()


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
    df = fetch_data_yf(symbol, timeframe)
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
    if rsi < 30:
        rsi_signal = "bullish"
        bullish_count += 1
    elif rsi > 70:
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
    if bb_pct < 0.2:
        bb_signal = "bullish"
        bullish_count += 1
    elif bb_pct > 0.8:
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
    if volume_ratio > 1.5:
        vol_signal = "bullish"
        bullish_count += 1
    elif volume_ratio < 0.5:
        vol_signal = "bearish"
        bearish_count += 1
    else:
        vol_signal = "neutral"
    indicators.append({
        "name": "Volume",
        "value": "Above Avg" if volume_ratio > 1.0 else "Below Avg",
        "signal": vol_signal
    })
    
    # Determine overall signal
    total_signals = bullish_count + bearish_count
    if bullish_count > bearish_count:
        signal = "buy"
        confidence = int((bullish_count / len(indicators)) * 100)  # Returns 0-100 integer percentage
    elif bearish_count > bullish_count:
        signal = "sell"
        confidence = int((bearish_count / len(indicators)) * 100)  # Returns 0-100 integer percentage
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
        entry_mult = 0.10      # Tighter entry range
        sl_mult = 0.75         # ATR-based SL
        tp1_mult = 0.75        # 1:1 R:R
        tp2_mult = 1.50        # 2:1 R:R
        tp3_mult = 2.25        # 3:1 R:R
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
        "atr": round(atr, decimals + 1),
        "trade_style": trade_style,
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


@router.get("/analysis/{symbol:path}")
async def get_market_analysis(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    trade_style: str = Query("swing", regex="^(scalp|swing)$")
) -> dict:
    """Get comprehensive market analysis for a symbol."""
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
            "multiTimeframe": []
        }
        return fallback
    
    # Add multi-timeframe analysis
    analysis["multiTimeframe"] = analyze_multitimeframe(symbol, timeframe)
    
    set_cached_data(cache_key, analysis)
    return analysis


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
            df = fetch_data_yf(symbol, "1h")
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

# Typical starting prices for mock candle generation
_MOCK_START_PRICES: Dict[str, float] = {
    "EUR/USD": 1.0850, "GBP/USD": 1.2650, "USD/JPY": 155.50,
    "USD/CHF": 0.8850, "AUD/USD": 0.6550, "USD/CAD": 1.3650,
    "NZD/USD": 0.6050, "EUR/GBP": 0.8550, "EUR/JPY": 168.50,
    "GBP/JPY": 196.50, "BTC/USD": 68500.0, "ETH/USD": 3500.0,
    "XAU/USD": 2350.0, "US500": 5250.0, "US30": 39800.0,
    "US100": 18500.0,
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
) -> List[CandleData]:
    """Get OHLCV candle data for a symbol.

    Attempts to fetch real data via yfinance; falls back to realistic mock data.
    """
    # Try real data first
    try:
        df = fetch_data_yf(symbol, timeframe)
        if df is not None and len(df) >= 5:
            # Convert DataFrame rows to CandleData
            candles: List[CandleData] = []
            for idx, row in df.tail(limit).iterrows():
                ts = int(idx.timestamp()) if hasattr(idx, "timestamp") else int(time.time())
                candles.append(CandleData(
                    time=ts,
                    open=round(float(row["open"]), 5),
                    high=round(float(row["high"]), 5),
                    low=round(float(row["low"]), 5),
                    close=round(float(row["close"]), 5),
                    volume=round(float(row["volume"]), 2),
                ))
            logger.info(f"Returning {len(candles)} real candles for {symbol} ({timeframe})")
            return candles
    except Exception as e:
        logger.warning(f"Real candle fetch failed for {symbol}: {e}")

    # Fallback to mock data
    logger.info(f"Generating {limit} mock candles for {symbol} ({timeframe})")
    return _generate_mock_candles(symbol, timeframe, limit)
