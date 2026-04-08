"""Social routes for the trading bot API."""

import random
import uuid
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import APIRouter, Query

from trading_bot.api.models import LeaderboardEntry, SignalDirection, SignalPost

router = APIRouter(prefix="/api/social", tags=["social"])

# Mock user data
_USERNAMES = [
    "AlphaTrader", "CryptoKing", "ForexMaster", "ChartWizard", "TradeHunter",
    "BullRunner", "BearSlayer", "PipCollector", "TrendSurfer", "MarketMaven",
    "WaveRider", "SignalPro", "ChartMaster", "TradeKing", "PipsQueen",
    "CryptoWhale", "FxGuru", "TradeNinja", "BullMarket", "SmartMoney"
]

_AVATARS = [
    "https://api.dicebear.com/7.x/avataaars/svg?seed=1",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=2",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=3",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=4",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=5",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=6",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=7",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=8",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=9",
    "https://api.dicebear.com/7.x/avataaars/svg?seed=10",
]

_SYMBOLS = ["EUR/USD", "GBP/USD", "USD/JPY", "BTC/USD", "ETH/USD", "AUD/USD", "XAU/USD", "SPX500"]


def generate_random_timestamp(days_back: int = 7) -> datetime:
    """Generate a random timestamp within the last N days."""
    now = datetime.now()
    delta = timedelta(
        days=random.randint(0, days_back),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59)
    )
    return now - delta


@router.get("/leaderboard")
async def get_leaderboard(
    timeframe: str = Query("monthly", description="weekly, monthly, all-time"),
    limit: int = Query(10, ge=1, le=50)
) -> List[dict]:
    """Get trading leaderboard."""
    leaderboard = []
    
    # Shuffle usernames for variety
    shuffled_users = list(zip(_USERNAMES, _AVATARS))
    random.shuffle(shuffled_users)
    
    for rank, (username, avatar) in enumerate(shuffled_users[:limit], 1):
        monthly_return = round(random.uniform(-15.0, 45.0), 2)
        win_rate = round(random.uniform(45.0, 85.0), 1)
        
        entry = {
            "rank": rank,
            "username": username,
            "avatar": avatar,
            "monthly_return": monthly_return,
            "win_rate": win_rate,
            "sharpe_ratio": round(random.uniform(0.8, 3.5), 2),
            "total_trades": random.randint(50, 500),
            "followers": random.randint(100, 5000),
            "verified": rank <= 3  # Top 3 are verified
        }
        leaderboard.append(entry)
    
    # Sort by monthly return
    leaderboard.sort(key=lambda x: x["monthly_return"], reverse=True)
    
    # Reassign ranks after sorting
    for i, entry in enumerate(leaderboard, 1):
        entry["rank"] = i
    
    return leaderboard


@router.get("/feed")
async def get_social_feed(
    symbol: Optional[str] = Query(None, description="Filter by symbol"),
    limit: int = Query(20, ge=1, le=100)
) -> List[dict]:
    """Get social trading feed with signal posts."""
    posts = []
    
    for i in range(limit):
        username = random.choice(_USERNAMES)
        avatar = random.choice(_AVATARS)
        post_symbol = symbol or random.choice(_SYMBOLS)
        
        rand = random.random()
        if rand < 0.45:
            direction = SignalDirection.BUY
        elif rand < 0.90:
            direction = SignalDirection.SELL
        else:
            direction = SignalDirection.HOLD
        
        entry_price = round(random.uniform(1.0, 50000.0), 4)
        
        # Determine if trade has a result
        result_rand = random.random()
        if result_rand < 0.4:
            result = "won"
            pnl = round(random.uniform(50, 500), 2)
        elif result_rand < 0.7:
            result = "lost"
            pnl = round(random.uniform(-300, -20), 2)
        else:
            result = "open"
            pnl = None
        
        post = {
            "id": str(uuid.uuid4())[:8],
            "username": username,
            "avatar": avatar,
            "symbol": post_symbol,
            "direction": direction.value,
            "confidence": round(random.uniform(0.60, 0.95), 2),
            "entry_price": entry_price,
            "stop_loss": round(entry_price * 0.98, 4) if direction == SignalDirection.BUY else round(entry_price * 1.02, 4),
            "take_profit": round(entry_price * 1.05, 4) if direction == SignalDirection.BUY else round(entry_price * 0.95, 4),
            "result": result,
            "pnl": pnl,
            "timestamp": generate_random_timestamp(3).isoformat(),
            "likes": random.randint(0, 150),
            "comments": random.randint(0, 30),
            "is_following": random.choice([True, False])
        }
        posts.append(post)
    
    # Sort by timestamp (newest first)
    posts.sort(key=lambda x: x["timestamp"], reverse=True)
    
    return posts


@router.post("/share")
async def share_signal(signal: dict) -> dict:
    """Share a signal to the social feed."""
    post_id = str(uuid.uuid4())[:8]
    
    return {
        "success": True,
        "post_id": post_id,
        "message": "Signal shared successfully",
        "timestamp": datetime.now().isoformat(),
        "signal": signal
    }


@router.post("/like/{post_id}")
async def like_post(post_id: str) -> dict:
    """Like a social post."""
    return {
        "success": True,
        "post_id": post_id,
        "likes": random.randint(10, 200),
        "message": "Post liked"
    }


@router.get("/user/{username}")
async def get_user_profile(username: str) -> dict:
    """Get user profile information."""
    avatar = random.choice(_AVATARS)
    
    return {
        "username": username,
        "avatar": avatar,
        "bio": f"Professional trader specializing in forex and crypto. Sharing my journey and insights.",
        "joined_date": (datetime.now() - timedelta(days=random.randint(100, 1000))).strftime("%Y-%m-%d"),
        "followers": random.randint(100, 10000),
        "following": random.randint(50, 500),
        "verified": random.choice([True, False]),
        "stats": {
            "total_signals": random.randint(100, 1000),
            "win_rate": round(random.uniform(50.0, 80.0), 1),
            "avg_return": round(random.uniform(2.0, 8.0), 2),
            "sharpe_ratio": round(random.uniform(1.0, 3.0), 2),
            "best_trade": round(random.uniform(500, 5000), 2),
            "worst_trade": round(random.uniform(-2000, -100), 2)
        },
        "achievements": [
            {"name": "Top Trader", "icon": "trophy", "description": "Ranked top 10 for 3 consecutive months"},
            {"name": "Signal Master", "icon": "signal", "description": "Shared 100+ profitable signals"},
            {"name": "Community", "icon": "users", "description": "Gained 1000+ followers"}
        ]
    }


@router.get("/trending-symbols")
async def get_trending_symbols(limit: int = Query(5, ge=1, le=20)) -> List[dict]:
    """Get trending symbols from social activity."""
    trending = []
    
    for symbol in random.sample(_SYMBOLS, min(limit, len(_SYMBOLS))):
        bullish_count = random.randint(10, 100)
        bearish_count = random.randint(5, 80)
        total = bullish_count + bearish_count
        
        trending.append({
            "symbol": symbol,
            "mentions": random.randint(50, 500),
            "bullish_pct": round((bullish_count / total) * 100, 1),
            "bearish_pct": round((bearish_count / total) * 100, 1),
            "sentiment": "bullish" if bullish_count > bearish_count else "bearish",
            "trending_rank": len(trending) + 1,
            "change_24h": round(random.uniform(-5.0, 5.0), 2)
        })
    
    # Sort by mentions
    trending.sort(key=lambda x: x["mentions"], reverse=True)
    
    return trending
