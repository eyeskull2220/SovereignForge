#!/usr/bin/env python3
"""
SovereignForge - Hybrid Data Integration Service
Multi-exchange market data aggregation with MiCA compliance

Delegates WebSocket connections to MultiExchangeConnector (websocket_connector.py)
which has complete parsers for all 7 exchanges (Binance, Coinbase, Kraken, KuCoin, OKX, Bybit, Gate).
"""

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional

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
    Hybrid data integration service for multi-exchange market data with WebSocket resilience.

    Wraps MultiExchangeConnector from websocket_connector.py and adds:
    - MiCA compliance filtering
    - Async callback dispatch
    - Connection health monitoring
    """

    def __init__(self):
        self.data_sources = ['binance', 'coinbase', 'kraken', 'kucoin', 'okx', 'bybit', 'gate']
        self.data_sources_count = len(self.data_sources)
        self.is_running = False
        self.data_callbacks: List[Callable] = []
        self._connector = None
        self._stream_task: Optional[asyncio.Task] = None

        # Connection tracking
        self.connections: Dict[str, ConnectionStatus] = {}
        for exchange in self.data_sources:
            self.connections[exchange] = ConnectionStatus(
                exchange=exchange,
                connected=False,
                last_message=0,
                reconnect_attempts=0,
                error_count=0
            )

        # Import compliance engine
        try:
            from compliance import get_compliance_engine
            self.compliance_engine = get_compliance_engine()
        except ImportError:
            logger.warning("Compliance engine not available, using mock")
            self.compliance_engine = MockComplianceEngine()

    def _get_connector(self):
        """Lazily initialize MultiExchangeConnector."""
        if self._connector is None:
            from websocket_connector import MultiExchangeConnector
            self._connector = MultiExchangeConnector()
            # Register our bridge callback
            self._connector.add_data_callback(self._on_market_data_sync)
        return self._connector

    async def initialize(self):
        """Initialize the data integration service"""
        logger.info("Initializing HybridDataIntegrationService")
        self._get_connector()
        logger.info(f"Data integration service initialized with {self.data_sources_count} exchanges")

    def add_data_callback(self, callback: Callable):
        """Add callback for market data updates"""
        self.data_callbacks.append(callback)

    def _on_market_data_sync(self, data):
        """Bridge: sync callback from MultiExchangeConnector → async dispatch.

        MultiExchangeConnector invokes callbacks synchronously from its streaming loop.
        We convert the connector's MarketData to our MarketData and schedule async dispatch.
        """
        try:
            # Convert websocket_connector.MarketData to our MarketData
            market_data = MarketData(
                exchange=data.exchange,
                pair=data.pair,
                timestamp=data.timestamp,
                price=data.price,
                volume=data.volume,
                bid_price=data.bid_price,
                ask_price=data.ask_price,
                bid_volume=data.bid_volume,
                ask_volume=data.ask_volume,
            )

            # Update connection status
            if data.exchange in self.connections:
                self.connections[data.exchange].connected = True
                self.connections[data.exchange].last_message = time.time()

            # Schedule async handling
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.ensure_future(self._handle_market_data(market_data))
            else:
                loop.run_until_complete(self._handle_market_data(market_data))

        except Exception as e:
            logger.error(f"Error in sync→async bridge: {e}")
            if data.exchange in self.connections:
                self.connections[data.exchange].error_count += 1

    async def _handle_market_data(self, data: MarketData):
        """Handle incoming market data with compliance filtering"""
        # Apply compliance filtering
        if hasattr(self.compliance_engine, 'is_pair_compliant'):
            if not self.compliance_engine.is_pair_compliant(data.pair):
                logger.warning(f"Non-compliant pair filtered: {data.pair}")
                return

        # Notify callbacks in parallel
        async def _invoke(cb, market_data):
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(market_data)
                else:
                    cb(market_data)
            except Exception as e:
                logger.error(f"Error in data callback: {e}")

        await asyncio.gather(*[_invoke(cb, data) for cb in self.data_callbacks])

    async def start_websocket_connections(self):
        """Start WebSocket connections for all exchanges via MultiExchangeConnector."""
        connector = self._get_connector()

        # MiCA compliant pairs to subscribe to
        compliant_pairs = [
            'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC',
            'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
            'XDC/USDC', 'ONDO/USDC',
        ]

        logger.info(f"Connecting to {len(self.data_sources)} exchanges for {len(compliant_pairs)} pairs...")
        success = await connector.connect_all_exchanges(compliant_pairs)

        if success:
            self.is_running = True
            # Start streaming in background task
            self._stream_task = asyncio.create_task(self._run_data_stream())
            logger.info("WebSocket connections established, data streaming started")
        else:
            logger.error("Failed to connect to any exchange")

    async def _run_data_stream(self):
        """Run the data stream with automatic reconnection."""
        connector = self._get_connector()
        while self.is_running:
            try:
                await connector.start_data_stream()
            except Exception as e:
                logger.error(f"Data stream error, restarting in 5s: {e}")
                if self.is_running:
                    await asyncio.sleep(5)

    async def stop(self):
        """Stop all WebSocket connections"""
        self.is_running = False

        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None

        if self._connector:
            await self._connector.stop()

        # Mark all connections as disconnected
        for status in self.connections.values():
            status.connected = False

        logger.info("Data integration service stopped")

    def get_connection_health(self) -> Dict[str, Any]:
        """Get WebSocket connection health status"""
        health = {}
        current_time = time.time()

        for exchange, status in self.connections.items():
            health[exchange] = {
                'connected': status.connected,
                'last_message_seconds_ago': current_time - status.last_message if status.last_message > 0 else None,
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

    async def is_healthy(self) -> bool:
        """Check if the data service is healthy"""
        try:
            if not self.is_running:
                return False
            if len(self.data_callbacks) == 0:
                return False
            health = self.get_connection_health()
            healthy_connections = sum(1 for conn in health.values() if conn.get('healthy', False))
            return healthy_connections > 0
        except Exception as e:
            logger.error(f"Health check error: {e}")
            return False


class MockComplianceEngine:
    """Mock compliance engine for when compliance.py is not available"""

    def is_asset_compliant(self, asset: str) -> bool:
        compliant_assets = ['BTC', 'ETH', 'XRP', 'ADA', 'XLM', 'HBAR', 'ALGO', 'LINK', 'IOTA', 'VET', 'XDC', 'ONDO']
        return asset in compliant_assets

    def is_pair_compliant(self, pair: str) -> bool:
        base = pair.split('/')[0] if '/' in pair else pair
        return self.is_asset_compliant(base)

    def filter_compliant_pairs(self, pairs: List[str]) -> List[str]:
        return [pair for pair in pairs if self.is_pair_compliant(pair)]
