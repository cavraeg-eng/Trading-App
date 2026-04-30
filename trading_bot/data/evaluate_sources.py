"""Data source evaluation harness.

Run this module to produce a comprehensive diagnostic report on the
current dual-source data collection system. Measures accuracy, reliability,
consistency, and performance across all data sources and app endpoints.

Usage:
    python -m trading_bot.data.evaluate_sources
"""

import asyncio
import statistics
import time
from datetime import datetime
from typing import Dict, List, Optional

import pandas as pd

from trading_bot.config import get_logger

logger = get_logger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────────────────────────

class SourceTestResult:
    """Container for a single source test result."""
    def __init__(self, source: str, symbol: str):
        self.source = source
        self.symbol = symbol
        self.success = False
        self.price: Optional[float] = None
        self.latency_ms: float = 0
        self.error: Optional[str] = None
        self.rows: int = 0
        self.issues: List[str] = []
        self.metadata: Dict = {}


def _fmt_price(p: Optional[float]) -> str:
    return f"${p:,.2f}" if p is not None else "N/A"


def _fmt_ms(ms: float) -> str:
    return f"{ms:.0f}ms"


# ─────────────────────────────────────────────────────────────────────────────
# Individual source tests
# ─────────────────────────────────────────────────────────────────────────────

def test_yfinance_fetch(symbol: str, timeframe: str = "1h") -> SourceTestResult:
    """Test yfinance data fetch for a symbol."""
    from trading_bot.data.market_data_service import fetch_yf_sync, TIMEFRAME_MAP
    result = SourceTestResult("yfinance", symbol)
    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))

    t0 = time.time()
    try:
        df = fetch_yf_sync(symbol, period=period, interval=interval)
        result.latency_ms = (time.time() - t0) * 1000
        if df is not None and not df.empty:
            result.success = True
            result.price = float(df["close"].iloc[-1])
            result.rows = len(df)

            # Check for data quality issues
            from trading_bot.data.data_validator import validate_ohlcv
            _, issues = validate_ohlcv(df, symbol, timeframe)
            result.issues = issues
        else:
            result.error = "Empty or None response"
    except Exception as e:
        result.latency_ms = (time.time() - t0) * 1000
        result.error = str(e)

    return result


async def test_spot_sources(symbol: str = "XAU/USD") -> List[SourceTestResult]:
    """Test all spot price sources individually."""
    import httpx
    results = []

    # Test goldapi.io (only if key available)
    from trading_bot.config import get_settings
    settings = get_settings()

    if settings.gold_api_key:
        r = SourceTestResult("goldapi.io", symbol)
        t0 = time.time()
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(
                    f"https://www.goldapi.io/api/XAU/USD",
                    headers={"x-access-token": settings.gold_api_key},
                )
                r.latency_ms = (time.time() - t0) * 1000
                resp.raise_for_status()
                data = resp.json()
                r.price = data.get("price", 0)
                r.success = r.price > 0
        except Exception as e:
            r.latency_ms = (time.time() - t0) * 1000
            r.error = str(e)
        results.append(r)

    # Test metals.live
    r = SourceTestResult("metals.live", symbol)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get("https://api.metals.live/v1/spot")
            r.latency_ms = (time.time() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            for metal in data:
                if metal.get("gold") is not None:
                    r.price = float(metal["gold"])
                    r.success = r.price > 0
                    break
    except Exception as e:
        r.latency_ms = (time.time() - t0) * 1000
        r.error = str(e)
    results.append(r)

    # Test CoinGecko PAXG
    r = SourceTestResult("coingecko-paxg", symbol)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/simple/price"
                "?ids=pax-gold&vs_currencies=usd"
            )
            r.latency_ms = (time.time() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            r.price = data.get("pax-gold", {}).get("usd")
            r.success = r.price is not None and r.price > 0
    except Exception as e:
        r.latency_ms = (time.time() - t0) * 1000
        r.error = str(e)
    results.append(r)

    # Test exchangerate-api.com
    r = SourceTestResult("exchangerate-api", symbol)
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(
                "https://api.exchangerate-api.com/v4/latest/USD"
            )
            r.latency_ms = (time.time() - t0) * 1000
            resp.raise_for_status()
            data = resp.json()
            xau_rate = data.get("rates", {}).get("XAU")
            if xau_rate and xau_rate > 0:
                r.price = 1 / xau_rate if xau_rate < 1 else xau_rate
                r.success = True
    except Exception as e:
        r.latency_ms = (time.time() - t0) * 1000
        r.error = str(e)
    results.append(r)

    # Test yfinance GC=F
    r = test_yfinance_fetch("XAU/USD", "1h")
    r.source = "yfinance-GC=F"
    results.append(r)

    return results


def test_endpoint_consistency(symbol: str = "XAU/USD", timeframe: str = "1h") -> Dict:
    """Test if all app endpoints return consistent prices for the same symbol."""
    from trading_bot.data.market_data_service import get_ohlcv

    prices = {}

    # Market data service (swing = futures)
    df = get_ohlcv(symbol, timeframe, trade_style="swing")
    if df is not None and not df.empty:
        prices["market_service_swing"] = float(df["close"].iloc[-1])

    # Market data service (scalp = spot-adjusted if enabled)
    df = get_ohlcv(symbol, timeframe, trade_style="scalp")
    if df is not None and not df.empty:
        prices["market_service_scalp"] = float(df["close"].iloc[-1])

    # Direct yfinance (for comparison)
    from trading_bot.data.market_data_service import fetch_yf_sync, TIMEFRAME_MAP
    period, interval = TIMEFRAME_MAP.get(timeframe, ("5d", "60m"))
    df_raw = fetch_yf_sync(symbol, period=period, interval=interval)
    if df_raw is not None and not df_raw.empty:
        prices["yfinance_direct"] = float(df_raw["close"].iloc[-1])

    # Check deviations
    if len(prices) >= 2:
        all_vals = list(prices.values())
        max_dev = (max(all_vals) - min(all_vals)) / statistics.mean(all_vals) * 100
    else:
        max_dev = 0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "prices": prices,
        "max_deviation_pct": round(max_dev, 4),
        "consistent": max_dev < 1.0,  # <1% deviation is acceptable
    }


def test_rate_limit_resilience(symbol: str = "EUR/USD", burst_count: int = 10) -> Dict:
    """Test how the system handles burst traffic."""
    from trading_bot.data.market_data_service import get_ohlcv

    successes = 0
    failures = 0
    latencies = []

    for i in range(burst_count):
        t0 = time.time()
        try:
            df = get_ohlcv(symbol, "1h")
            lat = (time.time() - t0) * 1000
            latencies.append(lat)
            if df is not None:
                successes += 1
            else:
                failures += 1
        except Exception:
            failures += 1
            latencies.append((time.time() - t0) * 1000)

    return {
        "burst_count": burst_count,
        "successes": successes,
        "failures": failures,
        "success_rate_pct": round(successes / burst_count * 100, 1),
        "median_latency_ms": round(statistics.median(latencies), 1) if latencies else 0,
        "p95_latency_ms": round(
            sorted(latencies)[int(len(latencies) * 0.95)] if latencies else 0, 1
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Full evaluation report
# ─────────────────────────────────────────────────────────────────────────────

async def run_full_evaluation() -> Dict:
    """Run the complete data source evaluation suite.

    Returns a structured report with all test results.
    """
    report: Dict = {
        "timestamp": datetime.utcnow().isoformat(),
        "tests": {},
    }

    print("=" * 70)
    print("DATA SOURCE EVALUATION REPORT")
    print("=" * 70)
    print(f"Timestamp: {datetime.utcnow().isoformat()}")
    print()

    # ── 1. Spot source comparison ────────────────────────────────────────────
    print("─" * 50)
    print("1. SPOT PRICE SOURCE COMPARISON (XAU/USD)")
    print("─" * 50)

    spot_results = await test_spot_sources("XAU/USD")
    report["tests"]["spot_sources"] = []

    reference_price = None
    for r in spot_results:
        status = "OK" if r.success else "FAIL"
        print(f"  {r.source:20s} │ {status:4s} │ {_fmt_price(r.price):>12s} │ {_fmt_ms(r.latency_ms):>8s}")
        if r.error:
            print(f"  {'':20s} │ Error: {r.error}")
        report["tests"]["spot_sources"].append({
            "source": r.source, "success": r.success,
            "price": r.price, "latency_ms": r.latency_ms,
            "error": r.error,
        })
        # Use first successful non-PAXG source as reference
        if r.success and r.price and reference_price is None and "paxg" not in r.source:
            reference_price = r.price

    # Cross-source deviation
    successful_prices = [r.price for r in spot_results if r.success and r.price]
    if len(successful_prices) >= 2:
        max_dev = (max(successful_prices) - min(successful_prices)) / statistics.mean(successful_prices) * 100
        print(f"\n  Max cross-source deviation: {max_dev:.3f}%")
        report["tests"]["spot_source_max_deviation_pct"] = round(max_dev, 3)

        # PAXG-specific deviation
        paxg_price = next((r.price for r in spot_results if r.source == "coingecko-paxg" and r.success), None)
        if paxg_price and reference_price:
            paxg_dev = abs(paxg_price - reference_price) / reference_price * 100
            print(f"  PAXG vs reference deviation: {paxg_dev:.3f}%")
            report["tests"]["paxg_deviation_pct"] = round(paxg_dev, 3)

    # ── 2. yfinance reliability across symbols ───────────────────────────────
    print()
    print("─" * 50)
    print("2. YFINANCE RELIABILITY (multi-symbol)")
    print("─" * 50)

    test_symbols = ["EUR/USD", "GBP/USD", "BTC/USD", "XAU/USD", "US500"]
    yf_results = []
    for sym in test_symbols:
        r = test_yfinance_fetch(sym)
        yf_results.append(r)
        status = "OK" if r.success else "FAIL"
        issues_str = f" [{', '.join(r.issues)}]" if r.issues else ""
        print(f"  {sym:12s} │ {status:4s} │ {_fmt_price(r.price):>12s} │ {r.rows:>4d} bars │ {_fmt_ms(r.latency_ms):>8s}{issues_str}")

    yf_success_rate = sum(1 for r in yf_results if r.success) / len(yf_results) * 100
    yf_avg_latency = statistics.mean(r.latency_ms for r in yf_results)
    print(f"\n  Success rate: {yf_success_rate:.0f}% │ Avg latency: {_fmt_ms(yf_avg_latency)}")
    report["tests"]["yfinance"] = {
        "success_rate_pct": round(yf_success_rate, 1),
        "avg_latency_ms": round(yf_avg_latency, 1),
        "results": [{"symbol": r.symbol, "success": r.success, "rows": r.rows,
                      "latency_ms": r.latency_ms, "issues": r.issues, "error": r.error}
                     for r in yf_results],
    }

    # ── 3. Endpoint consistency ──────────────────────────────────────────────
    print()
    print("─" * 50)
    print("3. ENDPOINT CONSISTENCY (XAU/USD)")
    print("─" * 50)

    consistency = test_endpoint_consistency("XAU/USD", "1h")
    for endpoint, price in consistency["prices"].items():
        print(f"  {endpoint:25s} │ {_fmt_price(price)}")
    print(f"\n  Max deviation: {consistency['max_deviation_pct']:.4f}%")
    print(f"  Consistent: {'YES' if consistency['consistent'] else 'NO — sources disagree'}")
    report["tests"]["endpoint_consistency"] = consistency

    # ── 4. Rate limit resilience ─────────────────────────────────────────────
    print()
    print("─" * 50)
    print("4. RATE LIMIT RESILIENCE (10-request burst)")
    print("─" * 50)

    burst = test_rate_limit_resilience("EUR/USD", burst_count=10)
    print(f"  Success: {burst['successes']}/{burst['burst_count']} ({burst['success_rate_pct']}%)")
    print(f"  Median latency: {_fmt_ms(burst['median_latency_ms'])}")
    print(f"  P95 latency: {_fmt_ms(burst['p95_latency_ms'])}")
    report["tests"]["rate_limit_resilience"] = burst

    # ── 5. Health status ─────────────────────────────────────────────────────
    print()
    print("─" * 50)
    print("5. DATA SOURCE HEALTH STATUS")
    print("─" * 50)

    from trading_bot.data.market_data_service import get_health_status
    health = get_health_status()
    for source, metrics in health.items():
        print(f"  {source:20s} │ {metrics['status']:8s} │ "
              f"ok={metrics['success_count']} fail={metrics['failure_count']} "
              f"fallback={metrics['fallback_count']}")
        if metrics.get("median_latency_ms"):
            print(f"  {'':20s} │ latency: median={metrics['median_latency_ms']}ms"
                  f" p95={metrics.get('p95_latency_ms', 'N/A')}ms")
    report["tests"]["health_status"] = health

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("SUMMARY & RECOMMENDATIONS")
    print("=" * 70)

    issues_found = []

    if yf_success_rate < 100:
        issues_found.append(f"yfinance reliability: {yf_success_rate:.0f}% (some symbols failed)")
    if not consistency["consistent"]:
        issues_found.append(f"Endpoint inconsistency: {consistency['max_deviation_pct']:.3f}% deviation")
    if burst["success_rate_pct"] < 100:
        issues_found.append(f"Rate limit pressure: {burst['failures']} failures in burst test")
    if report["tests"].get("paxg_deviation_pct", 0) > 0.5:
        issues_found.append(f"PAXG deviation: {report['tests']['paxg_deviation_pct']:.3f}% from spot reference")

    if issues_found:
        print("  Issues found:")
        for issue in issues_found:
            print(f"    - {issue}")
    else:
        print("  All tests passed. Data sources are operating within acceptable parameters.")

    report["summary"] = {
        "issues_found": len(issues_found),
        "issues": issues_found,
        "overall_status": "degraded" if issues_found else "healthy",
    }

    print()
    return report


# ─────────────────────────────────────────────────────────────────────────────
# CLI entry point
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    asyncio.run(run_full_evaluation())
