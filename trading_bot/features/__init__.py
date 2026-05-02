"""Feature engineering module for technical indicators and custom features."""

from trading_bot.features.indicators import TechnicalIndicators
from trading_bot.features.engineering import FeatureEngineer
from trading_bot.features.market_features import (
    MarketFeaturePayload,
    MarketFeatureRequest,
    MarketQuote,
    NormalizedCandle,
    build_market_features,
    build_market_features_batch,
)

try:
    from trading_bot.features.store import FeatureStore
except Exception:
    FeatureStore = None

__all__ = [
    "TechnicalIndicators",
    "FeatureEngineer",
    "FeatureStore",
    "NormalizedCandle",
    "MarketQuote",
    "MarketFeatureRequest",
    "MarketFeaturePayload",
    "build_market_features",
    "build_market_features_batch",
]
