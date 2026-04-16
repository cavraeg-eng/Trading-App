"""Strategy catalog endpoints for Package 3."""

from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from trading_bot.execution.broker_manager import broker_manager
from trading_bot.persistence import repositories as repo
from trading_bot.services.automation_worker import get_worker_mode, get_worker_status, start_worker, stop_worker
from trading_bot.services.strategy_registry import get_strategy, list_strategies

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class ActivateStrategyRequest(BaseModel):
    strategy_id: str
    mode: str = "paper"
    enabled: bool = True


class AutomationTemplateRequest(BaseModel):
    strategy_id: str
    mode: str = "paper"
    allocation_percent: float = 2.0
    max_positions: int = 1
    cooldown_seconds: int = 120
    max_executions_per_hour: int = 2
    enabled: bool = True


@router.get("")
async def strategies(category: str = Query("all")) -> dict:
    active = repo.get_setting("active_strategy_id")
    mode = repo.get_setting("active_strategy_mode", "paper")
    rows = []
    for strategy in list_strategies(category):
        rows.append({
            **strategy,
            "isActive": strategy["id"] == active,
            "activeMode": mode if strategy["id"] == active else None,
        })
    return {"results": rows}


@router.get("/catalog/{strategy_id}")
async def strategy_detail(strategy_id: str) -> dict:
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    active = repo.get_setting("active_strategy_id")
    mode = repo.get_setting("active_strategy_mode", "paper")
    return {
        **strategy,
        "isActive": strategy["id"] == active,
        "activeMode": mode if strategy["id"] == active else None,
        "performanceSnapshot": repo.get_strategy_performance_snapshot(strategy_id),
    }


@router.post("/activate")
async def activate_strategy(body: ActivateStrategyRequest) -> dict:
    strategy = get_strategy(body.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    if body.enabled:
        repo.set_setting("active_strategy_id", body.strategy_id)
        repo.set_setting("active_strategy_mode", body.mode)
    else:
        repo.set_setting("active_strategy_id", "")
        repo.set_setting("active_strategy_mode", body.mode)
    return {
        "success": True,
        "strategy_id": body.strategy_id,
        "enabled": body.enabled,
        "mode": body.mode,
    }


@router.get("/automation-template")
async def get_automation_template(strategy_id: str = Query(...)) -> dict:
    strategy = get_strategy(strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    active = repo.get_setting("active_strategy_id", "")
    return {
        "strategyId": strategy["id"],
        "mode": repo.get_setting("active_strategy_mode", "paper"),
        "allocationPercent": float(repo.get_setting(f"strategy:{strategy_id}:allocation_percent", "2.0")),
        "maxPositions": int(repo.get_setting(f"strategy:{strategy_id}:max_positions", "1")),
        "cooldownSeconds": int(repo.get_setting(f"strategy:{strategy_id}:cooldown_seconds", "120")),
        "maxExecutionsPerHour": int(repo.get_setting(f"strategy:{strategy_id}:max_executions_per_hour", "2")),
        "enabled": active == strategy_id,
    }


@router.post("/automation-template")
async def save_automation_template(body: AutomationTemplateRequest) -> dict:
    strategy = get_strategy(body.strategy_id)
    if not strategy:
        raise HTTPException(status_code=404, detail="Strategy not found")
    repo.set_setting(f"strategy:{body.strategy_id}:allocation_percent", str(body.allocation_percent))
    repo.set_setting(f"strategy:{body.strategy_id}:max_positions", str(body.max_positions))
    repo.set_setting(f"strategy:{body.strategy_id}:cooldown_seconds", str(body.cooldown_seconds))
    repo.set_setting(f"strategy:{body.strategy_id}:max_executions_per_hour", str(body.max_executions_per_hour))
    repo.set_setting(f"strategy:{body.strategy_id}:enabled", "1" if body.enabled else "0")
    repo.set_setting(f"strategy:{body.strategy_id}:mode", body.mode)
    return {
        "success": True,
        "strategyId": body.strategy_id,
        "mode": body.mode,
        "allocationPercent": body.allocation_percent,
        "maxPositions": body.max_positions,
        "cooldownSeconds": body.cooldown_seconds,
        "maxExecutionsPerHour": body.max_executions_per_hour,
        "enabled": body.enabled,
    }


@router.get("/automation-center")
async def automation_center() -> dict:
    active_id = repo.get_setting("active_strategy_id", "")
    active_mode = repo.get_setting("active_strategy_mode", "paper")
    strategy = get_strategy(active_id) if active_id else None
    template = None
    snapshot = None
    if strategy:
        template = await get_automation_template(active_id)
        snapshot = repo.get_strategy_performance_snapshot(active_id)
    return {
        "activeStrategy": strategy,
        "activeMode": active_mode,
        "template": template,
        "performanceSnapshot": snapshot,
        "worker": get_worker_status(),
        "executions": repo.get_automation_executions(20, active_id if active_id else None),
    }


@router.post("/automation-worker/start")
async def start_automation_worker(
    mode: Optional[str] = Query("paper", description="Execution mode: paper or live"),
    broker_id: Optional[str] = Query(None, description="Broker ID for live mode"),
) -> dict:
    # Validate live mode requirements
    if mode == "live":
        if not broker_id:
            raise HTTPException(status_code=400, detail="broker_id is required for live mode")
        status = broker_manager.get_broker_status(broker_id)
        if not status["exists"]:
            raise HTTPException(status_code=404, detail=f"Broker '{broker_id}' not found")
        if not status["connected"]:
            raise HTTPException(status_code=400, detail=f"Broker '{broker_id}' is not connected")
    start_worker(mode=mode or "paper", broker_id=broker_id)
    return {"success": True, "worker": get_worker_status()}


@router.post("/automation-worker/stop")
async def stop_automation_worker() -> dict:
    await stop_worker()
    return {"success": True, "worker": get_worker_status()}


@router.get("/automation-status")
async def automation_status() -> dict:
    """Lightweight status endpoint for the Live Trading page to poll."""
    active_id = repo.get_setting("active_strategy_id", "")
    strategy = get_strategy(active_id) if active_id else None
    worker = get_worker_status()
    mode_info = get_worker_mode()
    return {
        "worker": worker,
        "mode": mode_info["mode"],
        "brokerId": mode_info["brokerId"],
        "activeStrategy": strategy,
        "activeMode": repo.get_setting("active_strategy_mode", "paper"),
        "lastAnalysis": worker.get("lastAnalysis"),
        "executions": repo.get_automation_executions(5, active_id if active_id else None),
    }


@router.get("/active-signal")
async def active_signal() -> dict:
    """Return the latest signal analysis from the running automation worker."""
    worker = get_worker_status()
    analysis = worker.get("lastAnalysis")
    if not analysis:
        return {"hasSignal": False}
    return {"hasSignal": True, **analysis}