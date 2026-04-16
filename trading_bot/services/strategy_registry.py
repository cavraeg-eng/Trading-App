"""Strategy catalog and activation metadata for Package 3."""

from typing import Dict, List, Optional


STRATEGIES: List[Dict] = [
    {
        "id": "gold-scalp-burst",
        "name": "Gold Scalp Burst",
        "symbol": "XAU/USD",
        "tradeStyle": "scalp",
        "category": "gold",
        "description": "Short-term XAU/USD momentum strategy focused on burst moves during active sessions.",
        "bestTimeframes": ["1m", "5m"],
        "bestSession": "new_york",
        "riskLevel": "high",
        "sourcePolicy": "spot_preferred",
        "tags": ["gold", "scalp", "volatility", "session-driven"],
        "performance": {
            "winRate": 62.0,
            "profitFactor": 1.48,
            "maxDrawdown": 8.7,
            "expectancy": 0.32,
        },
    },
    {
        "id": "gold-swing-trend",
        "name": "Gold Swing Trend",
        "symbol": "XAU/USD",
        "tradeStyle": "swing",
        "category": "gold",
        "description": "Trend-following XAU/USD strategy using higher-timeframe alignment and regime filters.",
        "bestTimeframes": ["1h", "4h"],
        "bestSession": "london",
        "riskLevel": "medium",
        "sourcePolicy": "futures_only",
        "tags": ["gold", "swing", "trend", "alignment"],
        "performance": {
            "winRate": 58.0,
            "profitFactor": 1.74,
            "maxDrawdown": 6.1,
            "expectancy": 0.44,
        },
    },
    {
        "id": "gold-event-safe",
        "name": "Gold Event Safe",
        "symbol": "XAU/USD",
        "tradeStyle": "swing",
        "category": "gold",
        "description": "Reduced-risk XAU/USD profile that avoids high-impact macro windows and weak source conditions.",
        "bestTimeframes": ["15m", "1h"],
        "bestSession": "london",
        "riskLevel": "low",
        "sourcePolicy": "spot_preferred",
        "tags": ["gold", "macro", "risk-managed", "defensive"],
        "performance": {
            "winRate": 55.0,
            "profitFactor": 1.63,
            "maxDrawdown": 4.2,
            "expectancy": 0.28,
        },
    },
    {
        "id": "forex-momentum-core",
        "name": "Forex Momentum Core",
        "symbol": "EUR/USD",
        "tradeStyle": "swing",
        "category": "forex",
        "description": "Core momentum strategy for major FX pairs using RSI/MACD/EMA agreement.",
        "bestTimeframes": ["1h", "4h"],
        "bestSession": "london",
        "riskLevel": "medium",
        "sourcePolicy": "futures_only",
        "tags": ["forex", "momentum", "majors"],
        "performance": {
            "winRate": 57.0,
            "profitFactor": 1.52,
            "maxDrawdown": 5.9,
            "expectancy": 0.31,
        },
    },
]


def list_strategies(category: Optional[str] = None) -> List[Dict]:
    if not category or category == "all":
        return STRATEGIES
    return [strategy for strategy in STRATEGIES if strategy["category"] == category]


def get_strategy(strategy_id: str) -> Optional[Dict]:
    for strategy in STRATEGIES:
        if strategy["id"] == strategy_id:
            return strategy
    return None