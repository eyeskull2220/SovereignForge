#!/usr/bin/env python3
"""
Telegram Alerts System for SovereignForge
Handles notification delivery for trading signals and system alerts
"""

import requests
import logging
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import time
import threading
from queue import Queue

logger = logging.getLogger(__name__)

@dataclass
class TelegramConfig:
    """Telegram bot configuration"""
    bot_token: str
    chat_id: str
    enabled: bool = True
    rate_limit: float = 1.0  # Messages per second

@dataclass
class AlertMessage:
    """Alert message container"""
    message_type: str  # 'signal', 'error', 'info', 'warning'
    title: str
    message: str
    symbol: Optional[str] = None
    timestamp: datetime = None
    metadata: Optional[Dict[str, Any]] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()

class TelegramAlerts:
    """Telegram notification system with rate limiting and queuing"""

    def __init__(self, config: TelegramConfig):
        self.config = config
        self.message_queue: Queue = Queue()
        self.is_running = False
        self.worker_thread: Optional[threading.Thread] = None
        self.last_message_time = 0

        # Message type emojis
        self.emojis = {
            'signal': '🚀',
            'error': '❌',
            'warning': '⚠️',
            'info': 'ℹ️',
            'success': '✅'
        }

        # Start worker thread if enabled
        if self.config.enabled:
            self.start()

    def start(self):
        """Start the alert worker thread"""
        if self.is_running:
            return

        self.is_running = True
        self.worker_thread = threading.Thread(target=self._message_worker, daemon=True)
        self.worker_thread.start()
        logger.info("Telegram alerts worker started")

    def stop(self):
        """Stop the alert worker thread"""
        self.is_running = False
        if self.worker_thread:
            self.worker_thread.join(timeout=5)
        logger.info("Telegram alerts worker stopped")

    def _format_message(self, alert: AlertMessage) -> str:
        """Format alert message for Telegram"""
        emoji = self.emojis.get(alert.message_type, '📢')

        formatted_message = f"{emoji} **{alert.title}**\n\n"
        formatted_message += f"{alert.message}\n\n"

        if alert.symbol:
            formatted_message += f"**Symbol:** {alert.symbol}\n"

        formatted_message += f"**Time:** {alert.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC')}\n"

        if alert.metadata:
            formatted_message += f"**Details:**\n"
            for key, value in alert.metadata.items():
                formatted_message += f"• {key}: {value}\n"

        return formatted_message

    def _send_message(self, message: str) -> bool:
        """Send message to Telegram"""
        if not self.config.enabled or not self.config.bot_token or not self.config.chat_id:
            logger.warning("Telegram alerts not configured or disabled")
            return False

        try:
            # Rate limiting
            current_time = time.time()
            time_since_last = current_time - self.last_message_time
            if time_since_last < self.config.rate_limit:
                time.sleep(self.config.rate_limit - time_since_last)

            url = f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage"
            payload = {
                'chat_id': self.config.chat_id,
                'text': message,
                'parse_mode': 'Markdown',
                'disable_web_page_preview': True
            }

            response = requests.post(url, json=payload, timeout=10)

            if response.status_code == 200:
                self.last_message_time = time.time()
                logger.info("Telegram message sent successfully")
                return True
            else:
                logger.error(f"Telegram API error: {response.status_code} - {response.text}")
                return False

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to send Telegram message: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error sending Telegram message: {e}")
            return False

    def _message_worker(self):
        """Background worker for processing message queue"""
        while self.is_running:
            try:
                # Get message from queue with timeout
                alert = self.message_queue.get(timeout=1)

                # Format and send message
                formatted_message = self._format_message(alert)
                success = self._send_message(formatted_message)

                if not success:
                    logger.warning(f"Failed to send alert: {alert.title}")

                # Mark task as done
                self.message_queue.task_done()

            except Exception as e:
                # Continue processing even if one message fails
                logger.error(f"Message worker error: {e}")
                continue

    def send_alert(self, alert: AlertMessage) -> bool:
        """Send an alert message"""
        if not self.config.enabled:
            logger.debug("Telegram alerts disabled, skipping message")
            return True

        try:
            self.message_queue.put(alert)
            logger.debug(f"Alert queued: {alert.title}")
            return True
        except Exception as e:
            logger.error(f"Failed to queue alert: {e}")
            return False

    def send_signal_alert(self, symbol: str, signal_type: str, confidence: float,
                         entry_price: float, stop_loss: float, take_profit: float,
                         metadata: Optional[Dict[str, Any]] = None):
        """Send arbitrage signal alert"""
        title = f"Arbitrage Signal - {signal_type.upper()}"
        message = f"New arbitrage opportunity detected for {symbol}"

        alert_metadata = {
            'confidence': f"{confidence:.1%}",
            'entry_price': f"${entry_price:.4f}",
            'stop_loss': f"${stop_loss:.4f}",
            'take_profit': f"${take_profit:.4f}",
            'potential_profit': f"${take_profit - entry_price:.4f}",
            'risk_reward_ratio': f"{(take_profit - entry_price) / (entry_price - stop_loss):.2f}"
        }

        if metadata:
            alert_metadata.update(metadata)

        alert = AlertMessage(
            message_type='signal',
            title=title,
            message=message,
            symbol=symbol,
            metadata=alert_metadata
        )

        return self.send_alert(alert)

    def send_error_alert(self, error_message: str, component: str,
                        metadata: Optional[Dict[str, Any]] = None):
        """Send error alert"""
        title = f"System Error - {component}"
        message = f"Critical error in {component}: {error_message}"

        alert = AlertMessage(
            message_type='error',
            title=title,
            message=message,
            metadata=metadata
        )

        return self.send_alert(alert)

    def send_warning_alert(self, warning_message: str, component: str,
                          metadata: Optional[Dict[str, Any]] = None):
        """Send warning alert"""
        title = f"System Warning - {component}"
        message = f"Warning from {component}: {warning_message}"

        alert = AlertMessage(
            message_type='warning',
            title=title,
            message=message,
            metadata=metadata
        )

        return self.send_alert(alert)

    def send_info_alert(self, info_message: str, component: str,
                       metadata: Optional[Dict[str, Any]] = None):
        """Send info alert"""
        title = f"System Info - {component}"
        message = f"Information from {component}: {info_message}"

        alert = AlertMessage(
            message_type='info',
            title=title,
            message=message,
            metadata=metadata
        )

        return self.send_alert(alert)

    def send_success_alert(self, success_message: str, component: str,
                          metadata: Optional[Dict[str, Any]] = None):
        """Send success alert"""
        title = f"Success - {component}"
        message = f"Operation completed successfully in {component}: {success_message}"

        alert = AlertMessage(
            message_type='success',
            title=title,
            message=message,
            metadata=metadata
        )

        return self.send_alert(alert)

    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return {
            'enabled': self.config.enabled,
            'queue_size': self.message_queue.qsize(),
            'is_running': self.is_running,
            'rate_limit': self.config.rate_limit,
            'last_message_time': self.last_message_time
        }

    def test_connection(self) -> bool:
        """Test Telegram bot connection"""
        if not self.config.enabled:
            return False

        test_message = "🧪 SovereignForge Telegram Test Message\n\nConnection test successful!"
        return self._send_message(test_message)

# Global alerts instance
_telegram_alerts = None

def get_telegram_alerts(config: Optional[TelegramConfig] = None) -> TelegramAlerts:
    """Get or create Telegram alerts instance"""
    global _telegram_alerts

    if _telegram_alerts is None:
        if config is None:
            # Try to load from environment or config file
            config = TelegramConfig(
                bot_token="YOUR_BOT_TOKEN",  # Should be loaded from secure config
                chat_id="YOUR_CHAT_ID",      # Should be loaded from secure config
                enabled=False  # Disabled by default for security
            )
        _telegram_alerts = TelegramAlerts(config)

    return _telegram_alerts

def init_telegram_alerts(bot_token: str, chat_id: str, enabled: bool = True) -> TelegramAlerts:
    """Initialize Telegram alerts with configuration"""
    config = TelegramConfig(
        bot_token=bot_token,
        chat_id=chat_id,
        enabled=enabled
    )
    global _telegram_alerts
    _telegram_alerts = TelegramAlerts(config)
    return _telegram_alerts