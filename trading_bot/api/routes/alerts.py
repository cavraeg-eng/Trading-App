"""Smart Alerts API routes."""

import json
import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from trading_bot.persistence import repositories as repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/alerts", tags=["alerts"])


# ── Request / Response models ───────────────────────────────────────────────

class CheckAlertsRequest(BaseModel):
    symbol: str


# ── Alert condition checker ─────────────────────────────────────────────────

def check_alert_conditions(
    symbol: str,
    signal_data: Optional[Dict[str, Any]] = None,
    ai_score_data: Optional[Dict[str, Any]] = None,
) -> List[dict]:
    """Evaluate current data and create alerts when conditions are met.

    Returns list of created alerts (dicts with id/type).
    """
    created: List[dict] = []
    signal_data = signal_data or {}
    ai_score_data = ai_score_data or {}

    ai_score = ai_score_data.get("score", 0)
    confidence = signal_data.get("confidence", 0)
    direction = signal_data.get("direction", "neutral")
    patterns = signal_data.get("patterns", [])
    timeframes = signal_data.get("timeframes", {})
    previous_score = ai_score_data.get("previous_score")

    # ── STRONG_SIGNAL ───────────────────────────────────────────────────
    if ai_score >= 80 or confidence >= 85:
        if not repo.get_recent_alert(symbol, "STRONG_SIGNAL"):
            score_val = max(ai_score, confidence)
            dir_label = direction.upper() if direction else "TRADE"
            title = "Strong {} Signal - {} (Score: {})".format(dir_label, symbol, score_val)
            message = (
                "{} shows a strong {} signal with AI score {} and confidence {}%.".format(
                    symbol, dir_label.lower(), ai_score, confidence
                )
            )
            data_blob = json.dumps({
                "ai_score": ai_score,
                "confidence": confidence,
                "direction": direction,
            })
            alert_id = repo.create_alert(
                symbol=symbol,
                alert_type="STRONG_SIGNAL",
                title=title,
                message=message,
                severity="critical",
                data=data_blob,
            )
            created.append({"id": alert_id, "type": "STRONG_SIGNAL"})

    # ── PATTERN_COMPLETE ────────────────────────────────────────────────
    for pat in patterns:
        success_rate = pat.get("success_rate", 0)
        if success_rate >= 70:
            pat_name = pat.get("name", "Unknown Pattern")
            if not repo.get_recent_alert(symbol, "PATTERN_COMPLETE"):
                title = "Pattern Complete: {} - {}".format(pat_name, symbol)
                message = (
                    "{} pattern detected on {} with {}% historical success rate.".format(
                        pat_name, symbol, success_rate
                    )
                )
                data_blob = json.dumps({
                    "pattern": pat_name,
                    "success_rate": success_rate,
                    "direction": direction,
                })
                alert_id = repo.create_alert(
                    symbol=symbol,
                    alert_type="PATTERN_COMPLETE",
                    title=title,
                    message=message,
                    severity="info",
                    data=data_blob,
                )
                created.append({"id": alert_id, "type": "PATTERN_COMPLETE"})
            break  # only one pattern alert per check

    # ── MULTITF_ALIGNED ─────────────────────────────────────────────────
    if timeframes:
        tf_directions = list(timeframes.values()) if isinstance(timeframes, dict) else timeframes
        if tf_directions:
            bullish = sum(1 for d in tf_directions if str(d).lower() in ("bullish", "buy", "long"))
            bearish = sum(1 for d in tf_directions if str(d).lower() in ("bearish", "sell", "short"))
            total = len(tf_directions)
            aligned = max(bullish, bearish)
            if aligned >= 4 and total >= 5:
                align_dir = "Bullish" if bullish >= bearish else "Bearish"
                if not repo.get_recent_alert(symbol, "MULTITF_ALIGNED"):
                    title = "Multi-TF Alignment: {}/{} {} - {}".format(
                        aligned, total, align_dir, symbol
                    )
                    message = (
                        "{} out of {} timeframes agree on {} direction for {}.".format(
                            aligned, total, align_dir.lower(), symbol
                        )
                    )
                    data_blob = json.dumps({
                        "aligned": aligned,
                        "total": total,
                        "direction": align_dir.lower(),
                        "timeframes": timeframes,
                    })
                    alert_id = repo.create_alert(
                        symbol=symbol,
                        alert_type="MULTITF_ALIGNED",
                        title=title,
                        message=message,
                        severity="warning",
                        data=data_blob,
                    )
                    created.append({"id": alert_id, "type": "MULTITF_ALIGNED"})

    # ── SCORE_CHANGE ────────────────────────────────────────────────────
    if previous_score is not None and ai_score:
        change = ai_score - previous_score
        if abs(change) >= 15:
            if not repo.get_recent_alert(symbol, "SCORE_CHANGE"):
                sign = "+" if change > 0 else ""
                verb = "Surge" if change > 0 else "Drop"
                title = "Score {}: {} {}{} points".format(verb, symbol, sign, change)
                message = (
                    "{} AI score changed by {} points (from {} to {}).".format(
                        symbol, change, previous_score, ai_score
                    )
                )
                data_blob = json.dumps({
                    "previous_score": previous_score,
                    "current_score": ai_score,
                    "change": change,
                })
                alert_id = repo.create_alert(
                    symbol=symbol,
                    alert_type="SCORE_CHANGE",
                    title=title,
                    message=message,
                    severity="info",
                    data=data_blob,
                )
                created.append({"id": alert_id, "type": "SCORE_CHANGE"})

    return created


# ── Route handlers ──────────────────────────────────────────────────────────

@router.get("")
async def list_alerts(unread_only: bool = False, limit: int = 50):
    """Return alerts list, newest first."""
    return repo.get_alerts(unread_only=unread_only, limit=limit)


@router.get("/unread-count")
async def unread_count():
    """Return count of unread alerts."""
    return {"count": repo.get_unread_count()}


@router.post("/{alert_id}/read")
async def mark_alert_read(alert_id: int):
    """Mark a single alert as read."""
    success = repo.mark_read(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"success": True}


@router.post("/read-all")
async def mark_all_alerts_read():
    """Mark all alerts as read."""
    repo.mark_all_read()
    return {"success": True}


@router.post("/check")
async def check_alerts(body: CheckAlertsRequest):
    """Manually trigger alert condition checks for a given symbol.

    Fetches the latest signal and AI score data, evaluates conditions,
    and creates alerts as appropriate.
    """
    symbol = body.symbol

    # Gather signal data from the signals route helpers
    signal_data: Dict[str, Any] = {}
    ai_score_data: Dict[str, Any] = {}

    try:
        from trading_bot.api.routes.signals import _generate_signals
        raw = _generate_signals(symbol)
        if raw:
            signal_data = {
                "confidence": raw.get("confidence", 0),
                "direction": raw.get("direction", "neutral"),
                "patterns": raw.get("patterns", []),
                "timeframes": raw.get("timeframes", {}),
            }
            ai_score_data = {
                "score": raw.get("ai_score", raw.get("score", 0)),
                "previous_score": raw.get("previous_score"),
            }
    except Exception as exc:
        logger.warning("Could not fetch signal data for %s: %s", symbol, exc)

    created = check_alert_conditions(symbol, signal_data, ai_score_data)
    return {"symbol": symbol, "alerts_created": len(created), "alerts": created}
