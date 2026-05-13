"""Scanner run orchestration seam."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any, Optional
from uuid import uuid4

from trading_bot.api.models import (
    IndicatorCondition,
    PredictionRequest,
    PredictionSourceContext,
    PredictionSourceType,
    PredictionStrategyMode,
    ScannerConfig,
)
from trading_bot.config import get_logger, get_settings
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.monitoring.bot_metrics import bot_metrics
from trading_bot.services.market_analysis import analyze_symbol
from trading_bot.services.opportunity_ranker import rank_opportunity
from trading_bot.services.prediction_pipeline import (
    asset_class_for_symbol,
    build_prediction_response,
)
from trading_bot.services.scanner_engine import (
    ALLOWED_OPERATORS,
    INDICATOR_DEFINITION_MAP,
    SUPPORTED_TIMEFRAMES,
    SUPPORTED_TRADE_STYLES,
    build_indicator_snapshot,
    evaluate_condition,
    get_indicator_value_at,
    indicator_definition,
    resolve_indicator_name,
    safe_float,
)

logger = get_logger(__name__)

SCANNER_CONCURRENCY_FALLBACK = 4

DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "XAU/USD", "BTC/USD", "US500", "EUR/GBP"
]

METAL_SYMBOLS = {"XAU/USD", "XAG/USD", "XPT/USD", "COPPER/USD"}
CRYPTO_SYMBOLS = {
    "BTC/USD",
    "ETH/USD",
    "SOL/USD",
    "XRP/USD",
    "BNB/USD",
    "ADA/USD",
    "DOGE/USD",
    "LTC/USD",
    "LINK/USD",
    "DOT/USD",
    "AVAX/USD",
    "MATIC/USD",
}
INDEX_SYMBOLS = {"US30", "US500", "US100", "UK100", "DE40", "FR40", "JP225", "AU200"}


class ScannerConfigError(ValueError):
    """Raised when a scanner config cannot be executed."""


@dataclass(frozen=True)
class ScannerRun:
    results: list[dict[str, Any]]
    total_scanned: int
    total_matches: int
    warnings: list[str]
    request_id: str
    timeframe: str
    trade_style: str
    logic: str
    groups: list[dict[str, Any]]
    scan: dict[str, Any]


def get_scanner_concurrency_limit(total_symbols: Optional[int] = None) -> int:
    configured = getattr(get_settings(), "scanner_max_concurrent", SCANNER_CONCURRENCY_FALLBACK)
    try:
        value = int(configured)
    except (TypeError, ValueError):
        value = SCANNER_CONCURRENCY_FALLBACK
    if total_symbols is None:
        return value
    return max(1, min(value, max(total_symbols, 1)))


def _elapsed_ms(started_at: float) -> float:
    return round((time.perf_counter() - started_at) * 1000, 2)


def confidence_band_for_scan(confidence: object) -> str:
    value = safe_float(confidence)
    if value >= 85:
        return "very_high"
    if value >= 70:
        return "high"
    if value >= 50:
        return "medium"
    return "low"


def market_focus_for_symbol(symbol: str) -> str:
    asset_class = asset_class_for_symbol(symbol)
    asset_value = getattr(asset_class, "value", str(asset_class))
    if symbol in METAL_SYMBOLS:
        return "metals"
    if symbol in CRYPTO_SYMBOLS or asset_value == "crypto":
        return "crypto"
    if symbol in INDEX_SYMBOLS or asset_value == "index":
        return "indices"
    if asset_value == "commodity":
        return "commodities"
    return "forex"


def risk_gate_reasons(
    analysis: dict[str, Any],
    source_metadata: Optional[dict[str, Any]],
    risk_gate: Optional[str],
    opportunity_score: Optional[float],
) -> list[str]:
    reasons: list[str] = []
    confidence = safe_float(analysis.get("confidence"), 50.0)
    risk_reward = analysis.get("riskReward")
    risk_reward_value = safe_float(risk_reward)
    market_status = (source_metadata or {}).get("marketStatus")
    quality_flags = set((source_metadata or {}).get("qualityFlags", []))
    current_price = safe_float(analysis.get("currentPrice"))
    atr = safe_float(analysis.get("atr"))

    if confidence < 55:
        reasons.append(f"Confidence is {round(confidence)}%, below the 55% action threshold")
    if opportunity_score is not None and opportunity_score < 50:
        reasons.append(f"Opportunity score is {round(opportunity_score)}%, below the preferred 50% gate")
    if risk_reward is None or risk_reward_value <= 0:
        reasons.append("Risk/reward is unavailable")
    elif risk_reward_value < 1.2:
        reasons.append(f"Risk/reward is {risk_reward_value:.2f}R, below the 1.20R gate")
    if market_status in {"stale", "delayed"}:
        reasons.append(f"Market data is {market_status}")
    if (source_metadata or {}).get("isFallback"):
        reasons.append("Data source is using fallback market data")
    if "stale_data" in quality_flags:
        reasons.append("Source quality flags include stale data")
    if current_price > 0 and atr > 0:
        atr_pct = atr / current_price * 100
        if atr_pct > 2:
            reasons.append(f"ATR is elevated at {atr_pct:.2f}% of price")
    if risk_gate == "high" and not reasons:
        reasons.append("Risk gate is high based on volatility, data quality, or opportunity score")

    return reasons


def build_market_context(
    symbol: str,
    analysis: dict[str, Any],
    source_metadata: Optional[dict[str, Any]],
    trade_style: str,
    timeframe: str,
) -> dict[str, Any]:
    return {
        "asset_class": market_focus_for_symbol(symbol),
        "timeframe": timeframe,
        "trade_style": trade_style,
        "market_status": (source_metadata or {}).get("marketStatus", "unknown"),
        "data_source": (source_metadata or {}).get("sourceName", "unknown"),
        "freshness_seconds": (source_metadata or {}).get("freshnessSeconds"),
        "volatility_regime": analysis.get("marketRegime", "ranging"),
        "current_price": analysis.get("currentPrice"),
        "atr": analysis.get("atr"),
        "risk_reward": analysis.get("riskReward"),
    }


def has_entry_level(analysis: dict[str, Any]) -> bool:
    entry_range = analysis.get("entryRange") or analysis.get("entry_range")
    if isinstance(entry_range, dict):
        if safe_float(entry_range.get("min")) > 0:
            return True
        if safe_float(entry_range.get("entry")) > 0:
            return True
    return any(
        safe_float(analysis.get(key)) > 0
        for key in ("entry", "entryPrice", "entry_price", "entryMin", "entry_min")
    )


def build_scan_action(
    recommendation: str,
    confidence: object,
    risk_gate: Optional[str],
    risk_reasons: list[str],
    analysis: dict[str, Any],
    matched_summary: str,
) -> dict[str, Any]:
    normalized = str(recommendation or "hold").lower()
    confidence_value = safe_float(confidence)
    risk_reward_value = safe_float(analysis.get("riskReward"))
    setup_blockers: list[str] = []
    if not has_entry_level(analysis):
        setup_blockers.append("Entry level is unavailable")
    if safe_float(analysis.get("stopLoss")) <= 0:
        setup_blockers.append("Stop loss is unavailable")
    if safe_float(analysis.get("takeProfit1")) <= 0:
        setup_blockers.append("Take profit is unavailable")
    if safe_float(analysis.get("currentPrice")) <= 0:
        setup_blockers.append("Current price is unavailable")
    if risk_reward_value <= 0:
        setup_blockers.append("Risk/reward is unavailable")
    elif risk_reward_value < 1.2:
        setup_blockers.append(f"Risk/reward is {risk_reward_value:.2f}R, below the 1.20R gate")
    if risk_gate == "high":
        setup_blockers.append("Risk gate is high based on volatility, data quality, or opportunity score")

    blockers = list(dict.fromkeys([*risk_reasons, *setup_blockers]))
    trade_allowed = (
        normalized in {"buy", "sell", "strong_buy", "strong_sell"}
        and confidence_value >= 55
        and not blockers
    )

    if trade_allowed:
        label = "Trade-ready setup"
        summary = f"{str(recommendation).upper()} setup cleared scanner rules and core risk gates."
        next_steps = [
            "Review entry, stop, target, and position sizing before placing an order.",
            "Confirm the current candle has not invalidated the setup.",
        ]
        blockers = []
    elif normalized in {"hold", "neutral", "no_trade"}:
        label = "Watch only"
        summary = "Scanner rules matched, but AI analysis does not support a trade yet."
        next_steps = [
            "Wait for directional confirmation or stronger confidence.",
            "Use the matching conditions as a watchlist trigger.",
        ]
        blockers = blockers or ["Recommendation is not actionable"]
    else:
        label = "Review setup"
        summary = f"{str(recommendation).upper()} setup needs confirmation before trading."
        next_steps = [
            "Check risk gate reasons and data freshness.",
            "Confirm entry and stop placement before acting.",
        ]

    if matched_summary and matched_summary not in summary:
        next_steps.append(matched_summary)

    return {
        "label": label,
        "summary": summary,
        "next_steps": next_steps,
        "blockers": blockers,
        "trade_allowed": trade_allowed,
    }


def scanner_error_result(
    symbol: str,
    error: object,
    trade_style: str,
    timeframe: str,
    latency_ms: Optional[float] = None,
) -> dict[str, Any]:
    message = str(error) or "Scanner evaluation failed"
    return {
        "symbol": symbol,
        "signal": "NEUTRAL",
        "score": 0.0,
        "matching_conditions": [],
        "indicator_values": {},
        "confidence": 0,
        "market_regime": None,
        "trade_style": trade_style,
        "timeframe": timeframe,
        "opportunity_score": 0,
        "source_score": None,
        "source_metadata": None,
        "reason": message,
        "confidence_band": "low",
        "rationale": [message],
        "action": {
            "label": "Backend failure",
            "summary": "This symbol could not be evaluated by the scanner.",
            "next_steps": ["Review the backend error before considering this market."],
            "blockers": [message],
            "trade_allowed": False,
        },
        "market_context": {
            "asset_class": market_focus_for_symbol(symbol),
            "timeframe": timeframe,
            "trade_style": trade_style,
            "market_status": "unknown",
            "data_source": "unknown",
            "freshness_seconds": None,
            "volatility_regime": None,
            "current_price": None,
            "atr": None,
            "risk_reward": None,
        },
        "risk_gate": "high",
        "risk_gate_reasons": [message],
        "scan_status": "error",
        "error_message": message,
        "evaluation_latency_ms": latency_ms,
    }


def flatten_conditions(config: ScannerConfig) -> list[IndicatorCondition]:
    if config.groups:
        merged: list[IndicatorCondition] = []
        for group in config.groups:
            merged.extend(group.conditions or [])
        return merged
    return config.conditions or []


def group_descriptors(config: ScannerConfig) -> list[dict[str, Any]]:
    if not config.groups:
        return [
            {"name": "Primary group", "logic": config.logic, "conditions": config.conditions or []}
        ]
    return [
        {
            "name": group.name or f"Group {index + 1}",
            "logic": group.logic,
            "conditions": group.conditions or [],
        }
        for index, group in enumerate(config.groups)
    ]


def group_metadata(config: ScannerConfig) -> list[dict[str, Any]]:
    return [
        {"name": group["name"], "logic": group["logic"], "conditions": len(group["conditions"])}
        for group in group_descriptors(config)
    ]


def validate_scanner_config(config: ScannerConfig) -> list[str]:
    if config.timeframe not in SUPPORTED_TIMEFRAMES:
        raise ScannerConfigError(
            f"Unsupported timeframe '{config.timeframe}'. Allowed: {list(SUPPORTED_TIMEFRAMES)}"
        )
    if config.trade_style not in SUPPORTED_TRADE_STYLES:
        raise ScannerConfigError(
            f"Unsupported trade style '{config.trade_style}'. "
            f"Allowed: {list(SUPPORTED_TRADE_STYLES)}"
        )
    if config.logic not in {"AND", "OR"}:
        raise ScannerConfigError("Logic must be 'AND' or 'OR'")

    warnings: list[str] = []
    for group in group_descriptors(config):
        if group["logic"] not in {"AND", "OR"}:
            raise ScannerConfigError(f"Group '{group['name']}' must use AND or OR logic")

    for cond in flatten_conditions(config):
        if cond.operator not in ALLOWED_OPERATORS:
            raise ScannerConfigError(
                f"Invalid operator: '{cond.operator}'. Allowed: {ALLOWED_OPERATORS}"
            )
        definition = indicator_definition(cond.indicator)
        if definition is None:
            raise ScannerConfigError(f"Unknown indicator '{cond.indicator}'")
        if not definition["supported"]:
            raise ScannerConfigError(f"Indicator '{cond.indicator}' is not supported yet")
        if cond.operator not in definition["operators"]:
            raise ScannerConfigError(
                f"Operator '{cond.operator}' is not valid for indicator '{cond.indicator}'"
            )
        if cond.compare_indicator:
            compare_definition = indicator_definition(cond.compare_indicator)
            if compare_definition is None or not compare_definition["supported"]:
                raise ScannerConfigError(
                    f"Compare indicator '{cond.compare_indicator}' is not supported"
                )
        indicator_key = resolve_indicator_name(cond.indicator)
        indicator_meta = INDICATOR_DEFINITION_MAP[indicator_key]
        lo = indicator_meta["range"]["min"]
        hi = indicator_meta["range"]["max"]
        if cond.compare_indicator is None and not (lo <= cond.value <= hi):
            raise ScannerConfigError(
                f"Threshold {cond.value} for '{cond.indicator}' out of valid range [{lo}, {hi}]"
            )
        if cond.operator == "between":
            if cond.value2 is None:
                raise ScannerConfigError(
                    f"Indicator '{cond.indicator}' requires a second value for between"
                )
            if not (lo <= cond.value2 <= hi):
                raise ScannerConfigError(
                    f"Threshold2 {cond.value2} for '{cond.indicator}' "
                    f"out of valid range [{lo}, {hi}]"
                )
        elif cond.value2 is not None:
            warnings.append(f"{cond.indicator} value2 ignored because operator is {cond.operator}")

    return warnings


def evaluate_single_pair(
    symbol: str,
    conditions: list[IndicatorCondition],
    logic: str,
    trade_style: str = "swing",
    timeframe: str = "1h",
    groups: Optional[list[dict[str, Any]]] = None,
) -> Optional[dict[str, Any]]:
    """Evaluate a single pair against scanner conditions using real indicator data."""
    bot_metrics.increment_counter(
        "scanner.symbol_scanned",
        context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
    )
    try:
        data, source_metadata = get_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
        if data is None or len(data) < 30:
            bot_metrics.increment_counter(
                "scanner.symbol_failed",
                label="market_data_unavailable",
                context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
            )
            return None

        indicator_map = build_indicator_snapshot(data, -1)
        matched_count = 0
        matching_conditions = []
        failed_conditions = []
        total_count = len(conditions) if conditions else 1
        group_results = []

        def evaluate_conditions(
            condition_list: list[IndicatorCondition],
            group_logic: str,
        ) -> dict[str, Any]:
            group_match_count = 0
            group_matching_conditions = []
            group_failed_conditions = []
            for cond in condition_list:
                raw_name = cond.indicator
                ind_name = resolve_indicator_name(raw_name)
                op = cond.operator
                threshold = cond.value
                compare_indicator = None
                if cond.compare_indicator:
                    compare_indicator = resolve_indicator_name(cond.compare_indicator)

                current_val = indicator_map.get(ind_name)
                compare_val = (
                    indicator_map.get(compare_indicator) if compare_indicator else threshold
                )

                met = False
                try:
                    previous_left = (
                        get_indicator_value_at(ind_name, data, -2) if len(data) >= 2 else None
                    )
                    previous_right = (
                        get_indicator_value_at(compare_indicator, data, -2)
                        if compare_indicator and len(data) >= 2
                        else None
                    )
                    met = evaluate_condition(
                        op,
                        current_left=current_val if current_val is not None else 0.0,
                        current_right=compare_val if compare_val is not None else 0.0,
                        previous_left=previous_left,
                        previous_right=previous_right,
                        secondary_value=cond.value2,
                    )
                except Exception:
                    met = False

                if met:
                    group_match_count += 1
                    descriptor = (
                        f"{raw_name} {op.replace('_', ' ')} {cond.compare_indicator}"
                        if cond.compare_indicator
                        else f"{raw_name} {op.replace('_', ' ')} {threshold}"
                    )
                    group_matching_conditions.append(descriptor)
                else:
                    group_failed_conditions.append(raw_name)

            group_total = len(condition_list) if condition_list else 1
            group_passed = (
                group_match_count == group_total if group_logic == "AND" else group_match_count > 0
            )
            group_score = 0.0 if group_total == 0 else group_match_count / group_total
            return {
                "passed": group_passed,
                "score": group_score,
                "matched_count": group_match_count,
                "matching_conditions": group_matching_conditions,
                "failed_conditions": group_failed_conditions,
                "total_count": group_total,
            }

        grouped = groups or [{"name": "Primary group", "logic": logic, "conditions": conditions}]

        for group in grouped:
            result = evaluate_conditions(group["conditions"], group["logic"])
            group_results.append({
                "name": group["name"],
                "logic": group["logic"],
                **result,
            })
            matched_count += result["matched_count"]
            matching_conditions.extend(result["matching_conditions"])
            failed_conditions.extend(result["failed_conditions"])

        total_count = (
            sum(item["total_count"] for item in group_results) if group_results else total_count
        )

        if logic == "AND":
            passed = all(item["passed"] for item in group_results) if group_results else False
        else:
            passed = any(item["passed"] for item in group_results) if group_results else False

        matched_count = min(matched_count, total_count)

        if total_count == 0:
            score = 0.0
        elif logic == "AND":
            score = 1.0 if passed else matched_count / total_count
        else:
            score = matched_count / total_count if passed and total_count > 0 else 0.0

        rsi_val = indicator_map.get("RSI", 50.0)
        if rsi_val < 40:
            signal = "BUY"
        elif rsi_val > 60:
            signal = "SELL"
        else:
            signal = "NEUTRAL"

        if matched_count == 0 or not passed:
            return None

        safe_indicators = {}
        for k, v in indicator_map.items():
            safe_indicators[k] = round(safe_float(v), 4)

        analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
        prediction_request = PredictionRequest(
            symbol=symbol,
            asset_class=asset_class_for_symbol(symbol),
            timeframe=timeframe,
            strategy_mode=(
                PredictionStrategyMode.SCALP
                if trade_style == "scalp"
                else PredictionStrategyMode.SWING
            ),
            source_context=PredictionSourceContext(source_type=PredictionSourceType.SCANNER),
        )
        prediction = build_prediction_response(
            prediction_request,
            analysis_override=analysis,
            metadata_override=source_metadata,
        )
        source_meta = source_metadata if isinstance(source_metadata, dict) else {}
        analysis_payload = analysis or {}
        ranking = rank_opportunity(analysis_payload, source_meta)
        recommendation = (analysis or {}).get("signal", signal)
        quality_flags = (
            source_meta.get("qualityFlags", []) if isinstance(source_metadata, dict) else []
        )
        warnings = [str(flag).replace("_", " ") for flag in quality_flags if flag]
        if recommendation == "hold":
            warnings.append("No actionable trade from current AI analysis")

        matched_summary = f"Matched {matched_count}/{total_count} conditions"
        if failed_conditions:
            matched_summary += f"; missed {', '.join(failed_conditions[:3])}"
        analysis_reason = (analysis or {}).get("reason", "")
        reason = analysis_reason if analysis_reason else matched_summary
        if analysis_reason and failed_conditions:
            reason = f"{analysis_reason} ({matched_summary})"
        opportunity_score = ranking.get("opportunityScore")
        risk_gate = ranking.get("riskGate")
        gate_reasons = risk_gate_reasons(
            analysis_payload,
            source_meta,
            risk_gate,
            opportunity_score,
        )
        rationale = [reason, matched_summary]
        if gate_reasons:
            rationale.append(f"Risk gate: {risk_gate or 'unknown'}")
        action = build_scan_action(
            str(recommendation or signal),
            analysis_payload.get("confidence", 50),
            risk_gate,
            gate_reasons,
            analysis_payload,
            matched_summary,
        )

        return {
            "symbol": symbol,
            "signal": str(recommendation).upper() if recommendation else signal,
            "recommendation": str(recommendation).upper() if recommendation else signal,
            "score": round(safe_float(score), 4),
            "matching_conditions": matching_conditions,
            "indicator_values": safe_indicators,
            "confidence": (analysis or {}).get("confidence", 50),
            "confidence_band": confidence_band_for_scan((analysis or {}).get("confidence", 50)),
            "market_regime": (analysis or {}).get("marketRegime", "ranging"),
            "trade_style": trade_style,
            "timeframe": timeframe,
            "opportunity_score": opportunity_score,
            "source_score": ranking.get("sourceScore"),
            "source_metadata": source_metadata,
            "prediction_id": prediction.prediction_id,
            "prediction_cache": {
                "status": prediction.freshness.cache_status,
                "key": prediction.freshness.cache_key,
                "ageSeconds": prediction.freshness.cache_age_seconds,
                "featureVersion": prediction.freshness.feature_version,
            },
            "prediction_latency_ms": prediction.latency.total_latency_ms,
            "reason": reason,
            "rationale": list(dict.fromkeys(rationale)),
            "action": action,
            "risk_reward": (analysis or {}).get("riskReward"),
            "data_fetched_at": (analysis or {}).get("data_fetched_at"),
            "warnings": warnings,
            "group_results": group_results,
            "entry_range": (analysis or {}).get("entryRange"),
            "stop_loss": (analysis or {}).get("stopLoss"),
            "take_profit1": (analysis or {}).get("takeProfit1"),
            "take_profit2": (analysis or {}).get("takeProfit2"),
            "take_profit3": (analysis or {}).get("takeProfit3"),
            "current_price": (analysis or {}).get("currentPrice"),
            "risk_gate": risk_gate,
            "risk_gate_reasons": gate_reasons,
            "market_context": build_market_context(
                symbol,
                analysis_payload,
                source_meta,
                trade_style,
                timeframe,
            ),
            "risk_context": {
                "volatility_regime": (analysis or {}).get("marketRegime", "ranging"),
                "market_status": source_meta.get("marketStatus", "unknown"),
            },
            "atr": (analysis or {}).get("atr"),
        }

    except Exception as e:
        bot_metrics.increment_counter(
            "scanner.symbol_failed",
            label="evaluation_error",
            context={"symbol": symbol, "timeframe": timeframe, "trade_style": trade_style},
        )
        logger.warning(f"Scanner: failed to evaluate {symbol}: {e}")
        return scanner_error_result(symbol, e, trade_style, timeframe)


async def evaluate_single_pair_async(
    symbol: str,
    conditions: list[IndicatorCondition],
    logic: str,
    trade_style: str,
    timeframe: str,
    groups: Optional[list[dict[str, Any]]],
    semaphore: asyncio.Semaphore,
) -> Optional[dict[str, Any]]:
    async with semaphore:
        started_at = time.perf_counter()
        try:
            result = await asyncio.to_thread(
                evaluate_single_pair,
                symbol,
                conditions,
                logic,
                trade_style,
                timeframe,
                groups,
            )
        except Exception as e:
            logger.warning(f"Scanner async evaluation failed for {symbol}: {e}")
            result = scanner_error_result(symbol, e, trade_style, timeframe)

        latency_ms = _elapsed_ms(started_at)
        if result is None:
            return None
        result["evaluation_latency_ms"] = latency_ms
        result.setdefault("scan_status", "matched")
        return result


async def scan_symbols(config: ScannerConfig) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Scan symbols using bounded async evaluation."""
    pairs = config.pairs if config.pairs else DEFAULT_PAIRS
    logic = getattr(config, "logic", "AND") or "AND"
    conditions = flatten_conditions(config)
    trade_style = getattr(config, "trade_style", None) or "swing"
    timeframe = getattr(config, "timeframe", None) or "1h"
    groups = group_descriptors(config)
    started_at = time.perf_counter()
    concurrency_limit = get_scanner_concurrency_limit(len(pairs))

    if not conditions:
        return [], len(pairs), {
            "batch_duration_ms": _elapsed_ms(started_at),
            "concurrency_limit": concurrency_limit,
            "total_symbols": len(pairs),
            "succeeded": 0,
            "failed": 0,
            "unmatched": len(pairs),
        }

    semaphore = asyncio.Semaphore(concurrency_limit)
    tasks = [
        evaluate_single_pair_async(
            symbol,
            conditions,
            logic,
            trade_style,
            timeframe,
            groups,
            semaphore,
        )
        for symbol in pairs
    ]
    evaluated = await asyncio.gather(*tasks, return_exceptions=True)
    input_order = {symbol: index for index, symbol in enumerate(pairs)}
    successful_results = []
    failed_results = []

    for index, item in enumerate(evaluated):
        if isinstance(item, Exception):
            failed_results.append(scanner_error_result(pairs[index], item, trade_style, timeframe))
            continue
        if item is None:
            continue
        if item.get("scan_status") == "error":
            failed_results.append(item)
        else:
            successful_results.append(item)

    successful_results.sort(
        key=lambda item: (
            -(item.get("opportunity_score") or 0),
            -(item.get("score") or 0),
            input_order.get(item["symbol"], 0),
        )
    )
    failed_results.sort(key=lambda item: input_order.get(item["symbol"], 0))
    results = successful_results + failed_results
    meta = {
        "batch_duration_ms": _elapsed_ms(started_at),
        "concurrency_limit": concurrency_limit,
        "total_symbols": len(pairs),
        "succeeded": len(successful_results),
        "failed": len(failed_results),
        "unmatched": max(0, len(pairs) - len(successful_results) - len(failed_results)),
    }
    return results, len(pairs), meta


async def execute_scanner_run(
    config: ScannerConfig,
    request_id: Optional[str] = None,
    endpoint: str = "/api/scanner/scan",
) -> ScannerRun:
    """Validate and execute a scanner run behind a single service interface."""
    scan_request_id = request_id or str(uuid4())
    started = time.perf_counter()
    context = {
        "endpoint": endpoint,
        "timeframe": config.timeframe,
        "trade_style": config.trade_style,
    }
    warnings = validate_scanner_config(config)

    try:
        results, total_scanned, scan_meta = await scan_symbols(config)
        bot_metrics.increment_counter(
            "scanner.success",
            request_id=scan_request_id,
            context=context,
        )
        return ScannerRun(
            results=results,
            total_scanned=total_scanned,
            total_matches=scan_meta["succeeded"],
            warnings=warnings,
            request_id=scan_request_id,
            timeframe=config.timeframe,
            trade_style=config.trade_style,
            logic=config.logic,
            groups=group_metadata(config),
            scan=scan_meta,
        )
    except Exception:
        bot_metrics.increment_counter(
            "scanner.failure",
            request_id=scan_request_id,
            context=context,
        )
        raise
    finally:
        bot_metrics.record_latency(
            "scanner.batch",
            (time.perf_counter() - started) * 1000,
            request_id=scan_request_id,
            context=context,
        )
