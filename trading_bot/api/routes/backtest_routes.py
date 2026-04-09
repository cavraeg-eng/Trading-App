"""Backtest API routes for running historical strategy simulations."""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from trading_bot.api.routes.market import (
    map_symbol_to_yf,
    calculate_rsi,
    calculate_macd,
    calculate_ema,
    calculate_bollinger_bands,
    calculate_atr,
)
from trading_bot.config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


# ── helpers ──────────────────────────────────────────────────────────────────

INTERVAL_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1h",
    "4h": "4h",
    "1d": "1d",
}


def map_timeframe(tf: str) -> str:
    """Map our timeframe strings to yfinance interval values."""
    return INTERVAL_MAP.get(tf, "1h")


def convert_symbol(symbol: str) -> str:
    """Convert a symbol like 'EUR/USD' to the yfinance ticker format.

    Re-uses the same mapping table that the market module uses.
    """
    return map_symbol_to_yf(symbol)


# ── request model ────────────────────────────────────────────────────────────

class BacktestRequest(BaseModel):
    symbol: str                    # e.g., "EUR/USD"
    start_date: str                # e.g., "2024-01-01"
    end_date: str                  # e.g., "2024-12-31"
    timeframe: str = "1h"
    initial_balance: float = 10000
    risk_percent: float = 2.0


# ── endpoint ─────────────────────────────────────────────────────────────────

@router.post("/run")
async def run_backtest(req: BacktestRequest):
    """Run a backtest simulation on historical data."""

    # 1. Fetch historical data ------------------------------------------------
    yf_symbol = convert_symbol(req.symbol)
    interval = map_timeframe(req.timeframe)

    try:
        data = yf.download(
            yf_symbol,
            start=req.start_date,
            end=req.end_date,
            interval=interval,
            progress=False,
        )
    except Exception as exc:
        logger.error(f"yfinance download failed for {req.symbol}: {exc}")
        return {"error": f"Failed to fetch data for {req.symbol}: {str(exc)}"}

    if data is None or data.empty or len(data) < 50:
        return {"error": f"Insufficient data for {req.symbol} ({len(data) if data is not None else 0} bars). Need at least 50."}

    # Normalise column names to title-case (yfinance default)
    # Handle potential MultiIndex columns from yfinance
    if isinstance(data.columns, pd.MultiIndex):
        data.columns = data.columns.get_level_values(0)
    data.columns = [str(c).strip().title() for c in data.columns]

    # Ensure required columns
    for col in ("Open", "High", "Low", "Close", "Volume"):
        if col not in data.columns:
            return {"error": f"Missing column '{col}' in downloaded data."}

    # 2. Walk through bars & generate signals ---------------------------------
    position = None        # None | "long" | "short"
    entry_price = 0.0
    position_size = 0.0
    equity = float(req.initial_balance)
    trades: List[dict] = []
    bar_equity: List[float] = []

    start_bar = 30  # warm-up for indicators

    for i in range(len(data)):
        if i < start_bar:
            bar_equity.append(equity)
            continue

        data_slice = data.iloc[: i + 1]
        close_series = data_slice["Close"]
        current_close = float(close_series.iloc[-1])

        # --- indicators (guard against NaN) ---
        rsi = calculate_rsi(close_series, 14)
        rsi = 0.0 if (rsi is None or (isinstance(rsi, float) and np.isnan(rsi))) else float(rsi)

        macd_line, signal_line, histogram = calculate_macd(close_series)
        macd_line = 0.0 if (macd_line is None or (isinstance(macd_line, float) and np.isnan(macd_line))) else float(macd_line)
        signal_line = 0.0 if (signal_line is None or (isinstance(signal_line, float) and np.isnan(signal_line))) else float(signal_line)
        histogram = 0.0 if (histogram is None or (isinstance(histogram, float) and np.isnan(histogram))) else float(histogram)

        ema20 = calculate_ema(close_series, 20)
        ema20 = current_close if (ema20 is None or (isinstance(ema20, float) and np.isnan(ema20))) else float(ema20)

        upper_bb, middle_bb, lower_bb = calculate_bollinger_bands(close_series)
        upper_bb = float(upper_bb) if upper_bb is not None and not (isinstance(upper_bb, float) and np.isnan(upper_bb)) else current_close
        lower_bb = float(lower_bb) if lower_bb is not None and not (isinstance(lower_bb, float) and np.isnan(lower_bb)) else current_close

        atr_val = calculate_atr(data_slice["High"], data_slice["Low"], close_series)
        atr_val = 0.0 if (atr_val is None or (isinstance(atr_val, float) and np.isnan(atr_val))) else float(atr_val)

        # --- signal logic (mirrors analyze_symbol) ---
        bullish_count = 0
        bearish_count = 0

        # RSI
        if rsi < 30:
            bullish_count += 1
        elif rsi > 70:
            bearish_count += 1

        # MACD
        if histogram > 0 and macd_line > signal_line:
            bullish_count += 1
        elif histogram < 0 and macd_line < signal_line:
            bearish_count += 1

        # EMA
        if current_close > ema20:
            bullish_count += 1
        else:
            bearish_count += 1

        # Bollinger Bands
        bb_range = upper_bb - lower_bb
        bb_pct = (current_close - lower_bb) / bb_range if bb_range > 0 else 0.5
        if bb_pct < 0.2:
            bullish_count += 1
        elif bb_pct > 0.8:
            bearish_count += 1

        # Determine signal
        if bullish_count >= 3:
            signal = "BUY"
        elif bearish_count >= 3:
            signal = "SELL"
        else:
            signal = "HOLD"

        # 3. Simulate trades --------------------------------------------------
        if signal == "BUY":
            if position == "short":
                # Close short
                pnl = (entry_price - current_close) * position_size
                equity += pnl
                trades.append({
                    "type": "close_short",
                    "entry": entry_price,
                    "exit": current_close,
                    "pnl": float(pnl),
                    "time": str(data.index[i]),
                })
                position = None
            if position is None:
                # Open long
                if atr_val > 0:
                    position_size = (equity * req.risk_percent / 100) / (atr_val * 2)
                else:
                    position_size = 0
                if position_size > 0:
                    entry_price = current_close
                    position = "long"

        elif signal == "SELL":
            if position == "long":
                # Close long
                pnl = (current_close - entry_price) * position_size
                equity += pnl
                trades.append({
                    "type": "close_long",
                    "entry": entry_price,
                    "exit": current_close,
                    "pnl": float(pnl),
                    "time": str(data.index[i]),
                })
                position = None
            if position is None:
                # Open short
                if atr_val > 0:
                    position_size = (equity * req.risk_percent / 100) / (atr_val * 2)
                else:
                    position_size = 0
                if position_size > 0:
                    entry_price = current_close
                    position = "short"

        bar_equity.append(equity)

    # Close any remaining open position at end of data
    if position is not None and len(data) > 0:
        last_close = float(data["Close"].iloc[-1])
        if position == "long":
            pnl = (last_close - entry_price) * position_size
        else:
            pnl = (entry_price - last_close) * position_size
        equity += pnl
        trades.append({
            "type": f"close_{position}",
            "entry": entry_price,
            "exit": last_close,
            "pnl": float(pnl),
            "time": str(data.index[-1]),
        })
        bar_equity[-1] = equity

    # 4. Calculate metrics ----------------------------------------------------
    initial_balance = float(req.initial_balance)
    final_equity = float(equity)
    total_return = (final_equity - initial_balance) / initial_balance if initial_balance > 0 else 0

    # Sharpe ratio (annualized)
    equity_series = pd.Series(bar_equity, dtype=float)
    returns = equity_series.pct_change().dropna()
    if len(returns) > 1 and returns.std() > 0:
        sharpe = float((returns.mean() / returns.std()) * np.sqrt(252))
    else:
        sharpe = 0.0

    # Max drawdown
    rolling_max = equity_series.cummax()
    drawdown = (equity_series - rolling_max) / rolling_max.replace(0, np.nan)
    drawdown = drawdown.fillna(0.0)
    max_drawdown = float(abs(drawdown.min())) if len(drawdown) > 0 and np.isfinite(drawdown.min()) else 0.0

    # Win rate
    winning = [t for t in trades if t["pnl"] > 0]
    win_rate = len(winning) / len(trades) if trades else 0.0

    # Profit factor
    gross_profit = sum(t["pnl"] for t in trades if t["pnl"] > 0)
    gross_loss = abs(sum(t["pnl"] for t in trades if t["pnl"] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0.0

    # 5. Build equity curve (sampled) -----------------------------------------
    step = max(1, len(bar_equity) // 100)
    equity_curve = [
        {"time": str(data.index[i]), "value": round(float(eq), 2)}
        for i, eq in enumerate(bar_equity)
        if i % step == 0
    ]

    # 6. Return response matching BacktestResult interface --------------------
    return {
        "totalReturn": round(total_return * 100, 2),
        "sharpeRatio": round(sharpe, 2),
        "maxDrawdown": round(max_drawdown * 100, 2),
        "winRate": round(win_rate * 100, 1),
        "profitFactor": round(profit_factor, 2),
        "numTrades": len(trades),
        "equityCurve": equity_curve,
    }
