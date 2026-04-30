"""Gold/XAU intelligence helpers for dashboard context."""

import time
from datetime import datetime, timezone
from typing import Dict

from trading_bot.data.market_data_service import fetch_yf_sync


def _session_name(hour_utc: int) -> str:
    if 0 <= hour_utc < 7:
        return "asia"
    if 7 <= hour_utc < 13:
        return "london"
    if 13 <= hour_utc < 21:
        return "new_york"
    return "after_hours"


def get_gold_context() -> Dict:
    now = datetime.now(timezone.utc)
    session = _session_name(now.hour)

    dxy_df = fetch_yf_sync("DX-Y.NYB", period="5d", interval="1h")
    yields_df = fetch_yf_sync("^TNX", period="5d", interval="1h")
    gold_df = fetch_yf_sync("XAU/USD", period="5d", interval="1h")

    dxy = float(dxy_df["close"].iloc[-1]) if dxy_df is not None and len(dxy_df) else None
    dxy_change = (
        float(dxy_df["close"].iloc[-1] - dxy_df["close"].iloc[-2])
        if dxy_df is not None and len(dxy_df) > 1 else None
    )
    yields = float(yields_df["close"].iloc[-1]) if yields_df is not None and len(yields_df) else None
    yields_change = (
        float(yields_df["close"].iloc[-1] - yields_df["close"].iloc[-2])
        if yields_df is not None and len(yields_df) > 1 else None
    )
    gold_price = float(gold_df["close"].iloc[-1]) if gold_df is not None and len(gold_df) else None

    volatility_regime = "unknown"
    if gold_df is not None and len(gold_df) >= 20:
        recent_range = (gold_df["high"] - gold_df["low"]).tail(20).mean()
        price = gold_df["close"].tail(20).mean()
        atr_pct = (recent_range / price) * 100 if price else 0
        if atr_pct < 0.25:
            volatility_regime = "calm"
        elif atr_pct < 0.75:
            volatility_regime = "normal"
        elif atr_pct < 1.5:
            volatility_regime = "elevated"
        else:
            volatility_regime = "high"

    macro_risk = "normal"
    if session == "new_york":
        macro_risk = "elevated"

    return {
        "symbol": "XAU/USD",
        "timestamp": time.time(),
        "session": session,
        "dxy": {
            "value": dxy,
            "change": dxy_change,
        },
        "yields10y": {
            "value": yields,
            "change": yields_change,
        },
        "gold": {
            "value": gold_price,
        },
        "volatilityRegime": volatility_regime,
        "macroRisk": macro_risk,
    }