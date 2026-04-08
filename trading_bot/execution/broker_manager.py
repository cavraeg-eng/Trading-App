"""Broker manager for handling multiple broker integrations."""

from typing import Dict, List, Optional

from trading_bot.config import get_logger
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderType,
)

logger = get_logger(__name__)


class BrokerManager:
    """Manager for multiple broker integrations."""

    def __init__(self):
        """Initialize broker manager."""
        self._brokers: Dict[str, BaseBroker] = {}
        self._active_broker: Optional[str] = None
        self._register_defaults()

    def _register_defaults(self) -> None:
        """Register all available brokers."""
        # Register CCXT brokers
        from trading_bot.execution.brokers.ccxt_broker import CCXTBroker

        for exchange in ["binance", "bybit", "okx", "kraken"]:
            self._brokers[exchange] = CCXTBroker(exchange)

        # Register OANDA
        from trading_bot.execution.brokers.oanda_broker import OANDABroker

        self._brokers["oanda"] = OANDABroker()

        # Register Alpaca
        from trading_bot.execution.brokers.alpaca_broker import AlpacaBroker

        self._brokers["alpaca"] = AlpacaBroker()

        logger.info(
            f"Registered {len(self._brokers)} brokers",
            brokers=list(self._brokers.keys()),
        )

    def list_brokers(self) -> List[dict]:
        """Get list of all available brokers with their info.

        Returns:
            List of broker info dictionaries
        """
        return [broker.get_info() for broker in self._brokers.values()]

    def get_broker(self, broker_id: str) -> Optional[BaseBroker]:
        """Get a specific broker by ID.

        Args:
            broker_id: Broker identifier

        Returns:
            Broker instance or None if not found
        """
        return self._brokers.get(broker_id)

    async def connect(self, broker_id: str, credentials: dict) -> bool:
        """Connect to a broker.

        Args:
            broker_id: Broker identifier
            credentials: API credentials dictionary

        Returns:
            True if connected successfully
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return False

        success = await broker.connect(credentials)
        if success:
            self._active_broker = broker_id
            logger.info(f"Connected to {broker_id} and set as active")
        return success

    async def disconnect(self, broker_id: str) -> bool:
        """Disconnect from a broker.

        Args:
            broker_id: Broker identifier

        Returns:
            True if disconnected successfully
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return False

        success = await broker.disconnect()
        if success and self._active_broker == broker_id:
            self._active_broker = None
        return success

    def get_active_broker(self) -> Optional[BaseBroker]:
        """Get the currently active broker.

        Returns:
            Active broker instance or None
        """
        if self._active_broker:
            return self._brokers.get(self._active_broker)
        return None

    def set_active_broker(self, broker_id: str) -> bool:
        """Set the active broker.

        Args:
            broker_id: Broker identifier

        Returns:
            True if broker exists and was set as active
        """
        if broker_id in self._brokers:
            self._active_broker = broker_id
            logger.info(f"Set {broker_id} as active broker")
            return True
        logger.error(f"Cannot set active broker: '{broker_id}' not found")
        return False

    async def place_order(
        self,
        broker_id: str,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
    ) -> Optional[BrokerOrder]:
        """Place an order with a specific broker.

        Args:
            broker_id: Broker identifier
            symbol: Trading symbol
            side: Order side
            quantity: Order quantity
            order_type: Order type
            price: Limit price (for limit orders)

        Returns:
            BrokerOrder or None if failed
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return None

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return None

        try:
            return await broker.place_order(symbol, side, quantity, order_type, price)
        except Exception as e:
            logger.error(f"Failed to place order with {broker_id}: {e}")
            return None

    async def cancel_order(self, broker_id: str, order_id: str) -> bool:
        """Cancel an order with a specific broker.

        Args:
            broker_id: Broker identifier
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return False

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return False

        try:
            return await broker.cancel_order(order_id)
        except Exception as e:
            logger.error(f"Failed to cancel order with {broker_id}: {e}")
            return False

    async def get_positions(self, broker_id: str) -> List[BrokerPosition]:
        """Get positions from a specific broker.

        Args:
            broker_id: Broker identifier

        Returns:
            List of positions
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return []

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return []

        try:
            return await broker.get_positions()
        except Exception as e:
            logger.error(f"Failed to get positions from {broker_id}: {e}")
            return []

    async def get_balance(self, broker_id: str) -> Optional[BrokerBalance]:
        """Get balance from a specific broker.

        Args:
            broker_id: Broker identifier

        Returns:
            BrokerBalance or None if failed
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return None

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return None

        try:
            return await broker.get_balance()
        except Exception as e:
            logger.error(f"Failed to get balance from {broker_id}: {e}")
            return None

    async def get_order_status(self, broker_id: str, order_id: str) -> Optional[BrokerOrder]:
        """Get order status from a specific broker.

        Args:
            broker_id: Broker identifier
            order_id: Order ID

        Returns:
            BrokerOrder or None if failed
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return None

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return None

        try:
            return await broker.get_order_status(order_id)
        except Exception as e:
            logger.error(f"Failed to get order status from {broker_id}: {e}")
            return None

    def get_broker_status(self, broker_id: str) -> dict:
        """Get status information for a broker.

        Args:
            broker_id: Broker identifier

        Returns:
            Status dictionary
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            return {
                "broker_id": broker_id,
                "exists": False,
                "connected": False,
                "is_active": False,
            }

        return {
            "broker_id": broker_id,
            "exists": True,
            "connected": broker.connected,
            "is_active": self._active_broker == broker_id,
            "info": broker.get_info(),
        }


# Global broker manager instance
broker_manager = BrokerManager()
