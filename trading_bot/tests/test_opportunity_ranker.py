from trading_bot.services.opportunity_ranker import rank_opportunity


def test_risk_gate_uses_computed_opportunity_score():
    strong_analysis = {
        "signal": "buy",
        "confidence": 90,
        "aiScore": {"value": 90},
        "marketRegime": "trending_up",
        "atr": 0,
        "currentPrice": 100,
    }
    weak_analysis = {
        "signal": "hold",
        "confidence": 20,
        "aiScore": {"value": 20},
        "marketRegime": "ranging",
        "atr": 0,
        "currentPrice": 100,
    }

    strong = rank_opportunity(strong_analysis, {"qualityFlags": [], "marketStatus": "open"})
    weak = rank_opportunity(weak_analysis, {"qualityFlags": [], "marketStatus": "open"})

    assert strong["opportunityScore"] > 50
    assert strong["riskGate"] == "low"
    assert weak["opportunityScore"] < 50
    assert weak["riskGate"] == "medium"