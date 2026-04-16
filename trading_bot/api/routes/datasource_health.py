"""Data source health monitoring endpoint."""

import time

from fastapi import APIRouter

from trading_bot.config import get_logger
from trading_bot.data.market_data_service import get_health_status, get_cache_info
from trading_bot.forex_fetcher import get_provider_status

logger = get_logger(__name__)

router = APIRouter(prefix="/api/health", tags=["health"])


@router.get("/datasources")
async def datasource_health() -> dict:
    """Return health status for all data sources.

    Reports per-source metrics including:
    - status (healthy / degraded)
    - last success / failure timestamps
    - success / failure / fallback counts
    - median and p95 latency
    - last error message
    """
    return {
        "sources": get_health_status(),
        "spotProviders": get_provider_status(),
        "cache": get_cache_info(),
        "timestamp": time.time(),
    }
