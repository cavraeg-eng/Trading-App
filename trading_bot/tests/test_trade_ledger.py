import sqlite3

from fastapi.testclient import TestClient

from trading_bot.api.server import app
from trading_bot.execution.broker_base import BrokerOrder, BrokerPosition, OrderSide, OrderStatus, OrderType
from trading_bot.execution import trade_ledger
from trading_bot.persistence import repositories as repo
from trading_bot.persistence.db import init_db


def test_trade_ledger_reconciles_position_and_order(tmp_path):
    init_db(tmp_path / "ledger.db")

    trade_ledger.reconcile_positions("oanda", [
        BrokerPosition(
            symbol="XAU/USD",
            side="long",
            quantity=1.0,
            entry_price=4700.0,
            current_price=4710.0,
            unrealized_pnl=10.0,
            broker_id="oanda",
            position_id="123",
            opened_at="2026-04-26T21:00:00Z",
        )
    ])
    trade_ledger.reconcile_orders("oanda", [
        BrokerOrder(
            order_id="trade:123",
            symbol="XAU/USD",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=1.0,
            price=4700.0,
            status=OrderStatus.OPEN,
            filled_quantity=1.0,
            avg_fill_price=4700.0,
            stop_loss=4680.0,
            take_profit_1=4740.0,
            broker_id="oanda",
        )
    ])

    entries = repo.get_trade_ledger_entries(broker_id="oanda", symbol="XAU/USD")

    assert len(entries) == 2
    trade_entry = next(entry for entry in entries if entry["source_type"] == "trade")
    position_entry = next(entry for entry in entries if entry["source_type"] == "position")
    assert trade_entry["source_id"] == "123"
    assert trade_entry["stop_loss"] == 4680.0
    assert trade_entry["take_profit_1"] == 4740.0
    assert trade_entry["r_multiple"] == 0.0
    assert position_entry["unrealized_pnl"] == 10.0
    assert position_entry["mfe"] == 10.0


def test_trade_ledger_endpoint_returns_summary(tmp_path):
    init_db(tmp_path / "ledger_endpoint.db")
    repo.upsert_trade_ledger_entry({
        "broker_id": "oanda",
        "source_type": "position",
        "source_id": "xau-long",
        "symbol": "XAU/USD",
        "side": "long",
        "status": "open",
        "quantity": 1.0,
        "entry_price": 4700.0,
        "current_price": 4710.0,
        "unrealized_pnl": 10.0,
    })

    client = TestClient(app)
    response = client.get("/api/broker/ledger?broker_id=oanda")

    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["total_entries"] == 1
    assert payload["summary"]["open_entries"] == 1
    assert payload["summary"]["unrealized_pnl"] == 10.0
    assert payload["entries"][0]["symbol"] == "XAU/USD"


def test_trade_ledger_csv_export(tmp_path):
    init_db(tmp_path / "ledger_export.db")
    repo.upsert_trade_ledger_entry({
        "broker_id": "oanda",
        "source_type": "position",
        "source_id": "xau-long",
        "signal_id": "signal-1",
        "symbol": "XAU/USD",
        "side": "long",
        "status": "open",
        "quantity": 1.0,
        "entry_price": 4700.0,
        "current_price": 4710.0,
        "unrealized_pnl": 10.0,
    })

    client = TestClient(app)
    response = client.get("/api/broker/ledger/export?broker_id=oanda")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    body = response.text
    assert "signal_id" in body
    assert "signal-1" in body


def test_trade_ledger_csv_export_filters_side_and_outcome(tmp_path):
    init_db(tmp_path / "ledger_export_filters.db")
    repo.upsert_trade_ledger_entry({
        "broker_id": "oanda",
        "source_type": "trade",
        "source_id": "win-long",
        "symbol": "XAU/USD",
        "side": "long",
        "status": "closed",
        "outcome": "WIN",
        "quantity": 1.0,
        "realized_pnl": 20.0,
    })
    repo.upsert_trade_ledger_entry({
        "broker_id": "oanda",
        "source_type": "trade",
        "source_id": "loss-short",
        "symbol": "XAU/USD",
        "side": "short",
        "status": "closed",
        "outcome": "LOSS",
        "quantity": 1.0,
        "realized_pnl": -10.0,
    })

    client = TestClient(app)
    response = client.get("/api/broker/ledger/export?broker_id=oanda&side=short&outcome=LOSS")

    assert response.status_code == 200
    body = response.text
    assert "loss-short" in body
    assert "win-long" not in body


def test_trade_ledger_metrics_include_outcomes(tmp_path):
    init_db(tmp_path / "ledger_metrics.db")
    trade_ledger.reconcile_history("oanda", [{
        "trade_id": "closed-win",
        "symbol": "XAU/USD",
        "side": "buy",
        "quantity": 1.0,
        "entry_price": 4700.0,
        "exit_price": 4740.0,
        "stop_loss": 4680.0,
        "take_profit_1": 4740.0,
        "realized_pnl": 40.0,
        "opened_at": "2026-04-26T21:00:00Z",
        "closed_at": "2026-04-26T22:00:00Z",
        "state": "closed",
    }])

    metrics = repo.get_trade_ledger_metrics(broker_id="oanda")

    assert metrics["closed_entries"] == 1
    assert metrics["win_rate"] == 100.0
    assert metrics["avg_r_multiple"] == 2.0
    assert metrics["by_symbol"][0]["symbol"] == "XAU/USD"


def test_trade_ledger_migrates_legacy_table_for_idempotent_upsert(tmp_path):
    db_path = tmp_path / "legacy_ledger.db"
    conn = sqlite3.connect(db_path)
    conn.execute(
        """CREATE TABLE trade_ledger_entries (
            ledger_id TEXT PRIMARY KEY,
            broker_id TEXT NOT NULL,
            source_type TEXT NOT NULL,
            source_id TEXT NOT NULL,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,
            status TEXT NOT NULL,
            quantity REAL NOT NULL DEFAULT 0.0,
            remaining_quantity REAL,
            entry_price REAL,
            current_price REAL,
            exit_price REAL,
            stop_loss REAL,
            take_profit_1 REAL,
            take_profit_2 REAL,
            take_profit_3 REAL,
            unrealized_pnl REAL NOT NULL DEFAULT 0.0,
            realized_pnl REAL NOT NULL DEFAULT 0.0,
            opened_at TEXT,
            closed_at TEXT,
            updated_at TEXT NOT NULL DEFAULT (datetime('now')),
            metadata_json TEXT
        )"""
    )
    conn.execute(
        """INSERT INTO trade_ledger_entries
        (ledger_id, broker_id, source_type, source_id, symbol, side, status, quantity)
        VALUES ('old-1', 'oanda', 'order', '123', 'XAU/USD', 'buy', 'pending', 1.0)"""
    )
    conn.commit()
    conn.close()

    init_db(db_path)
    ledger_id = repo.upsert_trade_ledger_entry({
        "broker_id": "oanda",
        "source_type": "order",
        "source_id": "123",
        "signal_id": "signal-legacy",
        "symbol": "XAU/USD",
        "side": "buy",
        "status": "filled",
        "quantity": 1.0,
        "entry_price": 4700.0,
        "r_multiple": 1.5,
    })

    entries = repo.get_trade_ledger_entries(broker_id="oanda", symbol="XAU/USD")

    assert ledger_id == "old-1"
    assert len(entries) == 1
    assert entries[0]["status"] == "filled"
    assert entries[0]["signal_id"] == "signal-legacy"
    assert entries[0]["r_multiple"] == 1.5