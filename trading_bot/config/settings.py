"""Pydantic settings for the trading bot."""

from enum import Enum
from pathlib import Path
from typing import List, Optional, Union

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class TradingMode(str, Enum):
    """Trading mode enumeration."""
    PAPER = "paper"
    LIVE = "live"


class ModelType(str, Enum):
    """RL model type enumeration."""
    PPO = "PPO"
    SAC = "SAC"


class Settings(BaseSettings):
    """Application settings with validation."""
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )
    
    # ============================================
    # Exchange Configuration
    # ============================================
    binance_api_key: str = Field(default="", description="Binance API key")
    binance_secret_key: str = Field(default="", description="Binance secret key")
    binance_testnet: bool = Field(default=True, description="Use Binance testnet")
    
    # ============================================
    # Market Data Configuration
    # ============================================
    gold_api_key: Optional[str] = Field(
        default=None, 
        description="GoldAPI.io API key for accurate XAU/USD spot prices (optional)"
    )
    use_spot_prices: bool = Field(
        default=True,
        description="Use spot price APIs for XAU/USD instead of futures"
    )
    coingecko_api_key: Optional[str] = Field(
        default=None,
        description="CoinGecko Pro API key for higher rate limits (optional)"
    )
    
    # ── yfinance tuning ──
    yf_max_concurrent: int = Field(
        default=2,
        description="Max concurrent yfinance requests (semaphore limit)"
    )
    yf_max_retries: int = Field(
        default=3,
        description="Max retry attempts for yfinance requests"
    )
    scanner_max_concurrent: int = Field(
        default=4,
        description="Max concurrent scanner symbol evaluations"
    )
    
    # ── Cache TTLs ──
    spot_cache_ttl_scalp: int = Field(
        default=20,
        description="Spot price cache TTL in seconds for scalp mode"
    )
    spot_cache_ttl_swing: int = Field(
        default=60,
        description="Spot price cache TTL in seconds for swing mode"
    )
    ohlcv_cache_ttl_intraday: int = Field(
        default=5,
        description="OHLCV cache TTL in seconds for intraday timeframes"
    )
    ohlcv_cache_ttl_daily: int = Field(
        default=300,
        description="OHLCV cache TTL in seconds for daily timeframe"
    )
    
    # ── Source policy ──
    xau_source_policy: str = Field(
        default="spot_preferred",
        description="XAU/USD source policy: spot_preferred, futures_only, spot_only"
    )
    enable_coingecko_fallback: bool = Field(
        default=True,
        description="Enable CoinGecko PAXG as last-resort fallback for gold spot"
    )
    coingecko_cooldown_seconds: int = Field(
        default=180,
        description="Temporary cooldown after CoinGecko rate-limit or provider failure"
    )
    enable_data_health_monitoring: bool = Field(
        default=True,
        description="Enable data source health tracking and reporting"
    )
    metals_live_enabled: bool = Field(
        default=False,
        description="Enable metals.live as a spot gold source"
    )
    gold_api_free_enabled: bool = Field(
        default=True,
        description="Enable free gold-api.com spot gold source"
    )
    swissquote_xau_enabled: bool = Field(
        default=True,
        description="Enable Swissquote public XAU/USD quote feed as backup source"
    )
    
    # ============================================
    # Trading Configuration
    # ============================================
    trading_mode: TradingMode = Field(
        default=TradingMode.PAPER, 
        description="Trading mode: paper or live"
    )
    symbols: str = Field(
        default="BTC/USDT,ETH/USDT",
        description="Comma-separated list of trading symbols"
    )
    timeframe: str = Field(default="1h", description="Candle timeframe")
    initial_capital: float = Field(default=10000.0, description="Initial capital in USDT")
    max_positions: int = Field(default=3, description="Maximum number of open positions")
    leverage: float = Field(default=1.0, description="Leverage multiplier")
    
    # ============================================
    # Risk Management
    # ============================================
    max_daily_drawdown: float = Field(
        default=0.05, 
        description="Maximum daily drawdown (0.05 = 5%)"
    )
    max_position_size: float = Field(
        default=0.3,
        description="Maximum position size as fraction of capital"
    )
    max_total_exposure: float = Field(
        default=0.8,
        description="Maximum total exposure as fraction of capital"
    )
    risk_per_trade: float = Field(
        default=0.02,
        description="Risk per trade as fraction of capital"
    )
    volatility_target: float = Field(
        default=0.15,
        description="Annualized volatility target"
    )
    prediction_min_actionable_confidence: float = Field(
        default=62.0,
        description="Minimum calibrated confidence required for actionable AI predictions"
    )
    prediction_stale_data_seconds: float = Field(
        default=900.0,
        description="Maximum source freshness age in seconds before AI predictions are gated"
    )
    prediction_max_spread_bps: float = Field(
        default=8.0,
        description="Maximum estimated spread in basis points before AI predictions are gated"
    )
    prediction_min_risk_reward: float = Field(
        default=1.35,
        description="Minimum reward-to-risk ratio required for actionable AI predictions"
    )
    prediction_volatility_spike_atr_pct: float = Field(
        default=2.5,
        description="ATR percentage threshold treated as a high-volatility no-trade spike"
    )
    
    # ============================================
    # Data Storage
    # ============================================
    data_dir: Path = Field(default=Path("./data"), description="Data directory path")
    db_path: Path = Field(default=Path("./data/trading.db"), description="SQLite database path")
    parquet_path: Path = Field(
        default=Path("./data/parquet"), 
        description="Parquet storage path"
    )
    
    # Redis configuration
    redis_host: str = Field(default="localhost", description="Redis host")
    redis_port: int = Field(default=6379, description="Redis port")
    redis_db: int = Field(default=0, description="Redis database number")
    redis_password: Optional[str] = Field(default=None, description="Redis password")
    
    # ============================================
    # Model Configuration
    # ============================================
    model_type: ModelType = Field(default=ModelType.PPO, description="RL model type")
    model_path: Path = Field(default=Path("./models"), description="Model storage path")
    timesteps: int = Field(default=100000, description="Training timesteps")
    learning_rate: float = Field(default=0.0003, description="Learning rate")
    batch_size: int = Field(default=64, description="Batch size for training")
    
    # ============================================
    # Notifications
    # ============================================
    telegram_bot_token: Optional[str] = Field(default=None, description="Telegram bot token")
    telegram_chat_id: Optional[str] = Field(default=None, description="Telegram chat ID")
    discord_webhook_url: Optional[str] = Field(default=None, description="Discord webhook URL")
    
    # ============================================
    # Logging
    # ============================================
    log_level: str = Field(default="INFO", description="Logging level")
    log_file: Path = Field(default=Path("./logs/trading_bot.log"), description="Log file path")
    
    # ============================================
    # Monitoring
    # ============================================
    dashboard_port: int = Field(default=8501, description="Dashboard port")
    metrics_port: int = Field(default=9090, description="Metrics port")
    
    @field_validator("symbols")
    @classmethod
    def parse_symbols(cls, v: str) -> str:
        """Validate symbols format."""
        if not v:
            raise ValueError("Symbols cannot be empty")
        symbols = [s.strip() for s in v.split(",")]
        if not symbols:
            raise ValueError("At least one symbol required")
        return ",".join(symbols)
    
    @field_validator("timeframe")
    @classmethod
    def validate_timeframe(cls, v: str) -> str:
        """Validate timeframe format."""
        valid_timeframes = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h", "1d", "3d", "1w", "1M"]
        if v not in valid_timeframes:
            raise ValueError(f"Invalid timeframe. Must be one of: {valid_timeframes}")
        return v

    @field_validator("scanner_max_concurrent", mode="before")
    @classmethod
    def clamp_scanner_concurrency(cls, v: Union[str, int]) -> int:
        try:
            value = int(v)
        except (TypeError, ValueError):
            value = 4
        return max(1, min(value, 12))
    
    @field_validator("data_dir", "db_path", "parquet_path", "model_path", "log_file", mode="before")
    @classmethod
    def parse_path(cls, v: Union[str, Path]) -> Path:
        """Parse string to Path."""
        if isinstance(v, str):
            return Path(v)
        return v
    
    @property
    def symbol_list(self) -> List[str]:
        """Get list of symbols."""
        return [s.strip() for s in self.symbols.split(",")]
    
    def ensure_directories(self) -> None:
        """Create necessary directories."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.parquet_path.mkdir(parents=True, exist_ok=True)
        self.model_path.mkdir(parents=True, exist_ok=True)
        self.log_file.parent.mkdir(parents=True, exist_ok=True)


# Global settings instance
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get or create global settings instance."""
    global _settings
    if _settings is None:
        _settings = Settings()
        _settings.ensure_directories()
    return _settings
