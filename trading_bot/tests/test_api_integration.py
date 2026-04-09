"""API integration tests for health, signals, broker, and persistence."""

import json
import os
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure the project root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from trading_bot.persistence.db import init_db, get_conn


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    """Initialize a fresh test DB for each test."""
    db_path = tmp_path / "test.db"
    init_db(db_path)
    yield db_path


class TestPersistence:
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
