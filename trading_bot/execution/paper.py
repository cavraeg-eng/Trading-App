"""Paper trading executor for backtesting, simulation, and application paper orders."""

import asyncio
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

from trading_bot.config import get_logger
from trading_bot.persistence import paper_trading as repo
from trading_bot.persistence.db import PersistenceError
from trading_bot.risk.manager import Position, RiskManager
from trading_bot.strategy.base import Signal, SignalType

logger = get_logger(__name__)


@dataclass(frozen=True)
class PaperOrderCommand:
    """Application-level paper order request."""

    symbol: str
    side: str
    quantity: float
    order_type: str = "market"
    price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    take_profit_3: Optional[float] = None
    risk_percent: Optional[float] = None
    trade_style: Optional[str] = None
    confidence: Optional[float] = None
    strategy_id: Optional[str] = None


class PaperOrderValidationError(ValueError):
    """Paper order input is invalid."""


class PaperExecutionPersistenceError(RuntimeError):
    """Paper execution state could not be persisted."""


def _initial_paper_account() -> dict[str, Any]:
    return {
        "balance": 10000.0,
        "equity": 10000.0,
        "positions": [],
        "trades_history": [],
        "initial_balance": 10000.0,
    }


_paper_account = _initial_paper_account()
_account_lock = asyncio.Lock()


class PaperExecutionService:
    """Own paper account state, validation, persistence, restore, and reset behavior."""

    def __init__(
        self,
        *,
        repository: Any = repo,
        account_state: Optional[dict[str, Any]] = None,
        account_lock: Optional[asyncio.Lock] = None,
    ) -> None:
        self._repo = repository
        self._account = account_state if account_state is not None else _paper_account
        self._lock = account_lock if account_lock is not None else _account_lock

    def restore_state(self) -> None:
        persisted = self._repo.get_paper_account()
        positions = self._repo.get_paper_positions()
        history = self._repo.get_paper_history()
        self._account["balance"] = persisted["balance"]
        self._account["equity"] = persisted["equity"]
        self._account["initial_balance"] = persisted["initial_balance"]
        self._account["positions"] = positions
        self._account["trades_history"] = history

    async def place_order(self, order: PaperOrderCommand) -> dict[str, Any]:
        """Validate, execute, persist, and return a route-compatible paper order response."""
        async with self._lock:
            entry_price = self._validate_order(order)

            trade_id = str(uuid.uuid4())[:8]
            quantity = round(order.quantity, 2)
            opened_at = datetime.utcnow().isoformat()
            trade = {
                "trade_id": trade_id,
                "symbol": order.symbol,
                "side": order.side,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_loss": order.stop_loss,
                "take_profit_1": order.take_profit_1,
                "take_profit_2": order.take_profit_2,
                "take_profit_3": order.take_profit_3,
                "status": "filled",
                "opened_at": opened_at,
                "risk_percent": order.risk_percent,
                "trade_style": order.trade_style,
                "confidence": order.confidence,
                "strategy_id": order.strategy_id,
                "pnl": 0.0,
            }

            self._account["positions"].append(trade)
            self._account["trades_history"].append(trade)
            try:
                self._repo.insert_paper_order(
                    {
                        "trade_id": trade_id,
                        "symbol": order.symbol,
                        "side": order.side,
                        "quantity": quantity,
                        "entry_price": entry_price,
                        "stop_loss": order.stop_loss,
                        "take_profit_1": order.take_profit_1,
                        "take_profit_2": order.take_profit_2,
                        "take_profit_3": order.take_profit_3,
                        "status": "filled",
                        "pnl": 0.0,
                        "risk_percent": order.risk_percent,
                        "trade_style": order.trade_style,
                        "strategy_id": order.strategy_id,
                        "confidence": order.confidence,
                        "opened_at": str(time.time()),
                    }
                )
            except PersistenceError as exc:
                self._account["positions"].remove(trade)
                self._account["trades_history"].remove(trade)
                raise PaperExecutionPersistenceError(str(exc)) from exc

            return {
                "success": True,
                "order_id": trade_id,
                "status": "filled",
                "symbol": order.symbol,
                "side": order.side,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_loss": order.stop_loss,
                "take_profit_levels": [
                    order.take_profit_1,
                    order.take_profit_2,
                    order.take_profit_3,
                ],
                "message": (
                    f"Paper {order.side.upper()} order filled: "
                    f"{quantity} {order.symbol} at {entry_price}"
                ),
                "timestamp": datetime.utcnow().isoformat(),
            }

    def get_positions(self) -> list[dict[str, Any]]:
        try:
            positions = self._repo.get_paper_positions()
            if positions:
                return positions
        except PersistenceError as exc:
            raise PaperExecutionPersistenceError(str(exc)) from exc
        return self._account["positions"]

    def get_account_summary(self) -> dict[str, Any]:
        try:
            persisted = self._repo.get_paper_account()
            total_positions = len(self._repo.get_paper_positions())
        except PersistenceError:
            persisted = None
            total_positions = len(self._account["positions"])

        account = persisted or self._account
        return {
            "balance": round(account["balance"], 2),
            "equity": round(account["equity"], 2),
            "initial_balance": account["initial_balance"],
            "total_positions": total_positions,
            "total_trades": len(self._account["trades_history"]),
        }

    def reset(self) -> None:
        try:
            self._repo.reset_paper_account()
        except PersistenceError as exc:
            raise PaperExecutionPersistenceError(str(exc)) from exc
        self._account["balance"] = 10000.0
        self._account["equity"] = 10000.0
        self._account["positions"] = []
        self._account["trades_history"] = []

    def _validate_order(self, order: PaperOrderCommand) -> float:
        if order.side not in ("buy", "sell"):
            raise PaperOrderValidationError("Side must be 'buy' or 'sell'")
        if order.quantity <= 0:
            raise PaperOrderValidationError("Quantity must be positive")
        if not order.price or order.price <= 0:
            raise PaperOrderValidationError("Market orders must include a valid current price")
        if self._account["balance"] <= 0:
            raise PaperOrderValidationError("Insufficient paper balance")
        return order.price


paper_execution_service = PaperExecutionService()


def restore_paper_trading_state() -> None:
    paper_execution_service.restore_state()


async def place_paper_order(order: PaperOrderCommand) -> dict[str, Any]:
    return await paper_execution_service.place_order(order)


def get_paper_positions() -> list[dict[str, Any]]:
    return paper_execution_service.get_positions()


def get_paper_account_summary() -> dict[str, Any]:
    return paper_execution_service.get_account_summary()


def reset_paper_account() -> None:
    paper_execution_service.reset()


@dataclass
class PaperTrade:
    """Paper trade record."""
    trade_id: str
    symbol: str
    side: str
    entry_price: float
    exit_price: Optional[float] = None
    quantity: float = 0.0
    entry_time: datetime = field(default_factory=datetime.now)
    exit_time: Optional[datetime] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    commission: float = 0.0
    slippage: float = 0.0
    status: str = "open"
    metadata: Dict = field(default_factory=dict)


class PaperTradingExecutor:
    """Paper trading executor with realistic simulation."""
    
    def __init__(
        self,
        initial_capital: float = 10000.0,
        commission_rate: float = 0.001,
        slippage_model: str = "fixed",
        slippage_pct: float = 0.0005,
        enable_slippage: bool = True,
    ):
        """Initialize paper trading executor.
        
        Args:
            initial_capital: Starting capital
            commission_rate: Commission rate (0.001 = 0.1%)
            slippage_model: Slippage model ('fixed' or 'variable')
            slippage_pct: Slippage percentage
            enable_slippage: Whether to apply slippage
        """
        self.initial_capital = initial_capital
        self.commission_rate = commission_rate
        self.slippage_model = slippage_model
        self.slippage_pct = slippage_pct
        self.enable_slippage = enable_slippage
        
        self.capital = initial_capital
        self.equity = initial_capital
        self.peak_equity = initial_capital
        self.trades: List[PaperTrade] = []
        self.positions: Dict[str, PaperTrade] = {}
        self.equity_curve: List[float] = [initial_capital]
        self.trade_history: List[Dict] = []
        
        self.risk_manager = RiskManager(
            initial_capital=initial_capital,
            max_position_size=0.3,
            max_total_exposure=0.8,
        )
    
    def _apply_slippage(self, price: float, side: str, volatility: float = 0.0) -> float:
        """Apply slippage to price.
        
        Args:
            price: Original price
            side: Trade side ('buy' or 'sell')
            volatility: Current volatility for variable slippage
            
        Returns:
            Slipped price
        """
        if not self.enable_slippage:
            return price
        
        if self.slippage_model == "fixed":
            slippage = self.slippage_pct
        elif self.slippage_model == "variable":
            # Variable slippage based on volatility
            slippage = self.slippage_pct * (1 + volatility * 10)
        else:
            slippage = 0
        
        # Apply slippage against the trader
        if side == "buy":
            return price * (1 + slippage)
        else:
            return price * (1 - slippage)
    
    def _calculate_commission(self, notional: float) -> float:
        """Calculate commission.
        
        Args:
            notional: Trade notional value
            
        Returns:
            Commission amount
        """
        return notional * self.commission_rate
    
    def execute_signal(
        self,
        signal: Signal,
        current_price: float,
        volatility: float = 0.0,
    ) -> Optional[PaperTrade]:
        """Execute trading signal.
        
        Args:
            signal: Trading signal
            current_price: Current market price
            volatility: Current volatility
            
        Returns:
            Trade record or None
        """
        symbol = signal.symbol
        
        # Handle close signal
        if signal.signal_type == SignalType.CLOSE:
            return self.close_position(symbol, current_price, volatility)
        
        # Determine side
        side = "buy" if signal.signal_type == SignalType.BUY else "sell"
        
        # Check if we already have a position
        if symbol in self.positions:
            existing = self.positions[symbol]
            if (side == "buy" and existing.side == "long") or \
               (side == "sell" and existing.side == "short"):
                logger.debug(f"Already have {existing.side} position in {symbol}")
                return None
            else:
                # Reverse position
                self.close_position(symbol, current_price, volatility)
        
        # Calculate position size
        stop_loss = current_price * 0.95 if side == "buy" else current_price * 1.05
        position_size = self.risk_manager.get_position_size(
            symbol, current_price, stop_loss
        )
        
        # Apply slippage
        executed_price = self._apply_slippage(current_price, side, volatility)
        
        # Calculate commission
        notional = position_size.size * executed_price
        commission = self._calculate_commission(notional)
        
        # Check if we have enough capital
        if notional + commission > self.capital:
            logger.warning(f"Insufficient capital for trade: {symbol}")
            return None
        
        # Create trade
        trade = PaperTrade(
            trade_id=f"{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            symbol=symbol,
            side="long" if side == "buy" else "short",
            entry_price=executed_price,
            quantity=position_size.size,
            commission=commission,
            slippage=abs(executed_price - current_price) * position_size.size,
            metadata={
                "signal_confidence": signal.confidence,
                "stop_loss": stop_loss,
            },
        )
        
        # Update capital
        self.capital -= commission
        
        # Track position
        self.positions[symbol] = trade
        
        # Open position in risk manager
        self.risk_manager.open_position(
            symbol=symbol,
            side="long" if side == "buy" else "short",
            size=position_size.size,
            entry_price=executed_price,
            stop_loss=stop_loss,
        )
        
        logger.info(
            "Paper trade executed",
            symbol=symbol,
            side=side,
            price=executed_price,
            size=position_size.size,
            commission=commission,
        )
        
        return trade
    
    def close_position(
        self,
        symbol: str,
        current_price: float,
        volatility: float = 0.0,
    ) -> Optional[PaperTrade]:
        """Close existing position.
        
        Args:
            symbol: Trading symbol
            current_price: Current market price
            volatility: Current volatility
            
        Returns:
            Closed trade record or None
        """
        if symbol not in self.positions:
            return None
        
        trade = self.positions[symbol]
        
        # Determine close side
        close_side = "sell" if trade.side == "long" else "buy"
        
        # Apply slippage
        executed_price = self._apply_slippage(current_price, close_side, volatility)
        
        # Calculate commission
        notional = trade.quantity * executed_price
        commission = self._calculate_commission(notional)
        
        # Calculate PnL
        if trade.side == "long":
            pnl = (executed_price - trade.entry_price) * trade.quantity - commission
        else:
            pnl = (trade.entry_price - executed_price) * trade.quantity - commission
        
        pnl_pct = pnl / (trade.entry_price * trade.quantity) if trade.entry_price > 0 else 0
        
        # Update trade
        trade.exit_price = executed_price
        trade.exit_time = datetime.now()
        trade.pnl = pnl
        trade.pnl_pct = pnl_pct
        trade.commission += commission
        trade.status = "closed"
        
        # Update capital and equity
        self.capital += trade.quantity * executed_price - commission
        self.equity += pnl
        
        # Update peak equity
        if self.equity > self.peak_equity:
            self.peak_equity = self.equity
        
        # Record trade
        self.trades.append(trade)
        self.equity_curve.append(self.equity)
        
        # Remove position
        del self.positions[symbol]
        
        # Close in risk manager
        self.risk_manager.close_position(symbol, executed_price)
        
        logger.info(
            "Paper position closed",
            symbol=symbol,
            entry=trade.entry_price,
            exit=executed_price,
            pnl=pnl,
            pnl_pct=pnl_pct,
        )
        
        return trade
    
    def update_positions(self, prices: Dict[str, float], volatility: float = 0.0) -> None:
        """Update all positions with current prices.
        
        Args:
            prices: Dictionary of symbol -> price
            volatility: Current volatility
        """
        for symbol, trade in list(self.positions.items()):
            if symbol in prices:
                current_price = prices[symbol]
                
                # Update unrealized PnL
                if trade.side == "long":
                    unrealized = (current_price - trade.entry_price) * trade.quantity
                else:
                    unrealized = (trade.entry_price - current_price) * trade.quantity
                
                # Check stop loss
                stop_loss = trade.metadata.get("stop_loss")
                if stop_loss:
                    if trade.side == "long" and current_price <= stop_loss:
                        logger.info(f"Stop loss triggered for {symbol}")
                        self.close_position(symbol, current_price, volatility)
                    elif trade.side == "short" and current_price >= stop_loss:
                        logger.info(f"Stop loss triggered for {symbol}")
                        self.close_position(symbol, current_price, volatility)
    
    def get_performance_metrics(self) -> Dict:
        """Calculate performance metrics.
        
        Returns:
            Metrics dictionary
        """
        if not self.trades:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
            }
        
        closed_trades = [t for t in self.trades if t.status == "closed"]
        
        if not closed_trades:
            return {
                "total_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
            }
        
        # Returns
        total_return = (self.equity - self.initial_capital) / self.initial_capital
        
        # Win rate
        wins = [t for t in closed_trades if t.pnl > 0]
        win_rate = len(wins) / len(closed_trades)
        
        # Profit factor
        gross_profit = sum(t.pnl for t in wins)
        gross_loss = abs(sum(t.pnl for t in closed_trades if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Sharpe ratio (simplified)
        if len(self.equity_curve) > 1:
            returns = np.diff(self.equity_curve) / self.equity_curve[:-1]
            if len(returns) > 1 and np.std(returns) > 0:
                sharpe = np.mean(returns) / np.std(returns) * np.sqrt(252)
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0
        
        # Max drawdown
        equity_array = np.array(self.equity_curve)
        peak = np.maximum.accumulate(equity_array)
        drawdown = (peak - equity_array) / peak
        max_drawdown = np.max(drawdown)
        
        return {
            "total_return": total_return,
            "total_trades": len(closed_trades),
            "winning_trades": len(wins),
            "losing_trades": len(closed_trades) - len(wins),
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "sharpe_ratio": sharpe,
            "max_drawdown": max_drawdown,
            "final_equity": self.equity,
            "avg_trade_pnl": np.mean([t.pnl for t in closed_trades]),
            "avg_win": np.mean([t.pnl for t in wins]) if wins else 0,
            "avg_loss": np.mean([t.pnl for t in closed_trades if t.pnl < 0]) if len(closed_trades) > len(wins) else 0,
        }
    
    def reset(self) -> None:
        """Reset executor state."""
        self.capital = self.initial_capital
        self.equity = self.initial_capital
        self.peak_equity = self.initial_capital
        self.trades = []
        self.positions = {}
        self.equity_curve = [self.initial_capital]
        self.risk_manager = RiskManager(initial_capital=self.initial_capital)
        logger.info("Paper trading executor reset")
