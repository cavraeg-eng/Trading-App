"""Scanner routes for the trading bot API."""

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from fastapi import APIRouter, HTTPException

from trading_bot.api.models import IndicatorCondition, ScannerConfig
from trading_bot.api.routes.market import analyze_symbol
from trading_bot.config import get_logger
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.persistence import repositories as repo
from trading_bot.services.opportunity_ranker import rank_opportunity, compute_risk_gate
from trading_bot.services.scanner_engine import (
    ALLOWED_OPERATORS,
    INDICATOR_DEFINITION_MAP,
    SUPPORTED_TIMEFRAMES,
    SUPPORTED_TRADE_STYLES,
    build_indicator_snapshot,
    evaluate_condition,
    get_indicator_value_at,
    indicator_definition,
    metadata_payload,
    resolve_indicator_name,
    safe_float,
)

logger = get_logger(__name__)

router = APIRouter(prefix="/api/scanner", tags=["scanner"])

DEFAULT_PAIRS = [
    "EUR/USD", "GBP/USD", "USD/JPY", "USD/CHF", "AUD/USD",
    "USD/CAD", "NZD/USD", "XAU/USD", "BTC/USD", "US500", "EUR/GBP"
]


def _flatten_conditions(config: ScannerConfig) -> list[IndicatorCondition]:
    if config.groups:
        merged: list[IndicatorCondition] = []
        for group in config.groups:
            merged.extend(group.conditions or [])
        return merged
    return config.conditions or []


def _group_descriptors(config: ScannerConfig) -> list[dict]:
    if not config.groups:
        return [{"name": "Primary group", "logic": config.logic, "conditions": config.conditions or []}]
    return [{"name": group.name or f"Group {index + 1}", "logic": group.logic, "conditions": group.conditions or []} for index, group in enumerate(config.groups)]

@router.get("/presets")
async def get_presets():
    """Get built-in scanner presets."""
    presets = [
        {
            "id": "apex_current",
            "name": "Apex Current",
            "description": "Tracks mature trend continuation using EMA reclaim, RSI strength, and directional confirmation",
            "icon": "trending-up",
            "category": "Trend follower",
            "best_for": "4H swing continuation when price reclaims the EMA with RSI confirmation.",
            "cadence": "4H",
            "risk": "medium",
            "popularity": "Core",
            "accent": "emerald",
            "logic": "AND",
            "groups": [
                {
                    "id": "trend-core",
                    "name": "Trend confirmation",
                    "logic": "AND",
                    "conditions": [
                        {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "EMA", "value": 0},
                        {"indicator": "RSI", "operator": ">", "value": 50},
                    ],
                }
            ],
            "trade_style": "swing",
            "timeframe": "4h",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "US500"],
            "tags": ["trend", "breakout", "swing"],
            "conditions": [
                {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "EMA", "value": 0},
                {"indicator": "RSI", "operator": ">", "value": 50}
            ]
        },
        {
            "id": "viper_entry",
            "name": "Viper Entry",
            "description": "Hunts precision pullback entries where oversold momentum flips back into confirmation",
            "icon": "zap",
            "category": "Precision entry",
            "best_for": "Fast mean-reversion entries after oversold momentum flips back bullish.",
            "cadence": "1H",
            "risk": "medium",
            "popularity": "Popular",
            "accent": "amber",
            "logic": "AND",
            "groups": [
                {
                    "id": "reversal-entry",
                    "name": "Reversal entry",
                    "logic": "AND",
                    "conditions": [
                        {"indicator": "RSI", "operator": "<", "value": 30},
                        {"indicator": "MACD", "operator": "crosses_above", "compare_indicator": "MACD Signal", "value": 0},
                    ],
                }
            ],
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "AUD/USD", "XAU/USD", "BTC/USD"],
            "tags": ["momentum", "reversal"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 30},
                {"indicator": "MACD", "operator": "crosses_above", "compare_indicator": "MACD Signal", "value": 0}
            ]
        },
        {
            "id": "nova_breaker",
            "name": "Nova Breaker",
            "description": "Detects high-energy breakouts when price expands beyond volatility bands",
            "icon": "activity",
            "category": "Breakout hunter",
            "best_for": "Expansion moves when price pushes outside the upper band with elevated ATR.",
            "cadence": "1H",
            "risk": "high",
            "popularity": "Aggressive",
            "accent": "rose",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["XAU/USD", "BTC/USD", "US500", "GBP/JPY", "EUR/JPY"],
            "tags": ["volatility", "breakout"],
            "conditions": [
                {"indicator": "Price", "operator": "crosses_above", "compare_indicator": "BB Upper", "value": 0},
                {"indicator": "ATR", "operator": ">", "value": 1.5}
            ]
        },
        {
            "id": "pulse_surge",
            "name": "Pulse Surge",
            "description": "Catches unusual participation bursts before short-term momentum accelerates",
            "icon": "bar-chart",
            "category": "Flow scanner",
            "best_for": "Short-term alerts when activity surges above the recent 20-period baseline.",
            "cadence": "15M",
            "risk": "medium",
            "popularity": "Intraday",
            "accent": "sky",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "15m",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD", "BTC/USD"],
            "tags": ["volume", "breakout"],
            "conditions": [
                {"indicator": "Volume", "operator": ">", "value": 2.0}
            ]
        },
        {
            "id": "gravity_snap",
            "name": "Gravity Snap",
            "description": "Finds stretched markets that may snap back after deep oversold pressure",
            "icon": "refresh-cw",
            "category": "Mean reversion",
            "best_for": "Pullbacks near the lower Bollinger zone where RSI is deeply oversold.",
            "cadence": "1H",
            "risk": "low",
            "popularity": "Defensive",
            "accent": "violet",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1h",
            "recommended_pairs": ["EUR/USD", "AUD/USD", "USD/CAD", "NZD/USD", "XAU/USD"],
            "tags": ["mean reversion", "oversold"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 25},
                {"indicator": "BB", "operator": "<", "value": -1}
            ]
        },
        {
            "id": "sweep_forge",
            "name": "Sweep Forge",
            "description": "Looks for stretched moves with volume confirmation after likely liquidity sweeps",
            "icon": "target",
            "category": "Liquidity hunter",
            "best_for": "Scalp setups where price tags an extreme and participation expands.",
            "cadence": "5M",
            "risk": "high",
            "popularity": "Fast",
            "accent": "amber",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "5m",
            "recommended_pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "XAU/USD"],
            "tags": ["liquidity", "scalp", "volume"],
            "conditions": [
                {"indicator": "RSI", "operator": "<", "value": 35},
                {"indicator": "Volume", "operator": ">", "value": 1.4},
                {"indicator": "BB", "operator": "<=", "value": -0.8}
            ]
        },
        {
            "id": "atlas_pulse",
            "name": "Atlas Pulse",
            "description": "Screens larger-market continuation with slower trend and volume agreement",
            "icon": "shield",
            "category": "Macro swing",
            "best_for": "Cleaner swing scans on majors, gold, indices, and crypto using slower confirmation.",
            "cadence": "1D",
            "risk": "low",
            "popularity": "Stable",
            "accent": "emerald",
            "logic": "AND",
            "trade_style": "swing",
            "timeframe": "1d",
            "recommended_pairs": ["EUR/USD", "USD/JPY", "XAU/USD", "BTC/USD", "US500"],
            "tags": ["macro", "trend", "confirmation"],
            "conditions": [
                {"indicator": "Price", "operator": ">", "compare_indicator": "EMA", "value": 0},
                {"indicator": "MACD Histogram", "operator": ">", "value": 0},
                {"indicator": "Volume", "operator": ">", "value": 1.0}
            ]
        },
        {
            "id": "aurum_edge",
            "name": "Aurum Edge",
            "description": "Gold-focused scalping scanner for fast XAU/USD extremes and participation bursts",
            "icon": "sparkles",
            "category": "Gold scalper",
            "best_for": "XAU/USD 5-minute scalp ideas when gold stretches into volatility extremes.",
            "cadence": "5M",
            "risk": "high",
            "popularity": "Gold",
            "accent": "amber",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "5m",
            "recommended_pairs": ["XAU/USD"],
            "tags": ["gold", "scalp", "volatility"],
            "conditions": [
                {"indicator": "RSI", "operator": "between", "value": 20, "value2": 38},
                {"indicator": "BB", "operator": "<=", "value": -0.7},
                {"indicator": "Volume", "operator": ">", "value": 1.2}
            ]
        },
        {
            "id": "volt_raider",
            "name": "Volt Raider",
            "description": "Crypto volatility scanner for fast expansions in BTC and high-beta markets",
            "icon": "bot",
            "category": "Crypto volatility",
            "best_for": "Crypto continuation or reversal watchlists during elevated volume and volatility.",
            "cadence": "15M",
            "risk": "high",
            "popularity": "Crypto",
            "accent": "violet",
            "logic": "AND",
            "trade_style": "scalp",
            "timeframe": "15m",
            "recommended_pairs": ["BTC/USD", "ETH/USD"],
            "tags": ["crypto", "momentum", "volatility"],
            "conditions": [
                {"indicator": "ATR", "operator": ">", "value": 1.0},
                {"indicator": "Volume", "operator": ">", "value": 1.3},
                {"indicator": "MACD Histogram", "operator": ">", "value": 0}
            ]
        },
    ]
    return {"presets": presets}


@router.get("/metadata")
async def get_scanner_metadata():
    return metadata_payload(["major", "minor", "exotic", "crypto", "commodity", "index"])


def evaluate_single_pair(
    symbol: str,
    conditions: list,
    logic: str,
    trade_style: str = "swing",
    timeframe: str = "1h",
    groups: Optional[list[dict]] = None,
) -> Optional[dict]:
    """Evaluate a single pair against scanner conditions using real indicator data."""
    try:
        data, source_metadata = get_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
        if data is None or len(data) < 30:
            return None

        indicator_map = build_indicator_snapshot(data, -1)
        matched_count = 0
        matching_conditions = []
        failed_conditions = []
        total_count = len(conditions) if conditions else 1
        group_results = []

        def evaluate_conditions(condition_list: list[IndicatorCondition], group_logic: str):
            group_match_count = 0
            group_matching_conditions = []
            group_failed_conditions = []
            for cond in condition_list:
                raw_name = cond.indicator
                ind_name = resolve_indicator_name(raw_name)
                op = cond.operator
                threshold = cond.value
                compare_indicator = resolve_indicator_name(cond.compare_indicator) if cond.compare_indicator else None

                current_val = indicator_map.get(ind_name)
                compare_val = indicator_map.get(compare_indicator) if compare_indicator else threshold

                met = False
                try:
                    previous_left = get_indicator_value_at(ind_name, data, -2) if len(data) >= 2 else None
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

        total_count = sum(item["total_count"] for item in group_results) if group_results else total_count

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

        # Only return if at least one condition matched
        if matched_count == 0 or not passed:
            return None

        safe_indicators = {}
        for k, v in indicator_map.items():
            safe_indicators[k] = round(safe_float(v), 4)

        analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
        ranking = rank_opportunity(analysis or {}, source_metadata)
        risk_gate = compute_risk_gate(analysis or {}, source_metadata)

        # Build an improved reason that blends analysis rationale with matched conditions
        matched_summary = f"Matched {matched_count}/{total_count} conditions"
        if failed_conditions:
            matched_summary += f"; missed {', '.join(failed_conditions[:3])}"
        analysis_reason = (analysis or {}).get("reason", "")
        reason = analysis_reason if analysis_reason else matched_summary
        if analysis_reason and failed_conditions:
            reason = f"{analysis_reason} ({matched_summary})"

        return {
            "symbol": symbol,
            "signal": signal,
            "score": round(safe_float(score), 4),
            "matching_conditions": matching_conditions,
            "indicator_values": safe_indicators,
            "confidence": (analysis or {}).get("confidence", 50),
            "market_regime": (analysis or {}).get("marketRegime", "ranging"),
            "trade_style": trade_style,
            "timeframe": timeframe,
            "opportunity_score": ranking.get("opportunityScore"),
            "source_score": ranking.get("sourceScore"),
            "source_metadata": source_metadata,
            "reason": reason,
            "group_results": group_results,
            "entry_range": (analysis or {}).get("entryRange"),
            "stop_loss": (analysis or {}).get("stopLoss"),
            "take_profit1": (analysis or {}).get("takeProfit1"),
            "take_profit2": (analysis or {}).get("takeProfit2"),
            "take_profit3": (analysis or {}).get("takeProfit3"),
            "current_price": (analysis or {}).get("currentPrice"),
            "risk_gate": risk_gate,
            "risk_context": {
                "volatility_regime": (analysis or {}).get("marketRegime", "ranging"),
                "market_status": (source_metadata or {}).get("marketStatus", "unknown"),
            },
            "atr": (analysis or {}).get("atr"),
        }

    except Exception as e:
        logger.warning(f"Scanner: failed to evaluate {symbol}: {e}")
        return None


def scan_symbols(config: ScannerConfig) -> tuple:
    """Scan symbols using real indicator evaluation with parallel execution."""
    pairs = config.pairs if config.pairs else DEFAULT_PAIRS
    logic = getattr(config, "logic", "AND") or "AND"
    conditions = _flatten_conditions(config)
    trade_style = getattr(config, "trade_style", None) or "swing"
    timeframe = getattr(config, "timeframe", None) or "1h"
    groups = _group_descriptors(config)

    if not conditions:
        return [], len(pairs)

    results = []
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(evaluate_single_pair, symbol, conditions, logic, trade_style, timeframe, groups): symbol
            for symbol in pairs
        }
        for future in as_completed(futures):
            try:
                result = future.result()
                if result is not None:
                    results.append(result)
            except Exception as e:
                logger.warning(f"Scanner thread error for {futures[future]}: {e}")

    results.sort(key=lambda x: (x.get("opportunity_score", 0), x["score"]), reverse=True)
    return results, len(pairs)


@router.post("/scan")
async def run_scan(config: ScannerConfig):
    """Run a scan with the given configuration."""
    if config.timeframe not in SUPPORTED_TIMEFRAMES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported timeframe '{config.timeframe}'. Allowed: {list(SUPPORTED_TIMEFRAMES)}",
        )
    if config.trade_style not in SUPPORTED_TRADE_STYLES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported trade style '{config.trade_style}'. Allowed: {list(SUPPORTED_TRADE_STYLES)}",
        )
    if config.logic not in {"AND", "OR"}:
        raise HTTPException(status_code=400, detail="Logic must be 'AND' or 'OR'")

    warnings = []
    for group in _group_descriptors(config):
        if group["logic"] not in {"AND", "OR"}:
            raise HTTPException(status_code=400, detail=f"Group '{group['name']}' must use AND or OR logic")
    for cond in _flatten_conditions(config):
        if cond.operator not in ALLOWED_OPERATORS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid operator: '{cond.operator}'. Allowed: {ALLOWED_OPERATORS}",
            )
        definition = indicator_definition(cond.indicator)
        if definition is None:
            raise HTTPException(status_code=400, detail=f"Unknown indicator '{cond.indicator}'")
        if not definition["supported"]:
            raise HTTPException(status_code=400, detail=f"Indicator '{cond.indicator}' is not supported yet")
        if cond.operator not in definition["operators"]:
            raise HTTPException(
                status_code=400,
                detail=f"Operator '{cond.operator}' is not valid for indicator '{cond.indicator}'",
            )
        if cond.compare_indicator:
            compare_definition = indicator_definition(cond.compare_indicator)
            if compare_definition is None or not compare_definition["supported"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Compare indicator '{cond.compare_indicator}' is not supported",
                )
        indicator_key = resolve_indicator_name(cond.indicator)
        indicator_meta = INDICATOR_DEFINITION_MAP[indicator_key]
        lo = indicator_meta["range"]["min"]
        hi = indicator_meta["range"]["max"]
        if cond.compare_indicator is None and not (lo <= cond.value <= hi):
            raise HTTPException(
                status_code=400,
                detail=f"Threshold {cond.value} for '{cond.indicator}' out of valid range [{lo}, {hi}]",
            )
        if cond.operator == "between":
            if cond.value2 is None:
                raise HTTPException(status_code=400, detail=f"Indicator '{cond.indicator}' requires a second value for between")
            if not (lo <= cond.value2 <= hi):
                raise HTTPException(
                    status_code=400,
                    detail=f"Threshold2 {cond.value2} for '{cond.indicator}' out of valid range [{lo}, {hi}]",
                )
        elif cond.value2 is not None:
            warnings.append(f"{cond.indicator} value2 ignored because operator is {cond.operator}")

    results, total_scanned = scan_symbols(config)
    return {
        "results": results,
        "total_scanned": total_scanned,
        "total_matches": len(results),
        "warnings": warnings,
        "meta": {
            "timeframe": config.timeframe,
            "trade_style": config.trade_style,
            "logic": config.logic,
            "groups": [{"name": group["name"], "logic": group["logic"], "conditions": len(group["conditions"])} for group in _group_descriptors(config)],
        },
    }


@router.get("/saved")
async def get_saved_scanners():
    return {"saved": repo.get_saved_scanners()}


@router.post("/save")
async def save_scanner(config: ScannerConfig):
    """Save a scanner configuration."""
    scanner_payload = config.model_dump() if hasattr(config, "model_dump") else config.dict()
    scanner_id = repo.save_scanner(config.name, scanner_payload)
    return {"status": "saved", "name": config.name, "id": scanner_id}


@router.put("/saved/{scanner_id}")
async def update_saved_scanner(scanner_id: int, config: ScannerConfig):
    scanner_payload = config.model_dump() if hasattr(config, "model_dump") else config.dict()
    updated = repo.update_scanner(scanner_id, config.name, scanner_payload)
    if not updated:
        raise HTTPException(status_code=404, detail="Saved scanner not found")
    return {"status": "updated", "id": scanner_id, "name": config.name}


@router.delete("/saved/{scanner_id}")
async def delete_saved_scanner(scanner_id: int):
    deleted = repo.delete_scanner(scanner_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Saved scanner not found")
    return {"status": "deleted", "id": scanner_id}


@router.post("/alert")
async def create_scanner_alert(config: ScannerConfig):
    conditions = _flatten_conditions(config)
    if not conditions:
        raise HTTPException(status_code=400, detail="Scanner alert requires at least one condition")
    symbol_scope = ", ".join((config.pairs or DEFAULT_PAIRS)[:6])
    alert_id = repo.create_alert(
        symbol=(config.pairs or ["SCAN"])[0],
        alert_type="SCANNER_MATCH",
        title=f"Scanner alert armed: {config.name}",
        message=(
            f"{config.name} will monitor {symbol_scope}"
            + ("…" if len(config.pairs or DEFAULT_PAIRS) > 6 else "")
            + f" on {config.timeframe} / {config.trade_style}."
        ),
        severity="info",
        data=json.dumps(
            {
                "scanner_name": config.name,
                "logic": config.logic,
                "timeframe": config.timeframe,
                "trade_style": config.trade_style,
                "pairs": config.pairs or DEFAULT_PAIRS,
                "groups": [
                    {
                        "name": group["name"],
                        "logic": group["logic"],
                        "conditions": len(group["conditions"]),
                    }
                    for group in _group_descriptors(config)
                ],
            }
        ),
    )
    return {"status": "armed", "id": alert_id, "name": config.name}
