"""Ranked opportunity endpoints for dashboard scanning."""

from typing import List, Optional

from fastapi import APIRouter, Query

from trading_bot.api.routes.market import analyze_symbol, get_shared_ohlcv_with_metadata
from trading_bot.config import get_logger
from trading_bot.services.opportunity_ranker import rank_opportunity, sort_opportunities

logger = get_logger(__name__)

router = APIRouter(prefix="/api/opportunities", tags=["opportunities"])

DEFAULT_SYMBOLS = [
    "XAU/USD",
    "EUR/USD",
    "GBP/USD",
    "USD/JPY",
    "BTC/USD",
    "ETH/USD",
    "US500",
    "US100",
]


def _build_opportunity(symbol: str, timeframe: str, trade_style: str) -> Optional[dict]:
    analysis = analyze_symbol(symbol, timeframe, trade_style=trade_style)
    if not analysis:
        return None

    _, source_metadata = get_shared_ohlcv_with_metadata(symbol, timeframe, trade_style=trade_style)
    ranking = rank_opportunity(analysis, source_metadata)

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "tradeStyle": trade_style,
        "signal": analysis.get("signal"),
        "confidence": analysis.get("confidence"),
        "marketRegime": analysis.get("marketRegime"),
        "reason": analysis.get("reason"),
        "currentPrice": analysis.get("currentPrice"),
        "sourceMetadata": source_metadata,
        **ranking,
    }


@router.get("/top")
async def top_opportunities(
    timeframe: str = Query("1h"),
    trade_style: str = Query("swing", pattern="^(scalp|swing)$"),
    symbols: Optional[str] = Query(None, description="Comma-separated symbols"),
) -> dict:
    symbol_list: List[str] = [s.strip() for s in symbols.split(",")] if symbols else DEFAULT_SYMBOLS
    rows = []
    for symbol in symbol_list:
        try:
            row = _build_opportunity(symbol, timeframe, trade_style)
            if row:
                rows.append(row)
        except Exception as exc:
            logger.warning("Failed to build opportunity for %s: %s", symbol, exc)
    return {"results": sort_opportunities(rows)}


@router.get("/xau")
async def xau_opportunities() -> dict:
    rows = []
    for timeframe, trade_style in [("1m", "scalp"), ("5m", "scalp"), ("1h", "swing"), ("4h", "swing")]:
        try:
            row = _build_opportunity("XAU/USD", timeframe, trade_style)
            if row:
                rows.append(row)
        except Exception as exc:
            logger.warning("Failed to build XAU opportunity for %s/%s: %s", timeframe, trade_style, exc)
    return {"results": sort_opportunities(rows)}