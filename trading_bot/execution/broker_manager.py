"""Broker manager for handling multiple broker integrations."""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from trading_bot.config import get_logger
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerCapabilityError,
    BrokerConfigurationError,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderType,
)
from trading_bot.execution import trade_ledger
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

    def __init__(self, register_defaults: bool = True, persist_state: bool = True):
        """Initialize broker manager."""
        self._brokers: Dict[str, BaseBroker] = {}
        self._active_broker: Optional[str] = None
        self._persist_state = persist_state
        if register_defaults:
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

    def register_broker(self, broker: BaseBroker, replace: bool = False) -> bool:
        """Register a broker adapter by ID."""
        existing = self._brokers.get(broker.broker_id)
        if existing is broker:
            return True
        if existing and not replace:
            logger.info(f"Broker '{broker.broker_id}' already registered")
            return False
        self._brokers[broker.broker_id] = broker
        return True

    def list_brokers(self) -> List[dict]:
        """Get list of all available brokers with their info.

        Returns:
            List of broker info dictionaries
        """
        return [
            self._broker_status_payload(broker_id, broker)
            for broker_id, broker in self._brokers.items()
        ]

    def get_broker(self, broker_id: str) -> Optional[BaseBroker]:
        """Get a specific broker by ID.

        Args:
            broker_id: Broker identifier

        Returns:
            Broker instance or None if not found
        """
        return self._brokers.get(broker_id)

    def _require_broker(self, broker_id: str, require_connected: bool = True) -> BaseBroker:
        broker = self._brokers.get(broker_id)
        if not broker:
            raise BrokerOperationError(
                detail=f"Broker '{broker_id}' not found",
                category="not_found",
                status_code=404,
            )
        if require_connected and not broker.connected:
            raise BrokerOperationError(
                detail=f"Broker '{broker_id}' is not connected",
                category="not_connected",
                status_code=400,
            )
        return broker

    def _broker_status_payload(self, broker_id: str, broker: BaseBroker) -> dict:
        info = broker.get_info()
        return {
            "broker_id": broker_id,
            "id": broker_id,
            "name": info["name"],
            "type": info["type"],
            "exists": True,
            "connected": broker.connected,
            "is_active": self._active_broker == broker_id,
            "supported_markets": info.get("supported_markets", []),
            "capabilities": info.get("capabilities", {}),
            "connection_schema": info.get("connection_schema", {}),
            "environment": info.get("environment"),
            "info": info,
        }

    def _handle_broker_exception(
        self,
        broker_id: str,
        operation: str,
        exc: Exception,
    ) -> BrokerOperationError:
        if isinstance(exc, BrokerOperationError):
            return exc
        if isinstance(exc, BrokerCapabilityError):
            return BrokerOperationError(
                detail=exc.detail,
                category=exc.category,
                status_code=exc.status_code,
            )
        if isinstance(exc, BrokerConfigurationError):
            return BrokerOperationError(
                detail=exc.detail,
                category=exc.category,
                status_code=exc.status_code,
            )
        if isinstance(exc, TimeoutError):
            return BrokerOperationError(
                detail=f"Timed out while running broker operation '{operation}' with {broker_id}",
                category="timeout",
                status_code=504,
            )
        return BrokerOperationError(
            detail=f"Failed to run broker operation '{operation}' with {broker_id}",
            category=f"{operation}_failed",
            status_code=502,
        )

    async def connect(self, broker_id: str, credentials: dict) -> bool:
        """Connect to a broker.

        Args:
            broker_id: Broker identifier
            credentials: API credentials dictionary

        Returns:
            True if connected successfully
        """
        broker = self._require_broker(broker_id, require_connected=False)
        try:
            prepared_credentials = broker.prepare_credentials(credentials)
            success = await broker.connect(prepared_credentials)
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "connect", e)
            logger.error(f"Failed to connect to {broker_id}: {safe_error.category}")
            raise safe_error
        if success:
            self._active_broker = broker_id
            self._clear_broker_credentials(broker_id)
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
        broker = self._require_broker(broker_id, require_connected=False)
        try:
            success = await broker.disconnect()
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "disconnect", e)
            logger.error(f"Failed to disconnect from {broker_id}: {safe_error.category}")
            raise safe_error
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

    def get_active_broker_info(self) -> Optional[dict]:
        """Get sanitized status information for the active broker."""
        active = self.get_active_broker()
        if not active:
            return None
        return self._broker_status_payload(active.broker_id, active)

    def set_active_broker(self, broker_id: str) -> bool:
        """Set the active broker.

        Args:
            broker_id: Broker identifier

        Returns:
            True if broker exists and was set as active
        """
        self._require_broker(broker_id, require_connected=False)
        self._active_broker = broker_id
        self._persist_active_broker()
        logger.info(f"Set {broker_id} as active broker")
        return True

    async def restore_state(self) -> None:
        """Restore persisted broker connections and active broker."""
        active_broker_id = repo.get_setting("broker:active")
        for broker_id in list(self._brokers.keys()):
            raw = repo.get_setting(f"broker:credentials:{broker_id}")
            if raw:
                logger.warning(f"Removing legacy persisted broker credentials for {broker_id}")
                repo.delete_setting(f"broker:credentials:{broker_id}")

        if (
            active_broker_id
            and active_broker_id in self._brokers
            and self._brokers[active_broker_id].connected
        ):
            self._active_broker = active_broker_id
            self._persist_active_broker()
        elif self._active_broker:
            self._persist_active_broker()
        else:
            repo.delete_setting("broker:active")

    def _clear_broker_credentials(self, broker_id: str) -> None:
        if not self._persist_state:
            return
        repo.delete_setting(f"broker:credentials:{broker_id}")

    def _persist_active_broker(self) -> None:
        if not self._persist_state:
            return
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
        broker = self._require_broker(broker_id)

        try:
            order = await broker.place_order(
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
            trade_ledger.upsert_order(broker_id, order)
            return order
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "place_order", e)
            logger.error(f"Failed to place order with {broker_id}: {safe_error.category}")
            raise safe_error

    async def cancel_order(self, broker_id: str, order_id: str) -> bool:
        """Cancel an order with a specific broker.

        Args:
            broker_id: Broker identifier
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        broker = self._require_broker(broker_id)

        try:
            success = await broker.cancel_order(order_id)
            if success:
                repo.update_trade_ledger_status(
                    broker_id,
                    "order",
                    order_id,
                    "cancelled",
                    {"event": "cancelled"},
                )
            return success
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "cancel_order", e)
            logger.error(f"Failed to cancel order with {broker_id}: {safe_error.category}")
            raise safe_error

    async def get_positions(self, broker_id: str) -> List[BrokerPosition]:
        """Get positions from a specific broker.

        Args:
            broker_id: Broker identifier

        Returns:
            List of positions
        """
        broker = self._require_broker(broker_id)

        try:
            positions = await broker.get_positions()
            trade_ledger.reconcile_positions(broker_id, positions)
            return positions
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "get_positions", e)
            logger.error(f"Failed to get positions from {broker_id}: {safe_error.category}")
            raise safe_error

    async def get_balance(self, broker_id: str) -> Optional[BrokerBalance]:
        """Get balance from a specific broker.

        Args:
            broker_id: Broker identifier

        Returns:
            BrokerBalance or None if failed
        """
        broker = self._require_broker(broker_id)

        try:
            return await broker.get_balance()
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "get_balance", e)
            logger.error(f"Failed to get balance from {broker_id}: {safe_error.category}")
            raise safe_error

    async def get_order_status(self, broker_id: str, order_id: str) -> Optional[BrokerOrder]:
        """Get order status from a specific broker.

        Args:
            broker_id: Broker identifier
            order_id: Order ID

        Returns:
            BrokerOrder or None if failed
        """
        broker = self._require_broker(broker_id)

        try:
            order = await broker.get_order_status(order_id)
            if order:
                trade_ledger.upsert_order(broker_id, order)
            return order
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "get_order_status", e)
            logger.error(f"Failed to get order status from {broker_id}: {safe_error.category}")
            raise safe_error

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
        broker = self._require_broker(broker_id)

        try:
            orders = await broker.get_orders(count=count, symbol=symbol, status=status)
            trade_ledger.reconcile_orders(broker_id, orders)
            return orders
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "get_orders", e)
            logger.error(f"Failed to get orders from {broker_id}: {safe_error.category}")
            raise safe_error

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
        broker = self._require_broker(broker_id)

        try:
            success = await broker.close_position(symbol, position_id=position_id)
            if success and position_id:
                repo.update_trade_ledger_status(
                    broker_id,
                    "position",
                    position_id,
                    "closed",
                    {"event": "closed_position", "symbol": symbol},
                )
            return success
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "close_position", e)
            logger.error(f"Failed to close position with {broker_id}: {safe_error.category}")
            raise safe_error

    async def modify_trade(
        self,
        broker_id: str,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify stop loss and/or take profit on an open trade.

        Args:
            broker_id: Broker identifier
            trade_id: Trade/position identifier
            stop_loss: New stop loss price
            take_profit: New take profit price

        Returns:
            True if modification was successful
        """
        broker = self._require_broker(broker_id)

        try:
            success = await broker.modify_trade(
                trade_id=trade_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "modify_trade", e)
            logger.error(f"Failed to modify trade with {broker_id}: {safe_error.category}")
            raise safe_error
        if success:
            repo.update_trade_ledger_status(
                broker_id,
                "trade",
                trade_id,
                "open",
                {"event": "modified_trade", "stop_loss": stop_loss, "take_profit": take_profit},
            )
        return success

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
        broker = self._require_broker(broker_id)

        try:
            trades = await broker.get_trade_history(count=count, symbol=symbol)
            trade_ledger.reconcile_history(broker_id, trades)
            return trades
        except Exception as e:
            safe_error = self._handle_broker_exception(broker_id, "get_trade_history", e)
            logger.error(f"Failed to get trade history from {broker_id}: {safe_error.category}")
            raise safe_error

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
                "id": broker_id,
                "exists": False,
                "connected": False,
                "is_active": False,
                "capabilities": {},
                "supported_markets": [],
            }

        return self._broker_status_payload(broker_id, broker)


# Global broker manager instance
broker_manager = BrokerManager()
