# AI Trading Bot

A production-ready, institutional-grade AI-powered cryptocurrency trading bot using Reinforcement Learning (PPO/SAC) with comprehensive risk management and backtesting capabilities.

## Architecture

```mermaid
graph TB
    subgraph "Data Layer"
        A[CCXT Data Fetcher] --> B[Parquet/SQLite Storage]
        C[WebSocket Feed] --> D[Redis Cache]
    end
    
    subgraph "Feature Engineering"
        B --> E[Technical Indicators]
        D --> E
        E --> F[Feature Store]
    end
    
    subgraph "AI/ML Core"
        F --> G[RL Environment]
        G --> H[PPO/SAC Agent]
        H --> I[Model Registry]
    end
    
    subgraph "Trading Engine"
        I --> J[Strategy Module]
        J --> K[Risk Manager]
        K --> L[Execution Engine]
    end
    
    subgraph "Monitoring"
        L --> M[Trade Logger]
        M --> N[Dashboard/Alerts]
    end
```

## Features

### Core Components
- **Data Pipeline**: Async CCXT integration for OHLCV, orderbook, and funding rate data
- **Feature Engineering**: 100+ technical indicators, volatility regimes, Fourier features
- **RL Models**: PPO/SAC with Stable-Baselines3, LSTM/Transformer feature extractors
- **Training Regimes**: Chronological splits, walk-forward validation, persisted preprocessing artifacts
- **Risk Management**: Kelly criterion, volatility targeting, circuit breakers
- **Backtesting**: VectorBT integration with walk-forward and Monte Carlo analysis
- **Monitoring**: Telegram/Discord alerts, Streamlit dashboard

### Risk Management
- Position sizing: Fixed fraction, Kelly criterion, ATR-based, volatility targeting
- Portfolio limits: Max drawdown, position size, total exposure
- Circuit breakers: Daily loss limits, consecutive loss detection
- Emergency stop: Automatic position closure on critical events

## Installation

### Prerequisites
- Python 3.11+
- Git
- (Optional) Docker and Docker Compose

### Setup

1. **Clone the repository**
```bash
git clone <repository-url>
cd trading-bot
```

2. **Create virtual environment**
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
# Or with pip install -e .
```

4. **Configure environment**
```bash
cp .env.example .env
# Edit .env with your API keys and settings
```

### Docker Setup

```bash
# Build and run with Docker Compose
docker-compose up -d

# View logs
docker-compose logs -f trading-bot

# Stop services
docker-compose down
```

## Configuration

Edit `.env` file with your settings:

```env
# Exchange API Keys (Binance)
BINANCE_API_KEY=your_api_key_here
BINANCE_SECRET_KEY=your_secret_key_here
BINANCE_TESTNET=true

# Trading Configuration
TRADING_MODE=paper
SYMBOLS=BTC/USDT,ETH/USDT,SOL/USDT
TIMEFRAME=1h
INITIAL_CAPITAL=10000

# Risk Management
MAX_DAILY_DRAWDOWN=0.05
MAX_POSITION_SIZE=0.3
RISK_PER_TRADE=0.02

# Model Configuration
MODEL_TYPE=PPO
TIMESTEPS=100000

# Notifications (optional)
TELEGRAM_BOT_TOKEN=your_token
TELEGRAM_CHAT_ID=your_chat_id
```

## Usage

### Command Line Interface

```bash
# Show help
python -m trading_bot.main --help

# Show configuration
python -m trading_bot.main config

# Fetch historical data
python -m trading_bot.main fetch-data --days 180

# Train model
python -m trading_bot.main train --model PPO --architecture lstm --timesteps 100000

# Or use the training script
python train.py --symbols BTC/USDT ETH/USDT --architecture lstm --timesteps 100000

# Run backtest
python -m trading_bot.main backtest --model ./models/PPO_20240101.zip

# Or use the backtest script
python backtest.py --model ./models/PPO_20240101.zip --monte-carlo

# Run paper trading
python -m trading_bot.main run --mode paper --model ./models/PPO_20240101.zip

# Run live trading (BE CAREFUL!)
python -m trading_bot.main run --mode live --model ./models/PPO_20240101.zip

# Launch dashboard
python -m trading_bot.main dashboard
```

### Training a Model

```bash
# Basic training
python train.py --model PPO --architecture lstm --timesteps 100000

# With hyperparameter optimization
python train.py --model PPO --architecture transformer --timesteps 100000 --trials 50

# Train on specific symbols
python train.py --symbols BTC/USDT ETH/USDT --architecture lstm --timesteps 50000

# Use existing data
python train.py --data-path ./data --model SAC --architecture mlp

# Run walk-forward validation
python train.py --model PPO --architecture lstm --walk-forward --train-days 180 --test-days 30
```

### Experiment Matrix

```bash
# Print the recommended PPO/SAC experiment matrix
python3 run_experiment_matrix.py

# Execute the full walk-forward experiment matrix
python3 run_experiment_matrix.py --data-path ./data --execute

# Summarize completed experiment folders only
python3 run_experiment_matrix.py --summarize-only

# Promote the best completed winner and write retrain artifacts
python3 run_experiment_matrix.py --summarize-only --promote-winner

# Promote and retrain the best winner on full data
python3 run_experiment_matrix.py --summarize-only --promote-winner --retrain-best
```

See `EXPERIMENT_MATRIX.md` for the full comparison plan and promotion criteria.
Completed runs also produce `experiment_stability.md` for fold-by-fold consistency review.

### Backtesting

```bash
# Basic backtest
python backtest.py --model ./models/PPO_20240101.zip

# With walk-forward analysis
python backtest.py --model ./models/PPO_20240101.zip --walk-forward

# With Monte Carlo simulation
python backtest.py --model ./models/PPO_20240101.zip --monte-carlo

# Specific symbol
python backtest.py --model ./models/PPO_20240101.zip --symbol ETH/USDT
```

## Project Structure

```
trading_bot/
├── config/              # Configuration and logging
├── data/                # Data fetching and storage
│   ├── fetcher.py       # CCXT async fetcher
│   ├── storage.py       # Parquet/SQLite storage
│   └── websocket.py     # WebSocket manager
├── features/            # Feature engineering
│   ├── indicators.py    # Technical indicators
│   ├── engineering.py   # Custom features
│   └── store.py         # Feature store
├── models/              # RL models
│   ├── environment.py   # Gymnasium trading env
│   ├── agent.py         # RL agent wrapper
│   └── train.py         # Training pipeline
├── risk/                # Risk management
│   ├── sizing.py        # Position sizing
│   ├── manager.py       # Risk manager
│   └── circuit_breaker.py
├── strategy/            # Trading strategies
│   ├── base.py          # Base strategy
│   └── rl_strategy.py   # RL strategy
├── execution/           # Order execution
│   ├── paper.py         # Paper trading
│   └── live.py          # Live execution
├── backtest/            # Backtesting
│   └── engine.py        # Backtest engine
├── monitoring/          # Monitoring & alerts
│   ├── alerts.py        # Telegram/Discord
│   └── dashboard.py     # Streamlit UI
└── tests/               # Unit tests
```

## Key Dependencies

- **Data**: CCXT 4.2+, Pandas 2.1+, PyArrow 14+
- **ML/RL**: PyTorch 2.1+, Stable-Baselines3 2.3+, Gymnasium 0.29+, Optuna 3.5+
- **Analysis**: vectorbt 0.26+, pandas-ta 0.3+
- **Monitoring**: structlog 24+, python-telegram-bot 20+, streamlit 1.29+

## Risk Management

### Position Sizing Methods

1. **Fixed Fraction**: Risk fixed percentage per trade
2. **Kelly Criterion**: Optimal position sizing based on win rate
3. **ATR-Based**: Position size based on volatility
4. **Volatility Targeting**: Target specific portfolio volatility

### Circuit Breakers

- Daily loss limit (default: 5%)
- Maximum drawdown (default: 15%)
- Consecutive losses (default: 5)
- Volatility spike detection

## Backtesting Features

- **VectorBT Integration**: Fast vectorized backtesting
- **Realistic Simulation**: Slippage, fees, latency
- **Walk-Forward Analysis**: Out-of-sample testing
- **Monte Carlo Simulation**: Risk analysis
- **Comprehensive Metrics**: Sharpe, Sortino, Calmar, max drawdown

## Monitoring

### Alerts
- Trade execution notifications
- Daily PnL reports
- Circuit breaker triggers
- Error notifications

### Dashboard
- Real-time equity curve
- Drawdown visualization
- Trade history
- Performance metrics

## Testing

```bash
# Run all tests
pytest

# Run specific test file
pytest trading_bot/tests/test_risk.py

# Run with coverage
pytest --cov=trading_bot --cov-report=html
```

### Release Validation

Before release, run the consolidated validation checklist:

```bash
python release_validate.py
```

This checks secret/artifact hygiene, targeted backend broker and trade-ledger tests, the frontend build, and read-only API smoke routes. See `RELEASE_VALIDATION.md` for the full checklist, manual UI smoke notes, and release note template.

## Safety & Risk Warnings

**IMPORTANT DISCLAIMERS:**

1. **Trading Risk**: Cryptocurrency trading involves substantial risk of loss. Past performance does not guarantee future results.

2. **Testing Required**: Always test thoroughly in paper trading mode before using real money.

3. **Start Small**: When going live, start with minimal capital and gradually increase.

4. **Monitoring**: Never leave the bot unattended for extended periods without monitoring.

5. **API Security**: Keep your API keys secure. Use testnet for development. Enable IP restrictions on your exchange API keys.

6. **No Financial Advice**: This software is for educational purposes only. It is not financial advice.

7. **Bugs**: This is complex software that may contain bugs. Use at your own risk.

## Troubleshooting

### Common Issues

**Import errors**: Ensure all dependencies are installed
```bash
pip install -r requirements.txt
```

**API connection errors**: Check API keys and testnet settings in `.env`

**Out of memory**: Reduce batch size or observation window in configuration

**Model not loading**: Ensure model file path is correct

## Development

### Adding New Features

1. **New Strategy**: Inherit from `BaseStrategy` in `strategy/base.py`
2. **New Indicator**: Add to `features/indicators.py`
3. **New Risk Rule**: Extend `RiskManager` in `risk/manager.py`

### Code Style

```bash
# Format code
black trading_bot/

# Lint code
ruff check trading_bot/

# Type check
mypy trading_bot/
```

## License

MIT License - See LICENSE file for details

## Support

For issues and feature requests, please use GitHub Issues.

## Acknowledgments

- [Stable-Baselines3](https://stable-baselines3.readthedocs.io/)
- [CCXT](https://docs.ccxt.com/)
- [VectorBT](https://vectorbt.dev/)
- [pandas-ta](https://twopirllc.github.io/pandas-ta/)

---

**WARNING**: This is sophisticated trading software. Use at your own risk. The authors assume no responsibility for trading losses.
