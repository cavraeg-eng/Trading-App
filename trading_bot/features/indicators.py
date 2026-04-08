"""Technical indicators using pandas and numpy."""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from trading_bot.config import get_logger

logger = get_logger(__name__)


class TechnicalIndicators:
    """Technical indicators calculator."""
    
    def __init__(self):
        """Initialize indicators."""
        pass
    
    def add_all_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add all technical indicators to dataframe.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with all indicators
        """
        df = df.copy()
        
        # Trend indicators
        df = self.add_trend_indicators(df)
        
        # Momentum indicators
        df = self.add_momentum_indicators(df)
        
        # Volatility indicators
        df = self.add_volatility_indicators(df)
        
        # Volume indicators
        df = self.add_volume_indicators(df)
        
        # Support/Resistance
        df = self.add_support_resistance(df)
        
        return df
    
    def add_trend_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend indicators.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with trend indicators
        """
        df = df.copy()
        
        # EMAs
        for period in [9, 21, 50, 200]:
            df[f"ema_{period}"] = df["close"].ewm(span=period, adjust=False).mean()
        
        # SMAs
        for period in [20, 50, 200]:
            df[f"sma_{period}"] = df["close"].rolling(window=period).mean()
        
        # MACD
        ema_12 = df["close"].ewm(span=12, adjust=False).mean()
        ema_26 = df["close"].ewm(span=26, adjust=False).mean()
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]
        
        # ADX (Trend strength) - Simplified calculation
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        df["atr_14"] = tr.rolling(window=14).mean()
        
        return df
    
    def add_momentum_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum indicators.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with momentum indicators
        """
        df = df.copy()
        
        # RSI
        for period in [7, 14, 21]:
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
            rs = gain / loss
            df[f"rsi_{period}"] = 100 - (100 / (1 + rs))
        
        # Stochastic
        low_min = df["low"].rolling(window=14).min()
        high_max = df["high"].rolling(window=14).max()
        df["stoch_k"] = 100 * (df["close"] - low_min) / (high_max - low_min)
        df["stoch_d"] = df["stoch_k"].rolling(window=3).mean()
        
        # Williams %R
        df["williams_r"] = -100 * (high_max - df["close"]) / (high_max - low_min)
        
        # Rate of Change
        for period in [10, 20]:
            df[f"roc_{period}"] = df["close"].pct_change(period) * 100
        
        return df
    
    def add_volatility_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility indicators.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with volatility indicators
        """
        df = df.copy()
        
        # Bollinger Bands
        df["bb_middle"] = df["close"].rolling(window=20).mean()
        bb_std = df["close"].rolling(window=20).std()
        df["bb_upper"] = df["bb_middle"] + (bb_std * 2)
        df["bb_lower"] = df["bb_middle"] - (bb_std * 2)
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_middle"]
        df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])
        
        # ATR (Average True Range)
        high_low = df["high"] - df["low"]
        high_close = np.abs(df["high"] - df["close"].shift())
        low_close = np.abs(df["low"] - df["close"].shift())
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        
        for period in [7, 14, 21]:
            df[f"atr_{period}"] = tr.rolling(window=period).mean()
        
        # Historical Volatility
        df["volatility"] = df["close"].pct_change().rolling(window=20).std() * np.sqrt(365)
        
        # Donchian Channels
        df["dc_upper"] = df["high"].rolling(window=20).max()
        df["dc_lower"] = df["low"].rolling(window=20).min()
        df["dc_middle"] = (df["dc_upper"] + df["dc_lower"]) / 2
        
        return df
    
    def add_volume_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volume indicators.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with volume indicators
        """
        df = df.copy()
        
        # Volume moving averages
        for period in [20, 50]:
            df[f"volume_sma_{period}"] = df["volume"].rolling(window=period).mean()
        
        # OBV (On Balance Volume)
        obv = [0]
        for i in range(1, len(df)):
            if df["close"].iloc[i] > df["close"].iloc[i-1]:
                obv.append(obv[-1] + df["volume"].iloc[i])
            elif df["close"].iloc[i] < df["close"].iloc[i-1]:
                obv.append(obv[-1] - df["volume"].iloc[i])
            else:
                obv.append(obv[-1])
        df["obv"] = obv
        
        # VWAP
        typical_price = (df["high"] + df["low"] + df["close"]) / 3
        df["vwap"] = (typical_price * df["volume"]).cumsum() / df["volume"].cumsum()
        
        # Volume Profile
        df["volume_ema"] = df["volume"].ewm(span=20, adjust=False).mean()
        df["volume_ratio"] = df["volume"] / df["volume_ema"]
        
        return df
    
    def add_support_resistance(self, df: pd.DataFrame, lookback: int = 20) -> pd.DataFrame:
        """Add support and resistance levels.
        
        Args:
            df: OHLCV DataFrame
            lookback: Lookback period for levels
            
        Returns:
            DataFrame with support/resistance
        """
        df = df.copy()
        
        # Pivot points
        df["pivot"] = (df["high"] + df["low"] + df["close"]) / 3
        df["pivot_high"] = df["high"].rolling(window=lookback, center=True).max()
        df["pivot_low"] = df["low"].rolling(window=lookback, center=True).min()
        
        # Fibonacci retracement levels
        high = df["high"].rolling(window=lookback).max()
        low = df["low"].rolling(window=lookback).min()
        diff = high - low
        
        df["fib_0"] = low
        df["fib_236"] = low + 0.236 * diff
        df["fib_382"] = low + 0.382 * diff
        df["fib_500"] = low + 0.5 * diff
        df["fib_618"] = low + 0.618 * diff
        df["fib_786"] = low + 0.786 * diff
        df["fib_1000"] = high
        
        # Distance to nearest support/resistance
        df["dist_to_resistance"] = (df["pivot_high"] - df["close"]) / df["close"]
        df["dist_to_support"] = (df["close"] - df["pivot_low"]) / df["close"]
        
        return df
    
    def add_price_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add price-based features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with price features
        """
        df = df.copy()
        
        # Returns
        for period in [1, 5, 10, 20]:
            df[f"return_{period}d"] = df["close"].pct_change(period)
        
        # Log returns
        df["log_return"] = np.log(df["close"] / df["close"].shift(1))
        
        # Price position within range
        df["price_position"] = (df["close"] - df["low"]) / (df["high"] - df["low"] + 1e-10)
        
        # Body size and wicks
        df["body_size"] = abs(df["close"] - df["open"]) / df["open"]
        df["upper_wick"] = (df["high"] - df[["close", "open"]].max(axis=1)) / df["open"]
        df["lower_wick"] = (df[["close", "open"]].min(axis=1) - df["low"]) / df["open"]
        
        # Gap detection
        df["gap"] = (df["open"] - df["close"].shift(1)) / df["close"].shift(1)
        
        return df
    
    def get_feature_names(self) -> List[str]:
        """Get list of all indicator feature names.
        
        Returns:
            List of feature names
        """
        return [
            # Trend
            "ema_9", "ema_21", "ema_50", "ema_200",
            "sma_20", "sma_50", "sma_200",
            "macd", "macd_signal", "macd_hist",
            "adx", "adx_pos", "adx_neg",
            "supertrend", "supertrend_direction",
            "ichi_tenkan", "ichi_kijun", "ichi_senkou_a", "ichi_senkou_b",
            # Momentum
            "rsi_7", "rsi_14", "rsi_21",
            "stoch_k", "stoch_d",
            "stochrsi_k", "stochrsi_d",
            "williams_r", "cci", "ao",
            "kdj_k", "kdj_d", "kdj_j",
            "roc_10", "roc_20",
            # Volatility
            "bb_upper", "bb_middle", "bb_lower", "bb_width", "bb_pct",
            "kc_upper", "kc_lower",
            "atr_7", "atr_14", "atr_21",
            "volatility",
            "dc_upper", "dc_lower", "dc_middle",
            # Volume
            "volume_sma_20", "volume_sma_50",
            "obv", "vwap", "mfi", "volume_ema", "volume_ratio",
            "cmf", "ad", "ad_osc",
            # Support/Resistance
            "pivot", "pivot_high", "pivot_low",
            "fib_0", "fib_236", "fib_382", "fib_500", "fib_618", "fib_786", "fib_1000",
            "dist_to_resistance", "dist_to_support",
        ]
