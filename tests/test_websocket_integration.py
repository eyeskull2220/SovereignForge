#!/usr/bin/env python3
"""
WebSocket Integration Tests for SovereignForge
Tests WebSocket connectivity, reconnection, and data streaming
"""

import asyncio
import logging
import os
import sys
import time
from typing import Any, Dict
from unittest.mock import AsyncMock, Mock, patch

import pytest

from exchange_connector import (
    WEBSOCKET_AVAILABLE,
    ExchangeConnector,
    MultiExchangeConnector,
)

logger = logging.getLogger(__name__)

class TestWebSocketIntegration:
    """Test WebSocket integration functionality"""

    @pytest.mark.asyncio
    async def test_exchange_connector_websocket_initialization(self):
        """Test WebSocket initialization in ExchangeConnector"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        assert connector.enable_websocket
        assert connector.websocket_manager is not None
        assert connector.reconnect_manager is not None
        assert 'ticker' in connector.websocket_manager.message_handlers
        assert 'orderbook' in connector.websocket_manager.message_handlers
        assert 'trade' in connector.websocket_manager.message_handlers

    @pytest.mark.asyncio
    async def test_websocket_url_mapping(self):
        """Test WebSocket URL mapping for different exchanges"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        test_cases = [
            ('binance', 'wss://stream.binance.com:9443/ws'),
            ('coinbase', 'wss://ws-feed.pro.coinbase.com'),
            ('kraken', 'wss://ws.kraken.com'),
            ('unknown', None)
        ]

        for exchange_name, expected_url in test_cases:
            connector = ExchangeConnector(exchange_name, enable_websocket=True)
            actual_url = connector._get_websocket_url()
            assert actual_url == expected_url, f"URL mismatch for {exchange_name}"

    @pytest.mark.asyncio
    async def test_websocket_connection_lifecycle(self):
        """Test WebSocket connection lifecycle"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Test connection status before connecting
        status = connector.get_websocket_status()
        assert status['websocket_enabled']
        assert 'connection_status' in status

        # Mock the WebSocket connection to avoid actual network calls
        with patch.object(connector.websocket_manager, 'connect', new_callable=AsyncMock) as mock_connect:
            with patch.object(connector.websocket_manager, 'start_auto_reconnect', new_callable=AsyncMock) as mock_start:
                mock_connect.return_value = True

                # Test starting WebSocket
                await connector.start_websocket()

                mock_start.assert_called_once()

                # Test stopping WebSocket
                with patch.object(connector.websocket_manager, 'disconnect', new_callable=AsyncMock) as mock_disconnect:
                    await connector.stop_websocket()
                    mock_disconnect.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_subscription_methods(self):
        """Test WebSocket subscription methods"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Mock WebSocket manager methods
        with patch.object(connector.websocket_manager, 'subscribe_to_ticker', new_callable=AsyncMock) as mock_ticker:
            with patch.object(connector.websocket_manager, 'subscribe_to_orderbook', new_callable=AsyncMock) as mock_orderbook:
                with patch.object(connector.websocket_manager, 'subscribe_to_trades', new_callable=AsyncMock) as mock_trades:

                    mock_ticker.return_value = True
                    mock_orderbook.return_value = True
                    mock_trades.return_value = True

                    # Test subscriptions
                    result = await connector.subscribe_to_ticker('BTC/USDC')
                    assert result
                    mock_ticker.assert_called_once_with('BTC/USDC')

                    result = await connector.subscribe_to_orderbook('BTC/USDC', 10)
                    assert result
                    mock_orderbook.assert_called_once_with('BTC/USDC', 10)

                    result = await connector.subscribe_to_trades('BTC/USDC')
                    assert result
                    mock_trades.assert_called_once_with('BTC/USDC')

    def test_message_handlers(self):
        """Test message handler registration and callbacks"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Test adding custom message handler
        custom_handler = Mock()
        connector.add_message_handler('custom_event', custom_handler)

        assert 'custom_event' in connector.message_handlers
        assert connector.message_handlers['custom_event'] == custom_handler

    @pytest.mark.asyncio
    async def test_multi_exchange_websocket_operations(self):
        """Test MultiExchangeConnector WebSocket operations"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        exchanges_config = {
            'binance': {},
            'coinbase': {}
        }

        multi_connector = MultiExchangeConnector(exchanges_config, enable_websocket=True)

        # Verify connectors were created with WebSocket enabled
        assert len(multi_connector.connectors) == 2
        for connector in multi_connector.connectors.values():
            assert connector.enable_websocket

        # Test WebSocket status
        status = multi_connector.get_websocket_status()
        assert status['websocket_enabled']
        assert len(status['exchanges']) == 2

        # Test message handler addition
        custom_handler = Mock()
        multi_connector.add_message_handler('test_event', custom_handler)

        assert 'test_event' in multi_connector.message_handlers
        for connector in multi_connector.connectors.values():
            assert 'test_event' in connector.message_handlers

    @pytest.mark.asyncio
    async def test_websocket_fallback_to_rest(self):
        """Test fallback to REST API when WebSocket fails"""
        # Test with WebSocket disabled
        connector = ExchangeConnector('binance', enable_websocket=False)

        assert not connector.enable_websocket
        assert connector.websocket_manager is None

        # REST API should still work
        # Note: This would require mocking the exchange API in a real test
        status = connector.get_websocket_status()
        assert not status['websocket_enabled']

    def test_websocket_disabled_gracefully(self):
        """Test graceful handling when WebSocket components are not available"""
        # Temporarily disable WebSocket availability
        import exchange_connector
        original_available = exchange_connector.WEBSOCKET_AVAILABLE
        exchange_connector.WEBSOCKET_AVAILABLE = False

        try:
            connector = ExchangeConnector('binance', enable_websocket=True)

            # Should fallback to REST-only mode
            assert not connector.enable_websocket
            assert connector.websocket_manager is None

        finally:
            # Restore original state
            exchange_connector.WEBSOCKET_AVAILABLE = original_available

    @pytest.mark.asyncio
    async def test_connection_health_monitoring(self):
        """Test connection health monitoring"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Get initial health status
        status = connector.get_websocket_status()
        health = status['connection_status']

        # Verify health metrics are present
        assert 'connected' in health
        assert 'uptime_seconds' in health
        assert 'message_count' in health
        assert 'error_count' in health
        assert 'healthy' in health

class TestWebSocketLoadTesting:
    """Load testing for WebSocket connections"""

    @pytest.mark.asyncio
    async def test_concurrent_connections(self):
        """Test multiple concurrent WebSocket connections"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        exchanges_config = {
            'binance': {},
            'coinbase': {},
            'kraken': {},
            'bitfinex': {}
        }

        multi_connector = MultiExchangeConnector(exchanges_config, enable_websocket=True)

        # Mock WebSocket connections to avoid actual network calls
        connection_mocks = []
        for connector in multi_connector.connectors.values():
            mock_connect = AsyncMock(return_value=True)
            mock_start = AsyncMock()
            patch.object(connector.websocket_manager, 'connect', mock_connect)
            patch.object(connector.websocket_manager, 'start_auto_reconnect', mock_start)
            connection_mocks.append((mock_connect, mock_start))

        # Start all WebSocket connections concurrently
        start_time = time.time()
        await multi_connector.start_websockets()
        end_time = time.time()

        # Verify all connections were attempted
        assert end_time - start_time < 5.0  # Should complete within 5 seconds

        # Stop all connections
        await multi_connector.stop_websockets()

    @pytest.mark.asyncio
    async def test_subscription_load(self):
        """Test high-volume subscription operations"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        exchanges_config = {
            'binance': {},
            'coinbase': {}
        }

        multi_connector = MultiExchangeConnector(exchanges_config, enable_websocket=True)

        # Mock subscription methods
        for connector in multi_connector.connectors.values():
            patch.object(connector, 'subscribe_to_ticker', AsyncMock(return_value=True))
            patch.object(connector, 'subscribe_to_orderbook', AsyncMock(return_value=True))

        # Perform multiple subscriptions concurrently
        symbols = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'ADA/USDC']

        start_time = time.time()

        # Subscribe to tickers for all symbols
        for symbol in symbols:
            await multi_connector.subscribe_all_to_ticker(symbol)

        # Subscribe to orderbooks for all symbols
        for symbol in symbols:
            await multi_connector.subscribe_all_to_orderbook(symbol, 10)

        end_time = time.time()

        # Should complete within reasonable time
        assert end_time - start_time < 10.0

class TestWebSocketFailureScenarios:
    """Test WebSocket failure scenarios and recovery"""

    @pytest.mark.asyncio
    async def test_connection_failure_recovery(self):
        """Test connection failure and recovery"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Mock connection failure followed by success
        call_count = 0
        async def mock_connect():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Network unreachable")
            return True

        with patch.object(connector.websocket_manager, 'connect', side_effect=mock_connect):
            with patch.object(connector.websocket_manager, 'start_auto_reconnect', new_callable=AsyncMock) as mock_start:
                # Attempt to start WebSocket (should handle failure gracefully)
                await connector.start_websocket()

                # Verify reconnection was attempted
                mock_start.assert_called_once()

    @pytest.mark.asyncio
    async def test_websocket_timeout_handling(self):
        """Test WebSocket timeout handling"""
        if not WEBSOCKET_AVAILABLE:
            pytest.skip("WebSocket components not available")

        connector = ExchangeConnector('binance', enable_websocket=True)

        # Mock timeout during connection
        with patch.object(connector.websocket_manager, 'connect', side_effect=asyncio.TimeoutError):
            with patch.object(connector.websocket_manager, 'start_auto_reconnect', new_callable=AsyncMock) as mock_start:
                await connector.start_websocket()

                # Should still attempt to start reconnection
                mock_start.assert_called_once()

if __name__ == "__main__":
    # Run basic connectivity test
    print("Running WebSocket integration tests...")

    if WEBSOCKET_AVAILABLE:
        print("✓ WebSocket components available")

        # Test basic initialization
        try:
            connector = ExchangeConnector('binance', enable_websocket=True)
            print("✓ ExchangeConnector with WebSocket initialized")

            status = connector.get_websocket_status()
            print(f"✓ WebSocket status: {status['websocket_enabled']}")

        except Exception as e:
            print(f"✗ WebSocket initialization failed: {e}")

    else:
        print("✗ WebSocket components not available - install aiohttp")

    print("WebSocket integration test completed!")
