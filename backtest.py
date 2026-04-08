#!/usr/bin/env python3
"""Backtesting script."""

import argparse
from pathlib import Path

import pandas as pd

from trading_bot.backtest.engine import BacktestEngine
from trading_bot.config import get_logger, get_settings, setup_logging
from trading_bot.data.storage import ParquetStorage

logger = get_logger(__name__)


def main():
    parser = argparse.ArgumentParser(description="Backtest trading strategy")
    parser.add_argument("--model", type=Path, required=True, help="Path to trained model")
    parser.add_argument("--data", type=Path, default="./data", help="Path to historical data")
    parser.add_argument("--symbol", help="Symbol to backtest")
    parser.add_argument("--output", type=Path, default="./backtest_results", help="Output directory")
    parser.add_argument("--walk-forward", action="store_true", help="Run walk-forward analysis")
    parser.add_argument("--monte-carlo", action="store_true", help="Run Monte Carlo simulation")
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging(log_level="INFO")
    
    settings = get_settings()
    symbol = args.symbol or settings.symbol_list[0]
    
    # Load data
    storage = ParquetStorage(args.data)
    df = storage.load_ohlcv(symbol, settings.timeframe)
    
    if df.empty:
        logger.error(f"No data found for {symbol}")
        return
    
    logger.info(f"Loaded {len(df)} records for {symbol}")
    
    # Create engine
    engine = BacktestEngine(
        initial_capital=settings.initial_capital,
        commission=0.001,
        slippage=0.0005,
    )
    
    # Run backtest
    logger.info("Running backtest...")
    result = engine.run_rl_backtest(df, args.model)
    
    # Print results
    print("\n" + "="*60)
    print("BACKTEST RESULTS")
    print("="*60)
    print(f"Total Return:        {result.total_return:>10.2%}")
    print(f"Sharpe Ratio:        {result.sharpe_ratio:>10.2f}")
    print(f"Max Drawdown:        {result.max_drawdown:>10.2%}")
    print(f"Win Rate:            {result.win_rate:>10.1%}")
    print(f"Profit Factor:       {result.profit_factor:>10.2f}")
    print(f"Number of Trades:    {result.num_trades:>10}")
    print("="*60)
    
    # Save report
    args.output.mkdir(parents=True, exist_ok=True)
    report_path = args.output / f"backtest_report_{symbol.replace('/', '_')}.txt"
    engine.generate_report(result, report_path)
    logger.info(f"Report saved to {report_path}")
    
    # Walk-forward analysis
    if args.walk_forward:
        logger.info("Running walk-forward analysis...")
        wf_results = engine.run_walk_forward(df)
        
        wf_df = pd.DataFrame([
            {
                "fold": r.fold if hasattr(r, 'fold') else i,
                "return": r.total_return,
                "sharpe": r.sharpe_ratio,
                "drawdown": r.max_drawdown,
            }
            for i, r in enumerate(wf_results)
        ])
        
        wf_path = args.output / f"walk_forward_{symbol.replace('/', '_')}.csv"
        wf_df.to_csv(wf_path, index=False)
        logger.info(f"Walk-forward results saved to {wf_path}")
    
    # Monte Carlo simulation
    if args.monte_carlo:
        logger.info("Running Monte Carlo simulation...")
        returns = result.equity_curve.pct_change().dropna()
        mc_results = engine.monte_carlo_simulation(returns)
        
        print("\n" + "="*60)
        print("MONTE CARLO SIMULATION")
        print("="*60)
        for key, value in mc_results.items():
            if isinstance(value, float):
                print(f"{key:25s}: {value:>10.4f}")
            else:
                print(f"{key:25s}: {value}")
        print("="*60)


if __name__ == "__main__":
    main()
