"""Model training pipeline with hyperparameter optimization."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import joblib
import numpy as np
import optuna
import pandas as pd

from trading_bot.config import ModelType, get_logger
from trading_bot.features.engineering import FeatureEngineer
from trading_bot.models.agent import RLAgent, resolve_feature_extractor
from trading_bot.models.environment import TradingEnvironment

logger = get_logger(__name__)


class ModelTrainer:
    """Model training pipeline."""
    
    def __init__(
        self,
        model_path: Path,
        n_trials: int = 50,
        n_splits: int = 5,
        train_ratio: float = 0.8,
        window_size: int = 50,
        architecture: str = "mlp",
    ):
        """Initialize model trainer.
        
        Args:
            model_path: Path to save models
            n_trials: Number of Optuna trials
            n_splits: Number of CV splits
            train_ratio: Train/test split ratio
        """
        self.model_path = Path(model_path)
        self.model_path.mkdir(parents=True, exist_ok=True)
        self.n_trials = n_trials
        self.n_splits = n_splits
        self.train_ratio = train_ratio
        self.window_size = window_size
        self.architecture = architecture
        self.feature_engineer = FeatureEngineer(lookback_window=window_size)
        self.feature_names: List[str] = []
        
        self.best_params: Optional[Dict] = None
        self.study: Optional[optuna.Study] = None

    def _get_agent_kwargs(self) -> Dict:
        """Get agent kwargs for the selected architecture."""
        extractor_class, extractor_kwargs = resolve_feature_extractor(self.architecture)
        if extractor_class is None:
            return {}
        return {
            "features_extractor_class": extractor_class,
            "features_extractor_kwargs": extractor_kwargs,
        }
    
    def prepare_data(
        self,
        df: pd.DataFrame,
        engineer_features: bool = True,
    ) -> pd.DataFrame:
        """Prepare data for training.
        
        Args:
            df: Raw OHLCV data
            engineer_features: Whether to engineer features
            
        Returns:
            Processed DataFrame
        """
        if engineer_features:
            logger.info("Engineering features")
            df = self.feature_engineer.create_features(df)
            self.feature_names = list(self.feature_engineer.feature_names)
        
        return df

    def prepare_train_test_data(
        self,
        train_raw_df: pd.DataFrame,
        test_raw_df: Optional[pd.DataFrame] = None,
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Prepare leakage-safe train/test datasets with shared feature history."""
        if test_raw_df is None:
            prepared_df = self.prepare_data(train_raw_df)
            train_df, test_df = self._split_dataframe(prepared_df)
        else:
            train_df = train_raw_df.copy()
            test_df = test_raw_df.copy()

            train_df["_dataset_split"] = "train"
            test_df["_dataset_split"] = "test"

            combined_df = pd.concat([train_df, test_df], axis=0)
            prepared_df = self.prepare_data(combined_df)

            train_df = prepared_df[prepared_df["_dataset_split"] == "train"].drop(
                columns="_dataset_split"
            )
            test_df = prepared_df[prepared_df["_dataset_split"] == "test"].drop(
                columns="_dataset_split"
            )

        if len(train_df) <= self.window_size or len(test_df) <= self.window_size:
            raise ValueError(
                "Insufficient data after feature engineering. Increase history or reduce window size."
            )

        self.feature_engineer.fit_scaler(train_df, self.feature_names)
        train_df = self.feature_engineer.transform_features(train_df, self.feature_names)
        test_df = self.feature_engineer.transform_features(test_df, self.feature_names)

        return train_df, test_df

    def _split_dataframe(self, df: pd.DataFrame) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """Create a chronological train/test split."""
        if len(df) < self.window_size * 3:
            raise ValueError(
                f"Need at least {self.window_size * 3} rows for stable training; received {len(df)}."
            )

        train_size = int(len(df) * self.train_ratio)
        min_train_size = self.window_size * 2
        max_train_size = len(df) - self.window_size
        train_size = max(min_train_size, min(train_size, max_train_size))

        train_df = df.iloc[:train_size].copy()
        test_df = df.iloc[train_size:].copy()
        return train_df, test_df
    
    def create_environment(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        window_size: Optional[int] = None,
        feature_columns: Optional[List[str]] = None,
    ) -> TradingEnvironment:
        """Create trading environment.
        
        Args:
            df: DataFrame with features
            initial_balance: Initial balance
            window_size: Observation window
            feature_columns: Feature column names
            
        Returns:
            Trading environment
        """
        return TradingEnvironment(
            df=df,
            initial_balance=initial_balance,
            window_size=window_size or self.window_size,
            feature_columns=feature_columns or self.feature_names,
        )
    
    def train(
        self,
        df: pd.DataFrame,
        model_type: ModelType = ModelType.PPO,
        total_timesteps: int = 100000,
        optimize_hyperparams: bool = True,
        use_optuna: bool = True,
    ) -> RLAgent:
        """Train RL model.
        
        Args:
            df: Training data
            model_type: PPO or SAC
            total_timesteps: Training timesteps
            optimize_hyperparams: Whether to optimize hyperparameters
            use_optuna: Use Optuna for optimization
            
        Returns:
            Trained agent
        """
        train_df, test_df = self.prepare_train_test_data(df)
        
        logger.info(
            "Data split",
            train_size=len(train_df),
            test_size=len(test_df),
        )

        agent, _, _ = self._train_prepared_data(
            train_df=train_df,
            test_df=test_df,
            model_type=model_type,
            total_timesteps=total_timesteps,
            optimize_hyperparams=optimize_hyperparams,
            use_optuna=use_optuna,
            persist_artifacts=True,
        )

        return agent
    
    def optimize_hyperparameters(
        self,
        df: pd.DataFrame,
        model_type: ModelType,
        n_trials: int = 50,
    ) -> Dict:
        """Optimize hyperparameters using Optuna.
        
        Args:
            df: Training data
            model_type: Model type
            n_trials: Number of trials
            
        Returns:
            Best hyperparameters
        """
        def objective(trial: optuna.Trial) -> float:
            """Optuna objective function."""
            params = self._sample_hyperparameters(trial, model_type)
            split_scores: List[float] = []

            for train_index, validation_index in self._get_optimization_splits(df):
                fold_train_df = df.iloc[train_index].copy()
                fold_validation_df = df.iloc[validation_index].copy()

                if len(fold_train_df) <= self.window_size or len(fold_validation_df) <= self.window_size:
                    continue

                train_env = self.create_environment(fold_train_df)
                validation_env = self.create_environment(fold_validation_df)

                agent = RLAgent(
                    model_type=model_type,
                    **params,
                    **self._get_agent_kwargs(),
                    verbose=0,
                )
                agent.create_model(train_env)

                optimization_timesteps = min(30000, max(5000, len(fold_train_df) * 5))
                agent.train(
                    total_timesteps=optimization_timesteps,
                    eval_env=validation_env,
                    eval_freq=max(1000, optimization_timesteps // 5),
                )

                metrics = self._evaluate_detailed(agent, validation_env)
                split_scores.append(self._score_metrics(metrics))

            if not split_scores:
                return float("-inf")

            return float(np.mean(split_scores))
        
        # Create study
        self.study = optuna.create_study(
            direction="maximize",
            pruner=optuna.pruners.MedianPruner(),
        )
        
        # Optimize
        self.study.optimize(objective, n_trials=n_trials, show_progress_bar=True)
        
        # Get best params
        best_params = self.study.best_params
        
        logger.info(
            "Hyperparameter optimization completed",
            best_value=self.study.best_value,
            best_params=best_params,
        )
        
        # Save study
        joblib.dump(self.study, self.model_path / "optuna_study.pkl")
        
        return best_params

    def _get_optimization_splits(
        self,
        df: pd.DataFrame,
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """Create chronological validation splits for Optuna."""
        max_splits = min(self.n_splits, max(2, len(df) // max(self.window_size * 4, 50)))
        if max_splits < 2:
            return []

        sample_count = len(df)
        test_size = max(self.window_size, sample_count // (max_splits + 1))
        splits: List[Tuple[np.ndarray, np.ndarray]] = []

        for split_index in range(max_splits):
            train_end = test_size * (split_index + 1)
            test_start = train_end
            test_end = min(test_start + test_size, sample_count)

            if train_end <= self.window_size or test_end - test_start <= self.window_size:
                continue

            train_index = np.arange(0, train_end)
            test_index = np.arange(test_start, test_end)
            splits.append((train_index, test_index))

        return splits[-min(3, len(splits)):]
    
    def _sample_hyperparameters(
        self,
        trial: optuna.Trial,
        model_type: ModelType,
    ) -> Dict:
        """Sample hyperparameters for Optuna.
        
        Args:
            trial: Optuna trial
            model_type: Model type
            
        Returns:
            Hyperparameter dictionary
        """
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 1e-5, 1e-3, log=True),
            "batch_size": trial.suggest_categorical("batch_size", [32, 64, 128, 256]),
            "gamma": trial.suggest_float("gamma", 0.95, 0.999),
            "ent_coef": trial.suggest_float("ent_coef", 1e-5, 0.02, log=True),
            "max_grad_norm": trial.suggest_float("max_grad_norm", 0.3, 1.0),
        }
        
        if model_type == ModelType.PPO:
            params.update({
                "n_steps": trial.suggest_categorical("n_steps", [512, 1024, 2048, 4096]),
                "gae_lambda": trial.suggest_float("gae_lambda", 0.9, 0.99),
                "clip_range": trial.suggest_float("clip_range", 0.1, 0.25),
                "vf_coef": trial.suggest_float("vf_coef", 0.3, 0.9),
            })
        
        return params
    
    def _evaluate_agent(
        self,
        agent: RLAgent,
        env: TradingEnvironment,
        n_episodes: int = 5,
    ) -> float:
        """Evaluate agent performance.
        
        Args:
            agent: RL agent
            env: Environment
            n_episodes: Number of episodes
            
        Returns:
            Mean reward
        """
        rewards = []
        
        for _ in range(n_episodes):
            obs, _ = env.reset()
            done = False
            episode_reward = 0.0
            
            while not done:
                action, _ = agent.predict(obs, deterministic=True)
                obs, reward, terminated, truncated, _ = env.step(action)
                episode_reward += reward
                done = terminated or truncated
            
            rewards.append(episode_reward)
        
        return np.mean(rewards)

    def _score_metrics(self, metrics: Dict[str, float]) -> float:
        """Convert evaluation metrics into a single Optuna score."""
        total_return = float(metrics.get("total_return", 0.0) or 0.0)
        sharpe_ratio = float(metrics.get("sharpe_ratio", 0.0) or 0.0)
        max_drawdown = float(metrics.get("max_drawdown", 1.0) or 1.0)
        win_rate = float(metrics.get("win_rate", 0.0) or 0.0)
        num_trades = float(metrics.get("num_trades", 0.0) or 0.0)

        trade_activity_penalty = -0.5 if num_trades < 2 else 0.0
        return (
            total_return * 100.0
            + sharpe_ratio * 2.5
            + win_rate * 10.0
            - max_drawdown * 20.0
            + trade_activity_penalty
        )

    def _train_prepared_data(
        self,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        model_type: ModelType,
        total_timesteps: int,
        optimize_hyperparams: bool,
        use_optuna: bool,
        persist_artifacts: bool,
    ) -> Tuple[RLAgent, Dict[str, float], Optional[str]]:
        """Train on already prepared datasets."""
        if optimize_hyperparams and use_optuna:
            logger.info("Starting hyperparameter optimization")
            self.best_params = self.optimize_hyperparameters(
                train_df,
                model_type,
                n_trials=self.n_trials,
            )
        else:
            self.best_params = self.get_default_params(model_type)

        train_env = self.create_environment(train_df)
        test_env = self.create_environment(test_df)

        agent = RLAgent(
            model_type=model_type,
            **self.best_params,
            **self._get_agent_kwargs(),
            verbose=1,
            tensorboard_log=str(self.model_path / "tensorboard"),
        )
        agent.create_model(train_env)
        agent.train(
            total_timesteps=total_timesteps,
            eval_env=test_env,
            eval_freq=max(2000, total_timesteps // 10),
            save_path=self.model_path if persist_artifacts else None,
            save_freq=max(10000, total_timesteps // 2),
        )

        evaluation_metrics = self._evaluate_detailed(
            agent,
            self.create_environment(test_df),
        )

        model_name: Optional[str] = None
        if persist_artifacts:
            model_name = self._save_training_artifacts(
                agent=agent,
                model_type=model_type,
                train_df=train_df,
                test_df=test_df,
                evaluation_metrics=evaluation_metrics,
            )

        return agent, evaluation_metrics, model_name

    def _save_training_artifacts(
        self,
        agent: RLAgent,
        model_type: ModelType,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
        evaluation_metrics: Dict[str, float],
    ) -> str:
        """Persist the trained model, metadata, and preprocessing artifacts."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        model_name = f"{model_type.value}_{timestamp}"

        model_file = self.model_path / f"{model_name}.zip"
        preprocessor_file = self.model_path / f"{model_name}_preprocessor.pkl"
        metadata_file = self.model_path / f"{model_name}_metadata.json"

        agent.save(model_file)
        self.feature_engineer.save_preprocessor(preprocessor_file)

        metadata = {
            "model_type": model_type.value,
            "timestamp": timestamp,
            "hyperparameters": self.best_params,
            "train_size": len(train_df),
            "test_size": len(test_df),
            "window_size": self.window_size,
            "architecture": self.architecture,
            "feature_names": list(self.feature_names),
            "validation_metrics": evaluation_metrics,
            "preprocessor_path": preprocessor_file.name,
        }

        with open(metadata_file, "w") as file_handle:
            json.dump(self._to_serializable(metadata), file_handle, indent=2)

        logger.info(
            "Model saved",
            model_name=model_name,
            validation_metrics=evaluation_metrics,
        )
        return model_name

    def _to_serializable(self, value: Any) -> Any:
        """Convert numpy/pandas objects into JSON-friendly Python values."""
        if isinstance(value, dict):
            return {key: self._to_serializable(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self._to_serializable(item) for item in value]
        if isinstance(value, tuple):
            return [self._to_serializable(item) for item in value]
        if isinstance(value, (np.floating, np.integer)):
            return value.item()
        return value
    
    def walk_forward_validation(
        self,
        df: pd.DataFrame,
        model_type: ModelType = ModelType.PPO,
        train_days: int = 180,
        test_days: int = 30,
        timesteps_per_fold: int = 50000,
    ) -> List[Dict]:
        """Perform walk-forward validation.
        
        Args:
            df: Full dataset
            model_type: Model type
            train_days: Training window in days
            test_days: Testing window in days
            timesteps_per_fold: Training timesteps per fold
            
        Returns:
            List of fold results
        """
        results = []
        
        # Calculate number of folds
        total_days = len(df)
        fold_size = train_days + test_days
        n_folds = (total_days - train_days) // test_days
        
        logger.info(f"Walk-forward validation: {n_folds} folds")
        
        for fold in range(n_folds):
            logger.info(f"Processing fold {fold + 1}/{n_folds}")
            
            # Split data
            train_start = fold * test_days
            train_end = train_start + train_days
            test_end = min(train_end + test_days, total_days)
            
            train_df = df.iloc[train_start:train_end]
            test_df = df.iloc[train_end:test_end]
            
            if len(test_df) < 10:
                logger.warning(f"Skipping fold {fold + 1}: insufficient test data")
                continue

            prepared_train_df, prepared_test_df = self.prepare_train_test_data(train_df, test_df)
            _, metrics, _ = self._train_prepared_data(
                train_df=prepared_train_df,
                test_df=prepared_test_df,
                model_type=model_type,
                total_timesteps=timesteps_per_fold,
                optimize_hyperparams=False,
                use_optuna=False,
                persist_artifacts=False,
            )
            
            results.append({
                "fold": fold + 1,
                "train_start": str(train_df.index[0]),
                "train_end": str(train_df.index[-1]),
                "test_start": str(test_df.index[0]),
                "test_end": str(test_df.index[-1]),
                **metrics,
            })
        
        # Save results
        results_df = pd.DataFrame(results)
        results_df.to_csv(self.model_path / "walk_forward_results.csv", index=False)

        if not results_df.empty:
            summary = {
                "num_folds": len(results_df),
                "average_total_return": float(results_df["total_return"].mean()),
                "median_total_return": float(results_df["total_return"].median()),
                "average_sharpe_ratio": float(results_df["sharpe_ratio"].mean()),
                "average_max_drawdown": float(results_df["max_drawdown"].mean()),
                "average_win_rate": float(results_df["win_rate"].mean()),
                "average_num_trades": float(results_df["num_trades"].mean()),
                "profitable_fold_ratio": float((results_df["total_return"] > 0).mean()),
                "worst_fold_return": float(results_df["total_return"].min()),
                "worst_fold_drawdown": float(results_df["max_drawdown"].max()),
            }
            summary["composite_score"] = float(
                self._score_metrics(
                    {
                        "total_return": summary["average_total_return"],
                        "sharpe_ratio": summary["average_sharpe_ratio"],
                        "max_drawdown": summary["average_max_drawdown"],
                        "win_rate": summary["average_win_rate"],
                        "num_trades": summary["average_num_trades"],
                    }
                )
            )

            with open(self.model_path / "walk_forward_summary.json", "w") as file_handle:
                json.dump(self._to_serializable(summary), file_handle, indent=2)
        
        logger.info("Walk-forward validation completed")
        logger.info(f"Average return: {results_df['total_return'].mean():.2%}")
        logger.info(f"Average Sharpe: {results_df['sharpe_ratio'].mean():.2f}")
        
        return results
    
    def _evaluate_detailed(
        self,
        agent: RLAgent,
        env: TradingEnvironment,
    ) -> Dict:
        """Detailed evaluation.
        
        Args:
            agent: RL agent
            env: Environment
            
        Returns:
            Metrics dictionary
        """
        obs, _ = env.reset()
        done = False
        
        while not done:
            action, _ = agent.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, _ = env.step(action)
            done = terminated or truncated
        
        return env.get_performance_metrics()
    
    def get_default_params(self, model_type: ModelType) -> Dict:
        """Get default hyperparameters.
        
        Args:
            model_type: Model type
            
        Returns:
            Default hyperparameters
        """
        params = {
            "learning_rate": 3e-4,
            "batch_size": 64,
            "gamma": 0.99,
            "ent_coef": 0.001,
            "max_grad_norm": 0.5,
        }
        
        if model_type == ModelType.PPO:
            params.update({
                "n_steps": 1024,
                "gae_lambda": 0.95,
                "clip_range": 0.15,
                "vf_coef": 0.5,
            })
        
        return params
    
    def load_study(self, path: Path) -> optuna.Study:
        """Load Optuna study.
        
        Args:
            path: Path to study file
            
        Returns:
            Optuna study
        """
        self.study = joblib.load(path)
        return self.study
