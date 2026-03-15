#!/usr/bin/env python3
"""
SovereignForge WebSocket Feed Validator
Tests WebSocket connections, validates data quality, and monitors feed reliability
"""

import asyncio
import json
import logging
import statistics
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import aiohttp
import websockets

logger = logging.getLogger(__name__)

@dataclass
class WebSocketMetrics:
    """Metrics for WebSocket connection performance"""
    connection_attempts: int = 0
    successful_connections: int = 0
    failed_connections: int = 0
    connection_drops: int = 0
    messages_received: int = 0
    messages_sent: int = 0
    bytes_received: int = 0
    bytes_sent: int = 0
    average_latency_ms: float = 0.0
    min_latency_ms: float = float('inf')
    max_latency_ms: float = 0.0
    latency_samples: List[float] = field(default_factory=list)
    uptime_percentage: float = 0.0
    last_message_time: Optional[float] = None
    connection_start_time: Optional[float] = None

@dataclass
class DataQualityMetrics:
    """Metrics for data quality validation"""
    total_messages: int = 0
    valid_messages: int = 0
    invalid_messages: int = 0
    duplicate_messages: int = 0
    out_of_order_messages: int = 0
    stale_messages: int = 0
    price_anomalies: int = 0
    volume_anomalies: int = 0
    schema_validation_errors: int = 0
    last_valid_message_time: Optional[float] = None
    message_frequency_hz: float = 0.0

@dataclass
class ExchangeConnection:
    """WebSocket connection for a specific exchange"""
    exchange: str
    url: str
    pairs: List[str]
    is_connected: bool = False
    connection: Optional[Any] = None
    metrics: WebSocketMetrics = field(default_factory=WebSocketMetrics)
    data_quality: DataQualityMetrics = field(default_factory=DataQualityMetrics)
    last_heartbeat: Optional[float] = None
    subscription_messages: List[Dict[str, Any]] = field(default_factory=list)

class WebSocketValidator:
    """Comprehensive WebSocket feed validation system"""

    def __init__(self):
        self.connections: Dict[str, ExchangeConnection] = {}
        self.is_running = False
        self.validation_interval = 60  # seconds
        self.heartbeat_interval = 30  # seconds
        self.stale_threshold = 300  # 5 minutes
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 5  # seconds

        # Exchange configurations
        self.exchange_configs = {
            'binance': {
                'url': 'wss://stream.binance.com:9443/ws',
                'pairs': ['btcusdc', 'ethusdc', 'xrpusdc', 'xlmusdc', 'hbarusdc', 'algousdc', 'adausdc'],
                'subscription_template': {
                    "method": "SUBSCRIBE",
                    "params": ["{pair}@ticker"],
                    "id": 1
                }
            },
            'coinbase': {
                'url': 'wss://ws-feed.pro.coinbase.com',
                'pairs': ['BTC-USD', 'ETH-USD', 'XRP-USD', 'XLM-USD', 'HBAR-USD', 'ALGO-USD', 'ADA-USD'],
                'subscription_template': {
                    "type": "subscribe",
                    "product_ids": ["{pair}"],
                    "channels": ["ticker"]
                }
            },
            'kraken': {
                'url': 'wss://ws.kraken.com',
                'pairs': ['BTC/USD', 'ETH/USD', 'XRP/USD', 'XLM/USD', 'HBAR/USD', 'ALGO/USD', 'ADA/USD'],
                'subscription_template': {
                    "event": "subscribe",
                    "pair": ["{pair}"],
                    "subscription": {"name": "ticker"}
                }
            }
        }

        self._initialize_connections()

    def _initialize_connections(self):
        """Initialize connection objects for all exchanges"""
        for exchange, config in self.exchange_configs.items():
            connection = ExchangeConnection(
                exchange=exchange,
                url=config['url'],
                pairs=config['pairs']
            )
            self.connections[exchange] = connection

    async def start_validation(self):
        """Start WebSocket validation for all exchanges"""
        self.is_running = True
        logger.info("Starting WebSocket feed validation")

        # Start validation tasks
        tasks = []
        for connection in self.connections.values():
            task = asyncio.create_task(self._validate_exchange_connection(connection))
            tasks.append(task)

        # Start monitoring task
        monitoring_task = asyncio.create_task(self._monitor_connections())
        tasks.append(monitoring_task)

        await asyncio.gather(*tasks, return_exceptions=True)

    async def stop_validation(self):
        """Stop all WebSocket validations"""
        self.is_running = False
        logger.info("Stopping WebSocket feed validation")

        # Close all connections
        for connection in self.connections.values():
            if connection.connection:
                try:
                    await connection.connection.close()
                except Exception as e:
                    logger.error(f"Error closing {connection.exchange} connection: {e}")

    async def _validate_exchange_connection(self, connection: ExchangeConnection):
        """Validate WebSocket connection for a specific exchange"""
        while self.is_running:
            try:
                await self._connect_and_validate(connection)
                await asyncio.sleep(self.validation_interval)
            except Exception as e:
                logger.error(f"Validation error for {connection.exchange}: {e}")
                connection.metrics.failed_connections += 1
                await asyncio.sleep(self.reconnect_delay)

    async def _connect_and_validate(self, connection: ExchangeConnection):
        """Connect to exchange and validate data feed"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                connection.metrics.connection_attempts += 1

                # Connect to WebSocket
                async with websockets.connect(connection.url) as ws:
                    connection.connection = ws
                    connection.is_connected = True
                    connection.metrics.successful_connections += 1
                    connection.metrics.connection_start_time = time.time()

                    logger.info(f"Connected to {connection.exchange} WebSocket")

                    # Subscribe to data streams
                    await self._subscribe_to_streams(connection)

                    # Validate connection with heartbeat/ping
                    await self._send_heartbeat(connection)

                    # Monitor data feed
                    await self._monitor_data_feed(connection)

            except Exception as e:
                connection.is_connected = False
                connection.metrics.connection_drops += 1
                logger.warning(f"Connection attempt {attempt + 1} failed for {connection.exchange}: {e}")

                if attempt < self.max_reconnect_attempts - 1:
                    await asyncio.sleep(self.reconnect_delay)
                else:
                    logger.error(f"Failed to connect to {connection.exchange} after {self.max_reconnect_attempts} attempts")

    async def _subscribe_to_streams(self, connection: ExchangeConnection):
        """Subscribe to data streams for the exchange"""
        try:
            template = self.exchange_configs[connection.exchange]['subscription_template']

            # Customize subscription for each pair
            for pair in connection.pairs:
                subscription = json.dumps(template).replace('{pair}', pair)
                await connection.connection.send(subscription)
                connection.metrics.messages_sent += 1
                connection.metrics.bytes_sent += len(subscription.encode())

                logger.debug(f"Subscribed to {pair} on {connection.exchange}")

            # Store subscription messages for reference
            connection.subscription_messages.append({
                'timestamp': time.time(),
                'pairs': connection.pairs.copy()
            })

        except Exception as e:
            logger.error(f"Error subscribing to {connection.exchange} streams: {e}")

    async def _send_heartbeat(self, connection: ExchangeConnection):
        """Send heartbeat/ping to maintain connection"""
        try:
            # Different exchanges have different ping formats
            if connection.exchange == 'binance':
                ping_msg = json.dumps({"ping": int(time.time() * 1000)})
            elif connection.exchange == 'coinbase':
                ping_msg = json.dumps({"type": "ping"})
            elif connection.exchange == 'kraken':
                ping_msg = json.dumps({"event": "ping"})
            else:
                ping_msg = json.dumps({"ping": True})

            await connection.connection.send(ping_msg)
            connection.last_heartbeat = time.time()
            connection.metrics.messages_sent += 1
            connection.metrics.bytes_sent += len(ping_msg.encode())

        except Exception as e:
            logger.error(f"Error sending heartbeat to {connection.exchange}: {e}")

    async def _monitor_data_feed(self, connection: ExchangeConnection):
        """Monitor incoming data feed and validate quality"""
        message_count = 0
        start_time = time.time()

        try:
            async for message in connection.connection:
                message_count += 1
                connection.metrics.messages_received += 1
                connection.metrics.bytes_received += len(message.encode())
                connection.metrics.last_message_time = time.time()

                # Validate message
                is_valid = await self._validate_message(connection, message)

                if is_valid:
                    connection.data_quality.valid_messages += 1
                    connection.data_quality.last_valid_message_time = time.time()
                else:
                    connection.data_quality.invalid_messages += 1

                # Check for staleness
                if connection.data_quality.last_valid_message_time:
                    time_since_last_valid = time.time() - connection.data_quality.last_valid_message_time
                    if time_since_last_valid > self.stale_threshold:
                        connection.data_quality.stale_messages += 1

                # Send periodic heartbeats
                if time.time() - (connection.last_heartbeat or 0) > self.heartbeat_interval:
                    await self._send_heartbeat(connection)

                # Limit monitoring time per connection attempt
                if time.time() - start_time > 300:  # 5 minutes
                    break

        except Exception as e:
            logger.error(f"Error monitoring {connection.exchange} data feed: {e}")

        # Calculate message frequency
        duration = time.time() - start_time
        if duration > 0:
            connection.data_quality.message_frequency_hz = message_count / duration

    async def _validate_message(self, connection: ExchangeConnection, message: str) -> bool:
        """Validate incoming message format and content"""
        try:
            data = json.loads(message)
            connection.data_quality.total_messages += 1

            # Exchange-specific validation
            if connection.exchange == 'binance':
                return self._validate_binance_message(data)
            elif connection.exchange == 'coinbase':
                return self._validate_coinbase_message(data)
            elif connection.exchange == 'kraken':
                return self._validate_kraken_message(data)
            else:
                return False

        except json.JSONDecodeError:
            connection.data_quality.schema_validation_errors += 1
            return False
        except Exception as e:
            logger.error(f"Error validating message from {connection.exchange}: {e}")
            return False

    def _validate_binance_message(self, data: Dict[str, Any]) -> bool:
        """Validate Binance WebSocket message"""
        try:
            # Check for required fields in ticker data
            required_fields = ['s', 'c', 'v', 'P', 'E']
            if not all(field in data for field in required_fields):
                return False

            # Validate data types
            if not isinstance(data['c'], (int, float)):  # price
                return False
            if not isinstance(data['v'], (int, float)):  # volume
                return False

            # Check for reasonable price/volume values
            if data['c'] <= 0 or data['v'] < 0:
                return False

            return True

        except Exception:
            return False

    def _validate_coinbase_message(self, data: Dict[str, Any]) -> bool:
        """Validate Coinbase WebSocket message"""
        try:
            # Check message type
            if data.get('type') != 'ticker':
                return True  # Non-ticker messages are OK

            # Check for required fields
            required_fields = ['product_id', 'price', 'volume_24h']
            if not all(field in data for field in required_fields):
                return False

            # Validate data types
            if not isinstance(data['price'], str):
                return False
            if not isinstance(data['volume_24h'], str):
                return False

            # Convert and validate numeric values
            try:
                price = float(data['price'])
                volume = float(data['volume_24h'])
                if price <= 0 or volume < 0:
                    return False
            except ValueError:
                return False

            return True

        except Exception:
            return False

    def _validate_kraken_message(self, data: Dict[str, Any]) -> bool:
        """Validate Kraken WebSocket message"""
        try:
            # Kraken ticker data comes as arrays
            if not isinstance(data, list) or len(data) < 4:
                return False

            ticker_data = data[1]
            if not isinstance(ticker_data, dict):
                return False

            # Check for required ticker fields
            required_fields = ['c', 'v', 'p', 't']
            if not all(field in ticker_data for field in required_fields):
                return False

            # Validate arrays contain proper data
            if not all(isinstance(ticker_data[field], list) and len(ticker_data[field]) >= 1
                      for field in ['c', 'v', 'p']):
                return False

            # Check numeric values
            try:
                price = float(ticker_data['c'][0])
                volume = float(ticker_data['v'][1])  # 24h volume
                if price <= 0 or volume < 0:
                    return False
            except (ValueError, IndexError):
                return False

            return True

        except Exception:
            return False

    async def _monitor_connections(self):
        """Monitor overall connection health"""
        while self.is_running:
            try:
                await self._update_connection_metrics()
                await self._log_connection_status()
                await asyncio.sleep(60)  # Update every minute

            except Exception as e:
                logger.error(f"Error in connection monitoring: {e}")
                await asyncio.sleep(60)

    async def _update_connection_metrics(self):
        """Update connection uptime and performance metrics"""
        current_time = time.time()

        for connection in self.connections.values():
            # Calculate uptime percentage
            if connection.metrics.connection_start_time:
                total_time = current_time - connection.metrics.connection_start_time
                connected_time = total_time if connection.is_connected else 0
                connection.metrics.uptime_percentage = (connected_time / total_time) * 100

            # Calculate average latency from samples
            if connection.metrics.latency_samples:
                connection.metrics.average_latency_ms = statistics.mean(connection.metrics.latency_samples)
                connection.metrics.min_latency_ms = min(connection.metrics.latency_samples)
                connection.metrics.max_latency_ms = max(connection.metrics.latency_samples)

    async def _log_connection_status(self):
        """Log current connection status"""
        status_summary = []

        for connection in self.connections.values():
            status = "🟢" if connection.is_connected else "🔴"
            uptime = f"{connection.metrics.uptime_percentage:.1f}%"
            messages = connection.metrics.messages_received
            valid_pct = (connection.data_quality.valid_messages /
                        max(connection.data_quality.total_messages, 1)) * 100

            status_summary.append(
                f"{connection.exchange}: {status} {uptime} uptime, "
                f"{messages} msgs, {valid_pct:.1f}% valid"
            )

        logger.info("WebSocket Status: " + " | ".join(status_summary))

    def get_validation_report(self) -> Dict[str, Any]:
        """Generate comprehensive validation report"""
        report = {
            'timestamp': datetime.now().isoformat(),
            'overall_status': 'healthy',
            'connections': {},
            'summary': {
                'total_connections': len(self.connections),
                'active_connections': sum(1 for c in self.connections.values() if c.is_connected),
                'total_messages_received': 0,
                'total_valid_messages': 0,
                'average_uptime': 0.0
            }
        }

        total_uptime = 0.0

        for exchange, connection in self.connections.items():
            conn_report = {
                'is_connected': connection.is_connected,
                'uptime_percentage': connection.metrics.uptime_percentage,
                'messages_received': connection.metrics.messages_received,
                'messages_sent': connection.metrics.messages_sent,
                'valid_messages': connection.data_quality.valid_messages,
                'invalid_messages': connection.data_quality.invalid_messages,
                'message_frequency_hz': connection.data_quality.message_frequency_hz,
                'average_latency_ms': connection.metrics.average_latency_ms,
                'data_quality_score': self._calculate_data_quality_score(connection)
            }

            report['connections'][exchange] = conn_report

            # Update summary
            report['summary']['total_messages_received'] += connection.metrics.messages_received
            report['summary']['total_valid_messages'] += connection.data_quality.valid_messages
            total_uptime += connection.metrics.uptime_percentage

        report['summary']['average_uptime'] = total_uptime / len(self.connections)

        # Determine overall status
        active_pct = report['summary']['active_connections'] / report['summary']['total_connections']
        valid_pct = (report['summary']['total_valid_messages'] /
                    max(report['summary']['total_messages_received'], 1))

        if active_pct < 0.5 or valid_pct < 0.8:
            report['overall_status'] = 'critical'
        elif active_pct < 0.8 or valid_pct < 0.95:
            report['overall_status'] = 'warning'
        else:
            report['overall_status'] = 'healthy'

        return report

    def _calculate_data_quality_score(self, connection: ExchangeConnection) -> float:
        """Calculate data quality score (0-100)"""
        try:
            metrics = connection.data_quality

            if metrics.total_messages == 0:
                return 0.0

            # Validity score (70% weight)
            validity_score = (metrics.valid_messages / metrics.total_messages) * 70

            # Freshness score (20% weight) - lower staleness = higher score
            staleness_rate = metrics.stale_messages / max(metrics.total_messages, 1)
            freshness_score = (1.0 - min(staleness_rate, 1.0)) * 20

            # Consistency score (10% weight) - based on message frequency stability
            frequency_score = min(metrics.message_frequency_hz / 10.0, 1.0) * 10  # Expect ~10 Hz

            return validity_score + freshness_score + frequency_score

        except Exception:
            return 0.0

    async def test_exchange_connectivity(self, exchange: str) -> Dict[str, Any]:
        """Test connectivity to a specific exchange"""
        if exchange not in self.connections:
            return {'error': f'Exchange {exchange} not configured'}

        connection = self.connections[exchange]

        try:
            start_time = time.time()

            async with websockets.connect(connection.url, extra_headers={'User-Agent': 'SovereignForge/1.0'}) as ws:
                connection_time = time.time() - start_time

                # Test ping/pong
                ping_start = time.time()
                await ws.ping()
                pong_time = time.time() - ping_start

                return {
                    'exchange': exchange,
                    'connection_successful': True,
                    'connection_time_ms': connection_time * 1000,
                    'ping_time_ms': pong_time * 1000,
                    'url': connection.url
                }

        except Exception as e:
            return {
                'exchange': exchange,
                'connection_successful': False,
                'error': str(e),
                'url': connection.url
            }

# Global validator instance
_validator = None

def get_websocket_validator() -> WebSocketValidator:
    """Get global WebSocket validator instance"""
    global _validator
    if _validator is None:
        _validator = WebSocketValidator()
    return _validator

async def start_websocket_validation():
    """Start WebSocket validation"""
    validator = get_websocket_validator()
    await validator.start_validation()

async def stop_websocket_validation():
    """Stop WebSocket validation"""
    validator = get_websocket_validator()
    await validator.stop_validation()

def get_validation_report() -> Dict[str, Any]:
    """Get current validation report"""
    validator = get_websocket_validator()
    return validator.get_validation_report()

async def test_exchange_connectivity(exchange: str) -> Dict[str, Any]:
    """Test connectivity to specific exchange"""
    validator = get_websocket_validator()
    return await validator.test_exchange_connectivity(exchange)
