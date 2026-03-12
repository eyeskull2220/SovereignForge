#!/usr/bin/env python3
"""
SovereignForge — Real Historical Data Fetcher
Fetches genuine OHLCV data from live exchange APIs.

Primary source : Binance public REST API  (zero credentials required)
Fallback source: ccxt for Coinbase / Kraken (uses public endpoints only)

Usage
-----
  python fetch_real_historical_data.py                     # 2 years, all pairs
  python fetch_real_historical_data.py --years 3           # 3 years
  python fetch_real_historical_data.py --pairs XRP ADA     # specific pairs
  python fetch_real_historical_data.py --exchanges binance # one exchange only
  python fetch_real_historical_data.py --since 2022-01-01  # custom start date
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
import pandas as pd
import numpy as np

# tqdm is optional — plain print fallback if missing
try:
    from tqdm import tqdm
    _TQDM = True
except ImportError:
    _TQDM = False

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fetcher")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data" / "real_historical"

# All 10 MiCA-compliant USDC pairs
ALL_PAIRS: List[str] = [
    "BTC/USDC",
    "ETH/USDC",
    "XRP/USDC",
    "XLM/USDC",
    "HBAR/USDC",
    "ALGO/USDC",
    "ADA/USDC",
    "LINK/USDC",
    "IOTA/USDC",
    "VET/USDC",
]

# Binance uses different symbol conventions for some assets
BINANCE_SYMBOL_MAP: Dict[str, str] = {
    "XDC/USDC": "XDCUSDC",
    "IOTA/USDC": "IOTAUSDC",   # still listed as IOTA on Binance
    "ONDO/USDC": "ONDOUSDC",
    # all others follow the <BASE>USDC pattern automatically
}

# Not all pairs exist on all exchanges — skip gracefully
EXCHANGE_SKIP: Dict[str, List[str]] = {
    "coinbase": ["IOTA/USDC", "XDC/USDC", "ONDO/USDC", "HBAR/USDC"],
    "kraken":   ["IOTA/USDC", "XDC/USDC", "ONDO/USDC"],
}

# Binance REST base
BINANCE_REST = "https://api.binance.com"
BINANCE_KLINES = f"{BINANCE_REST}/api/v3/klines"
BINANCE_EXCHANGE_INFO = f"{BINANCE_REST}/api/v3/exchangeInfo"

# How many candles per request (Binance max = 1000)
BATCH_SIZE = 1000
# Pause between HTTP requests (stay well under rate limits)
REQUEST_DELAY = 0.12   # seconds


# ---------------------------------------------------------------------------
# Binance public REST fetcher (primary)
# ---------------------------------------------------------------------------

class BinanceFetcher:
    """
    Fetches OHLCV data from Binance public REST API.
    No API key required. Rate limit: ~1 200 req/min per IP.
    """

    def __init__(self, session: aiohttp.ClientSession):
        self._session = session
        self._valid_symbols: Optional[set] = None

    async def _load_symbols(self) -> set:
        if self._valid_symbols is not None:
            return self._valid_symbols
        try:
            async with self._session.get(BINANCE_EXCHANGE_INFO, timeout=aiohttp.ClientTimeout(total=15)) as r:
                data = await r.json()
            self._valid_symbols = {s["symbol"] for s in data.get("symbols", [])}
            logger.info(f"Binance: {len(self._valid_symbols)} symbols available")
        except Exception as e:
            logger.warning(f"Could not load Binance symbol list: {e} — will attempt fetch anyway")
            self._valid_symbols = set()
        return self._valid_symbols

    def _to_symbol(self, pair: str) -> str:
        if pair in BINANCE_SYMBOL_MAP:
            return BINANCE_SYMBOL_MAP[pair]
        return pair.replace("/", "")

    async def pair_exists(self, pair: str) -> bool:
        symbols = await self._load_symbols()
        sym = self._to_symbol(pair)
        if not symbols:
            return True   # unknown — try anyway
        return sym in symbols

    async def fetch(
        self,
        pair: str,
        since_ms: int,
        until_ms: int,
        interval: str = "1h",
    ) -> Optional[pd.DataFrame]:
        symbol = self._to_symbol(pair)

        if not await self.pair_exists(pair):
            logger.warning(f"Binance: {symbol} not found in symbol list — skipping")
            return None

        rows: List[List] = []
        current = since_ms

        while current < until_ms:
            params = {
                "symbol": symbol,
                "interval": interval,
                "startTime": current,
                "endTime": until_ms,
                "limit": BATCH_SIZE,
            }
            try:
                async with self._session.get(
                    BINANCE_KLINES,
                    params=params,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as resp:
                    if resp.status == 400:
                        err = await resp.text()
                        logger.warning(f"Binance 400 for {symbol}: {err}")
                        return None
                    if resp.status == 429:
                        logger.warning("Binance rate limit hit — sleeping 60s")
                        await asyncio.sleep(60)
                        continue
                    resp.raise_for_status()
                    batch = await resp.json()

            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Binance request failed for {symbol}: {e}")
                await asyncio.sleep(5)
                break

            if not batch:
                break

            rows.extend(batch)
            last_ts = batch[-1][0]
            current = last_ts + 3_600_000   # next hour in ms

            if len(batch) < BATCH_SIZE:
                break   # no more data

            await asyncio.sleep(REQUEST_DELAY)

        if not rows:
            return None

        df = pd.DataFrame(rows, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades",
            "taker_buy_base", "taker_buy_quote", "ignore",
        ])
        df = df[["timestamp", "open", "high", "low", "close", "volume"]].copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = _clean(df)
        logger.info(f"  Binance {pair}: {len(df):,} candles  "
                    f"[{df['timestamp'].min().date()} → {df['timestamp'].max().date()}]")
        return df


# ---------------------------------------------------------------------------
# CCXT fallback fetcher (Coinbase, Kraken)
# ---------------------------------------------------------------------------

class CcxtFetcher:
    """
    Fetches OHLCV data via ccxt for exchanges other than Binance.
    Uses public (unauthenticated) endpoints only.
    """

    _instances: Dict[str, object] = {}

    def __init__(self, exchange_name: str):
        self._name = exchange_name
        self._ex = None

    def _init(self):
        if self._ex is not None:
            return
        try:
            import ccxt
            cls = getattr(ccxt, self._name)
            self._ex = cls({
                "enableRateLimit": True,
                "timeout": 30000,
            })
            # Use sandbox=False — we only touch public endpoints
        except ImportError:
            raise RuntimeError("ccxt not installed — run: pip install ccxt>=4.3.0")
        except AttributeError:
            raise RuntimeError(f"ccxt has no exchange '{self._name}'")

    async def pair_exists(self, pair: str) -> bool:
        try:
            self._init()
            loop = asyncio.get_event_loop()
            markets = await loop.run_in_executor(None, self._ex.load_markets)
            return pair in markets
        except Exception:
            return False

    async def fetch(
        self,
        pair: str,
        since_ms: int,
        until_ms: int,
        interval: str = "1h",
    ) -> Optional[pd.DataFrame]:
        skip = EXCHANGE_SKIP.get(self._name, [])
        if pair in skip:
            return None

        try:
            self._init()
        except RuntimeError as e:
            logger.warning(str(e))
            return None

        loop = asyncio.get_event_loop()
        rows: List[List] = []
        current = since_ms

        while current < until_ms:
            try:
                batch = await loop.run_in_executor(
                    None,
                    lambda: self._ex.fetch_ohlcv(pair, interval, since=current, limit=BATCH_SIZE),
                )
            except Exception as e:
                logger.warning(f"  {self._name} {pair}: error — {e}")
                break

            if not batch:
                break

            rows.extend(batch)
            last_ts = batch[-1][0]
            current = last_ts + 3_600_000

            if len(batch) < BATCH_SIZE:
                break

            await asyncio.sleep(REQUEST_DELAY)

        if not rows:
            return None

        df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df = _clean(df)
        logger.info(f"  {self._name} {pair}: {len(df):,} candles  "
                    f"[{df['timestamp'].min().date()} → {df['timestamp'].max().date()}]")
        return df


# ---------------------------------------------------------------------------
# Data cleaning helper
# ---------------------------------------------------------------------------

def _clean(df: pd.DataFrame) -> pd.DataFrame:
    """Drop invalid rows, deduplicate, sort."""
    df = df.dropna(subset=["open", "high", "low", "close", "volume"])
    df = df[df["volume"] > 0]
    df = df[np.isfinite(df["close"])]
    df = df[df["close"] > 0]
    # Fix OHLC relationship violations
    df["high"] = df[["high", "open", "close"]].max(axis=1)
    df["low"]  = df[["low",  "open", "close"]].min(axis=1)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


# ---------------------------------------------------------------------------
# Main orchestrator
# ---------------------------------------------------------------------------

class DataFetchOrchestrator:

    def __init__(
        self,
        pairs: List[str],
        exchanges: List[str],
        since: datetime,
        until: datetime,
        data_dir: Path = DATA_DIR,
        interval: str = "1h",
        overwrite: bool = False,
    ):
        self.pairs = pairs
        self.exchanges = exchanges
        self.since_ms = int(since.timestamp() * 1000)
        self.until_ms = int(until.timestamp() * 1000)
        self.data_dir = data_dir
        self.interval = interval
        self.overwrite = overwrite
        self.results: Dict[str, Dict] = {}

    async def run(self) -> Dict:
        self.data_dir.mkdir(parents=True, exist_ok=True)

        since_dt = datetime.fromtimestamp(self.since_ms / 1000, tz=timezone.utc)
        until_dt = datetime.fromtimestamp(self.until_ms / 1000, tz=timezone.utc)
        logger.info(
            f"Fetching {len(self.pairs)} pairs × {len(self.exchanges)} exchanges  "
            f"[{since_dt.date()} → {until_dt.date()}]  interval={self.interval}"
        )

        connector = aiohttp.TCPConnector(limit=5, ssl=False)
        async with aiohttp.ClientSession(connector=connector) as session:
            binance_fetcher = BinanceFetcher(session)
            ccxt_fetchers = {
                ex: CcxtFetcher(ex)
                for ex in self.exchanges
                if ex != "binance"
            }

            total = len(self.exchanges) * len(self.pairs)
            done = 0

            for exchange in self.exchanges:
                ex_dir = self.data_dir / exchange
                ex_dir.mkdir(exist_ok=True)

                for pair in self.pairs:
                    done += 1
                    tag = f"[{done}/{total}] {exchange} {pair}"

                    filename = pair.replace("/", "_") + f"_{self.interval}.csv"
                    filepath = ex_dir / filename

                    # Skip if already exists and not overwriting
                    if filepath.exists() and not self.overwrite:
                        existing = pd.read_csv(filepath)
                        logger.info(f"  SKIP {filepath.name} ({len(existing):,} rows already present)")
                        self.results.setdefault(exchange, {})[pair] = {
                            "status": "skipped", "rows": len(existing), "path": str(filepath)
                        }
                        continue

                    logger.info(tag)

                    df = None
                    if exchange == "binance":
                        df = await binance_fetcher.fetch(pair, self.since_ms, self.until_ms, self.interval)
                    else:
                        df = await ccxt_fetchers[exchange].fetch(pair, self.since_ms, self.until_ms, self.interval)

                    if df is not None and len(df) >= 100:
                        df.to_csv(filepath, index=False)
                        self.results.setdefault(exchange, {})[pair] = {
                            "status": "ok",
                            "rows": len(df),
                            "start": str(df["timestamp"].min()),
                            "end": str(df["timestamp"].max()),
                            "path": str(filepath),
                        }
                    else:
                        rows = len(df) if df is not None else 0
                        logger.warning(f"  {exchange} {pair}: insufficient data ({rows} rows) — skipping")
                        self.results.setdefault(exchange, {})[pair] = {
                            "status": "no_data", "rows": rows
                        }

                    await asyncio.sleep(0.5)   # polite pause between pairs

        self._save_report()
        self._print_summary()
        return self.results

    def _save_report(self):
        report = {
            "generated_at": datetime.now(tz=timezone.utc).isoformat(),
            "since": datetime.fromtimestamp(self.since_ms / 1000, tz=timezone.utc).isoformat(),
            "until": datetime.fromtimestamp(self.until_ms / 1000, tz=timezone.utc).isoformat(),
            "interval": self.interval,
            "exchanges": self.results,
            "totals": {
                ex: {
                    "ok": sum(1 for v in pairs.values() if v["status"] == "ok"),
                    "total_rows": sum(v.get("rows", 0) for v in pairs.values()),
                }
                for ex, pairs in self.results.items()
            },
        }
        report_path = self.data_dir / "fetch_report.json"
        with open(report_path, "w") as f:
            json.dump(report, f, indent=2, default=str)
        logger.info(f"Report saved → {report_path}")

    def _print_summary(self):
        print("\n" + "=" * 60)
        print("FETCH SUMMARY")
        print("=" * 60)
        for exchange, pairs in self.results.items():
            ok = sum(1 for v in pairs.values() if v["status"] == "ok")
            total_rows = sum(v.get("rows", 0) for v in pairs.values())
            print(f"\n  {exchange.upper()}: {ok}/{len(pairs)} pairs   {total_rows:,} candles")
            for pair, info in pairs.items():
                status_icon = "✓" if info["status"] == "ok" else ("→" if info["status"] == "skipped" else "✗")
                rows = info.get("rows", 0)
                date_range = f"  [{info.get('start','')[:10]} → {info.get('end','')[:10]}]" if info["status"] == "ok" else ""
                print(f"    {status_icon} {pair:<15} {rows:>7,} rows{date_range}")
        print("=" * 60)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

async def main():
    parser = argparse.ArgumentParser(
        description="Fetch real historical OHLCV data for SovereignForge"
    )
    parser.add_argument(
        "--years", type=float, default=2.0,
        help="Years of history to fetch (default: 2)"
    )
    parser.add_argument(
        "--since", type=str, default=None,
        help="Custom start date YYYY-MM-DD (overrides --years)"
    )
    parser.add_argument(
        "--pairs", nargs="+", default=ALL_PAIRS,
        help="Pairs to fetch (default: all 10 MiCA pairs)"
    )
    parser.add_argument(
        "--exchanges", nargs="+", default=["binance", "coinbase", "kraken"],
        help="Exchanges to fetch from (default: binance coinbase kraken)"
    )
    parser.add_argument(
        "--interval", default="1h",
        help="Candle interval (default: 1h)"
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Re-fetch and overwrite existing files"
    )
    parser.add_argument(
        "--data-dir", default=str(DATA_DIR),
        help=f"Output directory (default: {DATA_DIR})"
    )
    args = parser.parse_args()

    now = datetime.now(tz=timezone.utc)
    if args.since:
        since = datetime.fromisoformat(args.since).replace(tzinfo=timezone.utc)
    else:
        since = now - timedelta(days=int(args.years * 365))

    # Normalise pair format (accept both XRP/USDC and XRP_USDC and XRPUSDC)
    pairs = []
    for p in args.pairs:
        p = p.upper().replace("_", "/")
        if "/" not in p and p.endswith("USDC"):
            p = p[:-4] + "/USDC"
        pairs.append(p)

    orchestrator = DataFetchOrchestrator(
        pairs=pairs,
        exchanges=[ex.lower() for ex in args.exchanges],
        since=since,
        until=now,
        data_dir=Path(args.data_dir),
        interval=args.interval,
        overwrite=args.overwrite,
    )
    await orchestrator.run()


if __name__ == "__main__":
    asyncio.run(main())
