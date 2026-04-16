"""Gold-specific context endpoints for XAU/USD dashboard intelligence."""

from fastapi import APIRouter

from trading_bot.data.gold_context_service import get_gold_context

router = APIRouter(prefix="/api/gold", tags=["gold"])


@router.get("/context")
async def gold_context() -> dict:
    """Return gold/XAU context including session, DXY, yields, and volatility."""
    return get_gold_context()