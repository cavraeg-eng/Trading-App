"""Signal accuracy and prediction metrics API."""

from typing import Optional

from fastapi import APIRouter, Query

from trading_bot.persistence import repositories as repo

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/signals")
async def get_signal_metrics(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """Get aggregated signal prediction accuracy metrics from stored outcomes."""
    return repo.get_signal_metrics(symbol=symbol, timeframe=timeframe, limit=limit)
