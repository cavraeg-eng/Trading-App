"""Prediction confidence calibration and no-trade gate evaluation."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Optional

from trading_bot.api.models import PredictionNoTradeReason
from trading_bot.config import get_settings


@dataclass(frozen=True)
class PredictionQualityConfig:
    min_actionable_confidence: float = 62.0
    stale_data_seconds: float = 900.0
    max_spread_bps: float = 8.0
    min_risk_reward: float = 1.35
    volatility_spike_atr_pct: float = 2.5


@dataclass(frozen=True)
class NoTradeGate:
    code: PredictionNoTradeReason
    message: str
    blocking: bool = True
    context: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PredictionQualityResult:
    confidence: float
    gates: list[NoTradeGate]


def quality_config_from_settings() -> PredictionQualityConfig:
    settings = get_settings()
    return PredictionQualityConfig(
        min_actionable_confidence=float(settings.prediction_min_actionable_confidence),
        stale_data_seconds=float(settings.prediction_stale_data_seconds),
        max_spread_bps=float(settings.prediction_max_spread_bps),
        min_risk_reward=float(settings.prediction_min_risk_reward),
        volatility_spike_atr_pct=float(settings.prediction_volatility_spike_atr_pct),
    )


def evaluate_prediction_quality(
    analysis: Optional[dict[str, Any]],
    metadata: Optional[dict[str, Any]],
    broker_context: Optional[Any] = None,
    config: Optional[PredictionQualityConfig] = None,
) -> PredictionQualityResult:
    config = config or quality_config_from_settings()
    metadata = metadata or {}
    gates: list[NoTradeGate] = []

    if not analysis:
        return PredictionQualityResult(
            confidence=0.0,
            gates=[NoTradeGate(
                code=PredictionNoTradeReason.INSUFFICIENT_DATA,
                message="Market data or analysis features are unavailable.",
            )],
        )

    signal = str(analysis.get("signal") or "hold").lower()
    raw_confidence = _finite_float(analysis.get("confidence"), 0.0)
    current_price = _finite_float(analysis.get("currentPrice"), 0.0)
    atr = _finite_float(analysis.get("atr"), 0.0)
    risk_reward = _finite_float(analysis.get("riskReward"), 0.0)
    quality_flags = {str(flag) for flag in metadata.get("qualityFlags") or []}
    freshness_seconds = _finite_float(metadata.get("freshnessSeconds"), -1.0)

    _append_data_gates(gates, analysis, metadata, quality_flags, freshness_seconds, config)
    _append_signal_gates(gates, analysis, signal, risk_reward, current_price, atr, config)
    _append_account_risk_gates(gates, broker_context)

    calibrated_confidence = _calibrated_confidence(
        raw_confidence=raw_confidence,
        signal=signal,
        analysis=analysis,
        metadata=metadata,
        current_price=current_price,
        atr=atr,
        risk_reward=risk_reward,
        gates=gates,
        config=config,
    )

    if signal in {"buy", "sell"} and calibrated_confidence < config.min_actionable_confidence:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.LOW_CONFIDENCE,
            message=(
                f"Calibrated confidence {calibrated_confidence:.0f}% is below the "
                f"{config.min_actionable_confidence:.0f}% actionable threshold."
            ),
            context={
                "confidence": round(calibrated_confidence, 2),
                "minimumConfidence": config.min_actionable_confidence,
            },
        ))

    return PredictionQualityResult(confidence=round(_clamp(calibrated_confidence, 0.0, 100.0), 2), gates=gates)


def _append_data_gates(
    gates: list[NoTradeGate],
    analysis: dict[str, Any],
    metadata: dict[str, Any],
    quality_flags: set[str],
    freshness_seconds: float,
    config: PredictionQualityConfig,
) -> None:
    if "stale_data" in quality_flags or metadata.get("marketStatus") == "stale" or freshness_seconds > config.stale_data_seconds:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.STALE_DATA,
            message="Market data is stale; wait for a fresh quote/candle before acting.",
            context={
                "freshnessSeconds": freshness_seconds if freshness_seconds >= 0 else None,
                "maxFreshnessSeconds": config.stale_data_seconds,
                "marketStatus": metadata.get("marketStatus"),
            },
        ))

    spread_bps = _extract_spread_bps(analysis, metadata)
    if spread_bps is not None and spread_bps > config.max_spread_bps:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.EXCESSIVE_SPREAD,
            message="Estimated spread is too wide for a clean entry.",
            context={"spreadBps": round(spread_bps, 2), "maxSpreadBps": config.max_spread_bps},
        ))

    missing_features = _missing_required_features(analysis)
    if missing_features:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.MISSING_FEATURES,
            message=f"Required prediction features are missing: {', '.join(missing_features)}.",
            context={"missingFeatures": missing_features},
        ))


def _append_signal_gates(
    gates: list[NoTradeGate],
    analysis: dict[str, Any],
    signal: str,
    risk_reward: float,
    current_price: float,
    atr: float,
    config: PredictionQualityConfig,
) -> None:
    if _has_conflicting_timeframes(analysis, signal):
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.CONFLICTING_SIGNALS,
            message="Primary signal conflicts with higher timeframe alignment.",
        ))

    if signal in {"buy", "sell"} and risk_reward < config.min_risk_reward:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.REWARD_RISK_COMPRESSED,
            message="Reward-to-risk is too compressed for an actionable setup.",
            context={"riskReward": risk_reward, "minimumRiskReward": config.min_risk_reward},
        ))

    atr_pct = (atr / current_price) * 100.0 if current_price > 0 and atr > 0 else 0.0
    if atr_pct > config.volatility_spike_atr_pct:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.HIGH_VOLATILITY_SPIKE,
            message="ATR indicates a volatility spike; wait for conditions to normalize.",
            context={"atrPercent": round(atr_pct, 3), "maxAtrPercent": config.volatility_spike_atr_pct},
        ))


def _append_account_risk_gates(gates: list[NoTradeGate], broker_context: Optional[Any]) -> None:
    if broker_context is None:
        return

    equity = _finite_float(getattr(broker_context, "equity", None), 0.0)
    available_margin = _finite_float(getattr(broker_context, "available_margin", None), 0.0)
    max_risk_percent = getattr(broker_context, "max_risk_percent", None)
    if equity < 0 or available_margin < 0:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.RISK_LIMITS,
            message="Account risk context contains invalid balance or margin values.",
        ))
    elif equity > 0 and available_margin / equity < 0.1:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.RISK_LIMITS,
            message="Available margin is below the safe threshold for a new trade.",
            context={"availableMarginRatio": round(available_margin / equity, 4)},
        ))
    elif max_risk_percent is not None and _finite_float(max_risk_percent, 0.0) <= 0:
        gates.append(NoTradeGate(
            code=PredictionNoTradeReason.RISK_LIMITS,
            message="Account risk settings do not allow new trade risk.",
        ))


def _calibrated_confidence(
    *,
    raw_confidence: float,
    signal: str,
    analysis: dict[str, Any],
    metadata: dict[str, Any],
    current_price: float,
    atr: float,
    risk_reward: float,
    gates: list[NoTradeGate],
    config: PredictionQualityConfig,
) -> float:
    score = _clamp(raw_confidence, 0.0, 100.0)

    if signal in {"buy", "sell"}:
        score += _indicator_alignment_bonus(analysis, signal)
        score += _risk_reward_bonus(risk_reward, config)
        score += _structure_proximity_bonus(analysis, current_price, atr)
        score += _trend_alignment_bonus(analysis, signal)
    else:
        score = min(score, 54.0)

    quality_flags = {str(flag) for flag in metadata.get("qualityFlags") or []}
    if metadata.get("isFallback") or "fallback_source" in quality_flags:
        score -= 6.0
    if metadata.get("marketStatus") == "delayed":
        score -= 4.0
    score -= sum(18.0 if gate.blocking else 4.0 for gate in gates)

    return _clamp(score, 0.0, 100.0)


def _indicator_alignment_bonus(analysis: dict[str, Any], signal: str) -> float:
    indicators = analysis.get("indicators") or []
    if not indicators:
        return -8.0
    aligned = 0
    opposed = 0
    expected = "bullish" if signal == "buy" else "bearish"
    opposite = "bearish" if signal == "buy" else "bullish"
    for indicator in indicators:
        state = str(indicator.get("signal") or "").lower()
        if state == expected:
            aligned += 1
        elif state == opposite:
            opposed += 1
    return _clamp((aligned - opposed) * 2.0, -10.0, 10.0)


def _risk_reward_bonus(risk_reward: float, config: PredictionQualityConfig) -> float:
    if risk_reward <= 0:
        return -8.0
    if risk_reward < config.min_risk_reward:
        return -10.0
    return _clamp((risk_reward - config.min_risk_reward) * 4.0, 0.0, 8.0)


def _structure_proximity_bonus(analysis: dict[str, Any], current_price: float, atr: float) -> float:
    if current_price <= 0 or atr <= 0:
        return 0.0
    anchor = analysis.get("anchorModel") or {}
    support = _finite_float(anchor.get("support"), 0.0)
    resistance = _finite_float(anchor.get("resistance"), 0.0)
    nearest = min(
        abs(current_price - support) if support > 0 else math.inf,
        abs(resistance - current_price) if resistance > 0 else math.inf,
    )
    if nearest is math.inf:
        return 0.0
    distance_atr = nearest / atr
    if distance_atr <= 0.5:
        return 2.0
    if distance_atr >= 3.0:
        return -4.0
    return 0.0


def _trend_alignment_bonus(analysis: dict[str, Any], signal: str) -> float:
    bias = str((analysis.get("higherTimeframeBias") or {}).get("direction") or "").lower()
    if not bias:
        return 0.0
    expected = "bullish" if signal == "buy" else "bearish"
    if bias == expected:
        return 6.0
    if bias in {"bullish", "bearish"}:
        return -10.0
    return 0.0


def _has_conflicting_timeframes(analysis: dict[str, Any], signal: str) -> bool:
    if signal not in {"buy", "sell"}:
        return False
    bias = str((analysis.get("higherTimeframeBias") or {}).get("direction") or "").lower()
    expected = "bullish" if signal == "buy" else "bearish"
    if bias in {"bullish", "bearish"} and bias != expected:
        return True
    multi = analysis.get("multiTimeframe") or []
    if not multi:
        return False
    expected_signal = "BUY" if signal == "buy" else "SELL"
    opposing = "SELL" if signal == "buy" else "BUY"
    directional = [str(row.get("signal") or "").upper() for row in multi]
    return directional.count(opposing) >= 2 and directional.count(opposing) > directional.count(expected_signal)


def _missing_required_features(analysis: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("currentPrice", "confidence"):
        value = analysis.get(key)
        if value is None:
            missing.append(key)
    return missing


def _extract_spread_bps(analysis: dict[str, Any], metadata: dict[str, Any]) -> Optional[float]:
    for container in (analysis, metadata):
        for key in ("spreadBps", "spread_bps"):
            if key in container:
                return _finite_float(container.get(key), 0.0)
    spread = _finite_float(analysis.get("spread") or metadata.get("spread"), 0.0)
    price = _finite_float(analysis.get("currentPrice") or metadata.get("midPrice"), 0.0)
    if spread > 0 and price > 0:
        return (spread / price) * 10000.0
    return None


def _finite_float(value: Any, default: float = 0.0) -> float:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(converted) or math.isinf(converted):
        return default
    return converted


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))