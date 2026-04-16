"""CCXT-based broker implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import ccxt.async_support as ccxt

from trading_bot.config import get_logger
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    OrderType,
)

logger = get_logger(__name__)


class CCXTBroker(BaseBroker):
    """CCXT-based broker implementation for crypto exchanges."""

    def __init__(self, exchange_id: str):
        """Initialize CCXT broker.

        Args:
            exchange_id: Exchange identifier (e.g., 'binance', 'bybit', 'okx', 'kraken')
        """
        super().__init__(
            broker_id=exchange_id,
            name=exchange_id.capitalize(),
            broker_type="ccxt",
        )
        self.exchange_id = exchange_id
        self.supported_markets = ["crypto", "futures"]
        self.exchange: Optional[Any] = None
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None

    async def connect(self, credentials: Dict[str, str]) -> bool:
        """Connect to the exchange with API credentials.

        Args:
            credentials: Dictionary containing 'api_key' and 'api_secret'

        Returns:
            True if connected successfully
        """
        try:
            api_key = credentials.get("api_key")
            api_secret = credentials.get("api_secret")
            sandbox = credentials.get("sandbox", "true").lower() == "true"

            if not api_key or not api_secret:
                logger.error(f"Missing API credentials for {self.exchange_id}")
                return False

            self._api_key = api_key
            self._api_secret = api_secret

            # Get exchange class from ccxt
            exchange_class = getattr(ccxt, self.exchange_id, None)
            if not exchange_class:
                logger.error(f"Exchange {self.exchange_id} not supported by CCXT")
                return False

            # Initialize exchange
            config = {
                "apiKey": api_key,
                "secret": api_secret,
                "enableRateLimit": True,
                "options": {},
            }

            # Set sandbox mode for supported exchanges
            if sandbox:
                config["sandbox"] = True
                config["options"]["defaultType"] = "future"  # Use futures testnet

            self.exchange = exchange_class(config)

            # Test connection by loading markets
            await self.exchange.load_markets()

            self.connected = True
            logger.info(f"Connected to {self.exchange_id}")
            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_id}: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from the exchange."""
        try:
            if self.exchange:
                await self.exchange.close()
                self.exchange = None
            self.connected = False
            logger.info(f"Disconnected from {self.exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from {self.exchange_id}: {e}")
            return False

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
        """Place an order on the exchange.

        Args:
            symbol: Trading pair symbol (e.g., 'BTC/USDT')
            side: Order side (buy/sell)
            quantity: Order quantity
            order_type: Type of order (market/limit/stop)
            price: Limit price (required for limit orders)

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            ccxt_side = side.value
            ccxt_type = order_type.value

            # Place order through CCXT
            order_response = await self.exchange.create_order(
                symbol=symbol,
                type=ccxt_type,
                side=ccxt_side,
                amount=quantity,
                price=price,
            )

            # Map CCXT response to BrokerOrder
            order = BrokerOrder(
                order_id=str(order_response.get("id", "")),
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=self._map_order_status(order_response.get("status", "open")),
                filled_quantity=float(order_response.get("filled", 0.0)),
                avg_fill_price=float(order_response.get("average", 0.0)) if order_response.get("average") else 0.0,
                broker_id=self.broker_id,
                metadata=order_response,
            )

            logger.info(
                f"Order placed on {self.exchange_id}",
                order_id=order.order_id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
            )

            return order

        except Exception as e:
            logger.error(f"Failed to place order on {self.exchange_id}: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            # Note: CCXT requires symbol for cancel_order
            # We need to fetch the order first to get the symbol
            # For now, we'll try to cancel without symbol (some exchanges support this)
            await self.exchange.cancel_order(order_id)
            logger.info(f"Order {order_id} cancelled on {self.exchange_id}")
            return True
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on {self.exchange_id}: {e}")
            return False

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions from the exchange.

        Returns:
            List of BrokerPosition objects
        """
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            positions = await self.exchange.fetch_positions()
            broker_positions = []

            for pos in positions:
                contracts = float(pos.get("contracts", 0))
                if contracts == 0:
                    continue

                side = "long" if contracts > 0 else "short"
                entry_price = float(pos.get("entryPrice", 0.0) or 0.0)
                current_price = float(pos.get("markPrice", entry_price) or entry_price)
                unrealized_pnl = float(pos.get("unrealizedPnl", 0.0) or 0.0)

                broker_positions.append(
                    BrokerPosition(
                        symbol=pos.get("symbol", ""),
                        side=side,
                        quantity=abs(contracts),
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        broker_id=self.broker_id,
                    )
                )

            return broker_positions

        except Exception as e:
            logger.error(f"Failed to fetch positions from {self.exchange_id}: {e}")
            return []

    async def get_balance(self) -> BrokerBalance:
        """Get account balance from the exchange.

        Returns:
            BrokerBalance object
        """
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            balance_response = await self.exchange.fetch_balance()

            total = float(balance_response.get("total", {}).get("USDT", 0))
            free = float(balance_response.get("free", {}).get("USDT", 0))
            used = float(balance_response.get("used", {}).get("USDT", 0))

            # If no USDT balance, try to calculate from all assets
            if total == 0:
                for asset, amount in balance_response.get("total", {}).items():
                    if amount and amount > 0:
                        total += float(amount)
                for asset, amount in balance_response.get("free", {}).items():
                    if amount and amount > 0:
                        free += float(amount)
                for asset, amount in balance_response.get("used", {}).items():
                    if amount and amount > 0:
                        used += float(amount)

            return BrokerBalance(
                total_equity=total,
                available_margin=free,
                used_margin=used,
                currency="USDT",
            )

        except Exception as e:
            logger.error(f"Failed to fetch balance from {self.exchange_id}: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)

    def _map_order_type(self, raw_type: str) -> OrderType:
        normalized = raw_type.lower()
        if normalized == "market":
            return OrderType.MARKET
        if normalized == "limit":
            return OrderType.LIMIT
        return OrderType.STOP

    def _parse_timestamp(self, value: Any) -> datetime:
        if isinstance(value, (int, float)):
            return datetime.utcfromtimestamp(float(value) / 1000)
        if isinstance(value, str):
            try:
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            except ValueError:
                return datetime.utcnow()
        return datetime.utcnow()

    def _to_broker_order(self, order_response: Dict[str, Any]) -> BrokerOrder:
        created_at = order_response.get("timestamp") or order_response.get("datetime")
        updated_at = (
            order_response.get("lastTradeTimestamp")
            or order_response.get("lastUpdateTimestamp")
            or created_at
        )

        return BrokerOrder(
            order_id=str(order_response.get("id", "")),
            symbol=order_response.get("symbol", ""),
            side=OrderSide(order_response.get("side", "buy")),
            order_type=self._map_order_type(order_response.get("type", "market")),
            quantity=float(order_response.get("amount", 0.0) or 0.0),
            price=float(order_response.get("price", 0.0)) if order_response.get("price") else None,
            status=self._map_order_status(order_response.get("status", "open")),
            filled_quantity=float(order_response.get("filled", 0.0) or 0.0),
            avg_fill_price=float(order_response.get("average", 0.0)) if order_response.get("average") else 0.0,
            created_at=self._parse_timestamp(created_at),
            updated_at=self._parse_timestamp(updated_at),
            broker_id=self.broker_id,
            metadata=order_response,
        )

    async def get_orders(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from the exchange."""
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            normalized_status = (status or "").lower()

            if normalized_status in {"pending", "open"}:
                raw_orders = await self.exchange.fetch_open_orders(symbol, None, count)
            elif normalized_status in {"filled", "cancelled", "canceled", "rejected"}:
                raw_orders = await self.exchange.fetch_closed_orders(symbol, None, count)
            else:
                try:
                    raw_orders = await self.exchange.fetch_orders(symbol, None, count)
                except Exception:
                    open_orders = await self.exchange.fetch_open_orders(symbol, None, count)
                    try:
                        closed_orders = await self.exchange.fetch_closed_orders(symbol, None, count)
                    except Exception:
                        closed_orders = []
                    raw_orders = [*open_orders, *closed_orders]

            orders = [self._to_broker_order(order_response) for order_response in raw_orders]
            if normalized_status:
                orders = [order for order in orders if order.status.value == normalized_status]
            return orders[:count]
        except Exception as e:
            logger.error(f"Failed to fetch orders from {self.exchange_id}: {e}")
            return []

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get status of a specific order.

        Args:
            order_id: Order ID to check

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self.exchange:
            raise RuntimeError(f"Not connected to {self.exchange_id}")

        try:
            # Note: CCXT requires symbol for fetch_order
            # We'll need to handle this differently or store symbol with order
            order_response = await self.exchange.fetch_order(order_id)

            return self._to_broker_order(order_response)

        except Exception as e:
            logger.error(f"Failed to fetch order status from {self.exchange_id}: {e}")
            raise

    def _map_order_status(self, ccxt_status: str) -> OrderStatus:
        """Map CCXT order status to our OrderStatus enum.

        Args:
            ccxt_status: CCXT order status string

        Returns:
            OrderStatus enum value
        """
        status_map = {
            "open": OrderStatus.OPEN,
            "closed": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "pending": OrderStatus.PENDING,
            "rejected": OrderStatus.REJECTED,
        }
        return status_map.get(ccxt_status.lower(), OrderStatus.PENDING)
