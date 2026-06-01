from datetime import UTC, datetime

import pandas as pd
import pytest

from trading_bot.api.routes import market
from trading_bot.execution.broker_base import BrokerCandle, BrokerQuote


class FakeBroker:
    async def get_quote(self, symbol: str) -> BrokerQuote:
        return BrokerQuote(
            symbol=symbol,
            bid=1.1,
            ask=1.2,
            timestamp=datetime(2026, 1, 1, tzinfo=UTC),
            broker_id="oanda",
        )

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        count: int = 200,
    ) -> list[BrokerCandle]:
        return [
            BrokerCandle(
                symbol=symbol,
                time=datetime(2026, 1, 1, 0, minute, tzinfo=UTC),
                open=1.10 + minute / 1000,
                high=1.11 + minute / 1000,
                low=1.09 + minute / 1000,
                close=1.105 + minute / 1000,
                volume=100 + minute,
                broker_id="oanda",
            )
            for minute in range(5)
        ]


class FakeBrokerManager:
    def __init__(self, *, connected: bool = True, quotes: bool = True, candles: bool = True):
        self.connected = connected
        self.quotes = quotes
        self.candles = candles
        self.broker = FakeBroker()

    def get_active_broker_info(self) -> dict:
        return {
            "id": "oanda",
            "name": "OANDA",
            "connected": self.connected,
            "environment": "practice",
            "capabilities": {"quotes": self.quotes, "candles": self.candles},
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


@pytest.mark.asyncio
async def test_market_candles_prefers_connected_broker_candles(monkeypatch):
    monkeypatch.setattr(market, "broker_manager", FakeBrokerManager())

    def fail_ohlcv(*args, **kwargs):
        raise AssertionError("OHLCV fallback should not be used when broker candles are available")

    monkeypatch.setattr(market, "get_shared_ohlcv_with_metadata", fail_ohlcv)

    response = await market.get_candles("EUR/USD", timeframe="1m", limit=5)

    assert len(response["candles"]) == 5
    assert response["candles"][-1].close == 1.109
    assert response["sourceMetadata"]["priceSource"] == "broker_candles"
    assert response["sourceMetadata"]["brokerId"] == "oanda"


@pytest.mark.asyncio
async def test_market_candles_falls_back_to_ohlcv_without_connected_broker(monkeypatch):
    monkeypatch.setattr(market, "broker_manager", FakeBrokerManager(connected=False))
    candles = pd.DataFrame(
        {
            "open": [1.08, 1.081, 1.082, 1.083, 1.084],
            "high": [1.09, 1.091, 1.092, 1.093, 1.094],
            "low": [1.07, 1.071, 1.072, 1.073, 1.074],
            "close": [1.085, 1.086, 1.087, 1.088, 1.089],
            "volume": [100, 101, 102, 103, 104],
        },
        index=pd.date_range("2026-01-01", periods=5, freq="min", tz=UTC),
    )
    metadata = {"priceSource": "futures", "sourceName": "yfinance"}
    monkeypatch.setattr(
        market,
        "get_shared_ohlcv_with_metadata",
        lambda *args, **kwargs: (candles, metadata),
    )

    response = await market.get_candles("EUR/USD", timeframe="1m", limit=5)

    assert len(response["candles"]) == 5
    assert response["sourceMetadata"] == metadata
