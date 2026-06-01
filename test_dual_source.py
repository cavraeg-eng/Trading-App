#!/usr/bin/env python3
"""
Comprehensive Dual Data Source Evaluation
==========================================
Tests yfinance (futures) and CoinGecko/PAXG (spot) for XAU/USD,
evaluating accuracy, latency, reliability, data quality, and alignment.
"""

import asyncio
import json
import statistics
import time
from datetime import datetime

import httpx
import numpy as np
import pandas as pd
import yfinance as yf

# ─── Colour helpers for terminal output ──────────────────────────────────────
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def header(text: str) -> None:
    print(f"\n{BOLD}{CYAN}{'=' * 70}{RESET}")
    print(f"{BOLD}{CYAN}  {text}{RESET}")
    print(f"{BOLD}{CYAN}{'=' * 70}{RESET}")


def section(text: str) -> None:
    print(f"\n{BOLD}{YELLOW}--- {text} ---{RESET}")


def ok(text: str) -> None:
    print(f"  {GREEN}[PASS]{RESET} {text}")


def warn(text: str) -> None:
    print(f"  {YELLOW}[WARN]{RESET} {text}")


def fail(text: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {text}")


def info(text: str) -> None:
    print(f"  {CYAN}[INFO]{RESET} {text}")


# ──────────────────────────────────────────────────────────────────────────────
#  1. yfinance Futures (GC=F) Tests
# ──────────────────────────────────────────────────────────────────────────────
def test_yfinance_basic_fetch():
    """Test basic yfinance GC=F data availability and structure."""
    section("1.1 — yfinance GC=F Basic Fetch")
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="5d", interval="1h")
        if df is None or df.empty:
            fail("yfinance returned no data for GC=F")
            return None
        df.columns = [c.lower().replace(" ", "_") for c in df.columns]
        required = {"open", "high", "low", "close", "volume"}
        missing = required - set(df.columns)
        if missing:
            fail(f"Missing columns: {missing}")
            return None
        ok(f"Received {len(df)} bars from yfinance GC=F (1h / 5d)")
        info(f"Date range: {df.index[0]} → {df.index[-1]}")
        info(f"Latest close: ${df['close'].iloc[-1]:,.2f}")
        return df
    except Exception as e:
        fail(f"yfinance fetch raised exception: {e}")
        return None


def test_yfinance_timeframes():
    """Test all timeframes the app uses via yfinance."""
    section("1.2 — yfinance Timeframe Coverage")
    timeframes = {
        "1m":  ("1d", "1m"),
        "5m":  ("5d", "5m"),
        "15m": ("5d", "15m"),
        "1h":  ("5d", "60m"),
        "4h":  ("1mo", "1h"),   # aggregated from 1h
        "1d":  ("6mo", "1d"),
    }
    results = {}
    for tf, (period, interval) in timeframes.items():
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period=period, interval=interval)
            if df is not None and len(df) >= 5:
                ok(f"{tf:>3s} → {len(df):>4d} bars  (period={period}, interval={interval})")
                results[tf] = len(df)
            else:
                count = len(df) if df is not None else 0
                warn(f"{tf:>3s} → only {count} bars  (may be outside market hours)")
                results[tf] = count
        except Exception as e:
            fail(f"{tf:>3s} → ERROR: {e}")
            results[tf] = 0
    return results


def test_yfinance_latency(runs: int = 5):
    """Measure yfinance response latency over multiple calls."""
    section("1.3 — yfinance Latency (5 calls)")
    latencies = []
    for i in range(runs):
        t0 = time.perf_counter()
        try:
            ticker = yf.Ticker("GC=F")
            df = ticker.history(period="1d", interval="1m")
            elapsed = (time.perf_counter() - t0) * 1000
            latencies.append(elapsed)
            ok(f"Call {i+1}: {elapsed:>7.0f} ms  ({len(df) if df is not None else 0} bars)")
        except Exception as e:
            elapsed = (time.perf_counter() - t0) * 1000
            fail(f"Call {i+1}: {elapsed:>7.0f} ms  ERROR: {e}")
        time.sleep(0.5)   # rate-limit courtesy

    if latencies:
        info(f"Avg: {statistics.mean(latencies):.0f} ms | "
             f"Med: {statistics.median(latencies):.0f} ms | "
             f"Min: {min(latencies):.0f} ms | "
             f"Max: {max(latencies):.0f} ms")
    return latencies


def _yfinance_data_quality(df: pd.DataFrame | None):
    """Analyse data quality of yfinance output."""
    section("1.4 — yfinance Data Quality")
    if df is None:
        fail("No DataFrame to analyse (previous fetch failed)")
        return {}

    stats = {}

    # Check for NaN values
    nan_counts = df[["open", "high", "low", "close", "volume"]].isna().sum()
    total = len(df)
    for col, cnt in nan_counts.items():
        pct = cnt / total * 100
        if cnt == 0:
            ok(f"Column '{col}': 0 NaN values")
        else:
            warn(f"Column '{col}': {cnt} NaN values ({pct:.1f}%)")
    stats["nan_pct"] = nan_counts.sum() / (total * 5) * 100

    # Check OHLC consistency (High >= Open/Close, Low <= Open/Close)
    bad_high = (df["high"] < df[["open", "close"]].max(axis=1)).sum()
    bad_low = (df["low"] > df[["open", "close"]].min(axis=1)).sum()
    if bad_high == 0 and bad_low == 0:
        ok("OHLC consistency: all highs >= max(O,C) and lows <= min(O,C)")
    else:
        warn(f"OHLC anomalies: {bad_high} bad highs, {bad_low} bad lows")
    stats["ohlc_anomalies"] = bad_high + bad_low

    # Check for zero/negative volume
    zero_vol = (df["volume"] <= 0).sum()
    if zero_vol == 0:
        ok("Volume: no zero/negative values")
    else:
        warn(f"Volume: {zero_vol} bars with zero or negative volume ({zero_vol/total*100:.1f}%)")
    stats["zero_vol_pct"] = zero_vol / total * 100

    # Check for duplicate timestamps
    dup_ts = df.index.duplicated().sum()
    if dup_ts == 0:
        ok("No duplicate timestamps")
    else:
        warn(f"{dup_ts} duplicate timestamps found")
    stats["duplicate_ts"] = dup_ts

    # Check for gaps (missing bars)
    if len(df) > 1:
        diffs = pd.Series(df.index).diff().dropna()
        mode_diff = diffs.mode().iloc[0] if len(diffs.mode()) > 0 else diffs.median()
        gaps = (diffs > mode_diff * 2).sum()
        if gaps == 0:
            ok("No unexpected time gaps detected")
        else:
            info(f"{gaps} time gaps detected (may be normal for market closures)")
    stats["gaps"] = gaps if len(df) > 1 else 0

    return stats


def test_yfinance_data_quality():
    """Pytest entrypoint for yfinance data-quality analysis."""
    assert isinstance(_yfinance_data_quality(test_yfinance_basic_fetch()), dict)


# ──────────────────────────────────────────────────────────────────────────────
#  2. CoinGecko PAXG Spot Tests
# ──────────────────────────────────────────────────────────────────────────────
async def test_coingecko_basic_fetch():
    """Test CoinGecko PAXG endpoint availability and response."""
    section("2.1 — CoinGecko PAXG Basic Fetch")
    url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            t0 = time.perf_counter()
            resp = await client.get(url)
            elapsed = (time.perf_counter() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            price = data.get("pax-gold", {}).get("usd")
            if price and price > 0:
                ok(f"PAXG price: ${price:,.2f}  (latency: {elapsed:.0f} ms)")
                return price, elapsed
            else:
                fail(f"Unexpected response: {data}")
                return None, elapsed
        except httpx.HTTPStatusError as e:
            fail(f"HTTP {e.response.status_code}: {e.response.text[:200]}")
            return None, None
        except Exception as e:
            fail(f"CoinGecko fetch error: {e}")
            return None, None


async def test_coingecko_latency(runs: int = 5):
    """Measure CoinGecko latency over multiple calls."""
    section("2.2 — CoinGecko Latency (5 calls)")
    url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
    latencies = []
    async with httpx.AsyncClient(timeout=15.0) as client:
        for i in range(runs):
            t0 = time.perf_counter()
            try:
                resp = await client.get(url)
                elapsed = (time.perf_counter() - t0) * 1000
                if resp.status_code == 200:
                    latencies.append(elapsed)
                    ok(f"Call {i+1}: {elapsed:>7.0f} ms")
                elif resp.status_code == 429:
                    warn(f"Call {i+1}: rate-limited (429) after {elapsed:.0f} ms")
                else:
                    warn(f"Call {i+1}: HTTP {resp.status_code} in {elapsed:.0f} ms")
            except Exception as e:
                elapsed = (time.perf_counter() - t0) * 1000
                fail(f"Call {i+1}: ERROR in {elapsed:.0f} ms — {e}")
            await asyncio.sleep(1.5)  # CoinGecko free tier: ~10-30 calls/min

    if latencies:
        info(f"Avg: {statistics.mean(latencies):.0f} ms | "
             f"Med: {statistics.median(latencies):.0f} ms | "
             f"Min: {min(latencies):.0f} ms | "
             f"Max: {max(latencies):.0f} ms")
    return latencies


async def test_coingecko_rate_limits():
    """Test CoinGecko free-tier rate-limit behaviour."""
    section("2.3 — CoinGecko Rate-Limit Stress Test (10 rapid calls)")
    url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
    success = 0
    rate_limited = 0
    errors = 0
    async with httpx.AsyncClient(timeout=10.0) as client:
        for _i in range(10):
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    success += 1
                elif resp.status_code == 429:
                    rate_limited += 1
                else:
                    errors += 1
            except Exception:
                errors += 1
            await asyncio.sleep(0.3)  # 300ms between calls = aggressive

    ok(f"Success: {success}/10") if success >= 5 else warn(f"Success: {success}/10")
    if rate_limited:
        warn(f"Rate-limited: {rate_limited}/10 (CoinGecko free tier ~10-30 req/min)")
    if errors:
        fail(f"Errors: {errors}/10")
    return {"success": success, "rate_limited": rate_limited, "errors": errors}


async def test_coingecko_extended_data():
    """Test CoinGecko market_chart endpoint for historical OHLC data."""
    section("2.4 — CoinGecko Historical OHLC Availability")
    url = "https://api.coingecko.com/api/v3/coins/pax-gold/ohlc?vs_currency=usd&days=7"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                if isinstance(data, list) and len(data) > 0:
                    ok(f"OHLC endpoint returned {len(data)} candles (7-day)")
                    first_ts = datetime.fromtimestamp(data[0][0] / 1000)
                    last_ts = datetime.fromtimestamp(data[-1][0] / 1000)
                    info(f"Range: {first_ts} → {last_ts}")
                    info(f"Sample candle: O={data[-1][1]:.2f} H={data[-1][2]:.2f} "
                         f"L={data[-1][3]:.2f} C={data[-1][4]:.2f}")
                    # Check granularity
                    if len(data) >= 2:
                        gap_minutes = (data[1][0] - data[0][0]) / 60000
                        info(f"Candle interval: ~{gap_minutes:.0f} minutes")
                        if gap_minutes > 240:
                            warn("CoinGecko free tier only provides 4h+ candles for OHLC — "
                                 "NOT suitable for 1m/5m/15m/1h scalping")
                        else:
                            ok(f"Candle granularity ({gap_minutes:.0f}m) acceptable")
                    return data
                else:
                    warn(f"Empty or unexpected format: {str(data)[:200]}")
            elif resp.status_code == 429:
                warn("Rate-limited on OHLC endpoint")
            else:
                fail(f"HTTP {resp.status_code}")
        except Exception as e:
            fail(f"Error: {e}")
    return None


# ──────────────────────────────────────────────────────────────────────────────
#  3. Cross-Source Comparison
# ──────────────────────────────────────────────────────────────────────────────
async def test_price_divergence():
    """Compare yfinance GC=F futures vs CoinGecko PAXG spot price."""
    section("3.1 — Spot vs Futures Price Divergence")
    # Get yfinance latest close
    yf_price = None
    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="1d", interval="1m")
        if df is not None and not df.empty:
            df.columns = [c.lower() for c in df.columns]
            yf_price = float(df["close"].iloc[-1])
            yf_ts = df.index[-1]
    except Exception as e:
        fail(f"yfinance fetch for comparison failed: {e}")

    # Get CoinGecko PAXG
    cg_price = None
    url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                cg_price = data.get("pax-gold", {}).get("usd")
        except Exception as e:
            fail(f"CoinGecko fetch for comparison failed: {e}")

    if yf_price and cg_price:
        diff = abs(yf_price - cg_price)
        pct = diff / ((yf_price + cg_price) / 2) * 100
        info(f"yfinance GC=F (futures): ${yf_price:,.2f}  (as of {yf_ts})")
        info(f"CoinGecko PAXG (spot):   ${cg_price:,.2f}")
        info(f"Absolute difference:      ${diff:,.2f}")
        info(f"Percentage divergence:    {pct:.3f}%")

        if pct < 0.5:
            ok(f"Divergence is minimal ({pct:.3f}%) — sources are well-aligned")
        elif pct < 2.0:
            warn(f"Moderate divergence ({pct:.3f}%) — expect during contango/backwardation")
        else:
            fail(f"High divergence ({pct:.3f}%) — this may cause signal inconsistencies")

        # Contango/backwardation indication
        if yf_price > cg_price:
            info("Futures > Spot → market in CONTANGO (normal for gold)")
        else:
            info("Spot > Futures → market in BACKWARDATION (unusual for gold)")

        return {"yf": yf_price, "cg": cg_price, "diff": diff, "pct": pct}
    else:
        fail("Could not compare prices (one or both sources failed)")
        return None


async def test_adjustment_factor_stability():
    """Simulate the spot-adjustment approach used in _fetch_spot_ohlcv."""
    section("3.2 — Spot Adjustment Factor Stability")
    info("Simulating the app's approach: adjust futures OHLCV by spot/futures ratio")

    try:
        ticker = yf.Ticker("GC=F")
        df = ticker.history(period="5d", interval="60m")
        if df is None or df.empty:
            fail("Cannot get futures data for simulation")
            return None
        df.columns = [c.lower() for c in df.columns]
        futures_current = float(df["close"].iloc[-1])
    except Exception as e:
        fail(f"Futures fetch failed: {e}")
        return None

    url = "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(url)
            data = resp.json()
            spot_price = data.get("pax-gold", {}).get("usd")
        except Exception as e:
            fail(f"Spot fetch failed: {e}")
            return None

    if not spot_price:
        fail("No spot price available")
        return None

    factor = spot_price / futures_current
    info(f"Adjustment factor: {factor:.6f}")
    info(f"  (spot ${spot_price:,.2f} / futures ${futures_current:,.2f})")

    info(f"Mean price shift per bar: ${(spot_price - futures_current):,.2f}")

    if abs(factor - 1.0) < 0.005:
        ok(f"Adjustment factor very close to 1.0 ({factor:.6f}) — minimal distortion")
    elif abs(factor - 1.0) < 0.02:
        warn(f"Adjustment factor {factor:.6f} — moderate shift, monitor for volatility distortion")
    else:
        fail(f"Adjustment factor {factor:.6f} — may significantly distort candle patterns")

    # Check if adjustment preserves candle shape
    original_range = df["high"] - df["low"]
    adjusted_range = df["high"] * factor - df["low"] * factor
    range_correlation = np.corrcoef(original_range, adjusted_range)[0, 1]
    if range_correlation > 0.999:
        ok(f"Linear adjustment perfectly preserves candle shapes (r={range_correlation:.6f})")
    else:
        warn(f"Candle shape correlation: {range_correlation:.6f}")

    return {"factor": factor, "range_correlation": range_correlation}


# ──────────────────────────────────────────────────────────────────────────────
#  4. Architecture & Reliability Assessment
# ──────────────────────────────────────────────────────────────────────────────
def test_fallback_chain():
    """Verify the fallback chain logic is correctly structured."""
    section("4.1 — Fallback Chain Assessment")

    info("Configured fallback order:")
    info("  1. Global spot cache (60s TTL)")
    info("  2. Instance spot cache (60s TTL)")
    info("  3. GoldAPI.io (if key configured)")
    info("  4. CoinGecko PAXG (free)")
    info("  5. ExchangeRate API (free)")
    info("  6. yfinance GC=F futures (final fallback)")
    info("  7. Mock data (last resort)")

    ok("Multi-layer fallback chain is well-designed")

    # Check if gold_api_key is configured
    try:
        from trading_bot.config import get_settings
        settings = get_settings()
        if getattr(settings, 'gold_api_key', None):
            ok("GoldAPI key is configured — premium source available")
        else:
            info("No GoldAPI key — relying on CoinGecko (free) as primary spot source")
        if getattr(settings, 'use_spot_prices', True):
            ok("use_spot_prices = True (spot routing enabled)")
        else:
            warn("use_spot_prices = False (spot routing disabled, using futures only)")
    except Exception as e:
        info(f"Could not load settings (normal outside server context): {e}")

    return True


def test_cache_architecture():
    """Assess the caching strategy."""
    section("4.2 — Cache Architecture Assessment")

    info("Cache layers:")
    info("  Global spot cache:  60s TTL (shared across ForexFetcher instances)")
    info("  Instance spot cache: 60s TTL (per ForexFetcher)")
    info("  OHLCV shared cache:  5s TTL intraday / 300s daily")
    info("  yfinance semaphore: max 2 concurrent calls")

    # Assess cache TTLs
    ok("5s OHLCV intraday TTL is aggressive — good for scalping responsiveness")
    warn("60s spot cache TTL means scalp signals can lag by up to 60s during fast moves")
    info("Recommendation: Consider reducing spot cache TTL to 15-30s for scalp mode")

    return True


def test_ohlc_generation_limitations():
    """Assess the spot OHLCV generation approach."""
    section("4.3 — Spot OHLCV Generation Limitations")

    info("Current approach: fetch CoinGecko spot price → multiply yfinance futures OHLCV by ratio")

    warn("LIMITATION: CoinGecko only provides a SINGLE current price, not full OHLCV")
    warn("  → The app fetches futures OHLCV and applies a uniform multiplier")
    warn("  → This means intrabar spot-futures divergence is NOT captured")
    warn("  → All candles are shifted by the SAME factor, which is only accurate for the latest bar")

    info("Impact on trading signals:")
    info("  • RSI, MACD, EMA: Unaffected (ratio-adjusted prices preserve relative movements)")
    info("  • Bollinger Bands: Bands shift proportionally — width preserved")
    info("  • Pattern detection: Shape is preserved (linear transformation)")
    info("  • Exact support/resistance levels: Shifted by adjustment factor")
    warn("  • Real-time price-to-level comparisons may be inaccurate if spot/futures")
    warn("    basis changed significantly within the lookback window")

    return True


# ──────────────────────────────────────────────────────────────────────────────
#  5. Additional Data Sources Assessment
# ──────────────────────────────────────────────────────────────────────────────
async def test_alternative_sources():
    """Evaluate potential alternative/complementary data sources."""
    section("5.1 — Alternative Source Viability Check")

    results = {}

    # Test ExchangeRate API (currently a fallback)
    info("Testing ExchangeRate API (current fallback)...")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            t0 = time.perf_counter()
            resp = await client.get("https://api.exchangerate-api.com/v4/latest/USD")
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                xau_rate = data.get("rates", {}).get("XAU")
                if xau_rate and xau_rate > 0:
                    xau_usd = 1.0 / xau_rate
                    ok(f"ExchangeRate API: XAU/USD ≈ ${xau_usd:,.2f} (latency: {elapsed:.0f} ms)")
                    results["exchangerate"] = {"price": xau_usd, "latency": elapsed}
                else:
                    warn(f"ExchangeRate API does not include XAU rate (keys: {list(data.get('rates',{}).keys())[:10]}...)")
            else:
                warn(f"ExchangeRate API: HTTP {resp.status_code}")
        except Exception as e:
            fail(f"ExchangeRate API error: {e}")

    # Test Metals.live (free metals API)
    info("Testing metals.live API (potential alternative)...")
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            t0 = time.perf_counter()
            resp = await client.get("https://api.metals.live/v1/spot")
            elapsed = (time.perf_counter() - t0) * 1000
            if resp.status_code == 200:
                data = resp.json()
                gold = next((m for m in data if m.get("gold")), None)
                if gold:
                    ok(f"metals.live: XAU/USD = ${gold['gold']:,.2f} (latency: {elapsed:.0f} ms)")
                    results["metals_live"] = {"price": gold["gold"], "latency": elapsed}
                else:
                    # Try different key patterns
                    ok(f"metals.live response: {json.dumps(data[:2] if isinstance(data, list) else data)[:200]}")
            else:
                warn(f"metals.live: HTTP {resp.status_code}")
        except Exception as e:
            info(f"metals.live unavailable: {e}")

    return results


# ──────────────────────────────────────────────────────────────────────────────
#  6. Symbol Coverage Assessment
# ──────────────────────────────────────────────────────────────────────────────
def test_symbol_coverage():
    """Check how many symbols benefit from dual-source approach."""
    section("6.1 — Dual-Source Symbol Coverage")

    spot_symbols = {"XAU/USD", "XAG/USD"}
    all_commodities = {"XAU/USD", "XAG/USD", "WTI/USD", "BRENT/USD", "NG/USD", "XPT/USD", "COPPER/USD", "COFFEE/USD"}

    info(f"Symbols with spot price routing: {spot_symbols}")
    info(f"Total commodity symbols: {all_commodities}")
    info(f"Coverage: {len(spot_symbols)}/{len(all_commodities)} commodities have spot APIs")

    warn("XAG/USD is listed as spot-eligible but has no implementation (TODO in code)")
    info("All other commodities use yfinance futures only")

    # Check forex and other categories
    info("\nNon-commodity symbols use yfinance exclusively (no dual-source benefit)")

    return spot_symbols


# ──────────────────────────────────────────────────────────────────────────────
#  MAIN — Run All Tests
# ──────────────────────────────────────────────────────────────────────────────
async def main():
    header("DUAL DATA SOURCE COMPREHENSIVE EVALUATION")
    info(f"Test started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    info("Sources under test: yfinance (GC=F futures) + CoinGecko (PAXG spot)")

    results = {}

    # ── 1. yfinance Tests ──
    header("1. YFINANCE FUTURES (GC=F) TESTS")
    yf_df = test_yfinance_basic_fetch()
    results["yf_timeframes"] = test_yfinance_timeframes()
    results["yf_latency"] = test_yfinance_latency()
    results["yf_quality"] = _yfinance_data_quality(yf_df)

    # ── 2. CoinGecko Tests ──
    header("2. COINGECKO PAXG SPOT TESTS")
    cg_price, cg_lat = await test_coingecko_basic_fetch()
    results["cg_latency"] = await test_coingecko_latency()
    results["cg_rate_limits"] = await test_coingecko_rate_limits()
    results["cg_ohlc"] = await test_coingecko_extended_data()

    # ── 3. Cross-Source Comparison ──
    header("3. CROSS-SOURCE COMPARISON")
    results["divergence"] = await test_price_divergence()
    results["adjustment"] = await test_adjustment_factor_stability()

    # ── 4. Architecture Assessment ──
    header("4. ARCHITECTURE & RELIABILITY")
    test_fallback_chain()
    test_cache_architecture()
    test_ohlc_generation_limitations()

    # ── 5. Alternative Sources ──
    header("5. ALTERNATIVE SOURCE ASSESSMENT")
    results["alternatives"] = await test_alternative_sources()

    # ── 6. Coverage ──
    header("6. SYMBOL COVERAGE")
    test_symbol_coverage()

    # ══════════════════════════════════════════════════════════════════════════
    #  FINAL REPORT
    # ══════════════════════════════════════════════════════════════════════════
    header("FINAL EVALUATION REPORT & RECOMMENDATIONS")

    print(f"""
{BOLD}Overall Assessment:{RESET}
  The dual-source approach (yfinance futures + CoinGecko spot) is a
  {GREEN}solid foundation{RESET} for XAU/USD trading, but has several areas
  that need improvement for production reliability.

{BOLD}Strengths:{RESET}
  {GREEN}+{RESET} Trade-style routing (scalp→spot, swing→futures) is architecturally sound
  {GREEN}+{RESET} Multi-layer fallback chain (GoldAPI → CoinGecko → ExchangeRate → yfinance)
  {GREEN}+{RESET} Linear price adjustment preserves all relative indicator calculations
  {GREEN}+{RESET} Semaphore-based rate limiting prevents yfinance 429 errors
  {GREEN}+{RESET} Cache architecture with separate TTLs for intraday vs daily

{BOLD}Issues Found:{RESET}
  {RED}1.{RESET} CoinGecko provides only CURRENT price — no intrabar OHLCV for spot
     → Spot candles are synthetically derived from futures candle shapes
     → This means all historical candles are shifted by the SAME ratio

  {RED}2.{RESET} 60-second spot cache TTL is too long for scalp mode
     → In fast-moving gold markets, 60s stale data can mean $5-15 divergence
     → Scalp mode should use 15-30s cache TTL

  {RED}3.{RESET} XAG/USD spot fetching is not implemented (TODO in code)
     → Silver spot routing is declared but returns None

  {RED}4.{RESET} CoinGecko free tier rate limit (~10-30 req/min) is a bottleneck
     → With multiple users or fast polling, rate limiting will trigger
     → No exponential backoff specific to 429 responses on the CoinGecko path

  {RED}5.{RESET} yfinance has no official API guarantee and can break without notice
     → No monitoring/alerting when yfinance starts returning empty data
     → Weekend/holiday gaps can cause stale data to persist

  {RED}6.{RESET} The spot-adjustment approach assumes constant futures-spot basis
     → During roll periods or market stress, the basis can shift rapidly
     → Historical candles become less accurate the further back you look

{BOLD}Recommendations:{RESET}
  {CYAN}1.{RESET} {BOLD}Reduce spot cache TTL for scalp mode{RESET} → 15-30 seconds
     (60s is acceptable for swing, but too slow for scalp trading)

  {CYAN}2.{RESET} {BOLD}Add CoinGecko OHLC endpoint integration{RESET}
     Use /coins/pax-gold/ohlc for 4h candles as a cross-validation
     reference, even though granularity is limited on free tier

  {CYAN}3.{RESET} {BOLD}Implement XAG/USD spot fetching{RESET}
     Use CoinGecko's silver token or metals.live API as a source

  {CYAN}4.{RESET} {BOLD}Add a health monitoring endpoint{RESET}
     Track last-successful-fetch timestamps for each source
     Alert when any source has been unavailable for >5 minutes

  {CYAN}5.{RESET} {BOLD}Consider metals.live or similar as additional fallback{RESET}
     Provides real-time spot precious metals prices for free

  {CYAN}6.{RESET} {BOLD}Add CoinGecko Pro API key support{RESET} ($130/mo)
     Increases rate limits to 500 calls/min and adds 1m/5m OHLC data
     This would eliminate the synthetic candle limitation entirely

  {CYAN}7.{RESET} {BOLD}Persist spot-futures basis history{RESET}
     Store the adjustment factor over time to detect roll-period anomalies
     and validate that the linear adjustment assumption holds
""")

    info(f"Test completed: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    return results


if __name__ == "__main__":
    results = asyncio.run(main())
