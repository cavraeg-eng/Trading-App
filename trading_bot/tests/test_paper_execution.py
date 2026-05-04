"""Tests for application-facing paper execution behavior."""

import asyncio

import pytest

from trading_bot.execution.paper import (
    PaperExecutionPersistenceError,
    PaperExecutionService,
    PaperOrderCommand,
    PaperOrderValidationError,
)
from trading_bot.persistence import repositories as repo
from trading_bot.persistence.db import PersistenceError, init_db


@pytest.fixture(autouse=True)
def setup_test_db(tmp_path):
    init_db(tmp_path / "paper_execution.db")


def _fresh_account() -> dict:
    return {
        "balance": 10000.0,
        "equity": 10000.0,
        "positions": [],
        "trades_history": [],
        "initial_balance": 10000.0,
    }


def _service() -> PaperExecutionService:
    return PaperExecutionService(account_state=_fresh_account(), account_lock=asyncio.Lock())


def _order(**overrides) -> PaperOrderCommand:
    values = {
        "symbol": "EUR/USD",
        "side": "buy",
        "quantity": 1.234,
        "price": 1.1667,
        "stop_loss": 1.16,
        "take_profit_1": 1.17,
        "take_profit_2": 1.18,
        "take_profit_3": 1.19,
        "risk_percent": 2.0,
        "trade_style": "swing",
        "confidence": 70.0,
        "strategy_id": "strategy-1",
    }
    values.update(overrides)
    return PaperOrderCommand(**values)


def test_place_order_creates_position_history_and_persisted_order():
    async def run_order():
        service = _service()
        response = await service.place_order(_order())
        return response, service.get_account_summary()

    response, account_summary = asyncio.run(run_order())
    persisted = repo.get_paper_positions()
    assert response["success"] is True
    assert response["status"] == "filled"
    assert response["symbol"] == "EUR/USD"
    assert response["quantity"] == 1.23
    assert response["take_profit_levels"] == [1.17, 1.18, 1.19]
    assert persisted[0]["trade_id"] == response["order_id"]
    assert persisted[0]["strategy_id"] == "strategy-1"
    assert account_summary["total_trades"] == 1


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"side": "hold"}, "Side must be 'buy' or 'sell'"),
        ({"quantity": 0}, "Quantity must be positive"),
        ({"price": None}, "Market orders must include a valid current price"),
        ({"price": 0}, "Market orders must include a valid current price"),
    ],
)
def test_place_order_rejects_invalid_side_quantity_and_price(overrides, message):
    async def run_order():
        service = _service()
        with pytest.raises(PaperOrderValidationError, match=message):
            await service.place_order(_order(**overrides))
        return service.get_positions()

    assert asyncio.run(run_order()) == []
    assert repo.get_paper_positions() == []


def test_place_order_rolls_back_in_memory_state_when_persistence_fails(monkeypatch):
    def fail_insert(_trade):
        raise PersistenceError("database unavailable")

    monkeypatch.setattr(repo, "insert_paper_order", fail_insert)

    async def run_order():
        service = _service()
        with pytest.raises(PaperExecutionPersistenceError, match="database unavailable"):
            await service.place_order(_order())
        return service.get_positions(), service.get_account_summary()

    positions, account_summary = asyncio.run(run_order())
    assert positions == []
    assert account_summary["total_trades"] == 0


def test_restore_state_rehydrates_account_positions_and_history():
    repo.update_paper_balance(9500.0, 9600.0)
    repo.insert_paper_order(
        {
            "trade_id": "restore001",
            "symbol": "BTC/USD",
            "side": "sell",
            "quantity": 0.5,
            "entry_price": 70000.0,
            "stop_loss": 71000.0,
            "take_profit_1": 69000.0,
            "take_profit_2": 68000.0,
            "take_profit_3": 67000.0,
            "status": "filled",
            "pnl": 0.0,
            "risk_percent": 2.0,
            "trade_style": "swing",
            "confidence": 80.0,
            "opened_at": "2026-01-01T00:00:00",
        }
    )
    account = _fresh_account()
    service = PaperExecutionService(account_state=account)

    service.restore_state()

    assert account["balance"] == 9500.0
    assert account["equity"] == 9600.0
    assert account["positions"][0]["trade_id"] == "restore001"
    assert account["trades_history"][0]["trade_id"] == "restore001"


def test_reset_clears_persisted_and_in_memory_paper_state():
    account = _fresh_account()

    async def run_order():
        service = PaperExecutionService(account_state=account, account_lock=asyncio.Lock())
        await service.place_order(_order(symbol="BTC/USD", price=70000.0, quantity=0.5))
        service.reset()

    asyncio.run(run_order())

    assert repo.get_paper_positions() == []
    assert account["positions"] == []
    assert account["trades_history"] == []
    assert repo.get_paper_account()["balance"] == 10000.0
