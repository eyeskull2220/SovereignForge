#!/usr/bin/env python3
"""
SovereignForge — Live Training Progress Monitor
Run in a separate terminal:  python training_monitor.py
"""

import os
import re
import sys
import time
from pathlib import Path

LOG_PATH = Path(__file__).parent / "logs" / "gpu_training.log"

COIN_ORDER = [
    "BTC/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC", "ETH/USDC",
    "ALGO/USDC", "ADA/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
    "XDC/USDC", "ONDO/USDC",
]
STRATEGIES = ["arbitrage", "fibonacci", "grid", "dca"]
EXCHANGES = ["binance", "coinbase", "kraken", "okx"]

# ANSI colors
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
DIM = "\033[2m"
BOLD = "\033[1m"
RESET = "\033[0m"
CLEAR_SCREEN = "\033[2J\033[H"


def parse_log():
    """Parse the log file for the current coin-by-coin run."""
    if not LOG_PATH.exists():
        return None

    with open(LOG_PATH, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    # Find start of coin-by-coin run
    start_idx = None
    for i, line in enumerate(lines):
        if "COIN-BY-COIN" in line:
            start_idx = i
    if start_idx is None:
        # Fall back to last "STARTING SOVEREIGNFORGE" block
        for i, line in enumerate(lines):
            if "STARTING SOVEREIGNFORGE" in line:
                start_idx = i
    if start_idx is None:
        start_idx = 0

    run_lines = lines[start_idx:]

    finished = []
    skipped = []
    current_model = None
    current_epoch = 0
    max_epoch = 200
    train_loss = 0.0
    val_loss = 0.0
    risk = 0.0
    current_strategy = ""
    current_exchange = ""
    lr = 0.0

    for line in run_lines:
        # Finished model
        m = re.search(r"Finished (\w+) for (.+?)@(.+?): val_loss=([\d.]+)", line)
        if m:
            finished.append({
                "strategy": m.group(1),
                "pair": m.group(2),
                "exchange": m.group(3),
                "val_loss": float(m.group(4)),
            })
            current_model = None
            continue

        # Skipped
        if "skipping" in line.lower() or "below minimum" in line.lower():
            m2 = re.search(r"for (.+?)@(.+?),", line)
            if m2:
                skipped.append({"pair": m2.group(1), "exchange": m2.group(2)})
            continue

        # Currently training
        m = re.search(r"Training (\w+) model for (.+?) on (\w+)", line)
        if m:
            current_strategy = m.group(1)
            current_model = m.group(2)
            current_exchange = m.group(3)
            current_epoch = 0
            continue

        # Strategy header
        m = re.search(r"Training (\w+) strategy", line)
        if m:
            current_strategy = m.group(1).lower()
            continue

        # Epoch progress
        m = re.search(
            r"epoch (\d+)/(\d+).*?train_loss=([\d.]+),\s*val_loss=([\d.]+),\s*risk=([\d.]+)",
            line,
        )
        if m:
            current_epoch = int(m.group(1))
            max_epoch = int(m.group(2))
            train_loss = float(m.group(3))
            val_loss = float(m.group(4))
            risk = float(m.group(5))
            continue

        # Early stopping
        m = re.search(r"Early stopping at epoch (\d+)", line)
        if m:
            current_epoch = int(m.group(1))
            continue

    return {
        "finished": finished,
        "skipped": skipped,
        "current_model": current_model,
        "current_strategy": current_strategy,
        "current_exchange": current_exchange,
        "current_epoch": current_epoch,
        "max_epoch": max_epoch,
        "train_loss": train_loss,
        "val_loss": val_loss,
        "risk": risk,
    }


def progress_bar(current, total, width=40):
    """Render a text progress bar."""
    if total == 0:
        return "[" + "." * width + "]"
    filled = int(width * current / total)
    bar = "#" * filled + "." * (width - filled)
    pct = current / total * 100
    return f"[{bar}] {pct:.0f}%"


def render(data):
    """Render the dashboard."""
    if data is None:
        return "Waiting for training log..."

    finished = data["finished"]
    skipped = data["skipped"]
    n_done = len(finished)
    n_skip = len(skipped)

    # Figure out current coin
    current_pair = data["current_model"] or "—"
    current_coin = current_pair.split("/")[0] if "/" in current_pair else current_pair
    coin_idx = next((i for i, c in enumerate(COIN_ORDER) if current_pair == c), -1)

    # Epoch bar
    ep = data["current_epoch"]
    mx = data["max_epoch"]
    ep_bar = progress_bar(ep, mx, 30)

    # Overall bar (estimate total trainable: ~16 per coin for 4 strategies × 4 exchanges, minus skips)
    # But we don't know exact total, so use finished count
    overall_bar = progress_bar(n_done, max(n_done + 4, 48), 40)

    lines = []
    lines.append(f"{BOLD}{CYAN}{'=' * 62}{RESET}")
    lines.append(f"{BOLD}{CYAN}  SOVEREIGNFORGE LIVE TRAINING MONITOR  (5m candles){RESET}")
    lines.append(f"{BOLD}{CYAN}{'=' * 62}{RESET}")
    lines.append("")

    # Current model
    strat = data["current_strategy"].upper() or "—"
    exch = data["current_exchange"].upper() or "—"
    if data["current_model"]:
        lines.append(f"  {BOLD}Coin:{RESET}     {current_pair}  ({coin_idx + 1}/12)")
        lines.append(f"  {BOLD}Strategy:{RESET} {strat}")
        lines.append(f"  {BOLD}Exchange:{RESET} {exch}")
        lines.append(f"  {BOLD}Epoch:{RESET}    {ep}/{mx}  {ep_bar}")
    else:
        lines.append(f"  {DIM}Between models...{RESET}")
    lines.append("")

    # Losses
    tl = data["train_loss"]
    vl = data["val_loss"]
    rk = data["risk"]
    risk_color = GREEN if rk < 0.3 else (YELLOW if rk < 0.65 else RED)
    loss_color = GREEN if vl < 0.05 else (YELLOW if vl < 0.15 else RED)
    lines.append(f"  {BOLD}Train Loss:{RESET} {tl:.6f}   {BOLD}Val Loss:{RESET} {loss_color}{vl:.6f}{RESET}   {BOLD}Risk:{RESET} {risk_color}{rk:.3f}{RESET}")
    lines.append("")

    # Overall progress
    lines.append(f"  {BOLD}Overall:{RESET}  {overall_bar}  {n_done} done, {n_skip} skipped")
    lines.append("")

    # Recent completions
    lines.append(f"  {BOLD}Recent completions:{RESET}")
    for m in finished[-8:]:
        vl_color = GREEN if m["val_loss"] < 0.05 else (YELLOW if m["val_loss"] < 0.15 else RED)
        lines.append(
            f"    {GREEN}✓{RESET} {m['pair']}@{m['exchange']} {m['strategy']:<12} "
            f"val_loss={vl_color}{m['val_loss']:.6f}{RESET}"
        )

    if skipped:
        lines.append("")
        lines.append(f"  {BOLD}Skipped ({n_skip}):{RESET}")
        for s in skipped[-4:]:
            lines.append(f"    {DIM}— {s['pair']}@{s['exchange']}{RESET}")

    lines.append("")
    lines.append(f"  {DIM}Coin order: BTC → XRP → XLM → HBAR → ETH → ALGO → ADA → LINK → IOTA → VET → XDC → ONDO{RESET}")
    lines.append(f"  {DIM}Ctrl+C to stop monitor (training continues){RESET}")

    return "\n".join(lines)


def main():
    refresh = 3  # seconds
    if len(sys.argv) > 1:
        try:
            refresh = int(sys.argv[1])
        except ValueError:
            pass

    print(f"Monitoring {LOG_PATH} every {refresh}s...\n")

    try:
        while True:
            data = parse_log()
            output = render(data)
            sys.stdout.write(CLEAR_SCREEN + output + "\n")
            sys.stdout.flush()
            time.sleep(refresh)
    except KeyboardInterrupt:
        print(f"\n{DIM}Monitor stopped. Training continues in background.{RESET}")


if __name__ == "__main__":
    main()
