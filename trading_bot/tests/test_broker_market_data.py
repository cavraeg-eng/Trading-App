from datetime import UTC, datetime, timedelta

import pytest

from trading_bot.execution.broker_base import BrokerCandle
from trading_bot.services.broker_market_data import (
    active_broker_ohlcv,
    broker_candles_to_dataframe,
)


def _candles(count: int = 35) -> list[BrokerCandle]:
    start = datetime.now(UTC) - timedelta(minutes=count)
    return [
        BrokerCandle(
            symbol="EUR/USD",
            time=start + timedelta(minutes=index),
            open=1.1000 + index / 10_000,
            high=1.1010 + index / 10_000,
            low=1.0990 + index / 10_000,
            close=1.1005 + index / 10_000,
            volume=100 + index,
            broker_id="oanda",
        )
        for index in range(count)
    ]


class FakeBroker:
    def __init__(self, candles: list[BrokerCandle]):
        self.candles = candles
        self.calls: list[dict[str, object]] = []

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        count: int = 200,
    ) -> list[BrokerCandle]:
        self.calls.append({"symbol": symbol, "timeframe": timeframe, "count": count})
        return self.candles


class FakeBrokerManager:
    def __init__(self, *, connected: bool = True, candles: bool = True):
        self.broker = FakeBroker(_candles())
        self.connected = connected
        self.candles = candles

    def get_active_broker_info(self) -> dict:
        return {
            "id": "oanda",
            "name": "OANDA",
            "connected": self.connected,
            "environment": "practice",
            "capabilities": {"candles": self.candles},
        }

    def get_broker(self, broker_id: str) -> FakeBroker:
        return self.broker


def test_broker_candles_to_dataframe_sorts_and_normalizes_rows():
    candles = list(reversed(_candles(3)))

    df = broker_candles_to_dataframe(candles)

    assert list(df.columns) == ["open", "high", "low", "close", "volume"]
    assert df.index.is_monotonic_increasing
    assert df.iloc[-1]["close"] > df.iloc[0]["close"]


@pytest.mark.asyncio
async def test_active_broker_ohlcv_returns_valid_dataframe_and_metadata():
    manager = FakeBrokerManager()

    df, metadata = await active_broker_ohlcv(
        "EUR/USD",
        "1m",
        trade_style="scalp",
        count=35,
        broker_manager_override=manager,
    )

    assert df is not None
    assert metadata is not None
    assert len(df) == 35
    assert metadata["sourceName"] == "OANDA"
    assert metadata["sourceType"] == "broker_candles"
    assert metadata["priceSource"] == "broker_candles"
    assert metadata["brokerId"] == "oanda"
    assert metadata["environment"] == "practice"
    assert manager.broker.calls == [{"symbol": "EUR/USD", "timeframe": "1m", "count": 35}]


@pytest.mark.asyncio
async def test_active_broker_ohlcv_ignores_disconnected_or_unsupported_broker():
    disconnected = FakeBrokerManager(connected=False)
    unsupported = FakeBrokerManager(candles=False)

    assert await active_broker_ohlcv(
        "EUR/USD",
        "1m",
        trade_style="scalp",
        broker_manager_override=disconnected,
    ) == (None, None)
    assert await active_broker_ohlcv(
        "EUR/USD",
        "1m",
        trade_style="scalp",
        broker_manager_override=unsupported,
    ) == (None, None)
    assert disconnected.broker.calls == []
    assert unsupported.broker.calls == []
