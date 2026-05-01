"""Unified Market Data Service.

Single source of truth for all market data fetching in the application.
Consolidates yfinance, spot price APIs, caching, validation, and health tracking.

All consumers (market routes, scanner, signals, backtest) should use this module
instead of calling yfinance or other data sources directly.
"""

import asyncio
import threading
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

from trading_bot.config import get_logger, get_settings
from trading_bot.data.data_validator import validate_ohlcv, validate_spot_price
from trading_bot.monitoring.bot_metrics import bot_metrics

logger = get_logger(__name__)

# ── Symbol mapping from app format to yfinance format ────────────────────────
SYMBOL_MAPPING = {
    # Major Forex
    "EUR/USD": "EURUSD=X", "GBP/USD": "GBPUSD=X", "USD/JPY": "JPY=X",
    "USD/CHF": "USDCHF=X", "AUD/USD": "AUDUSD=X", "USD/CAD": "CAD=X",
    "NZD/USD": "NZDUSD=X",
    # Minor / Cross Forex
    "EUR/GBP": "EURGBP=X", "EUR/JPY": "EURJPY=X", "EUR/CHF": "EURCHF=X",
    "GBP/JPY": "GBPJPY=X", "GBP/CHF": "GBPCHF=X", "AUD/JPY": "AUDJPY=X",
    "AUD/NZD": "AUDNZD=X", "GBP/CAD": "GBPCAD=X", "NZD/JPY": "NZDJPY=X",
    "EUR/NZD": "EURNZD=X", "CAD/JPY": "CADJPY=X", "CHF/JPY": "CHFJPY=X",
    "EUR/AUD": "EURAUD=X",
    # Exotic Forex
    "USD/MXN": "USDMXN=X", "USD/ZAR": "USDZAR=X", "USD/TRY": "USDTRY=X",
    "USD/BRL": "USDBRL=X", "USD/SGD": "USDSGD=X", "USD/THB": "USDTHB=X",
    "USD/CNH": "USDCNH=X", "USD/SEK": "USDSEK=X", "USD/NOK": "USDNOK=X",
    "USD/HKD": "USDHKD=X", "USD/PLN": "USDPLN=X",
    # Crypto
    "BTC/USD": "BTC-USD", "ETH/USD": "ETH-USD", "LTC/USD": "LTC-USD",
    "XRP/USD": "XRP-USD", "BCH/USD": "BCH-USD", "SOL/USD": "SOL-USD",
    "BNB/USD": "BNB-USD", "ADA/USD": "ADA-USD", "DOGE/USD": "DOGE-USD",
    "LINK/USD": "LINK-USD", "DOT/USD": "DOT-USD", "AVAX/USD": "AVAX-USD",
    "MATIC/USD": "MATIC-USD",
    # Commodities
    "XAU/USD": "GC=F", "XAU/USD_FUTURES": "GC=F",
    "XAG/USD": "SI=F", "WTI/USD": "CL=F", "BRENT/USD": "BZ=F",
    "NG/USD": "NG=F", "XPT/USD": "PL=F", "COPPER/USD": "HG=F",
    "COFFEE/USD": "KC=F",
    # Indices
    "US30": "^DJI", "US500": "^GSPC", "US100": "^NDX",
    "UK100": "^FTSE", "DE40": "^GDAXI", "FR40": "^FCHI",
    "JP225": "^N225", "AU200": "^AXJO", "EU50": "^STOXX50E",
    "HK50": "^HSI", "IN50": "^NSEI", "ES35": "^IBEX",
    "IT40": "FTSEMIB.MI", "CN50": "000016.SS", "SA40": "^J200.JO",
}

# Timeframe → (yfinance period, yfinance interval)
TIMEFRAME_MAP = {
    "1m": ("1d", "1m"),
    "5m": ("5d", "5m"),
    "15m": ("5d", "15m"),
    "1h": ("5d", "60m"),
    "4h": ("1mo", "1h"),   # yfinance has no 4h; we fetch 1h and aggregate
    "1d": ("6mo", "1d"),
}

# Symbols that can use spot price APIs
SPOT_PRICE_SYMBOLS = {"XAU/USD", "XAG/USD"}


def map_symbol_to_yf(symbol: str) -> str:
    """Map app symbol format to yfinance ticker."""
    return SYMBOL_MAPPING.get(symbol, symbol)


# ─────────────────────────────────────────────────────────────────────────────
# Source Health Tracker
# ─────────────────────────────────────────────────────────────────────────────

class SourceHealthTracker:
    """Tracks health metrics for each data source."""

    def __init__(self):
        self._lock = threading.Lock()
        self._metrics: Dict[str, Dict] = {}

    def record_success(self, source: str, latency_ms: float) -> None:
        with self._lock:
            m = self._metrics.setdefault(source, self._empty())
            m["last_success"] = time.time()
            m["success_count"] += 1
            m["latencies"].append(latency_ms)
            # Keep only last 100 latencies
            if len(m["latencies"]) > 100:
                m["latencies"] = m["latencies"][-100:]

    def record_failure(self, source: str, error: str) -> None:
        with self._lock:
            m = self._metrics.setdefault(source, self._empty())
            m["last_failure"] = time.time()
            m["failure_count"] += 1
            m["last_error"] = error

    def record_fallback(self, primary: str, fallback: str) -> None:
        with self._lock:
            m = self._metrics.setdefault(primary, self._empty())
            m["fallback_count"] += 1
            m["last_fallback_to"] = fallback

    def get_status(self) -> Dict:
        with self._lock:
            result = {}
            for source, m in self._metrics.items():
                latencies = m["latencies"]
                result[source] = {
                    "status": "healthy" if m["last_success"] and (
                        time.time() - m["last_success"] < 300
                    ) else "degraded",
                    "last_success": m["last_success"],
                    "last_failure": m["last_failure"],
                    "success_count": m["success_count"],
                    "failure_count": m["failure_count"],
                    "fallback_count": m["fallback_count"],
                    "last_error": m["last_error"],
                    "median_latency_ms": round(float(np.median(latencies)), 1) if latencies else None,
                    "p95_latency_ms": round(float(np.percentile(latencies, 95)), 1) if len(latencies) >= 5 else None,
                }
            return result

    @staticmethod
    def _empty() -> Dict:
        return {
            "last_success": None,
            "last_failure": None,
            "success_count": 0,
            "failure_count": 0,
            "fallback_count": 0,
            "last_error": None,
            "last_fallback_to": None,
            "latencies": [],
        }


# ── Global singleton instances ───────────────────────────────────────────────
_health_tracker = SourceHealthTracker()

# Unified OHLCV cache: key -> {"df": DataFrame, "timestamp": float, "source": str}
_ohlcv_cache: Dict[str, dict] = {}
_ohlcv_lock = threading.RLock()

# yfinance concurrency semaphore (initialized lazily from settings)
_yf_semaphore: Optional[asyncio.Semaphore] = None
_yf_sync_lock = threading.Semaphore(2)  # sync version


def _get_settings_safe():
    """Get settings without failing on import-time errors."""
    try:
        return get_settings()
    except Exception:
        return None


def _timeframe_seconds(timeframe: str) -> int:
    mapping = {
        "1m": 60,
        "5m": 300,
        "15m": 900,
        "1h": 3600,
        "4h": 14400,
        "1d": 86400,
    }
    return mapping.get(timeframe, 3600)


def _extract_last_timestamp(df: Optional[pd.DataFrame]) -> Optional[float]:
    if df is None or df.empty:
        return None
    try:
        latest = df.index[-1]
        if hasattr(latest, "timestamp"):
            return float(latest.timestamp())
        return float(pd.Timestamp(latest).timestamp())
    except Exception:
        return None


def _freshness_thresholds(
    symbol: str,
    timeframe: str,
    trade_style: str,
    source_type: str,
) -> Tuple[float, float]:
    expected = _timeframe_seconds(timeframe)
    live_threshold = expected * 1.5
    delayed_threshold = expected * 3

    if symbol == "XAU/USD" and source_type == "synthetic_spot_from_futures" and trade_style == "scalp":
        if timeframe == "1m":
            return 5 * 60, 30 * 60
        if timeframe == "5m":
            return 15 * 60, 45 * 60

    return live_threshold, delayed_threshold


def build_source_metadata(
    symbol: str,
    timeframe: str,
    trade_style: str,
    df: Optional[pd.DataFrame],
    source_name: str,
    source_type: str,
    is_fallback: bool = False,
    quality_flags: Optional[List[str]] = None,
    reference_timestamp: Optional[float] = None,
) -> Dict:
    last_ts = _extract_last_timestamp(df)
    freshness_anchor = reference_timestamp if reference_timestamp is not None else last_ts
    freshness_seconds = None
    if freshness_anchor is not None:
        freshness_seconds = max(0.0, time.time() - freshness_anchor)

    market_status = "unknown"
    if freshness_seconds is not None:
        live_threshold, delayed_threshold = _freshness_thresholds(symbol, timeframe, trade_style, source_type)
        if freshness_seconds <= live_threshold:
            market_status = "live"
        elif freshness_seconds <= delayed_threshold:
            market_status = "delayed"
        else:
            market_status = "stale"

    flags = list(quality_flags or [])
    if is_fallback and "fallback_source" not in flags:
        flags.append("fallback_source")
    if source_type == "synthetic_spot_from_futures" and "synthetic_spot" not in flags:
        flags.append("synthetic_spot")
    if market_status == "stale" and "stale_data" not in flags:
        flags.append("stale_data")

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "tradeStyle": trade_style,
        "sourceName": source_name,
        "sourceType": source_type,
        "priceSource": source_type,
        "isFallback": is_fallback,
        "freshnessSeconds": round(freshness_seconds, 1) if freshness_seconds is not None else None,
        "qualityFlags": flags,
        "lastBarTimestamp": last_ts,
        "marketStatus": market_status,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Core Fetch Functions
# ─────────────────────────────────────────────────────────────────────────────

def fetch_yf_sync(
    symbol: str,
    max_retries: int = 3,
    **kwargs,
) -> Optional[pd.DataFrame]:
    """Fetch data from yfinance synchronously with retries and throttling.

    This is the ONE place in the app that calls yfinance for recent data.
    All other modules should call this or fetch_yf_historical().
    """
    yf_symbol = map_symbol_to_yf(symbol)
    settings = _get_settings_safe()
    retries = settings.yf_max_retries if settings else max_retries

    for attempt in range(retries):
        t0 = time.time()
        try:
            _yf_sync_lock.acquire()
            try:
                ticker = yf.Ticker(yf_symbol)
                df = ticker.history(**kwargs)
            finally:
                _yf_sync_lock.release()

            latency = (time.time() - t0) * 1000
            _health_tracker.record_success("yfinance", latency)
            bot_metrics.record_latency(
                "market_data.fetch",
                latency,
                context={"symbol": symbol, "source": "yfinance"},
            )

            if df is not None and not df.empty:
                df.columns = [c.lower().replace(" ", "_") for c in df.columns]
                required = ["open", "high", "low", "close", "volume"]
                for col in required:
                    if col not in df.columns:
                        logger.error(f"Missing column {col} in yfinance data for {symbol}")
                        return None
                return df

        except Exception as e:
            latency = (time.time() - t0) * 1000
            _health_tracker.record_failure("yfinance", str(e))
            bot_metrics.record_latency(
                "market_data.fetch",
                latency,
                context={"symbol": symbol, "source": "yfinance", "status": "error"},
            )
            bot_metrics.increment_counter(
                "external_api.error",
                label="yfinance",
                context={"symbol": symbol, "source": "yfinance"},
            )
            if "timeout" in str(e).lower():
                bot_metrics.increment_counter(
                    "external_api.timeout",
                    label="yfinance",
                    context={"symbol": symbol, "source": "yfinance"},
                )
            logger.warning(
                f"yfinance attempt {attempt + 1}/{retries} failed for {symbol}: {e}"
            )
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            else:
                logger.error(f"All {retries} yfinance attempts failed for {symbol}: {e}")

    return None


def fetch_yf_historical(
    symbol: str,
    interval: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    period: Optional[str] = None,
) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Fetch historical data from yfinance for backtesting.

    Supports explicit date ranges (start/end) and period-based queries.
    Returns (DataFrame, error_message). On success error_message is None.
    """
    yf_symbol = map_symbol_to_yf(symbol)
    t0 = time.time()
    try:
        kwargs = dict(interval=interval, progress=False)
        if period is not None:
            kwargs["period"] = period
        else:
            kwargs["start"] = start
            kwargs["end"] = end

        _yf_sync_lock.acquire()
        try:
            data = yf.download(yf_symbol, **kwargs)
        finally:
            _yf_sync_lock.release()

        latency = (time.time() - t0) * 1000
        _health_tracker.record_success("yfinance", latency)

    except Exception as exc:
        _health_tracker.record_failure("yfinance", str(exc))
        logger.error("yfinance download failed for %s: %s", symbol, exc)
        return None, f"Failed to fetch data for {symbol}: {str(exc)}"

    if data is None or data.empty or len(data) < 50:
        count = len(data) if data is not None else 0
        return None, f"Insufficient data for {symbol} ({count} bars). Need at least 50."

    # Normalise column names
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).strip().title() for c in data.columns]

    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in data.columns:
            return None, f"Missing column '{col}' in downloaded data."

    return data, None


# ─────────────────────────────────────────────────────────────────────────────
# Spot Price Fetching
# ─────────────────────────────────────────────────────────────────────────────

async def fetch_spot_price(symbol: str) -> Optional[Tuple[float, str]]:
    """Fetch current spot price for a commodity symbol.

    Returns (price, source_name) or None if all sources fail.
    Uses the improved fallback chain from forex_fetcher.
    """
    if symbol not in SPOT_PRICE_SYMBOLS:
        return None

    try:
        from trading_bot.forex_fetcher import ForexFetcher
    except ImportError:
        return None

    settings = _get_settings_safe()
    gold_api_key = settings.gold_api_key if settings else None

    try:
        async with ForexFetcher(gold_api_key=gold_api_key) as fetcher:
            if symbol == "XAU/USD":
                spot = await fetcher.fetch_xau_usd_spot()
            else:
                spot = None

            if spot:
                return spot.mid, spot.source
    except Exception as e:
        logger.warning(f"Spot price fetch failed for {symbol}: {e}")

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Unified OHLCV Access (the main entry point)
# ─────────────────────────────────────────────────────────────────────────────

def get_ohlcv(
    symbol: str,
    timeframe: str,
    trade_style: str = "swing",
    validate: bool = True,
) -> Optional[pd.DataFrame]:
    """Get OHLCV data — single source of truth for all consumers.

    This replaces the fragmented fetch_data_yf(), get_shared_ohlcv(),
    and direct yf.download() calls throughout the app.

    Source routing:
      - For XAU/USD in scalp mode with spot_preferred policy:
        tries spot-adjusted data, falls back to raw futures.
      - For all other symbols: yfinance directly.
      - All data passes through validation before caching/returning.
    """
    settings = _get_settings_safe()

    # Determine source policy
    use_spot = (
        symbol in SPOT_PRICE_SYMBOLS
        and trade_style == "scalp"
        and settings is not None
        and settings.use_spot_prices
        and settings.xau_source_policy != "futures_only"
    )
    source_tag = "spot" if use_spot else "futures"
    cache_key = f"ohlcv:{symbol}:{timeframe}:{source_tag}"

    # Determine cache TTL
    if settings:
        ttl = settings.ohlcv_cache_ttl_daily if timeframe == "1d" else settings.ohlcv_cache_ttl_intraday
    else:
        ttl = 300 if timeframe == "1d" else 5

    # Check cache
    now = time.time()
    cache_lookup_started = time.perf_counter()
    with _ohlcv_lock:
        cached = _ohlcv_cache.get(cache_key)
        if cached and (now - cached["timestamp"]) < ttl:
            bot_metrics.record_latency(
                "cache.lookup",
                (time.perf_counter() - cache_lookup_started) * 1000,
                context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
            )
            bot_metrics.increment_counter(
                "cache.hit",
                label="ohlcv",
                context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
            )
            return cached["df"]
    bot_metrics.record_latency(
        "cache.lookup",
        (time.perf_counter() - cache_lookup_started) * 1000,
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )
    bot_metrics.increment_counter(
        "cache.miss",
        label="ohlcv",
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )

    # ── Spot path ────────────────────────────────────────────────────────────
    if use_spot:
        df, spot_source = _fetch_spot_adjusted_ohlcv(symbol, timeframe)
        if df is not None:
            quality_flags: List[str] = []
            if validate:
                df, issues = validate_ohlcv(
                    df,
                    symbol,
                    timeframe,
                    source_type="synthetic_spot_from_futures",
                    trade_style=trade_style,
                )
                quality_flags.extend(issues)
                if issues:
                    logger.info(f"Spot OHLCV validation issues for {symbol}: {issues}")
            if df is not None:
                metadata = build_source_metadata(
                    symbol,
                    timeframe,
                    trade_style,
                    df,
                    spot_source or "spot_adjusted",
                    "synthetic_spot_from_futures",
                    False,
                    quality_flags,
                    reference_timestamp=time.time(),
                )
                with _ohlcv_lock:
                    _ohlcv_cache[cache_key] = {
                        "df": df,
                        "timestamp": time.time(),
                        "source": "spot_adjusted",
                        "spot_source": spot_source,
                        "metadata": metadata,
                    }
                bot_metrics.record_market_data_observation(metadata)
                return df
        logger.warning(f"Spot fetch failed for {symbol}, falling back to futures")
        _health_tracker.record_fallback("spot_api", "yfinance")

    # ── Futures / yfinance path ──────────────────────────────────────────────
    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
    df = fetch_yf_sync(symbol, period=period, interval=interval)

    if validate and df is not None:
        df, issues = validate_ohlcv(
            df,
            symbol,
            timeframe,
            source_type="futures",
            trade_style=trade_style,
        )
        if issues:
            logger.info(f"OHLCV validation issues for {symbol}: {issues}")

    if df is not None:
        metadata = build_source_metadata(
            symbol,
            timeframe,
            trade_style,
            df,
            "yfinance",
            "futures",
            False,
            issues if validate else [],
        )
        with _ohlcv_lock:
            _ohlcv_cache[cache_key] = {
                "df": df,
                "timestamp": time.time(),
                "source": "yfinance",
                "metadata": metadata,
            }
        bot_metrics.record_market_data_observation(metadata)

    return df


def get_ohlcv_with_metadata(
    symbol: str,
    timeframe: str,
    trade_style: str = "swing",
    validate: bool = True,
) -> Tuple[Optional[pd.DataFrame], Dict]:
    settings = _get_settings_safe()
    use_spot = (
        symbol in SPOT_PRICE_SYMBOLS
        and trade_style == "scalp"
        and settings is not None
        and settings.use_spot_prices
        and settings.xau_source_policy != "futures_only"
    )
    source_tag = "spot" if use_spot else "futures"
    cache_key = f"ohlcv:{symbol}:{timeframe}:{source_tag}"

    if settings:
        ttl = settings.ohlcv_cache_ttl_daily if timeframe == "1d" else settings.ohlcv_cache_ttl_intraday
    else:
        ttl = 300 if timeframe == "1d" else 5

    now = time.time()
    cache_lookup_started = time.perf_counter()
    with _ohlcv_lock:
        cached = _ohlcv_cache.get(cache_key)
        if cached and (now - cached["timestamp"]) < ttl:
            bot_metrics.record_latency(
                "cache.lookup",
                (time.perf_counter() - cache_lookup_started) * 1000,
                context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
            )
            bot_metrics.increment_counter(
                "cache.hit",
                label="ohlcv",
                context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
            )
            cached_source = cached.get("source", "unknown")
            cached_source_type = cached_source
            cached_quality_flags: List[str] = []
            reference_timestamp = None
            source_name = cached.get("spot_source") or cached_source
            if cached_source == "spot_adjusted":
                cached_source_type = "synthetic_spot_from_futures"
                cached_quality_flags.append("synthetic_spot")
                reference_timestamp = time.time()
            elif cached_source == "yfinance":
                cached_source_type = "futures"
            metadata = cached.get(
                "metadata",
                build_source_metadata(
                    symbol,
                    timeframe,
                    trade_style,
                    cached["df"],
                    source_name,
                    cached_source_type,
                    False,
                    cached_quality_flags,
                    reference_timestamp=reference_timestamp,
                ),
            )
            bot_metrics.record_market_data_observation(metadata)
            return cached["df"], metadata
    bot_metrics.record_latency(
        "cache.lookup",
        (time.perf_counter() - cache_lookup_started) * 1000,
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )
    bot_metrics.increment_counter(
        "cache.miss",
        label="ohlcv",
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )

    quality_flags: List[str] = []

    if use_spot:
        df, spot_source = _fetch_spot_adjusted_ohlcv(symbol, timeframe)
        if df is not None:
            if validate:
                df, issues = validate_ohlcv(
                    df,
                    symbol,
                    timeframe,
                    source_type="synthetic_spot_from_futures",
                    trade_style=trade_style,
                )
                quality_flags.extend(issues)
            if df is not None:
                metadata = build_source_metadata(
                    symbol,
                    timeframe,
                    trade_style,
                    df,
                    spot_source or "spot_adjusted",
                    "synthetic_spot_from_futures",
                    False,
                    quality_flags,
                    reference_timestamp=time.time(),
                )
                with _ohlcv_lock:
                    _ohlcv_cache[cache_key] = {
                        "df": df,
                        "timestamp": time.time(),
                        "source": "spot_adjusted",
                        "metadata": metadata,
                    }
                bot_metrics.record_market_data_observation(metadata)
                return df, metadata
        _health_tracker.record_fallback("spot_api", "yfinance")
        quality_flags.append("fallback_source")

    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
    df = fetch_yf_sync(symbol, period=period, interval=interval)

    if validate and df is not None:
        df, issues = validate_ohlcv(
            df,
            symbol,
            timeframe,
            source_type="futures",
            trade_style=trade_style,
        )
        quality_flags.extend(issues)

    metadata = build_source_metadata(
        symbol,
        timeframe,
        trade_style,
        df,
        "yfinance",
        "futures",
        use_spot,
        quality_flags,
    )

    if df is not None:
        with _ohlcv_lock:
            _ohlcv_cache[cache_key] = {
                "df": df,
                "timestamp": time.time(),
                "source": "yfinance",
                "metadata": metadata,
            }
        bot_metrics.record_market_data_observation(metadata)

    return df, metadata


def _fetch_spot_adjusted_ohlcv(symbol: str, timeframe: str) -> Tuple[Optional[pd.DataFrame], Optional[str]]:
    """Fetch futures OHLCV and adjust recent candles to spot price level.

    Only adjusts candles within the last 4 hours with full factor;
    older candles get a decayed adjustment to avoid historical distortion.
    """
    try:
        from trading_bot.forex_fetcher import ForexFetcher
    except ImportError:
        return None, None

    settings = _get_settings_safe()
    gold_api_key = settings.gold_api_key if settings else None

    try:
        import asyncio as _aio
        try:
            _loop = _aio.get_running_loop()
        except RuntimeError:
            _loop = None

        if _loop and _loop.is_running():
            # We're called from a sync context inside an async framework;
            # use asyncio.to_thread-safe pattern
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                spot_result = pool.submit(
                    lambda: _aio.run(_fetch_spot_async(symbol, gold_api_key))
                ).result(timeout=15)
        else:
            spot_result = _aio.run(_fetch_spot_async(symbol, gold_api_key))

        if spot_result is None:
            return None, None

        spot_price, spot_source = spot_result

    except Exception as e:
        logger.warning(f"Spot price fetch error for {symbol}: {e}")
        return None, None

    # Get futures baseline
    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
    futures_df = fetch_yf_sync(symbol, period=period, interval=interval)

    if futures_df is None or futures_df.empty:
        return None, spot_source

    # Calculate adjustment factor
    futures_current = float(futures_df["close"].iloc[-1])
    if futures_current <= 0:
        return None, spot_source

    adjustment_factor = spot_price / futures_current

    # Apply time-decayed adjustment: full for recent, decayed for older
    df = futures_df.copy()
    now_ts = time.time()
    full_adjust_window = 4 * 3600  # 4 hours: full adjustment
    decay_window = 24 * 3600      # 24 hours: linear decay to no adjustment

    for col in ["open", "high", "low", "close"]:
        if col not in df.columns:
            continue
        adjusted = df[col].copy()
        for i in range(len(df)):
            try:
                row_ts = df.index[i].timestamp() if hasattr(df.index[i], 'timestamp') else now_ts
            except Exception:
                row_ts = now_ts
            age = now_ts - row_ts
            if age <= full_adjust_window:
                # Full adjustment for recent candles
                adjusted.iloc[i] = df[col].iloc[i] * adjustment_factor
            elif age <= decay_window:
                # Linear decay from full to no adjustment
                decay = 1.0 - (age - full_adjust_window) / (decay_window - full_adjust_window)
                blended_factor = 1.0 + (adjustment_factor - 1.0) * decay
                adjusted.iloc[i] = df[col].iloc[i] * blended_factor
            # else: no adjustment — raw futures price
        df[col] = adjusted

    logger.info(
        f"Spot-adjusted {symbol}: futures={futures_current:.2f}, "
        f"spot={spot_price:.2f}, factor={adjustment_factor:.6f}, "
        f"source={spot_source}"
    )

    return df, spot_source


async def _fetch_spot_async(symbol: str, gold_api_key: Optional[str]) -> Optional[Tuple[float, str]]:
    """Async helper to fetch spot price."""
    from trading_bot.forex_fetcher import ForexFetcher
    async with ForexFetcher(gold_api_key=gold_api_key) as fetcher:
        if symbol == "XAU/USD":
            spot = await fetcher.fetch_xau_usd_spot()
        else:
            return None
        if spot:
            return spot.mid, spot.source
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def get_health_status() -> Dict:
    """Get health status for all data sources."""
    return _health_tracker.get_status()


def get_cache_info() -> Dict:
    """Get cache statistics."""
    with _ohlcv_lock:
        entries = len(_ohlcv_cache)
        oldest = min(
            (v["timestamp"] for v in _ohlcv_cache.values()),
            default=None,
        )
        sources = {}
        for v in _ohlcv_cache.values():
            src = v.get("source", "unknown")
            sources[src] = sources.get(src, 0) + 1

    return {
        "entries": entries,
        "oldest_entry_age_s": round(time.time() - oldest, 1) if oldest else None,
        "sources": sources,
    }


def clear_cache() -> None:
    """Clear the OHLCV cache."""
    with _ohlcv_lock:
        _ohlcv_cache.clear()
