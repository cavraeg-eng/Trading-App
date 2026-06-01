"""Deterministic trade setup suggestion generation."""

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Optional

from trading_bot.api.models import (
    PredictionNoTradeReason,
    PredictionPriceZone,
    PredictionRecommendation,
    PredictionTarget,
    PredictionWarning,
    PredictionWarningCode,
)

MIN_RISK_REWARD = 1.35
TIMEFRAME_EXPIRY_CANDLES = {
    "1m": 8,
    "5m": 6,
    "15m": 5,
    "1h": 4,
    "4h": 3,
    "1d": 2,
}
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}


class TradeSuggestionResult:
    def __init__(
        self,
        recommendation: PredictionRecommendation,
        entry: Optional[PredictionPriceZone] = None,
        stop_loss: Optional[float] = None,
        targets: Optional[list[PredictionTarget]] = None,
        invalidation_level: Optional[float] = None,
        risk_reward: Optional[float] = None,
        expires_at: Optional[datetime] = None,
        no_trade_reason: Optional[PredictionNoTradeReason] = None,
        warnings: Optional[list[PredictionWarning]] = None,
        annotations: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        self.recommendation = recommendation
        self.entry = entry
        self.stop_loss = stop_loss
        self.targets = targets or []
        self.invalidation_level = invalidation_level
        self.risk_reward = risk_reward
        self.expires_at = expires_at
        self.no_trade_reason = no_trade_reason
        self.warnings = warnings or []
        self.annotations = annotations or []


def _to_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if isfinite(parsed) else None


def _warning(message: str) -> PredictionWarning:
    return PredictionWarning(
        code=PredictionWarningCode.MODEL_DEGRADED,
        severity="warning",
        message=message,
    )


def _expiry_for_timeframe(timeframe: str, now: Optional[datetime] = None) -> datetime:
    evaluated_at = now or datetime.now(tz=timezone.utc)
    candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    candle_count = TIMEFRAME_EXPIRY_CANDLES.get(timeframe, 4)
    return evaluated_at + timedelta(seconds=candle_seconds * candle_count)


def _entry_mid(entry: PredictionPriceZone) -> float:
    return (entry.min + entry.max) / 2


def _targets(analysis: dict[str, Any], entry_mid: float, stop_loss: float) -> list[PredictionTarget]:
    risk = abs(entry_mid - stop_loss)
    targets: list[PredictionTarget] = []
    for index, key in enumerate(("takeProfit1", "takeProfit2", "takeProfit3"), start=1):
        price = _to_float(analysis.get(key))
        if price is None:
            continue
        targets.append(PredictionTarget(
            label=f"TP{index}",
            price=price,
            reward_risk=round(abs(price - entry_mid) / risk, 2) if risk > 0 else None,
            size_percent={1: 40, 2: 35, 3: 25}[index],
        ))
    return targets


def _best_reward_risk(targets: list[PredictionTarget]) -> float:
    reward_risks = [target.reward_risk for target in targets if target.reward_risk is not None]
    return max(reward_risks) if reward_risks else 0.0


def _coerce_required_levels(
    current_price: Optional[float],
    entry_min: Optional[float],
    entry_max: Optional[float],
    stop_loss: Optional[float],
) -> Optional[tuple[float, float, float, float]]:
    if current_price is None or entry_min is None or entry_max is None or stop_loss is None:
        return None
    return current_price, entry_min, entry_max, stop_loss


def _directionally_valid(
    recommendation: PredictionRecommendation,
    current_price: float,
    entry: PredictionPriceZone,
    stop_loss: float,
    targets: list[PredictionTarget],
    minimum_distance: float,
) -> list[str]:
    problems: list[str] = []
    entry_mid = _entry_mid(entry)

    if recommendation == PredictionRecommendation.BUY:
        if entry.max > current_price + minimum_distance:
            problems.append("Long entry zone is above the current price.")
        if stop_loss >= min(entry.min, current_price) - minimum_distance:
            problems.append("Long stop loss is not safely below entry/current price.")
        if any(target.price <= max(entry_mid, current_price) + minimum_distance for target in targets):
            problems.append("Long take-profit target is not above entry/current price.")
    elif recommendation == PredictionRecommendation.SELL:
        if entry.min < current_price - minimum_distance:
            problems.append("Short entry zone is below the current price.")
        if stop_loss <= max(entry.max, current_price) + minimum_distance:
            problems.append("Short stop loss is not safely above entry/current price.")
        if any(target.price >= min(entry_mid, current_price) - minimum_distance for target in targets):
            problems.append("Short take-profit target is not below entry/current price.")

    return problems


def _no_trade(
    reason: PredictionNoTradeReason,
    warnings: list[PredictionWarning],
    annotations: Optional[list[dict[str, Any]]] = None,
) -> TradeSuggestionResult:
    return TradeSuggestionResult(
        recommendation=PredictionRecommendation.NO_TRADE,
        no_trade_reason=reason,
        warnings=warnings,
        annotations=annotations or [],
    )


def _warnings(messages: list[str]) -> list[PredictionWarning]:
    return [_warning(message) for message in messages]


def generate_trade_suggestion(
    analysis: Optional[dict[str, Any]],
    recommendation: PredictionRecommendation,
    timeframe: str,
    default_no_trade_reason: PredictionNoTradeReason,
    evaluated_at: Optional[datetime] = None,
) -> TradeSuggestionResult:
    if recommendation in {PredictionRecommendation.HOLD, PredictionRecommendation.NO_TRADE}:
        return TradeSuggestionResult(
            recommendation=recommendation,
            no_trade_reason=default_no_trade_reason if recommendation == PredictionRecommendation.NO_TRADE else None,
            annotations=[{
                "type": "stand_aside",
                "label": "No actionable execution levels",
                "message": str((analysis or {}).get("reason") or "Market context does not support a directional setup."),
            }],
        )

    warnings: list[PredictionWarning] = []
    if not analysis:
        return _no_trade(
            PredictionNoTradeReason.INSUFFICIENT_DATA,
            [_warning("Market analysis was unavailable, so no actionable setup was generated.")],
        )

    current_price = _to_float(analysis.get("currentPrice"))
    entry_range = analysis.get("entryRange") or {}
    entry_min = _to_float(entry_range.get("min"))
    entry_max = _to_float(entry_range.get("max"))
    stop_loss = _to_float(analysis.get("stopLoss"))
    atr = _to_float(analysis.get("atr"))

    required_levels = _coerce_required_levels(current_price, entry_min, entry_max, stop_loss)
    if required_levels is None:
        return _no_trade(
            PredictionNoTradeReason.INSUFFICIENT_DATA,
            [_warning("Required entry, stop, or current-price data was missing.")],
        )
    current_price, entry_min, entry_max, stop_loss = required_levels

    entry = PredictionPriceZone(
        min=min(entry_min, entry_max),
        max=max(entry_min, entry_max),
        label="Entry zone",
    )
    entry_mid = _entry_mid(entry)
    targets = _targets(analysis, entry_mid, stop_loss)
    if not targets:
        return _no_trade(
            PredictionNoTradeReason.INSUFFICIENT_DATA,
            [_warning("Take-profit targets were unavailable.")],
        )

    risk_distance = abs(entry_mid - stop_loss)
    risk_reward = round(_best_reward_risk(targets), 2) if risk_distance > 0 else 0.0
    minimum_distance = max((atr or 0) * 0.05, abs(current_price) * 0.00005, 10 ** -6)

    validation_errors = _directionally_valid(
        recommendation,
        current_price,
        entry,
        stop_loss,
        targets,
        minimum_distance,
    )
    if risk_distance < minimum_distance:
        validation_errors.append("Risk distance is below the minimum price distance.")
    if risk_reward < MIN_RISK_REWARD:
        validation_errors.append(
            f"Best target risk/reward {risk_reward:.2f} is below the {MIN_RISK_REWARD:.2f} minimum."
        )
    elif (targets[0].reward_risk or 0.0) < MIN_RISK_REWARD and len(targets) > 1:
        warnings.append(_warning(
            "TP1 is conservative; later targets provide the minimum reward-to-risk runway."
        ))

    if validation_errors:
        return _no_trade(
            PredictionNoTradeReason.REWARD_RISK_COMPRESSED
            if any("risk/reward" in problem.lower() for problem in validation_errors)
            else PredictionNoTradeReason.INSUFFICIENT_DATA,
            _warnings(validation_errors),
            [{
                "type": "validation",
                "label": "Setup rejected",
                "messages": validation_errors,
            }],
        )

    direction_label = "Long" if recommendation == PredictionRecommendation.BUY else "Short"
    annotations = [
        {
            "type": "entry_zone",
            "label": f"{direction_label} entry zone",
            "min": entry.min,
            "max": entry.max,
        },
        {
            "type": "risk_reward",
            "label": "Risk/reward",
            "value": risk_reward,
        },
        {
            "type": "invalidation",
            "label": "Invalidation",
            "price": stop_loss,
            "message": f"{direction_label} setup invalidates if price trades through stop loss.",
        },
    ]

    return TradeSuggestionResult(
        recommendation=recommendation,
        entry=entry,
        stop_loss=stop_loss,
        targets=targets,
        invalidation_level=stop_loss,
        risk_reward=risk_reward,
        expires_at=_expiry_for_timeframe(timeframe, evaluated_at),
        warnings=warnings,
        annotations=annotations,
    )
