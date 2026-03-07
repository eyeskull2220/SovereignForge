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
                extra_headers=self.get_headers(),
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
        super().__init__(
            "binance",
            "wss://stream.binance.com:9443/ws",
            pairs
        )

    async def subscribe(self):
        """Subscribe to Binance ticker streams"""
        # Convert pairs to Binance format (e.g., XRPUSDC@ticker)
        streams = []
        for pair in self.pairs:
            # Remove / and convert to Binance format
            binance_symbol = pair.replace('/', '').lower()
            streams.append(f"{binance_symbol}@ticker")

        subscription = {
            "method": "SUBSCRIBE",
            "params": streams,
            "id": 1
        }

        await self.connection.send(json.dumps(subscription))
        logger.info(f"Subscribed to {len(streams)} Binance streams")

    def parse_message(self, message: str) -> Optional[TickerData]:
        """Parse Binance ticker message"""
        try:
            data = json.loads(message)

            if 'stream' not in data or 'data' not in data:
                return None

            ticker = data['data']
            symbol = ticker['s']

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
                timestamp=ticker['E'] / 1000,  # Convert ms to seconds
                price=float(ticker['c']),
                volume_24h=float(ticker['v']),
                price_change_24h=float(ticker['p']),
                price_change_pct_24h=float(ticker['P']),
                bid_price=float(ticker['b']),
                ask_price=float(ticker['a']),
                bid_volume=float(ticker['B']),
                ask_volume=float(ticker['A'])
            )

        except Exception as e:
            logger.error(f"Error parsing Binance message: {e}")
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


