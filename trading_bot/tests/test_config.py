"""Tests for configuration module."""

import pytest
from pathlib import Path

from trading_bot.config import Settings, TradingMode, ModelType


def test_settings_defaults():
    """Test default settings."""
    settings = Settings()
    
    assert settings.trading_mode == TradingMode.PAPER
    assert settings.model_type == ModelType.PPO
    assert settings.initial_capital == 10000.0
    assert settings.max_position_size == 0.3
    assert settings.scanner_max_concurrent == 4


def test_scanner_concurrency_clamped():
    assert Settings(scanner_max_concurrent=0).scanner_max_concurrent == 1
    assert Settings(scanner_max_concurrent=99).scanner_max_concurrent == 12
    assert Settings(scanner_max_concurrent="bad").scanner_max_concurrent == 4


def test_symbol_list():
    """Test symbol list parsing."""
    settings = Settings(symbols="BTC/USDT,ETH/USDT,SOL/USDT")
    
    assert len(settings.symbol_list) == 3
    assert "BTC/USDT" in settings.symbol_list
    assert "ETH/USDT" in settings.symbol_list


def test_timeframe_validation():
    """Test timeframe validation."""
    with pytest.raises(ValueError):
        Settings(timeframe="invalid")
    
    settings = Settings(timeframe="1h")
    assert settings.timeframe == "1h"


def test_ensure_directories(tmp_path):
    """Test directory creation."""
    settings = Settings(
        data_dir=tmp_path / "data",
        model_path=tmp_path / "models",
        log_file=tmp_path / "logs" / "test.log",
    )
    
    settings.ensure_directories()
    
    assert settings.data_dir.exists()
    assert settings.model_path.exists()
    assert settings.log_file.parent.exists()
