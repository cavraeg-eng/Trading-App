"""Signal routes for the trading bot API."""

import random
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

from fastapi import APIRouter, Query

from trading_bot.api.models import SignalBreakdown, SignalDirection, SignalStatus
from trading_bot.api.routes.market import (
    get_shared_ohlcv,
    analyze_symbol,
    compute_ai_score,
    get_shared_ohlcv_with_metadata,
)
from trading_bot.config import get_logger
from trading_bot.persistence import repositories as repo

logger = get_logger(__name__)

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

# Typical base prices for common forex/crypto symbols (fallback when live data unavailable)
SYMBOL_BASE_PRICES = {
    "EUR/USD": 1.1700,      "GBP/USD": 1.3400,     "USD/JPY": 158.50,
    "USD/CHF": 0.8450,      "AUD/USD": 0.6400,     "USD/CAD": 1.3850,
    "NZD/USD": 0.5950,      "EUR/GBP": 0.8730,     "EUR/JPY": 185.50,
    "GBP/JPY": 212.50,      "BTC/USD": 71300.0,    "ETH/USD": 2230.0,
    "XAU/USD": 4840.0,      "XAG/USD": 58.50,      "US500": 6620.0,
    "US30": 45200.0,        "US100": 21500.0,
}

# Cache for live prices to avoid hammering yfinance on every signal request
# (Now uses shared OHLCV cache from market.py with its own 5-second TTL)


def get_base_price(symbol: str, timeframe: str = "1h", trade_style: str = "swing") -> Tuple[float, str]:
    """Get current price using shared OHLCV cache, falling back to hardcoded prices.

    Returns (price, source) where source is 'live' or 'mock'.
    """
    try:
        df = get_shared_ohlcv(symbol, timeframe, trade_style=trade_style)
        if df is not None and len(df) > 0:
            live_price = float(df["close"].iloc[-1])
            if live_price > 0:
                return live_price, "live"
    except Exception as e:
        logger.warning(f"Failed to fetch live price for {symbol}: {e}")

    # Fallback to hardcoded prices
    logger.info(f"Using fallback price for {symbol}")
    return SYMBOL_BASE_PRICES.get(symbol, 1.0 + random.random()), "mock"


def get_base_price_metadata(symbol: str, timeframe: str = "1h", trade_style: str = "swing") -> dict:
    """Get source metadata for the current symbol price."""
    try:
        resolved_timeframe = "1m" if trade_style == "scalp" and timeframe not in ("1m", "5m") else timeframe
        _, metadata = get_shared_ohlcv_with_metadata(symbol, resolved_timeframe, trade_style=trade_style)
        return metadata
    except Exception:
        return {
            "sourceName": "mock",
            "sourceType": "mock",
            "priceSource": "mock",
            "isFallback": True,
            "freshnessSeconds": None,
            "qualityFlags": ["mock_data"],
            "lastBarTimestamp": None,
            "marketStatus": "stale",
        }


# ---------------------------------------------------------------------------
# Signal persistence dataclass & module-level stores
# ---------------------------------------------------------------------------

@dataclass
class ActiveSignal:
    """Tracks a persistent signal until it's resolved."""
    symbol: str
    direction: str  # "BUY", "SELL", "HOLD"
    confidence: int
    entry_min: float
    entry_max: float
    entry_price: float  # The base price when the signal was generated
    stop_loss: float
    take_profit1: float
    take_profit2: float
    take_profit3: float
    created_at: float  # Unix timestamp
    timeframe: str
    indicators: list
    signal_strength: int
    price_source: str = "mock"  # "live" or "mock"
    pattern_accuracy: Optional[int] = None
    resolved: bool = False
    resolved_reason: Optional[str] = None  # "TP_HIT", "SL_HIT", "EXPIRED", "COOLDOWN"
    resolved_at: Optional[float] = None


# Module-level stores
_active_signals: Dict[str, ActiveSignal] = {}  # signal_key -> active signal
_cooldown_until: Dict[str, float] = {}  # signal_key -> timestamp when cooldown ends
_signal_lock = threading.RLock()

# Cooldown = 1 candle after a signal resolves
COOLDOWN_CANDLES = 1
# Signal expires after 3 candles with no execution
MAX_SIGNAL_AGE_CANDLES = 3
# Maximum signal age before automatic cleanup (24 hours)
_SIGNAL_MAX_AGE = 86400


# ---------------------------------------------------------------------------
# Signal lifecycle manager
# ---------------------------------------------------------------------------

def _cleanup_stale_signals():
    """Remove signals older than 24 hours to prevent memory leak."""
    now = time.time()
    with _signal_lock:
        stale_keys = [
            k for k, v in _active_signals.items()
            if now - v.created_at > _SIGNAL_MAX_AGE
        ]
        for k in stale_keys:
            del _active_signals[k]
            _cooldown_until.pop(k, None)


def _signal_key(symbol: str, timeframe: str, trade_style: str) -> str:
    return f"{symbol}|{timeframe}|{trade_style}"


def _signal_id(symbol: str, timeframe: str, trade_style: str, created_at: float) -> str:
    return f"{symbol}|{timeframe}|{trade_style}|{int(created_at)}"


def _signal_direction(value: object) -> str:
    normalized = str(value or "").upper()
    if normalized in {"BUY", "SELL"}:
        return normalized
    return "HOLD"


def _is_chartable_signal(direction: object, confidence: object, status: object) -> bool:
    if _signal_direction(direction) == "HOLD":
        return False
    try:
        numeric_confidence = float(confidence)
    except (TypeError, ValueError):
        numeric_confidence = 0.0
    if numeric_confidence < 50:
        return False
    return str(status or "").upper() != SignalStatus.EXPIRED.value


def _preferred_chart_signal(
    symbol: str,
    timeframe: str,
    trade_style: str,
    primary: dict,
) -> dict:
    if _is_chartable_signal(
        primary.get("direction"),
        primary.get("confidence"),
        primary.get("signal_status"),
    ):
        primary["display_source"] = "primary"
        return primary

    candidates = [
        (timeframe, "swing"),
        ("1h", "swing"),
        ("1h", "scalp"),
        ("15m", "swing"),
    ]
    seen = {(timeframe, trade_style)}
    for candidate_timeframe, candidate_style in candidates:
        if (candidate_timeframe, candidate_style) in seen:
            continue
        seen.add((candidate_timeframe, candidate_style))
        analysis = analyze_symbol(symbol, candidate_timeframe, trade_style=candidate_style)
        if not analysis:
            continue
        direction = _signal_direction({"buy": "BUY", "sell": "SELL"}.get(analysis.get("signal")))
        confidence = int(analysis.get("confidence", 0) or 0)
        if not _is_chartable_signal(direction, confidence, SignalStatus.VALID.value):
            continue
        now = time.time()
        response = _build_response(
            ActiveSignal(
                symbol=symbol,
                direction=direction,
                confidence=confidence,
                entry_min=analysis["entryRange"]["min"],
                entry_max=analysis["entryRange"]["max"],
                entry_price=analysis["currentPrice"],
                stop_loss=analysis["stopLoss"],
                take_profit1=analysis["takeProfit1"],
                take_profit2=analysis["takeProfit2"],
                take_profit3=analysis["takeProfit3"],
                created_at=now,
                timeframe=candidate_timeframe,
                indicators=[
                    {
                        "name": ind["name"],
                        "signal": ind["signal"],
                        "contribution": 0.15 if ind["signal"] == "bullish" else (-0.15 if ind["signal"] == "bearish" else 0.0),
                        "value": ind["value"],
                    }
                    for ind in analysis.get("indicators", [])
                ],
                signal_strength=0,
                price_source=candidate_style,
                pattern_accuracy=analysis.get("patternAccuracy"),
            ),
            SignalStatus.VALID,
            datetime.fromtimestamp(now + (3 * TIMEFRAME_SECONDS.get(candidate_timeframe, 3600)), tz=timezone.utc),
        )
        response["timeframe"] = candidate_timeframe
        response["trade_style"] = candidate_style
        response["display_source"] = "fallback"
        response["fallback_reason"] = (
            f"Primary {timeframe} {trade_style} signal is HOLD; showing nearest actionable "
            f"{candidate_timeframe} {candidate_style} setup."
        )
        return response

    primary["display_source"] = "primary"
    return primary


def _persist_signal_outcome(sig: ActiveSignal, reason: str, exit_price: Optional[float]) -> None:
    resolved_at = time.time()
    final_price = float(exit_price if exit_price is not None else sig.entry_price)
    price_delta = final_price - float(sig.entry_price)

    if reason == "TP_HIT":
        direction_correct = 1
    elif reason == "SL_HIT":
        direction_correct = 0
    elif sig.direction == "BUY":
        direction_correct = 1 if price_delta > 0 else 0
    elif sig.direction == "SELL":
        direction_correct = 1 if price_delta < 0 else 0
    else:
        tolerance = max(abs(float(sig.entry_price)) * 0.0002, 1e-9)
        direction_correct = 1 if abs(price_delta) <= tolerance else 0

    if sig.direction == "BUY":
        pnl_pips = price_delta
    elif sig.direction == "SELL":
        pnl_pips = -price_delta
    else:
        pnl_pips = -abs(price_delta)

    try:
        repo.insert_signal_outcome({
            "signal_id": _signal_id(sig.symbol, sig.timeframe, sig.price_source, sig.created_at),
            "resolved_reason": reason,
            "resolved_at": resolved_at,
            "exit_price": final_price,
            "pnl_pips": float(pnl_pips),
            "direction_correct": int(direction_correct),
        })
    except Exception as exc:
        logger.warning(f"Failed to persist signal outcome for {sig.symbol}: {exc}")


def _resolve_signal(symbol: str, reason: str, timeframe: str, trade_style: str, exit_price: Optional[float] = None) -> None:
    """Mark a signal as resolved and start cooldown (only for executed signals)."""
    key = _signal_key(symbol, timeframe, trade_style)
    with _signal_lock:
        sig = _active_signals.get(key)
        if sig and not sig.resolved:
            sig.resolved = True
            sig.resolved_reason = reason
            sig.resolved_at = time.time()
            _persist_signal_outcome(sig, reason, exit_price)
        # Cooldown only applies after execution (TP/SL hit), NOT after natural expiration
        if reason in ("TP_HIT", "SL_HIT"):
            candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
            _cooldown_until[key] = time.time() + COOLDOWN_CANDLES * candle_seconds


def _build_response(sig: ActiveSignal, signal_status: SignalStatus,
                    expires_at: datetime, cooldown_remaining: float = 0) -> dict:
    """Build the breakdown response dict from an ActiveSignal."""
    now = time.time()
    metadata = get_base_price_metadata(sig.symbol, sig.timeframe, trade_style=sig.price_source)
    market_price, market_source = get_base_price(sig.symbol, sig.timeframe, trade_style=sig.price_source)
    effective_status = SignalStatus.VALID if sig.direction == "HOLD" else signal_status
    return {
        "symbol": sig.symbol,
        "direction": sig.direction,
        "confidence": sig.confidence,
        "indicators": sig.indicators,
        "signal_strength": sig.signal_strength,
        "pattern_accuracy": sig.pattern_accuracy,
        "timestamp": datetime.fromtimestamp(sig.created_at, tz=timezone.utc).isoformat(),
        "signal_status": effective_status.value,
        "expires_at": expires_at.isoformat(),
        "entry_min": sig.entry_min,
        "entry_max": sig.entry_max,
        "stop_loss": sig.stop_loss,
        "take_profit1": sig.take_profit1,
        "take_profit2": sig.take_profit2,
        "take_profit3": sig.take_profit3,
        # New persistence fields
        "signal_id": _signal_id(sig.symbol, sig.timeframe, sig.price_source, sig.created_at),
        "cooldown_remaining": max(0, int(cooldown_remaining)),
        "signal_age_seconds": int(now - sig.created_at),
        "resolved_reason": sig.resolved_reason,
        "price_source": market_source,
        "trade_style": sig.price_source,
        "current_price": market_price,
        "source_metadata": metadata,
        "prediction_source": "heuristic",
        "anchorPerformance": repo.get_signal_outcome_summary(
            symbol=sig.symbol,
            timeframe=sig.timeframe,
            direction=sig.direction,
            limit=100,
        ),
    }


def get_or_create_signal(symbol: str, timeframe: str, trade_style: str = "swing") -> dict:
    """Return an existing active signal if still valid, or create a new one.

    Lifecycle:
    1. Check if there's an active signal for this symbol.
    2. If active: check if it should expire / TP / SL hit.
       - If still valid, return the existing signal.
       - If expired/resolved, mark as resolved, start cooldown.
    3. If no active signal: check if in cooldown period.
       - If in cooldown, return a HOLD signal with "cooling down" status.
    4. If no cooldown, generate a new signal and store it.
    """
    now = time.time()
    candle_seconds = TIMEFRAME_SECONDS.get(timeframe, 3600)
    key = _signal_key(symbol, timeframe, trade_style)

    # ---- 1 & 2: Existing active signal? ----------------------------------
    with _signal_lock:
        sig = _active_signals.get(key)
    if sig and not sig.resolved:
        # Fetch current price from live data
        base_price, _src = get_base_price(symbol, timeframe, trade_style=trade_style)
        current_price = base_price  # Use actual price, no random noise

        # Check if price has diverged too far from signal's entry price
        price_divergence = abs(current_price - sig.entry_price) / sig.entry_price
        if price_divergence > 0.02:  # 2% divergence threshold — regenerate signal sooner
            logger.warning(f"Signal for {symbol} diverged {price_divergence:.1%} from current price, regenerating")
            _resolve_signal(symbol, "DIVERGED", timeframe, trade_style, current_price)
            with _signal_lock:
                _active_signals.pop(key, None)
            # Fall through to generate new signal
        else:
            signal_age_candles = (now - sig.created_at) / candle_seconds

            # Check TP / SL hits using real price comparison
            resolved_reason: Optional[str] = None
            if sig.direction == "BUY":
                if current_price >= sig.take_profit1:
                    resolved_reason = "TP_HIT"
                elif current_price <= sig.stop_loss:
                    resolved_reason = "SL_HIT"
            elif sig.direction == "SELL":
                if current_price <= sig.take_profit1:
                    resolved_reason = "TP_HIT"
                elif current_price >= sig.stop_loss:
                    resolved_reason = "SL_HIT"

            # Compute status via existing helper
            status = compute_signal_status(
                signal_timestamp=sig.created_at,
                current_price=current_price,
                entry_min=sig.entry_min,
                entry_max=sig.entry_max,
                stop_loss=sig.stop_loss,
                timeframe=timeframe,
            )

            if status == SignalStatus.EXPIRED:
                resolved_reason = resolved_reason or "EXPIRED"

            if resolved_reason:
                _resolve_signal(symbol, resolved_reason, timeframe, trade_style, current_price)
                if resolved_reason == "EXPIRED":
                    # Expired signals skip cooldown — delete and fall through
                    # to generate a fresh signal immediately
                    with _signal_lock:
                        _active_signals.pop(key, None)
                        _cooldown_until.pop(key, None)
                    # Fall through to section 4 (new signal generation)
                # For TP_HIT / SL_HIT, fall through to cooldown logic below
            else:
                # Refresh price levels only after the entry window has aged a bit;
                # otherwise the system keeps moving anchors away from the original thesis.
                fresh_analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
                if fresh_analysis is not None and signal_age_candles >= 1.0:
                    # Update entry/SL/TP to track current price
                    sig.entry_min = fresh_analysis["entryRange"]["min"]
                    sig.entry_max = fresh_analysis["entryRange"]["max"]
                    sig.stop_loss = fresh_analysis["stopLoss"]
                    sig.take_profit1 = fresh_analysis["takeProfit1"]
                    sig.take_profit2 = fresh_analysis["takeProfit2"]
                    sig.take_profit3 = fresh_analysis["takeProfit3"]
                    sig.entry_price = fresh_analysis["currentPrice"]
                    sig.confidence = fresh_analysis["confidence"]
                    sig.pattern_accuracy = fresh_analysis.get("patternAccuracy")

                    # If the fresh analysis direction DISAGREES with the stored signal,
                    # invalidate the old signal and generate a new one
                    signal_map = {"buy": "BUY", "sell": "SELL"}
                    fresh_direction = signal_map.get(fresh_analysis["signal"], "HOLD")
                    if fresh_direction != sig.direction:
                        # Direction flipped — delete old signal and fall through to create new one
                        _resolve_signal(symbol, "REPLACED", timeframe, trade_style, fresh_analysis["currentPrice"])
                        with _signal_lock:
                            _active_signals.pop(key, None)
                            _cooldown_until.pop(key, None)
                    else:
                        # Same direction — return with updated levels
                        # Also refresh indicators from fresh analysis
                        if "indicators" in fresh_analysis:
                            sig.indicators = []
                            for ind in fresh_analysis["indicators"]:
                                contribution = 0.15 if ind["signal"] == "bullish" else (-0.15 if ind["signal"] == "bearish" else 0.0)
                                sig.indicators.append({
                                    "name": ind["name"],
                                    "signal": ind["signal"],
                                    "contribution": contribution,
                                    "value": ind["value"]
                                })
                expires_at_ts = sig.created_at + (MAX_SIGNAL_AGE_CANDLES * candle_seconds)
                expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)
                return _build_response(sig, status, expires_at)

    # ---- 3: Cooldown check -----------------------------------------------
    with _signal_lock:
        cooldown_end = _cooldown_until.get(key, 0)
    if now < cooldown_end:
        remaining = cooldown_end - now
        # Return a HOLD / EXPIRED placeholder during cooldown
        with _signal_lock:
            hold_sig = _active_signals.get(key)
        if hold_sig:
            expires_at_ts = hold_sig.created_at + (MAX_SIGNAL_AGE_CANDLES * candle_seconds)
            expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)
            return _build_response(hold_sig, SignalStatus.EXPIRED, expires_at, cooldown_remaining=remaining)
        # No previous signal info — build a minimal HOLD response
        return {
            "symbol": symbol,
            "direction": "HOLD",
            "confidence": 0,
            "indicators": [],
            "signal_strength": 0,
            "pattern_accuracy": None,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
            "signal_status": SignalStatus.EXPIRED.value,
            "expires_at": datetime.now(tz=timezone.utc).isoformat(),
            "entry_min": 0,
            "entry_max": 0,
            "stop_loss": 0,
            "take_profit1": 0,
            "take_profit2": 0,
            "take_profit3": 0,
            "signal_id": f"{key}|cooldown",
            "cooldown_remaining": max(0, int(remaining)),
            "signal_age_seconds": 0,
            "resolved_reason": "COOLDOWN",
            "price_source": "mock",  # no active signal during cooldown
            "source_metadata": get_base_price_metadata(symbol, timeframe, trade_style=trade_style),
        }

    # ---- 4: Generate a brand-new signal -----------------------------------
    # Use real technical analysis instead of random generation
    analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)

    base_price, price_source = get_base_price(symbol, timeframe, trade_style=trade_style)
    current_price = base_price

    if analysis is not None:
        # Map analysis signal to SignalDirection
        signal_map = {"buy": SignalDirection.BUY, "sell": SignalDirection.SELL}
        direction = signal_map.get(analysis["signal"], SignalDirection.HOLD)
        confidence = analysis["confidence"]

        # Use real ATR-based levels from analysis
        entry_min = analysis["entryRange"]["min"]
        entry_max = analysis["entryRange"]["max"]
        stop_loss = analysis["stopLoss"]
        take_profit1 = analysis["takeProfit1"]
        take_profit2 = analysis["takeProfit2"]
        take_profit3 = analysis["takeProfit3"]

        # Use real indicator data when available
        if "indicators" in analysis:
            indicators = []
            for ind in analysis["indicators"]:
                contribution = 0.15 if ind["signal"] == "bullish" else (-0.15 if ind["signal"] == "bearish" else 0.0)
                indicators.append({
                    "name": ind["name"],
                    "signal": ind["signal"],
                    "contribution": contribution,
                    "value": ind["value"]
                })
        else:
            indicators = generate_indicator_contributions(direction)
    else:
        # Fallback to HOLD if analysis unavailable
        direction = SignalDirection.HOLD
        confidence = 50
        # Use base_price for fallback levels
        entry_min = base_price * 0.999
        entry_max = base_price * 1.001
        stop_loss = base_price * 0.99
        take_profit1 = base_price * 1.01
        take_profit2 = base_price * 1.02
        take_profit3 = base_price * 1.03
        indicators = generate_indicator_contributions(direction)

    signal_strength = int(sum(ind["contribution"] for ind in indicators) * 100)
    # pattern_accuracy is now computed from stored outcomes, not randomized
    pattern_accuracy = analysis.get("patternAccuracy") if analysis is not None else None

    new_sig = ActiveSignal(
        symbol=symbol,
        direction=direction.value,
        confidence=confidence,
        entry_min=entry_min,
        entry_max=entry_max,
        entry_price=current_price,
        stop_loss=stop_loss,
        take_profit1=take_profit1,
        take_profit2=take_profit2,
        take_profit3=take_profit3,
        created_at=now,
        timeframe=timeframe,
        indicators=indicators,
        signal_strength=signal_strength,
        price_source=trade_style,
        pattern_accuracy=pattern_accuracy,
    )
    with _signal_lock:
        _active_signals[key] = new_sig
        # Clear any lingering cooldown
        _cooldown_until.pop(key, None)

    # Persist signal prediction for tracking
    try:
        signal_id = _signal_id(symbol, timeframe, trade_style, now)
        repo.insert_signal_prediction({
            "signal_id": signal_id,
            "symbol": symbol,
            "direction": direction.value,
            "confidence": confidence,
            "entry_min": entry_min,
            "entry_max": entry_max,
            "stop_loss": stop_loss,
            "take_profit1": take_profit1,
            "take_profit2": take_profit2,
            "take_profit3": take_profit3,
            "timeframe": timeframe,
            "trade_style": trade_style,
            "source": "heuristic",
            "price_source": trade_style,
            "created_at": now,
        })
    except Exception as e:
        logger.warning(f"Failed to persist signal prediction: {e}")

    expires_at_ts = now + (MAX_SIGNAL_AGE_CANDLES * candle_seconds)
    expires_at = datetime.fromtimestamp(expires_at_ts, tz=timezone.utc)

    status = compute_signal_status(
        signal_timestamp=now,
        current_price=current_price,
        entry_min=entry_min,
        entry_max=entry_max,
        stop_loss=stop_loss,
        timeframe=timeframe,
    )

    return _build_response(new_sig, status, expires_at)


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

    # For BUY signals: SL is below entry, price hitting SL means it dropped
    if stop_loss < entry_min and current_price <= stop_loss:
        return SignalStatus.EXPIRED
    # For SELL signals: SL is above entry, price hitting SL means it rose
    if stop_loss > entry_max and current_price >= stop_loss:
        return SignalStatus.EXPIRED

    if signal_age_candles > 3:
        return SignalStatus.EXPIRED

    if 2.5 <= signal_age_candles <= 3:
        return SignalStatus.ABOUT_TO_EXPIRE

    if price_in_zone and signal_age_candles < 1.5:
        return SignalStatus.OPTIMAL_ENTRY

    if price_in_zone and signal_age_candles < 3:
        return SignalStatus.VALID

    # Price outside zone but signal not expired yet
    if signal_age_candles < 3:
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
    limit: int = Query(10, ge=1, le=100),
    timeframe: str = Query("1m", description="Timeframe for live signals"),
    trade_style: str = Query("scalp", pattern="^(scalp|swing)$"),
) -> List[dict]:
    """Get current trading signals with full indicator breakdown."""
    symbols = [symbol] if symbol else ["XAU/USD", "EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD"]

    signals = []
    for sym in symbols[:limit]:
        result = get_or_create_signal(sym, timeframe, trade_style=trade_style)
        signals.append(result)

    return signals


@router.get("/breakdown/{symbol:path}")
async def get_signal_breakdown(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$"),
    actionable: bool = Query(False, description="Return the nearest actionable fallback if the primary signal is HOLD"),
) -> dict:
    """Get detailed signal breakdown for a specific symbol.

    Returns a persistent signal that survives across calls until it is
    resolved (TP/SL hit or expired) and the subsequent cooldown elapses.
    """
    _cleanup_stale_signals()
    result = get_or_create_signal(symbol, timeframe, trade_style=trade_style)
    if actionable:
        result = _preferred_chart_signal(symbol, timeframe, trade_style, result)

    # Attach aiScore if not already present
    if "aiScore" not in result:
        _dir_map = {"BUY": "buy", "SELL": "sell", "HOLD": "hold"}
        result["aiScore"] = compute_ai_score(
            _dir_map.get(result.get("direction", "HOLD"), "hold"),
            float(result.get("confidence", 50)),
            result.get("indicators", []),
            "ranging",
            [],
        )

    return result


@router.post("/reset/{symbol:path}")
async def reset_signal(symbol: str) -> dict:
    """Force-reset the signal for a symbol (for testing)."""
    with _signal_lock:
        stale_keys = [key for key in _active_signals.keys() if key.startswith(f"{symbol}|")]
        for key in stale_keys:
            _active_signals.pop(key, None)
            _cooldown_until.pop(key, None)
    return {"status": "reset", "symbol": symbol}


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
