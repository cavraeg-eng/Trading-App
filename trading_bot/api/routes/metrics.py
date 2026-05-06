"""Signal accuracy and prediction metrics API."""

from typing import Optional

from fastapi import APIRouter, Query

from trading_bot.monitoring.bot_metrics import bot_metrics
from trading_bot.persistence import signals as signal_repo
from trading_bot.persistence import trade_ledger as ledger_repo

router = APIRouter(prefix="/api/metrics", tags=["metrics"])


@router.get("/signals")
async def get_signal_metrics(
    symbol: Optional[str] = Query(None),
    timeframe: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=1000),
) -> dict:
    """Get aggregated signal prediction accuracy metrics from stored outcomes."""
    return signal_repo.get_signal_metrics(symbol=symbol, timeframe=timeframe, limit=limit)


@router.get("/ledger")
async def get_ledger_metrics(
    broker_id: Optional[str] = Query(None),
    symbol: Optional[str] = Query(None),
    limit: int = Query(500, ge=1, le=2000),
) -> dict:
    """Get live broker ledger performance metrics including MFE/MAE and R multiples."""
    return ledger_repo.get_trade_ledger_metrics(broker_id=broker_id, symbol=symbol, limit=limit)


@router.get("/bot")
async def get_bot_performance_metrics() -> dict:
    """Get process-local AI bot latency and reliability metrics."""
    return bot_metrics.snapshot()
