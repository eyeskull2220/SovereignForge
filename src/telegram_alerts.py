#!/usr/bin/env python3
"""
Telegram Alert System for SovereignForge
Handles real-time arbitrage opportunity alerts and system notifications
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
import os

# Telegram imports - with fallbacks for testing
try:
    from telegram import Bot
    from telegram.ext import Application
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None
    Application = None

logger = logging.getLogger(__name__)

@dataclass
class TelegramConfig:
    """Configuration for Telegram alerts"""
    token: str
    chat_ids: List[int]
    enabled: bool = True

@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity data structure"""
    pair: str
    timestamp: float
    probability: float
    confidence: float
    spread_prediction: float
    exchanges: List[str]
    prices: Dict[str, float]
    volumes: Dict[str, float]
    risk_score: float
    profit_potential: float

class TelegramAlertSystem:
    """Telegram alert system for arbitrage opportunities"""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.bot = None
        self.application = None
        self.is_running = False
        self.alerts_sent = 0
        self.opportunities_alerted = 0
        self.errors_count = 0
        self.alert_callbacks: List[Callable] = []

    async def initialize(self) -> None:
        """Initialize the Telegram bot and application"""
        if not self.config.enabled or not self.config.token:
            logger.info("Telegram alerts disabled or no token provided")
            self.config.enabled = False
            return

        if not TELEGRAM_AVAILABLE:
            logger.error("Telegram library not available")
            self.config.enabled = False
            return

        try:
            # Create bot
            self.bot = Bot(token=self.config.token)

            # Verify bot
            bot_info = await self.bot.get_me()
            logger.info(f"Telegram bot initialized: @{bot_info.username}")

            # Create application
            self.application = Application.builder().token(self.config.token).build()

            # Initialize and start
            await self.application.initialize()
            await self.application.start()

            # Start polling
            await self.application.updater.start_polling()

            self.is_running = True
            logger.info("Telegram alert system initialized successfully")

        except Exception as e:
            logger.error(f"Failed to initialize Telegram bot: {e}")
            self.config.enabled = False
            self.is_running = False

    async def shutdown(self) -> None:
        """Shutdown the Telegram system"""
        if self.application and self.is_running:
            try:
                await self.application.updater.stop()
                await self.application.stop()
                await self.application.shutdown()
                logger.info("Telegram alert system shutdown")
            except Exception as e:
                logger.error(f"Error during Telegram shutdown: {e}")

        self.is_running = False

    async def send_opportunity_alert(self, opportunity: ArbitrageOpportunity) -> None:
        """Send arbitrage opportunity alert"""
        if not self.config.enabled or not self.is_running or not self.bot:
            return

        message = self._format_opportunity_message(opportunity)

        for chat_id in self.config.chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    parse_mode='Markdown'
                )
                self.alerts_sent += 1
            except Exception as e:
                logger.error(f"Failed to send alert to {chat_id}: {e}")
                self.errors_count += 1

        self.opportunities_alerted += 1

    async def send_system_alert(self, title: str, message: str, level: str = "info") -> None:
        """Send system alert"""
        if not self.config.enabled or not self.is_running or not self.bot:
            return

        emoji = {"info": "ℹ️", "warning": "⚠️", "error": "❌", "success": "✅"}.get(level, "ℹ️")

        full_message = f"{emoji} *{title.upper()}*\n\n{message}"

        for chat_id in self.config.chat_ids:
            try:
                await self.bot.send_message(
                    chat_id=chat_id,
                    text=full_message,
                    parse_mode='Markdown'
                )
            except Exception as e:
                logger.error(f"Failed to send system alert to {chat_id}: {e}")

    def _format_opportunity_message(self, opportunity: ArbitrageOpportunity) -> str:
        """Format opportunity data into message"""
        exchanges_str = ", ".join(opportunity.exchanges)
        prices_str = "\n".join([f"• {ex}: ${price:.2f}" for ex, price in opportunity.prices.items()])

        message = f"""🚀 *ARBITRAGE OPPORTUNITY DETECTED*

💰 *Pair:* {opportunity.pair}
📊 *Probability:* {opportunity.probability:.1%}
🎯 *Confidence:* {opportunity.confidence:.1%}
📈 *Spread:* {opportunity.spread_prediction:.4f}
💹 *Profit Potential:* {opportunity.profit_potential:.2%}
⚠️ *Risk Score:* {opportunity.risk_score:.2f}

🏦 *Exchanges:* {exchanges_str}

💵 *Prices:*
{prices_str}

⏰ *Time:* {opportunity.timestamp}
"""

        return message

    def add_alert_callback(self, callback: Callable) -> None:
        """Add callback for alert events"""
        self.alert_callbacks.append(callback)

    def get_status(self) -> Dict[str, Any]:
        """Get system status"""
        return {
            'enabled': self.config.enabled,
            'running': self.is_running,
            'alerts_sent': self.alerts_sent,
            'opportunities_alerted': self.opportunities_alerted,
            'errors': self.errors_count,
            'chat_ids': len(self.config.chat_ids)
        }

# Global instance
_telegram_system = None

def get_telegram_alert_system() -> TelegramAlertSystem:
    """Get global Telegram alert system instance"""
    global _telegram_system
    if _telegram_system is None:
        # Create with default config (disabled)
        config = TelegramConfig(
            token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
            chat_ids=[int(cid) for cid in os.getenv('TELEGRAM_CHAT_IDS', '').split(',') if cid.strip()],
            enabled=bool(os.getenv('TELEGRAM_ENABLED', 'false').lower() == 'true')
        )
        _telegram_system = TelegramAlertSystem(config)
    return _telegram_system

async def initialize_telegram_alerts() -> TelegramAlertSystem:
    """Initialize global Telegram alert system"""
    system = get_telegram_alert_system()
    await system.initialize()
    return system

async def shutdown_telegram_alerts() -> None:
    """Shutdown global Telegram alert system"""
    system = get_telegram_alert_system()
    await system.shutdown()

# Convenience functions for easy integration
async def send_opportunity_alert(opportunity: ArbitrageOpportunity) -> None:
    """Send arbitrage opportunity alert (convenience function)"""
    system = get_telegram_alert_system()
    await system.send_opportunity_alert(opportunity)

async def send_system_alert(title: str, message: str, level: str = "info") -> None:
    """Send system alert (convenience function)"""
    system = get_telegram_alert_system()
    await system.send_system_alert(title, message, level)
