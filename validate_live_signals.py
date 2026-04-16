from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Dict, List, Optional

import httpx


TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

DEFAULT_SYMBOLS = ["XAU/USD", "EUR/USD", "GBP/USD", "BTC/USD"]


@dataclass
class HorizonAssessment:
    seconds: int
    end_price: float
    delta: float
    delta_pct: float
    outcome: str


@dataclass
class SignalAssessment:
    symbol: str
    batch: int
    timeframe: str
    trade_style: str
    signal_id: str
    direction: str
    confidence: float
    start_price: float
    end_price: float
    delta: float
    delta_pct: float
    atr: float
    threshold: float
    observed_range: float
    one_minute_outcome: str
    three_minute_outcome: str
    timing: str
    time_to_favorable_seconds: Optional[float]
    time_to_unfavorable_seconds: Optional[float]
    market_regime: str
    regime_aligned: Optional[bool]
    alignment_score: int
    dominant_direction: str
    alignment_aligned: Optional[bool]
    ai_score: int
    ai_label: str
    ai_factors: Dict[str, float]
    pattern_name: Optional[str]
    pattern_direction: Optional[str]
    pattern_confidence: Optional[float]
    pattern_aligned: Optional[bool]
    backtest_win_rate: Optional[float]
    backtest_profit_factor: Optional[float]
    backtest_profitable_percent: Optional[float]
    confidence_error: float
    resolved_reason: Optional[str]
    persisted_direction_correct: Optional[bool]
    source_name: Optional[str]
    source_type: Optional[str]
    quality_flags: List[str]
    discrepancies: List[str]
    horizons: List[HorizonAssessment]


def normalize_signal(value: Optional[str]) -> str:
    raw = str(value or "").upper()
    if raw in {"BUY", "SELL", "HOLD"}:
        return raw
    if raw in {"BULLISH", "STRONG_BUY"}:
        return "BUY"
    if raw in {"BEARISH", "STRONG_SELL"}:
        return "SELL"
    return "HOLD"


def fetch_json(client: httpx.Client, method: str, path: str, **kwargs) -> dict:
    response = client.request(method, path, **kwargs)
    response.raise_for_status()
    return response.json()


def evaluate_outcome(direction: str, delta: float, threshold: float) -> str:
    if direction == "BUY":
        if delta >= threshold:
            return "correct"
        if delta <= -threshold:
            return "incorrect"
        return "flat"
    if direction == "SELL":
        if delta <= -threshold:
            return "correct"
        if delta >= threshold:
            return "incorrect"
        return "flat"
    if abs(delta) <= threshold:
        return "correct"
    return "incorrect"


def directional_probability(direction: str, horizon_outcome: str) -> Optional[float]:
    if direction not in {"BUY", "SELL", "HOLD"}:
        return None
    if horizon_outcome == "correct":
        return 1.0
    if horizon_outcome == "incorrect":
        return 0.0
    return 0.5


def discrepancy_score(item: SignalAssessment) -> int:
    score = 0
    for issue in item.discrepancies:
        if "1m direction opposed" in issue:
            score += 4
        elif "3m follow-through opposed" in issue:
            score += 3
        elif "market regime" in issue:
            score += 2
        elif "top pattern direction conflicted" in issue:
            score += 2
        elif "data quality flags" in issue:
            score += 1
        elif "confidence remained high" in issue:
            score += 2
        else:
            score += 1
    return score


def evaluate_alignment(direction: str, delta: float, threshold: float) -> Optional[bool]:
    if direction == "BUY":
        return delta >= threshold
    if direction == "SELL":
        return delta <= -threshold
    if direction == "HOLD":
        return abs(delta) <= threshold * 1.25
    return None


def evaluate_regime(regime: str, delta: float, threshold: float, observed_range: float, atr: float) -> Optional[bool]:
    if regime == "trending_up":
        return delta >= threshold
    if regime == "trending_down":
        return delta <= -threshold
    if regime == "ranging":
        return abs(delta) <= threshold * 1.25 and observed_range <= max(threshold * 2.5, atr * 0.45)
    if regime == "volatile":
        return observed_range >= max(threshold * 2.5, atr * 0.8)
    return None


def determine_timing(
    direction: str,
    prices: List[tuple[float, float]],
    start_price: float,
    threshold: float,
    observation_seconds: int,
) -> tuple[str, Optional[float], Optional[float]]:
    favorable_time = None
    unfavorable_time = None

    for elapsed, price in prices:
        delta = price - start_price
        if direction == "BUY":
            if favorable_time is None and delta >= threshold:
                favorable_time = elapsed
            if unfavorable_time is None and delta <= -threshold:
                unfavorable_time = elapsed
        elif direction == "SELL":
            if favorable_time is None and delta <= -threshold:
                favorable_time = elapsed
            if unfavorable_time is None and delta >= threshold:
                unfavorable_time = elapsed

    if direction == "HOLD":
        return "n/a", None, None
    if unfavorable_time is not None and (favorable_time is None or unfavorable_time < favorable_time):
        return "adverse", favorable_time, unfavorable_time
    if favorable_time is None:
        return "missed", None, unfavorable_time
    if favorable_time <= observation_seconds / 2:
        return "early", favorable_time, unfavorable_time
    return "late", favorable_time, unfavorable_time


def safe_float(value: object, default: float = 0.0) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(converted) or math.isinf(converted):
        return default
    return converted


def query_persisted_outcome(db_path: Path, signal_id: str) -> tuple[Optional[str], Optional[bool]]:
    if not db_path.exists():
        return None, None
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT resolved_reason, direction_correct FROM signal_outcomes WHERE signal_id = ?",
            (signal_id,),
        ).fetchone()
        if row is None:
            return None, None
        direction_correct = row["direction_correct"]
        return row["resolved_reason"], (bool(direction_correct) if direction_correct is not None else None)
    finally:
        conn.close()


def build_report(config: dict, results: List[SignalAssessment], status: str) -> dict:
    return {
        "config": config,
        "status": status,
        "summary": summarize_results(results),
        "results": [asdict(item) for item in results],
    }


def write_report(output_path: Path, report: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2))


def summarize_results(results: List[SignalAssessment]) -> dict:
    def count_outcomes(items: List[SignalAssessment], attr: str) -> Dict[str, int]:
        summary = {"correct": 0, "incorrect": 0, "flat": 0}
        for item in items:
            summary[getattr(item, attr)] = summary.get(getattr(item, attr), 0) + 1
        return summary

    one_minute = count_outcomes(results, "one_minute_outcome")
    three_minute = count_outcomes(results, "three_minute_outcome")
    actionable_one_minute = one_minute["correct"] + one_minute["incorrect"]
    actionable_three_minute = three_minute["correct"] + three_minute["incorrect"]

    regime_checks = [item.regime_aligned for item in results if item.regime_aligned is not None]
    alignment_checks = [item.alignment_aligned for item in results if item.alignment_aligned is not None]
    pattern_checks = [item.pattern_aligned for item in results if item.pattern_aligned is not None]
    persisted_checks = [item.persisted_direction_correct for item in results if item.persisted_direction_correct is not None]

    timing_summary: Dict[str, int] = {}
    for item in results:
        timing_summary[item.timing] = timing_summary.get(item.timing, 0) + 1

    by_symbol: Dict[str, dict] = {}
    calibration_buckets: Dict[str, List[SignalAssessment]] = {
        "40-54": [],
        "55-64": [],
        "65-74": [],
        "75-100": [],
    }
    for symbol in sorted({item.symbol for item in results}):
        symbol_items = [item for item in results if item.symbol == symbol]
        symbol_actionable = [item for item in symbol_items if item.one_minute_outcome in {"correct", "incorrect"}]
        symbol_accuracy = (
            round(sum(1 for item in symbol_actionable if item.one_minute_outcome == "correct") / len(symbol_actionable) * 100, 1)
            if symbol_actionable
            else None
        )
        by_symbol[symbol] = {
            "samples": len(symbol_items),
            "oneMinuteAccuracy": symbol_accuracy,
            "averageConfidence": round(mean(item.confidence for item in symbol_items), 1),
            "averageAiScore": round(mean(item.ai_score for item in symbol_items), 1),
            "averageAlignmentScore": round(mean(item.alignment_score for item in symbol_items), 1),
            "backtestWinRate": round(mean(item.backtest_win_rate for item in symbol_items if item.backtest_win_rate is not None), 1)
            if any(item.backtest_win_rate is not None for item in symbol_items)
            else None,
            "discrepancies": sum(len(item.discrepancies) for item in symbol_items),
        }

    for item in results:
        if item.confidence < 55:
            calibration_buckets["40-54"].append(item)
        elif item.confidence < 65:
            calibration_buckets["55-64"].append(item)
        elif item.confidence < 75:
            calibration_buckets["65-74"].append(item)
        else:
            calibration_buckets["75-100"].append(item)

    calibration_summary = {}
    for bucket, items in calibration_buckets.items():
        if not items:
            calibration_summary[bucket] = {
                "samples": 0,
                "avgConfidence": None,
                "realizedOneMinute": None,
                "realizedThreeMinute": None,
            }
            continue

        one_vals = [
            value for value in (
                directional_probability(item.direction, item.one_minute_outcome) for item in items
            ) if value is not None
        ]
        three_vals = [
            value for value in (
                directional_probability(item.direction, item.three_minute_outcome) for item in items
            ) if value is not None
        ]
        calibration_summary[bucket] = {
            "samples": len(items),
            "avgConfidence": round(mean(item.confidence for item in items), 1),
            "realizedOneMinute": round(mean(one_vals) * 100, 1) if one_vals else None,
            "realizedThreeMinute": round(mean(three_vals) * 100, 1) if three_vals else None,
        }

    return {
        "samples": len(results),
        "oneMinute": {
            "correct": one_minute["correct"],
            "incorrect": one_minute["incorrect"],
            "flat": one_minute["flat"],
            "accuracyExFlat": round(one_minute["correct"] / actionable_one_minute * 100, 1) if actionable_one_minute else None,
        },
        "threeMinute": {
            "correct": three_minute["correct"],
            "incorrect": three_minute["incorrect"],
            "flat": three_minute["flat"],
            "accuracyExFlat": round(three_minute["correct"] / actionable_three_minute * 100, 1) if actionable_three_minute else None,
        },
        "confidence": {
            "averageConfidence": round(mean(item.confidence for item in results), 1) if results else None,
            "averageConfidenceError": round(mean(item.confidence_error for item in results), 3) if results else None,
        },
        "marketRegimeAccuracy": round(sum(1 for value in regime_checks if value) / len(regime_checks) * 100, 1) if regime_checks else None,
        "alignmentAccuracy": round(sum(1 for value in alignment_checks if value) / len(alignment_checks) * 100, 1) if alignment_checks else None,
        "patternAccuracy": round(sum(1 for value in pattern_checks if value) / len(pattern_checks) * 100, 1) if pattern_checks else None,
        "persistedOutcomeAccuracy": round(sum(1 for value in persisted_checks if value) / len(persisted_checks) * 100, 1) if persisted_checks else None,
        "timing": timing_summary,
        "confidenceCalibration": calibration_summary,
        "bySymbol": by_symbol,
        "discrepancyScore": sum(discrepancy_score(item) for item in results),
        "discrepancies": [
            {
                "symbol": item.symbol,
                "batch": item.batch,
                "signalId": item.signal_id,
                "severity": discrepancy_score(item),
                "issues": item.discrepancies,
            }
            for item in results
            if item.discrepancies
        ],
    }


def render_markdown(summary: dict, results: List[SignalAssessment], config: dict) -> str:
    lines = [
        "# Live Signal Validation Report",
        "",
        f"- Run started: {config['startedAt']}",
        f"- Base URL: {config['baseUrl']}",
        f"- Symbols: {', '.join(config['symbols'])}",
        f"- Timeframe: {config['timeframe']}",
        f"- Trade style: {config['tradeStyle']}",
        f"- Observation seconds per batch: {config['observationSeconds']}",
        f"- Poll interval seconds: {config['pollSeconds']}",
        f"- Batches: {config['batches']}",
        "",
        "## Summary",
        "",
        f"- Samples: {summary['samples']}",
        f"- 1m directional accuracy (ex flat): {summary['oneMinute']['accuracyExFlat']}%",
        f"- 3m directional accuracy (ex flat): {summary['threeMinute']['accuracyExFlat']}%",
        f"- Avg confidence: {summary['confidence']['averageConfidence']}%",
        f"- Avg confidence error: {summary['confidence']['averageConfidenceError']}",
        f"- Market regime alignment accuracy: {summary['marketRegimeAccuracy']}%",
        f"- Multi-timeframe alignment accuracy: {summary['alignmentAccuracy']}%",
        f"- Pattern guidance accuracy: {summary['patternAccuracy']}%",
        f"- Persisted outcome accuracy: {summary['persistedOutcomeAccuracy']}%",
        f"- Timing distribution: {summary['timing']}",
        f"- Discrepancy score: {summary['discrepancyScore']}",
        "",
        "## Confidence Calibration",
        "",
    ]

    for bucket, item in summary["confidenceCalibration"].items():
        lines.append(
            f"- **{bucket}**: samples={item['samples']}, avg confidence={item['avgConfidence']}, "
            f"realized 1m={item['realizedOneMinute']}%, realized 3m={item['realizedThreeMinute']}%"
        )

    lines.extend([
        "",
        "## Symbol Breakdown",
        "",
    ])

    for symbol, data in summary["bySymbol"].items():
        lines.append(
            f"- **{symbol}**: samples={data['samples']}, 1m accuracy={data['oneMinuteAccuracy']}%, "
            f"avg confidence={data['averageConfidence']}%, avg AI score={data['averageAiScore']}, "
            f"avg alignment={data['averageAlignmentScore']}, backtest win rate={data['backtestWinRate']}%"
        )

    lines.extend(["", "## Sample Details", ""])
    for item in results:
        lines.append(
            f"- **{item.symbol} batch {item.batch}** `{item.direction}` conf {round(item.confidence)}% | "
            f"1m={item.one_minute_outcome} | 3m={item.three_minute_outcome} | "
            f"timing={item.timing} | regime={item.market_regime} ({item.regime_aligned}) | "
            f"alignment={item.alignment_score} ({item.alignment_aligned}) | "
            f"AI={item.ai_score}/{item.ai_label} | persisted={item.persisted_direction_correct} | "
            f"issues={'; '.join(item.discrepancies) if item.discrepancies else 'none'}"
        )

    return "\n".join(lines) + "\n"


def run_validation(
    base_url: str,
    symbols: List[str],
    timeframe: str,
    trade_style: str,
    observation_seconds: int,
    poll_seconds: int,
    batches: int,
    backtest_lookback_days: int,
    db_path: Path,
    progress_path: Optional[Path] = None,
) -> dict:
    started_at = datetime.now(timezone.utc).isoformat()
    results: List[SignalAssessment] = []
    timeout = httpx.Timeout(30.0, connect=10.0)
    config = {
        "startedAt": started_at,
        "baseUrl": base_url,
        "symbols": symbols,
        "timeframe": timeframe,
        "tradeStyle": trade_style,
        "observationSeconds": observation_seconds,
        "pollSeconds": poll_seconds,
        "batches": batches,
        "dbPath": str(db_path),
    }

    with httpx.Client(base_url=base_url, timeout=timeout) as client:
        health = fetch_json(client, "GET", "/api/health")
        if health.get("status") != "healthy":
            raise RuntimeError(f"API health check failed: {health}")

        for batch in range(1, batches + 1):
            print(f"[validator] starting batch {batch}/{batches}", flush=True)
            batch_state = []

            for symbol in symbols:
                fetch_json(client, "POST", f"/api/signals/reset/{symbol}")
                breakdown = fetch_json(
                    client,
                    "GET",
                    f"/api/signals/breakdown/{symbol}",
                    params={"timeframe": timeframe, "trade_style": trade_style},
                )
                analysis = fetch_json(
                    client,
                    "GET",
                    f"/api/market/analysis/{symbol}",
                    params={"timeframe": timeframe, "trade_style": trade_style},
                )
                alignment = fetch_json(
                    client,
                    "GET",
                    f"/api/ai/alignment/{symbol}",
                    params={"trade_style": trade_style},
                )
                direction = normalize_signal(breakdown.get("direction") or analysis.get("signal"))
                backtest_payload = {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "direction": direction.lower(),
                    "lookback_days": backtest_lookback_days,
                }
                backtest = fetch_json(client, "POST", "/api/backtest/signal", json=backtest_payload)
                start_price = safe_float(analysis.get("currentPrice"), safe_float(breakdown.get("entry_max")))
                atr = max(safe_float(analysis.get("atr"), 0.0), start_price * 0.0002)
                threshold = max(atr * 0.05, start_price * 0.0001)
                batch_state.append(
                    {
                        "symbol": symbol,
                        "breakdown": breakdown,
                        "analysis": analysis,
                        "alignment": alignment,
                        "backtest": backtest,
                        "direction": direction,
                        "start_price": start_price,
                        "atr": atr,
                        "threshold": threshold,
                        "prices": [(0.0, start_price)],
                    }
                )

            started = time.monotonic()
            next_poll = poll_seconds
            while next_poll <= observation_seconds:
                sleep_for = started + next_poll - time.monotonic()
                if sleep_for > 0:
                    time.sleep(sleep_for)
                elapsed = min(observation_seconds, int(round(time.monotonic() - started)))
                for item in batch_state:
                    quote = fetch_json(
                        client,
                        "GET",
                        f"/api/market/quote/{item['symbol']}",
                        params={"timeframe": timeframe, "trade_style": trade_style},
                    )
                    item["prices"].append((float(elapsed), safe_float(quote.get("currentPrice"), item["prices"][-1][1])))
                next_poll += poll_seconds

            for item in batch_state:
                final_breakdown = fetch_json(
                    client,
                    "GET",
                    f"/api/signals/breakdown/{item['symbol']}",
                    params={"timeframe": timeframe, "trade_style": trade_style},
                )
                signal_id = str(item["breakdown"].get("signal_id"))
                direction = item["direction"]
                prices = item["prices"]
                start_price = item["start_price"]
                end_price = prices[-1][1]
                delta = end_price - start_price
                delta_pct = (delta / start_price * 100) if start_price else 0.0
                observed_prices = [point[1] for point in prices]
                observed_range = max(observed_prices) - min(observed_prices) if observed_prices else 0.0
                one_minute_price = min(prices, key=lambda point: abs(point[0] - 60.0))[1]
                one_minute_delta = one_minute_price - start_price
                one_minute_delta_pct = (one_minute_delta / start_price * 100) if start_price else 0.0
                threshold = item["threshold"]
                one_minute_outcome = evaluate_outcome(direction, one_minute_delta, threshold)
                three_minute_outcome = evaluate_outcome(direction, delta, threshold)
                timing, favorable_time, unfavorable_time = determine_timing(
                    direction,
                    prices,
                    start_price,
                    threshold,
                    observation_seconds,
                )

                analysis = item["analysis"]
                alignment = item["alignment"]
                backtest = item["backtest"]
                ai_score = analysis.get("aiScore") or {}
                ai_factors = ai_score.get("factors") or {}
                patterns = analysis.get("patterns") or []
                top_pattern = patterns[0] if patterns else None
                dominant_direction = normalize_signal(alignment.get("dominantDirection"))
                market_regime = str(analysis.get("marketRegime") or "unknown")
                regime_aligned = evaluate_regime(market_regime, delta, threshold, observed_range, item["atr"])
                alignment_aligned = evaluate_alignment(dominant_direction, delta, threshold)
                pattern_direction = None
                if top_pattern:
                    if top_pattern.get("direction") == "bullish":
                        pattern_direction = "BUY"
                    elif top_pattern.get("direction") == "bearish":
                        pattern_direction = "SELL"
                pattern_aligned = evaluate_alignment(pattern_direction or "", delta, threshold) if pattern_direction else None
                realized = 1.0 if one_minute_outcome == "correct" else 0.0 if one_minute_outcome == "incorrect" else 0.5
                confidence = safe_float(item["breakdown"].get("confidence"), safe_float(analysis.get("confidence"), 50.0))
                confidence_error = abs((confidence / 100.0) - realized)

                discrepancies: List[str] = []
                if one_minute_outcome == "incorrect":
                    discrepancies.append("1m direction opposed realized move")
                if three_minute_outcome == "incorrect":
                    discrepancies.append("3m follow-through opposed realized move")
                if one_minute_outcome == "flat" and confidence >= 70:
                    discrepancies.append("high confidence produced flat 1m move")
                if regime_aligned is False:
                    discrepancies.append(f"market regime {market_regime} mismatched realized behavior")
                if alignment.get("alignmentScore", 0) >= 70 and alignment_aligned is False:
                    discrepancies.append("high multi-timeframe alignment missed realized direction")
                if pattern_aligned is False:
                    discrepancies.append("top pattern direction conflicted with realized move")
                if direction in {"BUY", "SELL"} and ai_score.get("value", 0) >= 65 and one_minute_outcome == "incorrect":
                    discrepancies.append("favorable AI score missed 1m direction")
                if ai_factors.get("marketRegimeFit", 100) < 50 and confidence >= 65:
                    discrepancies.append("confidence remained high despite weak regime fit")
                quality_flags = list((analysis.get("sourceMetadata") or {}).get("qualityFlags") or [])
                if quality_flags:
                    discrepancies.append(f"data quality flags: {', '.join(quality_flags)}")

                time.sleep(2)
                resolved_reason, persisted_direction_correct = query_persisted_outcome(db_path, signal_id)

                results.append(
                    SignalAssessment(
                        symbol=item["symbol"],
                        batch=batch,
                        timeframe=timeframe,
                        trade_style=trade_style,
                        signal_id=signal_id,
                        direction=direction,
                        confidence=confidence,
                        start_price=start_price,
                        end_price=end_price,
                        delta=delta,
                        delta_pct=delta_pct,
                        atr=item["atr"],
                        threshold=threshold,
                        observed_range=observed_range,
                        one_minute_outcome=one_minute_outcome,
                        three_minute_outcome=three_minute_outcome,
                        timing=timing,
                        time_to_favorable_seconds=favorable_time,
                        time_to_unfavorable_seconds=unfavorable_time,
                        market_regime=market_regime,
                        regime_aligned=regime_aligned,
                        alignment_score=int(alignment.get("alignmentScore", 0)),
                        dominant_direction=dominant_direction,
                        alignment_aligned=alignment_aligned,
                        ai_score=int(ai_score.get("value", 0)),
                        ai_label=str(ai_score.get("label") or "Unknown"),
                        ai_factors={key: safe_float(value) for key, value in ai_factors.items()},
                        pattern_name=top_pattern.get("name") if top_pattern else None,
                        pattern_direction=pattern_direction,
                        pattern_confidence=safe_float(top_pattern.get("confidence")) if top_pattern else None,
                        pattern_aligned=pattern_aligned,
                        backtest_win_rate=safe_float(backtest.get("winRate")) if "winRate" in backtest else None,
                        backtest_profit_factor=safe_float(backtest.get("profitFactor")) if "profitFactor" in backtest else None,
                        backtest_profitable_percent=safe_float(
                            ((backtest.get("confidenceCalibration") or {}).get("profitablePercent"))
                        ) if backtest.get("confidenceCalibration") else None,
                        confidence_error=confidence_error,
                        resolved_reason=resolved_reason or final_breakdown.get("resolved_reason"),
                        persisted_direction_correct=persisted_direction_correct,
                        source_name=(analysis.get("sourceMetadata") or {}).get("sourceName"),
                        source_type=(analysis.get("sourceMetadata") or {}).get("sourceType"),
                        quality_flags=quality_flags,
                        discrepancies=discrepancies,
                        horizons=[
                            HorizonAssessment(
                                seconds=60,
                                end_price=one_minute_price,
                                delta=one_minute_delta,
                                delta_pct=one_minute_delta_pct,
                                outcome=one_minute_outcome,
                            ),
                            HorizonAssessment(
                                seconds=observation_seconds,
                                end_price=end_price,
                                delta=delta,
                                delta_pct=delta_pct,
                                outcome=three_minute_outcome,
                            ),
                        ],
                    )
                )

            if progress_path is not None:
                write_report(progress_path, build_report(config, results, status="in_progress"))
            print(
                f"[validator] completed batch {batch}/{batches} "
                f"(samples={len(results)}, 1m_acc={summarize_results(results)['oneMinute']['accuracyExFlat']})",
                flush=True,
            )

    return build_report(config, results, status="completed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8010")
    parser.add_argument("--symbols", nargs="+", default=DEFAULT_SYMBOLS)
    parser.add_argument("--timeframe", default="1m", choices=sorted(TIMEFRAME_SECONDS))
    parser.add_argument("--trade-style", default="scalp", choices=["scalp", "swing"])
    parser.add_argument("--observation-seconds", type=int, default=180)
    parser.add_argument("--poll-seconds", type=int, default=15)
    parser.add_argument("--batches", type=int, default=2)
    parser.add_argument("--backtest-lookback-days", type=int, default=5)
    parser.add_argument("--db-path", default="data/trading_bot.db")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_path = Path(args.output) if args.output else Path("logs") / f"live_signal_validation_{timestamp}.json"

    report = run_validation(
        base_url=args.base_url,
        symbols=args.symbols,
        timeframe=args.timeframe,
        trade_style=args.trade_style,
        observation_seconds=args.observation_seconds,
        poll_seconds=args.poll_seconds,
        batches=args.batches,
        backtest_lookback_days=args.backtest_lookback_days,
        db_path=Path(args.db_path),
        progress_path=output_path,
    )
    write_report(output_path, report)

    markdown_path = output_path.with_suffix(".md")
    markdown_path.write_text(render_markdown(report["summary"], [SignalAssessment(**{
        **item,
        "horizons": [HorizonAssessment(**h) for h in item["horizons"]],
    }) for item in report["results"]], report["config"]))

    print(json.dumps({
        "output": str(output_path),
        "markdown": str(markdown_path),
        "summary": report["summary"],
    }, indent=2))


if __name__ == "__main__":
    main()