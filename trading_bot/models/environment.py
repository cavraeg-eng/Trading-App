"""Gymnasium trading environment for RL."""

from typing import Dict, List, Optional, Tuple

import gymnasium as gym
import numpy as np
import pandas as pd
from gymnasium import spaces

from trading_bot.config import get_logger

logger = get_logger(__name__)


class TradingEnvironment(gym.Env):
    """Custom trading environment for reinforcement learning."""
    
    metadata = {"render_modes": ["human", "rgb_array"], "render_fps": 30}

    min_action_threshold = 0.01
    
    def __init__(
        self,
        df: pd.DataFrame,
        initial_balance: float = 10000.0,
        commission: float = 0.001,
        slippage: float = 0.0005,
        window_size: int = 50,
        reward_scaling: float = 1.0,
        max_position_size: float = 1.0,
        stop_loss_pct: float = 0.05,
        take_profit_pct: float = 0.10,
        feature_columns: Optional[List[str]] = None,
    ):
        """Initialize trading environment.
        
        Args:
            df: DataFrame with OHLCV and features
            initial_balance: Starting capital
            commission: Trading commission (0.001 = 0.1%)
            slippage: Price slippage (0.0005 = 0.05%)
            window_size: Observation window size
            reward_scaling: Reward scaling factor
            max_position_size: Maximum position size (1.0 = 100%)
            stop_loss_pct: Stop loss percentage
            take_profit_pct: Take profit percentage
            feature_columns: List of feature column names
        """
        super().__init__()
        
        self.df = df.reset_index(drop=True)
        self.initial_balance = initial_balance
        self.commission = commission
        self.slippage = slippage
        self.window_size = window_size
        self.reward_scaling = reward_scaling
        self.max_position_size = max_position_size
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        
        # Feature columns
        if feature_columns is None:
            # Exclude OHLCV and non-numeric columns
            exclude = ["open", "high", "low", "close", "volume", "timestamp"]
            self.feature_columns = [
                c for c in df.select_dtypes(include=[np.number]).columns
                if c not in exclude
            ]
        else:
            self.feature_columns = feature_columns
        
        self.n_features = len(self.feature_columns)
        
        # Action space: [position_size, stop_loss, take_profit]
        # position_size: -1 (short) to 1 (long)
        self.action_space = spaces.Box(
            low=np.array([-1.0, 0.0, 0.0]),
            high=np.array([1.0, 0.1, 0.2]),
            dtype=np.float32,
        )
        
        # Observation space: window of features + account info
        obs_shape = (window_size, self.n_features + 3)  # +3 for balance, position, unrealized_pnl
        self.observation_space = spaces.Box(
            low=-np.inf,
            high=np.inf,
            shape=obs_shape,
            dtype=np.float32,
        )
        
        # State variables
        self.current_step = 0
        self.balance = initial_balance
        self.position = 0.0  # -1 to 1
        self.entry_price = 0.0
        self.position_notional = 0.0
        self.trades: List[Dict] = []
        self.equity_curve: List[float] = []
        self.peak_equity = initial_balance
        
        logger.info(
            "Trading environment initialized",
            features=self.n_features,
            window_size=window_size,
            data_points=len(df),
        )
    
    def reset(
        self,
        seed: Optional[int] = None,
        options: Optional[Dict] = None,
    ) -> Tuple[np.ndarray, Dict]:
        """Reset environment to initial state.
        
        Args:
            seed: Random seed
            options: Additional options
            
        Returns:
            Initial observation and info
        """
        super().reset(seed=seed)
        
        self.current_step = self.window_size
        self.balance = self.initial_balance
        self.position = 0.0
        self.entry_price = 0.0
        self.position_notional = 0.0
        self.trades = []
        self.equity_curve = [self.initial_balance]
        self.peak_equity = self.initial_balance
        
        observation = self._get_observation()
        info = self._get_info()
        
        return observation, info
    
    def step(self, action: np.ndarray) -> Tuple[np.ndarray, float, bool, bool, Dict]:
        """Execute one timestep.
        
        Args:
            action: [position_size, stop_loss, take_profit]
            
        Returns:
            observation, reward, terminated, truncated, info
        """
        position_size, stop_loss, take_profit = action
        position_size = float(np.clip(position_size, -self.max_position_size, self.max_position_size))
        stop_loss = float(np.clip(stop_loss, 0.0, self.stop_loss_pct))
        take_profit = float(np.clip(take_profit, 0.0, self.take_profit_pct))
        effective_stop_loss = stop_loss if stop_loss > self.min_action_threshold else self.stop_loss_pct
        effective_take_profit = (
            take_profit if take_profit > self.min_action_threshold else self.take_profit_pct
        )
        
        # Get current price
        current_price = self.df.iloc[self.current_step]["close"]
        realized_pnl = 0.0
        
        # Apply slippage
        if position_size > self.position:  # Buying
            executed_price = current_price * (1 + self.slippage)
        elif position_size < self.position:  # Selling
            executed_price = current_price * (1 - self.slippage)
        else:
            executed_price = current_price
        
        # Calculate position change
        position_change = position_size - self.position
        
        # Execute trade if position changes
        if abs(position_change) > self.min_action_threshold:
            previous_position = self.position
            previous_notional = self.position_notional
            closing_fraction = 0.0

            if abs(previous_position) > self.min_action_threshold and np.sign(previous_position) != np.sign(position_size):
                closing_fraction = 1.0
            elif abs(previous_position) > self.min_action_threshold:
                closing_fraction = min(abs(position_change), abs(previous_position)) / max(abs(previous_position), 1e-8)

            if closing_fraction > 0:
                price_change = (executed_price - self.entry_price) / max(self.entry_price, 1e-8)
                realized_trade_pnl = (
                    previous_notional * previous_position * price_change * closing_fraction
                )
                realized_pnl += realized_trade_pnl
                self.balance += realized_trade_pnl
                self.position_notional = max(previous_notional * (1 - closing_fraction), 0.0)

            trade_value = abs(position_change) * max(self.balance, 0.0)
            commission_cost = trade_value * self.commission
            
            # Update balance
            self.balance -= commission_cost
            
            # Record trade
            self.trades.append({
                "step": self.current_step,
                "price": executed_price,
                "position_change": position_change,
                "commission": commission_cost,
                "realized_pnl": realized_pnl,
                "balance": self.balance,
            })
            
            # Update entry price for new position
            if abs(position_size) <= self.min_action_threshold:
                self.entry_price = 0.0
                self.position_notional = 0.0
            elif abs(previous_position) <= self.min_action_threshold or np.sign(previous_position) != np.sign(position_size):
                self.entry_price = executed_price
                self.position_notional = abs(position_size) * self.balance
            else:
                added_notional = max(abs(position_change), 0.0) * self.balance
                total_notional = self.position_notional + added_notional
                if total_notional > 0:
                    self.entry_price = (
                        (self.position_notional * self.entry_price + added_notional * executed_price)
                        / total_notional
                    )
                    self.position_notional = total_notional

            self.position = position_size
        
        # Check stop loss / take profit
        if self.position != 0 and self.entry_price > 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            
            if self.position > 0:  # Long
                if (
                    price_change <= -effective_stop_loss
                    or price_change >= effective_take_profit
                ):
                    close_pnl = self.position_notional * self.position * price_change
                    realized_pnl += close_pnl
                    self.balance += close_pnl
                    self.position = 0.0
                    self.entry_price = 0.0
                    self.position_notional = 0.0
            else:  # Short
                if (
                    price_change >= effective_stop_loss
                    or price_change <= -effective_take_profit
                ):
                    close_pnl = self.position_notional * self.position * price_change
                    realized_pnl += close_pnl
                    self.balance += close_pnl
                    self.position = 0.0
                    self.entry_price = 0.0
                    self.position_notional = 0.0
        
        # Calculate unrealized PnL
        unrealized_pnl = 0.0
        if self.position != 0 and self.entry_price > 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            unrealized_pnl = self.position * price_change * self.position_notional
        
        # Calculate total equity
        equity = self.balance + unrealized_pnl
        self.equity_curve.append(equity)
        
        # Update peak equity
        if equity > self.peak_equity:
            self.peak_equity = equity
        
        # Calculate reward
        reward = self._calculate_reward(equity, unrealized_pnl, realized_pnl, position_change)
        
        # Move to next step
        self.current_step += 1
        
        # Check termination
        terminated = False
        truncated = False
        
        # End of data
        if self.current_step >= len(self.df) - 1:
            truncated = True
        
        # Bankruptcy check
        if equity < self.initial_balance * 0.1:  # Lost 90%
            terminated = True
            reward -= 10  # Penalty for bankruptcy
        
        # Max drawdown check
        drawdown = (self.peak_equity - equity) / self.peak_equity
        if drawdown > 0.5:  # 50% max drawdown
            terminated = True
            reward -= 10
        
        observation = self._get_observation()
        info = self._get_info()
        info["equity"] = equity
        info["unrealized_pnl"] = unrealized_pnl
        info["realized_pnl"] = realized_pnl
        info["drawdown"] = drawdown
        
        return observation, reward, terminated, truncated, info
    
    def _get_observation(self) -> np.ndarray:
        """Get current observation.
        
        Returns:
            Observation array
        """
        # Get feature window
        start_idx = max(0, self.current_step - self.window_size)
        end_idx = self.current_step
        
        features = self.df.iloc[start_idx:end_idx][self.feature_columns].values
        
        # Pad if necessary
        if len(features) < self.window_size:
            padding = np.zeros((self.window_size - len(features), self.n_features))
            features = np.vstack([padding, features])
        
        # Add account info
        current_price = self.df.iloc[self.current_step]["close"]
        
        unrealized_pnl = 0.0
        if self.position != 0 and self.entry_price > 0:
            price_change = (current_price - self.entry_price) / self.entry_price
            unrealized_pnl = self.position * price_change * (
                self.position_notional / max(self.initial_balance, 1e-8)
            )
        
        account_info = np.array([
            [self.balance / self.initial_balance,  # Normalized balance
             self.position,  # Current position
             unrealized_pnl]  # Unrealized PnL
        ])
        
        # Broadcast account info to match window size
        account_info = np.repeat(account_info, self.window_size, axis=0)
        
        # Combine features and account info
        observation = np.hstack([features, account_info])
        
        return observation.astype(np.float32)
    
    def _get_info(self) -> Dict:
        """Get additional info.
        
        Returns:
            Info dictionary
        """
        return {
            "step": self.current_step,
            "balance": self.balance,
            "position": self.position,
            "entry_price": self.entry_price,
            "position_notional": self.position_notional,
            "num_trades": len(self.trades),
            "equity": self.balance,
        }
    
    def _calculate_reward(
        self,
        equity: float,
        unrealized_pnl: float,
        realized_pnl: float,
        position_change: float,
    ) -> float:
        """Calculate reward.
        
        Args:
            equity: Current equity
            unrealized_pnl: Unrealized PnL
            
        Returns:
            Reward value
        """
        # Base reward: change in equity
        if len(self.equity_curve) > 1:
            equity_change = (equity - self.equity_curve[-2]) / self.initial_balance
        else:
            equity_change = 0.0
        
        # Risk-adjusted reward (Sharpe-like)
        if len(self.equity_curve) > 10:
            returns = np.diff(self.equity_curve[-10:]) / self.initial_balance
            if len(returns) > 1 and np.std(returns) > 0:
                sharpe_like = np.mean(returns) / (np.std(returns) + 1e-8)
            else:
                sharpe_like = 0.0
        else:
            sharpe_like = 0.0
        
        # Penalize drawdown
        drawdown = (self.peak_equity - equity) / self.peak_equity
        drawdown_penalty = -drawdown ** 2
        
        realized_return = realized_pnl / self.initial_balance
        unrealized_return = unrealized_pnl / self.initial_balance
        trading_penalty = -0.0005 * abs(position_change)
        holding_penalty = -0.0001 * abs(self.position)
        alignment_bonus = np.sign(unrealized_return) * min(abs(unrealized_return), 0.01)
        
        # Combine rewards
        reward = (
            equity_change * 8
            + realized_return * 12
            + unrealized_return * 2
            + sharpe_like * 0.2
            + drawdown_penalty * 5
            + trading_penalty
            + holding_penalty
            + alignment_bonus
        )
        
        return reward * self.reward_scaling
    
    def render(self, mode: str = "human") -> Optional[np.ndarray]:
        """Render environment.
        
        Args:
            mode: Render mode
            
        Returns:
            Rendered frame or None
        """
        if mode == "human":
            print(f"Step: {self.current_step}, Balance: {self.balance:.2f}, "
                  f"Position: {self.position:.2f}, Equity: {self.equity_curve[-1]:.2f}")
        
        return None
    
    def get_performance_metrics(self) -> Dict:
        """Calculate performance metrics.
        
        Returns:
            Performance metrics dictionary
        """
        if len(self.equity_curve) < 2:
            return {}
        
        equity_array = np.array(self.equity_curve)
        returns = np.diff(equity_array) / equity_array[:-1]
        
        # Total return
        total_return = (equity_array[-1] - self.initial_balance) / self.initial_balance
        
        # Sharpe ratio (annualized)
        if len(returns) > 1 and np.std(returns) > 0:
            sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
        else:
            sharpe = 0.0
        
        # Max drawdown
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        max_drawdown = np.max(drawdown)
        
        # Win rate (if trades exist)
        if self.trades:
            profitable_trades = sum(
                1
                for t in self.trades
                if t.get("realized_pnl", t.get("pnl", 0)) > 0
            )
            win_rate = profitable_trades / len(self.trades)
        else:
            win_rate = 0.0
        
        return {
            "total_return": total_return,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "win_rate": win_rate,
            "num_trades": len(self.trades),
            "final_equity": equity_array[-1],
        }
