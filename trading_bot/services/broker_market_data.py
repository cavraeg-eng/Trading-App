"""Broker-backed market data adapters for route-level consumers."""

from __future__ import annotations

import asyncio
from typing import Any

import pandas as pd

from trading_bot.data.data_validator import validate_ohlcv
from trading_bot.data.market_data_service import build_source_metadata
from trading_bot.execution.broker_base import BrokerCandle
from trading_bot.execution.broker_manager import BrokerOperationError, broker_manager

BROKER_CANDLES_TIMEOUT_SECONDS = 12.0


def broker_candles_to_dataframe(candles: list[BrokerCandle]) -> pd.DataFrame:
    """Convert broker candles into the app's normalized OHLCV DataFrame shape."""
    rows = [
        {
            "time": pd.Timestamp(candle.time),
            "open": candle.open,
            "high": candle.high,
            "low": candle.low,
            "close": candle.close,
            "volume": candle.volume,
        }
        for candle in candles
    ]
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(rows).set_index("time")
    return df.sort_index()


async def active_broker_ohlcv(
    symbol: str,
    timeframe: str,
    *,
    trade_style: str,
    count: int = 200,
    min_rows: int = 30,
    broker_manager_override: Any | None = None,
) -> tuple[pd.DataFrame | None, dict[str, Any] | None]:
    """Fetch normalized OHLCV from the connected active broker when supported."""
    manager = broker_manager_override or broker_manager
    active = manager.get_active_broker_info()
    if not active or not active.get("connected"):
        return None, None
    capabilities = active.get("capabilities") or {}
    if not capabilities.get("candles"):
        return None, None

    broker_id = str(active.get("id") or active.get("broker_id") or "")
    broker = manager.get_broker(broker_id)
    if not broker:
        return None, None

    try:
        candles = await asyncio.wait_for(
            broker.get_candles(symbol, timeframe=timeframe, count=count),
            timeout=BROKER_CANDLES_TIMEOUT_SECONDS,
        )
    except (BrokerOperationError, TimeoutError):
        return None, None

    df = broker_candles_to_dataframe(candles)
    df, issues = validate_ohlcv(
        df,
        symbol,
        timeframe,
        min_rows=min_rows,
        source_type="broker_candles",
        trade_style=trade_style,
    )
    if df is None:
        return None, None

    metadata = build_source_metadata(
        symbol,
        timeframe,
        trade_style,
        df,
        str(active.get("name") or broker_id),
        "broker_candles",
        False,
        issues,
    )
    metadata["brokerId"] = broker_id
    metadata["environment"] = active.get("environment")
    return df, metadata
