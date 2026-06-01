"""Abstract base class for broker integrations."""

from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
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


@dataclass(frozen=True)
class BrokerCapabilities:
    """Feature flags exposed by broker adapters."""
    market_orders: bool = True
    limit_orders: bool = True
    stop_orders: bool = False
    bracket_orders: bool = False
    cancel_orders: bool = True
    positions: bool = True
    balances: bool = True
    order_status: bool = True
    order_history: bool = False
    trade_history: bool = False
    close_position: bool = True
    modify_trade: bool = False
    quotes: bool = False
    candles: bool = False

    def as_dict(self) -> Dict[str, bool]:
        """Return capabilities as a serializable dictionary."""
        return asdict(self)


class BrokerConfigurationError(Exception):
    """Raised when broker configuration or credentials are invalid."""

    def __init__(self, detail: str, category: str = "configuration_error", status_code: int = 400):
        self.detail = detail
        self.category = category
        self.status_code = status_code
        super().__init__(detail)


class BrokerCapabilityError(Exception):
    """Raised when a broker does not support a requested capability."""

    def __init__(self, broker_id: str, capability: str):
        self.broker_id = broker_id
        self.capability = capability
        self.detail = f"Broker '{broker_id}' does not support capability '{capability}'"
        self.category = "unsupported_capability"
        self.status_code = 501
        super().__init__(self.detail)


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


@dataclass
class BrokerQuote:
    """Broker quote data class."""
    symbol: str
    bid: Optional[float] = None
    ask: Optional[float] = None
    last: Optional[float] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    broker_id: str = ""


@dataclass
class BrokerCandle:
    """Broker OHLCV candle data class."""
    symbol: str
    time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0
    broker_id: str = ""


class BaseBroker(ABC):
    """Abstract base class for broker integrations."""

    def __init__(self, broker_id: str, name: str, broker_type: str):
        self.broker_id = broker_id
        self.name = name
        self.broker_type = broker_type
        self.connected = False
        self.supported_markets: List[str] = []
        self.required_credentials: List[str] = []
        self.supported_environments: List[str] = []
        self.capabilities = BrokerCapabilities()

    def prepare_credentials(self, credentials: Dict[str, Any]) -> Dict[str, str]:
        """Validate and normalize connection credentials for this broker."""
        missing = [
            field_name
            for field_name in self.required_credentials
            if not credentials.get(field_name)
        ]
        if missing:
            raise BrokerConfigurationError(
                detail=(
                    f"Broker '{self.broker_id}' requires "
                    f"{', '.join(missing)}"
                ),
                category="missing_credentials",
            )

        prepared = {
            field_name: str(credentials[field_name])
            for field_name in self.required_credentials
        }

        if self.supported_environments:
            requested_environment = str(
                credentials.get("environment") or self.supported_environments[0]
            ).lower()
            environment = (
                requested_environment
                if requested_environment in self.supported_environments
                else self.supported_environments[0]
            )
            prepared["environment"] = environment

        return prepared

    def get_connection_schema(self) -> Dict[str, Any]:
        """Return non-secret connection requirements for clients."""
        return {
            "required_credentials": list(self.required_credentials),
            "supported_environments": list(self.supported_environments),
        }

    def get_capabilities(self) -> Dict[str, bool]:
        """Return broker capabilities as safe serializable metadata."""
        return self.capabilities.as_dict()

    def supports(self, capability: str) -> bool:
        """Return whether a broker supports a named capability."""
        return bool(self.get_capabilities().get(capability, False))

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

    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify stop loss and/or take profit on an open trade.

        Args:
            trade_id: Broker-specific trade/position identifier
            stop_loss: New stop loss price (None to leave unchanged)
            take_profit: New take profit price (None to leave unchanged)

        Returns:
            True if modification was successful
        """
        raise BrokerCapabilityError(self.broker_id, "modify_trade")

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

    async def get_quote(self, symbol: str) -> BrokerQuote:
        """Get the latest quote for a symbol."""
        raise BrokerCapabilityError(self.broker_id, "quotes")

    async def get_candles(
        self,
        symbol: str,
        timeframe: str = "1h",
        count: int = 200,
    ) -> List[BrokerCandle]:
        """Get recent OHLCV candles for a symbol."""
        raise BrokerCapabilityError(self.broker_id, "candles")

    def get_info(self) -> dict:
        """Get broker information."""
        info = {
            "id": self.broker_id,
            "name": self.name,
            "type": self.broker_type,
            "connected": self.connected,
            "supported_markets": self.supported_markets,
            "capabilities": self.get_capabilities(),
            "connection_schema": self.get_connection_schema(),
        }
        environment = getattr(self, "_environment", None)
        if environment:
            info["environment"] = environment
        return info
