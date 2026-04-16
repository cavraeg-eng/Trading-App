import pytest
from fastapi.testclient import TestClient

from trading_bot.api.server import app
from trading_bot.persistence import repositories as repo
from trading_bot.persistence.db import init_db


@pytest.fixture
def client(tmp_path):
    init_db(tmp_path / "copy_trading.db")
    return TestClient(app)


def seed_signal(
    signal_id: str,
    *,
    direction: str = "BUY",
    confidence: int = 80,
    symbol: str = "EUR/USD",
    timeframe: str = "1h",
    trade_style: str = "swing",
    created_at: float = 4_102_444_800.0,
):
    repo.insert_signal_prediction({
        "signal_id": signal_id,
        "symbol": symbol,
        "direction": direction,
        "confidence": confidence,
        "entry_min": 1.1000,
        "entry_max": 1.1010,
        "stop_loss": 1.0950,
        "take_profit1": 1.1050,
        "take_profit2": 1.1070,
        "take_profit3": 1.1100,
        "timeframe": timeframe,
        "trade_style": trade_style,
        "source": "heuristic",
        "price_source": "live",
        "created_at": created_at,
    })


def enable_copy_trading():
    repo.update_copy_settings(enabled=True, min_confidence=60, allowed_symbols=["EUR/USD", "XAU/USD"])


def test_copy_signal_rejects_unknown_signal(client):
    enable_copy_trading()
    response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "missing",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


def test_copy_signal_rejects_hold_signal(client):
    enable_copy_trading()
    seed_signal("hold_1", direction="HOLD")
    response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "hold_1",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert response.status_code == 400
    assert "hold" in response.json()["detail"].lower()


def test_copy_signal_rejects_expired_signal(client):
    enable_copy_trading()
    seed_signal("old_1", created_at=1.0)
    response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "old_1",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_copy_signal_rejects_low_confidence_signal(client):
    repo.update_copy_settings(enabled=True, min_confidence=85, allowed_symbols=["EUR/USD"])
    seed_signal("weak_1", confidence=70)
    response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "weak_1",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert response.status_code == 400
    assert "below minimum" in response.json()["detail"].lower()


def test_copy_signal_uses_canonical_signal_fields(client):
    enable_copy_trading()
    seed_signal("sig_1", created_at=4_102_444_800.0)
    response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_1",
        "quantity": 0.5,
        "risk_percent": 5.0,
        "entry_price": 1.1005,
    })
    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    trade = repo.get_copy_trade(payload["copy_trade_id"])
    assert trade is not None
    assert trade["signal_id"] == "sig_1"
    assert trade["direction"] == "BUY"
    assert trade["stop_loss"] == pytest.approx(1.0950)
    assert trade["initial_stop_loss"] == pytest.approx(1.0950)
    assert trade["take_profit1"] == pytest.approx(1.1050)
    assert trade["trade_style"] == "swing"
    assert trade["timeframe"] == "1h"
    assert trade["risk_percent"] == pytest.approx(3.0)
    assert trade["remaining_quantity"] == pytest.approx(0.5)


def test_positions_apply_partial_tp_and_breakeven(client, monkeypatch):
    enable_copy_trading()
    seed_signal("sig_partial")

    prices = iter([
        (1.1005, "live"),
        (1.1052, "live"),
        (1.1072, "live"),
    ])

    def fake_get_base_price(symbol: str, timeframe: str = "1h", trade_style: str = "swing"):
        return next(prices)

    monkeypatch.setattr("trading_bot.api.routes.copy_trading.get_base_price", fake_get_base_price)

    open_response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_partial",
        "quantity": 1.0,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert open_response.status_code == 200
    copy_trade_id = open_response.json()["copy_trade_id"]

    tp1_response = client.get("/api/copy-trading/positions")
    assert tp1_response.status_code == 200
    trade = repo.get_copy_trade(copy_trade_id)
    assert trade is not None
    assert trade["tp1_hit"] == 1
    assert trade["status"] == "partial_tp1"
    assert trade["remaining_quantity"] == pytest.approx(0.5)
    assert trade["stop_moved_to_breakeven"] == 1
    assert trade["stop_loss"] == pytest.approx(trade["entry_price"])

    tp2_response = client.get("/api/copy-trading/positions")
    assert tp2_response.status_code == 200
    trade = repo.get_copy_trade(copy_trade_id)
    assert trade is not None
    assert trade["tp2_hit"] == 1
    assert trade["status"] == "partial_tp2"
    assert trade["remaining_quantity"] == pytest.approx(0.2)
    assert trade["trailing_stop_active"] == 1
    assert trade["stop_loss"] >= trade["take_profit1"]


def test_manual_close_allows_partial_copy_positions(client, monkeypatch):
    enable_copy_trading()
    seed_signal("sig_partial_close")

    prices = iter([
        (1.1005, "live"),
        (1.1052, "live"),
        (1.1068, "live"),
    ])

    def fake_get_base_price(symbol: str, timeframe: str = "1h", trade_style: str = "swing"):
        return next(prices)

    monkeypatch.setattr("trading_bot.api.routes.copy_trading.get_base_price", fake_get_base_price)

    open_response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_partial_close",
        "quantity": 1.0,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert open_response.status_code == 200
    copy_trade_id = open_response.json()["copy_trade_id"]

    partial_response = client.get("/api/copy-trading/positions")
    assert partial_response.status_code == 200

    close_response = client.post(f"/api/copy-trading/close/{copy_trade_id}")
    assert close_response.status_code == 200
    trade = repo.get_copy_trade(copy_trade_id)
    assert trade is not None
    assert trade["status"] == "closed_manual"
    assert trade["remaining_quantity"] == pytest.approx(0.0)


def test_positions_close_on_tp3_after_partial_progress(client, monkeypatch):
    enable_copy_trading()
    seed_signal("sig_tp3")

    prices = iter([
        (1.1005, "live"),
        (1.1052, "live"),
        (1.1072, "live"),
        (1.1105, "live"),
    ])

    def fake_get_base_price(symbol: str, timeframe: str = "1h", trade_style: str = "swing"):
        return next(prices)

    monkeypatch.setattr("trading_bot.api.routes.copy_trading.get_base_price", fake_get_base_price)

    open_response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_tp3",
        "quantity": 1.0,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert open_response.status_code == 200
    copy_trade_id = open_response.json()["copy_trade_id"]

    client.get("/api/copy-trading/positions")
    client.get("/api/copy-trading/positions")
    tp3_response = client.get("/api/copy-trading/positions")
    assert tp3_response.status_code == 200

    trade = repo.get_copy_trade(copy_trade_id)
    assert trade is not None
    assert trade["status"] == "closed_tp3"
    assert trade["tp3_hit"] == 1
    assert trade["remaining_quantity"] == pytest.approx(0.0)
    assert trade["closed_at"] is not None


def test_copy_signal_rejects_duplicate_open_signal(client):
    enable_copy_trading()
    seed_signal("sig_dup", created_at=4_102_444_800.0)
    first = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_dup",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert first.status_code == 200
    second = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_dup",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 1.1005,
    })
    assert second.status_code == 409
    assert "already exists" in second.json()["detail"].lower()


def test_positions_and_close_use_trade_timeframe_and_style(client, monkeypatch):
    enable_copy_trading()
    repo.insert_signal_prediction({
        "signal_id": "sig_scalp",
        "symbol": "XAU/USD",
        "direction": "BUY",
        "confidence": 80,
        "entry_min": 4799.0,
        "entry_max": 4801.0,
        "stop_loss": 4790.0,
        "take_profit1": 4810.0,
        "take_profit2": 4820.0,
        "take_profit3": 4830.0,
        "timeframe": "5m",
        "trade_style": "scalp",
        "source": "heuristic",
        "price_source": "live",
        "created_at": 4_102_444_800.0,
    })

    calls: list[tuple[str, str, str]] = []

    def fake_get_base_price(symbol: str, timeframe: str = "1h", trade_style: str = "swing"):
        calls.append((symbol, timeframe, trade_style))
        return 4801.0, "live"

    monkeypatch.setattr("trading_bot.api.routes.copy_trading.get_base_price", fake_get_base_price)

    open_response = client.post("/api/copy-trading/copy-signal", json={
        "signal_id": "sig_scalp",
        "quantity": 0.5,
        "risk_percent": 1.0,
        "entry_price": 4800.0,
    })
    assert open_response.status_code == 200
    copy_trade_id = open_response.json()["copy_trade_id"]

    positions_response = client.get("/api/copy-trading/positions")
    assert positions_response.status_code == 200
    close_response = client.post(f"/api/copy-trading/close/{copy_trade_id}")
    assert close_response.status_code == 200
    assert ("XAU/USD", "5m", "scalp") in calls


def test_history_filters_and_export_csv(client):
    enable_copy_trading()
    seed_signal("sig_hist_1", created_at=1500.0)
    seed_signal("sig_hist_2", symbol="XAU/USD", direction="SELL", created_at=3200.0)
    repo.insert_copy_trade({
        "copy_trade_id": "ct_hist_1",
        "signal_id": "sig_hist_1",
        "symbol": "EUR/USD",
        "direction": "BUY",
        "quantity": 1.0,
        "remaining_quantity": 0.0,
        "entry_price": 1.1000,
        "current_price": 1.1100,
        "initial_stop_loss": 1.0950,
        "stop_loss": 1.1000,
        "take_profit1": 1.1050,
        "take_profit2": 1.1070,
        "take_profit3": 1.1100,
        "confidence": 80,
        "risk_percent": 1.0,
        "status": "closed_tp3",
        "unrealized_pnl": 0.0,
        "realized_pnl": 0.10,
        "realized_pnl_tp1": 0.03,
        "realized_pnl_tp2": 0.02,
        "partial_exit_count": 2,
        "tp1_hit": 1,
        "tp2_hit": 1,
        "tp3_hit": 1,
        "stop_moved_to_breakeven": 1,
        "trailing_stop_active": 1,
        "max_favorable_price": 1.1100,
        "max_adverse_price": 1.0990,
        "trade_style": "swing",
        "timeframe": "1h",
        "signal_source": "AI",
        "created_at": 1000.0,
        "closed_at": 2000.0,
    })
    repo.insert_copy_trade({
        "copy_trade_id": "ct_hist_2",
        "signal_id": "sig_hist_2",
        "symbol": "XAU/USD",
        "direction": "SELL",
        "quantity": 1.0,
        "remaining_quantity": 0.0,
        "entry_price": 4800.0,
        "current_price": 4810.0,
        "initial_stop_loss": 4815.0,
        "stop_loss": 4810.0,
        "take_profit1": 4790.0,
        "take_profit2": 4780.0,
        "take_profit3": 4770.0,
        "confidence": 78,
        "risk_percent": 1.0,
        "status": "closed_manual",
        "unrealized_pnl": 0.0,
        "realized_pnl": -10.0,
        "realized_pnl_tp1": 0.0,
        "realized_pnl_tp2": 0.0,
        "partial_exit_count": 0,
        "tp1_hit": 0,
        "tp2_hit": 0,
        "tp3_hit": 0,
        "stop_moved_to_breakeven": 0,
        "trailing_stop_active": 0,
        "max_favorable_price": 4795.0,
        "max_adverse_price": 4810.0,
        "trade_style": "scalp",
        "timeframe": "5m",
        "signal_source": "AI",
        "created_at": 3000.0,
        "closed_at": 3600.0,
    })

    history_response = client.get("/api/copy-trading/history?symbol=EUR/USD&status=closed_tp3&direction=BUY&from_ts=1500")
    assert history_response.status_code == 200
    assert history_response.json()["count"] == 1
    assert history_response.json()["history"][0]["copy_trade_id"] == "ct_hist_1"

    export_response = client.get("/api/copy-trading/history/export?status=closed_manual&direction=SELL")
    assert export_response.status_code == 200
    assert export_response.headers["content-type"].startswith("text/csv")
    body = export_response.text
    assert "ct_hist_2" in body
    assert "ct_hist_1" not in body


def test_history_pagination_and_sorting(client):
    enable_copy_trading()
    seed_signal("sig_page_1", created_at=1000.0)
    seed_signal("sig_page_2", created_at=2000.0)
    repo.insert_copy_trade({
        "copy_trade_id": "ct_page_1",
        "signal_id": "sig_page_1",
        "symbol": "EUR/USD",
        "direction": "BUY",
        "quantity": 1.0,
        "remaining_quantity": 0.0,
        "entry_price": 1.1000,
        "current_price": 1.1030,
        "initial_stop_loss": 1.0950,
        "stop_loss": 1.1000,
        "take_profit1": 1.1050,
        "take_profit2": 1.1070,
        "take_profit3": 1.1100,
        "confidence": 81,
        "risk_percent": 1.0,
        "status": "closed_tp3",
        "unrealized_pnl": 0.0,
        "realized_pnl": 3.0,
        "realized_pnl_tp1": 1.0,
        "realized_pnl_tp2": 1.0,
        "partial_exit_count": 2,
        "tp1_hit": 1,
        "tp2_hit": 1,
        "tp3_hit": 1,
        "stop_moved_to_breakeven": 1,
        "trailing_stop_active": 1,
        "max_favorable_price": 1.1030,
        "max_adverse_price": 1.0995,
        "trade_style": "swing",
        "timeframe": "1h",
        "signal_source": "AI",
        "created_at": 1000.0,
        "closed_at": 2000.0,
    })
    repo.insert_copy_trade({
        "copy_trade_id": "ct_page_2",
        "signal_id": "sig_page_2",
        "symbol": "EUR/USD",
        "direction": "BUY",
        "quantity": 1.0,
        "remaining_quantity": 0.0,
        "entry_price": 1.1000,
        "current_price": 1.1010,
        "initial_stop_loss": 1.0950,
        "stop_loss": 1.1000,
        "take_profit1": 1.1050,
        "take_profit2": 1.1070,
        "take_profit3": 1.1100,
        "confidence": 75,
        "risk_percent": 1.0,
        "status": "closed_manual",
        "unrealized_pnl": 0.0,
        "realized_pnl": 1.0,
        "realized_pnl_tp1": 0.0,
        "realized_pnl_tp2": 0.0,
        "partial_exit_count": 0,
        "tp1_hit": 0,
        "tp2_hit": 0,
        "tp3_hit": 0,
        "stop_moved_to_breakeven": 0,
        "trailing_stop_active": 0,
        "max_favorable_price": 1.1010,
        "max_adverse_price": 1.0990,
        "trade_style": "swing",
        "timeframe": "1h",
        "signal_source": "AI",
        "created_at": 1500.0,
        "closed_at": 3000.0,
    })

    response = client.get("/api/copy-trading/history?limit=1&offset=0&sort_by=realized_pnl&sort_dir=asc")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] >= 2
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["count"] == 1
    assert payload["history"][0]["copy_trade_id"] == "ct_page_2"