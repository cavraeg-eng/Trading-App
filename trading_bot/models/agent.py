"""RL Agent wrapper for Stable-Baselines3."""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Type

import gymnasium as gym
import numpy as np
import optuna
import torch
from stable_baselines3 import PPO, SAC
from stable_baselines3.common.callbacks import (
    BaseCallback,
    CallbackList,
    CheckpointCallback,
    EvalCallback,
)
from stable_baselines3.common.monitor import Monitor
from stable_baselines3.common.torch_layers import BaseFeaturesExtractor
from stable_baselines3.common.vec_env import DummyVecEnv, SubprocVecEnv
from torch import nn

from trading_bot.config import get_logger, ModelType

logger = get_logger(__name__)


FEATURE_EXTRACTOR_REGISTRY: Dict[str, Optional[Type[BaseFeaturesExtractor]]] = {
    "mlp": None,
    "lstm": None,
    "transformer": None,
}


class LSTMFeatureExtractor(BaseFeaturesExtractor):
    """LSTM feature extractor for time series data."""
    
    def __init__(
        self,
        observation_space: gym.Space,
        features_dim: int = 128,
        hidden_size: int = 64,
        num_layers: int = 2,
    ):
        """Initialize LSTM feature extractor.
        
        Args:
            observation_space: Observation space
            features_dim: Output features dimension
            hidden_size: LSTM hidden size
            num_layers: Number of LSTM layers
        """
        super().__init__(observation_space, features_dim)
        
        self.hidden_size = hidden_size
        self.num_layers = num_layers
        
        # Get input dimension from observation space
        if len(observation_space.shape) == 2:
            self.seq_len, self.input_dim = observation_space.shape
        else:
            self.seq_len = 50
            self.input_dim = observation_space.shape[0] // self.seq_len
        
        # LSTM layers
        self.lstm = nn.LSTM(
            input_size=self.input_dim,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.1 if num_layers > 1 else 0,
        )
        
        # Fully connected layer
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, features_dim),
            nn.ReLU(),
        )
    
    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        """Forward pass.
        
        Args:
            observations: Observation tensor
            
        Returns:
            Features tensor
        """
        batch_size = observations.shape[0]
        
        # Reshape to (batch, seq_len, features)
        if len(observations.shape) == 2:
            x = observations.view(batch_size, self.seq_len, -1)
        else:
            x = observations.view(batch_size, self.seq_len, self.input_dim)
        
        # LSTM forward
        lstm_out, _ = self.lstm(x)
        
        # Take last output
        last_output = lstm_out[:, -1, :]
        
        # FC layer
        features = self.fc(last_output)
        
        return features


class TransformerFeatureExtractor(BaseFeaturesExtractor):
    """Transformer feature extractor for time series data."""
    
    def __init__(
        self,
        observation_space: gym.Space,
        features_dim: int = 128,
        d_model: int = 64,
        nhead: int = 4,
        num_layers: int = 2,
    ):
        """Initialize Transformer feature extractor.
        
        Args:
            observation_space: Observation space
            features_dim: Output features dimension
            d_model: Transformer dimension
            nhead: Number of attention heads
            num_layers: Number of transformer layers
        """
        super().__init__(observation_space, features_dim)
        
        self.d_model = d_model
        
        # Get input dimension
        if len(observation_space.shape) == 2:
            self.seq_len, self.input_dim = observation_space.shape
        else:
            self.seq_len = 50
            self.input_dim = observation_space.shape[0] // self.seq_len
        
        # Input projection
        self.input_projection = nn.Linear(self.input_dim, d_model)
        
        # Positional encoding
        self.pos_encoding = nn.Parameter(torch.randn(1, self.seq_len, d_model))
        
        # Transformer encoder
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=0.1,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        
        # Output projection
        self.fc = nn.Sequential(
            nn.Linear(d_model, features_dim),
            nn.ReLU(),
        )
    
    def forward(self, observations: torch.Tensor) -> torch.Tensor:
        """Forward pass."""
        batch_size = observations.shape[0]
        
        # Reshape
        if len(observations.shape) == 2:
            x = observations.view(batch_size, self.seq_len, -1)
        else:
            x = observations.view(batch_size, self.seq_len, self.input_dim)
        
        # Project and add positional encoding
        x = self.input_projection(x) + self.pos_encoding
        
        # Transformer
        x = self.transformer(x)
        
        # Global average pooling
        x = x.mean(dim=1)
        
        # Output projection
        features = self.fc(x)
        
        return features


FEATURE_EXTRACTOR_REGISTRY.update(
    {
        "lstm": LSTMFeatureExtractor,
        "transformer": TransformerFeatureExtractor,
    }
)


class TrainingCallback(BaseCallback):
    """Custom training callback."""
    
    def __init__(self, verbose: int = 0):
        """Initialize callback."""
        super().__init__(verbose)
        self.episode_rewards: List[float] = []
        self.episode_lengths: List[int] = []
    
    def _on_step(self) -> bool:
        """Called at each step."""
        # Log episode info when available
        if len(self.model.ep_info_buffer) > 0:
            info = self.model.ep_info_buffer[-1]
            self.episode_rewards.append(info.get("r", 0))
            self.episode_lengths.append(info.get("l", 0))
            
            if self.verbose > 0 and len(self.episode_rewards) % 10 == 0:
                mean_reward = np.mean(self.episode_rewards[-10:])
                logger.info(
                    f"Episode {len(self.episode_rewards)}: "
                    f"Mean Reward = {mean_reward:.2f}"
                )
        
        return True


class RLAgent:
    """RL Agent wrapper."""
    
    def __init__(
        self,
        model_type: ModelType = ModelType.PPO,
        policy: str = "MlpPolicy",
        learning_rate: float = 3e-4,
        batch_size: int = 64,
        n_steps: int = 2048,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_range: float = 0.2,
        ent_coef: float = 0.01,
        vf_coef: float = 0.5,
        max_grad_norm: float = 0.5,
        use_sde: bool = True,
        sde_sample_freq: int = 64,
        features_extractor_class: Optional[Type[BaseFeaturesExtractor]] = None,
        features_extractor_kwargs: Optional[Dict] = None,
        device: str = "auto",
        verbose: int = 1,
        tensorboard_log: Optional[str] = None,
    ):
        """Initialize RL agent.
        
        Args:
            model_type: PPO or SAC
            policy: Policy network type
            learning_rate: Learning rate
            batch_size: Batch size
            n_steps: Number of steps per update
            gamma: Discount factor
            gae_lambda: GAE lambda
            clip_range: PPO clip range
            ent_coef: Entropy coefficient
            vf_coef: Value function coefficient
            max_grad_norm: Max gradient norm
            use_sde: Use state-dependent exploration
            sde_sample_freq: SDE sample frequency
            features_extractor_class: Custom features extractor
            features_extractor_kwargs: Features extractor kwargs
            device: Device to use
            verbose: Verbosity level
            tensorboard_log: TensorBoard log directory
        """
        self.model_type = model_type
        self.policy = policy
        self.learning_rate = learning_rate
        self.batch_size = batch_size
        self.n_steps = n_steps
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_range = clip_range
        self.ent_coef = ent_coef
        self.vf_coef = vf_coef
        self.max_grad_norm = max_grad_norm
        self.use_sde = use_sde
        self.sde_sample_freq = sde_sample_freq
        self.features_extractor_class = features_extractor_class
        self.features_extractor_kwargs = features_extractor_kwargs or {}
        self.device = device
        self.verbose = verbose
        self.tensorboard_log = tensorboard_log
        
        self.model: Optional[PPO | SAC] = None
        self.env: Optional[gym.Env] = None
    
    def create_model(self, env: gym.Env) -> PPO | SAC:
        """Create the RL model.
        
        Args:
            env: Training environment
            
        Returns:
            RL model instance
        """
        self.env = env
        
        # Policy kwargs
        policy_kwargs = {}
        
        if self.features_extractor_class is not None:
            policy_kwargs["features_extractor_class"] = self.features_extractor_class
            policy_kwargs["features_extractor_kwargs"] = self.features_extractor_kwargs
        
        # Net architecture
        policy_kwargs["net_arch"] = dict(
            pi=[256, 128],  # Policy network
            vf=[256, 128],  # Value network
        )
        
        # Activation function
        policy_kwargs["activation_fn"] = nn.ReLU
        
        # Create model
        if self.model_type == ModelType.PPO:
            self.model = PPO(
                self.policy,
                env,
                learning_rate=self.learning_rate,
                n_steps=self.n_steps,
                batch_size=self.batch_size,
                gamma=self.gamma,
                gae_lambda=self.gae_lambda,
                clip_range=self.clip_range,
                ent_coef=self.ent_coef,
                vf_coef=self.vf_coef,
                max_grad_norm=self.max_grad_norm,
                use_sde=self.use_sde,
                sde_sample_freq=self.sde_sample_freq,
                policy_kwargs=policy_kwargs,
                verbose=self.verbose,
                device=self.device,
                tensorboard_log=self.tensorboard_log,
            )
        elif self.model_type == ModelType.SAC:
            self.model = SAC(
                self.policy,
                env,
                learning_rate=self.learning_rate,
                buffer_size=1000000,
                batch_size=self.batch_size,
                gamma=self.gamma,
                tau=0.005,
                ent_coef="auto",
                target_update_interval=1,
                gradient_steps=1,
                use_sde=self.use_sde,
                sde_sample_freq=self.sde_sample_freq,
                policy_kwargs=policy_kwargs,
                verbose=self.verbose,
                device=self.device,
                tensorboard_log=self.tensorboard_log,
            )
        else:
            raise ValueError(f"Unknown model type: {self.model_type}")
        
        logger.info(
            f"Created {self.model_type.value} model",
            policy=self.policy,
            learning_rate=self.learning_rate,
            batch_size=self.batch_size,
        )
        
        return self.model
    
    def train(
        self,
        total_timesteps: int = 100000,
        callback: Optional[BaseCallback] = None,
        eval_env: Optional[gym.Env] = None,
        eval_freq: int = 10000,
        save_path: Optional[Path] = None,
        save_freq: int = 50000,
    ) -> None:
        """Train the model.
        
        Args:
            total_timesteps: Total training timesteps
            callback: Training callback
            eval_env: Evaluation environment
            eval_freq: Evaluation frequency
            save_path: Model save path
            save_freq: Save frequency
        """
        if self.model is None:
            raise RuntimeError("Model not created. Call create_model() first.")
        
        callbacks = []
        
        # Training callback
        callbacks.append(TrainingCallback(verbose=self.verbose))
        
        # Evaluation callback
        if eval_env is not None:
            eval_callback = EvalCallback(
                eval_env,
                best_model_save_path=str(save_path) if save_path else None,
                log_path=str(save_path) if save_path else None,
                eval_freq=eval_freq,
                deterministic=True,
                render=False,
            )
            callbacks.append(eval_callback)
        
        # Checkpoint callback
        if save_path:
            checkpoint_callback = CheckpointCallback(
                save_freq=save_freq,
                save_path=str(save_path),
                name_prefix="rl_model",
            )
            callbacks.append(checkpoint_callback)
        
        # Custom callback
        if callback:
            callbacks.append(callback)
        
        # Train
        logger.info(f"Starting training for {total_timesteps} timesteps")
        
        self.model.learn(
            total_timesteps=total_timesteps,
            callback=CallbackList(callbacks) if callbacks else None,
        )
        
        logger.info("Training completed")
    
    def predict(
        self,
        observation: np.ndarray,
        deterministic: bool = True,
    ) -> Tuple[np.ndarray, Optional[Dict]]:
        """Predict action.
        
        Args:
            observation: Environment observation
            deterministic: Use deterministic policy
            
        Returns:
            Action and state
        """
        if self.model is None:
            raise RuntimeError("Model not created")
        
        action, state = self.model.predict(observation, deterministic=deterministic)
        return action, state
    
    def save(self, path: Path) -> None:
        """Save model.
        
        Args:
            path: Save path
        """
        if self.model is None:
            raise RuntimeError("Model not created")
        
        path.parent.mkdir(parents=True, exist_ok=True)
        self.model.save(path)
        logger.info(f"Model saved to {path}")
    
    def load(self, path: Path, env: Optional[gym.Env] = None) -> None:
        """Load model.
        
        Args:
            path: Load path
            env: Environment (optional)
        """
        if self.model_type == ModelType.PPO:
            self.model = PPO.load(path, env=env)
        elif self.model_type == ModelType.SAC:
            self.model = SAC.load(path, env=env)
        
        logger.info(f"Model loaded from {path}")
    
    def get_hyperparameters(self) -> Dict:
        """Get hyperparameters dictionary.
        
        Returns:
            Hyperparameters
        """
        return {
            "model_type": self.model_type.value,
            "policy": self.policy,
            "learning_rate": self.learning_rate,
            "batch_size": self.batch_size,
            "n_steps": self.n_steps,
            "gamma": self.gamma,
            "gae_lambda": self.gae_lambda,
            "clip_range": self.clip_range,
            "ent_coef": self.ent_coef,
            "vf_coef": self.vf_coef,
            "max_grad_norm": self.max_grad_norm,
            "use_sde": self.use_sde,
            "sde_sample_freq": self.sde_sample_freq,
        }


def resolve_feature_extractor(
    architecture: str,
) -> Tuple[Optional[Type[BaseFeaturesExtractor]], Dict]:
    """Resolve a named feature extractor preset."""
    normalized = architecture.strip().lower()
    if normalized not in FEATURE_EXTRACTOR_REGISTRY:
        raise ValueError(
            f"Unknown architecture '{architecture}'. Choose from: "
            f"{', '.join(FEATURE_EXTRACTOR_REGISTRY)}"
        )

    extractor_class = FEATURE_EXTRACTOR_REGISTRY[normalized]
    extractor_kwargs: Dict = {}

    if normalized == "lstm":
        extractor_kwargs = {
            "features_dim": 128,
            "hidden_size": 96,
            "num_layers": 2,
        }
    elif normalized == "transformer":
        extractor_kwargs = {
            "features_dim": 128,
            "d_model": 64,
            "nhead": 4,
            "num_layers": 2,
        }

    return extractor_class, extractor_kwargs


def create_vec_env(
    env_fn,
    n_envs: int = 1,
    vec_env_cls = DummyVecEnv,
) -> DummyVecEnv | SubprocVecEnv:
    """Create vectorized environment.
    
    Args:
        env_fn: Function that creates environment
        n_envs: Number of environments
        vec_env_cls: Vectorized environment class
        
    Returns:
        Vectorized environment
    """
    env_fns = [env_fn for _ in range(n_envs)]
    return vec_env_cls(env_fns)
