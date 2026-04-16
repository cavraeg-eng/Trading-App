"""RL-based trading strategy."""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from trading_bot.config import get_logger, ModelType
from trading_bot.features.engineering import FeatureEngineer
from trading_bot.strategy.base import BaseStrategy, Signal, SignalType

try:
    from trading_bot.models.agent import RLAgent
    from trading_bot.models.environment import TradingEnvironment
except Exception as exc:
    RLAgent = None
    TradingEnvironment = None
    MODEL_DEPENDENCY_ERROR = exc
else:
    MODEL_DEPENDENCY_ERROR = None

logger = get_logger(__name__)


class RLStrategy(BaseStrategy):
    """Reinforcement Learning based trading strategy."""
    
    def __init__(
        self,
        symbols: List[str],
        model_path: Optional[Path] = None,
        model_type: ModelType = ModelType.PPO,
        window_size: int = 50,
        confidence_threshold: float = 0.6,
        feature_columns: Optional[List[str]] = None,
    ):
        """Initialize RL strategy.
        
        Args:
            symbols: Trading symbols
            model_path: Path to trained model
            model_type: RL model type
            window_size: Observation window size
            confidence_threshold: Minimum confidence for signal
            feature_columns: Feature column names
        """
        super().__init__("RLStrategy", symbols)
        
        self.model_path = model_path
        self.model_type = model_type
        self.window_size = window_size
        self.confidence_threshold = confidence_threshold
        self.feature_columns = feature_columns
        
        self.agent: Optional[RLAgent] = None
        self.feature_engineer = FeatureEngineer()
        self.environments: Dict[str, TradingEnvironment] = {}
        self.data_buffers: Dict[str, pd.DataFrame] = {}
        self.entry_prices: Dict[str, float] = {}
        self.metadata: Dict = {}
        
        # Load model if provided
        if model_path:
            self.load_model(model_path)
    
    def load_model(self, model_path: Path) -> None:
        """Load trained model.
        
        Args:
            model_path: Path to model file
        """
        if RLAgent is None:
            raise RuntimeError(
                "RL model dependencies are not installed. "
                "Install gymnasium, torch, stable-baselines3, and optuna."
            ) from MODEL_DEPENDENCY_ERROR

        metadata_path = model_path.with_name(f"{model_path.stem}_metadata.json")
        if metadata_path.exists():
            with metadata_path.open() as file_handle:
                self.metadata = json.load(file_handle)
            metadata_model_type = self.metadata.get("model_type")
            if metadata_model_type:
                self.model_type = ModelType(metadata_model_type)
            self.window_size = int(self.metadata.get("window_size", self.window_size))
            metadata_feature_columns = self.metadata.get("feature_names")
            if metadata_feature_columns:
                self.feature_columns = list(metadata_feature_columns)

            preprocessor_name = self.metadata.get("preprocessor_path")
            if preprocessor_name:
                preprocessor_path = model_path.with_name(preprocessor_name)
                if preprocessor_path.exists():
                    self.feature_engineer.load_preprocessor(preprocessor_path)
                    if not self.feature_columns:
                        self.feature_columns = list(self.feature_engineer.feature_names)

        architecture = str(self.metadata.get("architecture", "mlp"))
        try:
            from trading_bot.models.agent import resolve_feature_extractor

            extractor_class, extractor_kwargs = resolve_feature_extractor(architecture)
        except Exception:
            extractor_class, extractor_kwargs = None, {}

        self.agent = RLAgent(
            model_type=self.model_type,
            features_extractor_class=extractor_class,
            features_extractor_kwargs=extractor_kwargs,
        )
        self.agent.load(model_path)
        logger.info(f"Model loaded from {model_path}")
    
    def prepare_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Prepare data with features.
        
        Args:
            df: Raw OHLCV data
            
        Returns:
            DataFrame with features
        """
        featured_df = self.feature_engineer.create_features(df)

        if self.feature_columns:
            for column in self.feature_columns:
                if column not in featured_df.columns:
                    featured_df[column] = 0.0

        if self.feature_engineer.scaler is not None:
            featured_df = self.feature_engineer.transform_features(
                featured_df,
                self.feature_columns or self.feature_engineer.feature_names,
            )

        if self.feature_columns:
            ordered_columns = ["open", "high", "low", "close", "volume"]
            remaining_columns = [
                column for column in featured_df.columns
                if column not in ordered_columns and column not in self.feature_columns
            ]
            featured_df = featured_df[
                [column for column in ordered_columns if column in featured_df.columns]
                + list(self.feature_columns)
                + remaining_columns
            ]

        return featured_df
    
    def generate_signal(
        self,
        symbol: str,
        data: pd.DataFrame,
    ) -> Optional[Signal]:
        """Generate trading signal using RL model.
        
        Args:
            symbol: Trading symbol
            data: Market data with features
            
        Returns:
            Signal or None
        """
        if not self.is_active:
            return None
        
        if self.agent is None:
            logger.warning("No model loaded")
            return None

        if TradingEnvironment is None:
            raise RuntimeError(
                "Trading environment dependencies are not installed."
            ) from MODEL_DEPENDENCY_ERROR
        
        if len(data) < self.window_size:
            logger.debug(f"Insufficient data for {symbol}")
            return None
        
        current_position = self.get_position(symbol)
        current_price = data["close"].iloc[-1]

        # Create or update environment
        if symbol not in self.environments:
            self.environments[symbol] = TradingEnvironment(
                df=data,
                window_size=self.window_size,
                feature_columns=self.feature_columns or self.feature_engineer.feature_names,
            )
        
        env = self.environments[symbol]
        env.df = data.reset_index(drop=True)
        env.feature_columns = self.feature_columns or self.feature_engineer.feature_names
        env.n_features = len(env.feature_columns)
        
        # Get current observation
        obs, _ = env.reset()
        env.current_step = len(data) - 1
        if current_position == SignalType.BUY:
            env.position = 1.0
            env.position_notional = env.balance
            env.entry_price = self.entry_prices.get(symbol, current_price)
        elif current_position == SignalType.SELL:
            env.position = -1.0
            env.position_notional = env.balance
            env.entry_price = self.entry_prices.get(symbol, current_price)
        obs = env._get_observation()
        
        # Get action from model
        action, _ = self.agent.predict(obs, deterministic=True)
        position_size = float(np.clip(action[0], -1.0, 1.0))
        stop_loss = float(np.clip(action[1], 0.0, 0.1)) if len(action) > 1 else 0.0
        take_profit = float(np.clip(action[2], 0.0, 0.2)) if len(action) > 2 else 0.0
        
        # Convert position size to signal
        if position_size > 0.3:  # Long threshold
            if current_position != SignalType.BUY:
                signal_type = SignalType.BUY
                confidence = min(abs(position_size), 1.0)
            else:
                return None  # Already long
        elif position_size < -0.3:  # Short threshold
            if current_position != SignalType.SELL:
                signal_type = SignalType.SELL
                confidence = min(abs(position_size), 1.0)
            else:
                return None  # Already short
        else:  # Neutral
            if current_position is not None:
                signal_type = SignalType.CLOSE
                confidence = 1.0 - abs(position_size)
            else:
                return None  # Already neutral
        
        # Check confidence threshold
        if confidence < self.confidence_threshold and signal_type != SignalType.CLOSE:
            return None
        
        signal = Signal(
            symbol=symbol,
            signal_type=signal_type,
            timestamp=datetime.now(),
            price=current_price,
            confidence=confidence,
            metadata={
                "position_size": float(position_size),
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "model_type": self.model_type.value,
            },
        )
        
        self.signals.append(signal)
        
        # Update position tracking
        if signal_type == SignalType.CLOSE:
            self.entry_prices.pop(symbol, None)
            self.set_position(symbol, None)
        else:
            self.entry_prices[symbol] = current_price
            self.set_position(symbol, signal_type)
        
        logger.info(
            "Signal generated",
            symbol=symbol,
            signal=signal_type.value,
            confidence=confidence,
            price=current_price,
        )
        
        return signal
    
    def update(self, data: Dict[str, pd.DataFrame]) -> List[Signal]:
        """Update strategy with new data.
        
        Args:
            data: Dictionary of symbol -> DataFrame
            
        Returns:
            List of signals
        """
        signals = []
        
        for symbol, df in data.items():
            if symbol not in self.symbols:
                continue
            
            # Update data buffer
            if symbol not in self.data_buffers:
                self.data_buffers[symbol] = df
            else:
                self.data_buffers[symbol] = pd.concat([
                    self.data_buffers[symbol],
                    df,
                ]).drop_duplicates().sort_index()
            
            # Keep only recent data
            if len(self.data_buffers[symbol]) > 1000:
                self.data_buffers[symbol] = self.data_buffers[symbol].iloc[-1000:]
            
            # Prepare features
            try:
                featured_data = self.prepare_data(self.data_buffers[symbol])
                
                # Generate signal
                signal = self.generate_signal(symbol, featured_data)
                if signal:
                    signals.append(signal)
            except Exception as e:
                logger.error(f"Error processing {symbol}: {e}")
        
        return signals
    
    def train(
        self,
        historical_data: Dict[str, pd.DataFrame],
        total_timesteps: int = 100000,
        save_path: Optional[Path] = None,
    ) -> None:
        """Train RL model on historical data.
        
        Args:
            historical_data: Dictionary of symbol -> historical DataFrame
            total_timesteps: Training timesteps
            save_path: Path to save model
        """
        from trading_bot.models.train import ModelTrainer
        
        logger.info("Starting RL model training")
        
        # Combine data from all symbols
        combined_data = []
        for symbol, df in historical_data.items():
            featured_df = self.prepare_data(df)
            combined_data.append(featured_df)
        
        # Use first symbol's data for training
        # In practice, you might want to train on all symbols
        train_df = combined_data[0] if combined_data else None
        
        if train_df is None or train_df.empty:
            logger.error("No training data available")
            return
        
        # Create trainer
        trainer = ModelTrainer(
            model_path=save_path or Path("./models"),
            n_trials=20,
            window_size=self.window_size,
        )
        
        # Train
        agent = trainer.train(
            df=train_df,
            model_type=self.model_type,
            total_timesteps=total_timesteps,
            optimize_hyperparams=True,
        )
        
        self.agent = agent
        logger.info("RL model training completed")
    
    def get_model_info(self) -> Dict:
        """Get model information.
        
        Returns:
            Model info dictionary
        """
        if self.agent is None:
            return {"loaded": False}
        
        return {
            "loaded": True,
            "model_type": self.model_type.value,
            "hyperparameters": self.agent.get_hyperparameters(),
        }
