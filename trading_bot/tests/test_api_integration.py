"""API integration tests for health, signals, broker, and persistence."""

import asyncio
import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trading_bot.persistence.db import PersistenceError, get_conn, get_default_db_path, init_db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Initialize a fresh test DB for each test."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    yield db_path


class TestPersistence:
    def test_fresh_database_initializes_required_state(self, tmp_path):
        from trading_bot.persistence import repositories as repo

        db_path = tmp_path / "nested" / "fresh.db"

        init_db(db_path)
        init_db(db_path)

        assert db_path.exists()
        assert repo.get_paper_account()["balance"] == 10000.0
        assert repo.get_copy_settings()["enabled"] is False

        tables = {
            row["name"]
            for row in get_conn()
            .execute("SELECT name FROM sqlite_master WHERE type='table'")
            .fetchall()
        }
        assert {"app_settings", "paper_account", "copy_settings", "trade_ledger_entries"} <= tables

    def test_missing_database_file_is_recreated_with_defaults(self, tmp_path):
        from trading_bot.persistence import repositories as repo

        db_path = tmp_path / "restored.db"
        init_db(db_path)
        db_path.unlink()

        account = repo.get_paper_account()

        assert db_path.exists()
        assert account["balance"] == 10000.0

    def test_default_db_path_honors_environment(self, monkeypatch, tmp_path):
        expected_path = tmp_path / "env" / "state.db"

        monkeypatch.setenv("TRADING_BOT_DB_PATH", str(expected_path))

        assert get_default_db_path() == expected_path

    def test_repository_error_explains_unusable_database_path(self, tmp_path):
        invalid_path = tmp_path / "db-dir"
        invalid_path.mkdir()

        with pytest.raises(PersistenceError, match="Could not open SQLite database"):
            init_db(invalid_path)

    def test_state_restoration_rehydrates_paper_account_and_active_broker(self, tmp_path):
        from trading_bot.api.routes.paper_trading import _paper_account, restore_paper_trading_state
        from trading_bot.execution.broker_base import BaseBroker
        from trading_bot.execution.broker_manager import BrokerManager
        from trading_bot.persistence import repositories as repo

        class ConnectedBroker(BaseBroker):
            def __init__(self):
                super().__init__("connected", "Connected Broker", "test")

            async def connect(self, credentials):
                self.connected = True
                return True

            async def disconnect(self):
                self.connected = False
                return True

            async def get_balance(self):
                return None

            async def place_order(self, *args, **kwargs):
                raise NotImplementedError

            async def cancel_order(self, order_id):
                return False

            async def get_order_status(self, order_id):
                return None

            async def get_positions(self):
                return []

            async def get_orders(self, count=50, symbol=None, status=None):
                return []

            async def close_position(self, symbol, position_id=None):
                return False

        init_db(tmp_path / "state_restoration.db")
        repo.update_paper_balance(9500.0, 9600.0)
        repo.insert_paper_order({
            "trade_id": "restore001",
            "symbol": "EUR/USD",
            "side": "buy",
            "quantity": 1.0,
            "entry_price": 1.1,
            "stop_loss": 1.0,
            "take_profit_1": 1.2,
            "take_profit_2": 1.3,
            "take_profit_3": 1.4,
            "status": "filled",
            "pnl": 0.0,
            "risk_percent": 2.0,
            "trade_style": "swing",
            "confidence": 80.0,
            "opened_at": "2026-01-01T00:00:00",
        })
        repo.set_setting("broker:active", "connected")
        _paper_account["balance"] = 10000.0
        _paper_account["equity"] = 10000.0
        _paper_account["positions"] = []
        _paper_account["trades_history"] = []

        broker = ConnectedBroker()
        broker.connected = True
        manager = BrokerManager(register_defaults=False)
        manager.register_broker(broker)

        restore_paper_trading_state()
        asyncio.run(manager.restore_state())

        assert _paper_account["balance"] == 9500.0
        assert _paper_account["equity"] == 9600.0
        assert _paper_account["positions"][0]["trade_id"] == "restore001"
        assert manager.get_active_broker() is broker

    def test_paper_account_default(self):
        from trading_bot.persistence import repositories as repo
        acct = repo.get_paper_account()
        assert acct["balance"] == 10000.0
        assert acct["initial_balance"] == 10000.0

    def test_paper_order_roundtrip(self):
        from trading_bot.persistence import repositories as repo
        trade = {
            "trade_id": "test001",
            "symbol": "EUR/USD",
            "side": "buy",
            "quantity": 1.0,
            "entry_price": 1.1667,
            "stop_loss": 1.1645,
            "take_profit_1": 1.1688,
            "take_profit_2": 1.171,
            "take_profit_3": 1.1731,
            "status": "filled",
            "pnl": 0.0,
            "risk_percent": 2.0,
            "trade_style": "swing",
            "confidence": 66.0,
            "opened_at": "2026-01-01T00:00:00",
        }
        repo.insert_paper_order(trade)
        positions = repo.get_paper_positions()
        assert len(positions) == 1
        assert positions[0]["trade_id"] == "test001"

    def test_paper_reset(self):
        from trading_bot.persistence import repositories as repo
        repo.insert_paper_order({
            "trade_id": "test002", "symbol": "BTC/USD", "side": "buy",
            "quantity": 0.5, "entry_price": 70000, "stop_loss": 69000,
            "take_profit_1": 71000, "take_profit_2": 72000, "take_profit_3": 73000,
            "status": "filled", "pnl": 0.0, "risk_percent": 2.0,
            "trade_style": "swing", "confidence": 80.0,
            "opened_at": "2026-01-01T00:00:00",
        })
        repo.reset_paper_account()
        assert len(repo.get_paper_positions()) == 0
        assert repo.get_paper_account()["balance"] == 10000.0

    def test_scanner_save_load_delete(self):
        from trading_bot.persistence import repositories as repo
        sid = repo.save_scanner("TestScanner", {"conditions": [{"indicator": "RSI", "operator": ">", "value": 70}]})
        scanners = repo.get_saved_scanners()
        assert any(s["name"] == "TestScanner" for s in scanners)
        repo.delete_scanner(sid)
        assert not any(s["name"] == "TestScanner" for s in repo.get_saved_scanners())

    def test_settings_roundtrip(self):
        from trading_bot.persistence import repositories as repo
        repo.set_setting("maxPositionSize", "10")
        assert repo.get_setting("maxPositionSize") == "10"
        all_s = repo.get_all_settings()
        assert "maxPositionSize" in all_s

    def test_copy_settings_roundtrip(self):
        from trading_bot.persistence import repositories as repo
        settings = repo.get_copy_settings()
        assert settings["enabled"] is False
        repo.update_copy_settings(enabled=True, min_confidence=75)
        updated = repo.get_copy_settings()
        assert updated["enabled"] is True
        assert updated["min_confidence"] == 75

    def test_signal_prediction_roundtrip(self):
        from trading_bot.persistence import repositories as repo
        repo.insert_signal_prediction({
            "signal_id": "EUR/USD_1000",
            "symbol": "EUR/USD",
            "direction": "BUY",
            "confidence": 70,
            "entry_min": 1.166,
            "entry_max": 1.167,
            "stop_loss": 1.164,
            "take_profit1": 1.169,
            "take_profit2": 1.171,
            "take_profit3": 1.173,
            "timeframe": "1h",
            "trade_style": "swing",
            "source": "heuristic",
            "price_source": "live",
            "created_at": 1000.0,
        })
        repo.insert_signal_outcome({
            "signal_id": "EUR/USD_1000",
            "resolved_reason": "TP_HIT",
            "resolved_at": 2000.0,
            "exit_price": 1.169,
            "pnl_pips": 30.0,
            "direction_correct": 1,
        })
        metrics = repo.get_signal_metrics(symbol="EUR/USD")
        assert metrics["total"] == 1
        assert metrics["directional_accuracy"] == 100.0


class TestBrokerTruthfulness:
    def test_no_mock_positions_returned(self):
        """Broker positions endpoint should return empty list, not mock data."""
        from trading_bot.execution.broker_manager import broker_manager
        brokers = broker_manager.list_brokers()
        # None should be connected by default
        connected = [b for b in brokers if b["connected"]]
        assert len(connected) == 0, "No brokers should be connected by default"

    def test_orders_endpoint_returns_real_orders_shape(self):
        from datetime import datetime
        from fastapi.testclient import TestClient

        from trading_bot.api.server import app
        from trading_bot.execution.broker_base import BaseBroker, BrokerBalance, BrokerOrder, BrokerPosition, OrderSide, OrderStatus, OrderType
        from trading_bot.execution.broker_manager import broker_manager

        class FakeBroker(BaseBroker):
            def __init__(self):
                super().__init__("fake", "Fake Broker", "fake")
                self.connected = True
                self._environment = "paper"

            async def connect(self, credentials):
                return True

            async def disconnect(self):
                return True

            async def place_order(self, symbol, side, quantity, order_type=OrderType.MARKET, price=None):
                return BrokerOrder(order_id="new-1", symbol=symbol, side=side, order_type=order_type, quantity=quantity, broker_id=self.broker_id)

            async def cancel_order(self, order_id):
                return True

            async def get_positions(self):
                return [BrokerPosition(symbol="EUR/USD", side="long", quantity=1, entry_price=1.1, current_price=1.2, unrealized_pnl=0.1, broker_id=self.broker_id)]

            async def get_balance(self):
                return BrokerBalance(total_equity=1000, available_margin=900, used_margin=100)

            async def get_order_status(self, order_id):
                return BrokerOrder(order_id=order_id, symbol="EUR/USD", side=OrderSide.BUY, order_type=OrderType.MARKET, quantity=1, broker_id=self.broker_id)

            async def get_orders(self, count=50, symbol=None, status=None):
                orders = [
                    BrokerOrder(
                        order_id="ord-1",
                        symbol="EUR/USD",
                        side=OrderSide.BUY,
                        order_type=OrderType.MARKET,
                        quantity=1,
                        price=1.10001,
                        status=OrderStatus.FILLED,
                        filled_quantity=1,
                        avg_fill_price=1.10002,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        broker_id=self.broker_id,
                    ),
                    BrokerOrder(
                        order_id="ord-2",
                        symbol="XAU/USD",
                        side=OrderSide.SELL,
                        order_type=OrderType.LIMIT,
                        quantity=2,
                        price=3200.5,
                        status=OrderStatus.OPEN,
                        filled_quantity=0,
                        avg_fill_price=0,
                        created_at=datetime.utcnow(),
                        updated_at=datetime.utcnow(),
                        broker_id=self.broker_id,
                    ),
                ]
                if symbol:
                    orders = [order for order in orders if order.symbol == symbol]
                if status:
                    orders = [order for order in orders if order.status.value == status]
                return orders[:count]

        original_brokers = broker_manager._brokers.copy()
        original_active = broker_manager._active_broker
        broker_manager._brokers["fake"] = FakeBroker()
        broker_manager._active_broker = "fake"
        try:
            client = TestClient(app)
            response = client.get("/api/broker/orders?broker_id=fake&count=5")
            assert response.status_code == 200
            payload = response.json()
            assert len(payload) == 2
            assert payload[0]["status"] == "filled"
            assert payload[0]["order_id"] == "ord-1"
            assert payload[0]["broker_id"] == "fake"
            assert "created_at" in payload[0]
            filtered = client.get("/api/broker/orders?broker_id=fake&status=filled&symbol=EUR/USD")
            assert filtered.status_code == 200
            filtered_payload = filtered.json()
            assert len(filtered_payload) == 1
            assert filtered_payload[0]["symbol"] == "EUR/USD"

            active = client.get("/api/broker/active")
            assert active.status_code == 200
            active_payload = active.json()
            assert active_payload["id"] == "fake"
            assert active_payload["environment"] == "paper"
        finally:
            broker_manager._brokers = original_brokers
            broker_manager._active_broker = original_active

    def test_positions_endpoint_returns_individual_positions_and_close_uses_position_id(self):
        from fastapi.testclient import TestClient

        from trading_bot.api.server import app
        from trading_bot.execution.broker_base import BaseBroker, BrokerBalance, BrokerOrder, BrokerPosition, OrderSide, OrderType
        from trading_bot.execution.broker_manager import broker_manager

        class FakeBroker(BaseBroker):
            def __init__(self):
                super().__init__("fake", "Fake Broker", "fake")
                self.connected = True
                self._environment = "paper"
                self.closed_calls = []

            async def connect(self, credentials):
                return True

            async def disconnect(self):
                return True

            async def place_order(self, symbol, side, quantity, order_type=OrderType.MARKET, price=None):
                return BrokerOrder(
                    order_id="new-1",
                    symbol=symbol,
                    side=side,
                    order_type=order_type,
                    quantity=quantity,
                    broker_id=self.broker_id,
                )

            async def cancel_order(self, order_id):
                return True

            async def get_positions(self):
                return [
                    BrokerPosition(
                        symbol="EUR/USD",
                        side="long",
                        quantity=3,
                        entry_price=1.17812,
                        current_price=1.17778,
                        unrealized_pnl=-0.0010,
                        broker_id=self.broker_id,
                        position_id="101",
                        opened_at="2026-04-16T10:40:00Z",
                    ),
                    BrokerPosition(
                        symbol="EUR/USD",
                        side="long",
                        quantity=4,
                        entry_price=1.17845,
                        current_price=1.17778,
                        unrealized_pnl=-0.0019,
                        broker_id=self.broker_id,
                        position_id="102",
                        opened_at="2026-04-16T10:47:43Z",
                    ),
                ]

            async def get_balance(self):
                return BrokerBalance(total_equity=1000, available_margin=900, used_margin=100)

            async def get_order_status(self, order_id):
                return BrokerOrder(
                    order_id=order_id,
                    symbol="EUR/USD",
                    side=OrderSide.BUY,
                    order_type=OrderType.MARKET,
                    quantity=1,
                    broker_id=self.broker_id,
                )

            async def close_position(self, symbol, position_id=None):
                self.closed_calls.append({"symbol": symbol, "position_id": position_id})
                return True

        original_brokers = broker_manager._brokers.copy()
        original_active = broker_manager._active_broker
        fake_broker = FakeBroker()
        broker_manager._brokers["fake"] = fake_broker
        broker_manager._active_broker = "fake"
        try:
            client = TestClient(app)

            response = client.get("/api/broker/positions?broker_id=fake&symbol=EUR/USD")
            assert response.status_code == 200
            payload = response.json()
            assert len(payload) == 2
            assert payload[0]["symbol"] == "EUR/USD"
            assert payload[0]["position_id"] == "101"
            assert payload[0]["opened_at"] == "2026-04-16T10:40:00Z"
            assert payload[1]["position_id"] == "102"

            close_response = client.post("/api/broker/close-position/fake?symbol=EUR/USD&position_id=102")
            assert close_response.status_code == 200
            assert close_response.json()["success"] is True
            assert fake_broker.closed_calls == [{"symbol": "EUR/USD", "position_id": "102"}]
        finally:
            broker_manager._brokers = original_brokers
            broker_manager._active_broker = original_active

    def test_restore_state_clears_invalid_persisted_broker(self):
        import asyncio

        from trading_bot.execution.broker_manager import BrokerManager
        from trading_bot.persistence import repositories as repo

        repo.set_setting("broker:active", "oanda")
        repo.set_setting(
            "broker:credentials:oanda",
            json.dumps({
                "api_token": "bad",
                "account_id": "bad",
                "environment": "practice",
            }),
        )

        manager = BrokerManager()
        asyncio.run(manager.restore_state())

        assert manager.get_active_broker() is None
        assert repo.get_setting("broker:active") is None
        assert repo.get_setting("broker:credentials:oanda") is None


class TestSignalSourceLabeling:
    def test_signal_response_has_prediction_source(self):
        """Signal breakdown responses must include prediction_source field."""
        from trading_bot.api.routes.signals import _build_response, ActiveSignal, SignalStatus
        from datetime import datetime, timezone
        import time

        sig = ActiveSignal(
            symbol="EUR/USD", direction="BUY", confidence=70,
            entry_min=1.166, entry_max=1.167, entry_price=1.1665,
            stop_loss=1.164, take_profit1=1.169, take_profit2=1.171,
            take_profit3=1.173, created_at=time.time(), timeframe="1h",
            indicators=[], signal_strength=50, price_source="live",
        )
        expires = datetime.now(tz=timezone.utc)
        response = _build_response(sig, SignalStatus.VALID, expires)
        assert "prediction_source" in response
        assert response["prediction_source"] == "heuristic"
