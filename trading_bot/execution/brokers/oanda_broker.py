"""OANDA REST API v20 broker implementation."""

from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

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


class OANDABroker(BaseBroker):
    """OANDA REST API v20 broker implementation."""

    def __init__(self):
        """Initialize OANDA broker."""
        super().__init__(
            broker_id="oanda",
            name="OANDA",
            broker_type="oanda",
        )
        self.supported_markets = ["forex", "cfds"]
        self._client: Optional[httpx.AsyncClient] = None
        self._api_token: Optional[str] = None
        self._account_id: Optional[str] = None
        self._base_url: str = "https://api-fxpractice.oanda.com/v3"
        self._environment: str = "practice"

    async def connect(self, credentials: Dict[str, str]) -> bool:
        """Connect to OANDA with API credentials.

        Args:
            credentials: Dictionary containing 'api_token' and 'account_id'
                        Optional: 'environment' ('practice' or 'live')

        Returns:
            True if connected successfully
        """
        try:
            api_token = credentials.get("api_token")
            account_id = credentials.get("account_id")
            environment = credentials.get("environment", "practice")

            if not api_token or not account_id:
                logger.error("Missing OANDA API token or account ID")
                return False

            self._api_token = api_token
            self._account_id = account_id
            self._environment = environment

            # Set base URL based on environment
            if environment == "live":
                self._base_url = "https://api-fxtrade.oanda.com/v3"
            else:
                self._base_url = "https://api-fxpractice.oanda.com/v3"

            # Create HTTP client
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {api_token}",
                    "Content-Type": "application/json",
                },
                timeout=30.0,
            )

            # Test connection by fetching account details
            response = await self._client.get(
                f"{self._base_url}/accounts/{account_id}"
            )
            response.raise_for_status()

            self.connected = True
            logger.info(f"Connected to OANDA ({environment})")
            return True

        except httpx.HTTPError as e:
            logger.error(f"Failed to connect to OANDA: HTTP error {e}")
            self.connected = False
            return False
        except Exception as e:
            logger.error(f"Failed to connect to OANDA: {e}")
            self.connected = False
            return False

    async def disconnect(self) -> bool:
        """Disconnect from OANDA."""
        try:
            if self._client:
                await self._client.aclose()
                self._client = None
            self.connected = False
            logger.info("Disconnected from OANDA")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting from OANDA: {e}")
            return False

    async def place_order(
        self,
        symbol: str,
        side: OrderSide,
        quantity: float,
        order_type: OrderType = OrderType.MARKET,
        price: Optional[float] = None,
    ) -> BrokerOrder:
        """Place an order with OANDA.

        Args:
            symbol: Currency pair (e.g., 'EUR_USD')
            side: Order side (buy/sell)
            quantity: Order quantity (units)
            order_type: Type of order (market/limit/stop)
            price: Limit price (required for limit orders)

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            # Format symbol for OANDA (replace / with _)
            oanda_symbol = symbol.replace("/", "_")

            # Build order request
            order_request: Dict[str, Any] = {
                "order": {
                    "type": "MARKET" if order_type == OrderType.MARKET else "LIMIT",
                    "instrument": oanda_symbol,
                    "units": str(quantity if side == OrderSide.BUY else -quantity),
                }
            }

            if order_type == OrderType.LIMIT and price:
                order_request["order"]["price"] = str(price)

            # Place order
            response = await self._client.post(
                f"{self._base_url}/accounts/{self._account_id}/orders",
                json=order_request,
            )
            response.raise_for_status()
            data = response.json()

            order_data = data.get("orderCreateTransaction", {})
            order_id = order_data.get("id", "")

            order = BrokerOrder(
                order_id=order_id,
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=quantity,
                price=price,
                status=OrderStatus.PENDING,
                broker_id=self.broker_id,
                metadata=data,
            )

            logger.info(
                f"Order placed on OANDA",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                quantity=quantity,
            )

            return order

        except httpx.HTTPError as e:
            logger.error(f"Failed to place order on OANDA: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to place order on OANDA: {e}")
            raise

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order.

        Args:
            order_id: Order ID to cancel

        Returns:
            True if cancelled successfully
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            response = await self._client.put(
                f"{self._base_url}/accounts/{self._account_id}/orders/{order_id}/cancel"
            )
            response.raise_for_status()
            logger.info(f"Order {order_id} cancelled on OANDA")
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to cancel order {order_id} on OANDA: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to cancel order {order_id} on OANDA: {e}")
            return False

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions from OANDA.

        Returns:
            List of BrokerPosition objects
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/openPositions"
            )
            response.raise_for_status()
            data = response.json()

            positions = []
            for pos in data.get("positions", []):
                instrument = pos.get("instrument", "").replace("_", "/")
                long_units = float(pos.get("long", {}).get("units", 0))
                short_units = float(pos.get("short", {}).get("units", 0))

                if long_units != 0:
                    positions.append(
                        BrokerPosition(
                            symbol=instrument,
                            side="long",
                            quantity=abs(long_units),
                            entry_price=float(
                                pos.get("long", {}).get("averagePrice", 0)
                            ),
                            current_price=0.0,  # Would need separate price fetch
                            unrealized_pnl=float(
                                pos.get("long", {}).get("unrealizedPL", 0)
                            ),
                            broker_id=self.broker_id,
                        )
                    )

                if short_units != 0:
                    positions.append(
                        BrokerPosition(
                            symbol=instrument,
                            side="short",
                            quantity=abs(short_units),
                            entry_price=float(
                                pos.get("short", {}).get("averagePrice", 0)
                            ),
                            current_price=0.0,
                            unrealized_pnl=float(
                                pos.get("short", {}).get("unrealizedPL", 0)
                            ),
                            broker_id=self.broker_id,
                        )
                    )

            return positions

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch positions from OANDA: {e}")
            return []
        except Exception as e:
            logger.error(f"Failed to fetch positions from OANDA: {e}")
            return []

    async def get_balance(self) -> BrokerBalance:
        """Get account balance from OANDA.

        Returns:
            BrokerBalance object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/summary"
            )
            response.raise_for_status()
            data = response.json()

            account = data.get("account", {})

            return BrokerBalance(
                total_equity=float(account.get("balance", 0)),
                available_margin=float(account.get("marginAvailable", 0)),
                used_margin=float(account.get("marginUsed", 0)),
                currency=account.get("currency", "USD"),
            )

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch balance from OANDA: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)
        except Exception as e:
            logger.error(f"Failed to fetch balance from OANDA: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get status of a specific order.

        Args:
            order_id: Order ID to check

        Returns:
            BrokerOrder object
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/orders/{order_id}"
            )
            response.raise_for_status()
            data = response.json()

            order = data.get("order", {})

            return BrokerOrder(
                order_id=order_id,
                symbol=order.get("instrument", "").replace("_", "/"),
                side=OrderSide.BUY if float(order.get("units", 0)) > 0 else OrderSide.SELL,
                order_type=OrderType.MARKET if order.get("type") == "MARKET" else OrderType.LIMIT,
                quantity=abs(float(order.get("units", 0))),
                price=float(order.get("price", 0)) if order.get("price") else None,
                status=self._map_order_status(order.get("state", "PENDING")),
                broker_id=self.broker_id,
                metadata=order,
            )

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch order status from OANDA: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to fetch order status from OANDA: {e}")
            raise

    def _map_order_status(self, oanda_status: str) -> OrderStatus:
        """Map OANDA order status to our OrderStatus enum.

        Args:
            oanda_status: OANDA order status string

        Returns:
            OrderStatus enum value
        """
        status_map = {
            "PENDING": OrderStatus.PENDING,
            "FILLED": OrderStatus.FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELLED_BY_CLIENT": OrderStatus.CANCELLED,
            "CANCELLED_BY_TRADE_CLOSE": OrderStatus.CANCELLED,
        }
        return status_map.get(oanda_status, OrderStatus.PENDING)
