"""OANDA REST API v20 broker implementation."""

from __future__ import annotations

import asyncio
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from trading_bot.config import TradingMode, get_logger, get_settings
from trading_bot.execution.broker_base import (
    BaseBroker,
    BrokerBalance,
    BrokerCapabilities,
    BrokerConfigurationError,
    BrokerOrder,
    BrokerPosition,
    BrokerQuote,
    OrderSide,
    OrderStatus,
    OrderType,
)
from trading_bot.execution.broker_manager import BrokerOperationError

logger = get_logger(__name__)

_MISS = object()
_PRACTICE_URL = "https://api-fxpractice.oanda.com/v3"
_LIVE_URL = "https://api-fxtrade.oanda.com/v3"
_TRANSIENT_STATUS_CODES = {408, 429, 500, 502, 503, 504}


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
            stop_orders=True,
            bracket_orders=True,
            order_history=True,
            trade_history=True,
            close_position=True,
            modify_trade=True,
            quotes=True,
        )
        self._client: Optional[httpx.AsyncClient] = None
        self._api_token: Optional[str] = None
        self._account_id: Optional[str] = None
        self._base_url: str = _PRACTICE_URL
        self._environment: str = "practice"
        self._timeout = httpx.Timeout(connect=10.0, read=25.0, write=25.0, pool=10.0)
        self._cache: Dict[str, Tuple[float, Any]] = {}
        self._cache_ttl: float = 10.0
        self._cache_stale_ttl: float = 45.0
        self._cache_refreshing: set[str] = set()

    def prepare_credentials(self, credentials: Dict[str, Any]) -> Dict[str, str]:
        """Validate OANDA credentials and enforce explicit live opt-in."""
        missing = [
            field_name
            for field_name in self.required_credentials
            if not credentials.get(field_name)
        ]
        if missing:
            raise BrokerConfigurationError(
                detail=f"Broker '{self.broker_id}' requires {', '.join(missing)}",
                category="missing_credentials",
            )

        environment = self._normalize_environment(credentials.get("environment"))
        if environment == "live" and not self._live_mode_explicitly_enabled(credentials):
            raise BrokerConfigurationError(
                detail=(
                    "OANDA live environment requires explicit live configuration. "
                    "Set TRADING_MODE=live or pass live_trading_enabled=true."
                ),
                category="live_mode_not_enabled",
            )

        return {
            "api_token": str(credentials["api_token"]),
            "account_id": str(credentials["account_id"]),
            "environment": environment,
            "_oanda_credentials_validated": "true",
        }

    def _normalize_environment(self, environment: Any) -> str:
        value = str(environment or "practice").strip().lower()
        aliases = {
            "paper": "practice",
            "sandbox": "practice",
            "demo": "practice",
            "fxpractice": "practice",
            "fxtrade": "live",
            "production": "live",
            "prod": "live",
        }
        normalized = aliases.get(value, value)
        if normalized not in self.supported_environments:
            raise BrokerConfigurationError(
                detail=(
                    "Unsupported OANDA environment. Use 'practice' for paper trading "
                    "or 'live' with explicit live configuration."
                ),
                category="invalid_environment",
            )
        return normalized

    def _live_mode_explicitly_enabled(self, credentials: Dict[str, Any]) -> bool:
        live_flags = (
            credentials.get("live_trading_enabled"),
            credentials.get("live_confirmed"),
            credentials.get("confirm_live"),
            credentials.get("allow_live"),
        )
        if any(str(flag).strip().lower() in {"1", "true", "yes", "y", "on"} for flag in live_flags):
            return True
        return get_settings().trading_mode == TradingMode.LIVE

    def _create_client(self, api_token: str) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=self._timeout,
        )

    def _cache_get(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry[0]) < self._cache_ttl:
            return entry[1]
        return _MISS

    def _cache_get_stale(self, key: str) -> Any:
        entry = self._cache.get(key)
        if entry and (time.monotonic() - entry[0]) < self._cache_stale_ttl:
            return entry[1]
        return _MISS

    def _cache_set(self, key: str, value: Any) -> None:
        self._cache[key] = (time.monotonic(), value)

    def _cache_invalidate(self, *keys: str) -> None:
        if keys:
            for key in keys:
                self._cache.pop(key, None)
        else:
            self._cache.clear()

    def _redact(self, value: Any) -> str:
        text = str(value)
        for secret in (self._api_token, self._account_id):
            if secret:
                text = text.replace(secret, "[REDACTED]")
        return text

    def _safe_error_detail(self, response: Optional[httpx.Response]) -> str:
        if response is None:
            return "OANDA returned an error without a response body"

        detail = ""
        try:
            payload = response.json()
        except ValueError:
            detail = response.text
        else:
            candidates = [
                payload.get("errorMessage"),
                payload.get("errorCode"),
                payload.get("rejectReason"),
                payload.get("message"),
            ]
            detail = " - ".join(str(candidate) for candidate in candidates if candidate)
            if not detail:
                detail = str(payload)

        return self._redact(detail[:500]) or f"OANDA HTTP {response.status_code}"

    def _operation_error(
        self,
        *,
        operation: str,
        category: str,
        status_code: int,
        detail: str,
    ) -> BrokerOperationError:
        return BrokerOperationError(
            detail=f"OANDA {operation} failed: {self._redact(detail)}",
            category=category,
            status_code=status_code,
        )

    def _raise_for_status(self, response: httpx.Response, operation: str) -> None:
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            category = "rate_limited" if response.status_code == 429 else "rejected"
            raise self._operation_error(
                operation=operation,
                category=category,
                status_code=response.status_code,
                detail=self._safe_error_detail(exc.response),
            ) from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        operation: str,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        retry_safe: bool = True,
    ) -> Dict[str, Any]:
        if not self.connected or not self._client:
            raise BrokerOperationError(
                detail="OANDA broker is not connected",
                category="not_connected",
                status_code=400,
            )

        attempts = 3 if retry_safe and method.upper() in {"GET", "PUT", "DELETE"} else 1
        last_error: Optional[Exception] = None

        for attempt in range(attempts):
            try:
                response = await self._client.request(
                    method,
                    f"{self._base_url}{path}",
                    params=params,
                    json=json,
                )
                if response.status_code in _TRANSIENT_STATUS_CODES and attempt < attempts - 1:
                    await asyncio.sleep(0.2 * (2**attempt))
                    continue
                self._raise_for_status(response, operation)
                if response.content:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise self._operation_error(
                            operation=operation,
                            category="invalid_response",
                            status_code=502,
                            detail="OANDA returned malformed JSON",
                        ) from exc
                return {}
            except httpx.TimeoutException as exc:
                last_error = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(0.2 * (2**attempt))
                    continue
                raise self._operation_error(
                    operation=operation,
                    category="timeout",
                    status_code=504,
                    detail="request timed out",
                ) from exc
            except httpx.TransportError as exc:
                last_error = exc
                if attempt < attempts - 1:
                    await asyncio.sleep(0.2 * (2**attempt))
                    continue
                raise self._operation_error(
                    operation=operation,
                    category="http_error",
                    status_code=502,
                    detail=str(exc),
                ) from exc

        raise self._operation_error(
            operation=operation,
            category="http_error",
            status_code=502,
            detail=str(last_error or "request failed"),
        )

    def _to_float(self, value: Any, default: float = 0.0) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _positive_float(self, value: Any) -> Optional[float]:
        parsed = self._to_float(value, default=0.0)
        return parsed if parsed > 0 else None

    def _extract_price(self, payload: Dict[str, Any], *keys: str) -> Optional[float]:
        for key in keys:
            value = payload.get(key)
            if isinstance(value, dict):
                parsed = self._positive_float(value.get("price"))
            else:
                parsed = self._positive_float(value)
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

    def _format_instrument(self, symbol: str) -> str:
        return symbol.replace("/", "_").upper()

    def _display_symbol(self, instrument: str) -> str:
        return instrument.replace("_", "/")

    def _parse_timestamp(self, value: Optional[str]) -> datetime:
        if not value:
            return datetime.utcnow()
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return datetime.utcnow()

    def _map_order_type(self, oanda_type: str) -> OrderType:
        normalized = str(oanda_type or "MARKET").upper()
        if normalized == "LIMIT":
            return OrderType.LIMIT
        if normalized == "STOP":
            return OrderType.STOP
        return OrderType.MARKET

    def _map_order_status(self, oanda_status: str) -> OrderStatus:
        status_map = {
            "PENDING": OrderStatus.PENDING,
            "OPEN": OrderStatus.OPEN,
            "FILLED": OrderStatus.FILLED,
            "PARTIALLY_FILLED": OrderStatus.PARTIALLY_FILLED,
            "CANCELLED": OrderStatus.CANCELLED,
            "CANCELED": OrderStatus.CANCELLED,
            "CANCELLED_BY_CLIENT": OrderStatus.CANCELLED,
            "CANCELLED_BY_TRADE_CLOSE": OrderStatus.CANCELLED,
            "REJECTED": OrderStatus.REJECTED,
        }
        return status_map.get(str(oanda_status or "").upper(), OrderStatus.PENDING)

    def _order_sort_timestamp(self, order: BrokerOrder) -> float:
        try:
            return order.updated_at.timestamp()
        except Exception:
            return 0.0

    def _quote_from_price(self, price: Dict[str, Any], symbol: str) -> BrokerQuote:
        bids = price.get("bids") or []
        asks = price.get("asks") or []
        bid = self._positive_float(bids[0].get("price")) if bids else None
        ask = self._positive_float(asks[0].get("price")) if asks else None
        last = (bid + ask) / 2 if bid is not None and ask is not None else bid or ask
        return BrokerQuote(
            symbol=symbol,
            bid=bid,
            ask=ask,
            last=last,
            timestamp=self._parse_timestamp(price.get("time")),
            broker_id=self.broker_id,
        )

    def _balance_from_account(self, account: Dict[str, Any]) -> BrokerBalance:
        total_equity = self._to_float(account.get("NAV"), self._to_float(account.get("balance")))
        available_margin = self._to_float(account.get("marginAvailable"))
        used_margin = self._to_float(account.get("marginUsed"))
        return BrokerBalance(
            total_equity=total_equity,
            available_margin=available_margin,
            used_margin=used_margin,
            currency=str(account.get("currency") or "USD"),
        )

    def _positions_from_payload(
        self,
        positions_payload: List[Dict[str, Any]],
        current_prices: Dict[str, float],
    ) -> List[BrokerPosition]:
        positions: List[BrokerPosition] = []
        for payload in positions_payload:
            instrument_raw = str(payload.get("instrument") or "")
            if not instrument_raw:
                continue

            for side_name, side_payload in (("long", payload.get("long") or {}), ("short", payload.get("short") or {})):
                units = self._to_float(side_payload.get("units"))
                if units == 0:
                    continue

                entry_price = self._to_float(side_payload.get("averagePrice"))
                current_price = current_prices.get(instrument_raw, entry_price)
                positions.append(
                    BrokerPosition(
                        symbol=self._display_symbol(instrument_raw),
                        side=side_name,
                        quantity=abs(units),
                        entry_price=entry_price,
                        current_price=current_price,
                        unrealized_pnl=self._to_float(side_payload.get("unrealizedPL")),
                        broker_id=self.broker_id,
                        position_id=f"{instrument_raw}:{side_name}",
                    )
                )
        return positions

    def _order_from_transaction_response(
        self,
        symbol: str,
        side: OrderSide,
        order_type: OrderType,
        quantity: float,
        requested_price: Optional[float],
        payload: Dict[str, Any],
        stop_loss: Optional[float],
        take_profit_1: Optional[float],
        take_profit_2: Optional[float],
        take_profit_3: Optional[float],
    ) -> BrokerOrder:
        fill = payload.get("orderFillTransaction") or {}
        cancel = payload.get("orderCancelTransaction") or {}
        reject = payload.get("orderRejectTransaction") or {}
        create = payload.get("orderCreateTransaction") or {}

        order_data = fill or cancel or reject or create
        order_id = str(
            order_data.get("orderID")
            or order_data.get("id")
            or create.get("id")
            or payload.get("lastTransactionID")
            or ""
        )
        raw_units = order_data.get("units") or create.get("units") or quantity
        filled_quantity = abs(self._to_float(fill.get("units"))) if fill else 0.0
        fill_price = self._positive_float(fill.get("price"))
        status = OrderStatus.FILLED if fill else OrderStatus.CANCELLED if cancel else OrderStatus.REJECTED if reject else OrderStatus.PENDING

        return BrokerOrder(
            order_id=order_id,
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=abs(self._to_float(raw_units, quantity)),
            price=fill_price or requested_price,
            status=status,
            filled_quantity=filled_quantity,
            avg_fill_price=fill_price or 0.0,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
            created_at=self._parse_timestamp(order_data.get("time") or create.get("time")),
            updated_at=self._parse_timestamp(order_data.get("time") or create.get("time")),
            broker_id=self.broker_id,
            metadata=payload,
        )

    async def connect(self, credentials: Dict[str, str]) -> bool:
        """Connect to OANDA with API credentials."""
        if credentials.get("_oanda_credentials_validated") == "true":
            prepared = credentials
        else:
            prepared = self.prepare_credentials(credentials)
        api_token = prepared["api_token"]
        account_id = prepared["account_id"]
        environment = prepared["environment"]

        self._api_token = api_token
        self._account_id = account_id
        self._environment = environment
        self._base_url = _LIVE_URL if environment == "live" else _PRACTICE_URL
        self._client = self._create_client(api_token)

        try:
            await self._connectivity_check()
        except Exception:
            await self.disconnect()
            raise

        self.connected = True
        self._cache_invalidate()
        logger.info("Connected to OANDA", environment=environment)
        return True

    async def _connectivity_check(self) -> None:
        if not self._client or not self._account_id:
            raise BrokerOperationError(
                detail="OANDA broker credentials were not initialized",
                category="missing_credentials",
                status_code=400,
            )

        try:
            response = await self._client.get(f"{self._base_url}/accounts/{self._account_id}")
        except httpx.TimeoutException as exc:
            raise self._operation_error(
                operation="connection test",
                category="timeout",
                status_code=504,
                detail="request timed out",
            ) from exc
        except httpx.TransportError as exc:
            raise self._operation_error(
                operation="connection test",
                category="http_error",
                status_code=502,
                detail=str(exc),
            ) from exc
        self._raise_for_status(response, "connection test")

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
        except Exception as exc:
            logger.error("Error disconnecting from OANDA", error=self._redact(exc))
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
        """Place an order with OANDA."""
        if quantity <= 0:
            raise BrokerOperationError(
                detail="OANDA order quantity must be greater than zero",
                category="invalid_order",
                status_code=400,
            )
        if order_type in {OrderType.LIMIT, OrderType.STOP} and not price:
            raise BrokerOperationError(
                detail=f"OANDA {order_type.value} orders require a price",
                category="invalid_order",
                status_code=400,
            )

        normalized_quantity = max(1, int(round(quantity)))
        units = normalized_quantity if side == OrderSide.BUY else -normalized_quantity
        order_payload: Dict[str, Any] = {
            "type": order_type.value.upper(),
            "instrument": self._format_instrument(symbol),
            "units": str(units),
        }
        if order_type in {OrderType.LIMIT, OrderType.STOP} and price:
            order_payload["price"] = str(price)
            order_payload["timeInForce"] = "GTC"

        if stop_loss and stop_loss > 0:
            order_payload["stopLossOnFill"] = {"price": str(stop_loss)}

        take_profit_targets = [
            target
            for target in (take_profit_1, take_profit_2, take_profit_3)
            if target and target > 0
        ]
        if take_profit_targets:
            primary_target = max(take_profit_targets) if side == OrderSide.BUY else min(take_profit_targets)
            order_payload["takeProfitOnFill"] = {"price": str(primary_target)}

        payload = await self._request(
            "POST",
            f"/accounts/{self._account_id}/orders",
            operation="order placement",
            json={"order": order_payload},
            retry_safe=False,
        )
        order = self._order_from_transaction_response(
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=float(normalized_quantity),
            requested_price=price,
            payload=payload,
            stop_loss=stop_loss,
            take_profit_1=take_profit_1,
            take_profit_2=take_profit_2,
            take_profit_3=take_profit_3,
        )

        logger.info(
            "Order placed on OANDA",
            order_id=order.order_id,
            symbol=symbol,
            side=side.value,
            quantity=normalized_quantity,
            status=order.status.value,
        )
        self._cache_invalidate()
        return order

    async def cancel_order(self, order_id: str) -> bool:
        """Cancel an existing order."""
        await self._request(
            "PUT",
            f"/accounts/{self._account_id}/orders/{order_id}/cancel",
            operation="order cancellation",
        )
        logger.info("Order cancelled on OANDA", order_id=order_id)
        self._cache_invalidate()
        return True

    async def get_quote(self, symbol: str) -> BrokerQuote:
        """Get the latest OANDA quote for a symbol."""
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/pricing",
            operation="pricing lookup",
            params={"instruments": self._format_instrument(symbol)},
        )
        prices = payload.get("prices") or []
        if not prices:
            raise BrokerOperationError(
                detail=f"OANDA pricing lookup failed: no price returned for {symbol}",
                category="not_found",
                status_code=404,
            )
        return self._quote_from_price(prices[0], symbol)

    async def _price_map(self, instruments: List[str]) -> Dict[str, float]:
        if not instruments:
            return {}
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/pricing",
            operation="pricing lookup",
            params={"instruments": ",".join(instruments)},
        )
        result: Dict[str, float] = {}
        for price in payload.get("prices") or []:
            quote = self._quote_from_price(price, self._display_symbol(price.get("instrument", "")))
            if quote.last is not None and price.get("instrument"):
                result[str(price["instrument"])] = quote.last
        return result

    async def get_positions(self) -> List[BrokerPosition]:
        """Get current positions from OANDA."""
        cached = self._cache_get("positions")
        if cached is not _MISS:
            return cached

        stale = self._cache_get_stale("positions")
        if stale is not _MISS and "positions" not in self._cache_refreshing:
            self._cache_refreshing.add("positions")
            asyncio.get_event_loop().create_task(self._refresh_positions())
            return stale

        positions = await self._fetch_positions_from_oanda()
        self._cache_set("positions", positions)
        return positions

    async def _refresh_positions(self) -> None:
        try:
            positions = await self._fetch_positions_from_oanda()
            self._cache_set("positions", positions)
        except Exception as exc:
            logger.warning("Background OANDA position refresh failed", error=self._redact(exc))
        finally:
            self._cache_refreshing.discard("positions")

    async def _fetch_positions_from_oanda(self) -> List[BrokerPosition]:
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/openPositions",
            operation="positions lookup",
        )
        raw_positions = payload.get("positions") or []
        instruments = [
            str(position.get("instrument"))
            for position in raw_positions
            if position.get("instrument")
        ]
        current_prices: Dict[str, float] = {}
        try:
            current_prices = await self._price_map(list(dict.fromkeys(instruments)))
        except BrokerOperationError as exc:
            logger.warning("Could not fetch OANDA position prices", category=exc.category)
        return self._positions_from_payload(raw_positions, current_prices)

    async def get_balance(self) -> BrokerBalance:
        """Get account balance from OANDA."""
        cached = self._cache_get("balance")
        if cached is not _MISS:
            return cached

        stale = self._cache_get_stale("balance")
        if stale is not _MISS and "balance" not in self._cache_refreshing:
            self._cache_refreshing.add("balance")
            asyncio.get_event_loop().create_task(self._refresh_balance())
            return stale

        balance = await self._fetch_balance_from_oanda()
        self._cache_set("balance", balance)
        return balance

    async def _refresh_balance(self) -> None:
        try:
            balance = await self._fetch_balance_from_oanda()
            self._cache_set("balance", balance)
        except Exception as exc:
            logger.warning("Background OANDA balance refresh failed", error=self._redact(exc))
        finally:
            self._cache_refreshing.discard("balance")

    async def _fetch_balance_from_oanda(self) -> BrokerBalance:
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/summary",
            operation="account summary lookup",
        )
        return self._balance_from_account(payload.get("account") or {})

    async def get_orders(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
        status: Optional[str] = None,
    ) -> List[BrokerOrder]:
        """Get recent orders from OANDA."""
        cache_key = f"orders:{count}:{symbol}:{status}"
        cached = self._cache_get(cache_key)
        if cached is not _MISS:
            return cached

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
            params["instrument"] = self._format_instrument(symbol)

        data = await self._request(
            "GET",
            f"/accounts/{self._account_id}/orders",
            operation="orders lookup",
            params=params,
        )
        transactions_data = await self._request(
            "GET",
            f"/accounts/{self._account_id}/transactions",
            operation="order fills lookup",
            params={"count": str(min(max(count * 3, 10), 200)), "type": "ORDER_FILL"},
        )
        fill_map: Dict[str, Dict[str, Any]] = {}
        for transaction in transactions_data.get("transactions", []):
            order_id = transaction.get("orderID")
            if order_id:
                fill_map[str(order_id)] = transaction

        orders: List[BrokerOrder] = []
        for order in data.get("orders", []):
            raw_status = order.get("state", "PENDING")
            units = self._to_float(order.get("units"))
            raw_price = order.get("price") or order.get("priceBound")
            fill = fill_map.get(str(order.get("id", "")), {})
            fill_price = fill.get("fullPrice") or fill.get("price")
            price = self._positive_float(fill_price) or self._positive_float(raw_price)
            filled_quantity = abs(self._to_float(fill.get("units", units))) if raw_status == "FILLED" else 0.0
            updated_at = (
                fill.get("time")
                or order.get("filledTime")
                or order.get("cancelledTime")
                or order.get("createTime")
            )

            orders.append(
                BrokerOrder(
                    order_id=str(order.get("id", "")),
                    symbol=self._display_symbol(str(order.get("instrument", ""))),
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

        open_trade_orders = await self._open_trade_orders(count=count, symbol=symbol)
        result = sorted(
            [*orders, *open_trade_orders],
            key=lambda order: (
                order.status == OrderStatus.OPEN,
                self._order_sort_timestamp(order),
            ),
            reverse=True,
        )[:count]
        self._cache_set(cache_key, result)
        return result

    async def _open_trade_orders(self, count: int, symbol: Optional[str]) -> List[BrokerOrder]:
        trades_data = await self._request(
            "GET",
            f"/accounts/{self._account_id}/openTrades",
            operation="open trades lookup",
        )
        orders: List[BrokerOrder] = []
        for trade in trades_data.get("trades", []):
            trade_symbol = self._display_symbol(str(trade.get("instrument", "")))
            if symbol and trade_symbol != symbol:
                continue
            stop_loss = self._extract_trade_stop_loss(trade)
            take_profit = self._extract_trade_take_profit(trade)
            if stop_loss is None and take_profit is None:
                continue
            trade_units = self._to_float(trade.get("currentUnits", trade.get("initialUnits", 0)))
            if trade_units == 0:
                continue
            entry_price = self._to_float(trade.get("price"))
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
        return orders[:count]

    async def get_order_status(self, order_id: str) -> BrokerOrder:
        """Get status of a specific order."""
        payload = await self._request(
            "GET",
            f"/accounts/{self._account_id}/orders/{order_id}",
            operation="order status lookup",
        )
        order = payload.get("order") or {}
        units = self._to_float(order.get("units"))
        return BrokerOrder(
            order_id=order_id,
            symbol=self._display_symbol(str(order.get("instrument", ""))),
            side=OrderSide.BUY if units >= 0 else OrderSide.SELL,
            order_type=self._map_order_type(order.get("type", "MARKET")),
            quantity=abs(units),
            price=self._positive_float(order.get("price")),
            status=self._map_order_status(order.get("state", "PENDING")),
            stop_loss=self._extract_price(order, "stopLossOnFill", "stopLossOrder", "stopLoss"),
            take_profit_1=self._extract_price(order, "takeProfitOnFill", "takeProfitOrder", "takeProfit"),
            created_at=self._parse_timestamp(order.get("createTime")),
            updated_at=self._parse_timestamp(order.get("createTime")),
            broker_id=self.broker_id,
            metadata=order,
        )

    async def close_position(
        self,
        symbol: str,
        position_id: Optional[str] = None,
    ) -> bool:
        """Close an open position or trade on OANDA."""
        if position_id and ":" not in position_id:
            await self._request(
                "PUT",
                f"/accounts/{self._account_id}/trades/{position_id}/close",
                operation="trade close",
                json={"units": "ALL"},
            )
            logger.info("Trade closed on OANDA", symbol=symbol, position_id=position_id)
            self._cache_invalidate()
            return True

        body: Dict[str, str] = {}
        for position in await self.get_positions():
            if position.symbol != symbol:
                continue
            if position_id and position.position_id != position_id:
                continue
            if position.side == "long":
                body["longUnits"] = "ALL"
            elif position.side == "short":
                body["shortUnits"] = "ALL"

        if not body:
            logger.warning("No open OANDA position found", symbol=symbol, position_id=position_id)
            return False

        await self._request(
            "PUT",
            f"/accounts/{self._account_id}/positions/{self._format_instrument(symbol)}/close",
            operation="position close",
            json=body,
        )
        logger.info("Position closed on OANDA", symbol=symbol)
        self._cache_invalidate()
        return True

    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> bool:
        """Modify stop loss and/or take profit on an open OANDA trade."""
        body: Dict[str, Any] = {}
        if stop_loss is not None:
            body["stopLoss"] = {"price": str(stop_loss)} if stop_loss > 0 else None
        if take_profit is not None:
            body["takeProfit"] = {"price": str(take_profit)} if take_profit > 0 else None

        if not body:
            logger.warning("modify_trade called with no changes", trade_id=trade_id)
            return True

        await self._request(
            "PUT",
            f"/accounts/{self._account_id}/trades/{trade_id}/orders",
            operation="trade modification",
            json=body,
        )
        logger.info("Trade modified on OANDA", trade_id=trade_id)
        self._cache_invalidate()
        return True

    async def get_trade_history(
        self,
        count: int = 50,
        symbol: Optional[str] = None,
    ) -> List[dict]:
        """Get closed trade history from OANDA."""
        cache_key = f"history:{count}:{symbol}"
        cached = self._cache_get(cache_key)
        if cached is not _MISS:
            return cached

        params: Dict[str, str] = {"state": "CLOSED", "count": str(count)}
        if symbol:
            params["instrument"] = self._format_instrument(symbol)

        data = await self._request(
            "GET",
            f"/accounts/{self._account_id}/trades",
            operation="trade history lookup",
            params=params,
        )
        trades = []
        for trade in data.get("trades", []):
            trades.append(
                {
                    "trade_id": str(trade.get("id", "")),
                    "symbol": self._display_symbol(str(trade.get("instrument", ""))),
                    "side": "buy" if self._to_float(trade.get("initialUnits")) > 0 else "sell",
                    "quantity": abs(self._to_float(trade.get("initialUnits"))),
                    "entry_price": self._to_float(trade.get("price")),
                    "exit_price": self._to_float(trade.get("averageClosePrice")),
                    "realized_pnl": self._to_float(trade.get("realizedPL")),
                    "opened_at": trade.get("openTime", ""),
                    "closed_at": trade.get("closeTime", ""),
                    "state": trade.get("state", "CLOSED"),
                }
            )
        self._cache_set(cache_key, trades)
        return trades