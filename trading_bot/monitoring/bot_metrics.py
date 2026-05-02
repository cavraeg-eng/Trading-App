"""In-memory AI bot latency and reliability metrics."""

from __future__ import annotations

import math
import threading
import time
from collections import Counter, defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Dict, Iterable, Iterator, Mapping, Optional

from trading_bot.config import get_logger

logger = get_logger(__name__)

DEFAULT_LATENCY_STAGES = (
    "prediction.endpoint",
    "scanner.batch",
    "market_data.fetch",
    "prediction.feature_generation",
    "prediction.scoring",
    "cache.lookup",
)

TARGET_THRESHOLDS_MS = {
    "prediction.endpoint.p95": 2500,
    "scanner.batch.p95": 8000,
    "market_data.fetch.p95": 2000,
    "prediction.feature_generation.p95": 750,
    "prediction.scoring.p95": 250,
    "cache.lookup.p95": 50,
}

MAX_SAMPLES_PER_STAGE = 1000


def _utc_now() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


def _safe_label(value: object) -> str:
    text = str(value or "unknown").strip().lower()
    text = text.replace(" ", "_").replace("-", "_")
    return "".join(char for char in text if char.isalnum() or char in {"_", ".", "/"})[:80] or "unknown"


def _percentile(samples: Iterable[float], percentile: float) -> Optional[float]:
    values = sorted(float(sample) for sample in samples)
    if not values:
        return None
    if len(values) == 1:
        return round(values[0], 2)
    rank = math.ceil((percentile / 100.0) * len(values)) - 1
    rank = max(0, min(rank, len(values) - 1))
    return round(values[rank], 2)


def _stats(samples: list[float]) -> dict:
    if not samples:
        return {
            "count": 0,
            "avgMs": None,
            "minMs": None,
            "maxMs": None,
            "p50Ms": None,
            "p95Ms": None,
            "p99Ms": None,
            "latestMs": None,
        }
    return {
        "count": len(samples),
        "avgMs": round(sum(samples) / len(samples), 2),
        "minMs": round(min(samples), 2),
        "maxMs": round(max(samples), 2),
        "p50Ms": _percentile(samples, 50),
        "p95Ms": _percentile(samples, 95),
        "p99Ms": _percentile(samples, 99),
        "latestMs": round(samples[-1], 2),
    }


def _rate(numerator: int, denominator: int) -> Optional[float]:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 4)


def classify_no_trade_reason(reason: str) -> str:
    normalized = reason.lower()
    if "data quality" in normalized or "stale" in normalized or "degraded" in normalized:
        return "data_quality"
    if "reward-to-risk" in normalized or "compressed" in normalized:
        return "risk_reward_compressed"
    if "mixed" in normalized or "no clear direction" in normalized:
        return "mixed_indicators"
    if "confidence" in normalized or "conviction" in normalized:
        return "low_confidence"
    if "structure" in normalized:
        return "structure_conflict"
    return "other"


class BotMetricsCollector:
    """Thread-safe process-local metrics for development observability."""

    def __init__(self, stages: Iterable[str] = DEFAULT_LATENCY_STAGES) -> None:
        self._known_stages = set(stages)
        self._timings: Dict[str, list[float]] = defaultdict(list)
        self._counters: Counter[str] = Counter()
        self._breakdowns: Dict[str, Counter[str]] = defaultdict(Counter)
        self._lock = threading.RLock()
        self._started_at = time.time()

    def record_latency(
        self,
        stage: str,
        duration_ms: float,
        *,
        request_id: Optional[str] = None,
        context: Optional[Mapping[str, object]] = None,
    ) -> None:
        duration = max(0.0, float(duration_ms))
        safe_context = self._safe_context(context)
        with self._lock:
            self._known_stages.add(stage)
            samples = self._timings[stage]
            samples.append(duration)
            if len(samples) > MAX_SAMPLES_PER_STAGE:
                del samples[: len(samples) - MAX_SAMPLES_PER_STAGE]
        logger.info(
            "ai_bot_latency_metric",
            metric=stage,
            duration_ms=round(duration, 2),
            request_id=request_id,
            **safe_context,
        )

    @contextmanager
    def timer(
        self,
        stage: str,
        *,
        request_id: Optional[str] = None,
        context: Optional[Mapping[str, object]] = None,
    ) -> Iterator[None]:
        start = time.perf_counter()
        try:
            yield
        finally:
            self.record_latency(
                stage,
                (time.perf_counter() - start) * 1000,
                request_id=request_id,
                context=context,
            )

    def increment_counter(
        self,
        name: str,
        amount: int = 1,
        *,
        label: Optional[str] = None,
        request_id: Optional[str] = None,
        context: Optional[Mapping[str, object]] = None,
    ) -> None:
        safe_context = self._safe_context(context)
        safe_label = _safe_label(label) if label is not None else None
        with self._lock:
            self._counters[name] += amount
            if safe_label is not None:
                self._breakdowns[name][safe_label] += amount
        logger.info(
            "ai_bot_reliability_metric",
            metric=name,
            amount=amount,
            label=safe_label,
            request_id=request_id,
            **safe_context,
        )

    def record_market_data_observation(
        self,
        metadata: Mapping[str, object],
        *,
        request_id: Optional[str] = None,
    ) -> None:
        source = metadata.get("sourceName") or metadata.get("sourceType") or "unknown"
        flags = metadata.get("qualityFlags") or []
        market_status = metadata.get("marketStatus")
        is_stale = market_status == "stale" or any(str(flag).startswith("stale_data") for flag in flags)
        context = {
            "symbol": metadata.get("symbol"),
            "timeframe": metadata.get("timeframe"),
            "trade_style": metadata.get("tradeStyle"),
            "source": source,
        }
        self.increment_counter("market_data.observation", request_id=request_id, context=context)
        if is_stale:
            self.increment_counter(
                "market_data.stale",
                label=str(source),
                request_id=request_id,
                context=context,
            )

    def snapshot(self) -> dict:
        with self._lock:
            timings = {stage: list(self._timings.get(stage, [])) for stage in sorted(self._known_stages)}
            counters = dict(self._counters)
            breakdowns = {
                name: dict(counter)
                for name, counter in self._breakdowns.items()
                if counter
            }
            started_at = self._started_at

        cache_hits = counters.get("cache.hit", 0)
        cache_misses = counters.get("cache.miss", 0)
        market_observations = counters.get("market_data.observation", 0)
        scanner_symbols = counters.get("scanner.symbol_scanned", 0)
        prediction_success = counters.get("prediction.success", 0)
        prediction_failure = counters.get("prediction.failure", 0)
        scanner_success = counters.get("scanner.success", 0)
        scanner_failure = counters.get("scanner.failure", 0)

        return {
            "generatedAt": _utc_now(),
            "processStartedAt": datetime.fromtimestamp(started_at, tz=timezone.utc).isoformat(),
            "processUptimeSeconds": round(time.time() - started_at, 2),
            "latency": {stage: _stats(samples) for stage, samples in timings.items()},
            "counters": counters,
            "breakdowns": breakdowns,
            "rates": {
                "cacheHitRate": _rate(cache_hits, cache_hits + cache_misses),
                "staleDataRate": _rate(counters.get("market_data.stale", 0), market_observations),
                "failedSymbolRate": _rate(counters.get("scanner.symbol_failed", 0), scanner_symbols),
                "predictionSuccessRate": _rate(
                    prediction_success,
                    prediction_success + prediction_failure,
                ),
                "scannerSuccessRate": _rate(scanner_success, scanner_success + scanner_failure),
            },
            "thresholdsMs": TARGET_THRESHOLDS_MS,
            "sampleWindow": {
                "maxSamplesPerLatencyStage": MAX_SAMPLES_PER_STAGE,
                "persistence": "process_memory_only",
            },
            "privacy": "Metrics must not contain broker credentials, API tokens, account balances, or full account identifiers.",
        }

    def reset(self) -> None:
        with self._lock:
            self._timings.clear()
            self._counters.clear()
            self._breakdowns.clear()
            self._started_at = time.time()

    def _safe_context(self, context: Optional[Mapping[str, object]]) -> dict:
        if not context:
            return {}
        allowed = {
            "endpoint",
            "symbol",
            "timeframe",
            "trade_style",
            "source",
            "status",
            "reason",
        }
        return {
            key: value
            for key, value in context.items()
            if key in allowed and value is not None
        }


bot_metrics = BotMetricsCollector()