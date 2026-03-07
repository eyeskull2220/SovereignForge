#!/usr/bin/env python3
"""
WebSocket Connection Manager
Handles WebSocket connections with health monitoring and error handling
"""

import asyncio
import logging
import time
from typing import Dict, Optional, Callable, Any
from datetime import datetime, timedelta
import aiohttp
from aiohttp import WSMsgType

logger = logging.getLogger(__name__)

class ConnectionHealth:
    """Tracks connection health metrics"""

    def __init__(self):
        self.connected_at: Optional[datetime] = None
        self.last_message_at: Optional[datetime] = None
        self.message_count: int = 0
        self.error_count: int = 0
        self.reconnect_count: int = 0
        self.uptime_seconds: float = 0.0

    def mark_connected(self):
        """Mark connection as established"""
        self.connected_at = datetime.now()
        self.last_message_at = datetime.now()
        self.error_count = 0

    def mark_message_received(self):
        """Mark message received"""
        self.last_message_at = datetime.now()
        self.message_count += 1

    def mark_error(self):
        """Mark error occurred"""
        self.error_count += 1

    def mark_reconnect(self):
        """Mark reconnection attempt"""
        self.reconnect_count += 1

    def get_uptime(self) -> float:
        """Get connection uptime in seconds"""
        if self.connected_at:
            return (datetime.now() - self.connected_at).total_seconds()
        return 0.0

    def is_healthy(self, max_errors: int = 5, timeout_seconds: int = 30) -> bool:
        """Check if connection is healthy"""
        if not self.connected_at:
            return False

        # Check for too many errors
        if self.error_count > max_errors:
            return False

        # Check for message timeout
        if self.last_message_at:
            time_since_last_message = (datetime.now() - self.last_message_at).total_seconds()
            if time_since_last_message > timeout_seconds:
                return False

        return True

class WebSocketConnectionManager:
    """Manages WebSocket connections with health monitoring"""

    def __init__(self, exchange_name: str, base_url: str, api_key: str = None, api_secret: str = None):
        self.exchange_name = exchange_name
        self.base_url = base_url
        self.api_key = api_key
        self.api_secret = api_secret

        self.session: Optional[aiohttp.ClientSession] = None
        self.ws: Optional[aiohttp.ClientWebSocketResponse] = None
        self.health = ConnectionHealth()

        self.message_handlers: Dict[str, Callable] = {}
        self.error_handlers: Dict[str, Callable] = {}
        self.connection_handlers: Dict[str, Callable] = {}

        self.is_running = False
        self.reconnect_delay = 1.0  # Start with 1 second
        self.max_reconnect_delay = 60.0  # Max 1 minute
        self.reconnect_backoff = 2.0  # Exponential backoff multiplier

    async def connect(self) -> bool:
        """Establish WebSocket connection"""
        try:
            if not self.session:
                self.session = aiohttp.ClientSession()

            # Construct WebSocket URL
            ws_url = self.base_url.replace('https://', 'wss://').replace('http://', 'ws://')

            logger.info(f"Connecting to {self.exchange_name} WebSocket: {ws_url}")

            self.ws = await self.session.ws_connect(
                ws_url,
                heartbeat=30,  # 30 second heartbeat
                compress=15,   # Compression level
                proxy=None
            )

            self.health.mark_connected()
            logger.info(f"Successfully connected to {self.exchange_name} WebSocket")

            # Notify connection handlers
            for handler in self.connection_handlers.values():
                try:
                    await handler('connected', self.exchange_name)
                except Exception as e:
                    logger.error(f"Error in connection handler: {e}")

            return True

        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_name} WebSocket: {e}")
            self.health.mark_error()
            return False

    async def disconnect(self):
        """Close WebSocket connection"""
        try:
            if self.ws:
                await self.ws.close()
                self.ws = None

            if self.session:
                await self.session.close()
                self.session = None

            logger.info(f"Disconnected from {self.exchange_name} WebSocket")

            # Notify connection handlers
            for handler in self.connection_handlers.values():
                try:
                    await handler('disconnected', self.exchange_name)
                except Exception as e:
                    logger.error(f"Error in disconnection handler: {e}")

        except Exception as e:
            logger.error(f"Error during disconnect: {e}")

    async def send_message(self, message: Dict[str, Any]) -> bool:
        """Send message over WebSocket"""
        try:
            if not self.ws:
                logger.warning("WebSocket not connected, cannot send message")
                return False

            await self.ws.send_json(message)
            return True

        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            self.health.mark_error()
            return False

    async def receive_messages(self):
        """Receive and process messages from WebSocket"""
        try:
            async for msg in self.ws:
                if msg.type == WSMsgType.TEXT:
                    try:
                        data = msg.json()
                        self.health.mark_message_received()

                        # Route message to appropriate handler
                        await self._handle_message(data)

                    except Exception as e:
                        logger.error(f"Error processing message: {e}")
                        self.health.mark_error()

                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {msg}")
                    self.health.mark_error()
                    break

                elif msg.type == WSMsgType.CLOSED:
                    logger.warning("WebSocket connection closed")
                    break

        except Exception as e:
            logger.error(f"Error in message reception: {e}")
            self.health.mark_error()

    async def _handle_message(self, data: Dict[str, Any]):
        """Handle incoming WebSocket message"""
        try:
            # Determine message type and route to handler
            message_type = data.get('type', 'unknown')

            if message_type in self.message_handlers:
                await self.message_handlers[message_type](data, self.exchange_name)
            else:
                logger.debug(f"No handler for message type: {message_type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def add_message_handler(self, message_type: str, handler: Callable):
        """Add message handler for specific message type"""
        self.message_handlers[message_type] = handler

    def add_error_handler(self, error_type: str, handler: Callable):
        """Add error handler for specific error type"""
        self.error_handlers[error_type] = handler

    def add_connection_handler(self, event_type: str, handler: Callable):
        """Add connection event handler"""
        self.connection_handlers[event_type] = handler

    async def start_auto_reconnect(self):
        """Start automatic reconnection with exponential backoff"""
        self.is_running = True

        while self.is_running:
            try:
                # Attempt connection
                if await self.connect():
                    # Reset reconnect delay on successful connection
                    self.reconnect_delay = 1.0

                    # Start message reception
                    await self.receive_messages()

                else:
                    logger.warning(f"Connection failed, retrying in {self.reconnect_delay}s")

            except Exception as e:
                logger.error(f"Connection error: {e}")
                self.health.mark_reconnect()

            # Wait before reconnect attempt
            if self.is_running:
                await asyncio.sleep(self.reconnect_delay)

                # Exponential backoff with max delay
                self.reconnect_delay = min(
                    self.reconnect_delay * self.reconnect_backoff,
                    self.max_reconnect_delay
                )

    def stop_auto_reconnect(self):
        """Stop automatic reconnection"""
        self.is_running = False

    def get_health_status(self) -> Dict[str, Any]:
        """Get connection health status"""
        return {
            'exchange': self.exchange_name,
            'connected': self.ws is not None and not self.ws.closed,
            'uptime_seconds': self.health.get_uptime(),
            'message_count': self.health.message_count,
            'error_count': self.health.error_count,
            'reconnect_count': self.health.reconnect_count,
            'healthy': self.health.is_healthy(),
            'last_message_age': (
                (datetime.now() - self.health.last_message_at).total_seconds()
                if self.health.last_message_at else None
            )
        }

    async def subscribe_to_ticker(self, symbol: str):
        """Subscribe to ticker updates"""
        subscription_msg = {
            'type': 'subscribe',
            'channel': 'ticker',
            'symbol': symbol
        }
        return await self.send_message(subscription_msg)

    async def subscribe_to_orderbook(self, symbol: str, depth: int = 10):
        """Subscribe to orderbook updates"""
        subscription_msg = {
            'type': 'subscribe',
            'channel': 'orderbook',
            'symbol': symbol,
            'depth': depth
        }
        return await self.send_message(subscription_msg)

    async def subscribe_to_trades(self, symbol: str):
        """Subscribe to trade updates"""
        subscription_msg = {
            'type': 'subscribe',
            'channel': 'trades',
            'symbol': symbol
        }
        return await self.send_message(subscription_msg)