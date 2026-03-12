#!/usr/bin/env python3
"""
SovereignForge Data Fetcher - Wave 3
Real exchange data integration using CCXT
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import json
import os
import asyncio
import time

logger = logging.getLogger(__name__)

class RealDataFetcher:
    """Fetches real historical data from exchanges using CCXT"""

    def __init__(self, data_directory: str = None):
        self.data_directory = data_directory or os.path.join(os.path.dirname(__file__), '..', 'data')
        self.exchanges = {}

        # Initialize exchanges and load markets
        for name in ['binance', 'coinbase', 'kraken']:
            exchange = getattr(ccxt, name)()
            try:
                exchange.load_markets()
                self.exchanges[name] = exchange
                logger.info(f"Loaded {name} markets: {len(exchange.symbols)} symbols")
            except Exception as e:
                logger.error(f"Failed to load {name} markets: {e}")

        # MiCA compliant pairs (only these are allowed)
        self.mica_pairs = [
            'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT',
            'LINK/USDT', 'IOTA/USDT', 'XDC/USDT', 'ONDO/USDT', 'VET/USDT',
            'USDC/USDT', 'RLUSD/USDT', 'BTC/USDT', 'ETH/USDT'
        ]

        # Ensure data directory exists
        os.makedirs(self.data_directory, exist_ok=True)

        logger.info("Real Data Fetcher initialized")

    async def fetch_all_data(self, days: int = 90, timeframe: str = '1h') -> Dict:
        """Fetch historical data for all MiCA pairs from all exchanges"""

        logger.info(f"Fetching {days} days of {timeframe} data for {len(self.mica_pairs)} pairs")

        all_data = {}

        for pair in self.mica_pairs:
            all_data[pair] = {}
            logger.info(f"Fetching data for {pair}")

            for exchange_name, exchange in self.exchanges.items():
                try:
                    data = await self._fetch_pair_data(exchange, pair, days, timeframe)
                    if data is not None:
                        all_data[pair][exchange_name] = data
                        logger.info(f"  {exchange_name}: {len(data)} candles")
                    else:
                        logger.warning(f"  {exchange_name}: No data for {pair}")

                except Exception as e:
                    logger.error(f"  {exchange_name} {pair}: {e}")

                # Rate limiting
                await asyncio.sleep(0.1)

        # Save to files
        self._save_data(all_data)

        return all_data

    async def _fetch_pair_data(self, exchange: ccxt.Exchange, pair: str, days: int,
                              timeframe: str) -> Optional[pd.DataFrame]:
        """Fetch historical OHLCV data for a pair"""

        try:
            # Check if pair exists on exchange
            if pair not in exchange.symbols:
                return None

            # Calculate timestamps
            since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
            limit = min(1000, days * 24)  # Max 1000 candles per request

            # Fetch OHLCV
            ohlcv = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)

            if not ohlcv:
                return None

            # Convert to DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df = df.set_index('timestamp')

            return df

        except Exception as e:
            logger.error(f"Error fetching {pair} from {exchange.id}: {e}")
            return None

    def _save_data(self, data: Dict):
        """Save fetched data to JSON files"""

        for pair, exchange_data in data.items():
            filename = f"{self.data_directory}/{pair.replace('/', '_')}_data.json"

            # Convert DataFrames to dict for JSON serialization
            serializable_data = {}
            for exchange_name, df in exchange_data.items():
                serializable_data[exchange_name] = {
                    'timestamps': df.index.tolist(),
                    'open': df['open'].tolist(),
                    'high': df['high'].tolist(),
                    'low': df['low'].tolist(),
                    'close': df['close'].tolist(),
                    'volume': df['volume'].tolist()
                }

            with open(filename, 'w') as f:
                json.dump(serializable_data, f, default=str, indent=2)

            logger.info(f"Saved {pair} data to {filename}")

    def load_data(self, pair: str) -> Dict:
        """Load saved data for a pair"""

        filename = f"{self.data_directory}/{pair.replace('/', '_')}_data.json"

        if not os.path.exists(filename):
            return {}

        with open(filename, 'r') as f:
            data = json.load(f)

        # Convert back to DataFrames
        result = {}
        for exchange_name, exchange_data in data.items():
            df = pd.DataFrame({
                'open': exchange_data['open'],
                'high': exchange_data['high'],
                'low': exchange_data['low'],
                'close': exchange_data['close'],
                'volume': exchange_data['volume']
            }, index=pd.to_datetime(exchange_data['timestamps']))
            result[exchange_name] = df

        return result

    def get_available_pairs(self) -> List[str]:
        """Get list of pairs with available data"""
        return [f for f in os.listdir(self.data_directory) if f.endswith('_data.json')]

    def get_available_exchanges(self) -> List[str]:
        """Get list of available exchanges"""
        # Check first available pair to see what exchanges have data
        pairs = self.get_available_pairs()
        if not pairs:
            return []

        first_pair = pairs[0].replace('_data.json', '').replace('_', '/')
        data = self.load_data(first_pair)
        return list(data.keys()) if data else []

    def get_price_at_time(self, symbol: str, exchange: str, timestamp: datetime) -> Optional[Dict]:
        """Get price data for specific symbol/exchange at given time"""

        data = self.load_data(symbol)
        if exchange not in data:
            return None

        df = data[exchange]

        # Find closest timestamp
        if df.empty:
            return None

        # Convert timestamp to pandas timestamp for comparison
        ts = pd.Timestamp(timestamp)

        # Find closest index
        closest_idx = df.index.get_indexer([ts], method='nearest')[0]

        if closest_idx == -1:
            return None

        row = df.iloc[closest_idx]

        return {
            'price': row['close'],  # Use close price as current price
            'volume': row['volume'],
            'high': row['high'],
            'low': row['low'],
            'timestamp': row.name.to_pydatetime()
        }

async def fetch_demo_data():
    """Demo function to fetch real data"""

    print("SovereignForge Real Data Fetcher")
    print("=" * 40)

    fetcher = RealDataFetcher()

    # Fetch 90 days of data for training
    print("Fetching 90 days of hourly data...")
    data = await fetcher.fetch_all_data(days=90, timeframe='1h')

    print("\nData Summary:")
    for pair, exchange_data in data.items():
        print(f"{pair}: {len(exchange_data)} exchanges")
        for exchange_name, df in exchange_data.items():
            print(f"  {exchange_name}: {len(df)} candles")

    return data

if __name__ == "__main__":
    asyncio.run(fetch_demo_data())