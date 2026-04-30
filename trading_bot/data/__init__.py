"""Data pipeline module for fetching and storing market data."""

from trading_bot.data.fetcher import DataFetcher
from trading_bot.data.websocket import WebSocketManager
from trading_bot.data.market_data_service import (
    get_ohlcv,
    fetch_yf_sync,
    fetch_yf_historical,
    get_health_status,
    map_symbol_to_yf,
    SYMBOL_MAPPING,
    TIMEFRAME_MAP,
    SPOT_PRICE_SYMBOLS,
)
from trading_bot.data.data_validator import validate_ohlcv, validate_spot_price

try:
    from trading_bot.data.storage import DataStorage, ParquetStorage, SQLiteStorage
except ModuleNotFoundError:
    DataStorage = None
    ParquetStorage = None
    SQLiteStorage = None

__all__ = [
    "DataFetcher",
    "DataStorage",
    "ParquetStorage",
    "SQLiteStorage",
    "WebSocketManager",
    "get_ohlcv",
    "fetch_yf_sync",
    "fetch_yf_historical",
    "get_health_status",
    "map_symbol_to_yf",
    "validate_ohlcv",
    "validate_spot_price",
    "SYMBOL_MAPPING",
    "TIMEFRAME_MAP",
    "SPOT_PRICE_SYMBOLS",
]
