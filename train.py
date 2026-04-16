#!/usr/bin/env python3
"""Training script for RL models."""

import argparse
import asyncio
from pathlib import Path

from trading_bot.config import get_logger, get_settings, setup_logging
from trading_bot.data.fetcher import DataFetcher
from trading_bot.data.storage import ParquetStorage
from trading_bot.models.train import ModelTrainer
from trading_bot.config import ModelType

logger = get_logger(__name__)


async def fetch_training_data(symbols, timeframe, days=180):
    """Fetch training data from exchange."""
    settings = get_settings()
    
    async with DataFetcher(
        api_key=settings.binance_api_key,
        secret=settings.binance_secret_key,
        testnet=settings.binance_testnet,
    ) as fetcher:
        logger.info(f"Fetching data for {symbols}")
        
        data = await fetcher.fetch_multiple_symbols(
            symbols=symbols,
            timeframe=timeframe,
            lookback_days=days,
        )
        
        # Save to storage
        storage = ParquetStorage(settings.parquet_path)
        for symbol, df in data.items():
            storage.save_ohlcv(symbol, timeframe, df)
            logger.info(f"Saved {symbol}: {len(df)} records")
        
        return data


def main():
    parser = argparse.ArgumentParser(description="Train RL trading model")
    parser.add_argument("--symbols", nargs="+", help="Symbols to train on")
    parser.add_argument("--model", choices=["PPO", "SAC"], default="PPO", help="Model type")
    parser.add_argument(
        "--architecture",
        choices=["mlp", "lstm", "transformer"],
        default="lstm",
        help="Policy feature extractor architecture",
    )
    parser.add_argument("--timesteps", type=int, default=100000, help="Training timesteps")
    parser.add_argument("--trials", type=int, default=20, help="Optuna trials")
    parser.add_argument("--no-optimize", action="store_true", help="Skip hyperparameter optimization")
    parser.add_argument("--data-path", type=Path, help="Path to existing data")
    parser.add_argument("--output", type=Path, default="./models", help="Model output path")
    parser.add_argument("--window-size", type=int, default=50, help="Observation window size")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward validation")
    parser.add_argument("--train-days", type=int, default=180, help="Walk-forward train window")
    parser.add_argument("--test-days", type=int, default=30, help="Walk-forward test window")
    parser.add_argument(
        "--timesteps-per-fold",
        type=int,
        default=50000,
        help="Training timesteps per walk-forward fold",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level="INFO")
    
    settings = get_settings()
    symbols = args.symbols or settings.symbol_list
    
    # Fetch or load data
    if args.data_path:
        storage = ParquetStorage(args.data_path)
        data = {}
        for symbol in symbols:
            df = storage.load_ohlcv(symbol, settings.timeframe)
            if not df.empty:
                data[symbol] = df
    else:
        data = asyncio.run(fetch_training_data(symbols, settings.timeframe))
    
    if not data:
        logger.error("No data available for training")
        return
    
    # Use first symbol for training
    train_df = list(data.values())[0]
    logger.info(f"Training on {len(train_df)} records")
    
    # Create trainer
    trainer = ModelTrainer(
        model_path=args.output,
        n_trials=args.trials,
        window_size=args.window_size,
        architecture=args.architecture,
    )
    
    # Train
    model_type = ModelType.PPO if args.model == "PPO" else ModelType.SAC
    
    if args.walk_forward:
        trainer.walk_forward_validation(
            df=train_df,
            model_type=model_type,
            train_days=args.train_days,
            test_days=args.test_days,
            timesteps_per_fold=args.timesteps_per_fold,
        )
        logger.info("Walk-forward validation completed successfully!")
        return

    trainer.train(
        df=train_df,
        model_type=model_type,
        total_timesteps=args.timesteps,
        optimize_hyperparams=not args.no_optimize,
    )
    
    logger.info("Training completed successfully!")


if __name__ == "__main__":
    main()
