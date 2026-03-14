#!/usr/bin/env python3
"""
Coin-by-coin training launcher for SovereignForge.
Trains each coin on all 4 exchanges, all 7 strategies, before moving to next coin.
Order: BTC -> XRP -> XLM -> HBAR -> ETH -> ALGO -> ADA -> LINK -> IOTA -> VET -> XDC -> ONDO
"""

import subprocess
import sys
import time
from datetime import datetime

COIN_ORDER = [
    "BTC/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC",
    "ETH/USDC", "ALGO/USDC", "ADA/USDC", "LINK/USDC",
    "IOTA/USDC", "VET/USDC", "XDC/USDC", "ONDO/USDC",
]

EXCHANGES = ["binance", "coinbase", "kraken", "okx"]

LOG_FILE = "logs/gpu_training.log"

def main():
    total = len(COIN_ORDER)
    start_time = time.time()

    print(f"\n{'='*60}")
    print(f"SovereignForge Coin-by-Coin Training")
    print(f"Coins: {total} | Exchanges: {len(EXCHANGES)} | Strategy: all")
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    for i, pair in enumerate(COIN_ORDER):
        coin = pair.split("/")[0]
        print(f"\n[{i+1}/{total}] Training {coin} on all exchanges, all strategies...")

        cmd = [
            sys.executable, "gpu_train.py",
            "--pairs", pair,
            "--strategy", "all",
            "--exchanges", *EXCHANGES,
            "--epochs", "200",
            "--batch-size", "96",
            "--learning-rate", "8e-5",
            "--seq-len", "128",
            "--memory-fraction", "0.82",
            "--mixed-precision",
            "--gpu-monitor",
        ]

        result = subprocess.run(
            cmd,
            cwd="E:/Users/Gino/Downloads/SovereignForge",
            capture_output=False,
        )

        if result.returncode != 0:
            print(f"  WARNING: {coin} training exited with code {result.returncode}")
        else:
            print(f"  {coin} training complete.")

        elapsed = time.time() - start_time
        avg_per_coin = elapsed / (i + 1)
        remaining = avg_per_coin * (total - i - 1)
        print(f"  Elapsed: {elapsed/60:.1f}m | Est. remaining: {remaining/60:.1f}m")

    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"All {total} coins trained in {total_time/60:.1f} minutes")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
