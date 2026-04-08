"""Advanced feature engineering for trading."""

from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats
from scipy.fft import fft
from sklearn.preprocessing import RobustScaler, StandardScaler

from trading_bot.config import get_logger
from trading_bot.features.indicators import TechnicalIndicators

logger = get_logger(__name__)


class FeatureEngineer:
    """Advanced feature engineering for trading."""
    
    def __init__(self, lookback_window: int = 50):
        """Initialize feature engineer.
        
        Args:
            lookback_window: Window for rolling calculations
        """
        self.lookback_window = lookback_window
        self.indicators = TechnicalIndicators()
        self.scaler: Optional[StandardScaler] = None
        self.feature_names: List[str] = []
    
    def create_features(
        self,
        df: pd.DataFrame,
        add_indicators: bool = True,
        add_custom: bool = True,
        add_lags: bool = True,
        add_rolling: bool = True,
    ) -> pd.DataFrame:
        """Create complete feature set.
        
        Args:
            df: OHLCV DataFrame
            add_indicators: Add technical indicators
            add_custom: Add custom features
            add_lags: Add lagged features
            add_rolling: Add rolling statistics
            
        Returns:
            DataFrame with all features
        """
        df = df.copy()
        
        if add_indicators:
            logger.info("Adding technical indicators")
            df = self.indicators.add_all_indicators(df)
            df = self.indicators.add_price_features(df)
        
        if add_custom:
            logger.info("Adding custom features")
            df = self.add_volatility_regime(df)
            df = self.add_trend_strength(df)
            df = self.add_momentum_regime(df)
            df = self.add_market_structure(df)
            df = self.add_fourier_features(df)
        
        if add_rolling:
            logger.info("Adding rolling statistics")
            df = self.add_rolling_stats(df)
        
        if add_lags:
            logger.info("Adding lagged features")
            df = self.add_lagged_features(df)
        
        # Store feature names
        self.feature_names = [c for c in df.columns if c not in ["open", "high", "low", "close", "volume"]]
        
        # Drop rows with NaN values
        initial_len = len(df)
        df = df.dropna()
        dropped = initial_len - len(df)
        
        if dropped > 0:
            logger.info(f"Dropped {dropped} rows with NaN values")
        
        return df
    
    def add_volatility_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility regime features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with volatility regime features
        """
        df = df.copy()
        
        # Calculate returns
        returns = df["close"].pct_change()
        
        # Realized volatility (different windows)
        for window in [5, 10, 20, 50]:
            df[f"realized_vol_{window}d"] = returns.rolling(window).std() * np.sqrt(365)
        
        # Volatility regime (low, medium, high)
        vol_20 = df["realized_vol_20d"]
        vol_percentile = vol_20.rolling(252).apply(lambda x: stats.percentileofscore(x, x.iloc[-1]))
        
        df["vol_regime"] = pd.cut(
            vol_percentile,
            bins=[0, 33, 66, 100],
            labels=[0, 1, 2],  # low, medium, high
        ).astype(float)
        
        # Volatility trend
        df["vol_trend"] = np.where(
            df["realized_vol_5d"] > df["realized_vol_20d"], 1,
            np.where(df["realized_vol_5d"] < df["realized_vol_20d"], -1, 0)
        )
        
        # Volatility of volatility
        df["vol_of_vol"] = df["realized_vol_20d"].rolling(20).std()
        
        # GARCH-like features (squared returns)
        df["squared_returns"] = returns ** 2
        for window in [5, 20]:
            df[f"sq_ret_ma_{window}"] = df["squared_returns"].rolling(window).mean()
        
        return df
    
    def add_trend_strength(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add trend strength features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with trend strength features
        """
        df = df.copy()
        
        # Linear regression slope
        for window in [10, 20, 50]:
            x = np.arange(window)
            slopes = df["close"].rolling(window).apply(
                lambda y: np.polyfit(x[-len(y):], y, 1)[0] if len(y) >= 2 else 0,
                raw=True,
            )
            df[f"trend_slope_{window}"] = slopes
            
            # R-squared of trend
            r2 = df["close"].rolling(window).apply(
                lambda y: np.corrcoef(x[-len(y):], y)[0, 1] ** 2 if len(y) >= 2 else 0,
                raw=True,
            )
            df[f"trend_r2_{window}"] = r2
        
        # Price vs moving averages
        if "ema_50" in df.columns:
            df["price_vs_ema50"] = (df["close"] - df["ema_50"]) / df["ema_50"]
        if "sma_200" in df.columns:
            df["price_vs_sma200"] = (df["close"] - df["sma_200"]) / df["sma_200"]
        
        # Trend alignment (all EMAs aligned)
        if all(col in df.columns for col in ["ema_9", "ema_21", "ema_50"]):
            df["trend_alignment"] = np.where(
                (df["ema_9"] > df["ema_21"]) & (df["ema_21"] > df["ema_50"]), 1,  # Uptrend
                np.where(
                    (df["ema_9"] < df["ema_21"]) & (df["ema_21"] < df["ema_50"]), -1,  # Downtrend
                    0  # Mixed
                )
            )
        
        return df
    
    def add_momentum_regime(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum regime features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with momentum regime features
        """
        df = df.copy()
        
        # Momentum (price change over different periods)
        for period in [5, 10, 20, 50]:
            df[f"momentum_{period}d"] = df["close"].pct_change(period)
        
        # Acceleration (change in momentum)
        df["momentum_accel"] = df["momentum_10d"].diff()
        
        # Momentum divergence (price vs RSI)
        if "rsi_14" in df.columns:
            price_momentum = df["close"].pct_change(14)
            rsi_momentum = df["rsi_14"].diff(14)
            df["momentum_divergence"] = np.where(
                (price_momentum > 0) & (rsi_momentum < 0), -1,  # Bearish divergence
                np.where(
                    (price_momentum < 0) & (rsi_momentum > 0), 1,  # Bullish divergence
                    0
                )
            )
        
        # Rate of change momentum
        df["roc_momentum"] = df["close"].pct_change(10).rolling(10).mean()
        
        return df
    
    def add_market_structure(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add market structure features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with market structure features
        """
        df = df.copy()
        
        # Higher highs / lower lows detection
        window = 5
        df["higher_high"] = (
            (df["high"] > df["high"].shift(1)) & 
            (df["high"].shift(1) > df["high"].shift(2))
        ).astype(int)
        
        df["lower_low"] = (
            (df["low"] < df["low"].shift(1)) & 
            (df["low"].shift(1) < df["low"].shift(2))
        ).astype(int)
        
        # Market structure score
        df["structure_score"] = df["higher_high"].rolling(window).sum() - df["lower_low"].rolling(window).sum()
        
        # Breakout detection
        df["resistance_break"] = (df["close"] > df["high"].rolling(20).max().shift(1)).astype(int)
        df["support_break"] = (df["close"] < df["low"].rolling(20).min().shift(1)).astype(int)
        
        # Range contraction/expansion
        df["atr_ratio"] = df["atr_14"] / df["atr_14"].rolling(20).mean() if "atr_14" in df.columns else 1
        
        return df
    
    def add_fourier_features(self, df: pd.DataFrame, n_components: int = 5) -> pd.DataFrame:
        """Add Fourier transform features.
        
        Args:
            df: OHLCV DataFrame
            n_components: Number of Fourier components
            
        Returns:
            DataFrame with Fourier features
        """
        df = df.copy()
        
        # Detrend price
        price = df["close"].values
        detrended = price - np.mean(price)
        
        # FFT
        if len(detrended) >= n_components * 2:
            fft_vals = fft(detrended)
            frequencies = np.fft.fftfreq(len(detrended))
            
            # Add dominant frequencies as features
            for i in range(1, min(n_components + 1, len(fft_vals) // 2)):
                df[f"fft_amp_{i}"] = np.abs(fft_vals[i])
                df[f"fft_freq_{i}"] = frequencies[i]
        
        # Cyclical time features
        df["hour_sin"] = np.sin(2 * np.pi * df.index.hour / 24)
        df["hour_cos"] = np.cos(2 * np.pi * df.index.hour / 24)
        df["dayofweek_sin"] = np.sin(2 * np.pi * df.index.dayofweek / 7)
        df["dayofweek_cos"] = np.cos(2 * np.pi * df.index.dayofweek / 7)
        
        return df
    
    def add_rolling_stats(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add rolling statistics features.
        
        Args:
            df: OHLCV DataFrame
            
        Returns:
            DataFrame with rolling statistics
        """
        df = df.copy()
        
        returns = df["close"].pct_change()
        
        for window in [5, 10, 20, 50]:
            # Rolling mean and std of returns
            df[f"ret_mean_{window}"] = returns.rolling(window).mean()
            df[f"ret_std_{window}"] = returns.rolling(window).std()
            
            # Skewness and kurtosis
            df[f"ret_skew_{window}"] = returns.rolling(window).skew()
            df[f"ret_kurt_{window}"] = returns.rolling(window).kurt()
            
            # Min/Max
            df[f"ret_min_{window}"] = returns.rolling(window).min()
            df[f"ret_max_{window}"] = returns.rolling(window).max()
            
            # Quantiles
            df[f"ret_q10_{window}"] = returns.rolling(window).quantile(0.1)
            df[f"ret_q90_{window}"] = returns.rolling(window).quantile(0.9)
        
        return df
    
    def add_lagged_features(self, df: pd.DataFrame, lags: List[int] = None) -> pd.DataFrame:
        """Add lagged features.
        
        Args:
            df: OHLCV DataFrame
            lags: List of lag periods
            
        Returns:
            DataFrame with lagged features
        """
        df = df.copy()
        
        if lags is None:
            lags = [1, 2, 3, 5, 10]
        
        # Key features to lag
        base_features = ["close", "volume", "rsi_14", "atr_14"]
        base_features = [f for f in base_features if f in df.columns]
        
        for feature in base_features:
            for lag in lags:
                df[f"{feature}_lag_{lag}"] = df[feature].shift(lag)
        
        return df
    
    def add_cross_asset_features(
        self,
        df: pd.DataFrame,
        other_assets: Dict[str, pd.DataFrame],
    ) -> pd.DataFrame:
        """Add cross-asset correlation features.
        
        Args:
            df: Primary asset DataFrame
            other_assets: Dict of other asset DataFrames
            
        Returns:
            DataFrame with cross-asset features
        """
        df = df.copy()
        
        primary_returns = df["close"].pct_change()
        
        for name, other_df in other_assets.items():
            if len(other_df) != len(df):
                continue
            
            other_returns = other_df["close"].pct_change()
            
            # Correlation
            for window in [20, 50]:
                df[f"corr_{name}_{window}"] = primary_returns.rolling(window).corr(other_returns)
            
            # Beta (sensitivity to other asset)
            df[f"beta_{name}"] = (
                primary_returns.rolling(50).cov(other_returns) / 
                other_returns.rolling(50).var()
            )
            
            # Relative strength
            df[f"rel_str_{name}"] = (df["close"] / df["close"].iloc[0]) / (other_df["close"] / other_df["close"].iloc[0])
        
        return df
    
    def scale_features(
        self,
        df: pd.DataFrame,
        feature_cols: Optional[List[str]] = None,
        fit: bool = True,
    ) -> pd.DataFrame:
        """Scale features using RobustScaler.
        
        Args:
            df: DataFrame with features
            feature_cols: Columns to scale (None = all numeric except OHLCV)
            fit: Whether to fit the scaler
            
        Returns:
            DataFrame with scaled features
        """
        df = df.copy()
        
        if feature_cols is None:
            exclude = ["open", "high", "low", "close", "volume"]
            feature_cols = [c for c in df.select_dtypes(include=[np.number]).columns if c not in exclude]
        
        if fit or self.scaler is None:
            self.scaler = RobustScaler()
            df[feature_cols] = self.scaler.fit_transform(df[feature_cols])
        else:
            df[feature_cols] = self.scaler.transform(df[feature_cols])
        
        return df
    
    def get_feature_importance(
        self,
        df: pd.DataFrame,
        target_col: str = "target",
        method: str = "mutual_info",
    ) -> pd.Series:
        """Calculate feature importance.
        
        Args:
            df: DataFrame with features and target
            target_col: Target column name
            method: Importance method ('mutual_info', 'correlation')
            
        Returns:
            Series with feature importance scores
        """
        from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
        
        feature_cols = [c for c in df.columns if c not in [target_col, "open", "high", "low", "close", "volume"]]
        X = df[feature_cols].dropna()
        y = df.loc[X.index, target_col]
        
        if method == "mutual_info":
            if y.dtype == "object" or y.nunique() < 10:
                scores = mutual_info_classif(X, y, random_state=42)
            else:
                scores = mutual_info_regression(X, y, random_state=42)
            importance = pd.Series(scores, index=feature_cols)
        
        elif method == "correlation":
            importance = X.corrwith(y).abs()
        
        else:
            raise ValueError(f"Unknown method: {method}")
        
        return importance.sort_values(ascending=False)
