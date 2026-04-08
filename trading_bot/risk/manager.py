"""Risk manager for portfolio-level risk control."""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from trading_bot.config import get_logger
from trading_bot.risk.sizing import PositionSize, PositionSizer

logger = get_logger(__name__)


@dataclass
class Position:
    """Position data."""
    symbol: str
    side: str  # "long" or "short"
    size: float
    entry_price: float
    entry_time: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    
    def update_unrealized_pnl(self, current_price: float) -> float:
        """Update and return unrealized PnL."""
        if self.side == "long":
            self.unrealized_pnl = (current_price - self.entry_price) * self.size
        else:
            self.unrealized_pnl = (self.entry_price - current_price) * self.size
        return self.unrealized_pnl
    
    def close(self, exit_price: float, exit_time: datetime) -> float:
        """Close position and return realized PnL."""
        self.update_unrealized_pnl(exit_price)
        self.realized_pnl = self.unrealized_pnl
        self.unrealized_pnl = 0.0
        return self.realized_pnl


@dataclass
class RiskState:
    """Current risk state."""
    total_exposure: float = 0.0
    daily_pnl: float = 0.0
    daily_drawdown: float = 0.0
    open_positions: Dict[str, Position] = field(default_factory=dict)
    peak_equity: float = 0.0
    current_equity: float = 0.0
    trades_today: int = 0
    last_trade_time: Optional[datetime] = None


class RiskManager:
    """Portfolio risk manager."""
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        max_daily_drawdown: float = 0.05,
        max_position_size: float = 0.3,
        max_total_exposure: float = 0.8,
        risk_per_trade: float = 0.02,
        max_trades_per_day: int = 10,
        correlation_threshold: float = 0.8,
    ):
        """Initialize risk manager.
        
        Args:
            initial_capital: Initial capital
            max_daily_drawdown: Maximum daily drawdown (0.05 = 5%)
            max_position_size: Maximum position size (0.3 = 30%)
            max_total_exposure: Maximum total exposure (0.8 = 80%)
            risk_per_trade: Risk per trade (0.02 = 2%)
            max_trades_per_day: Maximum trades per day
            correlation_threshold: Correlation threshold for position limits
        """
        self.initial_capital = initial_capital
        self.max_daily_drawdown = max_daily_drawdown
        self.max_position_size = max_position_size
        self.max_total_exposure = max_total_exposure
        self.risk_per_trade = risk_per_trade
        self.max_trades_per_day = max_trades_per_day
        self.correlation_threshold = correlation_threshold
        
        self.position_sizer = PositionSizer(
            risk_per_trade=risk_per_trade,
            max_position_size=max_position_size,
        )
        
        self.state = RiskState(current_equity=initial_capital, peak_equity=initial_capital)
        self.daily_returns: List[float] = []
        self.trade_history: List[Dict] = []
        
        self._current_date: Optional[datetime] = None
        self._daily_pnl_start: float = initial_capital
    
    def can_open_position(
        self,
        symbol: str,
        side: str,
        size: float,
        price: float,
    ) -> Tuple[bool, str]:
        """Check if position can be opened.
        
        Args:
            symbol: Trading symbol
            side: Position side
            size: Position size
            price: Entry price
            
        Returns:
            (can_trade, reason)
        """
        notional = size * price
        
        # Check daily drawdown
        if self.state.daily_drawdown >= self.max_daily_drawdown:
            return False, f"Daily drawdown limit reached: {self.state.daily_drawdown:.2%}"
        
        # Check max trades per day
        if self.state.trades_today >= self.max_trades_per_day:
            return False, f"Max trades per day reached: {self.state.trades_today}"
        
        # Check position size
        position_value = notional / self.state.current_equity
        if position_value > self.max_position_size:
            return False, f"Position size exceeds limit: {position_value:.2%}"
        
        # Check total exposure
        new_exposure = self.state.total_exposure + notional
        if new_exposure > self.state.current_equity * self.max_total_exposure:
            return False, f"Total exposure would exceed limit: {new_exposure / self.state.current_equity:.2%}"
        
        # Check if already have position in symbol
        if symbol in self.state.open_positions:
            return False, f"Already have position in {symbol}"
        
        # Check correlation with existing positions
        if not self._check_correlation(symbol):
            return False, f"High correlation with existing positions"
        
        return True, "OK"
    
    def open_position(
        self,
        symbol: str,
        side: str,
        size: float,
        entry_price: float,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> Optional[Position]:
        """Open a new position.
        
        Args:
            symbol: Trading symbol
            side: Position side (long/short)
            size: Position size
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            
        Returns:
            Position object or None if rejected
        """
        can_trade, reason = self.can_open_position(symbol, side, size, entry_price)
        
        if not can_trade:
            logger.warning(f"Position rejected: {reason}")
            return None
        
        position = Position(
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
            entry_time=datetime.now(),
            stop_loss=stop_loss,
            take_profit=take_profit,
        )
        
        self.state.open_positions[symbol] = position
        self.state.total_exposure += size * entry_price
        self.state.trades_today += 1
        self.state.last_trade_time = datetime.now()
        
        logger.info(
            "Position opened",
            symbol=symbol,
            side=side,
            size=size,
            entry_price=entry_price,
        )
        
        return position
    
    def close_position(
        self,
        symbol: str,
        exit_price: float,
    ) -> Optional[float]:
        """Close a position.
        
        Args:
            symbol: Trading symbol
            exit_price: Exit price
            
        Returns:
            Realized PnL or None
        """
        if symbol not in self.state.open_positions:
            logger.warning(f"No position found for {symbol}")
            return None
        
        position = self.state.open_positions[symbol]
        pnl = position.close(exit_price, datetime.now())
        
        # Update state
        notional = position.size * position.entry_price
        self.state.total_exposure -= notional
        self.state.current_equity += pnl
        self.state.daily_pnl += pnl
        
        # Update peak equity
        if self.state.current_equity > self.state.peak_equity:
            self.state.peak_equity = self.state.current_equity
        
        # Calculate drawdown
        self.state.daily_drawdown = (
            self.state.peak_equity - self.state.current_equity
        ) / self.state.peak_equity
        
        # Record trade
        self.trade_history.append({
            "symbol": symbol,
            "side": position.side,
            "entry_price": position.entry_price,
            "exit_price": exit_price,
            "size": position.size,
            "pnl": pnl,
            "entry_time": position.entry_time.isoformat(),
            "exit_time": datetime.now().isoformat(),
        })
        
        # Remove position
        del self.state.open_positions[symbol]
        
        logger.info(
            "Position closed",
            symbol=symbol,
            pnl=pnl,
            equity=self.state.current_equity,
        )
        
        return pnl
    
    def update_positions(self, prices: Dict[str, float]) -> Dict[str, float]:
        """Update all positions with current prices.
        
        Args:
            prices: Dictionary of symbol -> price
            
        Returns:
            Dictionary of symbol -> unrealized PnL
        """
        unrealized_pnls = {}
        
        for symbol, position in self.state.open_positions.items():
            if symbol in prices:
                pnl = position.update_unrealized_pnl(prices[symbol])
                unrealized_pnls[symbol] = pnl
                
                # Check stop loss
                if position.stop_loss:
                    if position.side == "long" and prices[symbol] <= position.stop_loss:
                        logger.info(f"Stop loss triggered for {symbol}")
                        self.close_position(symbol, prices[symbol])
                    elif position.side == "short" and prices[symbol] >= position.stop_loss:
                        logger.info(f"Stop loss triggered for {symbol}")
                        self.close_position(symbol, prices[symbol])
                
                # Check take profit
                if position.take_profit and symbol in self.state.open_positions:
                    if position.side == "long" and prices[symbol] >= position.take_profit:
                        logger.info(f"Take profit triggered for {symbol}")
                        self.close_position(symbol, prices[symbol])
                    elif position.side == "short" and prices[symbol] <= position.take_profit:
                        logger.info(f"Take profit triggered for {symbol}")
                        self.close_position(symbol, prices[symbol])
        
        return unrealized_pnls
    
    def check_circuit_breakers(self) -> Tuple[bool, str]:
        """Check if any circuit breakers should trigger.
        
        Returns:
            (should_stop, reason)
        """
        # Daily drawdown
        if self.state.daily_drawdown >= self.max_daily_drawdown:
            return True, f"Daily drawdown circuit breaker: {self.state.daily_drawdown:.2%}"
        
        # Total drawdown
        total_drawdown = (self.state.peak_equity - self.state.current_equity) / self.state.peak_equity
        if total_drawdown >= self.max_daily_drawdown * 2:  # 2x daily limit for total
            return True, f"Total drawdown circuit breaker: {total_drawdown:.2%}"
        
        # Consecutive losses
        recent_trades = self.trade_history[-5:]
        if len(recent_trades) >= 5:
            losses = sum(1 for t in recent_trades if t["pnl"] < 0)
            if losses >= 5:
                return True, "5 consecutive losses circuit breaker"
        
        return False, "OK"
    
    def get_position_size(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        method: str = "fixed_fraction",
    ) -> PositionSize:
        """Calculate position size.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price
            stop_loss: Stop loss price
            method: Sizing method
            
        Returns:
            Position size
        """
        if method == "fixed_fraction":
            return self.position_sizer.fixed_fraction(
                self.state.current_equity, entry_price, stop_loss
            )
        elif method == "atr":
            # Would need ATR value from data
            return self.position_sizer.fixed_fraction(
                self.state.current_equity, entry_price, stop_loss
            )
        else:
            return self.position_sizer.fixed_fraction(
                self.state.current_equity, entry_price, stop_loss
            )
    
    def get_portfolio_metrics(self) -> Dict:
        """Get portfolio risk metrics.
        
        Returns:
            Metrics dictionary
        """
        # Calculate returns
        if len(self.trade_history) > 1:
            returns = [t["pnl"] / self.initial_capital for t in self.trade_history]
            volatility = np.std(returns) * np.sqrt(252) if len(returns) > 1 else 0
        else:
            volatility = 0
        
        # Win rate
        if self.trade_history:
            wins = sum(1 for t in self.trade_history if t["pnl"] > 0)
            win_rate = wins / len(self.trade_history)
        else:
            win_rate = 0
        
        return {
            "current_equity": self.state.current_equity,
            "peak_equity": self.state.peak_equity,
            "total_return": (self.state.current_equity - self.initial_capital) / self.initial_capital,
            "daily_pnl": self.state.daily_pnl,
            "daily_drawdown": self.state.daily_drawdown,
            "total_drawdown": (self.state.peak_equity - self.state.current_equity) / self.state.peak_equity,
            "open_positions": len(self.state.open_positions),
            "total_exposure": self.state.total_exposure,
            "exposure_pct": self.state.total_exposure / self.state.current_equity if self.state.current_equity > 0 else 0,
            "trades_today": self.state.trades_today,
            "total_trades": len(self.trade_history),
            "win_rate": win_rate,
            "volatility": volatility,
        }
    
    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of new day)."""
        self.state.daily_pnl = 0.0
        self.state.daily_drawdown = 0.0
        self.state.trades_today = 0
        self._daily_pnl_start = self.state.current_equity
        logger.info("Daily stats reset")
    
    def _check_correlation(self, symbol: str) -> bool:
        """Check correlation with existing positions.
        
        Args:
            symbol: New symbol to check
            
        Returns:
            True if OK to trade
        """
        # Simplified - would need actual correlation data
        # For now, limit number of correlated positions
        return len(self.state.open_positions) < 3
    
    def close_all_positions(self, prices: Dict[str, float]) -> float:
        """Close all open positions.
        
        Args:
            prices: Current prices
            
        Returns:
            Total PnL
        """
        total_pnl = 0.0
        symbols = list(self.state.open_positions.keys())
        
        for symbol in symbols:
            if symbol in prices:
                pnl = self.close_position(symbol, prices[symbol])
                if pnl:
                    total_pnl += pnl
        
        logger.info(f"All positions closed, total PnL: {total_pnl:.2f}")
        return total_pnl
