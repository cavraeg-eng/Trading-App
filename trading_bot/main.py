"""Main entry point for the trading bot."""

import asyncio
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from trading_bot.config import get_logger, get_settings, setup_logging
from trading_bot.data.fetcher import DataFetcher
from trading_bot.execution.live import LiveExecutor
from trading_bot.execution.paper import PaperTradingExecutor
from trading_bot.monitoring.alerts import AlertManager, AlertLevel
from trading_bot.risk.circuit_breaker import CircuitBreaker
from trading_bot.strategy.rl_strategy import RLStrategy

app = typer.Typer(help="AI Trading Bot CLI")
console = Console()
logger = get_logger(__name__)


@app.callback()
def main(
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose output"),
    config: Path = typer.Option(None, "--config", "-c", help="Config file path"),
):
    """AI Trading Bot - Production-ready cryptocurrency trading system."""
    settings = get_settings()
    setup_logging(
        log_level="DEBUG" if verbose else settings.log_level,
        log_file=settings.log_file,
    )


@app.command()
def version():
    """Show version information."""
    console.print(Panel.fit(
        "[bold blue]AI Trading Bot[/bold blue]\n"
        "Version: 1.0.0\n"
        "Author: Quantitative Developer",
        title="About",
    ))


@app.command()
def config():
    """Show current configuration."""
    settings = get_settings()
    
    table = Table(title="Configuration")
    table.add_column("Setting", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Trading Mode", settings.trading_mode.value)
    table.add_row("Symbols", ", ".join(settings.symbol_list))
    table.add_row("Timeframe", settings.timeframe)
    table.add_row("Initial Capital", f"${settings.initial_capital:,.2f}")
    table.add_row("Max Position Size", f"{settings.max_position_size:.1%}")
    table.add_row("Risk Per Trade", f"{settings.risk_per_trade:.1%}")
    table.add_row("Model Type", settings.model_type.value)
    
    console.print(table)


@app.command()
def fetch_data(
    symbols: list[str] = typer.Option(None, "--symbol", "-s", help="Symbols to fetch"),
    days: int = typer.Option(30, "--days", "-d", help="Days of data to fetch"),
    output: Path = typer.Option("./data", "--output", "-o", help="Output directory"),
):
    """Fetch historical market data."""
    settings = get_settings()
    
    if not symbols:
        symbols = settings.symbol_list
    
    async def _fetch():
        async with DataFetcher(
            api_key=settings.binance_api_key,
            secret=settings.binance_secret_key,
            testnet=settings.binance_testnet,
        ) as fetcher:
            console.print(f"[yellow]Fetching data for {len(symbols)} symbols...[/yellow]")
            
            data = await fetcher.fetch_multiple_symbols(
                symbols=symbols,
                timeframe=settings.timeframe,
                lookback_days=days,
            )
            
            # Save data
            from trading_bot.data.storage import ParquetStorage
            storage = ParquetStorage(output)
            
            for symbol, df in data.items():
                storage.save_ohlcv(symbol, settings.timeframe, df)
                console.print(f"[green]✓[/green] Saved {symbol}: {len(df)} records")
    
    asyncio.run(_fetch())


@app.command()
def train(
    data_path: Path = typer.Option("./data", "--data", "-d", help="Path to training data"),
    model_type: str = typer.Option("PPO", "--model", "-m", help="Model type (PPO/SAC)"),
    timesteps: int = typer.Option(100000, "--timesteps", "-t", help="Training timesteps"),
    optimize: bool = typer.Option(True, "--optimize/--no-optimize", help="Optimize hyperparameters"),
):
    """Train RL model."""
    settings = get_settings()
    
    console.print(Panel.fit(
        f"[bold]Training Configuration[/bold]\n"
        f"Model: {model_type}\n"
        f"Timesteps: {timesteps:,}\n"
        f"Optimize: {optimize}",
        title="Training",
    ))
    
    # Load data
    from trading_bot.data.storage import ParquetStorage
    storage = ParquetStorage(data_path)
    
    # Get first symbol's data
    symbol = settings.symbol_list[0]
    df = storage.load_ohlcv(symbol, settings.timeframe)
    
    if df.empty:
        console.print(f"[red]No data found for {symbol}[/red]")
        raise typer.Exit(1)
    
    console.print(f"[green]Loaded {len(df)} records for {symbol}[/green]")
    
    # Train model
    from trading_bot.models.train import ModelTrainer
    from trading_bot.config import ModelType
    
    trainer = ModelTrainer(
        model_path=settings.model_path,
        n_trials=20 if optimize else 0,
    )
    
    model_type_enum = ModelType.PPO if model_type.upper() == "PPO" else ModelType.SAC
    
    with console.status("[bold green]Training model..."):
        agent = trainer.train(
            df=df,
            model_type=model_type_enum,
            total_timesteps=timesteps,
            optimize_hyperparams=optimize,
        )
    
    console.print("[bold green]✓ Training completed![/bold green]")


@app.command()
def backtest(
    model_path: Path = typer.Option(..., "--model", "-m", help="Path to trained model"),
    data_path: Path = typer.Option("./data", "--data", "-d", help="Path to test data"),
    output: Path = typer.Option("./backtest_results", "--output", "-o", help="Output directory"),
):
    """Run backtest on trained model."""
    settings = get_settings()
    
    console.print("[yellow]Running backtest...[/yellow]")
    
    # Load data
    from trading_bot.data.storage import ParquetStorage
    storage = ParquetStorage(data_path)
    
    symbol = settings.symbol_list[0]
    df = storage.load_ohlcv(symbol, settings.timeframe)
    
    if df.empty:
        console.print(f"[red]No data found for {symbol}[/red]")
        raise typer.Exit(1)
    
    # Run backtest
    from trading_bot.backtest.engine import BacktestEngine
    
    engine = BacktestEngine(
        initial_capital=settings.initial_capital,
        commission=0.001,
        slippage=0.0005,
    )
    
    result = engine.run_rl_backtest(df, model_path)
    
    # Print results
    table = Table(title="Backtest Results")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", style="magenta")
    
    table.add_row("Total Return", f"{result.total_return:.2%}")
    table.add_row("Sharpe Ratio", f"{result.sharpe_ratio:.2f}")
    table.add_row("Max Drawdown", f"{result.max_drawdown:.2%}")
    table.add_row("Win Rate", f"{result.win_rate:.1%}")
    table.add_row("Profit Factor", f"{result.profit_factor:.2f}")
    table.add_row("Number of Trades", str(result.num_trades))
    
    console.print(table)
    
    # Save report
    output.mkdir(parents=True, exist_ok=True)
    report_path = output / "backtest_report.txt"
    engine.generate_report(result, report_path)
    
    console.print(f"[green]Report saved to {report_path}[/green]")


@app.command()
def run(
    mode: str = typer.Option("paper", "--mode", help="Trading mode (paper/live)"),
    model_path: Path = typer.Option(None, "--model", "-m", help="Path to trained model"),
    interval: int = typer.Option(60, "--interval", "-i", help="Update interval in seconds"),
):
    """Run the trading bot."""
    settings = get_settings()
    
    if mode == "live" and settings.trading_mode.value == "paper":
        console.print("[red]Warning: Running in LIVE mode![/red]")
        if not typer.confirm("Are you sure you want to continue?"):
            raise typer.Exit()
    
    async def _run():
        # Initialize components
        alert_manager = AlertManager()
        circuit_breaker = CircuitBreaker()
        
        # Initialize strategy
        if model_path:
            strategy = RLStrategy(
                symbols=settings.symbol_list,
                model_path=model_path,
            )
        else:
            console.print("[red]No model specified[/red]")
            raise typer.Exit(1)
        
        # Initialize executor
        if mode == "paper":
            executor = PaperTradingExecutor(
                initial_capital=settings.initial_capital,
            )
            console.print("[blue]Running in PAPER trading mode[/blue]")
        else:
            executor = LiveExecutor(testnet=settings.binance_testnet)
            await executor.initialize()
            console.print("[red]Running in LIVE trading mode[/red]")
        
        # Send startup alert
        await alert_manager.send_alert(
            f"Trading bot started in {mode.upper()} mode",
            AlertLevel.INFO,
        )
        
        console.print("[bold green]Trading bot started![/bold green]")
        console.print(f"Monitoring: {', '.join(settings.symbol_list)}")
        
        try:
            while True:
                # Check circuit breakers
                should_stop, reason = circuit_breaker.check(
                    current_equity=executor.equity if hasattr(executor, 'equity') else settings.initial_capital,
                    daily_pnl=0,  # Calculate from trades
                    position_pnls={},
                    volatility=0.1,  # Get from data
                )
                
                if should_stop:
                    await alert_manager.send_circuit_breaker_alert(
                        reason,
                        executor.risk_manager.get_portfolio_metrics() if hasattr(executor, 'risk_manager') else {},
                    )
                    console.print(f"[red]Circuit breaker: {reason}[/red]")
                    break
                
                # Fetch latest data
                async with DataFetcher(
                    api_key=settings.binance_api_key,
                    secret=settings.binance_secret_key,
                    testnet=settings.binance_testnet,
                ) as fetcher:
                    data = {}
                    for symbol in settings.symbol_list:
                        try:
                            df = await fetcher.fetch_ohlcv(symbol, settings.timeframe, limit=100)
                            data[symbol] = df
                        except Exception as e:
                            logger.error(f"Failed to fetch {symbol}: {e}")
                
                # Generate signals
                signals = strategy.update(data)
                
                # Execute signals
                for signal in signals:
                    if mode == "paper":
                        executor.execute_signal(
                            signal,
                            signal.price,
                        )
                    else:
                        await executor.execute_signal(signal)
                    
                    await alert_manager.send_trade_alert(
                        symbol=signal.symbol,
                        side=signal.signal_type.value,
                        price=signal.price,
                        size=1.0,
                    )
                
                # Wait for next iteration
                await asyncio.sleep(interval)
                
        except KeyboardInterrupt:
            console.print("[yellow]Shutting down...[/yellow]")
        finally:
            if mode == "live":
                await executor.close()
            await alert_manager.close()
    
    asyncio.run(_run())


@app.command()
def dashboard(
    port: int = typer.Option(8501, "--port", "-p", help="Dashboard port"),
):
    """Launch monitoring dashboard."""
    import subprocess
    import sys
    
    console.print(f"[green]Starting dashboard on port {port}...[/green]")
    
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        "trading_bot/monitoring/dashboard.py",
        "--server.port", str(port),
    ])


if __name__ == "__main__":
    app()
