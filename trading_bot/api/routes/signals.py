"""Signal routes for the trading bot API."""

import random
import time
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Query

from trading_bot.api.models import SignalBreakdown, SignalDirection, SignalStatus

router = APIRouter(prefix="/api/signals", tags=["signals"])

# Timeframe to seconds mapping for signal status computation
TIMEFRAME_SECONDS = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "4h": 14400,
    "1d": 86400,
}

# Typical base prices for common forex/crypto symbols (for mock entry/SL/TP)
SYMBOL_BASE_PRICES = {
    "EUR/USD": 1.0850, "GBP/USD": 1.2650, "USD/JPY": 155.50,
    "USD/CHF": 0.8850, "AUD/USD": 0.6550, "USD/CAD": 1.3650,
    "NZD/USD": 0.6050, "EUR/GBP": 0.8550, "EUR/JPY": 168.50,
    "GBP/JPY": 196.50, "BTC/USD": 68500.0, "ETH/USD": 3500.0,
    "XAU/USD": 2350.0, "US500": 5250.0,
}


def get_base_price(symbol: str) -> float:
    """Get a realistic base price for the symbol."""
    return SYMBOL_BASE_PRICES.get(symbol, 1.0 + random.random())


def compute_signal_status(
    signal_timestamp: float,
    current_price: float,
    entry_min: float,
    entry_max: float,
    stop_loss: float,
    timeframe: str,
) -> SignalStatus:
    """Compute signal status based on age, price position, and stop loss.

    Returns one of: OPTIMAL_ENTRY, VALID, ABOUT_TO_EXPIRE, EXPIRED.
    """
    candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    signal_age_seconds = time.time() - signal_timestamp
    signal_age_candles = signal_age_seconds / candle_seconds

    price_in_zone = entry_min <= current_price <= entry_max

    # Check if price has moved past stop loss
    if current_price <= stop_loss or current_price >= stop_loss:
        # Need directional check: if SL < entry zone → long trade; SL > entry zone → short trade
        if stop_loss < entry_min and current_price < stop_loss:
            return SignalStatus.EXPIRED
        if stop_loss > entry_max and current_price > stop_loss:
            return SignalStatus.EXPIRED

    if signal_age_candles > 5:
        return SignalStatus.EXPIRED

    if 4 <= signal_age_candles <= 5:
        return SignalStatus.ABOUT_TO_EXPIRE

    if price_in_zone and signal_age_candles < 2:
        return SignalStatus.OPTIMAL_ENTRY

    if price_in_zone and signal_age_candles < 5:
        return SignalStatus.VALID

    # Price outside zone but signal not expired yet
    if signal_age_candles < 5:
        return SignalStatus.VALID

    return SignalStatus.EXPIRED


def generate_indicator_contributions(direction: SignalDirection) -> List[dict]:
    """Generate realistic indicator contributions for a signal."""
    indicators = [
        {"name": "RSI", "weight": 0.20, "bullish_threshold": 50, "bearish_threshold": 50},
        {"name": "MACD", "weight": 0.20, "bullish_threshold": 0, "bearish_threshold": 0},
        {"name": "EMA_9", "weight": 0.15, "bullish_threshold": 50, "bearish_threshold": 50},
        {"name": "BB", "weight": 0.15, "bullish_threshold": 0.5, "bearish_threshold": 0.5},
        {"name": "ATR", "weight": 0.10, "bullish_threshold": 1.0, "bearish_threshold": 1.0},
        {"name": "Volume", "weight": 0.10, "bullish_threshold": 1.5, "bearish_threshold": 1.5},
        {"name": "Stoch", "weight": 0.10, "bullish_threshold": 50, "bearish_threshold": 50},
    ]
    
    contributions = []
    total_contribution = 0.0
    
    for ind in indicators:
        # Generate realistic values based on direction
        if direction == SignalDirection.BUY:
            if ind["name"] == "RSI":
                value = random.uniform(45, 75)
                signal = "bullish" if value > 50 else "neutral"
            elif ind["name"] == "MACD":
                value = random.uniform(-0.1, 0.5)
                signal = "bullish" if value > 0 else "bearish"
            elif ind["name"] == "BB":
                value = random.uniform(0.3, 0.8)
                signal = "bullish" if value > 0.5 else "neutral"
            elif ind["name"] == "Stoch":
                value = random.uniform(40, 80)
                signal = "bullish" if value > 50 else "neutral"
            else:
                value = random.uniform(0.8, 2.0)
                signal = "bullish"
        elif direction == SignalDirection.SELL:
            if ind["name"] == "RSI":
                value = random.uniform(25, 55)
                signal = "bearish" if value < 50 else "neutral"
            elif ind["name"] == "MACD":
                value = random.uniform(-0.5, 0.1)
                signal = "bearish" if value < 0 else "bullish"
            elif ind["name"] == "BB":
                value = random.uniform(0.2, 0.6)
                signal = "bearish" if value < 0.5 else "neutral"
            elif ind["name"] == "Stoch":
                value = random.uniform(20, 60)
                signal = "bearish" if value < 50 else "neutral"
            else:
                value = random.uniform(0.5, 1.5)
                signal = "bearish"
        else:
            value = random.uniform(0.4, 0.6)
            signal = "neutral"
        
        # Calculate contribution based on alignment with signal
        if signal == "bullish" and direction == SignalDirection.BUY:
            contribution = ind["weight"] * random.uniform(0.8, 1.0)
        elif signal == "bearish" and direction == SignalDirection.SELL:
            contribution = ind["weight"] * random.uniform(0.8, 1.0)
        elif signal == "neutral":
            contribution = ind["weight"] * random.uniform(0.3, 0.6)
        else:
            contribution = ind["weight"] * random.uniform(0.1, 0.3)
        
        total_contribution += contribution
        
        contributions.append({
            "name": ind["name"],
            "value": round(value, 4),
            "signal": signal,
            "weight": ind["weight"],
            "contribution": round(contribution, 4)
        })
    
    return contributions


@router.get("/current")
async def get_current_signals(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(10, ge=1, le=100)
) -> List[dict]:
    """Get current trading signals with full indicator breakdown."""
    symbols = [symbol] if symbol else ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]
    
    signals = []
    for sym in symbols[:limit]:
        # Randomly determine signal direction
        rand = random.random()
        if rand < 0.4:
            direction = SignalDirection.BUY
            confidence = int(random.uniform(65, 95))  # Returns 0-100 integer percentage, consistent with market.py
        elif rand < 0.8:
            direction = SignalDirection.SELL
            confidence = int(random.uniform(65, 95))  # Returns 0-100 integer percentage, consistent with market.py
        else:
            direction = SignalDirection.HOLD
            confidence = int(random.uniform(40, 60))  # Returns 0-100 integer percentage, consistent with market.py
        
        indicators = generate_indicator_contributions(direction)
        signal_strength = int(sum(ind["contribution"] for ind in indicators) * 100)  # Returns 0-100 integer percentage
        
        signal = {
            "symbol": sym,
            "direction": direction.value,
            "confidence": confidence,
            "indicators": indicators,
            "signal_strength": signal_strength,
            "pattern_accuracy": int(random.uniform(70, 90)) if direction != SignalDirection.HOLD else None,  # Returns 0-100 integer percentage
            "timestamp": datetime.now().isoformat()
        }
        signals.append(signal)
    
    return signals


@router.get("/breakdown/{symbol:path}")
async def get_signal_breakdown(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
) -> dict:
    """Get detailed signal breakdown for a specific symbol."""
    rand = random.random()
    if rand < 0.4:
        direction = SignalDirection.BUY
    elif rand < 0.8:
        direction = SignalDirection.SELL
    else:
        direction = SignalDirection.HOLD

    indicators = generate_indicator_contributions(direction)
    signal_strength = int(sum(ind["contribution"] for ind in indicators) * 100)

    # --- Compute realistic entry / SL / TP values ---
    base_price = get_base_price(symbol)
    current_price = base_price * (1 + random.uniform(-0.002, 0.002))

    entry_half = current_price * 0.0015  # ±0.15% of price
    entry_min = round(current_price - entry_half, 5)
    entry_max = round(current_price + entry_half, 5)

    if direction == SignalDirection.BUY:
        stop_loss = round(current_price * (1 - 0.0075), 5)
        take_profit1 = round(current_price * (1 + 0.015), 5)
        take_profit2 = round(current_price * (1 + 0.030), 5)
        take_profit3 = round(current_price * (1 + 0.045), 5)
    elif direction == SignalDirection.SELL:
        stop_loss = round(current_price * (1 + 0.0075), 5)
        take_profit1 = round(current_price * (1 - 0.015), 5)
        take_profit2 = round(current_price * (1 - 0.030), 5)
        take_profit3 = round(current_price * (1 - 0.045), 5)
    else:
        # HOLD — still provide levels (long-biased defaults)
        stop_loss = round(current_price * (1 - 0.0075), 5)
        take_profit1 = round(current_price * (1 + 0.015), 5)
        take_profit2 = round(current_price * (1 + 0.030), 5)
        take_profit3 = round(current_price * (1 + 0.045), 5)

    # Signal was generated "now" (mock), so status will be OPTIMAL_ENTRY
    signal_ts = time.time() - random.uniform(0, 60)  # slight jitter
    candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    expires_at_ts = signal_ts + (5 * candle_seconds)
    expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)

    signal_status = compute_signal_status(
        signal_timestamp=signal_ts,
        current_price=current_price,
        entry_min=entry_min,
        entry_max=entry_max,
        stop_loss=stop_loss,
        timeframe=timeframe,
    )

    return {
        "symbol": symbol,
        "direction": direction.value,
        "confidence": int(random.uniform(65, 95)),
        "indicators": indicators,
        "signal_strength": signal_strength,
        "pattern_accuracy": int(random.uniform(70, 90)) if direction != SignalDirection.HOLD else None,
        "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        "signal_status": signal_status.value,
        "expires_at": expires_at.isoformat(),
        "entry_min": entry_min,
        "entry_max": entry_max,
        "stop_loss": stop_loss,
        "take_profit1": take_profit1,
        "take_profit2": take_profit2,
        "take_profit3": take_profit3,
    }


@router.get("/history")
async def get_signal_history(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    days: int = Query(7, ge=1, le=90)
) -> List[dict]:
    """Get historical signal data."""
    symbols = [symbol] if symbol else ["EUR/USD", "GBP/USD", "USD/JPY"]
    history = []
    
    for sym in symbols:
        for _ in range(days * 3):  # Multiple signals per day
            rand = random.random()
            if rand < 0.35:
                direction = SignalDirection.BUY
            elif rand < 0.70:
                direction = SignalDirection.SELL
            else:
                direction = SignalDirection.HOLD
            
            history.append({
                "symbol": sym,
                "direction": direction.value,
                "confidence": int(random.uniform(60, 95)),  # Returns 0-100 integer percentage, consistent with market.py
                "price": round(random.uniform(1.0, 50000.0), 4),
                "timestamp": datetime.now().isoformat()
            })
    
    return sorted(history, key=lambda x: x["timestamp"], reverse=True)[:100]
