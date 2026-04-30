"""Alpaca API broker implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

from trading_bot.config import get_logger
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerCapabilities,
    BrokerOrder,
    BrokerPosition,
    OrderSide,
    OrderStatus,
    OrderType,
)

logger = get_logger(__name__)


class AlpacaBroker(BaseBroker):
    """Alpaca API broker implementation."""

    def __init__(self):
        """Initialize Alpaca broker."""
        super().__init__(
            broker_id="alpaca",
            name="Alpaca",
            broker_type="alpaca",
        )
        self.supported_markets = ["stocks", "crypto"]
        self.required_credentials = ["api_key", "api_secret"]
        self.supported_environments = ["paper", "live"]
        self.capabilities = BrokerCapabilities(
            order_history=True,
            close_position=True,
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._api_key: Optional[str] = None
        self._api_secret: Optional[str] = None
        self._base_url: str = "https://paper-api.alpaca.markets/v2"
        self._environment: str = "paper"

    async def connect(self, credentials: Dict[str, str]) -> bool:
        """Connect to Alpaca with API credentials.

        Args:
            credentials: Dictionary containing 'api_key' and 'api_secret'
                        Optional: 'environment' ('paper' or 'live')

        Returns:
            True if connected successfully
        """
        try:
            api_key = credentials.get("api_key")
            api_secret = credentials.get("api_secret")
            environment = credentials.get("environment", "paper")

            if not api_key or not api_secret:
                logger.error("Missing Alpaca API key or secret")
                return False

            self._api_key = api_key
            self._api_secret = api_secret
            self._environment = environment

            # Set base URL based on environment
            if environment == "live":
                self._base_url = "https://api.alpaca.markets/v2"
            else:
                self._base_url = "https://paper-api.alpaca.markets/v2"

            # Create HTTP client
            self._client = httpx.AsyncClient(
                headers={
                    "APCA-API-KEY-ID": api_key,
                    "APCA-API-SECRET-KEY": api_secret,
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

            # Test connection by fetching account details
            response = await self._client.get(f"{self._base_url}/account")
            response.raise_for_status()

            self.connected = True
            logger.info(f"Connected to Alpaca ({environment})")
            return True

        except httpx.HTTPError as e:
            logger.error(f"Failed to connect to Alpaca: HTTP error {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to Alpaca: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from Alpaca."""
        try:
            if self._client:
                await self._client.aclose()
                self._client = None
            self.connected = False
            logger.info("Disconnected from Alpaca")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from Alpaca: {e}")
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
        """Place an order with Alpaca.

        Args:
            symbol: Stock symbol (e.g., 'AAPL') or crypto pair (e.g., 'BTCUSD')
            side: Order side (buy/sell)
            quantity: Order quantity (shares/units)
            order_type: Type of order (market/limit/stop)
            price: Limit price (required for limit orders)

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            # Build order request
            order_data: Dict[str, Any] = {
                "symbol": symbol,
                "side": side.value,
                "type": order_type.value,
                "qty": str(quantity),
                "time_in_force": "day",
            }

            if order_type == OrderType.LIMIT and price:
                order_data["limit_price"] = str(price)

            # Place order
            response = await self._client.post(
                f"{self._base_url}/orders",
                json=order_data,
            )
            response.raise_for_status()
            data = response.json()

            order_id = data.get("id", "")

            order = BrokerOrder(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=self._map_order_status(data.get("status", "new")),
                filled_quantity=float(data.get("filled_qty", 0)),
                avg_fill_price=float(data.get("filled_avg_price", 0)) if data.get("filled_avg_price") else 0.0,
                broker_id=self.broker_id,
                metadata=data,
            )

            logger.info(
                f"Order placed on Alpaca",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
            )

            return order

        except httpx.HTTPError as e:
            logger.error(f"Failed to place order on Alpaca: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to place order on Alpaca: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            response = await self._client.delete(
                f"{self._base_url}/orders/{order_id}"
            )
            response.raise_for_status()
            logger.info(f"Order {order_id} cancelled on Alpaca")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to cancel order {order_id} on Alpaca: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on Alpaca: {e}")
            return False

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions from Alpaca.

        Returns:
            List of BrokerPosition objects
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            response = await self._client.get(f"{self._base_url}/positions")
            response.raise_for_status()
            data = response.json()

            positions = []
            for pos in data:
                qty = float(pos.get("qty", 0))
                if qty == 0:
                    continue

                side = "long" if qty > 0 else "short"
                entry_price = float(pos.get("avg_entry_price", 0))
                current_price = float(pos.get("current_price", 0))
                unrealized_pnl = float(pos.get("unrealized_pl", 0))

                positions.append(
                    BrokerPosition(
                        symbol=pos.get("symbol", ""),
                        side=side,
                        quantity=abs(qty),
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=unrealized_pnl,
                        broker_id=self.broker_id,
                    )
                )

            return positions

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch positions from Alpaca: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch positions from Alpaca: {e}")
            return []

    async def get_balance(self) -> BrokerBalance:
        """Get account balance from Alpaca.

        Returns:
            BrokerBalance object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            response = await self._client.get(f"{self._base_url}/account")
            response.raise_for_status()
            data = response.json()

            return BrokerBalance(
                total_equity=float(data.get("equity", 0)),
                available_margin=float(data.get("buying_power", 0)),
                used_margin=float(data.get("initial_margin", 0)),
                currency="USD",
            )

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch balance from Alpaca: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)
        except Exception as e:
            logger.error(f"Failed to fetch balance from Alpaca: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)

    def _map_order_type(self, raw_type: str) -> OrderType:
        normalized = raw_type.lower()
        if normalized == "market":
            return OrderType.MARKET
        if normalized == "limit":
            return OrderType.LIMIT
        return OrderType.STOP

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow()

    async def get_orders(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from Alpaca."""
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            status_filter = (status or "all").lower()
            status_param = {
                "pending": "open",
                "open": "open",
                "filled": "closed",
                "partially_filled": "closed",
                "cancelled": "closed",
                "canceled": "closed",
                "rejected": "closed",
                "all": "all",
            }.get(status_filter, "all")

            response = await self._client.get(
                f"{self._base_url}/orders",
                params={
                    "status": status_param,
                    "limit": str(count),
                    "direction": "desc",
                },
            )
            response.raise_for_status()
            data = response.json()

            orders: List[BrokerOrder] = []
            for order in data:
                if symbol and order.get("symbol") != symbol:
                    continue

                broker_order = BrokerOrder(
                    order_id=order.get("id", ""),
                    symbol=order.get("symbol", ""),
                    side=OrderSide(order.get("side", "buy")),
                    order_type=self._map_order_type(order.get("type", "market")),
                    quantity=float(order.get("qty", 0) or 0),
                    price=float(order.get("limit_price", 0)) if order.get("limit_price") else None,
                    status=self._map_order_status(order.get("status", "new")),
                    filled_quantity=float(order.get("filled_qty", 0) or 0),
                    avg_fill_price=float(order.get("filled_avg_price", 0)) if order.get("filled_avg_price") else 0.0,
                    created_at=self._parse_timestamp(order.get("created_at")),
                    updated_at=self._parse_timestamp(order.get("updated_at") or order.get("filled_at") or order.get("submitted_at")),
                    broker_id=self.broker_id,
                    metadata=order,
                )
                if status_filter not in ("", "all") and broker_order.status.value != status_filter:
                    continue
                orders.append(broker_order)

            return orders[:count]
        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch orders from Alpaca: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch orders from Alpaca: {e}")
            return []

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get status of a specific order.

        Args:
            order_id: Order ID to check

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to Alpaca")

        try:
            response = await self._client.get(
                f"{self._base_url}/orders/{order_id}"
            )
            response.raise_for_status()
            data = response.json()

            return BrokerOrder(
                order_id=order_id,
                symbol=data.get("symbol", ""),
                side=OrderSide(data.get("side", "buy")),
                order_type=self._map_order_type(data.get("type", "market")),
                quantity=float(data.get("qty", 0)),
                price=float(data.get("limit_price", 0)) if data.get("limit_price") else None,
                status=self._map_order_status(data.get("status", "new")),
                filled_quantity=float(data.get("filled_qty", 0)),
                avg_fill_price=float(data.get("filled_avg_price", 0)) if data.get("filled_avg_price") else 0.0,
                broker_id=self.broker_id,
                metadata=data,
            )

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch order status from Alpaca: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch order status from Alpaca: {e}")
            raise

    def _map_order_status(self, alpaca_status: str) -> OrderStatus:
        """Map Alpaca order status to our OrderStatus enum.

        Args:
            alpaca_status: Alpaca order status string

        Returns:
            OrderStatus enum value
        """
        status_map = {
            "new": OrderStatus.PENDING,
            "partially_filled": OrderStatus.PARTIALLY_FILLED,
            "filled": OrderStatus.FILLED,
            "done_for_day": OrderStatus.FILLED,
            "canceled": OrderStatus.CANCELLED,
            "cancelled": OrderStatus.CANCELLED,
            "expired": OrderStatus.CANCELLED,
            "replaced": OrderStatus.PENDING,
            "pending_cancel": OrderStatus.PENDING,
            "stopped": OrderStatus.REJECTED,
            "rejected": OrderStatus.REJECTED,
            "suspended": OrderStatus.REJECTED,
            "pending_new": OrderStatus.PENDING,
            "calculated": OrderStatus.PENDING,
            "accepted": OrderStatus.OPEN,
            "pending_replace": OrderStatus.PENDING,
            "accepted_for_bidding": OrderStatus.PENDING,
        }
        return status_map.get(alpaca_status.lower(), OrderStatus.PENDING)
