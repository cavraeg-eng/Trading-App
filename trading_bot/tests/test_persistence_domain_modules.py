"""Representative coverage for domain-specific persistence modules."""

from trading_bot.persistence import (
    alerts,
    automation,
    copy_trading,
    paper_trading,
    scanners,
    settings,
    signals,
    trade_ledger,
)
from trading_bot.persistence.db import init_db


def test_settings_repository_roundtrip(tmp_path):
    init_db(tmp_path / "settings.db")

    settings.set_setting("active_strategy_id", "apex")

    assert settings.get_setting("active_strategy_id") == "apex"
    assert settings.get_all_settings()["active_strategy_id"] == "apex"

    settings.delete_setting("active_strategy_id")

    assert settings.get_setting("active_strategy_id") is None


def test_scanner_repository_roundtrip(tmp_path):
    init_db(tmp_path / "scanner.db")

    scanner_id = scanners.save_scanner("Momentum", {"conditions": [{"indicator": "RSI"}]})

    assert scanners.update_scanner(scanner_id, "Momentum v2", {"conditions": []}) is True
    assert scanners.get_saved_scanners()[0]["name"] == "Momentum v2"
    assert scanners.delete_scanner(scanner_id) is True


def test_paper_trading_repository_roundtrip(tmp_path):
    init_db(tmp_path / "paper.db")

    paper_trading.update_paper_balance(9500.0, 9600.0)
    paper_trading.insert_paper_order(
        {
            "trade_id": "paper-1",
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
            "risk_percent": 1.0,
            "trade_style": "swing",
            "opened_at": "2026-01-01T00:00:00",
        }
    )

    assert paper_trading.get_paper_account()["balance"] == 9500.0
    assert paper_trading.get_paper_positions()[0]["trade_id"] == "paper-1"

    paper_trading.reset_paper_account()

    assert paper_trading.get_paper_positions() == []


def test_copy_trading_repository_roundtrip(tmp_path):
    init_db(tmp_path / "copy.db")

    copy_trading.update_copy_settings(enabled=True, allowed_symbols=["EUR/USD"])
    signals.insert_signal_prediction(
        {
            "signal_id": "signal-1",
            "symbol": "EUR/USD",
            "direction": "BUY",
            "confidence": 80,
            "entry_min": 1.1,
            "entry_max": 1.2,
            "stop_loss": 1.0,
            "take_profit1": 1.3,
            "take_profit2": 1.4,
            "take_profit3": 1.5,
            "timeframe": "1h",
            "trade_style": "swing",
            "source": "test",
            "price_source": "unit",
            "created_at": 1000.0,
        }
    )
    copy_trading.insert_copy_trade(
        {
            "copy_trade_id": "copy-1",
            "signal_id": "signal-1",
            "symbol": "EUR/USD",
            "direction": "BUY",
            "quantity": 1.0,
            "remaining_quantity": 1.0,
            "entry_price": 1.1,
            "current_price": 1.1,
            "initial_stop_loss": 1.0,
            "stop_loss": 1.0,
            "take_profit1": 1.2,
            "take_profit2": 1.3,
            "take_profit3": 1.4,
            "confidence": 80.0,
            "risk_percent": 1.0,
            "status": "open",
            "unrealized_pnl": 0.0,
            "realized_pnl": 0.0,
            "realized_pnl_tp1": 0.0,
            "realized_pnl_tp2": 0.0,
            "partial_exit_count": 0,
            "tp1_hit": 0,
            "tp2_hit": 0,
            "tp3_hit": 0,
            "stop_moved_to_breakeven": 0,
            "trailing_stop_active": 0,
            "max_favorable_price": 1.1,
            "max_adverse_price": 1.1,
            "trade_style": "swing",
            "timeframe": "1h",
            "signal_source": "test",
            "created_at": 1000.0,
            "closed_at": None,
        }
    )

    assert copy_trading.get_copy_settings()["enabled"] is True
    assert copy_trading.get_open_copy_trade_for_signal("signal-1")["copy_trade_id"] == "copy-1"

    copy_trading.update_copy_trade("copy-1", status="closed", closed_at=1100.0)

    assert copy_trading.count_copy_history(status="closed") == 1


def test_signal_repository_metrics(tmp_path):
    init_db(tmp_path / "signals.db")

    signals.insert_signal_prediction(
        {
            "signal_id": "signal-1",
            "symbol": "EUR/USD",
            "direction": "BUY",
            "confidence": 70,
            "entry_min": 1.1,
            "entry_max": 1.2,
            "stop_loss": 1.0,
            "take_profit1": 1.3,
            "take_profit2": 1.4,
            "take_profit3": 1.5,
            "timeframe": "1h",
            "trade_style": "swing",
            "source": "test",
            "price_source": "unit",
            "created_at": 1000.0,
        }
    )
    signals.insert_signal_outcome(
        {
            "signal_id": "signal-1",
            "resolved_reason": "TP_HIT",
            "resolved_at": 1100.0,
            "exit_price": 1.3,
            "pnl_pips": 20.0,
            "direction_correct": 1,
        }
    )

    assert signals.get_signal_prediction("signal-1")["symbol"] == "EUR/USD"
    assert signals.get_signal_metrics(symbol="EUR/USD")["directional_accuracy"] == 100.0


def test_alert_repository_roundtrip(tmp_path):
    init_db(tmp_path / "alerts.db")

    alert_id = alerts.create_alert(
        "EUR/USD", "STRONG_SIGNAL", "Signal", "Buy", data='{"score": 80}'
    )

    assert alerts.get_recent_alert("EUR/USD", "STRONG_SIGNAL")["id"] == alert_id
    assert alerts.get_unread_count() == 1
    assert alerts.mark_read(alert_id) is True
    assert alerts.get_alerts()[0]["data"]["score"] == 80


def test_automation_repository_records_execution(tmp_path):
    init_db(tmp_path / "automation.db")

    automation.insert_automation_execution("strategy-1", "EUR/USD", "execute", "success")

    assert automation.get_automation_executions(strategy_id="strategy-1")[0]["symbol"] == "EUR/USD"
    assert automation.count_recent_automation_executions("strategy-1", 3600) == 1


def test_trade_ledger_repository_metrics(tmp_path):
    init_db(tmp_path / "ledger.db")

    ledger_id = trade_ledger.upsert_trade_ledger_entry(
        {
            "broker_id": "oanda",
            "source_type": "trade",
            "source_id": "trade-1",
            "symbol": "XAU/USD",
            "side": "buy",
            "status": "closed",
            "quantity": 1.0,
            "realized_pnl": 20.0,
            "closed_at": "2026-01-01T01:00:00Z",
        }
    )

    assert trade_ledger.get_trade_ledger_entries(broker_id="oanda")[0]["ledger_id"] == ledger_id
    assert trade_ledger.get_trade_ledger_metrics(broker_id="oanda")["closed_entries"] == 1
