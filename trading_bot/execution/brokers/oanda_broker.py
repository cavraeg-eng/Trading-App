"""OANDA REST API v20 broker implementation."""

import asyncio
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
from trading_bot.execution.broker_manager import BrokerOperationError

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
        self._timeout = httpx.Timeout(connect=10.0, read=25.0, write=25.0, pool=10.0)

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
                timeout=self._timeout,
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
        stop_loss: Optional[float] = None,
        take_profit_1: Optional[float] = None,
        take_profit_2: Optional[float] = None,
        take_profit_3: Optional[float] = None,
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
            normalized_quantity = max(1, int(round(quantity)))

            # Format symbol for OANDA (replace / with _)
            oanda_symbol = symbol.replace("/", "_")

            # Build order request
            order_request: Dict[str, Any] = {
                "order": {
                    "type": "MARKET" if order_type == OrderType.MARKET else "LIMIT",
                    "instrument": oanda_symbol,
                    "units": str(normalized_quantity if side == OrderSide.BUY else -normalized_quantity),
                }
            }

            if order_type == OrderType.LIMIT and price:
                order_request["order"]["price"] = str(price)

            if stop_loss and stop_loss > 0:
                order_request["order"]["stopLossOnFill"] = {"price": str(stop_loss)}

            take_profit_targets = [target for target in [take_profit_1, take_profit_2, take_profit_3] if target and target > 0]
            if take_profit_targets:
                primary_tp = max(take_profit_targets) if side == OrderSide.BUY else min(take_profit_targets)
                order_request["order"]["takeProfitOnFill"] = {"price": str(primary_tp)}

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
                quantity=float(normalized_quantity),
                price=price,
                status=OrderStatus.PENDING,
                stop_loss=stop_loss,
                take_profit_1=take_profit_1,
                take_profit_2=take_profit_2,
                take_profit_3=take_profit_3,
                broker_id=self.broker_id,
                metadata=data,
            )

            logger.info(
                f"Order placed on OANDA",
                order_id=order_id,
                symbol=symbol,
                side=side.value,
                quantity=normalized_quantity,
            )

            return order

        except httpx.TimeoutException as e:
            logger.error(f"Timed out placing order on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"OANDA order request timed out for {symbol}",
                category="timeout",
                status_code=504,
            )
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response is not None else str(e)
            logger.error(f"Failed to place order on OANDA: {detail}")
            raise BrokerOperationError(
                detail=f"OANDA rejected order for {symbol}: {detail}",
                category="rejected",
                status_code=e.response.status_code if e.response is not None else 502,
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to place order on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"OANDA HTTP error placing order for {symbol}: {e}",
                category="http_error",
                status_code=502,
            )
        except asyncio.TimeoutError as e:
            logger.error(f"Async timeout placing order on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"OANDA async timeout placing order for {symbol}",
                category="timeout",
                status_code=504,
            )
        except Exception as e:
            logger.error(f"Failed to place order on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"Unexpected OANDA error placing order for {symbol}: {e}",
                category="unexpected_error",
                status_code=502,
            )

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
                f"{self._base_url}/accounts/{self._account_id}/openTrades"
            )
            response.raise_for_status()
            data = response.json()

            trades = data.get("trades", [])
            instruments = list(
                dict.fromkeys(
                    trade.get("instrument", "")
                    for trade in trades
                    if trade.get("instrument")
                )
            )

            current_prices: dict = {}
            if instruments:
                try:
                    price_resp = await self._client.get(
                        f"{self._base_url}/accounts/{self._account_id}/pricing",
                        params={"instruments": ",".join(instruments)},
                    )
                    price_resp.raise_for_status()
                    for p in price_resp.json().get("prices", []):
                        inst = p.get("instrument", "")
                        # mid-price = (best ask + best bid) / 2
                        asks = p.get("asks", [])
                        bids = p.get("bids", [])
                        if asks and bids:
                            mid = (float(asks[0]["price"]) + float(bids[0]["price"])) / 2
                            current_prices[inst] = mid
                except Exception as e:
                    logger.warning(f"Could not fetch live prices: {e}")

            positions = []
            for trade in trades:
                instrument_raw = trade.get("instrument", "")
                current_units = float(trade.get("currentUnits", 0) or 0)
                if not instrument_raw or current_units == 0:
                    continue

                instrument = instrument_raw.replace("_", "/")
                cur_price = current_prices.get(instrument_raw, 0.0)
                positions.append(
                    BrokerPosition(
                        symbol=instrument,
                        side="long" if current_units > 0 else "short",
                        quantity=abs(current_units),
                        entry_price=float(trade.get("price", 0) or 0),
                        current_price=cur_price,
                        unrealized_pnl=float(trade.get("unrealizedPL", 0) or 0),
                        broker_id=self.broker_id,
                        position_id=str(trade.get("id", "") or "") or None,
                        opened_at=trade.get("openTime"),
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

    def _map_order_type(self, oanda_type: str) -> OrderType:
        normalized = oanda_type.upper()
        if normalized == "MARKET":
            return OrderType.MARKET
        if normalized == "LIMIT":
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
        """Get recent orders from OANDA."""
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            status_map = {
                "pending": "PENDING",
                "open": "PENDING",
                "filled": "FILLED",
                "cancelled": "CANCELLED",
                "canceled": "CANCELLED",
                "all": "ALL",
            }
            params: Dict[str, str] = {
                "count": str(count),
                "state": status_map.get((status or "all").lower(), "ALL"),
            }
            if symbol:
                params["instrument"] = symbol.replace("/", "_")

            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/orders",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            transactions_response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/transactions",
                params={"count": str(min(max(count * 3, 10), 200)), "type": "ORDER_FILL"},
            )
            transactions_response.raise_for_status()
            transactions_data = transactions_response.json()
            fill_map: Dict[str, Dict[str, Any]] = {}
            for transaction in transactions_data.get("transactions", []):
                order_id = transaction.get("orderID")
                if order_id:
                    fill_map[str(order_id)] = transaction

            orders: List[BrokerOrder] = []
            for order in data.get("orders", []):
                raw_status = order.get("state", "PENDING")
                units = float(order.get("units", 0) or 0)
                raw_price = order.get("price") or order.get("priceBound")
                fill = fill_map.get(str(order.get("id", "")), {})
                fill_price = fill.get("fullPrice") or fill.get("price")
                price = float(fill_price) if fill_price else (float(raw_price) if raw_price else None)
                filled_quantity = abs(float(fill.get("units", units) or 0)) if raw_status == "FILLED" else 0.0
                updated_at = (
                    fill.get("time")
                    or order.get("filledTime")
                    or order.get("cancelledTime")
                    or order.get("createTime")
                )

                orders.append(
                    BrokerOrder(
                        order_id=order.get("id", ""),
                        symbol=order.get("instrument", "").replace("_", "/"),
                        side=OrderSide.BUY if units >= 0 else OrderSide.SELL,
                        order_type=self._map_order_type(order.get("type", "MARKET")),
                        quantity=abs(units),
                        price=price,
                        status=self._map_order_status(raw_status),
                        filled_quantity=filled_quantity,
                        avg_fill_price=price if raw_status == "FILLED" and price is not None else 0.0,
                        created_at=self._parse_timestamp(order.get("createTime")),
                        updated_at=self._parse_timestamp(updated_at),
                        broker_id=self.broker_id,
                        metadata={**order, "fill_transaction": fill},
                    )
                )

            return orders[:count]
        except Exception as e:
            logger.error(f"Failed to fetch orders from OANDA: {e}")
            return []

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
                order_type=self._map_order_type(order.get("type", "MARKET")),
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

    async def close_position(
        self,
        symbol: str,
        position_id: Optional[str] = None,
    ) -> bool:
        """Close an open position or trade on OANDA.

        Args:
            symbol: Trading symbol (e.g. 'EUR/USD')
            position_id: Optional OANDA trade ID for closing a specific trade

        Returns:
            True if closed successfully
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            if position_id:
                response = await self._client.put(
                    f"{self._base_url}/accounts/{self._account_id}/trades/{position_id}/close",
                    json={"units": "ALL"},
                )
                response.raise_for_status()
                logger.info("Trade closed on OANDA", symbol=symbol, position_id=position_id)
                return True

            oanda_symbol = symbol.replace("/", "_")

            positions = await self.get_positions()
            body: dict = {}
            for pos in positions:
                if pos.symbol == symbol:
                    if pos.side == "long":
                        body["longUnits"] = "ALL"
                    elif pos.side == "short":
                        body["shortUnits"] = "ALL"

            if not body:
                logger.warning(f"No open position found for {symbol}")
                return False

            response = await self._client.put(
                f"{self._base_url}/accounts/{self._account_id}/positions/{oanda_symbol}/close",
                json=body,
            )
            response.raise_for_status()
            logger.info(f"Position closed on OANDA", symbol=symbol)
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to close position on OANDA: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to close position on OANDA: {e}")
            return False

    async def get_trade_history(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
    ) -> List[dict]:
        """Get closed trade history from OANDA.

        Args:
            count: Number of trades to fetch
            symbol: Optional symbol filter

        Returns:
            List of trade dictionaries
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            params: dict = {"state": "CLOSED", "count": str(count)}
            if symbol:
                params["instrument"] = symbol.replace("/", "_")

            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/trades",
                params=params,
            )
            response.raise_for_status()
            data = response.json()

            trades = []
            for t in data.get("trades", []):
                trades.append({
                    "trade_id": t.get("id", ""),
                    "symbol": t.get("instrument", "").replace("_", "/"),
                    "side": "buy" if float(t.get("initialUnits", 0)) > 0 else "sell",
                    "quantity": abs(float(t.get("initialUnits", 0))),
                    "entry_price": float(t.get("price", 0)),
                    "exit_price": float(t.get("averageClosePrice", 0)),
                    "realized_pnl": float(t.get("realizedPL", 0)),
                    "opened_at": t.get("openTime", ""),
                    "closed_at": t.get("closeTime", ""),
                    "state": t.get("state", "CLOSED"),
                })
            return trades

        except Exception as e:
            logger.error(f"Failed to fetch trade history from OANDA: {e}")
            return []
