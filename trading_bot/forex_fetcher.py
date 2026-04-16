"""Forex and commodity spot price fetcher.

This module provides spot prices for forex pairs and commodities (XAU/USD, XAG/USD)
that match TradingView data, unlike yfinance which only provides futures.
"""

import time
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import httpx
import pandas as pd
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from trading_bot.config import get_logger

logger = get_logger(__name__)


@dataclass
class SpotPrice:
    """Spot price data container."""
    symbol: str
    bid: float
    ask: float
    mid: float
    timestamp: float
    source: str


# Global cache for spot prices to reduce API calls
_global_spot_cache: Dict[str, SpotPrice] = {}
_global_cache_timestamp: float = 0
_GLOBAL_CACHE_TTL = 60  # 60 seconds global cache
_provider_cooldowns: Dict[str, float] = {}


def get_provider_status() -> Dict[str, dict]:
    """Expose spot provider cooldown/availability state for diagnostics."""
    now = time.time()
    providers = ["goldapi.io", "metals.live", "gold-api.com", "swissquote", "coingecko", "exchangerate-api.com"]
    status: Dict[str, dict] = {}
    for provider in providers:
        cooldown_until = _provider_cooldowns.get(provider, 0.0)
        remaining = max(0.0, cooldown_until - now)
        status[provider] = {
            "available": remaining <= 0,
            "cooldownRemainingSeconds": round(remaining, 1),
            "cooldownUntil": cooldown_until if cooldown_until > 0 else None,
        }
    return status


class ForexFetcher:
    """Fetch spot forex and commodity prices from free APIs."""
    
    # Primary API: exchangerate-api.com (free tier available)
    EXCHANGE_RATE_API_BASE = "https://api.exchangerate-api.com/v4/latest/USD"
    
    # Backup APIs for XAU/USD specifically
    GOLD_API_BASE = "https://www.goldapi.io/api"
    
    # Fallback: Use a simple approximation from multiple sources
    FALLBACK_APIS = [
        "https://api.exchangerate-api.com/v4/latest/USD",
    ]
    
    def __init__(self, gold_api_key: Optional[str] = None):
        """Initialize forex fetcher.
        
        Args:
            gold_api_key: Optional API key for goldapi.io (more accurate XAU/USD)
        """
        self.gold_api_key = gold_api_key
        self._cache: Dict[str, SpotPrice] = {}
        self._cache_ttl = 60  # 60 seconds cache to reduce API calls
        self._client: Optional[httpx.AsyncClient] = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        self._client = httpx.AsyncClient(timeout=10.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self._client:
            await self._client.aclose()
    
    def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    def _provider_available(self, provider: str, cooldown_seconds: int = 180) -> bool:
        expiry = _provider_cooldowns.get(provider, 0)
        return time.time() >= expiry

    def _mark_provider_failed(self, provider: str, cooldown_seconds: int = 180) -> None:
        _provider_cooldowns[provider] = time.time() + cooldown_seconds
    
    @retry(
        retry=retry_if_exception_type((httpx.NetworkError, httpx.TimeoutException)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=1, max=10),
    )
    async def fetch_xau_usd_spot(self) -> Optional[SpotPrice]:
        """Fetch XAU/USD spot price.
        
        Tries multiple sources in order:
        1. Global cache (shared across instances)
        2. goldapi.io (if API key provided) - most accurate
        3. metals.live - free, no key, real spot gold
        4. CoinGecko PAXG - free fallback (crypto proxy, may diverge)
        5. exchangerate-api.com - free, reliable
        
        Returns:
            SpotPrice with bid/ask/mid or None if all fail
        """
        global _global_spot_cache, _global_cache_timestamp
        
        # Check global cache first (shared across all instances)
        now = time.time()
        if "XAU/USD" in _global_spot_cache:
            cached = _global_spot_cache["XAU/USD"]
            if (now - cached.timestamp) < _GLOBAL_CACHE_TTL:
                logger.debug("Using global cached XAU/USD spot price")
                return cached
        
        # Check instance cache
        cached = self._cache.get("XAU/USD")
        if cached and (now - cached.timestamp) < self._cache_ttl:
            return cached
        
        # Try goldapi.io first (most accurate for gold)
        if self.gold_api_key:
            try:
                price = await self._fetch_from_goldapi()
                if price:
                    self._cache["XAU/USD"] = price
                    _global_spot_cache["XAU/USD"] = price
                    _global_cache_timestamp = time.time()
                    return price
            except Exception as e:
                logger.warning(f"GoldAPI fetch failed: {e}")
        
        # Load settings for optional providers
        try:
            from trading_bot.config import get_settings
            settings = get_settings()
        except Exception:
            settings = None

        # Try metals.live only when explicitly enabled
        if getattr(settings, "metals_live_enabled", False) and self._provider_available("metals.live"):
            try:
                price = await self._fetch_from_metals_live()
                if price:
                    self._cache["XAU/USD"] = price
                    _global_spot_cache["XAU/USD"] = price
                    _global_cache_timestamp = time.time()
                    return price
            except Exception as e:
                self._mark_provider_failed("metals.live", 600)
                logger.warning(f"metals.live fetch failed: {e}")

        # Try gold-api.com (free, no auth, real gold spot)
        if getattr(settings, "gold_api_free_enabled", True) and self._provider_available("gold-api.com"):
            try:
                price = await self._fetch_from_gold_api_free()
                if price:
                    self._cache["XAU/USD"] = price
                    _global_spot_cache["XAU/USD"] = price
                    _global_cache_timestamp = time.time()
                    return price
            except Exception as e:
                self._mark_provider_failed("gold-api.com", 300)
                logger.warning(f"gold-api.com fetch failed: {e}")

        # Try Swissquote public quotes as another no-key XAU/USD backup
        if getattr(settings, "swissquote_xau_enabled", True) and self._provider_available("swissquote"):
            try:
                price = await self._fetch_from_swissquote()
                if price:
                    self._cache["XAU/USD"] = price
                    _global_spot_cache["XAU/USD"] = price
                    _global_cache_timestamp = time.time()
                    return price
            except Exception as e:
                self._mark_provider_failed("swissquote", 300)
                logger.warning(f"Swissquote XAU fetch failed: {e}")
        
        # Try CoinGecko PAXG (crypto proxy — may diverge from real spot)
        cooldown_seconds = getattr(settings, "coingecko_cooldown_seconds", 180) if settings else 180
        try:
            if getattr(settings, 'enable_coingecko_fallback', True) and self._provider_available("coingecko", cooldown_seconds):
                price = await self._fetch_from_coingecko()
                if price:
                    logger.info(
                        "Using CoinGecko PAXG as fallback for XAU/USD spot "
                        "(crypto proxy — may deviate 0.1-0.5% from institutional spot)"
                    )
                    self._cache["XAU/USD"] = price
                    _global_spot_cache["XAU/USD"] = price
                    _global_cache_timestamp = time.time()
                    return price
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                self._mark_provider_failed("coingecko", cooldown_seconds)
            logger.warning(f"CoinGecko fetch failed: {e}")
        except Exception as e:
            self._mark_provider_failed("coingecko", cooldown_seconds)
            logger.warning(f"CoinGecko fetch failed: {e}")
        
        # Try exchangerate-api.com
        try:
            price = await self._fetch_from_exchangerate_api()
            if price:
                self._cache["XAU/USD"] = price
                return price
        except Exception as e:
            logger.warning(f"ExchangeRate API fetch failed: {e}")
        
        return None
    
    async def _fetch_from_metals_live(self) -> Optional[SpotPrice]:
        """Fetch from metals.live API (free, no key required, real spot prices)."""
        client = self._get_client()
        
        response = await client.get("https://api.metals.live/v1/spot")
        response.raise_for_status()
        data = response.json()
        
        # metals.live returns a list of metals with their spot prices
        gold_price = None
        for metal in data:
            if metal.get("gold") is not None:
                gold_price = float(metal["gold"])
                break
        
        if gold_price and gold_price > 0:
            # Typical institutional gold spread ~0.03-0.05%
            spread = gold_price * 0.0004
            return SpotPrice(
                symbol="XAU/USD",
                bid=gold_price - spread / 2,
                ask=gold_price + spread / 2,
                mid=gold_price,
                timestamp=time.time(),
                source="metals.live"
            )
        return None
    
    async def _fetch_from_goldapi(self) -> Optional[SpotPrice]:
        """Fetch from goldapi.io (requires API key)."""
        if not self.gold_api_key:
            return None
            
        client = self._get_client()
        headers = {"x-access-token": self.gold_api_key}
        
        response = await client.get(
            f"{self.GOLD_API_BASE}/XAU/USD",
            headers=headers
        )
        response.raise_for_status()
        data = response.json()
        
        # GoldAPI returns price in USD per ounce
        price = data.get("price", 0)
        bid = data.get("bid", price)
        ask = data.get("ask", price)
        
        if price > 0:
            return SpotPrice(
                symbol="XAU/USD",
                bid=bid,
                ask=ask,
                mid=(bid + ask) / 2,
                timestamp=time.time(),
                source="goldapi.io"
            )
        return None

    async def _fetch_from_gold_api_free(self) -> Optional[SpotPrice]:
        """Fetch from gold-api.com free endpoint."""
        client = self._get_client()
        response = await client.get("https://api.gold-api.com/price/XAU/USD")
        response.raise_for_status()
        data = response.json()

        price = data.get("price")
        if price and price > 0:
            spread = price * 0.0004
            return SpotPrice(
                symbol="XAU/USD",
                bid=price - spread / 2,
                ask=price + spread / 2,
                mid=price,
                timestamp=time.time(),
                source="gold-api.com"
            )
        return None

    async def _fetch_from_swissquote(self) -> Optional[SpotPrice]:
        """Fetch XAU/USD best bid/offer from Swissquote public feed."""
        client = self._get_client()
        response = await client.get(
            "https://forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU/USD"
        )
        response.raise_for_status()
        data = response.json()

        quotes = data if isinstance(data, list) else [data]
        for quote in quotes:
            top = quote.get("spreadProfilePrices") or quote.get("price") or {}
            bid = top.get("bid") or quote.get("bid")
            ask = top.get("ask") or quote.get("ask")
            if bid and ask and bid > 0 and ask > 0:
                return SpotPrice(
                    symbol="XAU/USD",
                    bid=float(bid),
                    ask=float(ask),
                    mid=(float(bid) + float(ask)) / 2,
                    timestamp=time.time(),
                    source="swissquote"
                )
        return None
    
    async def _fetch_from_coingecko(self) -> Optional[SpotPrice]:
        """Fetch from CoinGecko using PAXG (tokenized gold) as proxy for spot gold.
        
        PAXG is a token backed 1:1 by physical gold, so its price closely tracks
        spot gold with minimal deviation (~0.1-0.3%).
        """
        client = self._get_client()
        
        response = await client.get(
            "https://api.coingecko.com/api/v3/simple/price?ids=pax-gold&vs_currencies=usd"
        )
        response.raise_for_status()
        data = response.json()
        
        paxg_price = data.get("pax-gold", {}).get("usd")
        
        if paxg_price and paxg_price > 0:
            # PAXG tracks spot gold very closely
            # Estimate spread (typical for gold is ~0.05%)
            spread = paxg_price * 0.0005
            
            return SpotPrice(
                symbol="XAU/USD",
                bid=paxg_price - spread/2,
                ask=paxg_price + spread/2,
                mid=paxg_price,
                timestamp=time.time(),
                source="coingecko-paxg"
            )
        return None
    
    async def _fetch_from_exchangerate_api(self) -> Optional[SpotPrice]:
        """Fetch from exchangerate-api.com (free tier).
        
        Note: This API provides XAU rate but may not be as precise as gold-specific APIs.
        """
        client = self._get_client()
        
        response = await client.get(self.EXCHANGE_RATE_API_BASE)
        response.raise_for_status()
        data = response.json()
        
        rates = data.get("rates", {})
        xau_rate = rates.get("XAU")
        
        if xau_rate and xau_rate > 0:
            # XAU rate is usually in oz per USD, convert to USD per oz
            # Some APIs return it directly as USD per oz, check the value magnitude
            if xau_rate < 1:  # It's oz per USD (e.g., 0.00021)
                price = 1 / xau_rate
            else:  # It's already USD per oz
                price = xau_rate
            
            # Estimate spread (typical for gold is ~0.05%)
            spread = price * 0.0005
            
            return SpotPrice(
                symbol="XAU/USD",
                bid=price - spread/2,
                ask=price + spread/2,
                mid=price,
                timestamp=time.time(),
                source="exchangerate-api.com"
            )
        return None
    
    async def fetch_forex_spot(self, base: str, quote: str) -> Optional[SpotPrice]:
        """Fetch spot price for forex pair (e.g., EUR/USD).
        
        Args:
            base: Base currency (e.g., "EUR")
            quote: Quote currency (e.g., "USD")
            
        Returns:
            SpotPrice or None
        """
        symbol = f"{base}/{quote}"
        
        # Check cache
        cached = self._cache.get(symbol)
        if cached and (time.time() - cached.timestamp) < self._cache_ttl:
            return cached
        
        try:
            client = self._get_client()
            response = await client.get(f"https://api.exchangerate-api.com/v4/latest/{base}")
            response.raise_for_status()
            data = response.json()
            
            rate = data.get("rates", {}).get(quote)
            if rate:
                # Estimate typical forex spread (~0.01% for majors)
                spread = rate * 0.0001
                
                price = SpotPrice(
                    symbol=symbol,
                    bid=rate - spread/2,
                    ask=rate + spread/2,
                    mid=rate,
                    timestamp=time.time(),
                    source="exchangerate-api.com"
                )
                self._cache[symbol] = price
                return price
        except Exception as e:
            logger.warning(f"Failed to fetch {symbol}: {e}")
        
        return None
    
    def clear_cache(self) -> None:
        """Clear the price cache."""
        self._cache.clear()


class SpotPriceAdapter:
    """Adapter to integrate spot prices with existing yfinance data pipeline.
    
    This allows using spot prices for XAU/USD while keeping yfinance for other symbols.
    """
    
    # Symbols that should use spot price APIs instead of yfinance
    SPOT_SYMBOLS = {"XAU/USD", "XAG/USD"}
    
    def __init__(self, gold_api_key: Optional[str] = None):
        """Initialize adapter.
        
        Args:
            gold_api_key: Optional API key for goldapi.io
        """
        self.forex_fetcher = ForexFetcher(gold_api_key)
        self._spot_cache: Dict[str, Dict] = {}
    
    async def get_current_price(self, symbol: str) -> Optional[float]:
        """Get current spot price for symbol.
        
        Args:
            symbol: Trading symbol (e.g., "XAU/USD")
            
        Returns:
            Current mid price or None
        """
        if symbol not in self.SPOT_SYMBOLS:
            return None  # Not a spot symbol, use yfinance
        
        async with self.forex_fetcher as fetcher:
            if symbol == "XAU/USD":
                spot = await fetcher.fetch_xau_usd_spot()
            elif symbol == "XAG/USD":
                # For silver, we'd need similar implementation
                spot = None
            else:
                return None
            
            if spot:
                return spot.mid
        
        return None
    
    def is_spot_symbol(self, symbol: str) -> bool:
        """Check if symbol should use spot price API.
        
        Args:
            symbol: Trading symbol
            
        Returns:
            True if symbol should use spot price API
        """
        return symbol in self.SPOT_SYMBOLS


# Global instance for convenience
_spot_adapter: Optional[SpotPriceAdapter] = None


def get_spot_adapter(gold_api_key: Optional[str] = None) -> SpotPriceAdapter:
    """Get or create global spot price adapter."""
    global _spot_adapter
    if _spot_adapter is None:
        _spot_adapter = SpotPriceAdapter(gold_api_key)
    return _spot_adapter
