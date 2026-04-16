"""Abstract base class for broker integrations."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class OrderSide(str, Enum):
    """Order side enumeration."""
    BUY = "buy"
    SELL = "sell"


class OrderType(str, Enum):
    """Order type enumeration."""
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"


class OrderStatus(str, Enum):
    """Order status enumeration."""
    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    PARTIALLY_FILLED = "partially_filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


@dataclass
class BrokerOrder:
    """Broker order data class."""
    order_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    price: Optional[float] = None
    status: OrderStatus = OrderStatus.PENDING
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    broker_id: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class BrokerPosition:
    """Broker position data class."""
    symbol: str
    side: str
    quantity: float
    entry_price: float
    current_price: float
    unrealized_pnl: float
    realized_pnl: float = 0.0
    broker_id: str = ""
    position_id: Optional[str] = None
    opened_at: Optional[str] = None


@dataclass
class BrokerBalance:
    """Broker balance data class."""
    total_equity: float
    available_margin: float
    used_margin: float
    currency: str = "USD"


class BaseBroker(ABC):
    """Abstract base class for broker integrations."""

    def __init__(self, broker_id: str, name: str, broker_type: str):
        self.broker_id = broker_id
        self.name = name
        self.broker_type = broker_type
        self.connected = False
        self.supported_markets: List[str] = []

    @abstractmethod
    async def connect(self, credentials: Dict[str, str]) -> bool:
        """Connect to the broker with API credentials."""
        pass

    @abstractmethod
    async def disconnect(self) -> bool:
        """Disconnect from the broker."""
        pass

    @abstractmethod
    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
        stop_loss: Optional[float] = None,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None,
        take_profit_3: Optional[float] = None,
    ) -> BrokerOrder:
        """Place an order with the broker."""
        pass

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        pass

    @abstractmethod
    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions."""
        pass

    @abstractmethod
    async def get_balance(self) -> BrokerBalance:
        """Get account balance."""
        pass

    @abstractmethod
    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get status of a specific order."""
        pass

    async def get_orders(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from the broker."""
        return []

    async def close_position(
        self,
        symbol: str,
        position_id: Optional[str] = None,
    ) -> bool:
        """Close an open position for a symbol.

        Default implementation places a market order in the opposite direction.
        Subclasses may override with broker-specific close mechanics.

        Args:
            symbol: Trading symbol to close
            position_id: Optional broker-specific position or trade identifier

        Returns:
            True if position was closed successfully
        """
        positions = await self.get_positions()
        for pos in positions:
            if pos.symbol != symbol:
                continue
            if position_id and pos.position_id != position_id:
                continue

            opposite = OrderSide.SELL if pos.side == "long" else OrderSide.BUY
            await self.place_order(
                symbol=symbol,
                side=opposite,
                quantity=pos.quantity,
                order_type=OrderType.MARKET,
            )
            return True
        return False

    async def get_trade_history(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get closed trade history from the broker.

        Subclasses should override this with broker-specific implementations.

        Returns:
            List of trade history dictionaries
        """
        return []

    def get_info(self) -> dict:
        """Get broker information."""
        info = {
            "id": self.broker_id,
            "name": self.name,
            "type": self.broker_type,
            "connected": self.connected,
            "supported_markets": self.supported_markets,
        }
        environment = getattr(self, "_environment", None)
        if environment:
            info["environment"] = environment
        return info
