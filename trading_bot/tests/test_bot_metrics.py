from fastapi.testclient import TestClient

from trading_bot.api.server import app
from trading_bot.monitoring.bot_metrics import BotMetricsCollector, bot_metrics, classify_no_trade_reason


def test_bot_metrics_latency_percentiles_are_deterministic():
    collector = BotMetricsCollector(stages=("prediction.endpoint",))

    for sample in [10, 20, 30, 40, 50]:
        collector.record_latency("prediction.endpoint", sample)

    stats = collector.snapshot()["latency"]["prediction.endpoint"]
    assert stats["count"] == 5
    assert stats["avgMs"] == 30
    assert stats["p50Ms"] == 30
    assert stats["p95Ms"] == 50
    assert stats["p99Ms"] == 50


def test_bot_metrics_counters_and_rates_aggregate():
    collector = BotMetricsCollector()

    collector.increment_counter("cache.hit", label="ohlcv")
    collector.increment_counter("cache.miss", label="ohlcv")
    collector.increment_counter("market_data.observation", amount=2)
    collector.increment_counter("market_data.stale", label="yfinance")
    collector.increment_counter("scanner.symbol_scanned", amount=4)
    collector.increment_counter("scanner.symbol_failed", label="market_data_unavailable")
    collector.increment_counter("no_trade_reason", label=classify_no_trade_reason("indicators are mixed"))

    snapshot = collector.snapshot()
    assert snapshot["rates"]["cacheHitRate"] == 0.5
    assert snapshot["rates"]["staleDataRate"] == 0.5
    assert snapshot["rates"]["failedSymbolRate"] == 0.25
    assert snapshot["breakdowns"]["no_trade_reason"]["mixed_indicators"] == 1


def test_bot_metrics_endpoint_shape_is_stable():
    bot_metrics.reset()
    bot_metrics.record_latency("prediction.endpoint", 12.5)
    bot_metrics.increment_counter("prediction.success")

    client = TestClient(app)
    response = client.get("/api/metrics/bot")

    assert response.status_code == 200
    payload = response.json()
    assert "latency" in payload
    assert "counters" in payload
    assert "rates" in payload
    assert "thresholdsMs" in payload
    assert payload["latency"]["prediction.endpoint"]["count"] == 1
    assert payload["counters"]["prediction.success"] == 1
    assert "credentials" in payload["privacy"]