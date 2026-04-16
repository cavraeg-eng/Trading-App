"""Reporting endpoints for source-aware backtest summaries."""

from fastapi import APIRouter, Query
from trading_bot.api.routes.backtest_routes import BacktestRequest, run_backtest

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/backtest")
async def backtest_report(
    symbol: str = Query(...),
    timeframe: str = Query("1h"),
    trade_style: str = Query("swing"),
    start_date: str = Query(...),
    end_date: str = Query(...),
) -> dict:
    result = await run_backtest(BacktestRequest(
        symbol=symbol,
        timeframe=timeframe,
        trade_style=trade_style,
        start_date=start_date,
        end_date=end_date,
    ))
    if result.get("error"):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "tradeStyle": trade_style,
            "sourcePolicy": "spot_preferred" if trade_style == "scalp" and symbol == "XAU/USD" else "futures_only",
            "bestSession": "unknown",
            "sourceConfidence": 0,
            "regimeFit": 0,
            "sessionBreakdown": [],
            "sourceBreakdown": [],
            "startDate": start_date,
            "endDate": end_date,
            "error": result["error"],
        }
    report = result.get("report", {})
    report.update({
        "symbol": symbol,
        "timeframe": timeframe,
        "startDate": start_date,
        "endDate": end_date,
    })
    return report