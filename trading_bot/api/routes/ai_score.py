"""Dedicated AI Score endpoint."""

import asyncio
import time
from uuid import uuid4
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from trading_bot.api.routes.market import analyze_symbol, compute_ai_score
from trading_bot.data.market_data_service import get_ohlcv_with_metadata
from trading_bot.config import get_logger
from trading_bot.monitoring.bot_metrics import bot_metrics
from trading_bot.sentiment.analyzer import SentimentAnalyzer

logger = get_logger(__name__)

router = APIRouter(prefix="/api/ai", tags=["ai"])

_sentiment_analyzer = SentimentAnalyzer()


def _get_sentiment_score(symbol: str) -> Optional[float]:
    """Fetch sentiment score for *symbol*, returning None on failure."""
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop and loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                data = pool.submit(
                    lambda: asyncio.run(_sentiment_analyzer.get_sentiment(symbol))
                ).result(timeout=2)
        else:
            data = asyncio.run(_sentiment_analyzer.get_sentiment(symbol))
        return data.get("score")  # -1 .. 1
    except Exception:
        return None


def _compute_change(current_score: int, symbol: str) -> float:
    """Compare *current_score* against the most recent persisted prediction.

    Returns the numeric difference (positive = improving, negative = declining, 0 = stable).
    The frontend expects a number to display with toFixed(1).
    """
    try:
        from trading_bot.persistence import repositories as repo
        from trading_bot.persistence.db import get_conn
        row = get_conn().execute(
            "SELECT confidence FROM signal_predictions WHERE symbol = ? ORDER BY created_at DESC LIMIT 1",
            (symbol,),
        ).fetchone()
        if row:
            prev = int(row["confidence"])
            return float(current_score - prev)
        return 0.0
    except Exception:
        return 0.0


@router.get("/score/{symbol:path}")
async def get_ai_score(
    symbol: str,
    timeframe: str = Query("1h", description="Timeframe: 1m, 5m, 15m, 1h, 4h, 1d"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$"),
) -> dict:
    """Return the AI score for *symbol* with full factor breakdown."""

    request_id = str(uuid4())
    started = time.perf_counter()
    context = {
        "endpoint": "/api/ai/score",
        "symbol": symbol,
        "timeframe": timeframe,
        "trade_style": trade_style,
    }
    try:
        analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
        if analysis is None:
            bot_metrics.increment_counter("prediction.failure", request_id=request_id, context=context)
            raise HTTPException(status_code=503, detail=f"AI score unavailable for {symbol}")

        # Extract values needed for score computation
        signal = analysis["signal"]
        confidence = analysis["confidence"]
        indicators = analysis.get("indicators", [])
        regime = analysis.get("marketRegime", "ranging")
        patterns = analysis.get("patterns", [])
        volume_ratio_val = None
        # volume_ratio is already computed inside analyze_symbol; recompute from OHLCV
        try:
            from trading_bot.api.routes.market import get_shared_ohlcv
            df = get_shared_ohlcv(symbol, timeframe, trade_style=trade_style)
            if df is not None and len(df) >= 20:
                current_vol = float(df["volume"].iloc[-1])
                avg_vol = float(df["volume"].rolling(window=20).mean().iloc[-1])
                if avg_vol > 0:
                    volume_ratio_val = current_vol / avg_vol
        except Exception:
            pass

        sentiment_val = _get_sentiment_score(symbol)
        metadata_timeframe = "1m" if trade_style == "scalp" and timeframe not in ("1m", "5m") else timeframe
        _, metadata = get_ohlcv_with_metadata(symbol, metadata_timeframe, trade_style=trade_style)

        with bot_metrics.timer("prediction.scoring", request_id=request_id, context=context):
            score_data = compute_ai_score(
                signal, confidence, indicators, regime, patterns,
                sentiment_score=sentiment_val,
                volume_ratio=volume_ratio_val,
            )

        change = _compute_change(score_data["value"], symbol)
        bot_metrics.increment_counter("prediction.success", request_id=request_id, context=context)

        return {
            "symbol": symbol,
            "tradeStyle": trade_style,
            "score": score_data["value"],
            "label": score_data["label"],
            "change": change,
            "dataSource": metadata.get("sourceName"),
            "dataQuality": metadata.get("qualityFlags", []),
            "freshnessSeconds": metadata.get("freshnessSeconds"),
            "factors": score_data["factors"],
            "requestId": request_id,
            "timestamp": datetime.now(tz=timezone.utc).isoformat(),
        }
    finally:
        bot_metrics.record_latency(
            "prediction.endpoint",
            (time.perf_counter() - started) * 1000,
            request_id=request_id,
            context=context,
        )
