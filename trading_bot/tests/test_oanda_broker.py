import asyncio
from typing import Any, Dict, List, Optional

import httpx
import pytest

from trading_bot.execution.broker_base import OrderSide, OrderStatus, OrderType
from trading_bot.execution.broker_manager import BrokerManager, BrokerOperationError
from trading_bot.execution.brokers.oanda_broker import OANDABroker, _MISS


def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()
        asyncio.set_event_loop(asyncio.new_event_loop())


class FakeOandaClient:
    def __init__(self, responses: Dict[tuple, Any]):
        self.responses = responses
        self.requests: List[dict] = []
        self.closed = False

    async def get(self, url: str, params: Optional[dict] = None):
        return await self.request("GET", url, params=params)

    async def request(
        self,
        method: str,
        url: str,
        params: Optional[dict] = None,
        json: Optional[dict] = None,
    ):
        path = "/" + url.split("/v3/", 1)[1]
        self.requests.append({"method": method, "path": path, "params": params, "json": json})
        response = self.responses[(method, path)]
        if isinstance(response, list):
            response = response.pop(0)
        if callable(response):
            response = response(self.requests[-1])
        if isinstance(response, Exception):
            raise response
        return response

    async def aclose(self):
        self.closed = True


def json_response(status_code: int, payload: dict, url: str = "https://api.test/v3/test"):
    request = httpx.Request("GET", url)
    return httpx.Response(status_code, json=payload, request=request)


def connected_broker(client: FakeOandaClient) -> OANDABroker:
    broker = OANDABroker()
    broker._client = client
    broker._account_id = "account-1"
    broker._api_token = "secret-token"
    broker.connected = True
    return broker


def test_prepare_credentials_defaults_to_practice_and_redacts_live_without_opt_in():
    broker = OANDABroker()

    prepared = broker.prepare_credentials({"api_token": "secret-token", "account_id": "account-1"})

    assert prepared["environment"] == "practice"
    assert prepared["api_token"] == "secret-token"

    with pytest.raises(Exception) as exc:
        broker.prepare_credentials(
            {
                "api_token": "secret-token",
                "account_id": "account-1",
                "environment": "live",
            }
        )

    assert "secret-token" not in str(exc.value)
    assert "explicit live configuration" in str(exc.value)


def test_maps_account_positions_and_quote_payloads():
    client = FakeOandaClient(
        {
            ("GET", "/accounts/account-1/summary"): json_response(
                200,
                {
                    "account": {
                        "NAV": "10500.50",
                        "balance": "10000",
                        "marginAvailable": "9000.25",
                        "marginUsed": "100.75",
                        "currency": "USD",
                    }
                },
            ),
            ("GET", "/accounts/account-1/openPositions"): json_response(
                200,
                {
                    "positions": [
                        {
                            "instrument": "EUR_USD",
                            "long": {
                                "units": "1000",
                                "averagePrice": "1.0800",
                                "unrealizedPL": "12.34",
                            },
                            "short": {"units": "0"},
                        }
                    ]
                },
            ),
            ("GET", "/accounts/account-1/pricing"): json_response(
                200,
                {
                    "prices": [
                        {
                            "instrument": "EUR_USD",
                            "time": "2026-04-30T01:00:00Z",
                            "bids": [{"price": "1.0810"}],
                            "asks": [{"price": "1.0812"}],
                        }
                    ]
                },
            ),
        }
    )
    broker = connected_broker(client)

    balance = run_async(broker.get_balance())
    positions = run_async(broker.get_positions())
    quote = run_async(broker.get_quote("EUR/USD"))

    assert balance.total_equity == 10500.50
    assert balance.available_margin == 9000.25
    assert positions[0].symbol == "EUR/USD"
    assert positions[0].side == "long"
    assert positions[0].quantity == 1000
    assert positions[0].current_price == pytest.approx(1.0811)
    assert quote.bid == 1.0810
    assert quote.ask == 1.0812
    assert quote.last == pytest.approx(1.0811)


def test_place_order_uses_oanda_units_and_normalizes_fill_response():
    def capture_order(request: dict):
        assert request["json"]["order"]["type"] == "STOP"
        assert request["json"]["order"]["instrument"] == "EUR_USD"
        assert request["json"]["order"]["units"] == "-1235"
        assert request["json"]["order"]["price"] == "1.07"
        assert request["json"]["order"]["stopLossOnFill"] == {"price": "1.09"}
        assert request["json"]["order"]["takeProfitOnFill"] == {"price": "1.04"}
        return json_response(
            201,
            {
                "orderCreateTransaction": {
                    "id": "10",
                    "instrument": "EUR_USD",
                    "units": "-1235",
                    "time": "2026-04-30T01:00:00Z",
                },
                "orderFillTransaction": {
                    "id": "11",
                    "orderID": "10",
                    "units": "-1235",
                    "price": "1.0698",
                    "time": "2026-04-30T01:00:01Z",
                },
            },
        )

    client = FakeOandaClient({("POST", "/accounts/account-1/orders"): capture_order})
    broker = connected_broker(client)

    order = run_async(
        broker.place_order(
            symbol="EUR/USD",
            side=OrderSide.SELL,
            quantity=1234.6,
            order_type=OrderType.STOP,
            price=1.07,
            stop_loss=1.09,
            take_profit_1=1.05,
            take_profit_2=1.04,
        )
    )

    assert order.order_id == "10"
    assert order.status == OrderStatus.FILLED
    assert order.filled_quantity == 1235
    assert order.avg_fill_price == 1.0698


def test_cancel_order_returns_true_and_invalidates_cache():
    client = FakeOandaClient(
        {
            ("PUT", "/accounts/account-1/orders/order-1/cancel"): json_response(
                200,
                {"orderCancelTransaction": {"id": "20", "orderID": "order-1"}},
            )
        }
    )
    broker = connected_broker(client)
    broker._cache_set("positions", ["stale"])

    assert run_async(broker.cancel_order("order-1")) is True
    assert broker._cache_get("positions") is _MISS
    assert client.requests[0]["path"] == "/accounts/account-1/orders/order-1/cancel"


def test_cancel_order_does_not_retry_after_transport_error():
    client = FakeOandaClient(
        {
            ("PUT", "/accounts/account-1/orders/order-1/cancel"): httpx.TransportError(
                "connection dropped after cancel"
            )
        }
    )
    broker = connected_broker(client)

    with pytest.raises(BrokerOperationError):
        run_async(broker.cancel_order("order-1"))

    assert len(client.requests) == 1


def test_stale_refresh_uses_running_loop_task_creation(monkeypatch):
    created_tasks = []

    def fake_create_task(coro):
        created_tasks.append(coro)

        class FakeTask:
            pass

        return FakeTask()

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)
    broker = connected_broker(FakeOandaClient({}))
    broker._cache_stale_ttl = 60
    broker._cache_ttl = 0
    broker._cache_set("positions", ["stale-position"])
    broker._cache_set("balance", "stale-balance")

    positions = run_async(broker.get_positions())
    balance = run_async(broker.get_balance())

    assert positions == ["stale-position"]
    assert balance == "stale-balance"
    assert len(created_tasks) == 2
    for coro in created_tasks:
        coro.close()


def test_oanda_error_details_are_redacted():
    client = FakeOandaClient(
        {
            ("GET", "/accounts/account-1/summary"): json_response(
                401,
                {"errorMessage": "token secret-token rejected for account-1"},
            )
        }
    )
    broker = connected_broker(client)

    with pytest.raises(BrokerOperationError) as exc:
        run_async(broker.get_balance())

    assert exc.value.status_code == 401
    assert exc.value.category == "rejected"
    assert "secret-token" not in exc.value.detail
    assert "account-1" not in exc.value.detail
    assert "[REDACTED]" in exc.value.detail


def test_manager_connect_preserves_explicit_oanda_live_opt_in():
    client = FakeOandaClient(
        {
            ("GET", "/accounts/account-1"): json_response(
                200,
                {"account": {"id": "account-1"}},
            )
        }
    )
    broker = OANDABroker()
    broker._create_client = lambda api_token: client
    manager = BrokerManager(register_defaults=False, persist_state=False)
    manager.register_broker(broker)

    connected = run_async(
        manager.connect(
            "oanda",
            {
                "api_token": "secret-token",
                "account_id": "account-1",
                "environment": "live",
                "live_trading_enabled": True,
            },
        )
    )

    assert connected is True
    assert broker._environment == "live"