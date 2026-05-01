"""Opportunity ranking for scanner and dashboard boards."""

from typing import Dict, List, Optional


def _score_signal(signal: str) -> float:
    if signal in ("buy", "strong_buy", "BUY"):
        return 1.0
    if signal in ("sell", "strong_sell", "SELL"):
        return 1.0
    return 0.35


def _score_regime(regime: str) -> float:
    if regime in ("trending_up", "trending_down"):
        return 1.0
    if regime == "volatile":
        return 0.75
    return 0.55


def _score_source(metadata: Optional[Dict]) -> float:
    if not metadata:
        return 0.4
    flags = set(metadata.get("qualityFlags", []))
    score = 1.0
    if metadata.get("isFallback"):
        score -= 0.2
    if "fallback_source" in flags:
        score -= 0.15
    if "synthetic_spot" in flags:
        score -= 0.1
    if "stale_data" in flags:
        score -= 0.35
    market_status = metadata.get("marketStatus")
    if market_status == "delayed":
        score -= 0.1
    if market_status == "stale":
        score -= 0.25
    return max(0.0, min(1.0, score))


def compute_risk_gate(
    analysis: Dict,
    source_metadata: Optional[Dict] = None,
    opportunity_score: Optional[float] = None,
) -> str:
    """Compute a risk gate level based on volatility, data quality, and opportunity."""
    atr = float(analysis.get("atr", 0))
    current_price = float(analysis.get("currentPrice", 0))
    opportunity_score_value = float(opportunity_score if opportunity_score is not None else 50)
    regime = analysis.get("marketRegime", "ranging")
    confidence = float(analysis.get("confidence", 50))

    risk_points = 0

    # Volatility risk: high ATR relative to price
    if current_price > 0:
        atr_pct = (atr / current_price) * 100
        if atr_pct > 2.0:
            risk_points += 2
        elif atr_pct > 1.0:
            risk_points += 1

    # Opportunity risk: very low opportunity score suggests unfavorable conditions
    if opportunity_score_value < 30:
        risk_points += 2
    elif opportunity_score_value < 50:
        risk_points += 1

    # Regime risk
    if regime in ("volatile", "choppy"):
        risk_points += 1
    elif regime == "ranging":
        risk_points += 0

    # Data quality risk
    if source_metadata:
        if source_metadata.get("isFallback"):
            risk_points += 1
        if source_metadata.get("marketStatus") in ("stale", "delayed"):
            risk_points += 1
        if "stale_data" in set(source_metadata.get("qualityFlags", [])):
            risk_points += 1

    # Confidence risk: very low confidence
    if confidence < 40:
        risk_points += 1

    if risk_points >= 4:
        return "high"
    if risk_points >= 2:
        return "medium"
    return "low"


def rank_opportunity(analysis: Dict, source_metadata: Optional[Dict] = None) -> Dict:
    confidence = float(analysis.get("confidence", 50))
    ai_score = float((analysis.get("aiScore") or {}).get("value", 50))
    signal = analysis.get("signal", "hold")
    regime = analysis.get("marketRegime", "ranging")

    confidence_score = confidence / 100.0
    ai_score_norm = ai_score / 100.0
    signal_score = _score_signal(signal)
    regime_score = _score_regime(regime)
    source_score = _score_source(source_metadata)

    opportunity_score = round(
        confidence_score * 0.35
        + ai_score_norm * 0.30
        + signal_score * 0.10
        + regime_score * 0.10
        + source_score * 0.15,
        4,
    )

    return {
        "opportunityScore": round(opportunity_score * 100, 1),
        "confidenceScore": round(confidence_score * 100, 1),
        "aiScore": round(ai_score_norm * 100, 1),
        "sourceScore": round(source_score * 100, 1),
        "regimeScore": round(regime_score * 100, 1),
        "signalStrength": signal,
        "riskGate": compute_risk_gate(analysis, source_metadata, opportunity_score * 100),
    }


def sort_opportunities(rows: List[Dict]) -> List[Dict]:
    return sorted(rows, key=lambda row: row.get("opportunityScore", 0), reverse=True)