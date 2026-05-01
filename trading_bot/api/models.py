"""Pydantic schemas for API request/response."""

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, model_validator


class SignalDirection(str, Enum):
    """Signal direction enumeration."""
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


class PredictionAssetClass(str, Enum):
    """Supported asset classes for AI prediction requests."""
    FOREX = "forex"
    METAL = "metal"
    CRYPTO = "crypto"
    INDEX = "index"
    EQUITY = "equity"
    COMMODITY = "commodity"
    UNKNOWN = "unknown"


class PredictionStrategyMode(str, Enum):
    """Strategy mode requested by an AI prediction consumer."""
    SCALP = "scalp"
    SWING = "swing"
    POSITION = "position"
    INTRADAY = "intraday"
    AUTOMATION = "automation"


class PredictionSourceType(str, Enum):
    """Originating surface for a prediction request."""
    SCANNER = "scanner"
    LIVE_WORKSPACE = "live_workspace"
    JOURNAL = "journal"
    AUTOMATION = "automation"
    API = "api"
    WATCHLIST = "watchlist"


class PredictionRecommendation(str, Enum):
    """Machine-readable prediction action."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    NO_TRADE = "no_trade"


class PredictionConfidenceBand(str, Enum):
    """Confidence bucket for UI badges and automation gates."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"


class PredictionNoTradeReason(str, Enum):
    """Machine-readable reasons for a valid no-trade prediction."""
    INSUFFICIENT_DATA = "insufficient_data"
    STALE_DATA = "stale_data"
    LOW_CONFIDENCE = "low_confidence"
    MARKET_CLOSED = "market_closed"
    RISK_LIMITS = "risk_limits"
    CONFLICTING_SIGNALS = "conflicting_signals"
    UNSUPPORTED_ASSET = "unsupported_asset"
    MODEL_UNAVAILABLE = "model_unavailable"
    REWARD_RISK_COMPRESSED = "reward_risk_compressed"
    AUTOMATION_DISABLED = "automation_disabled"


class PredictionWarningCode(str, Enum):
    """Warning codes that do not necessarily invalidate a prediction."""
    FALLBACK_DATA = "fallback_data"
    STALE_DATA = "stale_data"
    WIDE_SPREAD = "wide_spread"
    HIGH_VOLATILITY = "high_volatility"
    LOW_LIQUIDITY = "low_liquidity"
    NEAR_MAJOR_EVENT = "near_major_event"
    BROKER_LIMITATION = "broker_limitation"
    MODEL_DEGRADED = "model_degraded"


class PredictionBrokerContext(BaseModel):
    """Optional broker/account context for risk-aware prediction requests."""
    broker_id: Optional[str] = None
    account_id: Optional[str] = None
    account_mode: Optional[str] = None
    base_currency: Optional[str] = None
    equity: Optional[float] = None
    available_margin: Optional[float] = None
    open_positions: int = 0
    max_risk_percent: Optional[float] = None


class PredictionSourceContext(BaseModel):
    """Watchlist, scanner, or automation origin metadata."""
    source_type: PredictionSourceType = PredictionSourceType.API
    source_id: Optional[str] = None
    source_name: Optional[str] = None
    watchlist_id: Optional[str] = None
    scanner_preset_id: Optional[str] = None
    automation_template_id: Optional[str] = None


class PredictionRequest(BaseModel):
    """Stable AI prediction/suggestion request contract."""
    symbol: str
    asset_class: PredictionAssetClass = PredictionAssetClass.UNKNOWN
    timeframe: str = "1h"
    strategy_mode: PredictionStrategyMode = PredictionStrategyMode.SWING
    broker_context: Optional[PredictionBrokerContext] = None
    source_context: PredictionSourceContext = Field(default_factory=PredictionSourceContext)
    market_session: Optional[str] = None
    requested_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    correlation_symbols: List[str] = []
    features: Dict[str, Any] = {}


class PredictionPriceZone(BaseModel):
    """Price zone for entries, targets, and invalidation overlays."""
    min: float
    max: float
    label: Optional[str] = None


class PredictionTarget(BaseModel):
    """Take-profit target or partial-exit level."""
    label: str
    price: float
    reward_risk: Optional[float] = None
    size_percent: Optional[float] = None


class PredictionRationaleItem(BaseModel):
    """Structured reason contributing to the prediction."""
    category: str
    summary: str
    weight: Optional[float] = None
    direction: Optional[str] = None


class PredictionWarning(BaseModel):
    """Structured warning for UI and automation consumers."""
    code: PredictionWarningCode
    message: str
    severity: str = "info"


class PredictionFreshnessMetadata(BaseModel):
    """Market data freshness and source quality metadata."""
    source_name: Optional[str] = None
    source_type: Optional[str] = None
    price_source: Optional[str] = None
    cache_status: Optional[str] = None
    cache_key: Optional[str] = None
    cache_age_seconds: Optional[float] = None
    feature_version: Optional[str] = None
    generated_at: Optional[datetime] = None
    is_fallback: bool = False
    freshness_seconds: Optional[float] = None
    bar_age_seconds: Optional[float] = None
    base_bar_age_seconds: Optional[float] = None
    quote_age_seconds: Optional[float] = None
    last_bar_timestamp: Optional[datetime] = None
    base_last_bar_timestamp: Optional[datetime] = None
    market_status: Optional[str] = None
    market_hours_status: Optional[str] = None
    market_session: Optional[str] = None
    data_delay_reason: Optional[str] = None
    quality_flags: List[str] = []
    evaluated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))


class PredictionLatencyMetadata(BaseModel):
    """Latency metadata for model, data, and end-to-end request timing."""
    data_fetch_ms: Optional[float] = None
    feature_build_ms: Optional[float] = None
    model_inference_ms: Optional[float] = None
    total_latency_ms: Optional[float] = None
    model_name: Optional[str] = None
    model_version: Optional[str] = None


class PredictionChartOverlay(BaseModel):
    """Chart-ready overlay data for workspace and scanner views."""
    current_price: Optional[float] = None
    entry_zone: Optional[PredictionPriceZone] = None
    stop_loss: Optional[float] = None
    take_profit_targets: List[PredictionTarget] = []
    invalidation_level: Optional[float] = None
    support: Optional[float] = None
    resistance: Optional[float] = None
    annotations: List[Dict[str, Any]] = []


class PredictionSuggestionCard(BaseModel):
    """Suggestion-card-ready summary for scanner and workspace UI."""
    title: str
    subtitle: Optional[str] = None
    badge: str
    summary: str
    primary_metric_label: Optional[str] = None
    primary_metric_value: Optional[str] = None
    action_label: Optional[str] = None


class PredictionResponse(BaseModel):
    """Stable AI prediction/suggestion response contract.

    Required for every valid response: symbol, timeframe, strategy_mode,
    recommendation, confidence, confidence_band, rationale, freshness, latency,
    chart, suggestion_card, and generated_at. Trade setup fields are required
    for buy/sell recommendations and intentionally absent for no-trade states.
    """
    prediction_id: str
    request: PredictionRequest
    symbol: str
    asset_class: PredictionAssetClass
    timeframe: str
    strategy_mode: PredictionStrategyMode
    recommendation: PredictionRecommendation
    confidence: float = Field(ge=0, le=100)
    confidence_band: PredictionConfidenceBand
    no_trade_reason: Optional[PredictionNoTradeReason] = None
    entry: Optional[PredictionPriceZone] = None
    stop_loss: Optional[float] = None
    take_profit_targets: List[PredictionTarget] = []
    invalidation_level: Optional[float] = None
    risk_reward: Optional[float] = None
    rationale: List[PredictionRationaleItem]
    warnings: List[PredictionWarning] = []
    freshness: PredictionFreshnessMetadata = Field(default_factory=PredictionFreshnessMetadata)
    latency: PredictionLatencyMetadata = Field(default_factory=PredictionLatencyMetadata)
    chart: PredictionChartOverlay
    suggestion_card: PredictionSuggestionCard
    generated_at: datetime = Field(default_factory=lambda: datetime.now(tz=timezone.utc))
    compatibility: Dict[str, str] = {
        "scanner": "Use suggestion_card, confidence_band, warnings, and no_trade_reason for result cards and filters.",
        "live_workspace": "Use chart overlays for entry, stop, target, invalidation, support, and resistance rendering.",
        "journal": "Persist prediction_id, recommendation, confidence, rationale, and setup levels with trade outcomes.",
        "automation": "Treat no_trade as a successful non-execution result and gate orders on recommendation, confidence, freshness, warnings, and risk_reward.",
    }

    @model_validator(mode="after")
    def validate_trade_state(self) -> "PredictionResponse":
        if self.recommendation == PredictionRecommendation.NO_TRADE:
            if self.no_trade_reason is None:
                raise ValueError("no_trade responses require no_trade_reason")
            if self.entry is not None or self.stop_loss is not None or self.take_profit_targets:
                raise ValueError("no_trade responses must not include actionable trade levels")
        elif self.recommendation in {PredictionRecommendation.BUY, PredictionRecommendation.SELL}:
            if self.entry is None or self.stop_loss is None or not self.take_profit_targets:
                raise ValueError("buy/sell responses require entry, stop_loss, and take_profit_targets")
            if self.risk_reward is None:
                raise ValueError("buy/sell responses require risk_reward")
        return self


def confidence_band_for_score(confidence: float) -> PredictionConfidenceBand:
    """Convert a numeric confidence score into a stable confidence band."""
    if confidence >= 85:
        return PredictionConfidenceBand.VERY_HIGH
    if confidence >= 70:
        return PredictionConfidenceBand.HIGH
    if confidence >= 50:
        return PredictionConfidenceBand.MEDIUM
    return PredictionConfidenceBand.LOW


class IndicatorCondition(BaseModel):
    """Indicator condition for scanner."""
    indicator: str  # e.g., "RSI", "MACD", "BB"
    operator: str   # ">", "<", "crosses_above", "crosses_below", "between"
    value: float
    value2: Optional[float] = None  # for "between" operator
    compare_indicator: Optional[str] = None  # compare against another indicator instead of a numeric threshold


class ScannerConditionGroup(BaseModel):
    """Grouped scanner conditions."""
    id: str
    name: Optional[str] = None
    logic: str = "AND"
    conditions: List[IndicatorCondition] = []


class ScannerConfig(BaseModel):
    """Scanner configuration."""
    name: str = "Custom Scanner"
    conditions: List[IndicatorCondition] = []
    logic: str = "AND"  # "AND" or "OR"
    groups: Optional[List[ScannerConditionGroup]] = None
    pairs: Optional[List[str]] = None  # if None, scan all
    trade_style: str = "swing"
    timeframe: str = "1h"


class ScanResult(BaseModel):
    """Scan result for a single symbol."""
    symbol: str
    signal: str = "NEUTRAL"
    score: float
    matching_conditions: List[str] = []
    indicator_values: Dict[str, float] = {}
    confidence: Optional[float] = None
    market_regime: Optional[str] = None
    trade_style: Optional[str] = None
    timeframe: Optional[str] = None
    opportunity_score: Optional[float] = None
    source_score: Optional[float] = None
    source_metadata: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None


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
    source_metadata: Optional[Dict[str, Any]] = None


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
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    signal_id: Optional[str] = None


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
