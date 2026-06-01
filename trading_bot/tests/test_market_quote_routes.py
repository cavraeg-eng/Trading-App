from datetime import UTC, datetime

import pandas as pd
import pytest

from trading_bot.api.routes import market
from trading_bot.execution.broker_base import BrokerQuote


class FakeBroker:
    async def get_quote(self, symbol: str) -> BrokerQuote:
        return BrokerQuote(
            symbol=symbol,
            bid=1.1,
            ask=1.2,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            broker_id="oanda",
        )


class FakeBrokerManager:
    def __init__(self, *, connected: bool = True, quotes: bool = True):
        self.connected = connected
        self.quotes = quotes
        self.broker = FakeBroker()

    def get_active_broker_info(self) -> dict:
        return {
            "id": "oanda",
            "name": "OANDA",
            "connected": self.connected,
            "environment": "practice",
            "capabilities": {"quotes": self.quotes},
        }

    def get_broker(self, broker_id: str) -> FakeBroker:
        return self.broker


@pytest.mark.asyncio
async def test_market_quote_prefers_connected_broker_quote(monkeypatch):
    monkeypatch.setattr(market, "broker_manager", FakeBrokerManager())

    def fail_ohlcv(*args, **kwargs):
        raise AssertionError("OHLCV fallback should not be used when broker quote is available")

    monkeypatch.setattr(market, "get_shared_ohlcv_with_metadata", fail_ohlcv)

    response = await market.get_market_quote("EUR/USD", timeframe="1m")

    assert response["currentPrice"] == 1.15
    assert response["priceSource"] == "broker_quote"
    assert response["sourceMetadata"]["brokerId"] == "oanda"
    assert response["sourceMetadata"]["environment"] == "practice"


@pytest.mark.asyncio
async def test_market_quote_falls_back_to_ohlcv_without_connected_quote(monkeypatch):
    monkeypatch.setattr(market, "broker_manager", FakeBrokerManager(connected=False))
    candles = pd.DataFrame({"close": [1.08, 1.09]})
    metadata = {"priceSource": "futures", "sourceName": "yfinance"}
    monkeypatch.setattr(
        market,
        "get_shared_ohlcv_with_metadata",
        lambda *args, **kwargs: (candles, metadata),
    )

    response = await market.get_market_quote("EUR/USD", timeframe="1m")

    assert response["currentPrice"] == 1.09
    assert response["priceSource"] == "futures"
    assert response["sourceMetadata"] == metadata
