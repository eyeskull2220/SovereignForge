#!/usr/bin/env python3
"""
SovereignForge Exchange Connector - Wave 1
Simple exchange API connector for arbitrage detection
"""

import ccxt
import time
import logging
from typing import Dict, List, Optional
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

class ExchangeConnector:
    """Simple exchange API connector"""

    def __init__(self, exchange_name: str, api_key: str = None, api_secret: str = None):
        self.exchange_name = exchange_name
        self.api_key = api_key
        self.api_secret = api_secret

        # Initialize exchange
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

    def get_ticker(self, symbol: str = 'BTC/USDT') -> Optional[Dict]:
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

    def get_order_book(self, symbol: str = 'BTC/USDT', limit: int = 10) -> Optional[Dict]:
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

    def get_recent_trades(self, symbol: str = 'BTC/USDT', limit: int = 100) -> Optional[List]:
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
    """Connect to multiple exchanges"""

    def __init__(self, exchanges_config: Dict[str, Dict]):
        self.connectors = {}
        self.exchanges_config = exchanges_config

        for exchange_name, config in exchanges_config.items():
            self.connectors[exchange_name] = ExchangeConnector(
                exchange_name,
                config.get('api_key'),
                config.get('api_secret')
            )

    def get_market_data(self, symbol: str = 'BTC/USDT') -> Dict:
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

    def get_price_history(self, symbol: str = 'BTC/USDT', timeframe: str = '1m', limit: int = 100) -> List[float]:
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
    market_data = connector.get_market_data('BTC/USDT')

    print(f"Symbol: {market_data['symbol']}")
    print(f"Exchanges: {list(market_data['exchanges'].keys())}")

    for exchange_name, data in market_data['exchanges'].items():
        print(f"{exchange_name}: Bid={data['bid']}, Ask={data['ask']}, Volume={data['volume']}")

    price_history = connector.get_price_history('BTC/USDT')
    print(f"Price history: {len(price_history)} points")

    print("Exchange connector test completed!")

if __name__ == "__main__":
    test_connectors()