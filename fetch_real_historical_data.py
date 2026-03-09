#!/usr/bin/env python3
"""
Fetch Real Historical Data for MiCA Compliant Pairs
Downloads 2 years of 1h OHLCV data from Binance, Coinbase, and Kraken
"""

import ccxt
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
import os
import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class RealHistoricalDataFetcher:
    """
    Fetch real historical data for MiCA compliant USDC pairs
    """

    def __init__(self):
        self.exchanges = ['binance', 'coinbase', 'kraken']
        self.mica_pairs = [
            'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC',
            'LINK/USDC', 'IOTA/USDC', 'XDC/USDC', 'ONDO/USDC', 'VET/USDC'
        ]

        # Initialize exchange clients
        self.exchange_clients = {
            'binance': ccxt.binance(),
            'coinbase': ccxt.coinbase(),
            'kraken': ccxt.kraken()
        }

        # Data directory
        self.data_dir = Path('data/real_historical')
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def fetch_pair_data(self, exchange_name: str, pair: str) -> Optional[pd.DataFrame]:
        """
        Fetch 2 years of 1h OHLCV data for a specific pair from an exchange
        """
        try:
            client = self.exchange_clients[exchange_name]
            logger.info(f"Fetching {pair} from {exchange_name}...")

            # Calculate time range (2 years)
            end_time = datetime.now()
            start_time = end_time - timedelta(days=730)  # 2 years

            # Convert to milliseconds
            since = int(start_time.timestamp() * 1000)

            # Fetch data in chunks to avoid rate limits
            all_data = []
            current_since = since

            while current_since < int(end_time.timestamp() * 1000):
                try:
                    # Fetch 1 hour candles
                    ohlcv = client.fetch_ohlcv(pair, '1h', current_since, limit=1000)

                    if not ohlcv:
                        break

                    all_data.extend(ohlcv)

                    # Update since for next batch
                    current_since = ohlcv[-1][0] + (60 * 60 * 1000)  # Next hour

                    # Rate limiting
                    await asyncio.sleep(0.1)

                except Exception as e:
                    logger.warning(f"Error fetching batch for {pair} from {exchange_name}: {e}")
                    break

            if not all_data:
                logger.warning(f"No data fetched for {pair} from {exchange_name}")
                return None

            # Convert to DataFrame
            df = pd.DataFrame(all_data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')

            # Basic data validation
            df = df.dropna()
            df = df[df['volume'] > 0]  # Remove zero volume entries

            # Ensure OHLC relationships
            df['high'] = np.maximum(df['high'], df[['open', 'close']].max(axis=1))
            df['low'] = np.minimum(df['low'], df[['open', 'close']].min(axis=1))

            logger.info(f"Fetched {len(df)} records for {pair} from {exchange_name}")
            return df

        except Exception as e:
            logger.error(f"Failed to fetch {pair} from {exchange_name}: {e}")
            return None

    def save_data(self, df: pd.DataFrame, exchange: str, pair: str):
        """Save data to appropriate directory structure"""
        try:
            # Create directory
            exchange_dir = self.data_dir / exchange
            exchange_dir.mkdir(exist_ok=True)

            # Format filename
            pair_filename = pair.replace('/', '_')
            filename = f"{pair_filename}_1h.csv"
            filepath = exchange_dir / filename

            # Save to CSV
            df.to_csv(filepath, index=False)
            logger.info(f"Saved {len(df)} records to {filepath}")

        except Exception as e:
            logger.error(f"Failed to save data for {pair} from {exchange}: {e}")

    async def fetch_all_data(self):
        """Fetch data for all exchanges and pairs"""
        logger.info("Starting real historical data fetch for MiCA compliant pairs")
        logger.info(f"Exchanges: {self.exchanges}")
        logger.info(f"Pairs: {self.mica_pairs}")

        total_pairs = len(self.exchanges) * len(self.mica_pairs)
        completed = 0

        for exchange in self.exchanges:
            for pair in self.mica_pairs:
                try:
                    df = await self.fetch_pair_data(exchange, pair)
                    if df is not None and len(df) > 0:
                        self.save_data(df, exchange, pair)
                    else:
                        logger.warning(f"No data available for {pair} on {exchange}")

                    completed += 1
                    logger.info(f"Progress: {completed}/{total_pairs} pairs completed")

                    # Rate limiting between pairs
                    await asyncio.sleep(1)

                except Exception as e:
                    logger.error(f"Failed to process {pair} from {exchange}: {e}")
                    completed += 1

        logger.info("Real historical data fetch completed!")

    def generate_summary_report(self):
        """Generate a summary report of fetched data"""
        report = {
            'fetch_timestamp': datetime.now().isoformat(),
            'exchanges': self.exchanges,
            'pairs': self.mica_pairs,
            'data_files': []
        }

        total_records = 0

        for exchange in self.exchanges:
            exchange_dir = self.data_dir / exchange
            if exchange_dir.exists():
                for csv_file in exchange_dir.glob('*.csv'):
                    try:
                        df = pd.read_csv(csv_file)
                        file_info = {
                            'exchange': exchange,
                            'pair': csv_file.stem.replace('_1h', '').replace('_', '/'),
                            'records': len(df),
                            'start_date': df['timestamp'].min() if len(df) > 0 else None,
                            'end_date': df['timestamp'].max() if len(df) > 0 else None,
                            'file_path': str(csv_file)
                        }
                        report['data_files'].append(file_info)
                        total_records += len(df)
                    except Exception as e:
                        logger.warning(f"Could not read {csv_file}: {e}")

        report['total_records'] = total_records
        report['total_files'] = len(report['data_files'])

        # Save report
        report_path = self.data_dir / 'fetch_report.json'
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"Summary report saved to {report_path}")
        logger.info(f"Total records fetched: {total_records}")
        logger.info(f"Total files created: {len(report['data_files'])}")

        return report

async def main():
    """Main entry point"""
    fetcher = RealHistoricalDataFetcher()
    await fetcher.fetch_all_data()
    fetcher.generate_summary_report()

if __name__ == "__main__":
    asyncio.run(main())