"""Circuit breakers for emergency risk control."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple

from trading_bot.config import get_logger

logger = get_logger(__name__)


class CircuitBreakerLevel(Enum):
    """Circuit breaker severity levels."""
    WARNING = "warning"
    ALERT = "alert"
    CRITICAL = "critical"
    EMERGENCY = "emergency"


@dataclass
class CircuitBreakerEvent:
    """Circuit breaker event."""
    level: CircuitBreakerLevel
    name: str
    message: str
    timestamp: datetime
    metrics: Dict
    auto_action: Optional[str] = None


class CircuitBreaker:
    """Circuit breaker for risk management."""
    
    def __init__(
        self,
        max_daily_loss_pct: float = 0.05,
        max_position_loss_pct: float = 0.10,
        max_drawdown_pct: float = 0.15,
        max_consecutive_losses: int = 5,
        max_volatility_spike: float = 3.0,
        cooldown_minutes: int = 30,
    ):
        """Initialize circuit breaker.
        
        Args:
            max_daily_loss_pct: Maximum daily loss percentage
            max_position_loss_pct: Maximum single position loss
            max_drawdown_pct: Maximum drawdown percentage
            max_consecutive_losses: Maximum consecutive losses
            max_volatility_spike: Maximum volatility spike multiplier
            cooldown_minutes: Cooldown period after trigger
        """
        self.max_daily_loss_pct = max_daily_loss_pct
        self.max_position_loss_pct = max_position_loss_pct
        self.max_drawdown_pct = max_drawdown_pct
        self.max_consecutive_losses = max_consecutive_losses
        self.max_volatility_spike = max_volatility_spike
        self.cooldown_minutes = cooldown_minutes
        
        self.is_triggered = False
        self.trigger_level: Optional[CircuitBreakerLevel] = None
        self.trigger_time: Optional[datetime] = None
        self.events: List[CircuitBreakerEvent] = []
        self.handlers: Dict[CircuitBreakerLevel, List[Callable]] = {
            level: [] for level in CircuitBreakerLevel
        }
        
        # Tracking variables
        self.daily_pnl = 0.0
        self.peak_equity = 0.0
        self.consecutive_losses = 0
        self.baseline_volatility = 0.0
    
    def register_handler(
        self,
        level: CircuitBreakerLevel,
        handler: Callable[[CircuitBreakerEvent], None],
    ) -> None:
        """Register event handler.
        
        Args:
            level: Circuit breaker level
            handler: Handler function
        """
        self.handlers[level].append(handler)
    
    def check(
        self,
        current_equity: float,
        daily_pnl: float,
        position_pnls: Dict[str, float],
        volatility: float,
    ) -> Optional[CircuitBreakerEvent]:
        """Check all circuit breakers.
        
        Args:
            current_equity: Current portfolio equity
            daily_pnl: Daily PnL
            position_pnls: Position PnLs
            volatility: Current volatility
            
        Returns:
            Circuit breaker event if triggered
        """
        # Check cooldown
        if self.is_triggered and self.trigger_time:
            cooldown_end = self.trigger_time + timedelta(minutes=self.cooldown_minutes)
            if datetime.now() < cooldown_end:
                return None
            else:
                # Reset after cooldown
                self.reset()
        
        self.daily_pnl = daily_pnl
        
        # Update peak equity
        if current_equity > self.peak_equity:
            self.peak_equity = current_equity
        
        # Calculate drawdown
        drawdown = (self.peak_equity - current_equity) / self.peak_equity if self.peak_equity > 0 else 0
        
        # Check daily loss
        daily_loss_pct = -daily_pnl / current_equity if current_equity > 0 else 0
        if daily_loss_pct >= self.max_daily_loss_pct:
            return self._trigger(
                CircuitBreakerLevel.CRITICAL,
                "daily_loss_limit",
                f"Daily loss limit exceeded: {daily_loss_pct:.2%}",
                {"daily_loss_pct": daily_loss_pct, "limit": self.max_daily_loss_pct},
                "pause_trading",
            )
        
        # Check drawdown
        if drawdown >= self.max_drawdown_pct:
            return self._trigger(
                CircuitBreakerLevel.EMERGENCY,
                "max_drawdown",
                f"Maximum drawdown exceeded: {drawdown:.2%}",
                {"drawdown": drawdown, "limit": self.max_drawdown_pct},
                "close_all_positions",
            )
        
        # Check position losses
        for symbol, pnl in position_pnls.items():
            position_loss_pct = -pnl / current_equity if current_equity > 0 else 0
            if position_loss_pct >= self.max_position_loss_pct:
                return self._trigger(
                    CircuitBreakerLevel.ALERT,
                    "position_loss_limit",
                    f"Position loss limit exceeded for {symbol}: {position_loss_pct:.2%}",
                    {"symbol": symbol, "loss_pct": position_loss_pct, "limit": self.max_position_loss_pct},
                    f"close_position:{symbol}",
                )
        
        # Check consecutive losses
        if daily_pnl < 0:
            self.consecutive_losses += 1
        else:
            self.consecutive_losses = 0
        
        if self.consecutive_losses >= self.max_consecutive_losses:
            return self._trigger(
                CircuitBreakerLevel.WARNING,
                "consecutive_losses",
                f"{self.consecutive_losses} consecutive losing periods",
                {"consecutive_losses": self.consecutive_losses},
                "reduce_position_size",
            )
        
        # Check volatility spike
        if self.baseline_volatility > 0:
            vol_spike = volatility / self.baseline_volatility
            if vol_spike >= self.max_volatility_spike:
                return self._trigger(
                    CircuitBreakerLevel.WARNING,
                    "volatility_spike",
                    f"Volatility spike detected: {vol_spike:.2f}x baseline",
                    {"vol_spike": vol_spike, "baseline": self.baseline_volatility},
                    "reduce_exposure",
                )
        
        return None
    
    def _trigger(
        self,
        level: CircuitBreakerLevel,
        name: str,
        message: str,
        metrics: Dict,
        auto_action: Optional[str] = None,
    ) -> CircuitBreakerEvent:
        """Trigger circuit breaker.
        
        Args:
            level: Severity level
            name: Breaker name
            message: Alert message
            metrics: Related metrics
            auto_action: Automatic action to take
            
        Returns:
            Circuit breaker event
        """
        self.is_triggered = True
        self.trigger_level = level
        self.trigger_time = datetime.now()
        
        event = CircuitBreakerEvent(
            level=level,
            name=name,
            message=message,
            timestamp=datetime.now(),
            metrics=metrics,
            auto_action=auto_action,
        )
        
        self.events.append(event)
        
        # Call handlers
        for handler in self.handlers.get(level, []):
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Handler error: {e}")
        
        logger.critical(
            f"CIRCUIT BREAKER TRIGGERED: {name}",
            level=level.value,
            message=message,
            action=auto_action,
        )
        
        return event
    
    def reset(self) -> None:
        """Reset circuit breaker."""
        self.is_triggered = False
        self.trigger_level = None
        self.trigger_time = None
        self.consecutive_losses = 0
        logger.info("Circuit breaker reset")
    
    def set_baseline_volatility(self, volatility: float) -> None:
        """Set baseline volatility for spike detection.
        
        Args:
            volatility: Baseline volatility value
        """
        self.baseline_volatility = volatility
    
    def get_status(self) -> Dict:
        """Get circuit breaker status.
        
        Returns:
            Status dictionary
        """
        return {
            "is_triggered": self.is_triggered,
            "trigger_level": self.trigger_level.value if self.trigger_level else None,
            "trigger_time": self.trigger_time.isoformat() if self.trigger_time else None,
            "total_events": len(self.events),
            "consecutive_losses": self.consecutive_losses,
            "daily_pnl": self.daily_pnl,
        }
    
    def get_recent_events(self, n: int = 10) -> List[CircuitBreakerEvent]:
        """Get recent circuit breaker events.
        
        Args:
            n: Number of events to return
            
        Returns:
            List of events
        """
        return self.events[-n:]


class EmergencyStop:
    """Emergency stop mechanism."""
    
    def __init__(self):
        """Initialize emergency stop."""
        self.is_stopped = False
        self.stop_time: Optional[datetime] = None
        self.reason: Optional[str] = None
        self.handlers: List[Callable[[str], None]] = []
    
    def register_handler(self, handler: Callable[[str], None]) -> None:
        """Register stop handler.
        
        Args:
            handler: Handler function
        """
        self.handlers.append(handler)
    
    def stop(self, reason: str) -> None:
        """Trigger emergency stop.
        
        Args:
            reason: Stop reason
        """
        if self.is_stopped:
            return
        
        self.is_stopped = True
        self.stop_time = datetime.now()
        self.reason = reason
        
        logger.critical(f"EMERGENCY STOP: {reason}")
        
        # Call handlers
        for handler in self.handlers:
            try:
                handler(reason)
            except Exception as e:
                logger.error(f"Emergency handler error: {e}")
    
    def resume(self) -> None:
        """Resume after emergency stop."""
        if not self.is_stopped:
            return
        
        self.is_stopped = False
        logger.info(f"Emergency stop resumed. Previous reason: {self.reason}")
        self.reason = None
    
    def check(self) -> Tuple[bool, Optional[str]]:
        """Check if emergency stop is active.
        
        Returns:
            (is_stopped, reason)
        """
        return self.is_stopped, self.reason
