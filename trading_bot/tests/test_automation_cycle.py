import asyncio
from dataclasses import dataclass
from typing import List, Optional

from trading_bot.api.models import PredictionNoTradeReason, PredictionRecommendation
from trading_bot.execution.broker_base import BrokerBalance
from trading_bot.services.automation_cycle import (
    AutomationCycleContext,
    AutomationCycleDependencies,
    run_automation_cycle,
)
from trading_bot.services.automation_safety import AutomationGateResult


class FakeRepository:
    def __init__(self, *, active_mode: str = "paper", paper_positions=None, hourly_count: int = 0):
        self.settings = {
            "active_strategy_id": "forex-momentum-core",
            "active_strategy_mode": active_mode,
            "strategy:forex-momentum-core:enabled": "1",
            "strategy:forex-momentum-core:allocation_percent": "2.0",
            "strategy:forex-momentum-core:max_positions": "1",
            "strategy:forex-momentum-core:cooldown_seconds": "120",
            "strategy:forex-momentum-core:max_executions_per_hour": "2",
        }
        self.paper_positions = paper_positions or []
        self.hourly_count = hourly_count

    def get_setting(self, key, default=None):
        return self.settings.get(key, default)

    def get_paper_positions(self):
        return self.paper_positions

    def get_paper_account(self):
        return {"balance": 10000.0}

    def count_recent_automation_executions(self, strategy_id, window_seconds):
        return self.hourly_count


class FakeBrokerManager:
    def __init__(self):
        self.orders = []

    async def get_positions(self, broker_id):
        return []

    async def get_balance(self, broker_id):
        return BrokerBalance(total_equity=10000.0, available_margin=10000.0, used_margin=0.0)

    async def place_order(self, **kwargs):
        self.orders.append(kwargs)
        raise AssertionError("live order should remain safety-gated")


@dataclass
class FakeNoTradeDetail:
    code: PredictionNoTradeReason


@dataclass
class FakePrediction:
    recommendation: PredictionRecommendation
    trade_allowed: bool = True
    no_trade_reason: Optional[PredictionNoTradeReason] = None
    no_trade_reasons: Optional[List[FakeNoTradeDetail]] = None


def _strategy(strategy_id):
    return {
        "id": strategy_id,
        "name": "Forex Momentum Core",
        "symbol": "EUR/USD",
        "tradeStyle": "swing",
        "bestTimeframes": ["1h"],
    }


def _analysis(**overrides):
    base = {
        "signal": "buy",
        "confidence": 76,
        "reason": "bullish continuation",
        "marketRegime": "trend",
        "currentPrice": 1.1,
        "entryRange": {"min": 1.0995, "max": 1.1002},
        "stopLoss": 1.096,
        "takeProfit1": 1.104,
        "takeProfit2": 1.108,
        "takeProfit3": 1.112,
        "data_fetched_at": 1_700_000_000,
    }
    base.update(overrides)
    return base


def test_cycle_returns_explicit_no_trade_skip_without_worker_loop():
    placed_orders = []
    prediction = FakePrediction(
        recommendation=PredictionRecommendation.NO_TRADE,
        trade_allowed=False,
        no_trade_reason=PredictionNoTradeReason.LOW_CONFIDENCE,
        no_trade_reasons=[FakeNoTradeDetail(PredictionNoTradeReason.LOW_CONFIDENCE)],
    )
    deps = AutomationCycleDependencies(
        repository=FakeRepository(),
        strategy_provider=_strategy,
        analysis_provider=lambda symbol, timeframe, trade_style: _analysis(),
        prediction_provider=lambda request, analysis: prediction,
        paper_order_executor=placed_orders.append,
        live_gate_validator=lambda **kwargs: AutomationGateResult(True),
        clock=lambda: 1_700_000_100.0,
    )

    result = asyncio.run(run_automation_cycle(AutomationCycleContext(mode="paper"), deps))

    assert result.analyzed_symbols == ["EUR/USD"]
    assert placed_orders == []
    assert result.events[-1].status == "skipped"
    assert result.events[-1].detail["reason"] == "prediction_no_trade"
    assert result.events[-1].detail["noTradeReason"] == "low_confidence"


def test_cycle_executes_paper_trade_through_paper_seam():
    placed_orders = []

    async def place_order(order):
        placed_orders.append(order)
        return {"success": True, "order_id": "paper-1"}

    deps = AutomationCycleDependencies(
        repository=FakeRepository(),
        strategy_provider=_strategy,
        analysis_provider=lambda symbol, timeframe, trade_style: _analysis(),
        prediction_provider=lambda request, analysis: FakePrediction(PredictionRecommendation.BUY),
        paper_order_executor=place_order,
        live_gate_validator=lambda **kwargs: AutomationGateResult(True),
        clock=lambda: 1_700_000_100.0,
    )

    result = asyncio.run(run_automation_cycle(AutomationCycleContext(mode="paper"), deps))

    assert len(placed_orders) == 1
    assert placed_orders[0].symbol == "EUR/USD"
    assert placed_orders[0].strategy_id == "forex-momentum-core"
    assert result.events[-1].status == "success"
    assert result.events[-1].detail["mode"] == "paper"
    assert result.last_execution_at == 1_700_000_100.0


def test_cycle_keeps_live_execution_behind_risk_gate():
    broker = FakeBrokerManager()
    deps = AutomationCycleDependencies(
        repository=FakeRepository(active_mode="live"),
        broker_manager=broker,
        strategy_provider=_strategy,
        analysis_provider=lambda symbol, timeframe, trade_style: _analysis(),
        prediction_provider=lambda request, analysis: FakePrediction(PredictionRecommendation.BUY),
        live_gate_validator=lambda **kwargs: AutomationGateResult(True),
        live_risk_validator=lambda **kwargs: AutomationGateResult(
            False,
            "risk_amount_limit",
            {"riskAmount": 250.0, "maxRiskAmount": 200.0},
        ),
        clock=lambda: 1_700_000_100.0,
    )

    result = asyncio.run(
        run_automation_cycle(
            AutomationCycleContext(mode="live", broker_id="oanda"),
            deps,
        )
    )

    assert broker.orders == []
    assert result.events[-1].status == "skipped"
    assert result.events[-1].detail["reason"] == "risk_amount_limit"
    assert result.events[-1].detail["maxRiskAmount"] == 200.0
