"""Backtesting engine with vectorbt integration."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
import vectorbt as vbt

from trading_bot.config import get_logger
from trading_bot.execution.paper import PaperTradingExecutor
from trading_bot.features.engineering import FeatureEngineer
from trading_bot.models.agent import RLAgent
from trading_bot.models.environment import TradingEnvironment
from trading_bot.strategy.rl_strategy import RLStrategy

logger = get_logger(__name__)


@dataclass
class BacktestResult:
    """Backtest result container."""
    total_return: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown: float
    win_rate: float
    profit_factor: float
    expectancy: float
    volatility: float
    num_trades: int
    avg_trade_return: float
    equity_curve: pd.Series
    trades: pd.DataFrame
    metrics: Dict


class BacktestEngine:
    """Backtesting engine for strategy evaluation."""
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
    ):
        """Initialize backtest engine.
        
        Args:
            initial_capital: Starting capital
            commission: Commission rate
            slippage: Slippage percentage
        """
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        
        self.feature_engineer = FeatureEngineer()
    
    def run_vectorbt_backtest(
        self,
        df: pd.DataFrame,
        entries: pd.Series,
        exits: pd.Series,
        short_entries: Optional[pd.Series] = None,
        short_exits: Optional[pd.Series] = None,
    ) -> BacktestResult:
        """Run backtest using vectorbt.
        
        Args:
            df: OHLCV data
            entries: Entry signals
            exits: Exit signals
            short_entries: Short entry signals
            short_exits: Short exit signals
            
        Returns:
            Backtest result
        """
        # Create portfolio
        if short_entries is not None and short_exits is not None:
            portfolio = vbt.Portfolio.from_signals(
                close=df["close"],
                entries=entries,
                exits=exits,
                short_entries=short_entries,
                short_exits=short_exits,
                init_cash=self.initial_capital,
                fees=self.commission,
                slippage=self.slippage,
                freq="1h",
            )
        else:
            portfolio = vbt.Portfolio.from_signals(
                close=df["close"],
                entries=entries,
                exits=exits,
                init_cash=self.initial_capital,
                fees=self.commission,
                slippage=self.slippage,
                freq="1h",
            )
        
        # Get metrics
        total_return = portfolio.total_return()
        sharpe_ratio = portfolio.sharpe_ratio()
        sortino_ratio = portfolio.sortino_ratio()
        calmar_ratio = portfolio.calmar_ratio()
        max_drawdown = portfolio.max_drawdown()
        win_rate = portfolio.trades.win_rate()
        profit_factor = portfolio.trades.profit_factor()
        
        # Calculate expectancy
        avg_win = portfolio.trades.returns[portfolio.trades.returns > 0].mean()
        avg_loss = portfolio.trades.returns[portfolio.trades.returns < 0].mean()
        win_rate_val = win_rate if not pd.isna(win_rate) else 0
        expectancy = (win_rate_val * avg_win + (1 - win_rate_val) * avg_loss)
        
        # Get trades
        trades = portfolio.trades.records_readable
        
        return BacktestResult(
            total_return=total_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            max_drawdown=max_drawdown,
            win_rate=win_rate_val,
            profit_factor=profit_factor if not pd.isna(profit_factor) else 0,
            expectancy=expectancy if not pd.isna(expectancy) else 0,
            volatility=portfolio.returns().std() * np.sqrt(365),
            num_trades=len(trades),
            avg_trade_return=portfolio.trades.returns.mean() if len(trades) > 0 else 0,
            equity_curve=portfolio.value(),
            trades=trades,
            metrics={
                "avg_winning_trade": portfolio.trades.returns[portfolio.trades.returns > 0].mean() if len(trades) > 0 else 0,
                "avg_losing_trade": portfolio.trades.returns[portfolio.trades.returns < 0].mean() if len(trades) > 0 else 0,
                "max_trade_duration": portfolio.trades.duration.max() if len(trades) > 0 else 0,
                "avg_trade_duration": portfolio.trades.duration.mean() if len(trades) > 0 else 0,
            },
        )
    
    def run_rl_backtest(
        self,
        df: pd.DataFrame,
        model_path: Path,
        window_size: int = 50,
    ) -> BacktestResult:
        """Run backtest with RL agent.
        
        Args:
            df: OHLCV data
            model_path: Path to trained model
            window_size: Observation window
            
        Returns:
            Backtest result
        """
        metadata_path = model_path.with_name(f"{model_path.stem}_metadata.json")
        feature_columns: Optional[List[str]] = None

        if metadata_path.exists():
            strategy = RLStrategy(symbols=["BACKTEST"], model_path=model_path)
            self.feature_engineer = strategy.feature_engineer
            feature_columns = strategy.feature_columns
            window_size = strategy.window_size
        else:
            strategy = None

        # Prepare features
        featured_df = self.feature_engineer.create_features(df)

        if self.feature_engineer.scaler is not None:
            featured_df = self.feature_engineer.transform_features(
                featured_df,
                feature_columns or self.feature_engineer.feature_names,
            )
        
        # Create environment
        env = TradingEnvironment(
            df=featured_df,
            initial_balance=self.initial_capital,
            window_size=window_size,
            commission=self.commission,
            slippage=self.slippage,
            feature_columns=feature_columns or self.feature_engineer.feature_names,
        )
        
        # Load agent
        agent = strategy.agent if strategy is not None and strategy.agent is not None else RLAgent()
        if strategy is None or strategy.agent is None:
            agent.load(model_path, env=env)
        
        # Run backtest
        obs, _ = env.reset()
        done = False
        
        while not done:
            action, _ = agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
        
        # Get metrics
        metrics = env.get_performance_metrics()
        
        # Create equity curve series
        equity_curve = pd.Series(
            env.equity_curve,
            index=featured_df.index[-len(env.equity_curve):]
        )
        
        # Create trades dataframe
        trades_data = []
        for i, trade in enumerate(env.trades):
            trades_data.append({
                "trade_id": i,
                "entry_price": trade.get("price", 0),
                "exit_price": trade.get("exit_price", 0),
                "pnl": trade.get("realized_pnl", trade.get("pnl", 0)),
                "return": trade.get("realized_pnl", trade.get("pnl", 0)) / self.initial_capital,
            })
        
        trades_df = pd.DataFrame(trades_data)
        
        # Calculate additional metrics
        returns = equity_curve.pct_change().dropna()
        volatility = returns.std() * np.sqrt(365)
        
        # Win rate from trades
        if len(trades_df) > 0:
            win_rate = (trades_df["pnl"] > 0).mean()
            profit_factor = abs(
                trades_df[trades_df["pnl"] > 0]["pnl"].sum() /
                trades_df[trades_df["pnl"] < 0]["pnl"].sum()
            ) if trades_df[trades_df["pnl"] < 0]["pnl"].sum() != 0 else float('inf')
        else:
            win_rate = 0
            profit_factor = 0
        
        return BacktestResult(
            total_return=metrics.get("total_return", 0),
            sharpe_ratio=metrics.get("sharpe_ratio", 0),
            sortino_ratio=0,  # Calculate if needed
            calmar_ratio=0,  # Calculate if needed
            max_drawdown=metrics.get("max_drawdown", 0),
            win_rate=win_rate,
            profit_factor=profit_factor,
            expectancy=0,  # Calculate if needed
            volatility=volatility,
            num_trades=len(trades_df),
            avg_trade_return=trades_df["return"].mean() if len(trades_df) > 0 else 0,
            equity_curve=equity_curve,
            trades=trades_df,
            metrics=metrics,
        )
    
    def run_walk_forward(
        self,
        df: pd.DataFrame,
        train_size: int = 1000,
        test_size: int = 200,
        step_size: int = 100,
    ) -> List[BacktestResult]:
        """Run walk-forward analysis.
        
        Args:
            df: Full dataset
            train_size: Training window size
            test_size: Testing window size
            step_size: Step size between windows
            
        Returns:
            List of backtest results
        """
        results = []
        n_samples = len(df)
        
        start_idx = train_size
        
        while start_idx + test_size <= n_samples:
            train_end = start_idx
            test_end = start_idx + test_size
            
            train_df = df.iloc[start_idx - train_size:train_end]
            test_df = df.iloc[train_end:test_end]
            
            logger.info(
                f"Walk-forward window: train {train_df.index[0]} to {train_df.index[-1]}, "
                f"test {test_df.index[0]} to {test_df.index[-1]}"
            )
            
            # Train model on train set
            # (Simplified - would need actual training)
            
            # Test on test set
            # (Simplified - using simple signals)
            
            # Generate simple moving average signals
            short_ma = test_df["close"].rolling(10).mean()
            long_ma = test_df["close"].rolling(30).mean()
            
            entries = (short_ma > long_ma) & (short_ma.shift(1) <= long_ma.shift(1))
            exits = (short_ma < long_ma) & (short_ma.shift(1) >= long_ma.shift(1))
            
            result = self.run_vectorbt_backtest(test_df, entries, exits)
            results.append(result)
            
            start_idx += step_size
        
        return results
    
    def monte_carlo_simulation(
        self,
        returns: pd.Series,
        n_simulations: int = 1000,
        n_days: int = 252,
    ) -> Dict:
        """Run Monte Carlo simulation.
        
        Args:
            returns: Historical returns series
            n_simulations: Number of simulations
            n_days: Days to simulate
            
        Returns:
            Simulation results
        """
        np.random.seed(42)
        
        # Calculate statistics
        mean_return = returns.mean()
        std_return = returns.std()
        
        # Run simulations
        simulated_paths = []
        final_returns = []
        max_drawdowns = []
        
        for _ in range(n_simulations):
            # Generate random returns
            simulated_returns = np.random.normal(mean_return, std_return, n_days)
            
            # Calculate equity curve
            equity = (1 + simulated_returns).cumprod()
            simulated_paths.append(equity)
            
            # Final return
            final_returns.append(equity[-1] - 1)
            
            # Max drawdown
            peak = np.maximum.accumulate(equity)
            drawdown = (peak - equity) / peak
            max_drawdowns.append(np.max(drawdown))
        
        simulated_paths = np.array(simulated_paths)
        final_returns = np.array(final_returns)
        max_drawdowns = np.array(max_drawdowns)
        
        return {
            "mean_final_return": np.mean(final_returns),
            "median_final_return": np.median(final_returns),
            "std_final_return": np.std(final_returns),
            "worst_case_return": np.percentile(final_returns, 5),
            "best_case_return": np.percentile(final_returns, 95),
            "mean_max_drawdown": np.mean(max_drawdowns),
            "median_max_drawdown": np.median(max_drawdowns),
            "worst_max_drawdown": np.percentile(max_drawdowns, 95),
            "probability_of_profit": np.mean(final_returns > 0),
            "probability_of_drawdown_10pct": np.mean(max_drawdowns > 0.1),
            "probability_of_drawdown_20pct": np.mean(max_drawdowns > 0.2),
        }
    
    def generate_report(
        self,
        result: BacktestResult,
        output_path: Optional[Path] = None,
    ) -> str:
        """Generate backtest report.
        
        Args:
            result: Backtest result
            output_path: Path to save report
            
        Returns:
            Report string
        """
        report = f"""
{'='*60}
BACKTEST REPORT
{'='*60}

PERFORMANCE METRICS
{'-'*40}
Total Return:          {result.total_return:>10.2%}
Sharpe Ratio:          {result.sharpe_ratio:>10.2f}
Sortino Ratio:         {result.sortino_ratio:>10.2f}
Calmar Ratio:          {result.calmar_ratio:>10.2f}
Max Drawdown:          {result.max_drawdown:>10.2%}
Volatility:            {result.volatility:>10.2%}

TRADE STATISTICS
{'-'*40}
Number of Trades:      {result.num_trades:>10}
Win Rate:              {result.win_rate:>10.2%}
Profit Factor:         {result.profit_factor:>10.2f}
Expectancy:            {result.expectancy:>10.4f}
Avg Trade Return:      {result.avg_trade_return:>10.4f}

EQUITY CURVE
{'-'*40}
Initial Value:         {result.equity_curve.iloc[0]:>10.2f}
Final Value:           {result.equity_curve.iloc[-1]:>10.2f}
Peak Value:            {result.equity_curve.max():>10.2f}
Min Value:             {result.equity_curve.min():>10.2f}

ADDITIONAL METRICS
{'-'*40}
"""
        
        for key, value in result.metrics.items():
            if isinstance(value, float):
                report += f"{key:20s}: {value:>10.4f}\n"
            else:
                report += f"{key:20s}: {value:>10}\n"
        
        report += f"\n{'='*60}\n"
        
        if output_path:
            output_path.write_text(report)
            logger.info(f"Report saved to {output_path}")
        
        return report
