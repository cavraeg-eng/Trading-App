import json
from pathlib import Path

import pandas as pd
import pytest

from trading_bot.config import ModelType
from trading_bot.features.engineering import FeatureEngineer
from trading_bot.features.indicators import TechnicalIndicators


def _build_ohlcv(length: int = 320) -> pd.DataFrame:
    index = pd.date_range("2025-01-01", periods=length, freq="H", tz="UTC")
    close = pd.Series(range(length), index=index, dtype=float) * 0.25 + 100.0
    open_price = close.shift(1).fillna(close.iloc[0])

    return pd.DataFrame(
        {
            "open": open_price,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": pd.Series(1000.0 + (close.index.hour * 10), index=index),
        },
        index=index,
    )


def test_support_resistance_uses_only_past_data():
    df = _build_ohlcv(60)
    df.loc[df.index[40], "high"] = 1000.0

    indicators = TechnicalIndicators()
    featured = indicators.add_support_resistance(df, lookback=20)

    target_index = df.index[30]
    expected = df["high"].iloc[10:30].max()
    assert featured.loc[target_index, "pivot_high"] == expected
    assert featured.loc[target_index, "pivot_high"] != 1000.0


def test_feature_engineer_preprocessor_roundtrip(tmp_path: Path):
    df = _build_ohlcv()
    engineer = FeatureEngineer(lookback_window=32)
    featured = engineer.create_features(df)
    engineer.fit_scaler(featured, engineer.feature_names)

    path = tmp_path / "preprocessor.pkl"
    engineer.save_preprocessor(path)

    restored = FeatureEngineer()
    restored.load_preprocessor(path)

    assert restored.lookback_window == 32
    assert restored.feature_names == engineer.feature_names
    assert restored.scaler is not None


def test_rl_strategy_loads_metadata_and_preprocessor(tmp_path: Path):
    rl_strategy = pytest.importorskip("trading_bot.strategy.rl_strategy")
    RLStrategy = rl_strategy.RLStrategy

    model_path = tmp_path / "PPO_test.zip"
    model_path.write_bytes(b"placeholder")

    engineer = FeatureEngineer(lookback_window=24)
    featured = engineer.create_features(_build_ohlcv())
    engineer.fit_scaler(featured, engineer.feature_names)
    engineer.save_preprocessor(tmp_path / "PPO_test_preprocessor.pkl")

    metadata = {
        "model_type": ModelType.PPO.value,
        "window_size": 24,
        "feature_names": engineer.feature_names[:5],
        "preprocessor_path": "PPO_test_preprocessor.pkl",
    }
    (tmp_path / "PPO_test_metadata.json").write_text(json.dumps(metadata))

    strategy = RLStrategy(symbols=["BTC/USDT"])

    class DummyAgent:
        def __init__(
            self,
            model_type: ModelType,
            features_extractor_class=None,
            features_extractor_kwargs=None,
        ):
            self.model_type = model_type
            self.features_extractor_class = features_extractor_class
            self.features_extractor_kwargs = features_extractor_kwargs or {}
            self.loaded_path = None

        def load(self, path: Path, env=None):
            self.loaded_path = path

    original_agent_class = rl_strategy.RLAgent
    rl_strategy.RLAgent = DummyAgent
    try:
        strategy.load_model(model_path)
    finally:
        rl_strategy.RLAgent = original_agent_class

    assert strategy.window_size == 24
    assert strategy.feature_columns == engineer.feature_names[:5]
    assert strategy.feature_engineer.scaler is not None
    assert strategy.agent is not None
    assert strategy.agent.loaded_path == model_path