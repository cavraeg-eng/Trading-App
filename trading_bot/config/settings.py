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
