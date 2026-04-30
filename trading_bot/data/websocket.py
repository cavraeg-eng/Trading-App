"""WebSocket manager for real-time data feeds."""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Set

import websockets
from websockets.exceptions import ConnectionClosed, InvalidStatusCode

from trading_bot.config import get_logger

logger = get_logger(__name__)


@dataclass
class WebSocketConfig:
    """WebSocket configuration."""
    url: str
    symbols: List[str]
    channels: List[str] = field(default_factory=lambda: ["trade", "bookTicker"])
    reconnect_delay: float = 5.0
    max_reconnects: int = 10
    ping_interval: float = 20.0
    ping_timeout: float = 10.0


class WebSocketManager:
    """Manages WebSocket connections for real-time market data."""
    
    def __init__(self, config: WebSocketConfig):
        """Initialize WebSocket manager.
        
        Args:
            config: WebSocket configuration
        """
        self.config = config
        self.websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._running = False
        self._reconnect_count = 0
        self._handlers: Dict[str, List[Callable]] = {
            "trade": [],
            "bookTicker": [],
            "kline": [],
            "aggTrade": [],
        }
        self._last_prices: Dict[str, float] = {}
        self._tasks: Set[asyncio.Task] = set()
    
    def add_handler(self, channel: str, handler: Callable) -> None:
        """Add a handler for a specific channel.
        
        Args:
            channel: Channel name (trade, bookTicker, etc.)
            handler: Callback function
        """
        if channel not in self._handlers:
            self._handlers[channel] = []
        self._handlers[channel].append(handler)
        logger.debug("Handler added", channel=channel)
    
    def remove_handler(self, channel: str, handler: Callable) -> None:
        """Remove a handler.
        
        Args:
            channel: Channel name
            handler: Callback function
        """
        if channel in self._handlers and handler in self._handlers[channel]:
            self._handlers[channel].remove(handler)
    
    def get_last_price(self, symbol: str) -> Optional[float]:
        """Get last known price for a symbol.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Last price or None
        """
        return self._last_prices.get(symbol)
    
    async def start(self) -> None:
        """Start WebSocket connection."""
        self._running = True
        await self._connect()
    
    async def stop(self) -> None:
        """Stop WebSocket connection."""
        self._running = False
        
        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
        
        if self.websocket:
            await self.websocket.close()
        
        logger.info("WebSocket manager stopped")
    
    async def _connect(self) -> None:
        """Establish WebSocket connection with reconnection logic."""
        while self._running and self._reconnect_count < self.config.max_reconnects:
            try:
                logger.info(
                    "Connecting to WebSocket",
                    url=self.config.url,
                    attempt=self._reconnect_count + 1,
                )
                
                self.websocket = await websockets.connect(
                    self.config.url,
                    ping_interval=self.config.ping_interval,
                    ping_timeout=self.config.ping_timeout,
                )
                
                # Subscribe to channels
                await self._subscribe()
                
                # Reset reconnect count on successful connection
                self._reconnect_count = 0
                
                # Start message handler
                await self._handle_messages()
                
            except ConnectionClosed as e:
                logger.warning(
                    "WebSocket connection closed",
                    code=e.code,
                    reason=e.reason,
                )
                await self._reconnect()
                
            except InvalidStatusCode as e:
                logger.error(
                    "WebSocket connection failed",
                    status_code=e.status_code,
                )
                await self._reconnect()
                
            except Exception as e:
                logger.error("WebSocket error", error=str(e))
                await self._reconnect()
    
    async def _reconnect(self) -> None:
        """Attempt to reconnect."""
        self._reconnect_count += 1
        
        if self._reconnect_count >= self.config.max_reconnects:
            logger.error("Max reconnection attempts reached")
            self._running = False
            return
        
        delay = self.config.reconnect_delay * (2 ** (self._reconnect_count - 1))
        delay = min(delay, 60)  # Cap at 60 seconds
        
        logger.info(
            "Reconnecting in {:.1f}s".format(delay),
            attempt=self._reconnect_count,
        )
        
        await asyncio.sleep(delay)
    
    async def _subscribe(self) -> None:
        """Subscribe to channels."""
        if not self.websocket:
            return
        
        # Binance combined stream format
        streams = []
        for symbol in self.config.symbols:
            clean_symbol = symbol.lower().replace("/", "")
            for channel in self.config.channels:
                streams.append(f"{clean_symbol}@{channel}")
        
        # Subscribe message
        subscribe_msg = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1,
        }
        
        await self.websocket.send(json.dumps(subscribe_msg))
        logger.info("Subscribed to streams", streams=len(streams))
    
    async def _handle_messages(self) -> None:
        """Handle incoming WebSocket messages."""
        if not self.websocket:
            return
        
        async for message in self.websocket:
            try:
                data = json.loads(message)
                await self._process_message(data)
            except json.JSONDecodeError as e:
                logger.warning("Failed to parse message", error=str(e))
            except Exception as e:
                logger.error("Error processing message", error=str(e))
    
    async def _process_message(self, data: Dict) -> None:
        """Process a single message.
        
        Args:
            data: Message data
        """
        # Handle subscription response
        if "id" in data:
            logger.debug("Subscription response", data=data)
            return
        
        # Handle error
        if "error" in data:
            logger.error("WebSocket error message", error=data["error"])
            return
        
        # Extract stream type and data
        stream = data.get("stream", "")
        payload = data.get("data", data)
        
        # Determine channel type
        channel = None
        for ch in self._handlers.keys():
            if ch in stream:
                channel = ch
                break
        
        if not channel:
            return
        
        # Update last price if available
        symbol = self._extract_symbol(stream)
        if symbol and "price" in str(payload).lower():
            price = self._extract_price(payload)
            if price:
                self._last_prices[symbol] = price
        
        # Call handlers
        for handler in self._handlers.get(channel, []):
            try:
                if asyncio.iscoroutinefunction(handler):
                    task = asyncio.create_task(handler(payload))
                    self._tasks.add(task)
                    task.add_done_callback(self._tasks.discard)
                else:
                    handler(payload)
            except Exception as e:
                logger.error("Handler error", error=str(e))
    
    def _extract_symbol(self, stream: str) -> Optional[str]:
        """Extract symbol from stream name.
        
        Args:
            stream: Stream name
            
        Returns:
            Symbol or None
        """
        # Remove channel suffix
        for channel in self.config.channels:
            if f"@{channel}" in stream:
                symbol_part = stream.replace(f"@{channel}", "")
                # Convert back to standard format
                if "usdt" in symbol_part:
                    base = symbol_part.replace("usdt", "").upper()
                    return f"{base}/USDT"
                return symbol_part.upper()
        return None
    
    def _extract_price(self, payload: Dict) -> Optional[float]:
        """Extract price from payload.
        
        Args:
            payload: Message payload
            
        Returns:
            Price or None
        """
        # Try different price fields
        price_fields = ["p", "price", "c", "close", "askPrice", "bidPrice"]
        for field in price_fields:
            if field in payload:
                try:
                    return float(payload[field])
                except (ValueError, TypeError):
                    continue
        return None


class BinanceWebSocketManager(WebSocketManager):
    """Binance-specific WebSocket manager."""
    
    BASE_URL = "wss://stream.binance.com:9443/ws"
    TESTNET_URL = "wss://testnet.binance.vision/ws"
    
    def __init__(
        self,
        symbols: List[str],
        channels: Optional[List[str]] = None,
        testnet: bool = True,
    ):
        """Initialize Binance WebSocket manager.
        
        Args:
            symbols: List of trading pairs
            channels: List of channels to subscribe
            testnet: Use testnet
        """
        url = self.TESTNET_URL if testnet else self.BASE_URL
        
        config = WebSocketConfig(
            url=url,
            symbols=symbols,
            channels=channels or ["trade", "bookTicker"],
        )
        
        super().__init__(config)


class MultiExchangeWebSocketManager:
    """Manager for multiple exchange WebSockets."""
    
    def __init__(self):
        """Initialize multi-exchange manager."""
        self.managers: Dict[str, WebSocketManager] = {}
        self._running = False
    
    def add_manager(self, name: str, manager: WebSocketManager) -> None:
        """Add a WebSocket manager.
        
        Args:
            name: Manager name
            manager: WebSocket manager instance
        """
        self.managers[name] = manager
    
    async def start_all(self) -> None:
        """Start all WebSocket connections."""
        self._running = True
        
        tasks = [
            asyncio.create_task(manager.start())
            for manager in self.managers.values()
        ]
        
        await asyncio.gather(*tasks, return_exceptions=True)
    
    async def stop_all(self) -> None:
        """Stop all WebSocket connections."""
        self._running = False
        
        await asyncio.gather(*[
            manager.stop()
            for manager in self.managers.values()
        ], return_exceptions=True)
    
    def get_price(self, exchange: str, symbol: str) -> Optional[float]:
        """Get price from specific exchange.
        
        Args:
            exchange: Exchange name
            symbol: Trading pair
            
        Returns:
            Price or None
        """
        manager = self.managers.get(exchange)
        if manager:
            return manager.get_last_price(symbol)
        return None
