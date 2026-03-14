#!/usr/bin/env python3
"""
SovereignForge AutoTuner -- Autonomous Strategy Parameter Optimization

Inspired by Karpathy's autoresearch loop. Runs unattended, automatically
experimenting with strategy parameters via backtesting.

Usage:
    python src/autotuner.py                          # Run until interrupted
    python src/autotuner.py --strategy grid           # Focus on one strategy
    python src/autotuner.py --max-experiments 100     # Run N experiments then stop
    python src/autotuner.py --resume                  # Resume from best config
"""

import asyncio
import copy
import json
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = PROJECT_ROOT / "config" / "trading_config.json"
RESULTS_PATH = PROJECT_ROOT / "data" / "autotuner_results.tsv"
BEST_CONFIG_PATH = PROJECT_ROOT / "config" / "trading_config_best.json"


# ---------------------------------------------------------------------------
# Mutable parameter definitions: (config_key_path, min, max, type, description)
# ---------------------------------------------------------------------------
PARAMETER_SPACE = {
    # Strategy weights (normalized after mutation so they sum to 1.0)
    'w_arbitrage':      ('strategies.arbitrage.weight',       0.05, 0.40, 'float', 'Arbitrage weight'),
    'w_fibonacci':      ('strategies.fibonacci.weight',       0.03, 0.25, 'float', 'Fibonacci weight'),
    'w_grid':           ('strategies.grid.weight',            0.05, 0.35, 'float', 'Grid weight'),
    'w_dca':            ('strategies.dca.weight',             0.03, 0.25, 'float', 'DCA weight'),
    'w_mean_reversion': ('strategies.mean_reversion.weight',  0.05, 0.35, 'float', 'Mean reversion weight'),
    'w_pairs_arbitrage':('strategies.pairs_arbitrage.weight', 0.03, 0.25, 'float', 'Pairs arb weight'),
    'w_momentum':       ('strategies.momentum.weight',        0.03, 0.30, 'float', 'Momentum weight'),
    # Risk parameters
    'kelly_fraction':   ('risk.kelly_fraction',               0.05, 0.50, 'float', 'Kelly fraction'),
    'stop_loss':        ('risk.stop_loss_percent',            1.0,  8.0,  'float', 'Stop loss %'),
    'take_profit':      ('risk.take_profit_percent',          1.5,  12.0, 'float', 'Take profit %'),
    # Grid strategy
    'grid_spacing':     ('strategies.grid.grid_spacing_pct',  0.5,  5.0,  'float', 'Grid spacing %'),
    'grid_levels':      ('strategies.grid.num_levels',        2,    8,    'int',   'Grid levels'),
    # Mean reversion
    'rsi_oversold':     ('strategies.mean_reversion.rsi_oversold',   15, 40, 'int', 'RSI oversold'),
    'rsi_overbought':   ('strategies.mean_reversion.rsi_overbought', 60, 85, 'int', 'RSI overbought'),
    # Momentum
    'ema_period':       ('strategies.momentum.ema_period',    5,  30, 'int', 'EMA period'),
    'adx_min':          ('strategies.momentum.adx_min',       15, 35, 'int', 'ADX minimum'),
    # Pairs arbitrage
    'zscore_threshold': ('strategies.pairs_arbitrage.zscore_threshold', 1.0, 3.5, 'float', 'Z-score threshold'),
    'spread_window':    ('strategies.pairs_arbitrage.spread_window',    20,  80,  'int',   'Spread window'),
    # DCA
    'dip_threshold':    ('strategies.dca.dip_threshold_pct',  1.0, 8.0, 'float', 'DCA dip threshold %'),
}


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def load_config(path: Path = CONFIG_PATH) -> dict:
    """Load trading config from JSON file."""
    with open(path) as f:
        return json.load(f)


def get_nested(d: dict, path: str):
    """Get a value from a nested dict using dot-separated path."""
    keys = path.split('.')
    current = d
    for k in keys:
        current = current[k]
    return current


def set_nested(d: dict, path: str, value):
    """Set a value in a nested dict using dot-separated path."""
    keys = path.split('.')
    current = d
    for k in keys[:-1]:
        current = current[k]
    current[keys[-1]] = value


def has_nested(d: dict, path: str) -> bool:
    """Check whether a dot-separated path exists in a nested dict."""
    keys = path.split('.')
    current = d
    for k in keys:
        if not isinstance(current, dict) or k not in current:
            return False
        current = current[k]
    return True


def normalize_weights(config: dict):
    """Normalize strategy weights so they sum to 1.0."""
    strategies = config.get('strategies', {})
    total = sum(
        s.get('weight', 0)
        for s in strategies.values()
        if isinstance(s, dict) and 'weight' in s
    )
    if total > 0:
        for s in strategies.values():
            if isinstance(s, dict) and 'weight' in s:
                s['weight'] = round(s['weight'] / total, 4)


# ---------------------------------------------------------------------------
# Mutation engine
# ---------------------------------------------------------------------------

def mutate_config(config: dict,
                  strategy_focus: Optional[str] = None) -> Tuple[dict, str]:
    """Mutate 1-2 random parameters in the config.

    Returns (mutated_config, human-readable description of changes).
    """
    mutated = copy.deepcopy(config)

    # Filter parameter keys to those that actually exist in this config
    available_keys = [
        k for k, (path, *_) in PARAMETER_SPACE.items()
        if has_nested(mutated, path)
    ]

    if strategy_focus:
        # Focus mutations on the specified strategy + risk params
        focused = [
            k for k in available_keys
            if strategy_focus in k or k.startswith(('kelly', 'stop', 'take'))
        ]
        if focused:
            available_keys = focused

    if not available_keys:
        return mutated, 'no mutable params found'

    # Usually mutate 1 param, sometimes 2
    n_mutations = random.choice([1, 1, 1, 2])
    chosen = random.sample(available_keys, min(n_mutations, len(available_keys)))

    changes: List[str] = []
    for key in chosen:
        path, lo, hi, ptype, desc = PARAMETER_SPACE[key]
        old_val = get_nested(mutated, path)

        if ptype == 'float':
            # Gaussian perturbation scaled to 15% of the valid range
            sigma = (hi - lo) * 0.15
            new_val = old_val + random.gauss(0, sigma)
            new_val = round(max(lo, min(hi, new_val)), 4)
        elif ptype == 'int':
            delta = random.choice([-2, -1, -1, 0, 1, 1, 2])
            new_val = max(lo, min(hi, int(old_val + delta)))
        else:
            new_val = old_val

        if new_val != old_val:
            set_nested(mutated, path, new_val)
            changes.append(f"{key}: {old_val} -> {new_val}")

    # Re-normalize weights if any were touched
    if any(k.startswith('w_') for k in chosen):
        normalize_weights(mutated)

    # --- Constraint: take_profit must be >= stop_loss * 0.5 ---
    if has_nested(mutated, 'risk.take_profit_percent') and has_nested(mutated, 'risk.stop_loss_percent'):
        tp = get_nested(mutated, 'risk.take_profit_percent')
        sl = get_nested(mutated, 'risk.stop_loss_percent')
        if tp < sl * 0.5:
            clamped = round(sl * 0.8, 2)
            set_nested(mutated, 'risk.take_profit_percent', clamped)
            changes.append(f"take_profit clamped to {clamped} (constraint)")

    # --- Constraint: rsi_oversold < rsi_overbought ---
    if (has_nested(mutated, 'strategies.mean_reversion.rsi_oversold') and
            has_nested(mutated, 'strategies.mean_reversion.rsi_overbought')):
        rsi_lo = get_nested(mutated, 'strategies.mean_reversion.rsi_oversold')
        rsi_hi = get_nested(mutated, 'strategies.mean_reversion.rsi_overbought')
        if rsi_lo >= rsi_hi:
            fixed = min(rsi_lo + 20, 85)
            set_nested(mutated, 'strategies.mean_reversion.rsi_overbought', fixed)
            changes.append(f"rsi_overbought clamped to {fixed} (constraint)")

    return mutated, '; '.join(changes) if changes else 'no change'


# ---------------------------------------------------------------------------
# Backtester evaluation wrapper
# ---------------------------------------------------------------------------

def _get_symbols_from_config(config: dict) -> List[str]:
    """Extract trading symbols from config."""
    return config.get('trading', {}).get(
        'enabled_pairs',
        ['BTC/USDC', 'ETH/USDC', 'XRP/USDC'],
    )


async def evaluate_config(config: dict) -> Dict[str, float]:
    """Run a full backtest with the given config and return metrics.

    Uses the project's ArbitrageBacktester with BacktestDataProvider.
    The backtester generates synthetic price data internally, so no
    external data files are required.
    """
    try:
        # Import backtester components -- these live in src/
        from backtester import ArbitrageBacktester, BacktestDataProvider
        from risk_management import create_default_risk_manager

        # Build risk manager seeded with the config's risk params
        risk_config = config.get('risk', {})
        risk_manager = create_default_risk_manager(risk_config)

        # Synthetic data provider (generates 60 days of 5-min candles)
        data_provider = BacktestDataProvider()

        backtester = ArbitrageBacktester(
            data_provider=data_provider,
            risk_manager=risk_manager,
        )

        # Backtest window: last 30 days of the generated data
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)

        symbols = _get_symbols_from_config(config)

        results = await backtester.run_backtest(
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            strategy_config=config.get('strategies'),
        )

        if 'error' in results:
            logger.warning(f"Backtest returned error: {results['error']}")
            return _empty_metrics()

        return {
            'sharpe':        results.get('sharpe_ratio', 0.0),
            'max_drawdown':  results.get('max_drawdown', 1.0),
            'win_rate':      results.get('win_rate', 0.0),
            'total_return':  results.get('total_return', 0.0),
            'total_trades':  results.get('total_trades', 0),
            'profit_factor': results.get('profit_factor', 0.0),
        }
    except Exception as e:
        logger.warning(f"Backtest failed: {e}", exc_info=True)
        return _empty_metrics()


def _empty_metrics() -> Dict[str, float]:
    return {
        'sharpe': -999.0,
        'max_drawdown': 1.0,
        'win_rate': 0.0,
        'total_return': 0.0,
        'total_trades': 0,
        'profit_factor': 0.0,
    }


# ---------------------------------------------------------------------------
# Fitness scoring
# ---------------------------------------------------------------------------

def compute_fitness(metrics: dict) -> float:
    """Compute composite fitness score from backtest metrics.

    Components (weighted):
        40%  Sharpe ratio     (normalized to [0, 1] over range [0, 3])
        30%  Drawdown penalty (1 - max_drawdown)
        20%  Win rate
        10%  Total return     (normalized to [0, 1] over range [0, 50%])

    A hard penalty halves the score when max drawdown exceeds 15%.
    Returns -1.0 for failed backtests or those with fewer than 5 trades.
    """
    if metrics['sharpe'] <= -999 or metrics['total_trades'] < 5:
        return -1.0

    sharpe_norm = max(0.0, min(metrics['sharpe'] / 3.0, 1.0))
    dd_norm     = max(0.0, 1.0 - metrics['max_drawdown'])
    wr_norm     = metrics['win_rate']
    ret_norm    = max(0.0, min(metrics['total_return'] / 0.5, 1.0))

    fitness = (sharpe_norm * 0.4
               + dd_norm * 0.3
               + wr_norm * 0.2
               + ret_norm * 0.1)

    # Hard drawdown penalty
    if metrics['max_drawdown'] > 0.15:
        fitness *= 0.5

    return round(fitness, 6)


# ---------------------------------------------------------------------------
# TSV logger
# ---------------------------------------------------------------------------

def log_result(experiment_id: int, fitness: float, metrics: dict,
               changes: str, kept: bool):
    """Append one experiment result to the TSV log file."""
    RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)

    header_needed = not RESULTS_PATH.exists()
    with open(RESULTS_PATH, 'a', encoding='utf-8') as f:
        if header_needed:
            f.write(
                "exp_id\ttimestamp\tfitness\tsharpe\tmax_dd\twin_rate"
                "\treturn\ttrades\tprofit_factor\tkept\tchanges\n"
            )
        # Escape tabs/newlines in the changes description
        safe_changes = changes.replace('\t', ' ').replace('\n', ' ')
        f.write(
            f"{experiment_id}\t{datetime.now().isoformat()}\t{fitness:.6f}\t"
            f"{metrics['sharpe']:.4f}\t{metrics['max_drawdown']:.4f}\t"
            f"{metrics['win_rate']:.4f}\t{metrics['total_return']:.4f}\t"
            f"{metrics['total_trades']}\t{metrics['profit_factor']:.4f}\t"
            f"{kept}\t{safe_changes}\n"
        )


def load_last_experiment_id() -> int:
    """Read the TSV to find the last experiment id (for --resume)."""
    if not RESULTS_PATH.exists():
        return 0
    last_id = 0
    with open(RESULTS_PATH, encoding='utf-8') as f:
        for line in f:
            parts = line.split('\t')
            if parts and parts[0].isdigit():
                last_id = max(last_id, int(parts[0]))
    return last_id


# ---------------------------------------------------------------------------
# Main autotuner loop
# ---------------------------------------------------------------------------

async def run_autotuner(strategy_focus: Optional[str] = None,
                        max_experiments: int = 0,
                        resume: bool = False):
    """Main autotuner loop. Runs until interrupted or max_experiments reached."""

    print("=" * 60)
    print("  SovereignForge AutoTuner")
    print("  Autonomous Strategy Parameter Optimization")
    print("=" * 60)
    print(f"  Focus: {strategy_focus or 'all strategies'}")
    print(f"  Max experiments: {max_experiments or 'unlimited'}")
    print(f"  Results: {RESULTS_PATH}")
    print(f"  Press Ctrl+C to stop")
    print("=" * 60)
    print()

    # Determine starting config
    if resume and BEST_CONFIG_PATH.exists():
        print(f"  Resuming from {BEST_CONFIG_PATH}")
        baseline_config = load_config(BEST_CONFIG_PATH)
    else:
        baseline_config = load_config(CONFIG_PATH)

    # Evaluate baseline
    print("Evaluating baseline config...", end=' ', flush=True)
    baseline_metrics = await evaluate_config(baseline_config)
    baseline_fitness = compute_fitness(baseline_metrics)
    print(
        f"fitness={baseline_fitness:.4f}  sharpe={baseline_metrics['sharpe']:.4f}  "
        f"dd={baseline_metrics['max_drawdown']:.4f}  trades={baseline_metrics['total_trades']}"
    )
    print()

    best_config  = copy.deepcopy(baseline_config)
    best_fitness = baseline_fitness
    best_metrics = baseline_metrics

    start_id = load_last_experiment_id() if resume else 0
    experiment_id = start_id
    improvements  = 0
    start_time    = time.time()

    try:
        while True:
            experiment_id += 1
            if max_experiments and (experiment_id - start_id) > max_experiments:
                break

            # 1. Propose a mutation
            mutated_config, changes = mutate_config(best_config, strategy_focus)

            if changes == 'no change':
                # Mutation was a no-op; skip evaluation
                continue

            # 2. Evaluate the mutant
            metrics = await evaluate_config(mutated_config)
            fitness = compute_fitness(metrics)

            # 3. Keep or revert
            kept = fitness > best_fitness
            if kept:
                best_config  = mutated_config
                best_fitness = fitness
                best_metrics = metrics
                improvements += 1
                marker = "  *** NEW BEST ***"

                # Persist best config
                BEST_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
                with open(BEST_CONFIG_PATH, 'w') as f:
                    json.dump(best_config, f, indent=2)
            else:
                marker = ""

            # 4. Log to TSV
            log_result(experiment_id, fitness, metrics, changes, kept)

            # 5. Print progress
            elapsed = time.time() - start_time
            n_done  = experiment_id - start_id
            rate    = n_done / (elapsed / 60) if elapsed > 0 else 0
            print(
                f"  [{experiment_id:>4}] fitness={fitness:.4f}  "
                f"sharpe={metrics['sharpe']:.4f}  dd={metrics['max_drawdown']:.3f}  "
                f"wr={metrics['win_rate']:.3f}  trades={metrics['total_trades']:>3}  "
                f"| best={best_fitness:.4f} ({improvements} improvements, "
                f"{rate:.1f}/min){marker}"
            )

    except KeyboardInterrupt:
        print("\n\nStopped by user.")

    # ----- Final summary -----
    elapsed = time.time() - start_time
    n_done  = experiment_id - start_id
    print()
    print("=" * 60)
    print("  AutoTuner Summary")
    print("=" * 60)
    print(f"  Experiments:   {n_done}")
    print(f"  Improvements:  {improvements} ({improvements / max(n_done, 1) * 100:.1f}%)")
    print(f"  Duration:      {elapsed / 60:.1f} minutes")
    print(f"  Best fitness:  {best_fitness:.4f} (baseline: {baseline_fitness:.4f})")
    print(f"  Best Sharpe:   {best_metrics['sharpe']:.4f}")
    print(f"  Best drawdown: {best_metrics['max_drawdown']:.4f}")
    print(f"  Best win rate: {best_metrics['win_rate']:.4f}")
    print(f"  Best return:   {best_metrics['total_return']:.4f}")
    print(f"  Best config:   {BEST_CONFIG_PATH}")
    print(f"  Results log:   {RESULTS_PATH}")
    print("=" * 60)

    return best_config


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description='SovereignForge AutoTuner -- autonomous strategy parameter optimization',
    )
    parser.add_argument(
        '--strategy', type=str, default=None,
        help='Focus mutations on a specific strategy (e.g., grid, mean_reversion, momentum)',
    )
    parser.add_argument(
        '--max-experiments', type=int, default=0,
        help='Maximum number of experiments to run (0 = unlimited)',
    )
    parser.add_argument(
        '--resume', action='store_true',
        help='Resume from the best config found in a previous run',
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s  %(levelname)-8s  %(name)s  %(message)s',
    )

    # Ensure src/ is on the import path so backtester / risk_management resolve
    src_dir = str(Path(__file__).resolve().parent)
    if src_dir not in sys.path:
        sys.path.insert(0, src_dir)

    asyncio.run(
        run_autotuner(
            strategy_focus=args.strategy,
            max_experiments=args.max_experiments,
            resume=args.resume,
        )
    )


if __name__ == '__main__':
    main()
