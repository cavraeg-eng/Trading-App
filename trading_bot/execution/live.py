"""Live trading executor for real exchange execution."""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

from trading_bot.config import get_logger, get_settings
from trading_bot.data.fetcher import DataFetcher
from trading_bot.risk.manager import RiskManager
from trading_bot.strategy.base import Signal, SignalType

logger = get_logger(__name__)


@dataclass
class Order:
    """Order data."""
    order_id: str
    symbol: str
    side: str
    order_type: str
    quantity: float
    price: Optional[float] = None
    status: str = "pending"
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    created_at: datetime = None
    updated_at: datetime = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.updated_at is None:
            self.updated_at = datetime.now()


class LiveExecutor:
    """Live trading executor."""
    
    def __init__(
        self,
        exchange_id: str = "binance",
        testnet: bool = True,
        risk_manager: Optional[RiskManager] = None,
    ):
        """Initialize live executor.
        
        Args:
            exchange_id: Exchange identifier
            testnet: Use testnet
            risk_manager: Risk manager instance
        """
        self.exchange_id = exchange_id
        self.testnet = testnet
        self.risk_manager = risk_manager or RiskManager()
        
        self.data_fetcher: Optional[DataFetcher] = None
        self.orders: Dict[str, Order] = {}
        self.positions: Dict[str, Dict] = {}
        self.is_running = False
        
        # Rate limiting
        self._order_count = 0
        self._order_window_start = datetime.now()
        self._max_orders_per_minute = 10
    
    async def initialize(self) -> None:
        """Initialize exchange connection."""
        settings = get_settings()
        
        self.data_fetcher = DataFetcher(
            exchange_id=self.exchange_id,
            api_key=settings.binance_api_key,
            secret=settings.binance_secret_key,
            testnet=self.testnet,
        )
        
        await self.data_fetcher.initialize()
        self.is_running = True
        
        logger.info(
            "Live executor initialized",
            exchange=self.exchange_id,
            testnet=self.testnet,
        )
    
    async def close(self) -> None:
        """Close exchange connection."""
        if self.data_fetcher:
            await self.data_fetcher.close()
        self.is_running = False
        logger.info("Live executor closed")
    
    def _check_rate_limit(self) -> bool:
        """Check if we can place an order (rate limiting).
        
        Returns:
            True if allowed
        """
        now = datetime.now()
        
        # Reset window
        if (now - self._order_window_start).seconds >= 60:
            self._order_count = 0
            self._order_window_start = now
        
        if self._order_count >= self._max_orders_per_minute:
            logger.warning("Rate limit exceeded")
            return False
        
        self._order_count += 1
        return True
    
    async def execute_signal(
        self,
        signal: Signal,
        order_type: str = "market",
    ) -> Optional[Order]:
        """Execute trading signal.
        
        Args:
            signal: Trading signal
            order_type: Order type ('market', 'limit')
            
        Returns:
            Order object or None
        """
        if not self.is_running:
            logger.error("Executor not initialized")
            return None
        
        if not self._check_rate_limit():
            return None
        
        symbol = signal.symbol
        
        # Get current price
        try:
            ticker = await self.data_fetcher.exchange.fetch_ticker(symbol)
            current_price = ticker["last"]
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            return None
        
        # Handle close signal
        if signal.signal_type == SignalType.CLOSE:
            return await self.close_position(symbol)
        
        # Determine side
        side = "buy" if signal.signal_type == SignalType.BUY else "sell"
        
        # Check risk limits
        can_trade, reason = self.risk_manager.can_open_position(
            symbol, side, 1.0, current_price
        )
        
        if not can_trade:
            logger.warning(f"Risk check failed: {reason}")
            return None
        
        # Calculate position size
        stop_loss = current_price * 0.95 if side == "buy" else current_price * 1.05
        position_size = self.risk_manager.get_position_size(
            symbol, current_price, stop_loss
        )
        
        # Create order
        order = Order(
            order_id=f"order_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            symbol=symbol,
            side=side,
            order_type=order_type,
            quantity=position_size.size,
            price=current_price if order_type == "limit" else None,
        )
        
        try:
            # Place order on exchange
            if order_type == "market":
                exchange_order = await self.data_fetcher.exchange.create_market_buy_order(
                    symbol, position_size.size
                ) if side == "buy" else await self.data_fetcher.exchange.create_market_sell_order(
                    symbol, position_size.size
                )
            else:
                exchange_order = await self.data_fetcher.exchange.create_limit_buy_order(
                    symbol, position_size.size, current_price
                ) if side == "buy" else await self.data_fetcher.exchange.create_limit_sell_order(
                    symbol, position_size.size, current_price
                )
            
            # Update order with exchange response
            order.order_id = exchange_order["id"]
            order.status = exchange_order["status"]
            order.filled_quantity = exchange_order.get("filled", 0)
            order.avg_fill_price = exchange_order.get("average", current_price)
            
            self.orders[order.order_id] = order
            
            # Update risk manager
            self.risk_manager.open_position(
                symbol=symbol,
                side="long" if side == "buy" else "short",
                size=position_size.size,
                entry_price=order.avg_fill_price or current_price,
                stop_loss=stop_loss,
            )
            
            logger.info(
                "Order placed",
                order_id=order.order_id,
                symbol=symbol,
                side=side,
                size=position_size.size,
                price=order.avg_fill_price,
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to place order: {e}")
            return None
    
    async def close_position(self, symbol: str) -> Optional[Order]:
        """Close position for symbol.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            Order object or None
        """
        if not self.is_running:
            return None
        
        # Check if we have a position
        position = self.risk_manager.state.open_positions.get(symbol)
        if not position:
            logger.warning(f"No position to close for {symbol}")
            return None
        
        # Get current price
        try:
            ticker = await self.data_fetcher.exchange.fetch_ticker(symbol)
            current_price = ticker["last"]
        except Exception as e:
            logger.error(f"Failed to get ticker: {e}")
            return None
        
        # Determine close side
        close_side = "sell" if position.side == "long" else "buy"
        
        # Create order
        order = Order(
            order_id=f"close_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}",
            symbol=symbol,
            side=close_side,
            order_type="market",
            quantity=position.size,
        )
        
        try:
            # Place closing order
            if close_side == "sell":
                exchange_order = await self.data_fetcher.exchange.create_market_sell_order(
                    symbol, position.size
                )
            else:
                exchange_order = await self.data_fetcher.exchange.create_market_buy_order(
                    symbol, position.size
                )
            
            # Update order
            order.order_id = exchange_order["id"]
            order.status = exchange_order["status"]
            order.filled_quantity = exchange_order.get("filled", 0)
            order.avg_fill_price = exchange_order.get("average", current_price)
            
            self.orders[order.order_id] = order
            
            # Update risk manager
            self.risk_manager.close_position(symbol, order.avg_fill_price or current_price)
            
            logger.info(
                "Position closed",
                order_id=order.order_id,
                symbol=symbol,
                price=order.avg_fill_price,
            )
            
            return order
            
        except Exception as e:
            logger.error(f"Failed to close position: {e}")
            return None
    
    async def update_orders(self) -> None:
        """Update status of pending orders."""
        if not self.is_running:
            return
        
        for order_id, order in list(self.orders.items()):
            if order.status in ["open", "pending"]:
                try:
                    exchange_order = await self.data_fetcher.exchange.fetch_order(
                        order_id, order.symbol
                    )
                    
                    order.status = exchange_order["status"]
                    order.filled_quantity = exchange_order.get("filled", 0)
                    order.avg_fill_price = exchange_order.get("average", order.avg_fill_price)
                    order.updated_at = datetime.now()
                    
                except Exception as e:
                    logger.error(f"Failed to fetch order {order_id}: {e}")
    
    async def sync_positions(self) -> None:
        """Sync positions with exchange."""
        if not self.is_running:
            return
        
        try:
            positions = await self.data_fetcher.exchange.fetch_positions()
            
            for pos in positions:
                symbol = pos["symbol"]
                size = float(pos.get("contracts", 0))
                
                if size != 0:
                    self.positions[symbol] = {
                        "size": size,
                        "entry_price": pos.get("entryPrice", 0),
                        "unrealized_pnl": pos.get("unrealizedPnl", 0),
                    }
                elif symbol in self.positions:
                    del self.positions[symbol]
                    
        except Exception as e:
            logger.error(f"Failed to sync positions: {e}")
    
    def get_account_summary(self) -> Dict:
        """Get account summary.
        
        Returns:
            Account summary dictionary
        """
        risk_metrics = self.risk_manager.get_portfolio_metrics()
        
        return {
            **risk_metrics,
            "open_orders": len([o for o in self.orders.values() if o.status == "open"]),
            "total_orders": len(self.orders),
            "exchange_positions": len(self.positions),
        }
    
    async def emergency_close_all(self) -> None:
        """Emergency close all positions."""
        logger.critical("EMERGENCY CLOSE ALL POSITIONS")
        
        for symbol in list(self.risk_manager.state.open_positions.keys()):
            await self.close_position(symbol)
            await asyncio.sleep(0.5)  # Rate limiting
