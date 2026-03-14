#!/usr/bin/env python3
"""
Fetch historical OHLCV data for all MiCA-compliant pairs from specified exchanges.
Saves to data/historical/{exchange}/{PAIR}_1h.csv

Usage:
    python fetch_exchange_data.py                    # Fetch all exchanges
    python fetch_exchange_data.py --exchanges okx    # Fetch only OKX
    python fetch_exchange_data.py --days 365         # Fetch 365 days
"""

import argparse
import logging
import os
import time
from datetime import datetime, timedelta

import ccxt
import pandas as pd

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MICA_PAIRS = [
    'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC',
    'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
    'XDC/USDC', 'ONDO/USDC',
]

SUPPORTED_EXCHANGES = ['binance', 'coinbase', 'kraken', 'okx', 'kucoin', 'bybit', 'gate']


def fetch_ohlcv(exchange: ccxt.Exchange, pair: str, days: int = 60, timeframe: str = '5m') -> pd.DataFrame:
    """Fetch OHLCV data, paginating if needed. Handles exchanges with limited history."""
    since = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)
    all_candles = []
    limit = 300  # Conservative limit for compatibility
    max_retries = 3
    empty_count = 0

    while True:
        candles = None
        for attempt in range(max_retries):
            try:
                candles = exchange.fetch_ohlcv(pair, timeframe=timeframe, since=since, limit=limit)
                break
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(1)
                else:
                    logger.warning(f"  Error fetching {pair} from {exchange.id}: {e}")
                    break

        if candles is None:
            break

        if not candles:
            # Some exchanges return empty for dates before listing — skip forward
            empty_count += 1
            if empty_count > 5:
                break
            # Jump forward by limit * timeframe_ms
            tf_seconds = {'1m': 60, '5m': 300, '15m': 900, '1h': 3600, '4h': 14400}
            since += limit * tf_seconds.get(timeframe, 300) * 1000
            if since > int(datetime.now().timestamp() * 1000):
                break
            time.sleep(exchange.rateLimit / 1000.0)
            continue

        empty_count = 0
        all_candles.extend(candles)
        since = candles[-1][0] + 1  # Next candle after last

        # Stop if we've caught up to now
        if len(candles) < limit:
            break

        time.sleep(exchange.rateLimit / 1000.0)  # Respect rate limits

    if not all_candles:
        return pd.DataFrame()

    df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    return df


def main():
    parser = argparse.ArgumentParser(description='Fetch exchange data for SovereignForge training')
    parser.add_argument('--exchanges', nargs='+', default=SUPPORTED_EXCHANGES,
                       help=f'Exchanges to fetch from (default: {SUPPORTED_EXCHANGES})')
    parser.add_argument('--days', type=int, default=60, help='Days of history to fetch (default: 60 = 45 train + 15 test)')
    parser.add_argument('--timeframe', default='5m', help='Candle timeframe (default: 5m)')
    args = parser.parse_args()

    base_dir = os.path.join(os.path.dirname(__file__), 'data', 'historical')

    for exchange_name in args.exchanges:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Fetching data from {exchange_name.upper()}")
        logger.info(f"{'=' * 50}")

        try:
            exchange = getattr(ccxt, exchange_name)()
            exchange.load_markets()
            logger.info(f"  {exchange_name} loaded: {len(exchange.symbols)} symbols available")
        except Exception as e:
            logger.error(f"  Failed to initialize {exchange_name}: {e}")
            continue

        exchange_dir = os.path.join(base_dir, exchange_name)
        os.makedirs(exchange_dir, exist_ok=True)

        for pair in MICA_PAIRS:
            if pair not in exchange.symbols:
                # MiCA compliance: NEVER fall back to USDT
                logger.warning(f"  {pair} not available on {exchange_name}, skipping (no USDT fallback)")
                continue
            else:
                fetch_pair = pair

            csv_path = os.path.join(exchange_dir, f"{pair.replace('/', '_')}_{args.timeframe}.csv")

            # Skip if recent data exists (less than 1 day old)
            if os.path.exists(csv_path):
                mtime = os.path.getmtime(csv_path)
                if (time.time() - mtime) < 86400:
                    logger.info(f"  {pair}: Recent data exists, skipping (use --force to refetch)")
                    continue

            logger.info(f"  Fetching {pair} ({args.days} days)...")
            df = fetch_ohlcv(exchange, fetch_pair, days=args.days, timeframe=args.timeframe)

            if df.empty:
                logger.warning(f"  {pair}: No data returned from {exchange_name}")
                continue

            df.to_csv(csv_path, index=False)
            logger.info(f"  {pair}: Saved {len(df)} candles to {csv_path}")
            time.sleep(0.5)  # Be nice to exchange APIs

    logger.info("\nData fetch complete!")
    logger.info(f"Data saved to: {base_dir}/")

    # Summary
    logger.info("\nSummary:")
    for exchange_name in args.exchanges:
        exchange_dir = os.path.join(base_dir, exchange_name)
        if os.path.exists(exchange_dir):
            files = [f for f in os.listdir(exchange_dir) if f.endswith('.csv')]
            logger.info(f"  {exchange_name}: {len(files)}/12 pairs")
        else:
            logger.info(f"  {exchange_name}: No data directory")


if __name__ == '__main__':
    main()
