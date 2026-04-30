"""OANDA REST API v20 broker implementation."""

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

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
from trading_bot.execution.broker_manager import BrokerOperationError

logger = get_logger(__name__)

_MISS = object()  # cache miss sentinel


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
        self.required_credentials = ["api_token", "account_id"]
        self.supported_environments = ["practice", "live"]
        self.capabilities = BrokerCapabilities(
            bracket_orders=True,
            order_history=True,
            trade_history=True,
            close_position=True,
            modify_trade=True,
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._api_token: Optional[str] = None
        self._account_id: Optional[str] = None
        self._base_url: str = "https://api-fxpractice.oanda.com/v3"
        self._environment: str = "practice"
        self._timeout = httpx.Timeout(connect=10.0, read=25.0, write=25.0, pool=10.0)

        # Simple TTL cache: {key: (timestamp, data)}
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl: float = 10.0
        self._cache_stale_ttl: float = 45.0
        self._cache_lock = asyncio.Lock()
        self._cache_refreshing: set = set()  # keys currently being refreshed

    def _cache_get(self, key: str) -> Any:
        """Return cached value if still fresh, else None sentinel."""
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry[0]) < self._cache_ttl:
            return entry[1]
        return _MISS

    def _cache_get_stale(self, key: str) -> Any:
        """Return cached value even if stale (within stale_ttl), else _MISS."""
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry[0]) < self._cache_stale_ttl:
            return entry[1]
        return _MISS

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    def _cache_invalidate(self, *keys: str) -> None:
        """Remove specific keys, or all if no keys given."""
        if keys:
            for k in keys:
                self._cache.pop(k, None)
        else:
            self._cache.clear()

    def _to_float(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    def _extract_price(self, payload: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                parsed = self._to_float(value.get("price"))
            else:
                parsed = self._to_float(value)
            if parsed is not None:
                return parsed
        return None

    def _extract_trade_stop_loss(self, trade: Dict[str, Any]) -> Optional[float]:
        return self._extract_price(
            trade,
            "stopLossOrder",
            "stopLossOnFill",
            "stopLoss",
            "stop_loss",
        )

    def _extract_trade_take_profit(self, trade: Dict[str, Any]) -> Optional[float]:
        return self._extract_price(
            trade,
            "takeProfitOrder",
            "takeProfitOnFill",
            "takeProfit",
            "take_profit",
        )

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
            self._cache_invalidate()
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
            self._cache_invalidate()
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

            # Invalidate caches after order placement
            self._cache_invalidate()
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
            self._cache_invalidate()
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
        cached = self._cache_get('positions')
        if cached is not _MISS:
            return cached

        # Return stale data immediately if available, refresh in background
        stale = self._cache_get_stale('positions')
        if stale is not _MISS and 'positions' not in self._cache_refreshing:
            self._cache_refreshing.add('positions')
            asyncio.get_event_loop().create_task(self._refresh_positions())
            return stale

        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        return await self._fetch_positions_from_oanda()

    async def _refresh_positions(self):
        """Background refresh of positions cache."""
        try:
            await self._fetch_positions_from_oanda()
        except Exception as e:
            logger.warning(f"Background position refresh failed: {e}")
        finally:
            self._cache_refreshing.discard('positions')

    async def _fetch_positions_from_oanda(self) -> List[BrokerPosition]:
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
                entry_price = float(trade.get("price", 0) or 0)
                cur_price = current_prices.get(instrument_raw, entry_price)
                positions.append(
                    BrokerPosition(
                        symbol=instrument,
                        side="long" if current_units > 0 else "short",
                        quantity=abs(current_units),
                        entry_price=entry_price,
                        current_price=cur_price,
                        unrealized_pnl=float(trade.get("unrealizedPL", 0) or 0),
                        broker_id=self.broker_id,
                        position_id=str(trade.get("id", "") or "") or None,
                        opened_at=trade.get("openTime"),
                    )
                )

            self._cache_set('positions', positions)
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
        cached = self._cache_get('balance')
        if cached is not _MISS:
            return cached

        # Return stale data immediately if available
        stale = self._cache_get_stale('balance')
        if stale is not _MISS and 'balance' not in self._cache_refreshing:
            self._cache_refreshing.add('balance')
            asyncio.get_event_loop().create_task(self._refresh_balance())
            return stale

        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/summary"
            )
            response.raise_for_status()
            data = response.json()

            account = data.get("account", {})

            result = BrokerBalance(
                total_equity=float(account.get("balance", 0)),
                available_margin=float(account.get("marginAvailable", 0)),
                used_margin=float(account.get("marginUsed", 0)),
                currency=account.get("currency", "USD"),
            )
            self._cache_set('balance', result)
            return result

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch balance from OANDA: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)
        except Exception as e:
            logger.error(f"Failed to fetch balance from OANDA: {e}")
            return BrokerBalance(total_equity=0, available_margin=0, used_margin=0)

    async def _refresh_balance(self):
        """Background refresh of balance cache."""
        try:
            if not self.connected or not self._client:
                return
            response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/summary"
            )
            response.raise_for_status()
            account = response.json().get("account", {})
            result = BrokerBalance(
                total_equity=float(account.get("balance", 0)),
                available_margin=float(account.get("marginAvailable", 0)),
                used_margin=float(account.get("marginUsed", 0)),
                currency=account.get("currency", "USD"),
            )
            self._cache_set('balance', result)
        except Exception as e:
            logger.warning(f"Background balance refresh failed: {e}")
        finally:
            self._cache_refreshing.discard('balance')

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

    def _order_sort_timestamp(self, order: BrokerOrder) -> float:
        try:
            return order.updated_at.timestamp()
        except Exception:
            return 0.0

    async def get_orders(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from OANDA."""
        cache_key = f'orders:{count}:{symbol}:{status}'
        cached = self._cache_get(cache_key)
        if cached is not _MISS:
            return cached

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
                        stop_loss=self._extract_price(order, "stopLossOnFill", "stopLossOrder", "stopLoss"),
                        take_profit_1=self._extract_price(order, "takeProfitOnFill", "takeProfitOrder", "takeProfit"),
                        created_at=self._parse_timestamp(order.get("createTime")),
                        updated_at=self._parse_timestamp(updated_at),
                        broker_id=self.broker_id,
                        metadata={**order, "fill_transaction": fill},
                    )
                )

            trade_response = await self._client.get(
                f"{self._base_url}/accounts/{self._account_id}/openTrades",
            )
            trade_response.raise_for_status()
            for trade in trade_response.json().get("trades", []):
                trade_symbol = trade.get("instrument", "").replace("_", "/")
                if symbol and trade_symbol != symbol:
                    continue
                stop_loss = self._extract_trade_stop_loss(trade)
                take_profit = self._extract_trade_take_profit(trade)
                if stop_loss is None and take_profit is None:
                    continue
                trade_units = float(trade.get("currentUnits", trade.get("initialUnits", 0)) or 0)
                if trade_units == 0:
                    continue
                entry_price = float(trade.get("price", 0) or 0)
                trade_id = str(trade.get("id", "") or "")
                take_profit_order = trade.get("takeProfitOrder")
                updated_at = (
                    take_profit_order.get("createTime")
                    if isinstance(take_profit_order, dict)
                    else trade.get("openTime")
                )
                orders.append(
                    BrokerOrder(
                        order_id=f"trade:{trade_id}" if trade_id else f"trade:{trade_symbol}",
                        symbol=trade_symbol,
                        side=OrderSide.BUY if trade_units > 0 else OrderSide.SELL,
                        order_type=OrderType.MARKET,
                        quantity=abs(trade_units),
                        price=entry_price,
                        status=OrderStatus.OPEN,
                        filled_quantity=abs(trade_units),
                        avg_fill_price=entry_price,
                        stop_loss=stop_loss,
                        take_profit_1=take_profit,
                        broker_id=self.broker_id,
                        created_at=self._parse_timestamp(trade.get("openTime")),
                        updated_at=self._parse_timestamp(updated_at),
                        metadata={"trade": trade},
                    )
                )

            result = sorted(
                orders,
                key=lambda order: (
                    order.status == OrderStatus.OPEN,
                    self._order_sort_timestamp(order),
                ),
                reverse=True,
            )[:count]
            self._cache_set(cache_key, result)
            return result
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
                stop_loss=self._extract_price(order, "stopLossOnFill", "stopLossOrder", "stopLoss"),
                take_profit_1=self._extract_price(order, "takeProfitOnFill", "takeProfitOrder", "takeProfit"),
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
            "OPEN": OrderStatus.OPEN,
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
                self._cache_invalidate()  # Invalidate after close-by-ID
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
            self._cache_invalidate()  # Invalidate after close
            return True
        except httpx.HTTPError as e:
            logger.error(f"Failed to close position on OANDA: {e}")
            return False
        except Exception as e:
            logger.error(f"Failed to close position on OANDA: {e}")
            return False

    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify stop loss and/or take profit on an open OANDA trade.

        Uses OANDA v20 PUT /accounts/{id}/trades/{tradeId}/orders endpoint.

        Args:
            trade_id: OANDA trade ID
            stop_loss: New stop loss price (None to leave unchanged, 0 to remove)
            take_profit: New take profit price (None to leave unchanged, 0 to remove)

        Returns:
            True if modification was successful
        """
        if not self.connected or not self._client:
            raise RuntimeError("Not connected to OANDA")

        try:
            body: Dict[str, Any] = {}

            if stop_loss is not None:
                if stop_loss > 0:
                    body["stopLoss"] = {"price": str(stop_loss)}
                else:
                    # Setting to 0 means remove SL
                    body["stopLoss"] = None

            if take_profit is not None:
                if take_profit > 0:
                    body["takeProfit"] = {"price": str(take_profit)}
                else:
                    body["takeProfit"] = None

            if not body:
                logger.warning(f"modify_trade called with no changes for trade {trade_id}")
                return True

            response = await self._client.put(
                f"{self._base_url}/accounts/{self._account_id}/trades/{trade_id}/orders",
                json=body,
            )
            response.raise_for_status()
            logger.info(
                "Trade modified on OANDA",
                trade_id=trade_id,
                stop_loss=stop_loss,
                take_profit=take_profit,
            )
            self._cache_invalidate()
            return True
        except httpx.HTTPStatusError as e:
            detail = e.response.text[:500] if e.response is not None else str(e)
            logger.error(f"Failed to modify trade {trade_id} on OANDA: {detail}")
            raise BrokerOperationError(
                detail=f"OANDA rejected trade modification for {trade_id}: {detail}",
                category="rejected",
                status_code=e.response.status_code if e.response is not None else 502,
            )
        except httpx.HTTPError as e:
            logger.error(f"Failed to modify trade {trade_id} on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"OANDA HTTP error modifying trade {trade_id}: {e}",
                category="http_error",
                status_code=502,
            )
        except Exception as e:
            logger.error(f"Failed to modify trade {trade_id} on OANDA: {e}")
            raise BrokerOperationError(
                detail=f"Unexpected error modifying trade {trade_id}: {e}",
                category="unexpected_error",
                status_code=502,
            )

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
        cache_key = f'history:{count}:{symbol}'
        cached = self._cache_get(cache_key)
        if cached is not _MISS:
            return cached

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
            self._cache_set(cache_key, trades)
            return trades

        except Exception as e:
            logger.error(f"Failed to fetch trade history from OANDA: {e}")
            return []
