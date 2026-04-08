"""Alert system for notifications."""

import asyncio
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

import aiohttp

from trading_bot.config import get_logger, get_settings

logger = get_logger(__name__)


class AlertLevel(Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertManager:
    """Alert manager for notifications."""
    
    def __init__(
        self,
        telegram_token: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        discord_webhook: Optional[str] = None,
    ):
        """Initialize alert manager.
        
        Args:
            telegram_token: Telegram bot token
            telegram_chat_id: Telegram chat ID
            discord_webhook: Discord webhook URL
        """
        settings = get_settings()
        
        self.telegram_token = telegram_token or settings.telegram_bot_token
        self.telegram_chat_id = telegram_chat_id or settings.telegram_chat_id
        self.discord_webhook = discord_webhook or settings.discord_webhook_url
        
        self.alert_history: List[Dict] = []
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session
    
    async def send_telegram(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
    ) -> bool:
        """Send Telegram alert.
        
        Args:
            message: Alert message
            level: Alert level
            
        Returns:
            True if sent successfully
        """
        if not self.telegram_token or not self.telegram_chat_id:
            return False
        
        # Add emoji based on level
        emojis = {
            AlertLevel.INFO: "ℹ️",
            AlertLevel.WARNING: "⚠️",
            AlertLevel.ERROR: "❌",
            AlertLevel.CRITICAL: "🚨",
        }
        
        emoji = emojis.get(level, "ℹ️")
        formatted_message = f"{emoji} <b>{level.value.upper()}</b>\n\n{message}"
        
        url = f"https://api.telegram.org/bot{self.telegram_token}/sendMessage"
        
        payload = {
            "chat_id": self.telegram_chat_id,
            "text": formatted_message,
            "parse_mode": "HTML",
        }
        
        try:
            session = await self._get_session()
            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    logger.info("Telegram alert sent")
                    return True
                else:
                    logger.error(f"Failed to send Telegram alert: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Telegram alert error: {e}")
            return False
    
    async def send_discord(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
    ) -> bool:
        """Send Discord alert.
        
        Args:
            message: Alert message
            level: Alert level
            
        Returns:
            True if sent successfully
        """
        if not self.discord_webhook:
            return False
        
        # Color based on level
        colors = {
            AlertLevel.INFO: 3447003,  # Blue
            AlertLevel.WARNING: 16776960,  # Yellow
            AlertLevel.ERROR: 15158332,  # Red
            AlertLevel.CRITICAL: 16711680,  # Dark Red
        }
        
        embed = {
            "title": f"{level.value.upper()} Alert",
            "description": message,
            "color": colors.get(level, 3447003),
            "timestamp": datetime.now().isoformat(),
        }
        
        payload = {"embeds": [embed]}
        
        try:
            session = await self._get_session()
            async with session.post(self.discord_webhook, json=payload) as response:
                if response.status == 204:
                    logger.info("Discord alert sent")
                    return True
                else:
                    logger.error(f"Failed to send Discord alert: {response.status}")
                    return False
        except Exception as e:
            logger.error(f"Discord alert error: {e}")
            return False
    
    async def send_alert(
        self,
        message: str,
        level: AlertLevel = AlertLevel.INFO,
    ) -> None:
        """Send alert to all configured channels.
        
        Args:
            message: Alert message
            level: Alert level
        """
        # Record alert
        alert_record = {
            "timestamp": datetime.now().isoformat(),
            "level": level.value,
            "message": message,
        }
        self.alert_history.append(alert_record)
        
        # Send to all channels
        tasks = [
            self.send_telegram(message, level),
            self.send_discord(message, level),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Log if no channels succeeded
        if not any(r for r in results if isinstance(r, bool) and r):
            logger.warning(f"Alert not sent to any channel: {message}")
    
    async def send_trade_alert(
        self,
        symbol: str,
        side: str,
        price: float,
        size: float,
        pnl: Optional[float] = None,
    ) -> None:
        """Send trade execution alert.
        
        Args:
            symbol: Trading symbol
            side: Trade side
            price: Execution price
            size: Position size
            pnl: Realized PnL (for closes)
        """
        message = f"""
<b>Trade Executed</b>

Symbol: {symbol}
Side: {side.upper()}
Price: {price:.4f}
Size: {size:.6f}
"""
        
        if pnl is not None:
            emoji = "✅" if pnl > 0 else "❌"
            message += f"\nPnL: {emoji} {pnl:+.2f}"
        
        await self.send_alert(message, AlertLevel.INFO)
    
    async def send_daily_report(
        self,
        metrics: Dict,
    ) -> None:
        """Send daily PnL report.
        
        Args:
            metrics: Performance metrics
        """
        message = f"""
<b>Daily Trading Report</b>

📊 Performance
Total Return: {metrics.get('total_return', 0):.2%}
Daily PnL: {metrics.get('daily_pnl', 0):+.2f}
Win Rate: {metrics.get('win_rate', 0):.1%}

📈 Risk Metrics
Max Drawdown: {metrics.get('max_drawdown', 0):.2%}
Volatility: {metrics.get('volatility', 0):.2%}
Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.2f}

📋 Trading Activity
Total Trades: {metrics.get('total_trades', 0)}
Open Positions: {metrics.get('open_positions', 0)}
"""
        
        await self.send_alert(message, AlertLevel.INFO)
    
    async def send_error_alert(
        self,
        error_message: str,
        context: Optional[str] = None,
    ) -> None:
        """Send error alert.
        
        Args:
            error_message: Error message
            context: Additional context
        """
        message = f"<b>Error</b>\n\n{error_message}"
        
        if context:
            message += f"\n\nContext: {context}"
        
        await self.send_alert(message, AlertLevel.ERROR)
    
    async def send_circuit_breaker_alert(
        self,
        reason: str,
        metrics: Dict,
    ) -> None:
        """Send circuit breaker alert.
        
        Args:
            reason: Circuit breaker reason
            metrics: Current metrics
        """
        message = f"""
🚨 <b>CIRCUIT BREAKER TRIGGERED</b> 🚨

Reason: {reason}

Current Metrics:
• Equity: {metrics.get('current_equity', 0):.2f}
• Drawdown: {metrics.get('daily_drawdown', 0):.2%}
• Daily PnL: {metrics.get('daily_pnl', 0):+.2f}

Trading has been paused. Manual intervention required.
"""
        
        await self.send_alert(message, AlertLevel.CRITICAL)
    
    def get_alert_history(
        self,
        level: Optional[AlertLevel] = None,
        limit: int = 100,
    ) -> List[Dict]:
        """Get alert history.
        
        Args:
            level: Filter by level
            limit: Maximum number of alerts
            
        Returns:
            List of alert records
        """
        alerts = self.alert_history
        
        if level:
            alerts = [a for a in alerts if a["level"] == level.value]
        
        return alerts[-limit:]
    
    async def close(self) -> None:
        """Close alert manager."""
        if self._session and not self._session.closed:
            await self._session.close()
