#!/usr/bin/env python3
"""
Fast Kraken historical OHLCV data downloader.

RESEARCH FINDINGS:
==================
Kraken's OHLC API endpoint (GET /0/public/OHLC) is HARD-CAPPED at 720 candles.
The 'since' parameter does NOT enable pagination past this limit -- it always
returns the most recent 720 candles regardless. This makes the OHLC endpoint
useless for fetching more than ~2.5 days of 5m data.

SOLUTION: Use the Trades endpoint (GET /0/public/Trades) which:
  - Returns 1000 trades per request
  - Supports full pagination via nanosecond 'since' parameter
  - Has complete history from market inception
  - Returns a 'last' field for seamless pagination

The trades are then aggregated into OHLCV candles locally using pandas.

SPEED: For Kraken USDC pairs (lower volume than USD pairs), 90 days of data
typically requires 50-150 API calls per pair, taking 2-5 minutes per pair.
Total for all 8 available USDC pairs: ~15-30 minutes.

ALTERNATIVE CONSIDERED BUT REJECTED:
  - Kraken Google Drive OHLCVT bulk download: Complete history in CSV format,
    but only updated quarterly, requires manual Google Drive access, and the
    support page (support.kraken.com/articles/360047124832) returns 403 when
    accessed programmatically. Not automatable.
  - CryptoDataDownload.com: Kraken data listed as "currently unavailable".
  - Kraken Futures: Less bulk download access than spot.

KRAKEN USDC PAIR AVAILABILITY (as of 2026-03):
  Available:     BTC, ETH, XRP, ALGO, ADA, LINK, VET, XDC
  Not available: XLM, HBAR, IOTA, ONDO

Usage:
    python fetch_kraken_fast.py                    # All pairs, 90 days
    python fetch_kraken_fast.py --days 60          # All pairs, 60 days
    python fetch_kraken_fast.py --pairs BTC ETH    # Specific pairs only
    python fetch_kraken_fast.py --resume            # Skip pairs with recent data
"""

import argparse
import logging
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# ── Kraken USDC pairs available for trading ──────────────────────────────────
# Maps our standard pair name -> Kraken API pair code
# Note: Kraken uses XBT instead of BTC
KRAKEN_USDC_PAIRS = {
    "BTC": "XBTUSDC",
    "ETH": "ETHUSDC",
    "XRP": "XRPUSDC",
    "ALGO": "ALGOUSDC",
    "ADA": "ADAUSDC",
    "LINK": "LINKUSDC",
    "VET": "VETUSDC",
    "XDC": "XDCUSDC",
}

# Pairs NOT available on Kraken with USDC (do NOT attempt):
# XLM, HBAR, IOTA, ONDO

KRAKEN_API_BASE = "https://api.kraken.com/0/public"
TRADES_PER_REQUEST = 1000  # Kraken returns up to 1000 trades per call
RATE_LIMIT_SECONDS = 1.5   # Conservative rate limit (Kraken allows ~1/sec for public)
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "historical", "kraken")


def fetch_trades_page(pair_code: str, since_ns: int) -> Optional[dict]:
    """Fetch a single page of trades from Kraken.

    Args:
        pair_code: Kraken pair code (e.g., 'XBTUSDC')
        since_ns: Nanosecond Unix timestamp for pagination

    Returns:
        Dict with 'trades' list and 'last' nanosecond timestamp, or None on error.
    """
    url = f"{KRAKEN_API_BASE}/Trades"
    params = {"pair": pair_code, "since": since_ns}

    for attempt in range(3):
        try:
            resp = requests.get(url, params=params, timeout=30)
            data = resp.json()

            if data.get("error"):
                errors = data["error"]
                # Rate limit errors: back off and retry
                if any("EAPI:Rate limit" in str(e) for e in errors):
                    wait = 5 * (attempt + 1)
                    logger.warning(f"  Rate limited, waiting {wait}s...")
                    time.sleep(wait)
                    continue
                logger.error(f"  API error: {errors}")
                return None

            # Extract trades from result (key is the pair name, varies)
            result = data["result"]
            trade_key = [k for k in result if k != "last"][0]
            trades_raw = result[trade_key]
            last_ns = int(result["last"])

            # Parse trades: [price, volume, time, buy/sell, market/limit, misc, trade_id]
            trades = []
            for t in trades_raw:
                trades.append({
                    "price": float(t[0]),
                    "volume": float(t[1]),
                    "time": float(t[2]),  # Unix timestamp with fractional seconds
                })

            return {"trades": trades, "last": last_ns}

        except requests.exceptions.Timeout:
            logger.warning(f"  Timeout on attempt {attempt + 1}, retrying...")
            time.sleep(3)
        except Exception as e:
            logger.error(f"  Error fetching trades: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                return None

    return None


def fetch_all_trades(pair_code: str, pair_name: str, days: int) -> pd.DataFrame:
    """Fetch all trades for a pair going back N days.

    Args:
        pair_code: Kraken pair code (e.g., 'XBTUSDC')
        pair_name: Display name (e.g., 'BTC')
        days: Number of days of history to fetch

    Returns:
        DataFrame with columns [time, price, volume]
    """
    start_dt = datetime.now(timezone.utc) - timedelta(days=days)
    since_ns = int(start_dt.timestamp()) * 1_000_000_000
    now_ns = int(datetime.now(timezone.utc).timestamp()) * 1_000_000_000

    all_trades = []
    pages = 0
    start_time = time.time()

    logger.info(f"  Fetching trades from {start_dt.strftime('%Y-%m-%d')} to now...")

    while since_ns < now_ns:
        result = fetch_trades_page(pair_code, since_ns)
        if result is None:
            logger.error(f"  Failed to fetch page {pages + 1}, stopping")
            break

        trades = result["trades"]
        last_ns = result["last"]
        pages += 1

        if not trades:
            # No trades in this range, jump forward
            since_ns += 3600 * 1_000_000_000  # Skip 1 hour
            time.sleep(RATE_LIMIT_SECONDS)
            continue

        all_trades.extend(trades)

        # Progress reporting
        last_trade_dt = datetime.fromtimestamp(trades[-1]["time"], tz=timezone.utc)
        if pages <= 3 or pages % 20 == 0:
            elapsed = time.time() - start_time
            logger.info(
                f"    Page {pages:>4d}: +{len(trades):>4d} trades "
                f"(total: {len(all_trades):>7,d}), "
                f"reached {last_trade_dt.strftime('%Y-%m-%d %H:%M')} "
                f"[{elapsed:.0f}s]"
            )

        # Check if we've reached the present
        if last_ns >= now_ns or trades[-1]["time"] > datetime.now(timezone.utc).timestamp() - 60:
            break

        since_ns = last_ns
        time.sleep(RATE_LIMIT_SECONDS)

    elapsed = time.time() - start_time
    logger.info(
        f"  Done: {len(all_trades):,d} trades in {pages} pages, {elapsed:.1f}s "
        f"({len(all_trades) / max(elapsed, 1):.0f} trades/sec)"
    )

    if not all_trades:
        return pd.DataFrame()

    df = pd.DataFrame(all_trades)
    return df


def aggregate_to_ohlcv(trades_df: pd.DataFrame, timeframe_minutes: int = 5) -> pd.DataFrame:
    """Aggregate raw trades into OHLCV candles.

    Args:
        trades_df: DataFrame with columns [time, price, volume]
        timeframe_minutes: Candle size in minutes (default: 5)

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume]
    """
    if trades_df.empty:
        return pd.DataFrame()

    # Convert Unix timestamps to datetime
    trades_df = trades_df.copy()
    trades_df["datetime"] = pd.to_datetime(trades_df["time"], unit="s", utc=True)
    trades_df = trades_df.sort_values("datetime")

    # Floor to candle boundaries
    freq = f"{timeframe_minutes}min"
    trades_df["candle"] = trades_df["datetime"].dt.floor(freq)

    # Aggregate
    ohlcv = (
        trades_df.groupby("candle")
        .agg(
            open=("price", "first"),
            high=("price", "max"),
            low=("price", "min"),
            close=("price", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
        .rename(columns={"candle": "timestamp"})
    )

    # Convert timestamp to string format matching existing data: 'YYYY-MM-DD HH:MM:SS'
    ohlcv["timestamp"] = ohlcv["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return ohlcv


def save_ohlcv(ohlcv_df: pd.DataFrame, pair_name: str, timeframe: str = "5m") -> str:
    """Save OHLCV data to CSV matching the project's expected format.

    Format: CSV with columns [timestamp, open, high, low, close, volume]
    Path: data/historical/kraken/{PAIR}_USDC_{timeframe}.csv

    Args:
        ohlcv_df: DataFrame with OHLCV data
        pair_name: Base asset name (e.g., 'BTC')
        timeframe: Timeframe string (e.g., '5m')

    Returns:
        Path to saved file
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    filename = f"{pair_name}_USDC_{timeframe}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    ohlcv_df.to_csv(filepath, index=False)
    return filepath


def main():
    parser = argparse.ArgumentParser(
        description="Fast Kraken OHLCV data downloader using Trades endpoint"
    )
    parser.add_argument(
        "--days",
        type=int,
        default=90,
        help="Days of history to fetch (default: 90)",
    )
    parser.add_argument(
        "--pairs",
        nargs="+",
        default=list(KRAKEN_USDC_PAIRS.keys()),
        help=f"Pairs to fetch (default: all). Available: {', '.join(KRAKEN_USDC_PAIRS.keys())}",
    )
    parser.add_argument(
        "--timeframe",
        type=int,
        default=5,
        help="Candle size in minutes (default: 5)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Skip pairs that already have data less than 24h old",
    )
    args = parser.parse_args()

    tf_str = f"{args.timeframe}m"

    logger.info("=" * 65)
    logger.info("Kraken Fast OHLCV Downloader (Trades -> OHLCV aggregation)")
    logger.info("=" * 65)
    logger.info(f"  Days:      {args.days}")
    logger.info(f"  Timeframe: {tf_str}")
    logger.info(f"  Pairs:     {', '.join(args.pairs)}")
    logger.info(f"  Output:    {OUTPUT_DIR}")
    logger.info("")

    results = {}
    total_start = time.time()

    for pair_name in args.pairs:
        pair_name = pair_name.upper()
        if pair_name not in KRAKEN_USDC_PAIRS:
            logger.warning(
                f"  {pair_name}/USDC not available on Kraken, skipping. "
                f"Available: {', '.join(KRAKEN_USDC_PAIRS.keys())}"
            )
            results[pair_name] = "NOT_AVAILABLE"
            continue

        pair_code = KRAKEN_USDC_PAIRS[pair_name]
        filename = f"{pair_name}_USDC_{tf_str}.csv"
        filepath = os.path.join(OUTPUT_DIR, filename)

        # Check for recent data if --resume
        if args.resume and os.path.exists(filepath):
            mtime = os.path.getmtime(filepath)
            age_hours = (time.time() - mtime) / 3600
            if age_hours < 24:
                # Also check if the file has enough data (not just the 720 cap)
                try:
                    existing_df = pd.read_csv(filepath)
                    expected_candles = args.days * 24 * 60 / args.timeframe
                    # If we have at least 80% of expected candles, skip
                    if len(existing_df) > expected_candles * 0.8:
                        logger.info(
                            f"[{pair_name}/USDC] Recent data exists "
                            f"({len(existing_df):,d} candles, {age_hours:.1f}h old), skipping"
                        )
                        results[pair_name] = f"SKIPPED ({len(existing_df):,d} candles)"
                        continue
                except Exception:
                    pass

        logger.info(f"[{pair_name}/USDC] ({pair_code})")

        # Fetch trades
        trades_df = fetch_all_trades(pair_code, pair_name, args.days)
        if trades_df.empty:
            logger.warning(f"  No trades returned for {pair_name}/USDC")
            results[pair_name] = "NO_DATA"
            continue

        # Aggregate to OHLCV candles
        ohlcv = aggregate_to_ohlcv(trades_df, args.timeframe)
        logger.info(
            f"  Aggregated: {len(ohlcv):,d} candles "
            f"({ohlcv['timestamp'].iloc[0]} to {ohlcv['timestamp'].iloc[-1]})"
        )

        # Save
        path = save_ohlcv(ohlcv, pair_name, tf_str)
        logger.info(f"  Saved: {path}")
        results[pair_name] = f"OK ({len(ohlcv):,d} candles)"

    # Summary
    total_elapsed = time.time() - total_start
    logger.info("")
    logger.info("=" * 65)
    logger.info(f"COMPLETE in {total_elapsed:.0f}s ({total_elapsed / 60:.1f} min)")
    logger.info("=" * 65)
    for pair, status in results.items():
        logger.info(f"  {pair + '/USDC':15s} {status}")


if __name__ == "__main__":
    main()
