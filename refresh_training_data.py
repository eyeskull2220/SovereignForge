#!/usr/bin/env python3
"""Fetch fresh OHLCV data for all trading pairs from all exchanges.

Downloads 90 days of 5-minute candles for all 12 MiCA-compliant USDC pairs
from binance, coinbase, kraken, okx, kucoin, bybit, and gate.  Saves to the same CSV format that
the training pipeline (multi_strategy_training._load_pair_data) expects:

    data/historical/{exchange}/{PAIR}_5m.csv

Columns: timestamp, open, high, low, close, volume
(timestamp is a human-readable datetime string produced by pd.to_datetime)

Skips any pair whose CSV was last written less than 1 day ago.

Kraken workaround:
    Kraken's OHLC endpoint hard-caps at 720 candles regardless of the `since`
    parameter (confirmed by Kraken docs: "Returns up to 720 of the most recent
    entries. Older data cannot be retrieved, regardless of the value of since.")
    To get full history we fetch raw trades via the Trades endpoint (which has
    unlimited pagination via `since` in nanoseconds) and aggregate them into
    5-minute OHLCV candles locally.  A 1h OHLCV file is also saved as fallback.

Usage:
    python refresh_training_data.py              # full refresh
    python refresh_training_data.py --days 120   # fetch 120 days instead of 90
    python refresh_training_data.py --exchanges binance okx  # specific exchanges
"""

import argparse
import csv
import os
import time
from datetime import datetime, timedelta
from pathlib import Path

import ccxt
import numpy as np
import pandas as pd

# ── Configuration ────────────────────────────────────────────────────────

EXCHANGES = ['binance', 'coinbase', 'kraken', 'okx', 'kucoin', 'bybit', 'gate']

PAIRS = [
    'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC',
    'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC',
]

TIMEFRAME = '5m'
DEFAULT_DAYS = 90
DATA_DIR = Path(__file__).resolve().parent / 'data' / 'historical'
MIN_TRAINING_CANDLES = 60 * 24 * (60 // 5)  # 60 days of 5m candles = 17 280

# Verified exchange API limits (2026-03-14)
# Source: official docs + ccxt + empirical testing
#
# Kraken: OHLC endpoint hard-caps at 720 candles for ANY timeframe.
# We bypass this by building candles from raw trades (see fetch_kraken_trades_ohlcv).
# max_history is set to None because the trades workaround has no cap.
EXCHANGE_CONFIG = {
    'binance':  {'per_request': 1000, 'max_history': None,  'notes': 'Full history, generous limits'},
    'coinbase': {'per_request': 300,  'max_history': None,  'notes': 'Full history, smallest per-req'},
    'kraken':   {'per_request': 720,  'max_history': None,  'notes': 'OHLC capped at 720; use trades workaround for full history'},
    'okx':      {'per_request': 300,  'max_history': None,  'notes': 'Two endpoints: /candles (1440 recent) + /history-candles (older, limit=100). ccxt handles switch.'},
    'kucoin':   {'per_request': 1500, 'max_history': None,  'notes': 'Full history, highest per-request limit'},
    'bybit':    {'per_request': 1000, 'max_history': None,  'notes': 'Full history, 600 req/5s IP limit'},
    'gate':     {'per_request': 1000, 'max_history': 10000, 'notes': 'Hard cap: 10000 candles ago max (~34d at 5m)'},
}

def _max_days_for_exchange(exchange_name: str, requested_days: int) -> int:
    """Cap requested days to what the exchange's total history limit supports."""
    cfg = EXCHANGE_CONFIG.get(exchange_name, {})
    max_candles = cfg.get('max_history')
    if max_candles:
        max_days = max(1, int(max_candles * 5 / (60 * 24)))  # candles to days for 5m
        if requested_days > max_days:
            return max_days
    return requested_days

def _per_request_limit(exchange_name: str) -> int:
    """Get the per-request candle limit for an exchange."""
    return EXCHANGE_CONFIG.get(exchange_name, {}).get('per_request', 300)

# ── Kraken Trades-to-OHLCV Workaround ────────────────────────────────────

def _trades_to_ohlcv(trades_df: pd.DataFrame, interval_minutes: int = 5) -> pd.DataFrame:
    """Aggregate a DataFrame of raw trades into OHLCV candles.

    Args:
        trades_df: DataFrame with columns [timestamp, price, amount].
                   timestamp must be a datetime64 or convertible to one.
        interval_minutes: Candle width in minutes (default 5).

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume],
        sorted by timestamp, one row per candle.
    """
    if trades_df.empty:
        return pd.DataFrame(columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

    df = trades_df.copy()
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp')

    # Floor each trade timestamp to the candle boundary
    df['candle'] = df['timestamp'].dt.floor(f'{interval_minutes}min')

    ohlcv = df.groupby('candle').agg(
        open=('price', 'first'),
        high=('price', 'max'),
        low=('price', 'min'),
        close=('price', 'last'),
        volume=('amount', 'sum'),
    ).reset_index().rename(columns={'candle': 'timestamp'})

    return ohlcv.sort_values('timestamp').reset_index(drop=True)


def fetch_kraken_trades_ohlcv(pair: str, days: int = 90, interval_minutes: int = 5) -> pd.DataFrame:
    """Fetch raw trades from Kraken and build OHLCV candles locally.

    Kraken's OHLC endpoint hard-caps at 720 candles regardless of timeframe
    or `since` parameter.  Their official workaround is to use the Trades
    endpoint, which supports unlimited pagination via the `since` parameter
    (nanosecond-resolution UNIX timestamp).  Each request returns up to 1000
    trades.

    This function:
      1. Paginates through Kraken's Trades endpoint from `days` ago to now
      2. Aggregates all trades into `interval_minutes`-minute OHLCV candles
      3. Returns a standard DataFrame matching the format of fetch_ohlcv()

    Rate limiting: Kraken allows ~1 req/sec for public endpoints.  We use
    ccxt's enableRateLimit plus an extra courtesy sleep.

    Args:
        pair: Trading pair (e.g. 'BTC/USDC')
        days: Number of days of history to fetch
        interval_minutes: Candle width in minutes (default 5)

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    try:
        exchange = ccxt.kraken({'enableRateLimit': True})
        exchange.load_markets()

        if pair not in exchange.markets:
            print(f"    {pair} not listed on kraken")
            return pd.DataFrame()

        # Start timestamp in milliseconds (ccxt convention)
        since_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
        now_ms = int(datetime.utcnow().timestamp() * 1000)

        all_trades = []
        pages = 0
        max_retries = 3

        while since_ms < now_ms:
            trades = None
            for attempt in range(max_retries):
                try:
                    # ccxt.fetch_trades returns list of trade dicts
                    # Kraken returns up to 1000 trades per request
                    trades = exchange.fetch_trades(pair, since=since_ms, limit=1000)
                    break
                except ccxt.RateLimitExceeded:
                    time.sleep(3)
                except ccxt.BadRequest as e:
                    err_str = str(e).lower()
                    if 'too long ago' in err_str or 'invalid' in err_str:
                        trades = []
                        break
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        print(f"    Trades fetch error: {e}")
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        print(f"    Trades fetch error after {max_retries} retries: {e}")

            if trades is None:
                break

            if not trades:
                # No trades in this window; jump ahead 1 hour and try again
                since_ms += 3600 * 1000
                time.sleep(1)
                continue

            all_trades.extend(trades)
            pages += 1

            # Progress bar: single-line overwrite with carriage return
            if pages % 5 == 0:
                last_dt = datetime.fromtimestamp(trades[-1]['timestamp'] / 1000)
                target_dt = datetime.utcnow()
                elapsed_days = (last_dt - (datetime.utcnow() - timedelta(days=days))).days
                pct = min(100, max(0, int(elapsed_days / days * 100)))
                bar_len = 30
                filled = int(bar_len * pct / 100)
                bar = '#' * filled + '-' * (bar_len - filled)
                print(f"\r    [{bar}] {pct:>3}% | {len(all_trades):>7} trades | {last_dt.strftime('%Y-%m-%d')} | pg {pages}  ", end='', flush=True)

            # Advance `since` past the last trade we received
            since_ms = trades[-1]['timestamp'] + 1

            # Safety: if the last trade is within 1 minute of now, stop
            if trades[-1]['timestamp'] > now_ms - 60000:
                break

            # Safety: cap at 500 pages (~500k trades, ~170 days of 5m candles for BTC/USDC)
            if pages > 500:
                print(f"(hit 500-page safety cap) ", end='', flush=True)
                break

            # Rate limiting: Kraken public endpoint allows ~1 req/sec
            time.sleep(max(exchange.rateLimit / 1000.0, 1.0))

        if not all_trades:
            return pd.DataFrame()

        # Convert ccxt trade dicts to DataFrame
        trades_df = pd.DataFrame([{
            'timestamp': datetime.fromtimestamp(t['timestamp'] / 1000),
            'price': float(t['price']),
            'amount': float(t['amount']),
        } for t in all_trades])

        # Build OHLCV candles
        ohlcv_df = _trades_to_ohlcv(trades_df, interval_minutes)

        print(f"\r    [{'#' * 30}] 100% | {len(all_trades):>7} trades -> {len(ohlcv_df)} candles ({pages} pg)", flush=True)

        return ohlcv_df

    except Exception as e:
        print(f"    Error in Kraken trades workaround: {e}")
        return pd.DataFrame()


# ── Helpers ──────────────────────────────────────────────────────────────


def fetch_ohlcv(exchange_name: str, pair: str, days: int = 90) -> pd.DataFrame:
    """Fetch OHLCV data from an exchange, paginating through history.

    Automatically caps lookback for exchanges with historical limits
    (e.g., Gate.io max 10,000 candles, KuCoin 1,500 per request).

    Returns a deduplicated, sorted DataFrame with columns:
        timestamp (datetime), open, high, low, close, volume
    matching the format written by fetch_exchange_data.py.
    """
    try:
        exchange_class = getattr(ccxt, exchange_name)
        exchange = exchange_class({'enableRateLimit': True})
        exchange.load_markets()

        if pair not in exchange.markets:
            print(f"    {pair} not listed on {exchange_name}")
            return pd.DataFrame()

        # Cap days to exchange-specific limits
        effective_days = _max_days_for_exchange(exchange_name, days)
        if effective_days < days:
            print(f"(capped to {effective_days}d) ", end='', flush=True)

        since = int((datetime.utcnow() - timedelta(days=effective_days)).timestamp() * 1000)
        all_candles = []
        # Per-request limit varies by exchange (verified from API docs)
        per_request = _per_request_limit(exchange_name)
        max_retries = 3
        empty_streak = 0
        tf_ms = 300 * 1000  # 5 minutes in milliseconds
        cfg = EXCHANGE_CONFIG.get(exchange_name, {})
        max_total = cfg.get('max_history') or 999999

        while len(all_candles) < max_total:
            candles = None
            for attempt in range(max_retries):
                try:
                    candles = exchange.fetch_ohlcv(
                        pair, timeframe=TIMEFRAME, since=since, limit=per_request
                    )
                    break
                except ccxt.BadRequest as e:
                    # Exchange rejected the request (e.g., too far back)
                    err_str = str(e).lower()
                    if 'too long ago' in err_str or 'maximum' in err_str or 'invalid' in err_str:
                        print(f"(history limit hit) ", end='', flush=True)
                        candles = []  # treat as empty, stop pagination
                        break
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        print(f"    Fetch error: {e}")
                except Exception as e:
                    if attempt < max_retries - 1:
                        time.sleep(2)
                    else:
                        print(f"    Fetch error after {max_retries} retries: {e}")

            if candles is None:
                break

            if not candles:
                empty_streak += 1
                if empty_streak > 3:
                    break
                since += per_request * tf_ms
                if since > int(datetime.utcnow().timestamp() * 1000):
                    break
                time.sleep(exchange.rateLimit / 1000.0)
                continue

            empty_streak = 0
            all_candles.extend(candles)
            since = candles[-1][0] + 1  # next ms after last candle

            # Stop if we got significantly fewer than requested (true last page)
            # Use 50% threshold to handle exchanges that return limit-1 (e.g., Bybit 999/1000)
            if len(candles) < per_request * 0.5:
                break
            # Stop if last candle is within 10 minutes of now (caught up to present)
            if candles[-1][0] > int(datetime.utcnow().timestamp() * 1000) - 600000:
                break
            time.sleep(max(exchange.rateLimit / 1000.0, 0.2))

        if not all_candles:
            return pd.DataFrame()

        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
        return df

    except Exception as e:
        print(f"    Error initializing {exchange_name}: {e}")
        return pd.DataFrame()


def save_csv(df: pd.DataFrame, path: Path) -> None:
    """Save DataFrame to CSV (matching fetch_exchange_data.py output format)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)


def candle_count_to_days(count: int) -> float:
    """Convert number of 5-minute candles to approximate days."""
    return count * 5 / (60 * 24)


# ── Main ─────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description='Refresh OHLCV training data for SovereignForge')
    parser.add_argument('--exchanges', nargs='+', default=EXCHANGES,
                        help=f'Exchanges to fetch from (default: {EXCHANGES})')
    parser.add_argument('--days', type=int, default=DEFAULT_DAYS,
                        help=f'Days of history to fetch (default: {DEFAULT_DAYS})')
    parser.add_argument('--force', action='store_true',
                        help='Re-fetch even if recent data exists')
    args = parser.parse_args()

    total = len(args.exchanges) * len(PAIRS)
    done = 0
    fetched = 0
    skipped = 0
    unavailable = 0
    insufficient = []

    print(f"SovereignForge Training Data Refresh")
    print(f"  Exchanges : {', '.join(args.exchanges)}")
    print(f"  Pairs     : {len(PAIRS)}")
    print(f"  Timeframe : {TIMEFRAME}")
    print(f"  Days      : {args.days}")
    print(f"  Output    : {DATA_DIR}")
    print(f"  Total jobs: {total}")
    print()

    for exchange_name in args.exchanges:
        print(f"{'=' * 60}")
        print(f"  Exchange: {exchange_name.upper()}")
        print(f"{'=' * 60}")

        for pair in PAIRS:
            done += 1
            safe_pair = pair.replace('/', '_')
            csv_path = DATA_DIR / exchange_name / f"{safe_pair}_{TIMEFRAME}.csv"

            # Skip if recent data exists (less than 1 day old)
            if not args.force and csv_path.exists():
                mtime = datetime.fromtimestamp(csv_path.stat().st_mtime)
                age = datetime.now() - mtime
                if age.total_seconds() < 86400:
                    print(f"  [{done:>3}/{total}] {pair:<12} recent data ({age.seconds // 3600}h old), skipping")
                    skipped += 1
                    continue

            print(f"  [{done:>3}/{total}] {pair:<12} fetching {args.days} days ... ", end='', flush=True)

            # ── Kraken: build 5m candles from raw trades (bypasses 720 cap) ──
            if exchange_name == 'kraken':
                df = fetch_kraken_trades_ohlcv(pair, days=args.days, interval_minutes=5)

                # Also save 1h candles as fallback (720 candles = 30 days)
                # This is a quick single-request fetch from the OHLC endpoint
                csv_1h = DATA_DIR / exchange_name / f"{safe_pair}_1h.csv"
                try:
                    ex = ccxt.kraken({'enableRateLimit': True})
                    ex.load_markets()
                    if pair in ex.markets:
                        candles_1h = ex.fetch_ohlcv(pair, '1h', limit=720)
                        if candles_1h:
                            df_1h = pd.DataFrame(candles_1h, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
                            df_1h['timestamp'] = pd.to_datetime(df_1h['timestamp'], unit='ms')
                            save_csv(df_1h, csv_1h)
                except Exception:
                    pass  # 1h fetch is best-effort
            else:
                df = fetch_ohlcv(exchange_name, pair, args.days)

            if df.empty:
                print("no data")
                unavailable += 1
                continue

            save_csv(df, csv_path)
            n = len(df)
            d = candle_count_to_days(n)
            status = "OK" if n >= MIN_TRAINING_CANDLES else "LOW"
            print(f"{n:>7} candles ({d:>5.1f} days) [{status}]")
            fetched += 1

            if n < MIN_TRAINING_CANDLES:
                insufficient.append((exchange_name, pair, n, d))

            time.sleep(1)  # extra courtesy sleep between pairs

    # ── Summary ──────────────────────────────────────────────────────────
    print()
    print(f"{'=' * 60}")
    print(f"  SUMMARY")
    print(f"{'=' * 60}")
    print(f"  Fetched     : {fetched}")
    print(f"  Skipped     : {skipped} (recent data)")
    print(f"  Unavailable : {unavailable} (pair not listed on exchange)")
    print(f"  Total       : {total}")
    print()

    # Report per-exchange file counts
    print("  Per-exchange coverage:")
    for exchange_name in args.exchanges:
        ex_dir = DATA_DIR / exchange_name
        if ex_dir.exists():
            csvs = list(ex_dir.glob('*.csv'))
            print(f"    {exchange_name:<10} {len(csvs):>2}/{len(PAIRS)} pairs")
        else:
            print(f"    {exchange_name:<10}  0/{len(PAIRS)} pairs")

    # Warn about insufficient data
    if insufficient:
        print()
        print(f"  WARNING: {len(insufficient)} pair(s) below 60-day minimum ({MIN_TRAINING_CANDLES} candles):")
        for ex, pair, n, d in insufficient:
            print(f"    {ex}/{pair}: {n} candles ({d:.1f} days)")

    print()
    print("Done.")


if __name__ == '__main__':
    main()
