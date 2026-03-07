#!/usr/bin/env python3
"""
SovereignForge - Hybrid Data Integration Service
Multi-exchange market data aggregation with MiCA compliance
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import time
import websockets
import json

logger = logging.getLogger(__name__)

@dataclass
class MarketData:
    """Standardized market data structure"""
    exchange: str
    pair: str
    timestamp: float
    price: float
    volume: float
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float

@dataclass
class ConnectionStatus:
    """WebSocket connection status"""
    exchange: str
    connected: bool
    last_message: float
    reconnect_attempts: int
    error_count: int

class HybridDataIntegrationService:
    """
    Hybrid data integration service for multi-exchange market data with WebSocket resilience
    """

    def __init__(self):
        self.data_sources = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx']
        self.data_sources_count = len(self.data_sources)
        self.is_running = False
        self.data_callbacks: List[Callable] = []

        # WebSocket resilience
        self.connections: Dict[str, ConnectionStatus] = {}
        self.websocket_tasks: Dict[str, asyncio.Task] = {}
        self.reconnect_delays = [1, 2, 5, 10, 30, 60]  # Progressive backoff in seconds
        self.max_reconnect_attempts = 10
        self.connection_timeout = 30  # seconds
        self.heartbeat_interval = 60  # seconds

        # Import compliance engine (will be available when compliance.py is created)
        try:
            from compliance import get_compliance_engine
            self.compliance_engine = get_compliance_engine()
        except ImportError:
            logger.warning("Compliance engine not available, using mock")
            self.compliance_engine = MockComplianceEngine()

        # Initialize connection status
        for exchange in self.data_sources:
            self.connections[exchange] = ConnectionStatus(
                exchange=exchange,
                connected=False,
                last_message=0,
                reconnect_attempts=0,
                error_count=0
            )

    async def initialize(self):
        """Initialize the data integration service"""
        logger.info("Initializing HybridDataIntegrationService")
        self.is_running = True
        logger.info(f"Data integration service initialized with {self.data_sources_count} exchanges")

    def add_data_callback(self, callback: Callable):
        """Add callback for market data updates"""
        self.data_callbacks.append(callback)

    async def _handle_market_data(self, data: MarketData):
        """Handle incoming market data"""
        # Apply compliance filtering
        if hasattr(self.compliance_engine, 'is_pair_compliant'):
            if not self.compliance_engine.is_pair_compliant(data.pair):
                logger.warning(f"Non-compliant pair filtered: {data.pair}")
                return

        # Notify callbacks
        for callback in self.data_callbacks:
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)
            except Exception as e:
                logger.error(f"Error in data callback: {e}")

    async def start_websocket_connections(self):
        """Start WebSocket connections for all exchanges"""
        for exchange in self.data_sources:
            if exchange not in self.websocket_tasks:
                task = asyncio.create_task(self._manage_websocket_connection(exchange))
                self.websocket_tasks[exchange] = task
                logger.info(f"Started WebSocket connection manager for {exchange}")

    async def stop_websocket_connections(self):
        """Stop all WebSocket connections"""
        for exchange, task in self.websocket_tasks.items():
            task.cancel()
            logger.info(f"Stopped WebSocket connection for {exchange}")

        self.websocket_tasks.clear()

        # Wait for tasks to complete
        await asyncio.gather(*[task for task in self.websocket_tasks.values()], return_exceptions=True)

    async def _manage_websocket_connection(self, exchange: str):
        """Manage WebSocket connection with automatic reconnection"""
        while self.is_running:
            try:
                await self._connect_websocket(exchange)
            except Exception as e:
                logger.error(f"WebSocket connection failed for {exchange}: {e}")
                await self._handle_connection_failure(exchange)

    async def _connect_websocket(self, exchange: str):
        """Establish WebSocket connection for an exchange"""
        ws_url = self._get_websocket_url(exchange)

        try:
            async with websockets.connect(ws_url, timeout=self.connection_timeout) as websocket:
                logger.info(f"Connected to {exchange} WebSocket")
                self.connections[exchange].connected = True
                self.connections[exchange].reconnect_attempts = 0

                # Subscribe to trading pairs
                await self._subscribe_to_pairs(websocket, exchange)

                # Start heartbeat
                heartbeat_task = asyncio.create_task(self._send_heartbeats(websocket, exchange))

                try:
                    async for message in websocket:
                        await self._process_websocket_message(exchange, message)
                        self.connections[exchange].last_message = time.time()
                finally:
                    heartbeat_task.cancel()
                    self.connections[exchange].connected = False

        except Exception as e:
            self.connections[exchange].connected = False
            raise e

    async def _subscribe_to_pairs(self, websocket, exchange: str):
        """Subscribe to trading pairs for an exchange"""
        # This would be implemented with exchange-specific subscription messages
        # For now, subscribe to MiCA compliant pairs
        compliant_pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'DOGE/USDT']

        subscription_message = self._create_subscription_message(exchange, compliant_pairs)
        if subscription_message:
            await websocket.send(json.dumps(subscription_message))
            logger.info(f"Subscribed to {len(compliant_pairs)} pairs on {exchange}")

    def _create_subscription_message(self, exchange: str, pairs: List[str]) -> Optional[Dict[str, Any]]:
        """Create exchange-specific subscription message"""
        # Simplified - would need exchange-specific implementations
        if exchange == 'binance':
            return {
                "method": "SUBSCRIBE",
                "params": [f"{pair.lower()}@ticker" for pair in pairs],
                "id": 1
            }
        return None

    async def _process_websocket_message(self, exchange: str, message: str):
        """Process incoming WebSocket message"""
        try:
            data = json.loads(message)

            # Convert to standardized MarketData format
            market_data = self._parse_market_data(exchange, data)
            if market_data:
                await self._handle_market_data(market_data)

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON message from {exchange}")
        except Exception as e:
            logger.error(f"Error processing message from {exchange}: {e}")
            self.connections[exchange].error_count += 1

    def _parse_market_data(self, exchange: str, data: Dict[str, Any]) -> Optional[MarketData]:
        """Parse exchange-specific data into standardized format"""
        try:
            # Simplified parsing - would need exchange-specific implementations
            if exchange == 'binance' and 'stream' in data:
                ticker_data = data.get('data', {})
                pair = ticker_data.get('s', '').replace('USDT', '/USDT')

                return MarketData(
                    exchange=exchange,
                    pair=pair,
                    timestamp=time.time(),
                    price=float(ticker_data.get('c', 0)),
                    volume=float(ticker_data.get('v', 0)),
                    bid_price=float(ticker_data.get('b', 0)),
                    ask_price=float(ticker_data.get('a', 0)),
                    bid_volume=float(ticker_data.get('B', 0)),
                    ask_volume=float(ticker_data.get('A', 0))
                )

            return None

        except Exception as e:
            logger.error(f"Error parsing market data from {exchange}: {e}")
            return None

    async def _send_heartbeats(self, websocket, exchange: str):
        """Send periodic heartbeats to maintain connection"""
        while True:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                # Send heartbeat (exchange-specific)
                heartbeat = self._create_heartbeat_message(exchange)
                if heartbeat:
                    await websocket.send(json.dumps(heartbeat))
            except Exception as e:
                logger.error(f"Heartbeat failed for {exchange}: {e}")
                break

    def _create_heartbeat_message(self, exchange: str) -> Optional[Dict[str, Any]]:
        """Create exchange-specific heartbeat message"""
        if exchange == 'binance':
            return {"method": "ping", "id": 1}
        return None

    async def _handle_connection_failure(self, exchange: str):
        """Handle WebSocket connection failure with exponential backoff"""
        status = self.connections[exchange]
        status.reconnect_attempts += 1

        if status.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {exchange}")
            return

        delay_index = min(status.reconnect_attempts - 1, len(self.reconnect_delays) - 1)
        delay = self.reconnect_delays[delay_index]

        logger.info(f"Reconnecting to {exchange} in {delay} seconds (attempt {status.reconnect_attempts})")
        await asyncio.sleep(delay)

    def _get_websocket_url(self, exchange: str) -> str:
        """Get WebSocket URL for exchange"""
        urls = {
            'binance': 'wss://stream.binance.com:9443/ws',
            'coinbase': 'wss://ws-feed.pro.coinbase.com',
            'kraken': 'wss://ws.kraken.com',
            'kucoin': 'wss://ws-api.kucoin.com',
            'okx': 'wss://ws.okx.com:8443/ws/v5/public'
        }
        return urls.get(exchange, '')

    def get_connection_health(self) -> Dict[str, Any]:
        """Get WebSocket connection health status"""
        health = {}
        current_time = time.time()

        for exchange, status in self.connections.items():
            health[exchange] = {
                'connected': status.connected,
                'last_message_seconds_ago': current_time - status.last_message,
                'reconnect_attempts': status.reconnect_attempts,
                'error_count': status.error_count,
                'healthy': status.connected and (current_time - status.last_message) < 300  # 5 minutes
            }

        return health

    def get_service_status(self) -> Dict[str, Any]:
        """Get service status with WebSocket health"""
        return {
            'is_running': self.is_running,
            'data_sources': self.data_sources_count,
            'active_callbacks': len(self.data_callbacks),
            'websocket_connections': self.get_connection_health()
        }

class MockComplianceEngine:
    """Mock compliance engine for when compliance.py is not available"""

    def is_asset_compliant(self, asset: str) -> bool:
        """Mock asset compliance check"""
        compliant_assets = ['BTC', 'ETH', 'XRP', 'ADA', 'XLM', 'HBAR', 'ALGO', 'DOGE']
        return asset in compliant_assets

    def is_pair_compliant(self, pair: str) -> bool:
        """Mock pair compliance check"""
        base = pair.split('/')[0] if '/' in pair else pair
        return self.is_asset_compliant(base)

    def filter_compliant_pairs(self, pairs: List[str]) -> List[str]:
        """Mock pair filtering"""
        return [pair for pair in pairs if self.is_pair_compliant(pair)]