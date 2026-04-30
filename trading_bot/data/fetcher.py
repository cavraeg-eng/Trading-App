"""Async data fetcher using CCXT."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import ccxt.async_support as ccxt
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from trading_bot.config import get_logger, get_settings

logger = get_logger(__name__)


@dataclass
class MarketData:
    """Market data container."""
    symbol: str
    timeframe: str
    ohlcv: pd.DataFrame
    orderbook: Optional[Dict] = None
    funding_rate: Optional[float] = None
    timestamp: Optional[datetime] = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class DataFetcher:
    """Async data fetcher for cryptocurrency exchanges."""
    
    def __init__(
        self,
        exchange_id: str = "binance",
        api_key: Optional[str] = None,
        secret: Optional[str] = None,
        testnet: bool = True,
    ):
        """Initialize data fetcher.
        
        Args:
            exchange_id: Exchange identifier (e.g., 'binance')
            api_key: API key for authenticated requests
            secret: API secret
            testnet: Use testnet/sandbox
        """
        self.exchange_id = exchange_id
        self.api_key = api_key
        self.secret = secret
        self.testnet = testnet
        self.exchange: Optional[ccxt.Exchange] = None
        self._rate_limiter = asyncio.Semaphore(10)  # Max 10 concurrent requests
        
    async def __aenter__(self):
        """Async context manager entry."""
        await self.initialize()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self.close()
    
    async def initialize(self) -> None:
        """Initialize exchange connection."""
        try:
            exchange_class = getattr(ccxt, self.exchange_id)
            config = {
                "enableRateLimit": True,
                "options": {},
            }
            
            if self.api_key and self.secret:
                config["apiKey"] = self.api_key
                config["secret"] = self.secret
            
            if self.testnet:
                config["options"]["defaultType"] = "future"
                if self.exchange_id == "binance":
                    config["options"]["sandbox"] = True
            
            self.exchange = exchange_class(config)
            
            if self.testnet and self.exchange_id == "binance":
                self.exchange.set_sandbox_mode(True)
            
            await self.exchange.load_markets()
            logger.info(
                "Exchange initialized",
                exchange=self.exchange_id,
                testnet=self.testnet,
                markets=len(self.exchange.markets),
            )
        except Exception as e:
            logger.error("Failed to initialize exchange", error=str(e))
            raise
    
    async def close(self) -> None:
        """Close exchange connection."""
        if self.exchange:
            await self.exchange.close()
            logger.info("Exchange connection closed")
    
    @retry(
        retry=retry_if_exception_type((ccxt.NetworkError, ccxt.ExchangeError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1h",
        since: Optional[int] = None,
        limit: int = 1000,
    ) -> pd.DataFrame:
        """Fetch OHLCV data.
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Candle timeframe
            since: Start timestamp in milliseconds
            limit: Number of candles to fetch
            
        Returns:
            DataFrame with OHLCV data
        """
        if not self.exchange:
            raise RuntimeError("Exchange not initialized")
        
        async with self._rate_limiter:
            try:
                ohlcv = await self.exchange.fetch_ohlcv(
                    symbol, timeframe, since=since, limit=limit
                )
                
                df = pd.DataFrame(
                    ohlcv,
                    columns=["timestamp", "open", "high", "low", "close", "volume"],
                )
                df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
                df.set_index("timestamp", inplace=True)
                
                # Convert to float
                for col in ["open", "high", "low", "close", "volume"]:
                    df[col] = df[col].astype(float)
                
                logger.debug(
                    "Fetched OHLCV",
                    symbol=symbol,
                    timeframe=timeframe,
                    records=len(df),
                )
                
                return df
                
            except Exception as e:
                logger.error(
                    "Failed to fetch OHLCV",
                    symbol=symbol,
                    error=str(e),
                )
                raise
    
    async def fetch_orderbook(
        self,
        symbol: str,
        limit: int = 20,
    ) -> Dict:
        """Fetch order book.
        
        Args:
            symbol: Trading pair
            limit: Order book depth
            
        Returns:
            Order book data
        """
        if not self.exchange:
            raise RuntimeError("Exchange not initialized")
        
        async with self._rate_limiter:
            try:
                orderbook = await self.exchange.fetch_order_book(symbol, limit)
                
                # Calculate order flow imbalance
                bids = orderbook["bids"]
                asks = orderbook["asks"]
                
                bid_volume = sum(b[1] for b in bids[:10])
                ask_volume = sum(a[1] for a in asks[:10])
                total_volume = bid_volume + ask_volume
                
                orderbook["imbalance"] = (
                    (bid_volume - ask_volume) / total_volume if total_volume > 0 else 0
                )
                orderbook["spread"] = asks[0][0] - bids[0][0] if bids and asks else 0
                orderbook["mid_price"] = (bids[0][0] + asks[0][0]) / 2 if bids and asks else 0
                
                return orderbook
                
            except Exception as e:
                logger.error(
                    "Failed to fetch orderbook",
                    symbol=symbol,
                    error=str(e),
                )
                raise
    
    async def fetch_funding_rate(self, symbol: str) -> Optional[float]:
        """Fetch funding rate for perpetual futures.
        
        Args:
            symbol: Trading pair
            
        Returns:
            Funding rate or None if not available
        """
        if not self.exchange:
            raise RuntimeError("Exchange not initialized")
        
        # Check if exchange supports funding rates
        if not hasattr(self.exchange, "fetchFundingRate"):
            return None
        
        async with self._rate_limiter:
            try:
                funding = await self.exchange.fetch_funding_rate(symbol)
                return funding.get("fundingRate", 0.0) if funding else None
            except Exception as e:
                logger.warning(
                    "Failed to fetch funding rate",
                    symbol=symbol,
                    error=str(e),
                )
                return None
    
    async def fetch_multiple_symbols(
        self,
        symbols: List[str],
        timeframe: str = "1h",
        lookback_days: int = 30,
    ) -> Dict[str, pd.DataFrame]:
        """Fetch OHLCV data for multiple symbols.
        
        Args:
            symbols: List of trading pairs
            timeframe: Candle timeframe
            lookback_days: Number of days to look back
            
        Returns:
            Dictionary mapping symbols to DataFrames
        """
        since = int((datetime.now() - timedelta(days=lookback_days)).timestamp() * 1000)
        
        tasks = [
            self.fetch_ohlcv(symbol, timeframe, since=since)
            for symbol in symbols
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        data = {}
        for symbol, result in zip(symbols, results):
            if isinstance(result, Exception):
                logger.error(
                    "Failed to fetch data for symbol",
                    symbol=symbol,
                    error=str(result),
                )
            else:
                data[symbol] = result
        
        return data
    
    async def fetch_market_data(
        self,
        symbol: str,
        timeframe: str = "1h",
    ) -> MarketData:
        """Fetch comprehensive market data.
        
        Args:
            symbol: Trading pair
            timeframe: Candle timeframe
            
        Returns:
            MarketData object
        """
        # Fetch OHLCV
        ohlcv = await self.fetch_ohlcv(symbol, timeframe, limit=100)
        
        # Fetch orderbook
        try:
            orderbook = await self.fetch_orderbook(symbol)
        except Exception:
            orderbook = None
        
        # Fetch funding rate
        try:
            funding_rate = await self.fetch_funding_rate(symbol)
        except Exception:
            funding_rate = None
        
        return MarketData(
            symbol=symbol,
            timeframe=timeframe,
            ohlcv=ohlcv,
            orderbook=orderbook,
            funding_rate=funding_rate,
        )
    
    async def get_exchange_info(self) -> Dict:
        """Get exchange information.
        
        Returns:
            Exchange metadata
        """
        if not self.exchange:
            raise RuntimeError("Exchange not initialized")
        
        return {
            "id": self.exchange.id,
            "name": self.exchange.name,
            "version": ccxt.__version__,
            "timeframes": list(self.exchange.timeframes.keys()) if self.exchange.timeframes else [],
            "symbols": list(self.exchange.markets.keys()),
            "has": self.exchange.has,
        }
