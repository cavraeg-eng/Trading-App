"""Position sizing strategies."""

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from trading_bot.config import get_logger

logger = get_logger(__name__)


@dataclass
class PositionSize:
    """Position size result."""
    size: float  # Position size in units
    notional: float  # Notional value
    leverage: float  # Leverage used
    risk_amount: float  # Risk amount in base currency
    stop_loss_price: Optional[float] = None  # Stop loss price
    take_profit_price: Optional[float] = None  # Take profit price


class PositionSizer:
    """Position sizing calculator."""
    
    def __init__(
        self,
        risk_per_trade: float = 0.02,
        max_position_size: float = 0.3,
        volatility_target: float = 0.15,
        kelly_fraction: float = 0.5,
    ):
        """Initialize position sizer.
        
        Args:
            risk_per_trade: Risk per trade as fraction of capital
            max_position_size: Maximum position size as fraction of capital
            volatility_target: Annualized volatility target
            kelly_fraction: Kelly criterion fraction (0.5 = half Kelly)
        """
        self.risk_per_trade = risk_per_trade
        self.max_position_size = max_position_size
        self.volatility_target = volatility_target
        self.kelly_fraction = kelly_fraction
    
    def fixed_fraction(
        self,
        capital: float,
        entry_price: float,
        stop_loss: float,
    ) -> PositionSize:
        """Fixed fractional position sizing.
        
        Args:
            capital: Available capital
            entry_price: Entry price
            stop_loss: Stop loss price
            
        Returns:
            Position size
        """
        risk_amount = capital * self.risk_per_trade
        price_risk = abs(entry_price - stop_loss)
        
        if price_risk == 0:
            logger.warning("Price risk is zero, using minimum position")
            return PositionSize(
                size=0,
                notional=0,
                leverage=1.0,
                risk_amount=0,
                stop_loss_price=stop_loss,
            )
        
        # Calculate position size
        position_value = risk_amount / (price_risk / entry_price)
        
        # Apply maximum position constraint
        max_notional = capital * self.max_position_size
        notional = min(position_value, max_notional)
        size = notional / entry_price
        
        return PositionSize(
            size=size,
            notional=notional,
            leverage=1.0,
            risk_amount=risk_amount,
            stop_loss_price=stop_loss,
        )
    
    def kelly_criterion(
        self,
        capital: float,
        entry_price: float,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
    ) -> PositionSize:
        """Kelly criterion position sizing.
        
        Args:
            capital: Available capital
            entry_price: Entry price
            win_rate: Historical win rate (0-1)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (positive number)
            
        Returns:
            Position size
        """
        # Kelly formula: f = (p*b - q) / b
        # where p = win rate, q = loss rate, b = avg_win/avg_loss
        
        if avg_loss == 0 or win_rate <= 0 or win_rate >= 1:
            logger.warning("Invalid Kelly parameters, using fixed fraction")
            return self.fixed_fraction(capital, entry_price, entry_price * 0.95)
        
        b = avg_win / avg_loss
        q = 1 - win_rate
        
        kelly_f = (win_rate * b - q) / b
        
        # Apply Kelly fraction (half Kelly for safety)
        f = max(0, kelly_f * self.kelly_fraction)
        
        # Calculate position
        notional = capital * f
        notional = min(notional, capital * self.max_position_size)
        size = notional / entry_price
        
        risk_amount = capital * self.risk_per_trade
        
        return PositionSize(
            size=size,
            notional=notional,
            leverage=1.0,
            risk_amount=risk_amount,
        )
    
    def volatility_targeting(
        self,
        capital: float,
        entry_price: float,
        price_history: pd.Series,
        target_volatility: Optional[float] = None,
    ) -> PositionSize:
        """Volatility targeting position sizing.
        
        Args:
            capital: Available capital
            entry_price: Entry price
            price_history: Historical price series
            target_volatility: Target volatility (default from init)
            
        Returns:
            Position size
        """
        if target_volatility is None:
            target_volatility = self.volatility_target
        
        # Calculate realized volatility
        returns = price_history.pct_change().dropna()
        
        if len(returns) < 20:
            logger.warning("Insufficient price history for volatility calculation")
            return self.fixed_fraction(capital, entry_price, entry_price * 0.95)
        
        realized_vol = returns.std() * np.sqrt(365)  # Annualized
        
        if realized_vol == 0:
            logger.warning("Realized volatility is zero")
            return self.fixed_fraction(capital, entry_price, entry_price * 0.95)
        
        # Volatility scaling factor
        vol_scalar = target_volatility / realized_vol
        
        # Base position size
        base_notional = capital * self.risk_per_trade * 10  # Scale up
        notional = base_notional * vol_scalar
        
        # Apply constraints
        max_notional = capital * self.max_position_size
        notional = min(notional, max_notional)
        size = notional / entry_price
        
        risk_amount = capital * self.risk_per_trade
        
        return PositionSize(
            size=size,
            notional=notional,
            leverage=1.0,
            risk_amount=risk_amount,
        )
    
    def atr_based(
        self,
        capital: float,
        entry_price: float,
        atr: float,
        atr_multiplier: float = 2.0,
    ) -> PositionSize:
        """ATR-based position sizing.
        
        Args:
            capital: Available capital
            entry_price: Entry price
            atr: Average True Range value
            atr_multiplier: ATR multiplier for stop loss
            
        Returns:
            Position size
        """
        risk_amount = capital * self.risk_per_trade
        stop_distance = atr * atr_multiplier
        
        if stop_distance == 0:
            logger.warning("ATR is zero")
            return self.fixed_fraction(capital, entry_price, entry_price * 0.95)
        
        # Position size based on ATR
        position_value = risk_amount / (stop_distance / entry_price)
        
        # Apply max position constraint
        max_notional = capital * self.max_position_size
        notional = min(position_value, max_notional)
        size = notional / entry_price
        
        stop_loss = entry_price - stop_distance if size > 0 else entry_price + stop_distance
        
        return PositionSize(
            size=size,
            notional=notional,
            leverage=1.0,
            risk_amount=risk_amount,
            stop_loss_price=stop_loss,
        )
    
    def optimal_f(
        self,
        capital: float,
        entry_price: float,
        historical_returns: pd.Series,
    ) -> PositionSize:
        """Optimal f position sizing (Ralph Vince).
        
        Args:
            capital: Available capital
            entry_price: Entry price
            historical_returns: Series of historical trade returns
            
        Returns:
            Position size
        """
        if len(historical_returns) < 10:
            logger.warning("Insufficient historical returns")
            return self.fixed_fraction(capital, entry_price, entry_price * 0.95)
        
        # Find optimal f that maximizes geometric mean
        best_f = 0
        best_g = 0
        
        for f in np.linspace(0.01, 1.0, 100):
            # Calculate HPRs (Holding Period Returns)
            hprs = 1 + f * (-historical_returns / historical_returns.min())
            
            # Geometric mean
            g = hprs.prod() ** (1 / len(hprs))
            
            if g > best_g:
                best_g = g
                best_f = f
        
        # Apply optimal f with safety factor
        f = best_f * 0.5  # Use half for safety
        
        notional = capital * f
        notional = min(notional, capital * self.max_position_size)
        size = notional / entry_price
        
        risk_amount = capital * self.risk_per_trade
        
        return PositionSize(
            size=size,
            notional=notional,
            leverage=1.0,
            risk_amount=risk_amount,
        )
    
    def calculate_leverage(
        self,
        notional: float,
        capital: float,
        max_leverage: float = 5.0,
    ) -> float:
        """Calculate appropriate leverage.
        
        Args:
            notional: Notional position value
            capital: Available capital
            max_leverage: Maximum allowed leverage
            
        Returns:
            Leverage multiplier
        """
        if capital <= 0:
            return 1.0
        
        required_leverage = notional / capital
        return min(required_leverage, max_leverage)
