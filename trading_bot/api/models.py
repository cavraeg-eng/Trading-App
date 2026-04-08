"""Pydantic schemas for API request/response."""

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class SignalDirection(str, Enum):
    """Signal direction enumeration."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class IndicatorCondition(BaseModel):
    """Indicator condition for scanner."""
    indicator: str  # e.g., "RSI", "MACD", "BB"
    operator: str   # ">", "<", "crosses_above", "crosses_below", "between"
    value: float
    value2: Optional[float] = None  # for "between" operator


class ScannerConfig(BaseModel):
    """Scanner configuration."""
    name: str = "Custom Scanner"
    conditions: List[IndicatorCondition] = []
    logic: str = "AND"  # "AND" or "OR"
    pairs: Optional[List[str]] = None  # if None, scan all


class ScanResult(BaseModel):
    """Scan result for a single symbol."""
    symbol: str
    signal: str = "NEUTRAL"
    score: float
    matching_conditions: List[str] = []
    indicator_values: Dict[str, float] = {}


class SignalStatus(str, Enum):
    """Signal status enumeration."""
    OPTIMAL_ENTRY = "OPTIMAL_ENTRY"
    VALID = "VALID"
    ABOUT_TO_EXPIRE = "ABOUT_TO_EXPIRE"
    EXPIRED = "EXPIRED"


class SignalBreakdown(BaseModel):
    """Detailed signal breakdown with indicator contributions."""
    symbol: str
    direction: SignalDirection
    confidence: float
    indicators: List[Dict[str, Any]]  # each: {name, value, signal, weight, contribution}
    signal_strength: float
    pattern_accuracy: Optional[float] = None
    timestamp: datetime
    signal_status: Optional[SignalStatus] = None
    expires_at: Optional[datetime] = None
    entry_min: Optional[float] = None
    entry_max: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit1: Optional[float] = None
    take_profit2: Optional[float] = None
    take_profit3: Optional[float] = None


class CandleData(BaseModel):
    """OHLCV candle data."""
    time: int  # Unix timestamp in seconds
    open: float
    high: float
    low: float
    close: float
    volume: float


class SentimentData(BaseModel):
    """Sentiment data for a symbol."""
    symbol: str
    score: float  # -1.0 to 1.0
    label: str  # "bearish", "neutral", "bullish"
    headlines: List[Dict[str, Any]]
    trend: List[float]  # last 24 data points


class BrokerInfo(BaseModel):
    """Broker information."""
    id: str
    name: str
    type: str  # "ccxt", "oanda", "alpaca"
    connected: bool = False
    supported_markets: List[str]


class OrderRequest(BaseModel):
    """Order request."""
    broker_id: str
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None


class LeaderboardEntry(BaseModel):
    """Leaderboard entry."""
    rank: int
    username: str
    avatar: str
    monthly_return: float
    win_rate: float
    sharpe_ratio: float
    total_trades: int
    followers: int


class SignalPost(BaseModel):
    """Social signal post."""
    id: str
    username: str
    avatar: str
    symbol: str
    direction: SignalDirection
    confidence: float
    entry_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    result: Optional[str] = None  # "won", "lost", "open"
    pnl: Optional[float] = None
    timestamp: datetime
    likes: int = 0
    comments: int = 0


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    uptime: float
