"""Market analysis routes using the unified market data service."""

import asyncio
import random
import threading
import time
from typing import Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, HTTPException, Query

from trading_bot.api.models import CandleData
from trading_bot.config import get_logger
from trading_bot.execution.broker_base import BrokerCandle, BrokerQuote
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager
from trading_bot.services.market_analysis import (
    ALLOWED_SYMBOLS,
    analyze_multitimeframe,
    analyze_symbol,
    calculate_sharpe_approximation,
    get_decimal_places,
    get_shared_ohlcv,
    get_shared_ohlcv_with_metadata,
    get_volatility_level,
    map_symbol_to_yf,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/market", tags=["market"])

# Simple in-memory cache with TTL
_cache: Dict[str, dict] = {}
_cache_timestamps: Dict[str, float] = {}
_cache_lock = threading.RLock()
CACHE_TTL_INTRADAY = 5  # Faster refresh for active intraday trading views
CACHE_TTL_DAILY = 300  # 300 seconds for daily timeframe
BROKER_QUOTE_TIMEOUT_SECONDS = 8.0
BROKER_CANDLES_TIMEOUT_SECONDS = 12.0

# Timeframes that need candle aggregation (yfinance doesn't support them natively)
AGGREGATE_TIMEFRAMES = {
    "4h": 4,  # Aggregate 4 x 1h candles
}


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


def _price_from_broker_quote(quote: BrokerQuote) -> Optional[float]:
    if quote.last and quote.last > 0:
        return float(quote.last)
    if quote.bid and quote.ask and quote.bid > 0 and quote.ask > 0:
        return (float(quote.bid) + float(quote.ask)) / 2
    if quote.bid and quote.bid > 0:
        return float(quote.bid)
    if quote.ask and quote.ask > 0:
        return float(quote.ask)
    return None


async def _active_broker_quote(symbol: str, timeframe: str) -> Optional[dict]:
    active = broker_manager.get_active_broker_info()
    if not active or not active.get("connected"):
        return None
    capabilities = active.get("capabilities") or {}
    if not capabilities.get("quotes"):
        return None

    broker_id = str(active.get("id") or active.get("broker_id") or "")
    broker = broker_manager.get_broker(broker_id)
    if not broker:
        return None

    try:
        quote = await asyncio.wait_for(
            broker.get_quote(symbol),
            timeout=BROKER_QUOTE_TIMEOUT_SECONDS,
        )
    except (BrokerOperationError, TimeoutError) as exc:
        logger.warning(
            "Active broker quote unavailable; falling back to market data",
            broker_id=broker_id,
            symbol=symbol,
            error=str(exc),
        )
        return None

    current_price = _price_from_broker_quote(quote)
    if current_price is None:
        return None

    decimals = get_decimal_places(current_price)
    fetched_at = time.time()
    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "currentPrice": round(current_price, decimals),
        "priceChange": 0.0,
        "priceChangePercent": 0.0,
        "data_fetched_at": fetched_at,
        "source": "live",
        "priceSource": "broker_quote",
        "sourceMetadata": {
            "sourceName": active.get("name") or broker_id,
            "sourceType": "broker",
            "priceSource": "broker_quote",
            "brokerId": broker_id,
            "environment": active.get("environment"),
            "isFallback": False,
            "freshnessSeconds": max(0.0, fetched_at - quote.timestamp.timestamp()),
            "qualityFlags": [],
            "lastBarTimestamp": quote.timestamp.isoformat(),
            "marketStatus": "live",
        },
    }


def _candle_to_api(candle: BrokerCandle, decimals: int) -> CandleData:
    return CandleData(
        time=int(candle.time.timestamp()),
        open=round(candle.open, decimals),
        high=round(candle.high, decimals),
        low=round(candle.low, decimals),
        close=round(candle.close, decimals),
        volume=round(float(candle.volume), 2),
    )


async def _active_broker_candles(symbol: str, timeframe: str, limit: int) -> Optional[dict]:
    active = broker_manager.get_active_broker_info()
    if not active or not active.get("connected"):
        return None
    capabilities = active.get("capabilities") or {}
    if not capabilities.get("candles"):
        return None

    broker_id = str(active.get("id") or active.get("broker_id") or "")
    broker = broker_manager.get_broker(broker_id)
    if not broker:
        return None

    try:
        broker_candles = await asyncio.wait_for(
            broker.get_candles(symbol, timeframe=timeframe, count=limit),
            timeout=BROKER_CANDLES_TIMEOUT_SECONDS,
        )
    except (BrokerOperationError, TimeoutError) as exc:
        logger.warning(
            "Active broker candles unavailable; falling back to market data",
            broker_id=broker_id,
            symbol=symbol,
            timeframe=timeframe,
            error=str(exc),
        )
        return None
    if len(broker_candles) < 5:
        return None

    sample_price = broker_candles[-1].close
    decimals = get_decimal_places(sample_price)
    fetched_at = time.time()
    last_candle = broker_candles[-1]
    return {
        "candles": [_candle_to_api(candle, decimals) for candle in broker_candles[-limit:]],
        "source": "live",
        "fetched_at": fetched_at,
        "sourceMetadata": {
            "sourceName": active.get("name") or broker_id,
            "sourceType": "broker",
            "priceSource": "broker_candles",
            "brokerId": broker_id,
            "environment": active.get("environment"),
            "isFallback": False,
            "freshnessSeconds": max(0.0, fetched_at - last_candle.time.timestamp()),
            "qualityFlags": [],
            "lastBarTimestamp": last_candle.time.isoformat(),
            "marketStatus": "live",
        },
    }




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
    analysis_tf = "1m" if trade_style == "scalp" and timeframe not in ("1m", "5m") else timeframe
    _, metadata = get_shared_ohlcv_with_metadata(symbol, analysis_tf, trade_style)
    
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
        fallback["sourceMetadata"] = {
            "sourceName": "mock",
            "sourceType": "mock",
            "priceSource": "mock",
            "isFallback": True,
            "freshnessSeconds": None,
            "qualityFlags": ["mock_data"],
            "lastBarTimestamp": None,
            "marketStatus": "stale",
        }
        return fallback
    
    # Add multi-timeframe analysis
    analysis["multiTimeframe"] = analyze_multitimeframe(symbol, timeframe, trade_style)
    analysis["sourceMetadata"] = metadata
    
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
    timeframe: str = Query("1m", description="Quote timeframe used for latest candle/price"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$", description="Trade style: scalp uses spot, swing uses futures"),
) -> dict:
    """Get a lightweight latest quote for fast UI refreshes."""
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    broker_quote = await _active_broker_quote(symbol, timeframe)
    if broker_quote:
        return broker_quote

    df, metadata = get_shared_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
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
        "priceSource": metadata.get("priceSource"),
        "sourceMetadata": metadata,
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
    trade_style: str = Query("swing", pattern="^(scalp|swing)$", description="Trade style: scalp uses spot, swing uses futures"),
) -> dict:
    """Get OHLCV candle data for a symbol.

    Attempts to fetch real data via yfinance; falls back to realistic mock data.
    """
    # Validate symbol against whitelist
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    broker_candles = await _active_broker_candles(symbol, timeframe, limit)
    if broker_candles:
        return broker_candles

    # Try real data first
    df = None
    try:
        df, metadata = get_shared_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
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
            return {
                "candles": candles,
                "source": "live",
                "fetched_at": time.time(),
                "sourceMetadata": metadata,
            }
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
