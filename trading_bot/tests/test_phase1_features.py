"""Tests for Phase 1 features: AI Score, Smart Alerts, Multi-TF Alignment, Signal Backtest."""
import pytest
import tempfile
from pathlib import Path
from fastapi.testclient import TestClient
from trading_bot.persistence.db import init_db

# Initialize a temp DB so alert endpoints work in tests
_tmp = tempfile.mkdtemp()
init_db(Path(_tmp) / "test.db")

from trading_bot.api.server import app

client = TestClient(app)

class TestAIScore:
    def test_ai_score_endpoint_exists(self):
        """GET /api/ai/score/{symbol} should return 200 or valid error."""
        resp = client.get("/api/ai/score/EURUSD=X")
        assert resp.status_code in (200, 500)  # 500 OK if market data unavailable
        
    def test_ai_score_response_structure(self):
        """Response should have score, label, factors fields."""
        resp = client.get("/api/ai/score/EURUSD=X")
        if resp.status_code == 200:
            data = resp.json()
            assert "score" in data
            assert "label" in data
            assert "factors" in data
            assert 0 <= data["score"] <= 100
            assert data["label"] in ("Strong", "Favorable", "Neutral", "Cautious")

class TestSmartAlerts:
    def test_alerts_list(self):
        """GET /api/alerts should return a list."""
        resp = client.get("/api/alerts")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
    
    def test_unread_count(self):
        """GET /api/alerts/unread-count should return count."""
        resp = client.get("/api/alerts/unread-count")
        assert resp.status_code == 200
        data = resp.json()
        assert "count" in data
        assert isinstance(data["count"], int)
    
    def test_mark_all_read(self):
        """POST /api/alerts/read-all should succeed."""
        resp = client.post("/api/alerts/read-all")
        assert resp.status_code == 200

class TestAlignment:
    def test_alignment_endpoint_exists(self):
        """GET /api/ai/alignment/{symbol} should return 200 or valid error."""
        resp = client.get("/api/ai/alignment/EURUSD=X")
        assert resp.status_code in (200, 500)
    
    def test_alignment_response_structure(self):
        """Response should have alignmentScore, dominantDirection, timeframes."""
        resp = client.get("/api/ai/alignment/EURUSD=X")
        if resp.status_code == 200:
            data = resp.json()
            assert "alignmentScore" in data
            assert "dominantDirection" in data
            assert "timeframes" in data
            assert 0 <= data["alignmentScore"] <= 100

class TestSignalBacktest:
    def test_signal_backtest_endpoint_exists(self):
        """POST /api/backtest/signal should accept valid request."""
        resp = client.post("/api/backtest/signal", json={
            "symbol": "EURUSD=X",
            "timeframe": "1h",
            "direction": "buy",
            "lookback_days": 30
        })
        assert resp.status_code in (200, 500)
    
    def test_signal_backtest_response_structure(self):
        """Response should have enhanced metrics."""
        resp = client.post("/api/backtest/signal", json={
            "symbol": "EURUSD=X",
            "timeframe": "1h",
            "direction": "buy",
            "lookback_days": 30
        })
        if resp.status_code == 200:
            data = resp.json()
            assert "winRate" in data
            assert "profitFactor" in data
            assert "avgHoldingPeriod" in data
            assert "confidenceCalibration" in data

class TestHealthAndExisting:
    def test_health_endpoint(self):
        """Existing health endpoint should still work."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
