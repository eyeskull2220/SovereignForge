#!/usr/bin/env python3
"""
SovereignForge Live Data Fetcher
Real-time market data aggregation from public WebSocket APIs
MiCA-compliant pairs only (USDC/RLUSD)
"""

import asyncio
import json
import logging
import websockets
import time
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from datetime import datetime
import gzip
import zlib

# Import core config for whitelist compliance
from core import config

logger = logging.getLogger(__name__)

@dataclass
class TickerData:
    """Real-time ticker data structure"""
    exchange: str
    pair: str
    timestamp: float
    price: float
    volume_24h: float
    price_change_24h: float
    price_change_pct_24h: float
    bid_price: float
    ask_price: float
    bid_volume: float
    ask_volume: float

class ExchangeConnector:
    """Base class for exchange WebSocket connections"""

    def __init__(self, exchange_name: str, ws_url: str, pairs: List[str]):
        self.exchange_name = exchange_name
        self.ws_url = ws_url
        self.pairs = pairs
        self.connection = None
        self.is_connected = False
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30  # seconds
        self.reconnect_delay = 5  # seconds
        self.max_reconnect_attempts = 10
        self.reconnect_attempts = 0

    async def connect(self):
        """Establish WebSocket connection"""
        try:
            logger.info(f"Connecting to {self.exchange_name} WebSocket...")
            self.connection = await websockets.connect(
                self.ws_url,
                compression=None
            )
            self.is_connected = True
            self.reconnect_attempts = 0
            logger.info(f"✅ Connected to {self.exchange_name}")

            # Send subscription message
            await self.subscribe()

        except Exception as e:
            logger.error(f"Failed to connect to {self.exchange_name}: {e}")
            self.is_connected = False
            await self.handle_reconnect()

    async def disconnect(self):
        """Close WebSocket connection"""
        if self.connection:
            await self.connection.close()
            self.is_connected = False
            logger.info(f"Disconnected from {self.exchange_name}")

    async def subscribe(self):
        """Send subscription message (override in subclasses)"""
        pass

    def get_headers(self) -> Dict[str, str]:
        """Get headers for connection (override if needed)"""
        return {}

    async def handle_reconnect(self):
        """Handle reconnection logic"""
        if self.reconnect_attempts >= self.max_reconnect_attempts:
            logger.error(f"Max reconnection attempts reached for {self.exchange_name}")
            return

        self.reconnect_attempts += 1
        delay = self.reconnect_delay * (2 ** (self.reconnect_attempts - 1))  # Exponential backoff
        logger.info(f"Reconnecting to {self.exchange_name} in {delay}s (attempt {self.reconnect_attempts})")
        await asyncio.sleep(delay)
        await self.connect()

    async def send_heartbeat(self):
        """Send heartbeat if needed"""
        pass

class BinanceConnector(ExchangeConnector):
    """Binance WebSocket connector"""

    def __init__(self, pairs: List[str]):
        # Use combined stream URL for multiple pairs
        streams = []
        for pair in pairs:
            binance_symbol = pair.replace('/', '').lower()
            streams.append(f"{binance_symbol}@ticker")

        combined_stream = "/".join(streams)
        ws_url = f"wss://stream.binance.com:9443/stream?streams={combined_stream}"

        super().__init__(
            "binance",
            ws_url,
            pairs
        )

        logger.info(f"Using combined stream URL: {ws_url}")

    async def subscribe(self):
        """No subscription needed for combined streams - data flows immediately"""
        logger.info("Connected to Binance combined stream - data will flow automatically")

    def parse_message(self, message: str) -> Optional[TickerData]:
        """Parse Binance ticker message"""
        try:
            data = json.loads(message)

            # Handle subscription confirmation
            if 'result' in data and data.get('id') == 1:
                logger.info("Binance subscription confirmed")
                return None

            # Handle ticker data
            if 'stream' in data and 'data' in data:
                ticker = data['data']
            elif 's' in data:  # Direct ticker data
                ticker = data
            else:
                return None

            symbol = ticker.get('s')
            if not symbol:
                return None

            # Convert Binance symbol back to our format
            if symbol.endswith('USDC'):
                pair = f"{symbol[:-4]}/USDC"
            elif symbol.endswith('USDT'):
                pair = f"{symbol[:-4]}/USDT"
            else:
                return None  # Skip non-USDC pairs

            return TickerData(
                exchange=self.exchange_name,
                pair=pair,
                timestamp=ticker.get('E', time.time() * 1000) / 1000,  # Convert ms to seconds
                price=float(ticker.get('c', 0)),
                volume_24h=float(ticker.get('v', 0)),
                price_change_24h=float(ticker.get('p', 0)),
                price_change_pct_24h=float(ticker.get('P', 0)),
                bid_price=float(ticker.get('b', 0)),
                ask_price=float(ticker.get('a', 0)),
                bid_volume=float(ticker.get('B', 0)),
                ask_volume=float(ticker.get('A', 0))
            )

        except Exception as e:
            logger.error(f"Error parsing Binance message: {e}")
            logger.error(f"Message content: {message[:200]}...")
            return None

class CoinbaseConnector(ExchangeConnector):
    """Coinbase WebSocket connector"""

    def __init__(self, pairs: List[str]):
        super().__init__(
            "coinbase",
            "wss://ws-feed.pro.coinbase.com",
            pairs
        )

    async def subscribe(self):
        """Subscribe to Coinbase ticker feeds"""
        # Coinbase uses different pair format (e.g., XRP-USDC)
        coinbase_pairs = [pair.replace('/', '-') for pair in self.pairs]

        subscription = {
            "type": "subscribe",
            "product_ids": coinbase_pairs,
            "channels": ["ticker"]
        }

        await self.connection.send(json.dumps(subscription))
        logger.info(f"Subscribed to {len(coinbase_pairs)} Coinbase pairs")

    def parse_message(self, message: str) -> Optional[TickerData]:
        """Parse Coinbase ticker message"""
        try:
            data = json.loads(message)

            if data.get('type') != 'ticker':
                return None

            product_id = data['product_id']

            # Convert Coinbase format back to our format
            if '-USDC' in product_id:
                pair = product_id.replace('-', '/')
            else:
                return None  # Skip non-USDC pairs

            return TickerData(
                exchange=self.exchange_name,
                pair=pair,
                timestamp=time.time(),
                price=float(data['price']),
                volume_24h=float(data.get('volume_24', 0)),
                price_change_24h=0.0,  # Coinbase doesn't provide 24h change
                price_change_pct_24h=0.0,
                bid_price=float(data.get('best_bid', 0)),
                ask_price=float(data.get('best_ask', 0)),
                bid_volume=float(data.get('best_bid_size', 0)),
                ask_volume=float(data.get('best_ask_size', 0))
            )

        except Exception as e:
            logger.error(f"Error parsing Coinbase message: {e}")
            return None

class LiveDataFetcher:
    """
    Multi-exchange live data fetcher using public WebSocket APIs
    Aggregates real-time ticker data for MiCA-compliant pairs
    """

    def __init__(self):
        # Generate MiCA-compliant pairs from core config whitelist
        self.mica_pairs = self._generate_whitelist_pairs()

        # Exchange connectors
        self.connectors: Dict[str, ExchangeConnector] = {}
        self.tasks: List[asyncio.Task] = []

        # Data callbacks
        self.data_callbacks: List[Callable] = []

        # Statistics
        self.stats = {
            'messages_received': 0,
            'tickers_processed': 0,
            'errors': 0,
            'start_time': time.time()
        }

        # Initialize connectors
        self._init_connectors()

        logger.info(f"LiveDataFetcher initialized for {len(self.mica_pairs)} MiCA pairs")

    def _generate_whitelist_pairs(self) -> List[str]:
        """Generate MiCA-compliant pairs from core config whitelist"""
        pairs = []

        # Generate crypto/USDC pairs
        for coin in config.WHITELIST_COINS:
            if coin != 'USDC' and coin != 'RLUSD':  # Skip stablecoins as base
                pairs.append(f"{coin}/USDC")

        # Generate crypto/RLUSD pairs (limited availability)
        for coin in ['XRP', 'XLM', 'ADA']:  # Only these have RLUSD pairs
            if coin in config.WHITELIST_COINS:
                pairs.append(f"{coin}/RLUSD")

        return pairs

    def _init_connectors(self):
        """Initialize exchange connectors"""

        # Filter pairs available on Binance (most reliable for USDC pairs)
        binance_available_coins = {
            'XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'ONDO', 'VET'
            # Note: XDC/USDC not available on Binance
        }

        # Get USDC pairs that are available on Binance
        binance_pairs = [
            pair for pair in self.mica_pairs
            if pair.endswith('/USDC') and pair.split('/')[0] in binance_available_coins
        ]

        # Binance connector (most reliable for USDC pairs)
        if binance_pairs:
            self.connectors['binance'] = BinanceConnector(binance_pairs)

        # Skip Coinbase for now - requires authentication or has geo restrictions
        # Coinbase connector (good USDC support) - DISABLED due to auth requirements
        # coinbase_pairs = [p for p in self.mica_pairs if p.endswith('/USDC')]
        # if coinbase_pairs:
        #     self.connectors['coinbase'] = CoinbaseConnector(coinbase_pairs)

        logger.info(f"Initialized {len(self.connectors)} exchange connectors with {len(binance_pairs)} USDC pairs")

    def add_data_callback(self, callback: Callable):
        """Add callback for ticker data"""
        self.data_callbacks.append(callback)

    async def start(self):
        """Start all WebSocket connections"""
        logger.info("Starting live data fetcher...")

        for name, connector in self.connectors.items():
            task = asyncio.create_task(self._run_connector(connector))
            self.tasks.append(task)

        # Start heartbeat monitor
        heartbeat_task = asyncio.create_task(self._monitor_heartbeats())
        self.tasks.append(heartbeat_task)

        logger.info(f"✅ Live data fetcher started with {len(self.connectors)} exchanges")

    async def stop(self):
        """Stop all connections"""
        logger.info("Stopping live data fetcher...")

        # Cancel all tasks
        for task in self.tasks:
            task.cancel()

        # Close all connections
        for connector in self.connectors.values():
            await connector.disconnect()

        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("✅ Live data fetcher stopped")

    async def _run_connector(self, connector: ExchangeConnector):
        """Run a single connector"""
        while True:
            try:
                await connector.connect()

                # Listen for messages
                async for message in connector.connection:
                    try:
                        self.stats['messages_received'] += 1

                        # Parse ticker data
                        ticker = connector.parse_message(message)
                        if ticker:
                            self.stats['tickers_processed'] += 1

                            # Notify callbacks
                            for callback in self.data_callbacks:
                                try:
                                    if asyncio.iscoroutinefunction(callback):
                                        await callback(ticker)
                                    else:
                                        callback(ticker)
                                except Exception as e:
                                    logger.error(f"Error in data callback: {e}")

                    except Exception as e:
                        self.stats['errors'] += 1
                        logger.error(f"Error processing message from {connector.exchange_name}: {e}")

            except websockets.exceptions.ConnectionClosed:
                logger.warning(f"Connection closed for {connector.exchange_name}")
                await connector.handle_reconnect()

            except Exception as e:
                logger.error(f"Connector error for {connector.exchange_name}: {e}")
                await asyncio.sleep(5)

    async def _monitor_heartbeats(self):
        """Monitor connection heartbeats"""
        while True:
            await asyncio.sleep(60)  # Check every minute

            current_time = time.time()
            for name, connector in self.connectors.items():
                if connector.is_connected:
                    time_since_heartbeat = current_time - connector.last_heartbeat
                    if time_since_heartbeat > 300:  # 5 minutes
                        logger.warning(f"No heartbeat from {name} for {time_since_heartbeat:.0f}s")
                        # Trigger reconnection
                        await connector.disconnect()
                        await connector.handle_reconnect()

    def get_stats(self) -> Dict[str, Any]:
        """Get fetcher statistics"""
        uptime = time.time() - self.stats['start_time']

        return {
            'uptime_seconds': uptime,
            'messages_received': self.stats['messages_received'],
            'tickers_processed': self.stats['tickers_processed'],
            'errors': self.stats['errors'],
            'messages_per_second': self.stats['messages_received'] / uptime if uptime > 0 else 0,
            'exchanges_connected': sum(1 for c in self.connectors.values() if c.is_connected),
            'total_exchanges': len(self.connectors),
            'pairs_monitored': len(self.mica_pairs)
        }

    def get_latest_prices(self, pair: str) -> Optional[Dict[str, float]]:
        """Get latest prices for a pair (placeholder - implement caching)"""
        # This would be implemented with a price cache
        # For now, return None - paper trading will handle this
        return None

# Global fetcher instance
_fetcher = None

def get_live_data_fetcher() -> LiveDataFetcher:
    """Get or create global live data fetcher"""
    global _fetcher
    if _fetcher is None:
        _fetcher = LiveDataFetcher()
    return _fetcher

async def test_live_data_fetcher():
    """Test the live data fetcher"""

    print("Live Data Fetcher Test")
    print("=" * 50)

    fetcher = get_live_data_fetcher()

    # Add test callback
    def test_callback(ticker: TickerData):
        print(f"[DATA] {ticker.exchange}: {ticker.pair} @ ${ticker.price:.4f} "
              f"(24h: {ticker.price_change_pct_24h:+.2f}%)")

    fetcher.add_data_callback(test_callback)

    try:
        # Start fetcher
        await fetcher.start()

        # Run for 30 seconds
        print("Listening for live data (30 seconds)...")
        await asyncio.sleep(30)

    except KeyboardInterrupt:
        print("\nTest interrupted")

    finally:
        await fetcher.stop()

        # Show stats
        stats = fetcher.get_stats()
        print("\nTest Statistics:")
        print(f"   Uptime: {stats['uptime_seconds']:.1f}s")
        print(f"   Messages: {stats['messages_received']}")
        print(f"   Tickers: {stats['tickers_processed']}")
        print(f"   Errors: {stats['errors']}")
        print(f"   Exchanges Connected: {stats['exchanges_connected']}/{stats['total_exchanges']}")
        print(f"   Pairs Monitored: {stats['pairs_monitored']}")

        print("\n" + "=" * 50)
        print("Live Data Fetcher Test Complete")

if __name__ == '__main__':
    asyncio.run(test_live_data_fetcher())