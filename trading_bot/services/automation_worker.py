"""Backend automation worker lifecycle for strategy-driven execution."""

import asyncio
import time
from typing import Dict, Optional

from trading_bot.config import get_logger
from trading_bot.persistence import automation as repo
from trading_bot.services.automation_cycle import AutomationCycleContext, run_automation_cycle

logger = get_logger(__name__)

_worker_task: Optional[asyncio.Task] = None
_worker_mode: str = "paper"
_worker_broker_id: Optional[str] = None
_worker_status: Dict[str, object] = {
    "running": False,
    "lastRun": None,
    "lastExecution": None,
    "lastError": None,
    "mode": "paper",
    "brokerId": None,
    "lastAnalysis": None,
}
_last_signal_key: Optional[str] = None
_last_strategy_execution_at: Dict[str, float] = {}


def get_worker_status() -> Dict[str, object]:
    return dict(_worker_status)


def get_worker_mode() -> Dict[str, object]:
    return {"mode": _worker_mode, "brokerId": _worker_broker_id}


def _persist_cycle_result_events(result) -> None:
    for event in result.events:
        repo.insert_automation_execution(
            event.strategy_id,
            event.symbol,
            event.action,
            event.status,
            event.detail,
        )


def _apply_cycle_result(result) -> None:
    global _last_signal_key

    _persist_cycle_result_events(result)
    if result.last_analysis is not None:
        _worker_status["lastAnalysis"] = result.last_analysis
    if result.last_error is not None:
        _worker_status["lastError"] = result.last_error
    if result.last_execution_at is not None:
        _worker_status["lastExecution"] = result.last_execution_at
        _worker_status["lastError"] = None
    if result.last_signal_key is not None:
        _last_signal_key = result.last_signal_key
    _last_strategy_execution_at.update(result.strategy_execution_updates)
    _worker_status["lastRun"] = time.time()


async def _automation_loop() -> None:
    try:
        while _worker_status["running"]:
            context = AutomationCycleContext(
                mode=_worker_mode,
                broker_id=_worker_broker_id,
                last_signal_key=_last_signal_key,
                last_strategy_execution_at=dict(_last_strategy_execution_at),
            )
            result = await run_automation_cycle(context)
            _apply_cycle_result(result)
            await asyncio.sleep(5)
    except asyncio.CancelledError:
        _worker_status["lastRun"] = time.time()
        raise
    except Exception as exc:
        logger.warning("Automation worker error: %s", exc)
        repo.insert_automation_execution(
            "unknown",
            "unknown",
            "execute",
            "error",
            {"reason": "worker_cycle_failed", "error": str(exc)},
        )
        _worker_status["lastError"] = str(exc)
        _worker_status["lastRun"] = time.time()


def start_worker(mode: str = "paper", broker_id: Optional[str] = None) -> None:
    global _worker_task, _worker_mode, _worker_broker_id
    if _worker_status["running"]:
        return
    _worker_mode = mode
    _worker_broker_id = broker_id
    _worker_status["mode"] = mode
    _worker_status["brokerId"] = broker_id
    _worker_status["lastAnalysis"] = None
    repo.insert_automation_execution(
        "system",
        "system",
        "worker",
        "started",
        {"mode": mode, "broker_id": broker_id},
    )
    _worker_status["running"] = True
    loop = asyncio.get_event_loop()
    _worker_task = loop.create_task(_automation_loop())


async def stop_worker() -> None:
    global _worker_task, _worker_mode, _worker_broker_id
    _worker_status["running"] = False
    _worker_status["mode"] = "paper"
    _worker_status["brokerId"] = None
    repo.insert_automation_execution(
        "system",
        "system",
        "worker",
        "stopped",
        {"mode": _worker_mode},
    )
    _worker_mode = "paper"
    _worker_broker_id = None
    if _worker_task:
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass
        _worker_task = None
