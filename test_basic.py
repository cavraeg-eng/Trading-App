#!/usr/bin/env python3
"""Basic test to verify project structure and imports."""

import sys
import os
from pathlib import Path

# Add project to path
sys.path.insert(0, str(Path(__file__).parent))

def test_structure():
    """Test that all required files exist."""
    print("Testing project structure...")
    
    required_files = [
        "trading_bot/__init__.py",
        "trading_bot/config/settings.py",
        "trading_bot/data/fetcher.py",
        "trading_bot/features/indicators.py",
        "trading_bot/models/environment.py",
        "trading_bot/risk/manager.py",
        "trading_bot/strategy/rl_strategy.py",
        "trading_bot/execution/paper.py",
        "trading_bot/backtest/engine.py",
        "trading_bot/monitoring/alerts.py",
        "pyproject.toml",
        "requirements.txt",
        "README.md",
        "Dockerfile",
        "docker-compose.yml",
    ]
    
    base_path = Path(__file__).parent
    
    all_exist = True
    for file in required_files:
        path = base_path / file
        if path.exists():
            print(f"  ✓ {file}")
        else:
            print(f"  ✗ {file} - MISSING")
            all_exist = False
    
    return all_exist

def test_imports():
    """Test basic imports (without heavy dependencies)."""
    print("\nTesting basic imports...")
    
    try:
        # These should work with standard library only
        from trading_bot.config.settings import Settings, TradingMode, ModelType
        print("  ✓ Settings imports")
        
        # Test that enums work
        assert TradingMode.PAPER.value == "paper"
        assert TradingMode.LIVE.value == "live"
        assert ModelType.PPO.value == "PPO"
        assert ModelType.SAC.value == "SAC"
        print("  ✓ Enum values correct")
        
        return True
    except Exception as e:
        print(f"  ✗ Import error: {e}")
        return False

def test_settings():
    """Test settings functionality."""
    print("\nTesting settings...")
    
    try:
        from trading_bot.config.settings import Settings
        
        # Create settings with defaults
        settings = Settings()
        
        print(f"  Trading Mode: {settings.trading_mode.value}")
        print(f"  Model Type: {settings.model_type.value}")
        print(f"  Symbols: {settings.symbol_list}")
        print(f"  Timeframe: {settings.timeframe}")
        print(f"  Initial Capital: ${settings.initial_capital:,.2f}")
        print(f"  Max Position Size: {settings.max_position_size:.0%}")
        print(f"  Risk Per Trade: {settings.risk_per_trade:.0%}")
        
        return True
    except Exception as e:
        print(f"  ✗ Settings error: {e}")
        return False

def main():
    print("="*60)
    print("AI Trading Bot - Basic Test")
    print("="*60)
    print(f"Python version: {sys.version}")
    print()
    
    results = []
    
    # Run tests
    results.append(("Structure", test_structure()))
    results.append(("Imports", test_imports()))
    results.append(("Settings", test_settings()))
    
    # Summary
    print("\n" + "="*60)
    print("Test Summary")
    print("="*60)
    
    for name, passed in results:
        status = "✓ PASS" if passed else "✗ FAIL"
        print(f"{name:20s}: {status}")
    
    all_passed = all(r[1] for r in results)
    
    print("="*60)
    if all_passed:
        print("All tests passed! ✓")
        print("\nTo run the full bot, install dependencies:")
        print("  pip install -r requirements.txt")
        print("\nThen configure your .env file and run:")
        print("  python -m trading_bot.main config")
    else:
        print("Some tests failed. ✗")
    
    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
