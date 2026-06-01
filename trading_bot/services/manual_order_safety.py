"""Safety gates for manually submitted broker orders."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from trading_bot.config import get_settings
from trading_bot.execution.broker_base import OrderSide
from trading_bot.execution.broker_manager import BrokerManager, BrokerOperationError
from trading_bot.services.automation_safety import (
    AutomationGateResult,
    requires_live_safety_for_broker,
    validate_live_execution_gate,
    validate_live_risk_constraints,
)


@dataclass(frozen=True)
class ManualOrderSafetyInput:
    broker_id: str
    symbol: str
    side: OrderSide
    quantity: float
    price: float | None = None
    stop_loss: float | None = None


def _invalid_order_result(reason: str, detail: dict[str, Any]) -> AutomationGateResult:
    return AutomationGateResult(False, reason, detail)


async def validate_manual_order_safety(
    order: ManualOrderSafetyInput,
    *,
    broker_manager: BrokerManager,
) -> AutomationGateResult:
    """Validate a manual order before it can reach a live broker adapter."""
    status = broker_manager.get_broker_status(order.broker_id)
    if not status["exists"]:
        return _invalid_order_result("broker_not_found", {"brokerId": order.broker_id})
    if not status["connected"]:
        return _invalid_order_result("broker_not_connected", {"brokerId": order.broker_id})

    if not requires_live_safety_for_broker(order.broker_id, status):
        return AutomationGateResult(True, detail={"liveSafetyRequired": False})

    live_gate = validate_live_execution_gate(
        mode="live",
        active_mode="live",
        broker_id=order.broker_id,
        broker_manager=broker_manager,
    )
    if not live_gate.allowed:
        return live_gate

    if order.price is None or order.price <= 0:
        return _invalid_order_result(
            "manual_live_order_requires_price",
            {"brokerId": order.broker_id, "symbol": order.symbol, "price": order.price},
        )
    if order.stop_loss is None or order.stop_loss <= 0:
        return _invalid_order_result(
            "manual_live_order_requires_stop_loss",
            {"brokerId": order.broker_id, "symbol": order.symbol, "stopLoss": order.stop_loss},
        )

    try:
        balance = await broker_manager.get_balance(order.broker_id)
        positions = await broker_manager.get_positions(order.broker_id)
    except BrokerOperationError as exc:
        return _invalid_order_result(
            "broker_context_unavailable",
            {"brokerId": order.broker_id, "category": exc.category},
        )

    settings = get_settings()
    side = order.side.value if isinstance(order.side, OrderSide) else str(order.side)
    return validate_live_risk_constraints(
        symbol=order.symbol,
        side=side,
        quantity=order.quantity,
        current_price=order.price,
        stop_loss=order.stop_loss,
        balance=balance,
        positions=positions,
        allocation_percent=float(settings.risk_per_trade) * 100,
        max_positions=int(settings.max_positions),
    )
