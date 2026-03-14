#!/usr/bin/env python3
"""
SovereignForge WebSocket Connector
Real-time cryptocurrency data streaming from multiple exchanges
"""

import asyncio
import json
import logging
import ssl
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import aiohttp
import websockets

logger = logging.getLogger(__name__)

@dataclass
class CircuitBreakerState:
    CLOSED = "closed"      # Normal operation
    OPEN = "open"          # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing if service recovered

class CircuitBreaker:
    """Circuit breaker for WebSocket connections"""

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0, expected_exception: Exception = Exception):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.expected_exception = expected_exception
        self.failure_count = 0
        self.last_failure_time = None
        self.state = CircuitBreakerState.CLOSED

    def _can_attempt_reset(self) -> bool:
        """Check if enough time has passed to attempt reset"""
        if self.last_failure_time is None:
            return True
        return time.time() - self.last_failure_time >= self.recovery_timeout

    def _record_success(self):
        """Record successful operation"""
        self.failure_count = 0
        self.state = CircuitBreakerState.CLOSED

    def _record_failure(self):
        """Record failed operation"""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            self.state = CircuitBreakerState.OPEN
            logger.warning(f"Circuit breaker opened after {self.failure_count} failures")

    async def call(self, func, *args, **kwargs):
        """Execute function with circuit breaker protection"""
        if self.state == CircuitBreakerState.OPEN:
            if self._can_attempt_reset():
                self.state = CircuitBreakerState.HALF_OPEN
                logger.info("Circuit breaker half-open, testing service")
            else:
                raise Exception("Circuit breaker is OPEN")

        try:
            result = await func(*args, **kwargs)
            if self.state == CircuitBreakerState.HALF_OPEN:
                self._record_success()
                logger.info("Circuit breaker reset to CLOSED")
            return result
        except self.expected_exception as e:
            self._record_failure()
            raise e

@dataclass
class MarketData:
    """Real-time market data structure"""
    exchange: str
    pair: str
    timestamp: float
    price: float
    volume: float
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float
    order_book: Dict[str, List[List[float]]] = None

class WebSocketConnector:
    """Base WebSocket connector with reconnection logic"""

    def __init__(self, exchange_name: str, reconnect_delay: float = 1.0, max_reconnect_attempts: int = 10):
        self.exchange_name = exchange_name
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_attempts = max_reconnect_attempts
        self.websocket = None
        self.is_connected = False
        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30.0  # seconds

    async def connect(self, uri: str) -> bool:
        """Establish WebSocket connection with retry logic and multiple strategies"""
        for attempt in range(self.max_reconnect_attempts):
            try:
                logger.info(f"Connecting to {self.exchange_name} (attempt {attempt + 1})")

                # Try different SSL configurations
                connection_strategies = [
                    # Strategy 1: Default SSL
                    {
                        'ssl': True,
                        'ping_interval': 20,
                        'ping_timeout': 10,
                        'close_timeout': 5
                    },
                    # Strategy 2: Custom SSL context
                    {
                        'ssl': ssl.create_default_context(),
                        'ping_interval': 20,
                        'ping_timeout': 10,
                        'close_timeout': 5
                    },
                    # Strategy 3: Retry with default SSL (always use SSL for security)
                    {
                        'ssl': True,  # Always use SSL for security
                        'ping_interval': 20,
                        'ping_timeout': 10,
                        'close_timeout': 5
                    }
                ]

                for strategy_idx, ssl_config in enumerate(connection_strategies):
                    try:
                        logger.debug(f"Trying connection strategy {strategy_idx + 1}")
                        self.websocket = await asyncio.wait_for(
                            websockets.connect(uri, **ssl_config),
                            timeout=10.0
                        )
                        self.is_connected = True
                        self.reconnect_attempts = 0
                        logger.info(f"Successfully connected to {self.exchange_name} using strategy {strategy_idx + 1}")
                        return True
                    except Exception as strategy_error:
                        logger.debug(f"Strategy {strategy_idx + 1} failed: {strategy_error}")
                        continue

                # If all strategies failed, raise the last error
                raise Exception("All connection strategies failed")

            except Exception as e:
                logger.warning(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt < self.max_reconnect_attempts - 1:
                    await asyncio.sleep(self.reconnect_delay * (2 ** attempt))  # Exponential backoff
                else:
                    logger.error(f"Failed to connect to {self.exchange_name} after {self.max_reconnect_attempts} attempts")
                    return False
        return False

    async def disconnect(self):
        """Close WebSocket connection"""
        if self.websocket:
            await self.websocket.close()
            self.is_connected = False
            logger.info(f"Disconnected from {self.exchange_name}")

    async def send(self, message: str):
        """Send message through WebSocket"""
        if self.websocket and self.is_connected:
            await self.websocket.send(message)

    async def receive(self) -> Optional[str]:
        """Receive message from WebSocket"""
        if self.websocket and self.is_connected:
            try:
                message = await asyncio.wait_for(self.websocket.recv(), timeout=30.0)
                self.last_heartbeat = time.time()
                return message
            except asyncio.TimeoutError:
                logger.warning(f"Timeout receiving from {self.exchange_name}")
                return None
            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Connection closed by {self.exchange_name}")
                self.is_connected = False
                return None
        return None

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for WebSocket connection"""
        return {
            'User-Agent': 'SovereignForge/1.0',
            'Accept': 'application/json'
        }

    async def check_connection(self) -> bool:
        """Check if connection is still alive"""
        if not self.is_connected:
            return False

        # Check heartbeat
        if time.time() - self.last_heartbeat > self.heartbeat_interval * 2:
            logger.warning(f"Heartbeat timeout for {self.exchange_name}")
            self.is_connected = False
            return False

        return True

class BinanceWebSocket(WebSocketConnector):
    """Binance WebSocket connector for real-time data"""

    BASE_URI = "wss://stream.binance.com:9443/ws/"

    def __init__(self):
        super().__init__("binance")
        self.subscribed_pairs = set()

    def get_stream_uri(self, streams: List[str]) -> str:
        """Get WebSocket URI for multiple streams"""
        if len(streams) == 1:
            return f"{self.BASE_URI}{streams[0]}"
        else:
            streams_param = "/".join(streams)
            return f"{self.BASE_URI}{streams_param}"

    def get_ticker_stream(self, pair: str) -> str:
        """Get ticker stream name for a pair"""
        return f"{pair.lower()}@ticker"

    def get_depth_stream(self, pair: str, depth: int = 20) -> str:
        """Get order book depth stream name"""
        return f"{pair.lower()}@depth{depth}"

    async def subscribe_ticker(self, pairs: List[str]):
        """Subscribe to ticker data for multiple pairs"""
        streams = [self.get_ticker_stream(pair) for pair in pairs]
        uri = self.get_stream_uri(streams)

        if await self.connect(uri):
            logger.info(f"Subscribed to ticker data for {len(pairs)} pairs on Binance")
            self.subscribed_pairs.update(pairs)
            return True
        return False

    async def subscribe_orderbook(self, pairs: List[str], depth: int = 20):
        """Subscribe to order book data"""
        streams = [self.get_depth_stream(pair, depth) for pair in pairs]
        uri = self.get_stream_uri(streams)

        if await self.connect(uri):
            logger.info(f"Subscribed to order book data for {len(pairs)} pairs on Binance")
            return True
        return False

    def parse_ticker_message(self, message: str) -> Optional[MarketData]:
        """Parse Binance ticker message"""
        try:
            data = json.loads(message)
            if 'stream' in data and '@ticker' in data['stream']:
                ticker_data = data['data']
                pair = ticker_data['s'].replace('USDC', '/USDC')

                return MarketData(
                    exchange='binance',
                    pair=pair,
                    timestamp=ticker_data['E'] / 1000,  # Convert ms to seconds
                    price=float(ticker_data['c']),  # Last price
                    volume=float(ticker_data['v']),  # Volume
                    bid_price=float(ticker_data['b']),  # Best bid
                    ask_price=float(ticker_data['a']),  # Best ask
                    bid_volume=float(ticker_data['B']),  # Bid volume
                    ask_volume=float(ticker_data['A'])   # Ask volume
                )
        except Exception as e:
            logger.error(f"Error parsing Binance ticker message: {e}")
        return None

    def parse_depth_message(self, message: str) -> Optional[Dict]:
        """Parse Binance order book depth message"""
        try:
            data = json.loads(message)
            if 'stream' in data and '@depth' in data['stream']:
                depth_data = data['data']
                pair = depth_data['s'].replace('USDC', '/USDC')

                return {
                    'exchange': 'binance',
                    'pair': pair,
                    'timestamp': depth_data['E'] / 1000,
                    'bids': [[float(price), float(qty)] for price, qty in depth_data['b']],
                    'asks': [[float(price), float(qty)] for price, qty in depth_data['a']]
                }
        except Exception as e:
            logger.error(f"Error parsing Binance depth message: {e}")
        return None

class CoinbaseWebSocket(WebSocketConnector):
    """Coinbase Pro WebSocket connector"""

    BASE_URI = "wss://ws-feed.pro.coinbase.com"

    def __init__(self):
        super().__init__("coinbase")
        self.subscribed_pairs = set()

    async def subscribe_ticker(self, pairs: List[str]):
        """Subscribe to Coinbase ticker data"""
        subscribe_message = {
            "type": "subscribe",
            "product_ids": pairs,
            "channels": ["ticker"]
        }

        if await self.connect(self.BASE_URI):
            await self.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to ticker data for {len(pairs)} pairs on Coinbase")
            self.subscribed_pairs.update(pairs)
            return True
        return False

    def parse_ticker_message(self, message: str) -> Optional[MarketData]:
        """Parse Coinbase ticker message"""
        try:
            data = json.loads(message)
            if data.get('type') == 'ticker':
                return MarketData(
                    exchange='coinbase',
                    pair=data['product_id'],
                    timestamp=time.time(),
                    price=float(data['price']),
                    volume=float(data.get('volume_24h', 0)),
                    bid_price=float(data['best_bid']),
                    ask_price=float(data['best_ask']),
                    bid_volume=0.0,  # Not provided in ticker
                    ask_volume=0.0   # Not provided in ticker
                )
        except Exception as e:
            logger.error(f"Error parsing Coinbase ticker message: {e}")
        return None

class KrakenWebSocket(WebSocketConnector):
    """Kraken WebSocket connector"""

    BASE_URI = "wss://ws.kraken.com"

    def __init__(self):
        super().__init__("kraken")
        self.subscribed_pairs = set()

    async def subscribe_ticker(self, pairs: List[str]):
        """Subscribe to Kraken ticker data"""
        # Convert pairs to Kraken format (XBT instead of BTC, etc.)
        kraken_pairs = []
        for pair in pairs:
            if pair.startswith('BTC'):
                kraken_pairs.append(pair.replace('BTC', 'XBT'))
            else:
                kraken_pairs.append(pair)

        subscribe_message = {
            "event": "subscribe",
            "pair": kraken_pairs,
            "subscription": {"name": "ticker"}
        }

        if await self.connect(self.BASE_URI):
            await self.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to ticker data for {len(pairs)} pairs on Kraken")
            self.subscribed_pairs.update(pairs)
            return True
        return False

    def parse_ticker_message(self, message: str) -> Optional[MarketData]:
        """Parse Kraken ticker message"""
        try:
            data = json.loads(message)
            if isinstance(data, list) and len(data) >= 4:
                channel_id, ticker_data, channel_name, pair = data

                if channel_name == 'ticker':
                    # Convert back to standard format
                    standard_pair = pair.replace('XBT', 'BTC')

                    return MarketData(
                        exchange='kraken',
                        pair=standard_pair,
                        timestamp=time.time(),
                        price=float(ticker_data['c'][0]),  # Last price
                        volume=float(ticker_data['v'][1]),  # Volume
                        bid_price=float(ticker_data['b'][0]),  # Best bid
                        ask_price=float(ticker_data['a'][0]),  # Best ask
                        bid_volume=float(ticker_data['b'][2]),  # Bid volume
                        ask_volume=float(ticker_data['a'][2])   # Ask volume
                    )
        except Exception as e:
            logger.error(f"Error parsing Kraken ticker message: {e}")
        return None

class KuCoinWebSocket(WebSocketConnector):
    """KuCoin WebSocket connector"""

    BASE_URI = "wss://ws-api.kucoin.com/endpoint"

    def __init__(self):
        super().__init__("kucoin")
        self.subscribed_pairs = set()
        self.token = None

    async def connect(self, uri: str) -> bool:
        """Override connect to get KuCoin token first"""
        try:
            # Get WebSocket token from KuCoin
            async with aiohttp.ClientSession() as session:
                async with session.post('https://api.kucoin.com/api/v1/bullet-public') as response:
                    if response.status == 200:
                        token_data = await response.json()
                        self.token = token_data['data']['token']
                        token_uri = f"wss://ws-api.kucoin.com/endpoint?token={self.token}"
                        return await super().connect(token_uri)
        except Exception as e:
            logger.error(f"Failed to get KuCoin token: {e}")

        return False

    async def subscribe_ticker(self, pairs: List[str]):
        """Subscribe to KuCoin ticker data"""
        subscribe_message = {
            "id": str(int(time.time() * 1000)),
            "type": "subscribe",
            "topic": "/market/ticker:" + ",".join(pairs),
            "privateChannel": False,
            "response": True
        }

        if await self.connect(""):  # URI handled in connect method
            await self.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to ticker data for {len(pairs)} pairs on KuCoin")
            self.subscribed_pairs.update(pairs)
            return True
        return False

    def parse_ticker_message(self, message: str) -> Optional[MarketData]:
        """Parse KuCoin ticker message"""
        try:
            data = json.loads(message)
            if data.get('type') == 'message' and 'topic' in data:
                if '/market/ticker:' in data['topic']:
                    ticker_data = data['data']

                    return MarketData(
                        exchange='kucoin',
                        pair=ticker_data['symbol'],
                        timestamp=time.time(),
                        price=float(ticker_data['price']),
                        volume=float(ticker_data['vol']),
                        bid_price=float(ticker_data['bestBid']),
                        ask_price=float(ticker_data['bestAsk']),
                        bid_volume=float(ticker_data['bestBidSize']),
                        ask_volume=float(ticker_data['bestAskSize'])
                    )
        except Exception as e:
            logger.error(f"Error parsing KuCoin ticker message: {e}")
        return None

class OKXWebSocket(WebSocketConnector):
    """OKX WebSocket connector"""

    BASE_URI = "wss://wsaws.okx.com:8443/ws/v5/public"

    def __init__(self):
        super().__init__("okx")
        self.subscribed_pairs = set()

    async def subscribe_ticker(self, pairs: List[str]):
        """Subscribe to OKX ticker data"""
        # Convert pairs to OKX format
        okx_pairs = []
        for pair in pairs:
            # OKX uses format like "BTC-USDC"
            okx_pair = pair.replace('/', '-')
            okx_pairs.append(okx_pair)

        subscribe_message = {
            "op": "subscribe",
            "args": [{"channel": "tickers", "instId": pair} for pair in okx_pairs]
        }

        if await self.connect(self.BASE_URI):
            await self.send(json.dumps(subscribe_message))
            logger.info(f"Subscribed to ticker data for {len(pairs)} pairs on OKX")
            self.subscribed_pairs.update(pairs)
            return True
        return False

    def parse_ticker_message(self, message: str) -> Optional[MarketData]:
        """Parse OKX ticker message"""
        try:
            data = json.loads(message)
            if data.get('event') == 'subscribe':
                return None  # Skip subscription confirmations

            if 'arg' in data and data['arg'].get('channel') == 'tickers':
                ticker_data = data['data'][0]

                # Convert back to standard format
                pair = ticker_data['instId'].replace('-', '/')

                return MarketData(
                    exchange='okx',
                    pair=pair,
                    timestamp=time.time(),
                    price=float(ticker_data['last']),
                    volume=float(ticker_data['vol24h']),
                    bid_price=float(ticker_data['bidPx']),
                    ask_price=float(ticker_data['askPx']),
                    bid_volume=float(ticker_data['bidSz']),
                    ask_volume=float(ticker_data['askSz'])
                )
        except Exception as e:
            logger.error(f"Error parsing OKX ticker message: {e}")
        return None

class MultiExchangeConnector:
    """Unified connector for multiple exchanges"""

    def __init__(self):
        self.connectors = {
            'binance': BinanceWebSocket(),
            'coinbase': CoinbaseWebSocket(),
            'kraken': KrakenWebSocket(),
            'kucoin': KuCoinWebSocket(),
            'okx': OKXWebSocket()
        }
        self.data_callbacks = []
        self.is_running = False

    def add_data_callback(self, callback: Callable[[MarketData], None]):
        """Add callback for processing market data"""
        self.data_callbacks.append(callback)

    async def connect_all_exchanges(self, pairs: List[str]) -> bool:
        """Connect to all exchanges for the specified pairs"""
        success_count = 0

        for exchange_name, connector in self.connectors.items():
            try:
                logger.info(f"Connecting to {exchange_name}...")
                if await connector.subscribe_ticker(pairs):
                    success_count += 1
                    logger.info(f"Successfully connected to {exchange_name}")
                else:
                    logger.error(f"Failed to connect to {exchange_name}")
            except Exception as e:
                logger.error(f"Error connecting to {exchange_name}: {e}")

        logger.info(f"Connected to {success_count}/{len(self.connectors)} exchanges")
        return success_count > 0

    async def start_data_stream(self):
        """Start streaming data from all connected exchanges"""
        self.is_running = True
        tasks = []

        for exchange_name, connector in self.connectors.items():
            if connector.is_connected:
                task = asyncio.create_task(self._stream_exchange_data(exchange_name, connector))
                tasks.append(task)

        if tasks:
            logger.info("Starting data streaming from all exchanges")
            await asyncio.gather(*tasks, return_exceptions=True)
        else:
            logger.warning("No exchanges connected for data streaming")

    async def _stream_exchange_data(self, exchange_name: str, connector: WebSocketConnector):
        """Stream data from a specific exchange"""
        logger.info(f"Starting data stream for {exchange_name}")

        while self.is_running and connector.is_connected:
            try:
                message = await connector.receive()
                if message:
                    market_data = None

                    # Parse message based on exchange
                    if exchange_name == 'binance':
                        market_data = connector.parse_ticker_message(message)
                    elif exchange_name == 'coinbase':
                        market_data = connector.parse_ticker_message(message)
                    elif exchange_name == 'kraken':
                        market_data = connector.parse_ticker_message(message)
                    elif exchange_name == 'kucoin':
                        market_data = connector.parse_ticker_message(message)
                    elif exchange_name == 'okx':
                        market_data = connector.parse_ticker_message(message)

                    # Call callbacks with parsed data
                    if market_data:
                        for callback in self.data_callbacks:
                            try:
                                callback(market_data)
                            except Exception as e:
                                logger.error(f"Error in data callback: {e}")

                # Small delay to prevent overwhelming the system
                await asyncio.sleep(0.01)

            except Exception as e:
                logger.error(f"Error streaming data from {exchange_name}: {e}")
                await asyncio.sleep(1.0)

        logger.info(f"Stopped data stream for {exchange_name}")

    async def stop(self):
        """Stop all connections and streaming"""
        logger.info("Stopping all exchange connections")
        self.is_running = False

        for connector in self.connectors.values():
            await connector.disconnect()

    async def get_connection_status(self) -> Dict[str, bool]:
        """Get connection status for all exchanges"""
        status = {}
        for exchange_name, connector in self.connectors.items():
            status[exchange_name] = await connector.check_connection()
        return status

# Utility functions
async def test_exchange_connections():
    """Test connections to all exchanges"""
    connector = MultiExchangeConnector()
    pairs = ['BTC/USDC', 'ETH/USDC']

    print("Testing exchange connections...")
    success = await connector.connect_all_exchanges(pairs)

    if success:
        print("✅ Successfully connected to exchanges")

        # Test data streaming for 10 seconds
        print("Testing data streaming for 10 seconds...")

        data_count = {'total': 0}

        def count_data(data: MarketData):
            data_count['total'] += 1
            if data_count['total'] % 10 == 0:
                print(f"Received {data_count['total']} data points...")

        connector.add_data_callback(count_data)

        try:
            stream_task = asyncio.create_task(connector.start_data_stream())
            await asyncio.wait_for(asyncio.shield(stream_task), timeout=10.0)
        except asyncio.TimeoutError:
            print("✅ Data streaming test completed")

        await connector.stop()
        print(f"Total data points received: {data_count['total']}")
    else:
        print("❌ Failed to connect to any exchanges")

if __name__ == "__main__":
    # Test the WebSocket connections
    asyncio.run(test_exchange_connections())
