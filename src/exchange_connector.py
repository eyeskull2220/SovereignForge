#!/usr/bin/env python3
"""
SovereignForge Exchange Connector - Wave 1
Simple exchange API connector for arbitrage detection
"""

import ccxt
import ccxt.async_support as ccxt_async
import asyncio
import time
import logging
from typing import Dict, List, Optional, Callable, Any
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# Import WebSocket components
try:
    from source.src.websocket.connection_manager import WebSocketConnectionManager
    from source.src.websocket.reconnect_handler import get_reconnect_manager
    WEBSOCKET_AVAILABLE = True
except ImportError:
    logger.warning("WebSocket components not available, falling back to REST-only mode")
    WEBSOCKET_AVAILABLE = False
    WebSocketConnectionManager = None
    get_reconnect_manager = None

class ExchangeConnector:
    """Exchange API connector with WebSocket support"""

    def __init__(self, exchange_name: str, api_key: str = None, api_secret: str = None,
                 enable_websocket: bool = True):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret
        self.enable_websocket = enable_websocket and WEBSOCKET_AVAILABLE

        # Initialize REST exchange
        try:
            exchange_class = getattr(ccxt, exchange_name)
            self.exchange = exchange_class({
                'apiKey': api_key,
                'secret': api_secret,
                'enableRateLimit': True,
                'timeout': 10000,
            })
        except Exception as e:
            logger.error(f"Failed to initialize {exchange_name}: {e}")
            self.exchange = None

        # Initialize WebSocket components
        self.websocket_manager = None
        self.reconnect_manager = None
        self.websocket_task = None
        self.message_handlers: Dict[str, Callable] = {}

        if self.enable_websocket:
            self._initialize_websocket()

    def _initialize_websocket(self):
        """Initialize WebSocket connection manager"""
        try:
            # Get exchange WebSocket URL
            ws_url = self._get_websocket_url()

            if ws_url:
                self.websocket_manager = WebSocketConnectionManager(
                    self.exchange_name,
                    ws_url,
                    self.api_key,
                    self.api_secret
                )

                # Add message handlers
                self.websocket_manager.add_message_handler('ticker', self._handle_ticker_message)
                self.websocket_manager.add_message_handler('orderbook', self._handle_orderbook_message)
                self.websocket_manager.add_message_handler('trade', self._handle_trade_message)

                # Add connection handlers
                self.websocket_manager.add_connection_handler('connected', self._handle_connection_event)
                self.websocket_manager.add_connection_handler('disconnected', self._handle_connection_event)

                # Register with global reconnect manager
                if get_reconnect_manager:
                    self.reconnect_manager = get_reconnect_manager()
                    self.reconnect_manager.add_connection(
                        f"{self.exchange_name}_ws",
                        self.websocket_manager
                    )

                logger.info(f"WebSocket initialized for {self.exchange_name}")
            else:
                logger.warning(f"No WebSocket URL available for {self.exchange_name}")
                self.enable_websocket = False

        except Exception as e:
            logger.error(f"Failed to initialize WebSocket for {self.exchange_name}: {e}")
            self.enable_websocket = False

    def _get_websocket_url(self) -> Optional[str]:
        """Get WebSocket URL for exchange"""
        websocket_urls = {
            'binance': 'wss://stream.binance.com:9443/ws',
            'coinbase': 'wss://ws-feed.pro.coinbase.com',
            'kraken': 'wss://ws.kraken.com',
            'bitfinex': 'wss://api-pub.bitfinex.com/ws/2',
            'huobi': 'wss://api.huobi.pro/ws',
            'okex': 'wss://ws.okex.com:8443/ws/v5/public',
            'ftx': 'wss://ftx.com/ws',
            'bybit': 'wss://stream.bybit.com/realtime',
            'kucoin': 'wss://api-sandbox.kucoin.com',
        }
        return websocket_urls.get(self.exchange_name.lower())

    async def start_websocket(self):
        """Start WebSocket connection and auto-reconnect"""
        if not self.enable_websocket or not self.websocket_manager:
            logger.warning("WebSocket not available or not enabled")
            return

        try:
            # Start WebSocket auto-reconnect
            self.websocket_task = asyncio.create_task(
                self.websocket_manager.start_auto_reconnect()
            )
            logger.info(f"WebSocket auto-reconnect started for {self.exchange_name}")

        except Exception as e:
            logger.error(f"Failed to start WebSocket for {self.exchange_name}: {e}")

    async def stop_websocket(self):
        """Stop WebSocket connection"""
        if self.websocket_task:
            self.websocket_manager.stop_auto_reconnect()
            self.websocket_task.cancel()
            try:
                await self.websocket_task
            except asyncio.CancelledError:
                pass
            self.websocket_task = None

        if self.websocket_manager:
            await self.websocket_manager.disconnect()

    def add_message_handler(self, message_type: str, handler: Callable):
        """Add custom message handler"""
        self.message_handlers[message_type] = handler

    def _handle_ticker_message(self, data: Dict[str, Any], exchange_name: str):
        """Handle ticker WebSocket message"""
        try:
            # Process ticker data
            ticker_data = {
                'exchange': exchange_name,
                'symbol': data.get('symbol', data.get('product_id')),
                'bid': data.get('bestBid'),
                'ask': data.get('bestAsk'),
                'last': data.get('price'),
                'volume': data.get('volume'),
                'timestamp': datetime.now()
            }

            # Call custom handler if registered
            if 'ticker' in self.message_handlers:
                self.message_handlers['ticker'](ticker_data)

        except Exception as e:
            logger.error(f"Error handling ticker message: {e}")

    def _handle_orderbook_message(self, data: Dict[str, Any], exchange_name: str):
        """Handle orderbook WebSocket message"""
        try:
            # Process orderbook data
            orderbook_data = {
                'exchange': exchange_name,
                'symbol': data.get('symbol', data.get('product_id')),
                'bids': data.get('bids', []),
                'asks': data.get('asks', []),
                'timestamp': datetime.now()
            }

            # Call custom handler if registered
            if 'orderbook' in self.message_handlers:
                self.message_handlers['orderbook'](orderbook_data)

        except Exception as e:
            logger.error(f"Error handling orderbook message: {e}")

    def _handle_trade_message(self, data: Dict[str, Any], exchange_name: str):
        """Handle trade WebSocket message"""
        try:
            # Process trade data
            trade_data = {
                'exchange': exchange_name,
                'symbol': data.get('symbol', data.get('product_id')),
                'price': data.get('price'),
                'amount': data.get('size', data.get('amount')),
                'side': data.get('side'),
                'timestamp': datetime.now()
            }

            # Call custom handler if registered
            if 'trade' in self.message_handlers:
                self.message_handlers['trade'](trade_data)

        except Exception as e:
            logger.error(f"Error handling trade message: {e}")

    def _handle_connection_event(self, event: str, exchange_name: str):
        """Handle WebSocket connection events"""
        logger.info(f"WebSocket {event} for {exchange_name}")

        # Call custom handler if registered
        if event in self.message_handlers:
            self.message_handlers[event]({'event': event, 'exchange': exchange_name})

    async def subscribe_to_ticker(self, symbol: str) -> bool:
        """Subscribe to ticker updates via WebSocket"""
        if not self.enable_websocket or not self.websocket_manager:
            return False

        try:
            return await self.websocket_manager.subscribe_to_ticker(symbol)
        except Exception as e:
            logger.error(f"Failed to subscribe to ticker {symbol}: {e}")
            return False

    async def subscribe_to_orderbook(self, symbol: str, depth: int = 10) -> bool:
        """Subscribe to orderbook updates via WebSocket"""
        if not self.enable_websocket or not self.websocket_manager:
            return False

        try:
            return await self.websocket_manager.subscribe_to_orderbook(symbol, depth)
        except Exception as e:
            logger.error(f"Failed to subscribe to orderbook {symbol}: {e}")
            return False

    async def subscribe_to_trades(self, symbol: str) -> bool:
        """Subscribe to trade updates via WebSocket"""
        if not self.enable_websocket or not self.websocket_manager:
            return False

        try:
            return await self.websocket_manager.subscribe_to_trades(symbol)
        except Exception as e:
            logger.error(f"Failed to subscribe to trades {symbol}: {e}")
            return False

    def get_websocket_status(self) -> Dict[str, Any]:
        """Get WebSocket connection status"""
        if not self.enable_websocket or not self.websocket_manager:
            return {'websocket_enabled': False}

        return {
            'websocket_enabled': True,
            'connection_status': self.websocket_manager.get_health_status(),
            'reconnect_manager': self.reconnect_manager.get_connection_status(f"{self.exchange_name}_ws") if self.reconnect_manager else None
        }

    def get_ticker(self, symbol: str = 'BTC/USDC') -> Optional[Dict]:
        """Get ticker data"""
        if not self.exchange:
            return None

        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'symbol': symbol,
                'bid': ticker.get('bid'),
                'ask': ticker.get('ask'),
                'last': ticker.get('last'),
                'volume': ticker.get('quoteVolume', ticker.get('baseVolume')),
                'timestamp': datetime.fromtimestamp(ticker.get('timestamp', time.time() * 1000) / 1000)
            }
        except Exception as e:
            logger.error(f"Failed to get ticker for {symbol}: {e}")
            return None

    def get_order_book(self, symbol: str = 'BTC/USDC', limit: int = 10) -> Optional[Dict]:
        """Get order book"""
        if not self.exchange:
            return None

        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': orderbook.get('bids', []),
                'asks': orderbook.get('asks', []),
                'timestamp': datetime.fromtimestamp(orderbook.get('timestamp', time.time() * 1000) / 1000)
            }
        except Exception as e:
            logger.error(f"Failed to get order book for {symbol}: {e}")
            return None

    def get_recent_trades(self, symbol: str = 'BTC/USDC', limit: int = 100) -> Optional[List]:
        """Get recent trades"""
        if not self.exchange:
            return None

        try:
            trades = self.exchange.fetch_trades(symbol, limit=limit)
            return [{
                'timestamp': datetime.fromtimestamp(trade.get('timestamp', time.time() * 1000) / 1000),
                'price': trade.get('price'),
                'amount': trade.get('amount'),
                'side': trade.get('side')
            } for trade in trades]
        except Exception as e:
            logger.error(f"Failed to get trades for {symbol}: {e}")
            return None

class MultiExchangeConnector:
    """Connect to multiple exchanges with WebSocket support"""

    def __init__(self, exchanges_config: Dict[str, Dict], enable_websocket: bool = True):
        self.connectors = {}
        self.exchanges_config = exchanges_config
        self.enable_websocket = enable_websocket
        self.websocket_tasks = []
        self.message_handlers: Dict[str, Callable] = {}

        for exchange_name, config in exchanges_config.items():
            self.connectors[exchange_name] = ExchangeConnector(
                exchange_name,
                config.get('api_key'),
                config.get('api_secret'),
                enable_websocket
            )

    async def start_websockets(self):
        """Start WebSocket connections for all exchanges"""
        if not self.enable_websocket:
            logger.warning("WebSocket support disabled")
            return

        logger.info("Starting WebSocket connections for all exchanges...")

        for exchange_name, connector in self.connectors.items():
            if connector.enable_websocket:
                try:
                    await connector.start_websocket()
                    logger.info(f"WebSocket started for {exchange_name}")
                except Exception as e:
                    logger.error(f"Failed to start WebSocket for {exchange_name}: {e}")

    async def stop_websockets(self):
        """Stop all WebSocket connections"""
        logger.info("Stopping all WebSocket connections...")

        stop_tasks = []
        for connector in self.connectors.values():
            if connector.enable_websocket:
                stop_tasks.append(connector.stop_websocket())

        if stop_tasks:
            await asyncio.gather(*stop_tasks, return_exceptions=True)

        logger.info("All WebSocket connections stopped")

    async def subscribe_all_to_ticker(self, symbol: str):
        """Subscribe all exchanges to ticker updates"""
        subscription_tasks = []
        for exchange_name, connector in self.connectors.items():
            if connector.enable_websocket:
                subscription_tasks.append(connector.subscribe_to_ticker(symbol))

        if subscription_tasks:
            results = await asyncio.gather(*subscription_tasks, return_exceptions=True)
            successful = sum(1 for r in results if r is True)
            logger.info(f"Ticker subscription: {successful}/{len(subscription_tasks)} successful")

    async def subscribe_all_to_orderbook(self, symbol: str, depth: int = 10):
        """Subscribe all exchanges to orderbook updates"""
        subscription_tasks = []
        for exchange_name, connector in self.connectors.items():
            if connector.enable_websocket:
                subscription_tasks.append(connector.subscribe_to_orderbook(symbol, depth))

        if subscription_tasks:
            results = await asyncio.gather(*subscription_tasks, return_exceptions=True)
            successful = sum(1 for r in results if r is True)
            logger.info(f"Orderbook subscription: {successful}/{len(subscription_tasks)} successful")

    def add_message_handler(self, message_type: str, handler: Callable):
        """Add message handler for all connectors"""
        self.message_handlers[message_type] = handler

        # Add to individual connectors
        for connector in self.connectors.values():
            connector.add_message_handler(message_type, handler)

    def get_websocket_status(self) -> Dict[str, Any]:
        """Get WebSocket status for all exchanges"""
        status = {
            'websocket_enabled': self.enable_websocket,
            'exchanges': {}
        }

        for exchange_name, connector in self.connectors.items():
            status['exchanges'][exchange_name] = connector.get_websocket_status()

        return status

    def get_market_data(self, symbol: str = 'BTC/USDC') -> Dict:
        """Get market data from all exchanges"""
        market_data = {
            'symbol': symbol,
            'exchanges': {},
            'timestamp': datetime.now()
        }

        for exchange_name, connector in self.connectors.items():
            ticker = connector.get_ticker(symbol)
            if ticker:
                market_data['exchanges'][exchange_name] = {
                    'bid': ticker['bid'],
                    'ask': ticker['ask'],
                    'volume': ticker['volume']
                }

        return market_data

    def get_price_history(self, symbol: str = 'BTC/USDC', timeframe: str = '1m', limit: int = 100) -> List[float]:
        """Get price history from first available exchange"""
        for connector in self.connectors.values():
            try:
                # Try to get OHLCV data
                ohlcv = connector.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
                if ohlcv:
                    return [candle[4] for candle in ohlcv]  # Close prices
            except Exception as e:
                logger.warning(f"Failed to get price history: {e}")
                continue

        # Fallback: return synthetic data
        logger.warning("Using synthetic price history")
        base_price = 45000
        return [base_price + i * 0.1 for i in range(limit)]

def create_demo_connector() -> MultiExchangeConnector:
    """Create connector for demo purposes (no API keys required)"""
    # Use public APIs that don't require authentication
    exchanges_config = {
        'binance': {},  # Public API
        'coinbase': {}  # Public API
    }

    return MultiExchangeConnector(exchanges_config)

def test_connectors():
    """Test exchange connectors"""
    print("Testing exchange connectors...")

    connector = create_demo_connector()
    market_data = connector.get_market_data('BTC/USDC')

    print(f"Symbol: {market_data['symbol']}")
    print(f"Exchanges: {list(market_data['exchanges'].keys())}")

    for exchange_name, data in market_data['exchanges'].items():
        print(f"{exchange_name}: Bid={data['bid']}, Ask={data['ask']}, Volume={data['volume']}")

    price_history = connector.get_price_history('BTC/USDC')
    print(f"Price history: {len(price_history)} points")

    print("Exchange connector test completed!")

if __name__ == "__main__":
    test_connectors()