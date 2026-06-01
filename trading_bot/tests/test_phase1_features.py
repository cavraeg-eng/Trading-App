"""Tests for Phase 1 features: AI Score, Smart Alerts, Multi-TF Alignment, Signal Backtest."""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from trading_bot.api.routes import ai_score as ai_score_routes
from trading_bot.api.routes import alignment as alignment_routes
from trading_bot.api.routes import backtest_routes
from trading_bot.persistence.db import init_db

# Initialize a temp DB so alert endpoints work in tests
_tmp = tempfile.mkdtemp()
init_db(Path(_tmp) / "test.db")

from trading_bot.api.server import app  # noqa: E402

client = TestClient(app)


def _market_metadata() -> dict:
    return {
        "sourceName": "fixture",
        "sourceType": "fixture",
        "priceSource": "fixture",
        "freshnessSeconds": 1,
        "qualityFlags": [],
    }


def _analysis_payload() -> dict:
    return {
        "aiScore": {
            "value": 72,
            "label": "Favorable",
            "factors": {
                "trend": 70,
                "momentum": 74,
                "volatility": 65,
            },
        },
    }


def _backtest_data(rows: int = 80) -> pd.DataFrame:
    index = pd.date_range("2026-01-01", periods=rows, freq="h", tz="UTC")
    close = pd.Series(1.08 + np.sin(np.linspace(0, 8, rows)) * 0.01, index=index)
    return pd.DataFrame(
        {
            "Open": close - 0.001,
            "High": close + 0.002,
            "Low": close - 0.002,
            "Close": close,
            "Volume": np.linspace(1_000, 2_000, rows),
        },
        index=index,
    )


def _patch_ai_score_market_data(monkeypatch) -> None:
    monkeypatch.setattr(
        ai_score_routes,
        "analyze_symbol",
        lambda *args, **kwargs: _analysis_payload(),
    )
    monkeypatch.setattr(
        ai_score_routes,
        "get_ohlcv_with_metadata",
        lambda *args, **kwargs: (None, _market_metadata()),
    )


def _patch_signal_backtest_market_data(monkeypatch) -> None:
    monkeypatch.setattr(
        backtest_routes,
        "_fetch_yf_data",
        lambda *args, **kwargs: (_backtest_data(), None),
    )


def _patch_alignment_data(monkeypatch) -> None:
    monkeypatch.setattr(
        alignment_routes,
        "compute_alignment",
        lambda symbol, trade_style="scalp": {
            "symbol": symbol,
            "alignmentScore": 76,
            "dominantDirection": "bullish",
            "timeframes": [
                {
                    "tf": "1h",
                    "direction": "bullish",
                    "confidence": 76,
                    "signal": "buy",
                    "weight": 20,
                    "aligned": True,
                },
            ],
        },
    )


class TestAIScore:
    def test_ai_score_endpoint_exists(self, monkeypatch):
        """GET /api/ai/score/{symbol} should return 200 or valid error."""
        _patch_ai_score_market_data(monkeypatch)
        resp = client.get("/api/ai/score/EURUSD=X")
        assert resp.status_code == 200

    def test_ai_score_response_structure(self, monkeypatch):
        """Response should have score, label, factors fields."""
        _patch_ai_score_market_data(monkeypatch)
        resp = client.get("/api/ai/score/EURUSD=X")
        assert resp.status_code == 200
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
    def test_alignment_endpoint_exists(self, monkeypatch):
        """GET /api/ai/alignment/{symbol} should return 200 or valid error."""
        _patch_alignment_data(monkeypatch)
        resp = client.get("/api/ai/alignment/EURUSD=X")
        assert resp.status_code == 200

    def test_alignment_response_structure(self, monkeypatch):
        """Response should have alignmentScore, dominantDirection, timeframes."""
        _patch_alignment_data(monkeypatch)
        resp = client.get("/api/ai/alignment/EURUSD=X")
        assert resp.status_code == 200
        data = resp.json()
        assert "alignmentScore" in data
        assert "dominantDirection" in data
        assert "timeframes" in data
        assert 0 <= data["alignmentScore"] <= 100

class TestSignalBacktest:
    def test_signal_backtest_endpoint_exists(self, monkeypatch):
        """POST /api/backtest/signal should accept valid request."""
        _patch_signal_backtest_market_data(monkeypatch)
        resp = client.post("/api/backtest/signal", json={
            "symbol": "EURUSD=X",
            "timeframe": "1h",
            "direction": "buy",
            "lookback_days": 30
        })
        assert resp.status_code == 200

    def test_signal_backtest_response_structure(self, monkeypatch):
        """Response should have enhanced metrics."""
        _patch_signal_backtest_market_data(monkeypatch)
        resp = client.post("/api/backtest/signal", json={
            "symbol": "EURUSD=X",
            "timeframe": "1h",
            "direction": "buy",
            "lookback_days": 30
        })
        assert resp.status_code == 200
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
