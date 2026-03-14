#!/usr/bin/env python3
"""Test Kraken OHLCV data limits and validate the trades workaround.

This script tests:
1. 5m OHLC pagination with BTC/USDC (confirm 720 cap)
2. 1h OHLC timeframe history depth
3. 15m OHLC timeframe history depth
4. BTC/USD vs BTC/USDC availability
5. Direct Kraken REST API `since` behavior
6. TRADES WORKAROUND: fetch raw trades and build 5m candles (the fix)
7. Available timeframes

Run with:  python -u test_kraken_pagination.py
"""

import ccxt
import time
import requests
import pandas as pd
from datetime import datetime, timedelta


def test_5m_pagination():
    """TEST 1: Can Kraken paginate 5m candles beyond 720?"""
    print("=" * 70)
    print("TEST 1: Kraken 5m OHLC pagination with BTC/USDC")
    print("  (Expected: HARD cap at 720 candles regardless of since)")
    print("=" * 70)

    ex = ccxt.kraken({"enableRateLimit": True})
    ex.load_markets()

    since = int((datetime.utcnow() - timedelta(days=60)).timestamp() * 1000)
    total = 0
    pages = 0
    first_ts = None
    last_ts = None

    while True:
        candles = ex.fetch_ohlcv("BTC/USDC", "5m", since=since, limit=720)
        if not candles:
            print(f"  Page {pages + 1}: EMPTY - stopping")
            break
        total += len(candles)
        pages += 1
        f = datetime.fromtimestamp(candles[0][0] / 1000)
        l = datetime.fromtimestamp(candles[-1][0] / 1000)
        if first_ts is None:
            first_ts = f
        last_ts = l
        print(
            f"  Page {pages}: +{len(candles)} candles, total={total}, "
            f"first={f}, last={l}"
        )
        since = candles[-1][0] + 1
        if candles[-1][0] > int(datetime.utcnow().timestamp() * 1000) - 600000:
            print("  Reached present time - stopping")
            break
        if pages > 50:
            print("  Hit 50 page safety limit - stopping")
            break
        time.sleep(1.5)

    if first_ts and last_ts:
        span = (last_ts - first_ts).total_seconds() / 86400
        print(f"RESULT: {total} candles in {pages} pages, spanning {span:.1f} days")
        print(f"  From {first_ts} to {last_ts}")
    else:
        print(f"RESULT: {total} candles in {pages} pages")

    return ex


def test_1h_pagination(ex):
    """TEST 2: How much 1h history can we get with pagination?"""
    print()
    print("=" * 70)
    print("TEST 2: Kraken 1h OHLC timeframe with pagination")
    print("  (Expected: 720 candles = ~30 days)")
    print("=" * 70)

    since_1h = int((datetime.utcnow() - timedelta(days=90)).timestamp() * 1000)
    total_1h = 0
    pages_1h = 0
    first_1h = None
    last_1h = None

    while True:
        candles = ex.fetch_ohlcv("BTC/USDC", "1h", since=since_1h, limit=720)
        if not candles:
            break
        total_1h += len(candles)
        pages_1h += 1
        f = datetime.fromtimestamp(candles[0][0] / 1000)
        l = datetime.fromtimestamp(candles[-1][0] / 1000)
        if first_1h is None:
            first_1h = f
        last_1h = l
        print(
            f"  Page {pages_1h}: +{len(candles)} candles, total={total_1h}, "
            f"first={f}, last={l}"
        )
        since_1h = candles[-1][0] + 1
        if candles[-1][0] > int(datetime.utcnow().timestamp() * 1000) - 3600000:
            break
        if pages_1h > 20:
            break
        time.sleep(1.5)

    if first_1h and last_1h:
        span = (last_1h - first_1h).total_seconds() / 86400
        print(f"RESULT: {total_1h} 1h-candles in {pages_1h} pages, spanning {span:.1f} days")
    return total_1h


def test_15m_pagination(ex):
    """TEST 3: How much 15m history can we get?"""
    print()
    print("=" * 70)
    print("TEST 3: Kraken 15m OHLC timeframe with pagination")
    print("  (Expected: 720 candles = ~7.5 days)")
    print("=" * 70)

    since_15m = int((datetime.utcnow() - timedelta(days=90)).timestamp() * 1000)
    total_15m = 0
    pages_15m = 0
    first_15m = None
    last_15m = None

    while True:
        candles = ex.fetch_ohlcv("BTC/USDC", "15m", since=since_15m, limit=720)
        if not candles:
            break
        total_15m += len(candles)
        pages_15m += 1
        f = datetime.fromtimestamp(candles[0][0] / 1000)
        l = datetime.fromtimestamp(candles[-1][0] / 1000)
        if first_15m is None:
            first_15m = f
        last_15m = l
        print(
            f"  Page {pages_15m}: +{len(candles)} candles, total={total_15m}, "
            f"first={f}, last={l}"
        )
        since_15m = candles[-1][0] + 1
        if candles[-1][0] > int(datetime.utcnow().timestamp() * 1000) - 900000:
            break
        if pages_15m > 20:
            break
        time.sleep(1.5)

    if first_15m and last_15m:
        span = (last_15m - first_15m).total_seconds() / 86400
        print(f"RESULT: {total_15m} 15m-candles in {pages_15m} pages, spanning {span:.1f} days")
    return total_15m


def test_btc_usd(ex):
    """TEST 4: Does BTC/USD have more history than BTC/USDC?"""
    print()
    print("=" * 70)
    print("TEST 4: BTC/USD vs BTC/USDC")
    print("=" * 70)

    if "BTC/USD" in ex.markets:
        candles_usd = ex.fetch_ohlcv("BTC/USD", "5m", limit=720)
        if candles_usd:
            span = (candles_usd[-1][0] - candles_usd[0][0]) / 86400000
            print(f"  BTC/USD 5m: {len(candles_usd)} candles, span: {span:.1f} days")
        else:
            print("  BTC/USD 5m: no candles")
    else:
        print("  BTC/USD not listed on Kraken")


def test_direct_api():
    """TEST 5: Direct Kraken REST API behavior."""
    print()
    print("=" * 70)
    print("TEST 5: Direct Kraken REST API")
    print("=" * 70)

    # With since=60 days ago
    since_sec = int((datetime.utcnow() - timedelta(days=60)).timestamp())
    resp = requests.get(
        f"https://api.kraken.com/0/public/OHLC?pair=BTCUSDC&interval=5&since={since_sec}"
    )
    data = resp.json()
    if "error" in data and data["error"]:
        print(f"  API errors: {data['error']}")
    if "result" in data:
        key = [k for k in data["result"] if k != "last"][0]
        candles_raw = data["result"][key]
        print(f"  Direct API (since=60d ago): {len(candles_raw)} candles")
        if candles_raw:
            print(f"    First: {datetime.fromtimestamp(candles_raw[0][0])}")
            print(f"    Last: {datetime.fromtimestamp(candles_raw[-1][0])}")
        print(f"    'last' field: {data['result']['last']}")
        print(f"    'last' as date: {datetime.fromtimestamp(data['result']['last'])}")

    # Without since param
    resp2 = requests.get("https://api.kraken.com/0/public/OHLC?pair=BTCUSDC&interval=5")
    data2 = resp2.json()
    if "result" in data2:
        key2 = [k for k in data2["result"] if k != "last"][0]
        candles_raw2 = data2["result"][key2]
        print(f"  Direct API (no since): {len(candles_raw2)} candles")
        if candles_raw2:
            print(f"    First: {datetime.fromtimestamp(candles_raw2[0][0])}")
            print(f"    Last: {datetime.fromtimestamp(candles_raw2[-1][0])}")


def test_trades_workaround(ex):
    """TEST 6: Validate the trades-to-OHLCV workaround (THE FIX)."""
    print()
    print("=" * 70)
    print("TEST 6: TRADES WORKAROUND - fetch raw trades, build 5m candles")
    print("  (This is the fix implemented in refresh_training_data.py)")
    print("=" * 70)

    pair = "BTC/USDC"
    # Test with just 3 days to be quick
    test_days = 3
    since_ms = int((datetime.utcnow() - timedelta(days=test_days)).timestamp() * 1000)
    now_ms = int(datetime.utcnow().timestamp() * 1000)

    all_trades = []
    pages = 0

    print(f"  Fetching {test_days} days of trades for {pair}...")
    while since_ms < now_ms:
        try:
            trades = ex.fetch_trades(pair, since=since_ms, limit=1000)
        except Exception as e:
            print(f"  Error: {e}")
            break

        if not trades:
            since_ms += 3600 * 1000
            time.sleep(1)
            continue

        all_trades.extend(trades)
        pages += 1

        last_dt = datetime.fromtimestamp(trades[-1]['timestamp'] / 1000)
        if pages <= 5 or pages % 10 == 0:
            print(f"    Page {pages}: +{len(trades)} trades, total={len(all_trades)}, "
                  f"last={last_dt.strftime('%Y-%m-%d %H:%M')}")

        since_ms = trades[-1]['timestamp'] + 1

        if trades[-1]['timestamp'] > now_ms - 60000:
            break
        if pages > 100:
            print("    Hit 100-page safety cap")
            break

        time.sleep(max(ex.rateLimit / 1000.0, 1.0))

    if not all_trades:
        print("  NO TRADES RETURNED - workaround may not work for this pair")
        return

    # Build OHLCV candles
    trades_df = pd.DataFrame([{
        'timestamp': datetime.fromtimestamp(t['timestamp'] / 1000),
        'price': float(t['price']),
        'amount': float(t['amount']),
    } for t in all_trades])

    trades_df['timestamp'] = pd.to_datetime(trades_df['timestamp'])
    trades_df = trades_df.sort_values('timestamp')
    trades_df['candle'] = trades_df['timestamp'].dt.floor('5min')

    ohlcv = trades_df.groupby('candle').agg(
        open=('price', 'first'),
        high=('price', 'max'),
        low=('price', 'min'),
        close=('price', 'last'),
        volume=('amount', 'sum'),
    ).reset_index().rename(columns={'candle': 'timestamp'})

    span = (ohlcv['timestamp'].max() - ohlcv['timestamp'].min()).total_seconds() / 86400

    print(f"\n  RESULT:")
    print(f"    Raw trades fetched : {len(all_trades)} in {pages} pages")
    print(f"    5m candles built   : {len(ohlcv)}")
    print(f"    Span               : {span:.1f} days")
    print(f"    First candle       : {ohlcv['timestamp'].min()}")
    print(f"    Last candle        : {ohlcv['timestamp'].max()}")

    # Compare with OHLC endpoint
    ohlc_candles = ex.fetch_ohlcv(pair, "5m", limit=720)
    if ohlc_candles:
        print(f"\n  For comparison, OHLC endpoint returned: {len(ohlc_candles)} candles")
        ohlc_span = (ohlc_candles[-1][0] - ohlc_candles[0][0]) / 86400000
        print(f"    Span: {ohlc_span:.1f} days")

    if len(ohlcv) > 720:
        print(f"\n  SUCCESS: Trades workaround produced {len(ohlcv)} candles (>{720} OHLC cap)")
    else:
        print(f"\n  Note: {test_days} day test produced {len(ohlcv)} candles. "
              f"For 90 days, expect ~{int(len(ohlcv) / test_days * 90)} candles.")


def test_timeframes(ex):
    """TEST 7: Show available timeframes."""
    print()
    print("=" * 70)
    print("TEST 7: Available Kraken timeframes")
    print("=" * 70)
    print(f"  Timeframes: {ex.timeframes}")
    print()
    print("  Timeframe -> 720 candles covers:")
    tf_minutes = {'1m': 1, '5m': 5, '15m': 15, '30m': 30, '1h': 60, '4h': 240, '1d': 1440, '1w': 10080}
    for tf, mins in tf_minutes.items():
        if tf in (ex.timeframes or {}):
            days_covered = 720 * mins / (60 * 24)
            print(f"    {tf:>4s}: {days_covered:>6.1f} days")


if __name__ == "__main__":
    ex = test_5m_pagination()
    test_1h_pagination(ex)
    test_15m_pagination(ex)
    test_btc_usd(ex)
    test_direct_api()
    test_trades_workaround(ex)
    test_timeframes(ex)

    print()
    print("=" * 70)
    print("CONCLUSIONS")
    print("=" * 70)
    print("""
Based on Kraken API documentation (confirmed):
  - OHLC endpoint HARD CAPS at 720 candles for ALL timeframes
  - The 'since' parameter does NOT enable pagination past this limit
  - "Older data cannot be retrieved, regardless of the value of since"

The fix (implemented in refresh_training_data.py):
  - Use Kraken Trades endpoint (GET /0/public/Trades) which HAS full history
  - Paginate via the 'since' parameter (nanosecond UNIX timestamp)
  - Aggregate raw trades into 5-minute OHLCV candles locally
  - This is Kraken's officially recommended workaround

Fallback:
  - 1h OHLCV file also saved (720 candles = ~30 days)
  - Training pipeline (_load_pair_data) already supports _1h.csv fallback
""")
