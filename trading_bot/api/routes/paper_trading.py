from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from trading_bot.execution.paper import (
    PaperExecutionPersistenceError,
    PaperOrderCommand,
    PaperOrderValidationError,
    get_paper_account_summary as get_paper_account_summary_from_execution,
    get_paper_positions as get_paper_positions_from_execution,
    place_paper_order as execute_paper_order,
    reset_paper_account as reset_paper_execution_account,
)

router = APIRouter(prefix="/api/trading", tags=["paper_trading"])


class PaperOrderRequest(BaseModel):
    symbol: str
    side: str  # "buy" or "sell"
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_percent: Optional[float] = None
    trade_style: Optional[str] = None
    confidence: Optional[float] = None
    strategy_id: Optional[str] = None


@router.post("/paper-order")
async def place_paper_order(order: PaperOrderRequest):
    """Place a simulated paper trade."""
    try:
        return await execute_paper_order(PaperOrderCommand(**order.model_dump()))
    except PaperOrderValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except PaperExecutionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/paper-positions")
async def get_paper_positions():
    """Get current paper trading positions."""
    try:
        return {"positions": get_paper_positions_from_execution()}
    except PaperExecutionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/paper-account")
async def get_paper_account():
    """Get paper trading account summary."""
    return get_paper_account_summary_from_execution()


@router.delete("/paper-reset")
async def reset_paper_account():
    """Reset paper trading account to initial state."""
    try:
        reset_paper_execution_account()
    except PaperExecutionPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {"success": True, "message": "Paper account reset to $10,000"}
