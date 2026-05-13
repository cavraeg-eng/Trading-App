from pathlib import Path
import threading
import time

from fastapi.testclient import TestClient

from trading_bot.api.server import app
from trading_bot.services import scanner_run
from trading_bot.persistence.db import init_db


client = TestClient(app)


def setup_module():
    init_db(Path("./data/test_scanner.db"))


def test_scanner_metadata_endpoint():
    response = client.get("/api/scanner/metadata")
    assert response.status_code == 200
    payload = response.json()
    assert "indicators" in payload
    assert "supportedTimeframes" in payload
    assert any(item["key"] == "RSI" for item in payload["indicators"])


def test_scanner_presets_include_market_and_risk_guidance():
    response = client.get("/api/scanner/presets")
    assert response.status_code == 200
    presets = response.json()["presets"]

    assert any("crypto" in preset["markets"] for preset in presets)
    assert any("metals" in preset["markets"] for preset in presets)
    for preset in presets:
        assert preset["market_scope"]
        assert preset["risk_gates"]
        assert preset["action_prompt"]


def test_saved_scanner_crud():
    create_response = client.post(
        "/api/scanner/save",
        json={
            "name": "Route Test Scanner",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "logic": "AND",
            "pairs": ["EUR/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )
    assert create_response.status_code == 200
    created = create_response.json()
    scanner_id = created["id"]

    list_response = client.get("/api/scanner/saved")
    assert list_response.status_code == 200
    saved = list_response.json()["saved"]
    assert any(item["id"] == scanner_id for item in saved)

    update_response = client.put(
        f"/api/scanner/saved/{scanner_id}",
        json={
            "name": "Route Test Scanner Updated",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 25}],
            "logic": "AND",
            "pairs": ["EUR/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )
    assert update_response.status_code == 200

    delete_response = client.delete(f"/api/scanner/saved/{scanner_id}")
    assert delete_response.status_code == 200


def test_scan_rejects_unsupported_indicator():
    response = client.post(
        "/api/scanner/scan",
        json={
            "name": "Unsupported",
            "conditions": [{"indicator": "Stochastic", "operator": "<", "value": 20}],
            "logic": "AND",
            "pairs": ["EUR/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]


def test_scan_rejects_invalid_timeframe():
    response = client.post(
        "/api/scanner/scan",
        json={
            "name": "Bad timeframe",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 20}],
            "logic": "AND",
            "pairs": ["EUR/USD"],
            "trade_style": "swing",
            "timeframe": "30m",
        },
    )
    assert response.status_code == 400
    assert "Unsupported timeframe" in response.json()["detail"]


def test_scan_returns_actionable_fields():
    response = client.post(
        "/api/scanner/scan",
        json={
            "name": "Actionable Test",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 100}],
            "logic": "AND",
            "pairs": ["EUR/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert "results" in payload
    assert "meta" in payload
    # If a result is returned, assert new actionable fields exist
    for result in payload["results"]:
        assert "risk_gate" in result
        assert result["risk_gate"] in ("low", "medium", "high")
        assert "risk_gate_reasons" in result
        assert "confidence_band" in result
        assert result["confidence_band"] in ("low", "medium", "high", "very_high")
        assert "rationale" in result
        assert "action" in result
        assert "trade_allowed" in result["action"]
        assert "market_context" in result
        assert "asset_class" in result["market_context"]
        assert "risk_context" in result
        assert "volatility_regime" in result["risk_context"]
        assert "market_status" in result["risk_context"]
        assert "group_results" in result
        # entry_range, stop_loss, take_profit1 may be present if analysis returned them
        if "entry_range" in result:
            assert "min" in result["entry_range"]
            assert "max" in result["entry_range"]


def test_scan_returns_partial_errors_and_scan_metadata(monkeypatch):
    def fake_evaluate(symbol, conditions, logic, trade_style, timeframe, groups):
        if symbol == "FAIL/USD":
            raise RuntimeError("market data unavailable")
        return {
            "symbol": symbol,
            "signal": "BUY",
            "score": 1.0,
            "matching_conditions": ["RSI < 100"],
            "indicator_values": {"RSI": 50},
            "confidence": 80,
            "trade_style": trade_style,
            "timeframe": timeframe,
            "opportunity_score": 70 if symbol == "EUR/USD" else 90,
            "reason": "Matched scanner conditions.",
        }

    monkeypatch.setattr(scanner_run, "evaluate_single_pair", fake_evaluate)
    monkeypatch.setattr(scanner_run, "get_scanner_concurrency_limit", lambda total_symbols=None: 2)

    response = client.post(
        "/api/scanner/scan",
        json={
            "name": "Partial errors",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 100}],
            "logic": "AND",
            "pairs": ["EUR/USD", "FAIL/USD", "GBP/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_matches"] == 2
    assert payload["meta"]["scan"]["succeeded"] == 2
    assert payload["meta"]["scan"]["failed"] == 1
    assert payload["meta"]["scan"]["concurrency_limit"] == 2
    assert payload["meta"]["scan"]["batch_duration_ms"] >= 0
    assert [item["symbol"] for item in payload["results"]] == ["GBP/USD", "EUR/USD", "FAIL/USD"]
    failed = payload["results"][-1]
    assert failed["scan_status"] == "error"
    assert failed["error_message"] == "market data unavailable"
    assert failed["evaluation_latency_ms"] >= 0


def test_scan_respects_configured_concurrency(monkeypatch):
    lock = threading.Lock()
    active = 0
    max_seen = 0

    def fake_evaluate(symbol, conditions, logic, trade_style, timeframe, groups):
        nonlocal active, max_seen
        with lock:
            active += 1
            max_seen = max(max_seen, active)
        time.sleep(0.03)
        with lock:
            active -= 1
        return {
            "symbol": symbol,
            "signal": "BUY",
            "score": 1.0,
            "matching_conditions": ["RSI < 100"],
            "indicator_values": {"RSI": 50},
            "confidence": 80,
            "trade_style": trade_style,
            "timeframe": timeframe,
            "opportunity_score": 50,
            "reason": "Matched scanner conditions.",
        }

    monkeypatch.setattr(scanner_run, "evaluate_single_pair", fake_evaluate)
    monkeypatch.setattr(scanner_run, "get_scanner_concurrency_limit", lambda total_symbols=None: 2)

    response = client.post(
        "/api/scanner/scan",
        json={
            "name": "Concurrency",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 100}],
            "logic": "AND",
            "pairs": ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "NZD/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )

    assert response.status_code == 200
    assert max_seen == 2


def test_scanner_alert_creation():
    response = client.post(
        "/api/scanner/alert",
        json={
            "name": "Alert Me",
            "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
            "logic": "AND",
            "groups": [
                {
                    "id": "group-a",
                    "name": "Entry setup",
                    "logic": "AND",
                    "conditions": [{"indicator": "RSI", "operator": "<", "value": 30}],
                }
            ],
            "pairs": ["EUR/USD", "GBP/USD"],
            "trade_style": "swing",
            "timeframe": "1h",
        },
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "armed"
    assert payload["name"] == "Alert Me"
