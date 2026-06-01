from trading_bot.config import settings as settings_module
from trading_bot.config.settings import Settings, TradingMode
from trading_bot.execution.broker_base import BrokerBalance, BrokerPosition, OrderSide
from trading_bot.services.automation_safety import (
    validate_live_execution_gate,
    validate_live_risk_constraints,
    validate_signal_quality,
)
from trading_bot.services.manual_order_safety import (
    ManualOrderSafetyInput,
    validate_manual_order_safety,
)


class FakeBrokerManager:
    def __init__(self, status):
        self.status = status
        self.balance = BrokerBalance(total_equity=10000.0, available_margin=10000.0, used_margin=0.0)
        self.positions = []

    def get_broker_status(self, broker_id: str) -> dict:
        return self.status

    async def get_balance(self, broker_id: str) -> BrokerBalance:
        return self.balance

    async def get_positions(self, broker_id: str) -> list[BrokerPosition]:
        return self.positions


def set_settings(monkeypatch, trading_mode: TradingMode = TradingMode.PAPER):
    monkeypatch.setattr(
        settings_module,
        "_settings",
        Settings(trading_mode=trading_mode),
    )


def test_live_gate_requires_global_live_mode(monkeypatch):
    set_settings(monkeypatch, TradingMode.PAPER)

    result = validate_live_execution_gate(
        mode="live",
        active_mode="live",
        broker_id="oanda",
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "live"},
        }),
    )

    assert result.allowed is False
    assert result.reason == "live_mode_not_enabled"


def test_live_gate_rejects_practice_broker_environment(monkeypatch):
    set_settings(monkeypatch, TradingMode.LIVE)

    result = validate_live_execution_gate(
        mode="live",
        active_mode="live",
        broker_id="oanda",
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "practice"},
        }),
    )

    assert result.allowed is False
    assert result.reason == "broker_not_live_environment"


def test_signal_quality_rejects_invalid_stop_loss_direction():
    result = validate_signal_quality({
        "signal": "strong_buy",
        "confidence": 82,
        "currentPrice": 4700.0,
        "stopLoss": 4710.0,
    })

    assert result.allowed is False
    assert result.reason == "invalid_stop_loss_direction"


def test_live_risk_gate_rejects_position_size_limit(monkeypatch):
    set_settings(monkeypatch, TradingMode.LIVE)

    result = validate_live_risk_constraints(
        symbol="XAU/USD",
        side="buy",
        quantity=1.0,
        current_price=4700.0,
        stop_loss=4680.0,
        balance=BrokerBalance(total_equity=10000.0, available_margin=10000.0, used_margin=0.0),
        positions=[],
        allocation_percent=2.0,
        max_positions=1,
    )

    assert result.allowed is False
    assert result.reason == "position_size_limit"


def test_live_risk_gate_rejects_symbol_exposure(monkeypatch):
    set_settings(monkeypatch, TradingMode.LIVE)

    result = validate_live_risk_constraints(
        symbol="XAU/USD",
        side="buy",
        quantity=0.01,
        current_price=4700.0,
        stop_loss=4680.0,
        balance=BrokerBalance(total_equity=10000.0, available_margin=10000.0, used_margin=0.0),
        positions=[
            BrokerPosition(
                symbol="XAU/USD",
                side="long",
                quantity=0.01,
                entry_price=4690.0,
                current_price=4700.0,
                unrealized_pnl=0.1,
            )
        ],
        allocation_percent=2.0,
        max_positions=1,
    )

    assert result.allowed is False
    assert result.reason == "max_positions_reached"


async def test_manual_live_order_uses_global_live_mode_gate(monkeypatch):
    set_settings(monkeypatch, TradingMode.PAPER)

    result = await validate_manual_order_safety(
        ManualOrderSafetyInput(
            broker_id="oanda",
            symbol="XAU/USD",
            side=OrderSide.BUY,
            quantity=0.01,
            price=4700.0,
            stop_loss=4680.0,
        ),
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "live"},
        }),
    )

    assert result.allowed is False
    assert result.reason == "live_mode_not_enabled"


async def test_manual_live_order_requires_price_and_stop(monkeypatch):
    set_settings(monkeypatch, TradingMode.LIVE)

    result = await validate_manual_order_safety(
        ManualOrderSafetyInput(
            broker_id="oanda",
            symbol="XAU/USD",
            side=OrderSide.BUY,
            quantity=0.01,
        ),
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "live"},
        }),
    )

    assert result.allowed is False
    assert result.reason == "manual_live_order_requires_price"


async def test_manual_live_order_applies_live_risk_gate(monkeypatch):
    set_settings(monkeypatch, TradingMode.LIVE)

    result = await validate_manual_order_safety(
        ManualOrderSafetyInput(
            broker_id="oanda",
            symbol="XAU/USD",
            side=OrderSide.BUY,
            quantity=1.0,
            price=4700.0,
            stop_loss=4680.0,
        ),
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "live"},
        }),
    )

    assert result.allowed is False
    assert result.reason == "position_size_limit"


async def test_manual_practice_order_does_not_require_live_safety(monkeypatch):
    set_settings(monkeypatch, TradingMode.PAPER)

    result = await validate_manual_order_safety(
        ManualOrderSafetyInput(
            broker_id="oanda",
            symbol="XAU/USD",
            side=OrderSide.BUY,
            quantity=1.0,
        ),
        broker_manager=FakeBrokerManager({
            "exists": True,
            "connected": True,
            "is_active": True,
            "info": {"environment": "practice"},
        }),
    )

    assert result.allowed is True
    assert result.detail["liveSafetyRequired"] is False
