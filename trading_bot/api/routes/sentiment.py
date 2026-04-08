"""Sentiment routes for the trading bot API."""

from typing import List, Optional

from fastapi import APIRouter, Query

from trading_bot.sentiment.analyzer import SentimentAnalyzer

router = APIRouter(prefix="/api/sentiment", tags=["sentiment"])

# Initialize sentiment analyzer
analyzer = SentimentAnalyzer()


@router.get("/overview")
async def get_sentiment_overview() -> dict:
    """Get overall market sentiment overview."""
    overview = await analyzer.get_overview()
    # Get last_updated from full sentiment data for first symbol
    last_updated = None
    if overview:
        full_sentiment = await analyzer.get_sentiment(overview[0]["symbol"])
        last_updated = full_sentiment.get("last_updated")
    return {
        "symbols": overview,
        "last_updated": last_updated
    }


@router.get("/symbol/{symbol:path}")
async def get_symbol_sentiment(symbol: str) -> dict:
    """Get detailed sentiment data for a specific symbol."""
    sentiment = await analyzer.get_sentiment(symbol)
    return sentiment


@router.get("/trending")
async def get_trending_sentiment(
    limit: int = Query(5, ge=1, le=20),
    sentiment_type: Optional[str] = Query(None, description="Filter by 'bullish', 'bearish', or 'neutral'")
) -> List[dict]:
    """Get trending sentiment changes."""
    overview = await analyzer.get_overview()
    
    trending = []
    for item in overview:
        if sentiment_type and item["label"] != sentiment_type:
            continue
        trending.append({
            "symbol": item["symbol"],
            "score": item["score"],
            "label": item["label"],
        })
    
    # Sort by absolute score (strongest sentiment first)
    trending.sort(key=lambda x: abs(x["score"]), reverse=True)
    return trending[:limit]
