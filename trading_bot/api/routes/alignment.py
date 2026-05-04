"""Multi-timeframe alignment score endpoint."""

from collections import Counter
from datetime import datetime, timezone
from typing import Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from trading_bot.services.market_analysis import (
    ALLOWED_SYMBOLS,
    analyze_symbol,
    map_symbol_to_yf,
    resolve_context_trade_style,
)
from trading_bot.config import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["alignment"])

# Weights for each timeframe (must sum to 100)
TF_WEIGHTS: Dict[str, int] = {
    "1d": 25,
    "4h": 25,
    "1h": 20,
    "15m": 15,
    "5m": 15,
}

TIMEFRAMES: List[str] = list(TF_WEIGHTS.keys())


def _classify_direction(signal: str) -> str:
    """Map a signal string to a direction label."""
    sig = signal.lower()
    if sig in ("buy", "strong_buy"):
        return "bullish"
    elif sig in ("sell", "strong_sell"):
        return "bearish"
    return "neutral"


def _strength_label(score: float) -> str:
    if score >= 85:
        return "Very Strong"
    elif score >= 70:
        return "Strong"
    elif score >= 55:
        return "Moderate"
    elif score >= 40:
        return "Weak"
    return "Conflicting"


def compute_alignment(symbol: str, trade_style: str = "scalp") -> dict:
    """Analyse *symbol* across 5 timeframes and return an alignment payload."""

    tf_details: List[dict] = []

    for tf in TIMEFRAMES:
        context_trade_style = resolve_context_trade_style(symbol, tf, trade_style)
        analysis = analyze_symbol(symbol, tf, context_trade_style)
        if analysis is not None:
            signal = analysis.get("signal", "hold")
            confidence = analysis.get("confidence", 50)
        else:
            signal = "hold"
            confidence = 50

        direction = _classify_direction(signal)
        tf_details.append({
            "tf": tf,
            "direction": direction,
            "confidence": confidence,
            "signal": signal,
            "weight": TF_WEIGHTS[tf],
        })

    # Determine dominant direction
    direction_counts: Dict[str, int] = Counter(
        d["direction"] for d in tf_details
    )
    dominant_direction = direction_counts.most_common(1)[0][0]
    agreeing = direction_counts[dominant_direction]

    # Mark each TF as aligned / not-aligned
    for entry in tf_details:
        entry["aligned"] = entry["direction"] == dominant_direction

    # Weighted alignment score (0-100)
    weighted_score = 0.0
    for entry in tf_details:
        if entry["aligned"]:
            weighted_score += (entry["weight"] / 100.0) * entry["confidence"]

    # Normalise: best possible = sum-of-weights-for-aligned * 100 confidence
    # Since weights already sum to 100 and confidence is 0-100, the max
    # weighted_score when all TFs agree with confidence 100 is exactly 100.
    alignment_score = int(round(min(max(weighted_score, 0), 100)))

    strength = _strength_label(alignment_score)

    return {
        "symbol": symbol,
        "alignmentScore": alignment_score,
        "strength": strength,
        "dominantDirection": dominant_direction,
        "agreeing": agreeing,
        "total": len(TIMEFRAMES),
        "timeframes": tf_details,
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


@router.get("/alignment/{symbol:path}")
async def get_alignment(
    symbol: str,
    trade_style: str = Query("scalp", description="Trade style: scalp or swing"),
) -> dict:
    """Return multi-timeframe alignment score for *symbol*."""
    if symbol not in ALLOWED_SYMBOLS and map_symbol_to_yf(symbol) not in ALLOWED_SYMBOLS:
        raise HTTPException(status_code=400, detail=f"Symbol '{symbol}' is not supported")

    result = compute_alignment(symbol, trade_style)
    return result
