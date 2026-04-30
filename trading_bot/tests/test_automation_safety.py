from trading_bot.config import settings as settings_module
from trading_bot.config.settings import Settings, TradingMode
from trading_bot.execution.broker_base import BrokerBalance, BrokerPosition
from trading_bot.services.automation_safety import (
    validate_live_execution_gate,
    validate_live_risk_constraints,
    validate_signal_quality,
)


class FakeBrokerManager:
    def __init__(self, status):
        self.status = status

    def get_broker_status(self, broker_id: str) -> dict:
        return self.status


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