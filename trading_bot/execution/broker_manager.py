"""Broker manager for handling multiple broker integrations."""

import json
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from trading_bot.config import get_logger
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderType,
)
from trading_bot.persistence import repositories as repo

logger = get_logger(__name__)


@dataclass
class BrokerOperationError(Exception):
    detail: str
    category: str = "broker_error"
    status_code: int = 502

    def __str__(self) -> str:
        return self.detail


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
            self._persist_broker_credentials(broker_id, credentials)
            self._persist_active_broker()
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
        if success:
            self._clear_broker_credentials(broker_id)
            self._persist_active_broker()
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
            self._persist_active_broker()
            logger.info(f"Set {broker_id} as active broker")
            return True
        logger.error(f"Cannot set active broker: '{broker_id}' not found")
        return False

    async def restore_state(self) -> None:
        """Restore persisted broker connections and active broker."""
        active_broker_id = repo.get_setting("broker:active")
        for broker_id in list(self._brokers.keys()):
            raw = repo.get_setting(f"broker:credentials:{broker_id}")
            if not raw:
                continue
            try:
                credentials = json.loads(raw)
            except json.JSONDecodeError:
                logger.warning(f"Skipping invalid persisted broker credentials for {broker_id}")
                repo.delete_setting(f"broker:credentials:{broker_id}")
                continue
            try:
                success = await self.connect(broker_id, credentials)
            except Exception as e:
                logger.warning(f"Failed restoring broker {broker_id}: {e}")
                success = False
            if not success:
                self._clear_broker_credentials(broker_id)

        if active_broker_id and active_broker_id in self._brokers and self._brokers[active_broker_id].connected:
            self._active_broker = active_broker_id
            self._persist_active_broker()
        elif self._active_broker:
            self._persist_active_broker()
        else:
            repo.delete_setting("broker:active")

    def _persist_broker_credentials(self, broker_id: str, credentials: dict) -> None:
        repo.set_setting(f"broker:credentials:{broker_id}", json.dumps(credentials))

    def _clear_broker_credentials(self, broker_id: str) -> None:
        repo.delete_setting(f"broker:credentials:{broker_id}")

    def _persist_active_broker(self) -> None:
        if self._active_broker:
            repo.set_setting("broker:active", self._active_broker)
        else:
            repo.delete_setting("broker:active")

    async def place_order(
        self,
        broker_id: str,
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
            return await broker.place_order(
                symbol,
                side,
                quantity,
                order_type,
                price,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
                take_profit_3=take_profit_3,
            )
        except BrokerOperationError:
            raise
        except TimeoutError as e:
            logger.error(f"Timed out placing order with {broker_id}: {e}")
            raise BrokerOperationError(
                detail=f"Timed out while placing order with {broker_id}",
                category="timeout",
                status_code=504,
            )
        except Exception as e:
            logger.error(f"Failed to place order with {broker_id}: {e}")
            raise BrokerOperationError(
                detail=f"Failed to place order with {broker_id}: {e}",
                category="placement_failed",
                status_code=502,
            )

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

    async def get_orders(
        self,
        broker_id: str,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from a specific broker.

        Args:
            broker_id: Broker identifier
            count: Number of orders
            symbol: Optional symbol filter
            status: Optional status filter

        Returns:
            List of broker orders
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return []

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return []

        try:
            return await broker.get_orders(count=count, symbol=symbol, status=status)
        except Exception as e:
            logger.error(f"Failed to get orders from {broker_id}: {e}")
            return []

    async def close_position(
        self,
        broker_id: str,
        symbol: str,
        position_id: Optional[str] = None,
    ) -> bool:
        """Close an open position.

        Args:
            broker_id: Broker identifier
            symbol: Trading symbol
            position_id: Optional broker-specific position or trade identifier

        Returns:
            True if closed successfully
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return False

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return False

        try:
            return await broker.close_position(symbol, position_id=position_id)
        except Exception as e:
            logger.error(f"Failed to close position with {broker_id}: {e}")
            return False

    async def get_trade_history(
        self, broker_id: str, count: int = 50, symbol: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Get trade history from a specific broker.

        Args:
            broker_id: Broker identifier
            count: Number of trades
            symbol: Optional symbol filter

        Returns:
            List of trade dictionaries
        """
        broker = self._brokers.get(broker_id)
        if not broker:
            logger.error(f"Broker '{broker_id}' not found")
            return []

        if not broker.connected:
            logger.error(f"Broker '{broker_id}' is not connected")
            return []

        try:
            return await broker.get_trade_history(count=count, symbol=symbol)
        except Exception as e:
            logger.error(f"Failed to get trade history from {broker_id}: {e}")
            return []

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
