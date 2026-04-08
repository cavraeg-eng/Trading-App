"""Base strategy class."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import pandas as pd

from trading_bot.config import get_logger

logger = get_logger(__name__)


class SignalType(Enum):
    """Signal types."""
    BUY = "buy"
    SELL = "sell"
    HOLD = "hold"
    CLOSE = "close"


@dataclass
class Signal:
    """Trading signal."""
    symbol: str
    signal_type: SignalType
    timestamp: datetime
    price: float
    confidence: float = 1.0
    metadata: Optional[Dict] = None
    
    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseStrategy(ABC):
    """Base strategy class."""
    
    def __init__(self, name: str, symbols: List[str]):
        """Initialize strategy.
        
        Args:
            name: Strategy name
            symbols: List of trading symbols
        """
        self.name = name
        self.symbols = symbols
        self.is_active = True
        self.signals: List[Signal] = []
        self.positions: Dict[str, SignalType] = {}
    
    @abstractmethod
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
    ) -> Optional[Signal]:
        """Generate trading signal.
        
        Args:
            symbol: Trading symbol
            data: Market data
            
        Returns:
            Signal or None
        """
        pass
    
    @abstractmethod
    def update(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Update strategy with new data.
        
        Args:
            data: Dictionary of symbol -> DataFrame
            
        Returns:
            List of signals
        """
        pass
    
    def activate(self) -> None:
        """Activate strategy."""
        self.is_active = True
        logger.info(f"Strategy {self.name} activated")
    
    def deactivate(self) -> None:
        """Deactivate strategy."""
        self.is_active = False
        logger.info(f"Strategy {self.name} deactivated")
    
    def get_position(self, symbol: str) -> Optional[SignalType]:
        """Get current position for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Position type or None
        """
        return self.positions.get(symbol)
    
    def set_position(self, symbol: str, position: Optional[SignalType]) -> None:
        """Set position for symbol.
        
        Args:
            symbol: Trading symbol
            position: Position type
        """
        if position is None:
            self.positions.pop(symbol, None)
        else:
            self.positions[symbol] = position
    
    def get_performance_metrics(self) -> Dict:
        """Get strategy performance metrics.
        
        Returns:
            Metrics dictionary
        """
        if not self.signals:
            return {}
        
        buy_signals = sum(1 for s in self.signals if s.signal_type == SignalType.BUY)
        sell_signals = sum(1 for s in self.signals if s.signal_type == SignalType.SELL)
        
        return {
            "total_signals": len(self.signals),
            "buy_signals": buy_signals,
            "sell_signals": sell_signals,
            "hold_signals": len(self.signals) - buy_signals - sell_signals,
            "active": self.is_active,
        }
