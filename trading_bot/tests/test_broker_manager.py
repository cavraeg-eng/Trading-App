import asyncio
from typing import Dict, List, Optional

import pytest

from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerCapabilities,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderType,
)
from trading_bot.execution.broker_manager import BrokerManager, BrokerOperationError


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class FakeBroker(BaseBroker):
    def __init__(self, broker_id: str = "fake"):
        super().__init__(broker_id, "Fake Broker", "fake")
        self.required_credentials = ["api_key"]
        self.supported_environments = ["paper", "live"]
        self.supported_markets = ["test"]
        self.capabilities = BrokerCapabilities(modify_trade=False)
        self.connected_credentials: Optional[Dict[str, str]] = None

    async def connect(self, credentials: Dict[str, str]) -> bool:
        self.connected_credentials = credentials
        self.connected = True
        return True

    async def disconnect(self) -> bool:
        self.connected = False
        return True

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None,
        take_profit_3: Optional[float] = None,
    ) -> BrokerOrder:
        return BrokerOrder(
            order_id="fake-order",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=quantity,
            price=price,
            broker_id=self.broker_id,
        )

    async def cancel_order(self, order_id: str) -> bool:
        return True

    async def get_positions(self) -> List[BrokerPosition]:
        return []

    async def get_balance(self) -> BrokerBalance:
        return BrokerBalance(total_equity=1000, available_margin=900, used_margin=100)

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        return BrokerOrder(
            order_id=order_id,
            symbol="EUR/USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1,
            broker_id=self.broker_id,
        )


def test_manager_registers_selects_and_reports_sanitized_status():
    manager = BrokerManager(register_defaults=False, persist_state=False)
    broker = FakeBroker()

    assert manager.register_broker(broker) is True
    assert manager.register_broker(broker) is True
    assert manager.set_active_broker("fake") is True
    assert run_async(manager.connect("fake", {"api_key": "secret", "environment": "live"})) is True

    status = manager.get_broker_status("fake")

    assert status["exists"] is True
    assert status["connected"] is True
    assert status["is_active"] is True
    assert status["capabilities"]["modify_trade"] is False
    assert status["connection_schema"]["required_credentials"] == ["api_key"]
    assert "secret" not in str(status)
    assert broker.connected_credentials == {"api_key": "secret", "environment": "live"}


def test_selecting_unknown_broker_raises_safe_manager_error():
    manager = BrokerManager(register_defaults=False, persist_state=False)

    with pytest.raises(BrokerOperationError) as exc:
        manager.set_active_broker("missing")

    assert exc.value.status_code == 404
    assert exc.value.category == "not_found"
    assert "missing" in exc.value.detail


def test_missing_credentials_raise_safe_configuration_error():
    manager = BrokerManager(register_defaults=False, persist_state=False)
    manager.register_broker(FakeBroker())

    with pytest.raises(BrokerOperationError) as exc:
        run_async(manager.connect("fake", {}))

    assert exc.value.status_code == 400
    assert exc.value.category == "missing_credentials"
    assert "api_key" in exc.value.detail


def test_unsupported_capability_is_explicit():
    manager = BrokerManager(register_defaults=False, persist_state=False)
    broker = FakeBroker()
    manager.register_broker(broker)
    run_async(manager.connect("fake", {"api_key": "secret"}))

    with pytest.raises(BrokerOperationError) as exc:
        run_async(manager.modify_trade("fake", "trade-1", stop_loss=1.1))

    assert exc.value.status_code == 501
    assert exc.value.category == "unsupported_capability"
    assert "modify_trade" in exc.value.detail