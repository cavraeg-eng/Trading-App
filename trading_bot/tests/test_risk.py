"""Tests for risk management module."""


from trading_bot.risk.circuit_breaker import CircuitBreaker, CircuitBreakerLevel
from trading_bot.risk.manager import RiskManager
from trading_bot.risk.sizing import PositionSizer


class TestPositionSizer:
    """Test position sizer."""

    def test_fixed_fraction(self):
        """Test fixed fraction sizing."""
        sizer = PositionSizer(risk_per_trade=0.02)

        position = sizer.fixed_fraction(
            capital=10000,
            entry_price=100,
            stop_loss=95,
        )

        assert position.size > 0
        assert position.notional > 0
        assert position.risk_amount == 200  # 2% of 10000

    def test_kelly_criterion(self):
        """Test Kelly criterion sizing."""
        sizer = PositionSizer()

        position = sizer.kelly_criterion(
            capital=10000,
            entry_price=100,
            win_rate=0.55,
            avg_win=0.05,
            avg_loss=0.03,
        )

        assert position.size >= 0
        assert position.notional >= 0

    def test_atr_based(self):
        """Test ATR-based sizing."""
        sizer = PositionSizer()

        position = sizer.atr_based(
            capital=10000,
            entry_price=100,
            atr=2.5,
        )

        assert position.size > 0
        assert position.stop_loss_price is not None


class TestRiskManager:
    """Test risk manager."""

    def test_can_open_position(self):
        """Test position opening check."""
        manager = RiskManager(initial_capital=10000)

        can_trade, reason = manager.can_open_position(
            symbol="BTC/USDT",
            side="buy",
            size=0.05,
            price=50000,
        )

        assert can_trade is True
        assert reason == "OK"

    def test_position_size_limit(self):
        """Test position size limit."""
        manager = RiskManager(
            initial_capital=10000,
            max_position_size=0.1,  # 10%
        )

        can_trade, reason = manager.can_open_position(
            symbol="BTC/USDT",
            side="buy",
            size=10.0,  # Too large
            price=50000,
        )

        assert can_trade is False
        assert "size" in reason.lower()

    def test_open_and_close_position(self):
        """Test opening and closing positions."""
        manager = RiskManager(initial_capital=10000)

        # Open position
        position = manager.open_position(
            symbol="BTC/USDT",
            side="long",
            size=0.05,
            entry_price=50000,
            stop_loss=45000,
        )

        assert position is not None
        assert "BTC/USDT" in manager.state.open_positions

        # Close position
        pnl = manager.close_position("BTC/USDT", 55000)

        assert pnl is not None
        assert "BTC/USDT" not in manager.state.open_positions

    def test_circuit_breaker_drawdown(self):
        """Test drawdown circuit breaker."""
        manager = RiskManager(
            initial_capital=10000,
            max_daily_drawdown=0.05,
        )

        # Simulate large loss
        manager.state.current_equity = 9400  # 6% loss
        manager.state.peak_equity = 10000
        manager.state.daily_drawdown = 0.06

        should_stop, reason = manager.check_circuit_breakers()

        assert should_stop is True
        assert "drawdown" in reason.lower()


class TestCircuitBreaker:
    """Test circuit breaker."""

    def test_daily_loss_trigger(self):
        """Test daily loss circuit breaker."""
        cb = CircuitBreaker(max_daily_loss_pct=0.05)

        event = cb.check(
            current_equity=9500,
            daily_pnl=-600,  # More than 5% loss
            position_pnls={},
            volatility=0.1,
        )

        assert event is not None
        assert event.level == CircuitBreakerLevel.CRITICAL
        assert cb.is_triggered is True

    def test_drawdown_trigger(self):
        """Test drawdown circuit breaker."""
        cb = CircuitBreaker(max_drawdown_pct=0.15)
        cb.peak_equity = 10000

        event = cb.check(
            current_equity=8000,  # 20% drawdown
            daily_pnl=0,
            position_pnls={},
            volatility=0.1,
        )

        assert event is not None
        assert event.level == CircuitBreakerLevel.EMERGENCY

    def test_no_trigger(self):
        """Test when no circuit breaker triggers."""
        cb = CircuitBreaker()

        event = cb.check(
            current_equity=10000,
            daily_pnl=100,
            position_pnls={},
            volatility=0.1,
        )

        assert event is None
        assert cb.is_triggered is False
