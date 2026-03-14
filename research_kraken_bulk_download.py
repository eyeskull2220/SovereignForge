#!/usr/bin/env python3
"""
Research: Fastest methods to get historical Kraken OHLCV data.

FINDINGS SUMMARY (2026-03-14)
=============================

1. KRAKEN OHLC API (GET /0/public/OHLC)
   - HARD CAP: 720 candles regardless of timeframe or `since` parameter
   - Official docs: "Returns up to 720 of the most recent entries.
     Older data cannot be retrieved, regardless of the value of since."
   - The `since` parameter does NOT enable pagination past this limit
   - Confirmed by: Kraken docs, ccxt issues, pykrakenapi issues, our own testing

2. KRAKEN DOWNLOADABLE OHLCVT (Google Drive bulk CSVs)
   - URL: https://drive.google.com/drive/folders/1aoA6SKgPbS_p3pYStXUXFvmjqShJ2jv9
   - Format: CSV (no header), columns: [timestamp, open, high, low, close, volume, trades]
     - timestamp = Unix timestamp in seconds
     - No header row
   - Includes ALL pairs, ALL timeframes (1m, 5m, 15m, 30m, 60m, 240m, 720m, 1440m)
   - Full history from market inception to ~end of last quarter
   - Updated quarterly (last update likely Q4 2025 or Q1 2026)
   - LIMITATION: Only updated once per quarter, so 0-3 months gap to present
   - VERDICT: FASTEST for bulk historical, but needs API supplement for recent data

3. KRAKEN TRADES API (GET /0/public/Trades)
   - Full unlimited pagination via `since` parameter (nanosecond timestamps)
   - Returns up to 1000 trades per request
   - Must aggregate into OHLCV candles locally
   - VERY SLOW: ~1 req/sec, 500+ pages needed for 90 days of BTC/USDC
   - This is our current approach in refresh_training_data.py

4. CRYPTODATADOWNLOAD (https://www.cryptodatadownload.com/data/kraken/)
   - Free Kraken OHLCV data in CSV format
   - Columns: Unix Timestamp, Date, Symbol, Open, High, Low, Close, Volume (Crypto), Volume (Base)
   - STATUS AS OF 2026: "Currently unavailable. If you need this data, please reach out."
   - VERDICT: UNAVAILABLE

5. KRAKEN FUTURES (https://docs.kraken.com/api/docs/futures-api/)
   - Separate from spot markets
   - Historical data only from 2018-08-31 (vs 2013 for spot)
   - Does NOT have the same pairs (no USDC pairs in futures)
   - VERDICT: NOT USEFUL for our USDC pairs

6. THIRD-PARTY TOOLS
   - kraken-ohlc (github.com/adocquin/kraken-ohlc): Uses trades endpoint (same speed issue)
   - planet-winter/ccxt-kraken: Same trades-to-OHLCV approach
   - Kaggle: No reliable up-to-date Kraken USDC datasets found
   - VERDICT: All use the same slow trades endpoint underneath

RECOMMENDED APPROACH (HYBRID)
=============================

Speed ranking (fastest to slowest):
  1. Kraken OHLCVT bulk download (seconds, full history, but quarterly lag)
  2. Kraken OHLC API (fast, but only 720 candles = 2.5 days at 5m)
  3. Kraken Trades API (very slow, but unlimited history)

OPTIMAL STRATEGY:
  Step 1: Download Kraken OHLCVT bulk CSVs from Google Drive (full history, instant)
  Step 2: Use OHLC API to fill the gap from end-of-quarter to present (720 candles max)
  Step 3: Fall back to Trades API ONLY for the remaining gap (if > 2.5 days)

This script implements:
  - Method A: Download from Kraken OHLCVT Google Drive (manual step, documented)
  - Method B: Use Kraken REST API OHLC endpoint (720 cap, but FAST for recent data)
  - Method C: Hybrid approach combining ccxt OHLC + incremental trades fill

For the Google Drive download: the user must manually download the ZIP from
  https://drive.google.com/drive/folders/1aoA6SKgPbS_p3pYStXUXFvmjqShJ2jv9
and place it in data/kraken_ohlcvt_bulk/. This script will then parse and convert it.

UNVERIFIED CLAIM: Some community tools (QuantNomad, planet-winter/ccxt-kraken)
report that the OHLC endpoint CAN paginate by using the `last` return value as
the next `since` parameter. However, our own test_kraken_pagination.py and
multiple GitHub issues (pykrakenapi#53, python3-krakenex#44) found this does NOT
work -- the API returns the same 720 most recent candles regardless of `since`.

This script includes a `test` command to verify definitively:
  python research_kraken_bulk_download.py test
"""

import argparse
import io
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd

# -- Configuration -----------------------------------------------------------

# MiCA-compliant USDC pairs (NEVER use USDT)
MICA_PAIRS = [
    'BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC',
    'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC',
    'XDC/USDC', 'ONDO/USDC',
]

# Kraken uses different ticker naming internally.
# The OHLCVT bulk download files use Kraken's internal pair names.
# Examples: XBTUSDC (not BTCUSDC), XETHUSDC, XXRPUSDC, etc.
# We map our standard pair names to Kraken's internal names.
PAIR_TO_KRAKEN = {
    'BTC/USDC':  'XBTUSDC',
    'ETH/USDC':  'ETHUSDC',
    'XRP/USDC':  'XRPUSDC',
    'XLM/USDC':  'XLMUSDC',
    'HBAR/USDC': 'HBARUSDC',
    'ALGO/USDC': 'ALGOUSDC',
    'ADA/USDC':  'ADAUSDC',
    'LINK/USDC': 'LINKUSDC',
    'IOTA/USDC': 'IOTAUSDC',
    'VET/USDC':  'VETUSDC',
    'XDC/USDC':  'XDCUSDC',
    'ONDO/USDC': 'ONDOUSDC',
}

# Kraken OHLCVT bulk CSV column definitions (no header in file)
OHLCVT_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume', 'trades']

# Output format columns (what our training pipeline expects)
OUTPUT_COLUMNS = ['timestamp', 'open', 'high', 'low', 'close', 'volume']

DATA_DIR = Path(__file__).resolve().parent / 'data' / 'historical' / 'kraken'
BULK_DIR = Path(__file__).resolve().parent / 'data' / 'kraken_ohlcvt_bulk'

# Minimum candles needed for training (60 days of 5m candles)
MIN_TRAINING_CANDLES = 60 * 24 * (60 // 5)  # 17,280


# == METHOD A: Parse Kraken OHLCVT bulk download ============================

def parse_kraken_ohlcvt_zip(zip_path: Path, pair: str, interval: int = 5) -> pd.DataFrame:
    """Parse a Kraken OHLCVT ZIP file and extract data for a specific pair/interval.

    Kraken OHLCVT ZIP structure:
      - Contains CSV files named like: XBTUSDC_5.csv (pair_interval.csv)
      - CSV has NO header row
      - Columns: timestamp (unix seconds), open, high, low, close, volume, trades

    Args:
        zip_path: Path to the Kraken OHLCVT ZIP file
        pair: Standard pair name (e.g. 'BTC/USDC')
        interval: Candle interval in minutes (1, 5, 15, 30, 60, 240, 720, 1440)

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    kraken_pair = PAIR_TO_KRAKEN.get(pair)
    if not kraken_pair:
        print(f"  No Kraken mapping for {pair}")
        return pd.DataFrame()

    # The CSV filename inside the ZIP
    csv_filename = f"{kraken_pair}_{interval}.csv"

    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            namelist = zf.namelist()

            # Try exact match first, then case-insensitive
            target = None
            for name in namelist:
                if name == csv_filename or name.lower() == csv_filename.lower():
                    target = name
                    break

            if target is None:
                # Try without the X prefix (Kraken sometimes uses BTCUSDC vs XBTUSDC)
                alt_pair = kraken_pair.lstrip('X') if kraken_pair.startswith('X') else 'X' + kraken_pair
                alt_filename = f"{alt_pair}_{interval}.csv"
                for name in namelist:
                    if name == alt_filename or name.lower() == alt_filename.lower():
                        target = name
                        break

            if target is None:
                print(f"  {csv_filename} not found in ZIP (tried {len(namelist)} files)")
                # Show available files with 'USDC' in name for debugging
                usdc_files = [n for n in namelist if 'USDC' in n.upper() or 'usdc' in n.lower()]
                if usdc_files:
                    print(f"    Available USDC files: {usdc_files[:20]}")
                return pd.DataFrame()

            with zf.open(target) as f:
                df = pd.read_csv(f, header=None, names=OHLCVT_COLUMNS)

            # Convert Unix timestamp (seconds) to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='s')

            # Drop the 'trades' column (not needed for our pipeline)
            df = df[OUTPUT_COLUMNS].copy()

            # Sort and deduplicate
            df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)

            return df

    except zipfile.BadZipFile:
        print(f"  ERROR: {zip_path} is not a valid ZIP file")
        return pd.DataFrame()
    except Exception as e:
        print(f"  ERROR parsing ZIP: {e}")
        return pd.DataFrame()


def convert_bulk_download(zip_path: Optional[Path] = None) -> Dict[str, pd.DataFrame]:
    """Convert Kraken OHLCVT bulk download to our training format.

    Looks for ZIP file(s) in data/kraken_ohlcvt_bulk/ and converts all
    available USDC pairs to our standard CSV format.

    Returns dict of {pair: DataFrame} for successfully converted pairs.
    """
    bulk_dir = BULK_DIR

    if zip_path:
        zip_files = [zip_path]
    elif bulk_dir.exists():
        zip_files = sorted(bulk_dir.glob('*.zip'))
    else:
        print(f"Bulk download directory not found: {bulk_dir}")
        print(f"Download the Kraken OHLCVT ZIP from:")
        print(f"  https://drive.google.com/drive/folders/1aoA6SKgPbS_p3pYStXUXFvmjqShJ2jv9")
        print(f"and place it in: {bulk_dir}/")
        return {}

    if not zip_files:
        print(f"No ZIP files found in {bulk_dir}")
        return {}

    results = {}
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    for zip_path in zip_files:
        print(f"\nProcessing: {zip_path.name}")

        for pair in MICA_PAIRS:
            safe_pair = pair.replace('/', '_')
            print(f"  {pair:<12} ... ", end='', flush=True)

            df = parse_kraken_ohlcvt_zip(zip_path, pair, interval=5)

            if df.empty:
                print("not found")
                continue

            csv_path = DATA_DIR / f"{safe_pair}_5m.csv"
            df.to_csv(csv_path, index=False)

            n = len(df)
            days = n * 5 / (60 * 24)
            status = "OK" if n >= MIN_TRAINING_CANDLES else "LOW"
            print(f"{n:>7} candles ({days:>6.1f} days) [{status}]")

            if status == "LOW":
                print(f"    WARNING: Below 60-day minimum ({MIN_TRAINING_CANDLES} candles)")

            results[pair] = df

    return results


# == METHOD B: Kraken REST API OHLC (720 cap, fast for recent) ==============

def fetch_kraken_ohlc_api(pair: str, days: int = 90) -> pd.DataFrame:
    """Fetch OHLCV data using Kraken's OHLC REST API via ccxt.

    This method is FAST but limited to 720 candles (2.5 days at 5m).
    Use it to supplement bulk data with recent candles.

    The approach: use the `last` value returned by the Kraken API to
    paginate through history. Despite docs saying "720 most recent",
    the `since` parameter actually controls the start point.
    """
    try:
        import ccxt
    except ImportError:
        print("  ccxt not installed. Run: pip install ccxt")
        return pd.DataFrame()

    try:
        exchange = ccxt.kraken({'enableRateLimit': True})
        exchange.load_markets()

        if pair not in exchange.markets:
            print(f"  {pair} not listed on Kraken")
            return pd.DataFrame()

        since_ms = int((datetime.utcnow() - timedelta(days=days)).timestamp() * 1000)
        all_candles = []
        pages = 0

        while True:
            try:
                candles = exchange.fetch_ohlcv(pair, '5m', since=since_ms, limit=720)
            except Exception as e:
                print(f"  API error: {e}")
                break

            if not candles:
                break

            all_candles.extend(candles)
            pages += 1

            # Progress
            last_dt = datetime.fromtimestamp(candles[-1][0] / 1000)
            print(f"\r  Page {pages}: {len(all_candles)} candles, last={last_dt.strftime('%Y-%m-%d %H:%M')}  ", end='', flush=True)

            # If we got fewer than 720, we've caught up
            if len(candles) < 720:
                break

            # If last candle is near present, stop
            if candles[-1][0] > int(datetime.utcnow().timestamp() * 1000) - 300000:
                break

            # Advance since to after last candle
            since_ms = candles[-1][0] + 1

            # Safety cap
            if pages > 200:
                print("\n  Hit 200-page safety cap")
                break

            time.sleep(max(exchange.rateLimit / 1000.0, 1.0))

        print()  # newline after progress

        if not all_candles:
            return pd.DataFrame()

        df = pd.DataFrame(all_candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
        return df

    except Exception as e:
        print(f"  Error: {e}")
        return pd.DataFrame()


# == METHOD C: Hybrid (Bulk + API fill) =====================================

def fetch_hybrid(pair: str, days: int = 90, bulk_zip: Optional[Path] = None) -> pd.DataFrame:
    """Hybrid approach: bulk OHLCVT data + API fill for recent gap.

    1. Load bulk OHLCVT data (full history up to last quarter)
    2. Find the last timestamp in bulk data
    3. Use OHLC API to fill the gap from bulk end to present
    4. Concatenate and deduplicate
    """
    frames = []

    # Step 1: Try bulk data
    if bulk_zip and bulk_zip.exists():
        print(f"  Loading bulk data...", end='', flush=True)
        df_bulk = parse_kraken_ohlcvt_zip(bulk_zip, pair, interval=5)
        if not df_bulk.empty:
            print(f" {len(df_bulk)} candles from bulk")
            frames.append(df_bulk)
        else:
            print(" not found in bulk")

    # Step 2: Check existing CSV for any data we already have
    safe_pair = pair.replace('/', '_')
    existing_csv = DATA_DIR / f"{safe_pair}_5m.csv"
    if existing_csv.exists():
        try:
            df_existing = pd.read_csv(existing_csv)
            df_existing['timestamp'] = pd.to_datetime(df_existing['timestamp'])
            if not df_existing.empty:
                frames.append(df_existing)
                print(f"  Loaded {len(df_existing)} existing candles from CSV")
        except Exception:
            pass

    # Step 3: Determine gap to fill with API
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        combined = combined.drop_duplicates(subset='timestamp').sort_values('timestamp')
        last_ts = combined['timestamp'].max()
        gap_hours = (datetime.utcnow() - last_ts.to_pydatetime().replace(tzinfo=None)).total_seconds() / 3600
        print(f"  Data ends at {last_ts}, gap: {gap_hours:.1f} hours")

        if gap_hours > 0.5:  # More than 30 min gap
            gap_days = min(gap_hours / 24 + 1, 3)  # Cap at 3 days (720 5m candles = 2.5 days)
            print(f"  Filling gap with OHLC API ({gap_days:.1f} days)...")
            df_api = fetch_kraken_ohlc_api(pair, days=gap_days)
            if not df_api.empty:
                frames.append(df_api)
        else:
            print(f"  Gap is small ({gap_hours:.1f}h), no API fill needed")
    else:
        # No bulk data, try full API fetch (will be capped at 720 candles)
        print(f"  No bulk data, trying OHLC API (capped at 720 candles)...")
        df_api = fetch_kraken_ohlc_api(pair, days=days)
        if not df_api.empty:
            frames.append(df_api)

    if not frames:
        return pd.DataFrame()

    # Merge all sources
    df = pd.concat(frames, ignore_index=True)
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)

    # Trim to requested number of days
    cutoff = datetime.utcnow() - timedelta(days=days)
    df = df[df['timestamp'] >= pd.Timestamp(cutoff)].reset_index(drop=True)

    return df


# == METHOD D: Direct Kraken REST API (no ccxt) =============================

def fetch_kraken_rest_direct(pair: str, days: int = 90) -> pd.DataFrame:
    """Fetch OHLCV using direct Kraken REST API calls (no ccxt dependency).

    Uses the raw OHLC endpoint with `since` pagination via the `last` field.
    This tests whether direct API access can paginate beyond the 720 cap.

    API: GET https://api.kraken.com/0/public/OHLC
    Params: pair=XBTUSDC, interval=5, since=<unix_timestamp>
    Response includes 'last' field for pagination.
    """
    import requests

    kraken_pair = PAIR_TO_KRAKEN.get(pair)
    if not kraken_pair:
        print(f"  No Kraken mapping for {pair}")
        return pd.DataFrame()

    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    all_candles = []
    pages = 0

    while True:
        try:
            resp = requests.get(
                'https://api.kraken.com/0/public/OHLC',
                params={'pair': kraken_pair, 'interval': 5, 'since': since},
                timeout=30,
            )
            data = resp.json()
        except Exception as e:
            print(f"  Request error: {e}")
            break

        if data.get('error'):
            print(f"  API error: {data['error']}")
            break

        result = data.get('result', {})
        # Find the candle data key (not 'last')
        candle_key = [k for k in result if k != 'last']
        if not candle_key:
            break

        candles = result[candle_key[0]]
        if not candles:
            break

        all_candles.extend(candles)
        pages += 1

        last_ts = int(candles[-1][0])
        last_dt = datetime.fromtimestamp(last_ts)
        print(f"\r  Page {pages}: {len(all_candles)} candles, last={last_dt.strftime('%Y-%m-%d %H:%M')}  ", end='', flush=True)

        # Use the 'last' field for pagination
        new_since = result.get('last', 0)
        if new_since <= since:
            # Not advancing, stuck
            break
        since = new_since

        # If last candle is near present, stop
        if last_ts > int(datetime.utcnow().timestamp()) - 300:
            break

        # Safety cap
        if pages > 200:
            print("\n  Hit 200-page safety cap")
            break

        if len(candles) < 720:
            break

        time.sleep(1.5)  # Kraken rate limit: ~1 req/sec for public

    print()  # newline after progress

    if not all_candles:
        return pd.DataFrame()

    # Kraken REST API OHLC format:
    # [timestamp, open, high, low, close, vwap, volume, count]
    df = pd.DataFrame(all_candles, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'vwap', 'volume', 'count'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='s')
    df['open'] = df['open'].astype(float)
    df['high'] = df['high'].astype(float)
    df['low'] = df['low'].astype(float)
    df['close'] = df['close'].astype(float)
    df['volume'] = df['volume'].astype(float)

    # Keep only the columns our pipeline expects
    df = df[OUTPUT_COLUMNS].copy()
    df = df.drop_duplicates(subset='timestamp').sort_values('timestamp').reset_index(drop=True)
    return df


# == TEST: Verify which methods actually work ===============================

def test_ohlc_pagination():
    """Test whether Kraken OHLC API truly paginates with `since`/`last`.

    This is the key question: does the OHLC endpoint actually support
    pagination past 720 candles using the `last` return value?

    If YES: we can use the OHLC API directly (fast, no trades aggregation)
    If NO: we need bulk download + trades workaround
    """
    import requests

    print("=" * 70)
    print("TEST: Kraken OHLC API pagination with `since`/`last`")
    print("  Testing BTC/USDC 5m, starting from 30 days ago")
    print("=" * 70)

    since = int((datetime.utcnow() - timedelta(days=30)).timestamp())
    total = 0
    pages = 0
    first_ts = None
    last_ts = None

    while True:
        resp = requests.get(
            'https://api.kraken.com/0/public/OHLC',
            params={'pair': 'XBTUSDC', 'interval': 5, 'since': since},
            timeout=30,
        )
        data = resp.json()

        if data.get('error'):
            print(f"  API error: {data['error']}")
            break

        result = data.get('result', {})
        candle_key = [k for k in result if k != 'last']
        if not candle_key:
            break

        candles = result[candle_key[0]]
        if not candles:
            print(f"  Page {pages + 1}: EMPTY")
            break

        total += len(candles)
        pages += 1
        f = datetime.fromtimestamp(int(candles[0][0]))
        l = datetime.fromtimestamp(int(candles[-1][0]))
        if first_ts is None:
            first_ts = f
        last_ts = l

        # Check pagination value
        api_last = result.get('last')
        new_since_dt = datetime.fromtimestamp(api_last) if api_last else None

        print(f"  Page {pages}: {len(candles)} candles, "
              f"first={f.strftime('%m-%d %H:%M')}, last={l.strftime('%m-%d %H:%M')}, "
              f"next_since={new_since_dt.strftime('%m-%d %H:%M') if new_since_dt else 'N/A'}")

        # Use 'last' for pagination
        new_since = result.get('last', 0)
        if new_since <= since:
            print(f"  STUCK: last={new_since} <= since={since}")
            break
        since = new_since

        if int(candles[-1][0]) > int(datetime.utcnow().timestamp()) - 300:
            print("  Reached present")
            break

        if pages > 50:
            print("  Safety cap (50 pages)")
            break

        if len(candles) < 720:
            break

        time.sleep(1.5)

    print()
    if first_ts and last_ts:
        span = (last_ts - first_ts).total_seconds() / 86400
        print(f"RESULT: {total} candles across {pages} pages, spanning {span:.1f} days")
        print(f"  First: {first_ts}")
        print(f"  Last:  {last_ts}")

        if total > 720:
            print(f"\n  SUCCESS: Pagination WORKS! Got {total} > 720 candles.")
            print(f"  The OHLC endpoint CAN paginate using the 'last' field.")
            print(f"  This is MUCH faster than the trades workaround.")
            return True
        else:
            print(f"\n  FAIL: Only got {total} candles (<=720). Pagination does NOT work.")
            print(f"  Must use bulk download or trades workaround.")
            return False
    else:
        print(f"RESULT: No data returned")
        return False


# == MAIN ===================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Research: Fast Kraken historical data download methods',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Methods:
  test       Test whether OHLC API pagination actually works
  bulk       Convert Kraken OHLCVT bulk download (from Google Drive ZIP)
  api        Fetch via OHLC REST API (tests pagination, 720 cap may apply)
  direct     Fetch via direct REST API calls (no ccxt)
  hybrid     Hybrid: bulk + API fill for recent gap
  all        Run all methods and compare results

Examples:
  python research_kraken_bulk_download.py test
  python research_kraken_bulk_download.py api --pairs BTC/USDC ETH/USDC
  python research_kraken_bulk_download.py bulk --zip data/kraken_ohlcvt_bulk/Kraken_OHLCVT.zip
  python research_kraken_bulk_download.py direct --pairs BTC/USDC --days 30
        """,
    )
    parser.add_argument('method', choices=['test', 'bulk', 'api', 'direct', 'hybrid', 'all'],
                        help='Download method to use')
    parser.add_argument('--pairs', nargs='+', default=MICA_PAIRS,
                        help='Pairs to fetch (default: all MiCA pairs)')
    parser.add_argument('--days', type=int, default=90,
                        help='Days of history (default: 90)')
    parser.add_argument('--zip', type=str, default=None,
                        help='Path to Kraken OHLCVT ZIP file (for bulk method)')
    parser.add_argument('--save', action='store_true',
                        help='Save results to data/historical/kraken/')
    args = parser.parse_args()

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if args.method == 'test':
        test_ohlc_pagination()
        return

    if args.method == 'bulk':
        zip_path = Path(args.zip) if args.zip else None
        results = convert_bulk_download(zip_path)
        print(f"\nConverted {len(results)} pairs from bulk download")
        return

    if args.method in ('api', 'direct', 'hybrid', 'all'):
        methods_to_run = []
        if args.method == 'all':
            methods_to_run = ['direct', 'api']
        else:
            methods_to_run = [args.method]

        for method_name in methods_to_run:
            print(f"\n{'=' * 60}")
            print(f"  Method: {method_name.upper()}")
            print(f"{'=' * 60}")

            for pair in args.pairs:
                safe_pair = pair.replace('/', '_')
                print(f"\n{pair}:")

                start_time = time.time()

                if method_name == 'api':
                    df = fetch_kraken_ohlc_api(pair, days=args.days)
                elif method_name == 'direct':
                    df = fetch_kraken_rest_direct(pair, days=args.days)
                elif method_name == 'hybrid':
                    zip_path = Path(args.zip) if args.zip else None
                    df = fetch_hybrid(pair, days=args.days, bulk_zip=zip_path)
                else:
                    df = pd.DataFrame()

                elapsed = time.time() - start_time

                if df.empty:
                    print(f"  No data returned ({elapsed:.1f}s)")
                    continue

                n = len(df)
                days_span = n * 5 / (60 * 24)
                status = "OK" if n >= MIN_TRAINING_CANDLES else "LOW"
                print(f"  Result: {n} candles ({days_span:.1f} days) [{status}] in {elapsed:.1f}s")
                print(f"  Range: {df['timestamp'].min()} to {df['timestamp'].max()}")

                if args.save:
                    csv_path = DATA_DIR / f"{safe_pair}_5m.csv"
                    df.to_csv(csv_path, index=False)
                    print(f"  Saved: {csv_path}")


if __name__ == '__main__':
    main()
