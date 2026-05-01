# AI Bot latency and reliability metrics

ONE-28 adds lightweight process-local observability for AI prediction and scanner performance. Metrics are intended for development and release validation, not long-term production storage.

## Endpoint

Call:

```bash
curl http://localhost:8000/api/metrics/bot
```

The endpoint returns JSON with:

- `latency`: p50, p95, p99, average, min, max, latest, and sample count for each measured stage.
- `counters`: process-local reliability counts.
- `breakdowns`: labeled counts such as no-trade reasons and failed-symbol causes.
- `rates`: cache hit rate, stale-data rate, failed-symbol rate, prediction success rate, and scanner success rate.
- `thresholdsMs`: release-validation latency targets.

Metrics reset when the API process restarts.

## Latency stages

| Stage | Meaning | Target |
| --- | --- | --- |
| `prediction.endpoint` | End-to-end `/api/ai/score/{symbol}` latency | p95 <= 2500 ms |
| `scanner.batch` | End-to-end scanner batch latency for `/api/scanner/scan` | p95 <= 8000 ms |
| `market_data.fetch` | External yfinance market-data fetch latency | p95 <= 2000 ms |
| `prediction.feature_generation` | Technical indicator, pattern, level, and setup generation time | p95 <= 750 ms |
| `prediction.scoring` | AI score and anchor-history scoring time | p95 <= 250 ms |
| `cache.lookup` | OHLCV cache lookup latency | p95 <= 50 ms |

## Reliability counters and rates

- `cache.hit` / `cache.miss`: used to calculate `cacheHitRate`.
- `market_data.observation` / `market_data.stale`: used to calculate `staleDataRate`.
- `scanner.symbol_scanned` / `scanner.symbol_failed`: used to calculate `failedSymbolRate`.
- `prediction.success` / `prediction.failure`: used to calculate `predictionSuccessRate`.
- `scanner.success` / `scanner.failure`: used to calculate `scannerSuccessRate`.
- `no_trade_reason`: labeled count of why `/api/ai/score/{symbol}` predictions resolved to hold/no-trade, including `mixed_indicators`, `risk_reward_compressed`, `data_quality`, `low_confidence`, `structure_conflict`, and `other`.
- `external_api.error` and `external_api.timeout`: labeled by source for external provider failures.

## Release validation

Before release, exercise the AI score and scanner flows with representative symbols and confirm:

1. `prediction.endpoint.p95` is at or below 2500 ms.
2. `scanner.batch.p95` is at or below 8000 ms for the expected scanner batch size.
3. `market_data.fetch.p95` is at or below 2000 ms, or slow external providers are clearly visible.
4. `cacheHitRate` improves on repeated requests.
5. `staleDataRate`, `failedSymbolRate`, and `external_api.timeout` are reviewed for regressions.
6. `no_trade_reason` counts match expected market/data conditions.

## Privacy and safety

Metrics and logs must not include broker credentials, API tokens, account balances, full account identifiers, or sensitive account details. Current metric context is limited to endpoint, symbol, timeframe, trade style, source, status, and reason labels.