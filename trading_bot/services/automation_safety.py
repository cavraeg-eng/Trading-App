"""Safety gates for automated execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional

from trading_bot.config import get_settings
from trading_bot.execution.broker_base import BrokerBalance, BrokerPosition
from trading_bot.execution.broker_manager import BrokerManager


LIVE_READY_ENVIRONMENTS = {
    "alpaca": {"live"},
    "oanda": {"live"},
}


@dataclass
class AutomationGateResult:
    allowed: bool
    reason: str = "ok"
    detail: Dict[str, Any] = field(default_factory=dict)


def _broker_environment(broker_info: dict) -> Optional[str]:
    info = broker_info.get("info") or {}
    environment = info.get("environment") or broker_info.get("environment")
    return str(environment).lower() if environment else None


def _is_live_ready_environment(broker_id: str, broker_info: dict) -> bool:
    environment = _broker_environment(broker_info)
    if broker_id in LIVE_READY_ENVIRONMENTS:
        return environment in LIVE_READY_ENVIRONMENTS[broker_id]
    if broker_info.get("info", {}).get("type") == "ccxt":
        return environment in {"live", "production", "mainnet"} if environment else False
    return environment in {"live", "production", "mainnet"} if environment else False


def validate_live_execution_gate(
    *,
    mode: str,
    active_mode: str,
    broker_id: Optional[str],
    broker_manager: BrokerManager,
) -> AutomationGateResult:
    if mode != "live":
        return AutomationGateResult(True)

    settings = get_settings()
    if settings.trading_mode.value != "live":
        return AutomationGateResult(
            False,
            "live_mode_not_enabled",
            {"configuredTradingMode": settings.trading_mode.value},
        )

    if active_mode != "live":
        return AutomationGateResult(
            False,
            "strategy_not_configured_for_live",
            {"activeMode": active_mode},
        )

    if not broker_id:
        return AutomationGateResult(False, "missing_live_broker")

    status = broker_manager.get_broker_status(broker_id)
    if not status["exists"]:
        return AutomationGateResult(False, "broker_not_found", {"brokerId": broker_id})
    if not status["connected"]:
        return AutomationGateResult(False, "broker_not_connected", {"brokerId": broker_id})
    if not status["is_active"]:
        return AutomationGateResult(False, "broker_not_active", {"brokerId": broker_id})
    if not _is_live_ready_environment(broker_id, status):
        return AutomationGateResult(
            False,
            "broker_not_live_environment",
            {"brokerId": broker_id, "environment": _broker_environment(status) or "unknown"},
        )

    return AutomationGateResult(True)


def validate_signal_quality(analysis: dict, *, minimum_confidence: float = 60.0) -> AutomationGateResult:
    signal = str(analysis.get("signal") or "hold").lower()
    confidence = float(analysis.get("confidence") or 0.0)
    if signal == "hold" or confidence < minimum_confidence:
        return AutomationGateResult(
            False,
            "signal_threshold",
            {"signal": signal, "confidence": confidence, "minimumConfidence": minimum_confidence},
        )

    current_price = float(analysis.get("currentPrice") or 0.0)
    stop_loss = float(analysis.get("stopLoss") or 0.0)
    if current_price <= 0:
        return AutomationGateResult(False, "invalid_price", {"currentPrice": current_price})
    if stop_loss <= 0 or stop_loss == current_price:
        return AutomationGateResult(
            False,
            "invalid_stop_loss",
            {"currentPrice": current_price, "stopLoss": stop_loss},
        )

    side = "buy" if "buy" in signal else "sell" if "sell" in signal else None
    if not side:
        return AutomationGateResult(False, "unsupported_signal", {"signal": signal})
    if side == "buy" and stop_loss >= current_price:
        return AutomationGateResult(
            False,
            "invalid_stop_loss_direction",
            {"side": side, "currentPrice": current_price, "stopLoss": stop_loss},
        )
    if side == "sell" and stop_loss <= current_price:
        return AutomationGateResult(
            False,
            "invalid_stop_loss_direction",
            {"side": side, "currentPrice": current_price, "stopLoss": stop_loss},
        )

    return AutomationGateResult(True, detail={"signal": signal, "confidence": confidence, "side": side})


def validate_live_risk_constraints(
    *,
    symbol: str,
    side: str,
    quantity: float,
    current_price: float,
    stop_loss: float,
    balance: BrokerBalance,
    positions: Iterable[BrokerPosition],
    allocation_percent: float,
    max_positions: int,
) -> AutomationGateResult:
    if quantity <= 0:
        return AutomationGateResult(False, "invalid_quantity", {"quantity": quantity})

    equity = float(balance.total_equity or 0.0)
    available_margin = float(balance.available_margin or 0.0)
    if equity <= 0 or available_margin <= 0:
        return AutomationGateResult(
            False,
            "no_broker_balance",
            {"totalEquity": equity, "availableMargin": available_margin},
        )

    open_positions = list(positions)
    same_symbol_positions = [position for position in open_positions if position.symbol == symbol]
    if len(same_symbol_positions) >= max_positions:
        return AutomationGateResult(
            False,
            "max_positions_reached",
            {"openPositions": len(same_symbol_positions), "maxPositions": max_positions},
        )

    risk_amount = abs(current_price - stop_loss) * quantity
    max_risk_amount = equity * (allocation_percent / 100.0)
    if max_risk_amount <= 0:
        return AutomationGateResult(
            False,
            "invalid_risk_allocation",
            {"allocationPercent": allocation_percent},
        )
    if risk_amount > max_risk_amount * 1.01:
        return AutomationGateResult(
            False,
            "risk_amount_limit",
            {
                "riskAmount": round(risk_amount, 2),
                "maxRiskAmount": round(max_risk_amount, 2),
                "allocationPercent": allocation_percent,
            },
        )

    settings = get_settings()
    leverage = max(float(settings.leverage or 1.0), 1.0)
    notional = abs(quantity * current_price)
    existing_exposure = sum(abs(position.quantity * position.current_price) for position in open_positions)
    max_position_notional = equity * settings.max_position_size * leverage
    max_total_exposure = equity * settings.max_total_exposure * leverage
    if notional > max_position_notional:
        return AutomationGateResult(
            False,
            "position_size_limit",
            {
                "notional": round(notional, 2),
                "maxPositionNotional": round(max_position_notional, 2),
                "allocationPercent": allocation_percent,
            },
        )
    if existing_exposure + notional > max_total_exposure:
        return AutomationGateResult(
            False,
            "total_exposure_limit",
            {
                "existingExposure": round(existing_exposure, 2),
                "newNotional": round(notional, 2),
                "maxTotalExposure": round(max_total_exposure, 2),
            },
        )

    return AutomationGateResult(
        True,
        detail={
            "notional": round(notional, 2),
            "existingExposure": round(existing_exposure, 2),
            "riskAmount": round(risk_amount, 2),
            "maxRiskAmount": round(max_risk_amount, 2),
            "maxPositionNotional": round(max_position_notional, 2),
            "maxTotalExposure": round(max_total_exposure, 2),
            "side": side,
        },
    )