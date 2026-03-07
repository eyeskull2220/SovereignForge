#!/usr/bin/env python3
"""
Test suite for Telegram alerts functionality
"""

import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from telegram_alerts import TelegramAlertSystem, ArbitrageOpportunity, TelegramConfig


class TestTelegramAlertSystem:
    """Test cases for Telegram alert system"""

    @pytest.fixture
    def telegram_config(self):
        """Create test Telegram configuration"""
        return TelegramConfig(
            token="test_token_123",
            chat_ids=[123456789, 987654321],
            enabled=True
        )

    @pytest.fixture
    def alert_system(self, telegram_config):
        """Create test alert system"""
        return TelegramAlertSystem(telegram_config)

    @pytest.fixture
    def sample_opportunity(self):
        """Create sample arbitrage opportunity"""
        return ArbitrageOpportunity(
            pair="BTC/USDT",
            timestamp=1640995200.0,  # 2022-01-01 00:00:00
            probability=0.85,
            confidence=0.92,
            spread_prediction=0.0012,
            exchanges=["binance", "coinbase", "kraken"],
            prices={"binance": 45000.0, "coinbase": 44950.0, "kraken": 45020.0},
            volumes={"binance": 100.0, "coinbase": 80.0, "kraken": 120.0},
            risk_score=0.15,
            profit_potential=0.0234
        )

    @pytest.mark.asyncio
    async def test_initialization_disabled(self):
        """Test initialization with disabled config"""
        config = TelegramConfig(token="", chat_ids=[], enabled=False)
        system = TelegramAlertSystem(config)

        assert not system.config.enabled
        assert system.bot is None
        assert not system.is_running

    @pytest.mark.asyncio
    async def test_initialization_enabled(self, alert_system):
        """Test initialization with enabled config"""
        with patch('telegram.Bot') as mock_bot_class, \
             patch('telegram.ext.Application.builder') as mock_app_builder:

            # Mock bot
            mock_bot = AsyncMock()
            mock_bot_class.return_value = mock_bot
            mock_bot.get_me = AsyncMock(return_value=MagicMock(username="testbot"))

            # Mock application
            mock_app = AsyncMock()
            mock_app.initialize = AsyncMock()
            mock_app.start = AsyncMock()
            mock_app.updater.start_polling = AsyncMock()
            mock_app.add_handler = MagicMock()

            # Mock builder
            mock_builder_instance = MagicMock()
            mock_builder_instance.token.return_value = mock_builder_instance
            mock_builder_instance.build.return_value = mock_app
            mock_app_builder.return_value = mock_builder_instance

            await alert_system.initialize()

            assert alert_system.config.enabled
            assert alert_system.bot is not None
            assert alert_system.is_running
            mock_bot.get_me.assert_called_once()
            mock_app.initialize.assert_called_once()
            mock_app.start.assert_called_once()

    @pytest.mark.asyncio
    async def test_initialization_failure(self, alert_system):
        """Test initialization failure handling"""
        with patch('telegram.Bot') as mock_bot_class:
            mock_bot = AsyncMock()
            mock_bot_class.return_value = mock_bot
            mock_bot.get_me.side_effect = Exception("API Error")

            await alert_system.initialize()

            assert not alert_system.config.enabled
            assert not alert_system.is_running

    @pytest.mark.asyncio
    async def test_send_opportunity_alert_disabled(self, sample_opportunity):
        """Test sending opportunity alert when disabled"""
        config = TelegramConfig(token="", chat_ids=[], enabled=False)
        system = TelegramAlertSystem(config)

        # Should not raise exception
        await system.send_opportunity_alert(sample_opportunity)

        assert system.alerts_sent == 0

    @pytest.mark.asyncio
    async def test_send_opportunity_alert_enabled(self, alert_system, sample_opportunity):
        """Test sending opportunity alert when enabled"""
        # Mock the bot and set up the system as running
        alert_system.bot = AsyncMock()
        alert_system.is_running = True

        await alert_system.send_opportunity_alert(sample_opportunity)

        # Should send to both chat IDs (2 total)
        assert alert_system.alerts_sent == 2
        assert alert_system.opportunities_alerted == 1
        assert alert_system.bot.send_message.call_count == 2

    @pytest.mark.asyncio
    async def test_send_opportunity_alert_failure(self, alert_system, sample_opportunity):
        """Test handling of send failure"""
        alert_system.bot = AsyncMock()
        alert_system.is_running = True
        alert_system.bot.send_message.side_effect = Exception("Send failed")

        await alert_system.send_opportunity_alert(sample_opportunity)

        assert alert_system.alerts_sent == 0  # No successful sends
        assert alert_system.errors_count == 2  # One error per chat ID

    @pytest.mark.asyncio
    async def test_send_system_alert(self, alert_system):
        """Test sending system alert"""
        alert_system.bot = AsyncMock()
        alert_system.is_running = True

        await alert_system.send_system_alert("Test Title", "Test message", "info")

        alert_system.bot.send_message.assert_called()

    def test_format_opportunity_message(self, alert_system, sample_opportunity):
        """Test opportunity message formatting"""
        message = alert_system._format_opportunity_message(sample_opportunity)

        assert "🚀 *ARBITRAGE OPPORTUNITY DETECTED*" in message
        assert "BTC/USDT" in message
        assert "85.0%" in message  # probability
        assert "0.0012" in message  # spread
        assert "2.34%" in message  # profit potential

    def test_get_status(self, alert_system):
        """Test status reporting"""
        alert_system.alerts_sent = 5
        alert_system.opportunities_alerted = 3
        alert_system.errors_count = 1

        status = alert_system.get_status()

        assert status['enabled'] == True
        assert status['running'] == False
        assert status['alerts_sent'] == 5
        assert status['opportunities_alerted'] == 3
        assert status['errors'] == 1
        assert status['chat_ids'] == 2

    @pytest.mark.asyncio
    async def test_shutdown(self, alert_system):
        """Test system shutdown"""
        # Set up mock application
        alert_system.application = AsyncMock()
        alert_system.is_running = True

        await alert_system.shutdown()

        assert not alert_system.is_running
        alert_system.application.updater.stop.assert_called()
        alert_system.application.stop.assert_called()
        alert_system.application.shutdown.assert_called()


class TestTelegramConfig:
    """Test cases for Telegram configuration"""

    def test_config_creation(self):
        """Test configuration object creation"""
        config = TelegramConfig(
            token="test_token",
            chat_ids=[123, 456],
            enabled=True
        )

        assert config.token == "test_token"
        assert config.chat_ids == [123, 456]
        assert config.enabled == True

    def test_config_defaults(self):
        """Test configuration defaults"""
        config = TelegramConfig(token="test_token", chat_ids=[123])

        assert config.enabled == True  # Default value


class TestGlobalFunctions:
    """Test global convenience functions"""

    @pytest.mark.asyncio
    async def test_get_telegram_alert_system(self):
        """Test global alert system getter"""
        from telegram_alerts import get_telegram_alert_system

        system1 = get_telegram_alert_system()
        system2 = get_telegram_alert_system()

        assert system1 is system2  # Should return same instance

    @pytest.mark.asyncio
    async def test_initialize_telegram_alerts(self):
        """Test global initialization function"""
        from telegram_alerts import initialize_telegram_alerts

        with patch('telegram_alerts.TelegramAlertSystem.initialize') as mock_init:
            mock_init.return_value = None

            system = await initialize_telegram_alerts()

            assert system is not None
            mock_init.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_telegram_alerts(self):
        """Test global shutdown function"""
        from telegram_alerts import shutdown_telegram_alerts

        with patch('telegram_alerts.TelegramAlertSystem.shutdown') as mock_shutdown:
            mock_shutdown.return_value = None

            await shutdown_telegram_alerts()

            mock_shutdown.assert_called_once()


if __name__ == "__main__":
    # Run tests
    pytest.main([__file__, "-v"])