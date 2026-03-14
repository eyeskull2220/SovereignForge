#!/usr/bin/env python3
"""
SovereignForge - Evolutionary Swarm Optimizer
Population-based evolutionary search over the 19-dimensional strategy parameter
space.  Uses the ArbitrageBacktester for fitness evaluation and persists every
experiment to a Research DAG (JSON knowledge graph) for reproducibility.

Usage:
    python src/swarm_optimizer.py "maximize Sharpe ratio"
    python src/swarm_optimizer.py "minimize drawdown" --population 30 --generations 100
    python src/swarm_optimizer.py "conservative growth" --apply-best
"""

from __future__ import annotations

import argparse
import asyncio
import copy
import json
import logging
import math
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

# ---------------------------------------------------------------------------
# Resolve project paths so imports work from any cwd
# ---------------------------------------------------------------------------
_SRC_DIR = Path(__file__).resolve().parent
_PROJECT_ROOT = _SRC_DIR.parent
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from backtester import ArbitrageBacktester, BacktestDataProvider
from risk_management import create_default_risk_manager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parameter space definition (19 tunable parameters)
# ---------------------------------------------------------------------------
PARAM_SPEC: List[Dict[str, Any]] = [
    # --- 7 strategy weights (simplex, sum to 1.0) ---
    {"name": "w_arbitrage",       "group": "weight", "type": "simplex", "init": 0.20, "min": 0.02, "max": 0.60},
    {"name": "w_fibonacci",       "group": "weight", "type": "simplex", "init": 0.10, "min": 0.02, "max": 0.40},
    {"name": "w_grid",            "group": "weight", "type": "simplex", "init": 0.18, "min": 0.02, "max": 0.50},
    {"name": "w_dca",             "group": "weight", "type": "simplex", "init": 0.10, "min": 0.02, "max": 0.40},
    {"name": "w_mean_reversion",  "group": "weight", "type": "simplex", "init": 0.17, "min": 0.02, "max": 0.50},
    {"name": "w_pairs_arbitrage", "group": "weight", "type": "simplex", "init": 0.12, "min": 0.02, "max": 0.40},
    {"name": "w_momentum",        "group": "weight", "type": "simplex", "init": 0.13, "min": 0.02, "max": 0.50},
    # --- 4 risk parameters ---
    {"name": "kelly_fraction",    "group": "risk", "type": "float", "init": 0.25, "min": 0.05, "max": 0.50},
    {"name": "position_size_pct", "group": "risk", "type": "float", "init": 2.0,  "min": 0.5,  "max": 5.0},
    {"name": "stop_loss_pct",     "group": "risk", "type": "float", "init": 3.0,  "min": 1.0,  "max": 8.0},
    {"name": "take_profit_pct",   "group": "risk", "type": "float", "init": 4.0,  "min": 1.5,  "max": 12.0},
    # --- 8 strategy-specific parameters ---
    {"name": "grid_spacing_pct",  "group": "strategy", "type": "float", "init": 1.5, "min": 0.5, "max": 5.0},
    {"name": "grid_num_levels",   "group": "strategy", "type": "int",   "init": 3,   "min": 2,   "max": 8},
    {"name": "grid_atr_mult",     "group": "strategy", "type": "float", "init": 1.5, "min": 0.5, "max": 3.0},
    {"name": "rsi_oversold",      "group": "strategy", "type": "int",   "init": 25,  "min": 15,  "max": 40},
    {"name": "rsi_overbought",    "group": "strategy", "type": "int",   "init": 75,  "min": 60,  "max": 85},
    {"name": "ema_period",        "group": "strategy", "type": "int",   "init": 12,  "min": 5,   "max": 30},
    {"name": "dip_threshold_pct", "group": "strategy", "type": "float", "init": 3.0, "min": 1.0, "max": 8.0},
    {"name": "zscore_threshold",  "group": "strategy", "type": "float", "init": 2.0, "min": 1.0, "max": 3.5},
]

WEIGHT_NAMES = [p["name"] for p in PARAM_SPEC if p["group"] == "weight"]
STRATEGY_KEY_MAP = {
    "w_arbitrage": "arbitrage",
    "w_fibonacci": "fibonacci",
    "w_grid": "grid",
    "w_dca": "dca",
    "w_mean_reversion": "mean_reversion",
    "w_pairs_arbitrage": "pairs_arbitrage",
    "w_momentum": "momentum",
}

DAG_PATH = _PROJECT_ROOT / "data" / "swarm_research_dag.json"
OPTIMIZED_CONFIG_PATH = _PROJECT_ROOT / "config" / "trading_config_optimized.json"


# ===================================================================
# Individual (a single candidate parameter set)
# ===================================================================

class Individual:
    """A single parameter-set candidate in the swarm population."""

    __slots__ = ("params", "fitness", "metrics", "uid", "parents", "mutations",
                 "generation")

    def __init__(self, params: Dict[str, float], generation: int = 0):
        self.params: Dict[str, float] = params
        self.fitness: float = -math.inf
        self.metrics: Dict[str, float] = {}
        self.uid: str = uuid.uuid4().hex[:12]
        self.parents: List[str] = []
        self.mutations: List[str] = []
        self.generation: int = generation

    # ---- serialisation helpers ----
    def to_dict(self) -> Dict[str, Any]:
        return {
            "uid": self.uid,
            "generation": self.generation,
            "params": self.params,
            "fitness": self.fitness,
            "metrics": self.metrics,
            "parents": self.parents,
            "mutations": self.mutations,
        }

    def copy(self) -> "Individual":
        ind = Individual(dict(self.params), self.generation)
        ind.fitness = self.fitness
        ind.metrics = dict(self.metrics)
        ind.parents = list(self.parents)
        ind.mutations = list(self.mutations)
        return ind


# ===================================================================
# Fitness evaluator
# ===================================================================

def _build_strategy_config(params: Dict[str, float]) -> Dict[str, Any]:
    """Convert flat param dict into the nested config the backtester expects."""
    config: Dict[str, Any] = {
        "risk": {
            "kelly_fraction": params["kelly_fraction"],
            "max_single_position_risk_percent": params["position_size_pct"],
            "stop_loss_percent": params["stop_loss_pct"],
            "take_profit_percent": params["take_profit_pct"],
        },
        "strategies": {},
    }
    for wname, skey in STRATEGY_KEY_MAP.items():
        entry: Dict[str, Any] = {"enabled": True, "weight": params[wname]}
        # Strategy-specific sub-params
        if skey == "grid":
            entry["grid_spacing_pct"] = params["grid_spacing_pct"]
            entry["num_levels"] = int(params["grid_num_levels"])
            entry["atr_multiplier"] = params["grid_atr_mult"]
        elif skey == "mean_reversion":
            entry["bb_threshold"] = 0.8
            entry["rsi_oversold"] = int(params["rsi_oversold"])
            entry["rsi_overbought"] = int(params["rsi_overbought"])
        elif skey == "momentum":
            entry["ema_period"] = int(params["ema_period"])
            entry["adx_min"] = 22
        elif skey == "dca":
            entry["dip_threshold_pct"] = params["dip_threshold_pct"]
        elif skey == "pairs_arbitrage":
            entry["zscore_threshold"] = params["zscore_threshold"]
            entry["spread_window"] = 40
            entry["exit_zscore"] = 0.5
        config["strategies"][skey] = entry
    return config


async def evaluate_individual(
    ind: Individual,
    data_provider: BacktestDataProvider,
    symbols: List[str],
    start_date: datetime,
    end_date: datetime,
    objective: str,
) -> float:
    """Run a backtest for *ind* and return scalar fitness."""
    strategy_config = _build_strategy_config(ind.params)
    risk_cfg = {
        "max_single_trade": ind.params["position_size_pct"] / 100.0,
        "kelly_fraction": ind.params["kelly_fraction"],
        "stop_loss_pct": ind.params["stop_loss_pct"],
        "take_profit_pct": ind.params["take_profit_pct"],
    }
    risk_manager = create_default_risk_manager(risk_cfg)
    backtester = ArbitrageBacktester(data_provider, risk_manager)

    try:
        results = await backtester.run_backtest(
            symbols, start_date, end_date, strategy_config,
        )
    except Exception as exc:
        logger.warning("Backtest failed for %s: %s", ind.uid, exc)
        ind.fitness = -math.inf
        ind.metrics = {}
        return ind.fitness

    if "error" in results:
        ind.fitness = -math.inf
        ind.metrics = {"error": str(results["error"])}
        return ind.fitness

    sharpe = results.get("sharpe_ratio", 0.0)
    max_dd = results.get("max_drawdown", 1.0)
    win_rate = results.get("win_rate", 0.0)
    total_ret = results.get("total_return", 0.0)

    # Composite fitness
    fitness = (
        sharpe * 0.4
        + (1.0 - max_dd) * 0.3
        + win_rate * 0.2
        + total_ret * 0.1
    )

    # Penalty for excessive drawdown
    if max_dd > 0.15:
        fitness -= (max_dd - 0.15) * 5.0

    # Objective-specific adjustments
    obj = objective.lower()
    if "drawdown" in obj or "minimize" in obj:
        fitness = (1.0 - max_dd) * 0.6 + sharpe * 0.2 + win_rate * 0.1 + total_ret * 0.1
        if max_dd > 0.10:
            fitness -= (max_dd - 0.10) * 8.0
    elif "conservative" in obj:
        fitness = (1.0 - max_dd) * 0.4 + sharpe * 0.3 + win_rate * 0.2 + total_ret * 0.1
        if max_dd > 0.12:
            fitness -= (max_dd - 0.12) * 6.0

    ind.fitness = fitness
    ind.metrics = {
        "sharpe_ratio": sharpe,
        "max_drawdown": max_dd,
        "win_rate": win_rate,
        "total_return": total_ret,
        "total_trades": results.get("total_trades", 0),
        "final_value": results.get("final_portfolio_value", 0.0),
    }
    return fitness


# ===================================================================
# Evolutionary operators
# ===================================================================

def _clip(val: float, spec: Dict) -> float:
    return max(spec["min"], min(spec["max"], val))


def _normalize_simplex(params: Dict[str, float]) -> None:
    """Re-normalise the 7 weight params so they sum to 1.0."""
    total = sum(params[w] for w in WEIGHT_NAMES)
    if total <= 0:
        equal = 1.0 / len(WEIGHT_NAMES)
        for w in WEIGHT_NAMES:
            params[w] = equal
    else:
        for w in WEIGHT_NAMES:
            params[w] /= total


def mutate(ind: Individual, sigma: float, rng: np.random.Generator) -> Individual:
    """Type-aware mutation: floats get Gaussian noise, ints get discrete delta,
    simplex weights are perturbed in log-space then re-normalised."""
    child = ind.copy()
    child.uid = uuid.uuid4().hex[:12]
    child.parents = [ind.uid]
    child.mutations = []

    for spec in PARAM_SPEC:
        name = spec["name"]
        if rng.random() > 0.4:  # 40% chance per gene
            continue

        if spec["type"] == "simplex":
            # Perturb in log-space
            log_val = math.log(max(child.params[name], 1e-6))
            log_val += rng.normal(0, sigma)
            child.params[name] = max(spec["min"], min(spec["max"], math.exp(log_val)))
            child.mutations.append(f"{name}:log_perturb")

        elif spec["type"] == "float":
            span = spec["max"] - spec["min"]
            delta = rng.normal(0, sigma * span)
            child.params[name] = _clip(child.params[name] + delta, spec)
            child.mutations.append(f"{name}:gauss({delta:+.4f})")

        elif spec["type"] == "int":
            delta = rng.choice([-2, -1, 0, 1, 2])
            child.params[name] = _clip(child.params[name] + delta, spec)
            child.params[name] = round(child.params[name])
            child.mutations.append(f"{name}:int_delta({delta:+d})")

    _normalize_simplex(child.params)
    return child


def crossover(
    parent_a: Individual, parent_b: Individual, rng: np.random.Generator,
) -> Individual:
    """Uniform crossover: each gene independently picked from either parent."""
    child_params: Dict[str, float] = {}
    for spec in PARAM_SPEC:
        name = spec["name"]
        if rng.random() < 0.5:
            child_params[name] = parent_a.params[name]
        else:
            child_params[name] = parent_b.params[name]
    _normalize_simplex(child_params)
    child = Individual(child_params)
    child.parents = [parent_a.uid, parent_b.uid]
    child.mutations = ["crossover"]
    return child


def tournament_select(
    population: List[Individual], k: int, rng: np.random.Generator,
) -> Individual:
    """Tournament selection: pick k random individuals, return the best."""
    candidates = rng.choice(len(population), size=min(k, len(population)), replace=False)
    best = max(candidates, key=lambda i: population[i].fitness)
    return population[best]


# ===================================================================
# Research DAG (knowledge graph)
# ===================================================================

class ResearchDAG:
    """Persists every experiment and generation stats to a JSON DAG."""

    def __init__(self, path: Path = DAG_PATH):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with open(self.path) as f:
                self.data = json.load(f)
        else:
            self.data = {
                "meta": {
                    "created": datetime.now().isoformat(),
                    "description": "SovereignForge Swarm Optimizer Research DAG",
                },
                "experiments": [],
                "generation_stats": [],
                "convergence_history": [],
                "synthesis_insights": [],
            }

    def record_experiment(self, ind: Individual) -> None:
        self.data["experiments"].append(ind.to_dict())

    def record_generation(
        self, gen: int, best: float, mean: float, std: float,
        best_uid: str, pop_size: int, sigma: float,
    ) -> None:
        self.data["generation_stats"].append({
            "generation": gen,
            "best_fitness": best,
            "mean_fitness": mean,
            "std_fitness": std,
            "best_uid": best_uid,
            "population_size": pop_size,
            "mutation_sigma": sigma,
            "timestamp": datetime.now().isoformat(),
        })
        self.data["convergence_history"].append({
            "generation": gen,
            "best": best,
            "mean": mean,
        })

    def synthesize(self, gen: int, population: List[Individual]) -> None:
        """Generate synthesis insights every N generations."""
        if not population:
            return

        # Parameter correlations with fitness
        fitnesses = np.array([ind.fitness for ind in population if ind.fitness > -math.inf])
        if len(fitnesses) < 5:
            return

        correlations: Dict[str, float] = {}
        for spec in PARAM_SPEC:
            name = spec["name"]
            values = np.array([
                ind.params[name] for ind in population if ind.fitness > -math.inf
            ])
            if len(values) == len(fitnesses) and np.std(values) > 1e-10:
                corr = float(np.corrcoef(values, fitnesses)[0, 1])
                correlations[name] = round(corr, 4)

        # Convergence detection: std of top 5 fitnesses
        top_fitnesses = sorted(fitnesses, reverse=True)[:5]
        convergence_spread = float(np.std(top_fitnesses)) if len(top_fitnesses) > 1 else 0.0
        is_converged = convergence_spread < 0.01

        # Top-3 parameter ranges
        top_inds = sorted(population, key=lambda i: i.fitness, reverse=True)[:3]
        param_ranges: Dict[str, Dict[str, float]] = {}
        for spec in PARAM_SPEC:
            name = spec["name"]
            vals = [ind.params[name] for ind in top_inds]
            param_ranges[name] = {
                "min": round(min(vals), 6),
                "max": round(max(vals), 6),
                "mean": round(sum(vals) / len(vals), 6),
            }

        insight = {
            "generation": gen,
            "timestamp": datetime.now().isoformat(),
            "parameter_fitness_correlations": correlations,
            "convergence_spread": round(convergence_spread, 6),
            "is_converged": is_converged,
            "top3_parameter_ranges": param_ranges,
        }
        self.data["synthesis_insights"].append(insight)

    def save(self) -> None:
        with open(self.path, "w") as f:
            json.dump(self.data, f, indent=2, default=str)


# ===================================================================
# SwarmOptimizer
# ===================================================================

class SwarmOptimizer:
    """Population-based evolutionary optimizer for the 19-parameter space."""

    def __init__(
        self,
        objective: str = "maximize Sharpe ratio",
        population_size: int = 20,
        generations: int = 50,
        elite_count: int = 3,
        tournament_k: int = 3,
        sigma_start: float = 0.15,
        sigma_end: float = 0.03,
        stall_threshold: int = 5,
        seed: int = 42,
        symbols: Optional[List[str]] = None,
        backtest_days: int = 45,
    ):
        self.objective = objective
        self.pop_size = population_size
        self.generations = generations
        self.elite_count = min(elite_count, population_size)
        self.tournament_k = tournament_k
        self.sigma_start = sigma_start
        self.sigma_end = sigma_end
        self.stall_threshold = stall_threshold
        self.rng = np.random.default_rng(seed)
        self.symbols = symbols or ["BTC/USDC", "ETH/USDC", "XRP/USDC"]
        self.backtest_days = backtest_days

        self.population: List[Individual] = []
        self.best_ever: Optional[Individual] = None
        self.dag = ResearchDAG()
        self.data_provider: Optional[BacktestDataProvider] = None

    # ----------------------------------------------------------------
    # Population initialisation
    # ----------------------------------------------------------------

    def _seed_from_config(self) -> Dict[str, float]:
        """Load current trading config as the seed individual."""
        config_path = _PROJECT_ROOT / "config" / "trading_config.json"
        if not config_path.exists():
            return {spec["name"]: spec["init"] for spec in PARAM_SPEC}

        with open(config_path) as f:
            cfg = json.load(f)

        params: Dict[str, float] = {}
        strats = cfg.get("strategies", {})
        risk = cfg.get("risk", {})
        trading = cfg.get("trading", {})

        for spec in PARAM_SPEC:
            name = spec["name"]
            if name.startswith("w_"):
                skey = STRATEGY_KEY_MAP[name]
                params[name] = strats.get(skey, {}).get("weight", spec["init"])
            elif name == "kelly_fraction":
                params[name] = risk.get("kelly_fraction", spec["init"])
            elif name == "position_size_pct":
                params[name] = trading.get("max_position_size_percent",
                               risk.get("max_single_position_risk_percent", spec["init"]))
            elif name == "stop_loss_pct":
                params[name] = risk.get("stop_loss_percent", spec["init"])
            elif name == "take_profit_pct":
                params[name] = risk.get("take_profit_percent", spec["init"])
            elif name == "grid_spacing_pct":
                params[name] = strats.get("grid", {}).get("grid_spacing_pct", spec["init"])
            elif name == "grid_num_levels":
                params[name] = strats.get("grid", {}).get("num_levels", spec["init"])
            elif name == "grid_atr_mult":
                params[name] = strats.get("grid", {}).get("atr_multiplier", spec["init"])
            elif name == "rsi_oversold":
                params[name] = strats.get("mean_reversion", {}).get("rsi_oversold", spec["init"])
            elif name == "rsi_overbought":
                params[name] = strats.get("mean_reversion", {}).get("rsi_overbought", spec["init"])
            elif name == "ema_period":
                params[name] = strats.get("momentum", {}).get("ema_period", spec["init"])
            elif name == "dip_threshold_pct":
                params[name] = strats.get("dca", {}).get("dip_threshold_pct", spec["init"])
            elif name == "zscore_threshold":
                params[name] = strats.get("pairs_arbitrage", {}).get("zscore_threshold", spec["init"])
            else:
                params[name] = spec["init"]

        _normalize_simplex(params)
        return params

    def _init_population(self) -> None:
        """Create initial population: config seed + (pop_size - 1) noisy variants."""
        seed_params = self._seed_from_config()
        seed_ind = Individual(seed_params, generation=0)
        self.population = [seed_ind]

        for _ in range(self.pop_size - 1):
            noisy = dict(seed_params)
            for spec in PARAM_SPEC:
                name = spec["name"]
                if spec["type"] == "simplex":
                    log_val = math.log(max(noisy[name], 1e-6))
                    log_val += self.rng.normal(0, self.sigma_start * 0.8)
                    noisy[name] = max(spec["min"], min(spec["max"], math.exp(log_val)))
                elif spec["type"] == "float":
                    span = spec["max"] - spec["min"]
                    noisy[name] = _clip(
                        noisy[name] + self.rng.normal(0, self.sigma_start * span * 0.5), spec,
                    )
                elif spec["type"] == "int":
                    noisy[name] = _clip(
                        noisy[name] + self.rng.choice([-2, -1, 0, 1, 2]), spec,
                    )
                    noisy[name] = round(noisy[name])
            _normalize_simplex(noisy)
            self.population.append(Individual(noisy, generation=0))

    # ----------------------------------------------------------------
    # Adaptive mutation rate
    # ----------------------------------------------------------------

    def _sigma(self, gen: int) -> float:
        """Linear annealing from sigma_start to sigma_end."""
        if self.generations <= 1:
            return self.sigma_start
        t = gen / (self.generations - 1)
        return self.sigma_start + (self.sigma_end - self.sigma_start) * t

    # ----------------------------------------------------------------
    # Diversity injection on stall
    # ----------------------------------------------------------------

    def _inject_diversity(self, gen: int) -> None:
        """Replace the bottom quarter of the population with fresh random
        individuals when the search stalls."""
        n_replace = max(2, self.pop_size // 4)
        self.population.sort(key=lambda i: i.fitness, reverse=True)
        seed_params = self._seed_from_config()

        for idx in range(self.pop_size - n_replace, self.pop_size):
            noisy = dict(seed_params)
            for spec in PARAM_SPEC:
                name = spec["name"]
                span = spec["max"] - spec["min"]
                if spec["type"] == "simplex":
                    log_val = math.log(max(spec["init"], 1e-6))
                    log_val += self.rng.normal(0, 0.3)
                    noisy[name] = max(spec["min"], min(spec["max"], math.exp(log_val)))
                elif spec["type"] == "float":
                    noisy[name] = _clip(spec["init"] + self.rng.normal(0, 0.25 * span), spec)
                elif spec["type"] == "int":
                    noisy[name] = _clip(spec["init"] + self.rng.integers(-3, 4), spec)
                    noisy[name] = round(noisy[name])
            _normalize_simplex(noisy)
            self.population[idx] = Individual(noisy, generation=gen)
            self.population[idx].mutations = ["diversity_injection"]

        logger.info("[gen %d] Diversity injection: replaced %d individuals", gen, n_replace)

    # ----------------------------------------------------------------
    # Main evolution loop
    # ----------------------------------------------------------------

    async def run(self) -> Individual:
        """Execute the full evolutionary optimisation loop.  Returns the
        best Individual found."""
        t0 = time.time()
        logger.info(
            "SwarmOptimizer starting | objective=%r  pop=%d  gens=%d  symbols=%s",
            self.objective, self.pop_size, self.generations, self.symbols,
        )

        # Data provider (shared across all evaluations for speed)
        self.data_provider = BacktestDataProvider()
        end_date = datetime.now()
        start_date = end_date - timedelta(days=self.backtest_days)

        # Initialise population
        self._init_population()
        stall_counter = 0
        prev_best = -math.inf

        for gen in range(self.generations):
            sigma = self._sigma(gen)
            gen_t0 = time.time()

            # --- Evaluate all individuals ---
            for ind in self.population:
                if ind.fitness == -math.inf:
                    ind.generation = gen
                    await evaluate_individual(
                        ind, self.data_provider, self.symbols,
                        start_date, end_date, self.objective,
                    )
                    self.dag.record_experiment(ind)

            # --- Sort by fitness ---
            self.population.sort(key=lambda i: i.fitness, reverse=True)

            # Track best-ever
            if self.best_ever is None or self.population[0].fitness > self.best_ever.fitness:
                self.best_ever = self.population[0].copy()

            # Generation stats
            fitnesses = [i.fitness for i in self.population if i.fitness > -math.inf]
            gen_best = max(fitnesses) if fitnesses else -math.inf
            gen_mean = float(np.mean(fitnesses)) if fitnesses else 0.0
            gen_std = float(np.std(fitnesses)) if fitnesses else 0.0

            self.dag.record_generation(
                gen, gen_best, gen_mean, gen_std,
                self.population[0].uid, len(self.population), sigma,
            )

            gen_elapsed = time.time() - gen_t0
            logger.info(
                "[gen %d/%d] best=%.4f  mean=%.4f  std=%.4f  sigma=%.4f  (%.1fs)",
                gen + 1, self.generations, gen_best, gen_mean, gen_std,
                sigma, gen_elapsed,
            )
            if self.best_ever and self.best_ever.metrics:
                m = self.best_ever.metrics
                logger.info(
                    "  best-ever | sharpe=%.3f  dd=%.3f  wr=%.3f  ret=%.3f",
                    m.get("sharpe_ratio", 0), m.get("max_drawdown", 0),
                    m.get("win_rate", 0), m.get("total_return", 0),
                )

            # Stall detection
            if gen_best <= prev_best:
                stall_counter += 1
            else:
                stall_counter = 0
            prev_best = gen_best

            if stall_counter >= self.stall_threshold:
                self._inject_diversity(gen)
                stall_counter = 0

            # Synthesis every 10 generations
            if (gen + 1) % 10 == 0 or gen == self.generations - 1:
                self.dag.synthesize(gen, self.population)

            # --- Selection + reproduction ---
            if gen < self.generations - 1:
                next_pop: List[Individual] = []

                # Elite preservation
                for i in range(self.elite_count):
                    elite = self.population[i].copy()
                    elite.generation = gen + 1
                    next_pop.append(elite)

                # Fill rest via tournament selection -> crossover -> mutation
                while len(next_pop) < self.pop_size:
                    parent_a = tournament_select(self.population, self.tournament_k, self.rng)
                    parent_b = tournament_select(self.population, self.tournament_k, self.rng)
                    child = crossover(parent_a, parent_b, self.rng)
                    child = mutate(child, sigma, self.rng)
                    child.generation = gen + 1
                    child.fitness = -math.inf  # force re-evaluation
                    next_pop.append(child)

                self.population = next_pop

        # Final save
        self.dag.save()
        elapsed = time.time() - t0
        logger.info(
            "Evolution complete in %.1fs | best fitness=%.4f", elapsed,
            self.best_ever.fitness if self.best_ever else -math.inf,
        )
        return self.best_ever

    # ----------------------------------------------------------------
    # Config writeback
    # ----------------------------------------------------------------

    def apply_best(self) -> str:
        """Write the best-ever params to trading_config_optimized.json and
        return a human-readable diff summary."""
        if self.best_ever is None:
            return "No best individual found -- nothing to apply."

        # Load current config as baseline
        config_path = _PROJECT_ROOT / "config" / "trading_config.json"
        with open(config_path) as f:
            baseline = json.load(f)
        optimized = copy.deepcopy(baseline)

        params = self.best_ever.params
        diffs: List[str] = []

        # Weights
        for wname, skey in STRATEGY_KEY_MAP.items():
            old = optimized.get("strategies", {}).get(skey, {}).get("weight", 0)
            new = round(params[wname], 4)
            if abs(old - new) > 1e-6:
                diffs.append(f"  strategies.{skey}.weight: {old:.4f} -> {new:.4f}")
            optimized.setdefault("strategies", {}).setdefault(skey, {})["weight"] = new

        # Risk params
        risk_map = [
            ("kelly_fraction", "kelly_fraction"),
            ("position_size_pct", "max_single_position_risk_percent"),
            ("stop_loss_pct", "stop_loss_percent"),
            ("take_profit_pct", "take_profit_percent"),
        ]
        for pname, cname in risk_map:
            old = optimized.get("risk", {}).get(cname, 0)
            new = round(params[pname], 4)
            if abs(old - new) > 1e-4:
                diffs.append(f"  risk.{cname}: {old} -> {new}")
            optimized.setdefault("risk", {})[cname] = new

        # Strategy-specific
        strat_map = [
            ("grid_spacing_pct", "grid", "grid_spacing_pct"),
            ("grid_num_levels", "grid", "num_levels"),
            ("grid_atr_mult", "grid", "atr_multiplier"),
            ("rsi_oversold", "mean_reversion", "rsi_oversold"),
            ("rsi_overbought", "mean_reversion", "rsi_overbought"),
            ("ema_period", "momentum", "ema_period"),
            ("dip_threshold_pct", "dca", "dip_threshold_pct"),
            ("zscore_threshold", "pairs_arbitrage", "zscore_threshold"),
        ]
        for pname, skey, cname in strat_map:
            old = optimized.get("strategies", {}).get(skey, {}).get(cname, 0)
            spec = next(s for s in PARAM_SPEC if s["name"] == pname)
            new = int(params[pname]) if spec["type"] == "int" else round(params[pname], 4)
            if old != new:
                diffs.append(f"  strategies.{skey}.{cname}: {old} -> {new}")
            optimized.setdefault("strategies", {}).setdefault(skey, {})[cname] = new

        # Add metadata
        optimized["_swarm_meta"] = {
            "optimized_at": datetime.now().isoformat(),
            "objective": self.objective,
            "best_fitness": round(self.best_ever.fitness, 6),
            "metrics": {k: round(v, 6) if isinstance(v, float) else v
                        for k, v in self.best_ever.metrics.items()},
            "generations_run": self.generations,
            "population_size": self.pop_size,
        }

        OPTIMIZED_CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(OPTIMIZED_CONFIG_PATH, "w") as f:
            json.dump(optimized, f, indent=2)

        summary_lines = [
            f"Optimized config written to {OPTIMIZED_CONFIG_PATH}",
            f"Objective: {self.objective}",
            f"Best fitness: {self.best_ever.fitness:.4f}",
        ]
        if self.best_ever.metrics:
            m = self.best_ever.metrics
            summary_lines.append(
                f"Metrics: sharpe={m.get('sharpe_ratio', 0):.3f}  "
                f"dd={m.get('max_drawdown', 0):.3f}  "
                f"wr={m.get('win_rate', 0):.3f}  "
                f"ret={m.get('total_return', 0):.3f}"
            )
        if diffs:
            summary_lines.append("Parameter changes:")
            summary_lines.extend(diffs)
        else:
            summary_lines.append("No parameter changes from baseline.")

        summary = "\n".join(summary_lines)
        logger.info(summary)
        return summary


# ===================================================================
# CLI entry point
# ===================================================================

def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="SovereignForge Swarm Optimizer -- evolutionary parameter search",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/swarm_optimizer.py "maximize Sharpe ratio"
  python src/swarm_optimizer.py "minimize drawdown" --population 30 --generations 100
  python src/swarm_optimizer.py "conservative growth" --apply-best
        """,
    )
    parser.add_argument(
        "objective", type=str,
        help='Optimisation objective (e.g. "maximize Sharpe ratio", "minimize drawdown")',
    )
    parser.add_argument("--population", type=int, default=20, help="Population size (default: 20)")
    parser.add_argument("--generations", type=int, default=50, help="Number of generations (default: 50)")
    parser.add_argument("--elite", type=int, default=3, help="Elite preservation count (default: 3)")
    parser.add_argument("--tournament-k", type=int, default=3, help="Tournament selection size (default: 3)")
    parser.add_argument("--sigma-start", type=float, default=0.15, help="Initial mutation rate (default: 0.15)")
    parser.add_argument("--sigma-end", type=float, default=0.03, help="Final mutation rate (default: 0.03)")
    parser.add_argument("--stall", type=int, default=5, help="Stall threshold for diversity injection (default: 5)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed (default: 42)")
    parser.add_argument("--symbols", nargs="+", default=None, help="Trading pairs to backtest")
    parser.add_argument("--days", type=int, default=45, help="Backtest window in days (default: 45)")
    parser.add_argument("--apply-best", action="store_true", help="Write best params to config file")
    return parser.parse_args(argv)


async def async_main(argv: Optional[List[str]] = None) -> None:
    args = parse_args(argv)

    optimizer = SwarmOptimizer(
        objective=args.objective,
        population_size=args.population,
        generations=args.generations,
        elite_count=args.elite,
        tournament_k=args.tournament_k,
        sigma_start=args.sigma_start,
        sigma_end=args.sigma_end,
        stall_threshold=args.stall,
        seed=args.seed,
        symbols=args.symbols,
        backtest_days=args.days,
    )

    best = await optimizer.run()

    # Print final summary
    print("\n" + "=" * 60)
    print("SWARM OPTIMISATION COMPLETE")
    print("=" * 60)
    if best:
        print(f"Objective:    {args.objective}")
        print(f"Best fitness: {best.fitness:.4f}")
        if best.metrics:
            m = best.metrics
            print(f"Sharpe:       {m.get('sharpe_ratio', 0):.4f}")
            print(f"Max DD:       {m.get('max_drawdown', 0):.4f}")
            print(f"Win rate:     {m.get('win_rate', 0):.4f}")
            print(f"Total return: {m.get('total_return', 0):.4f}")
            print(f"Total trades: {m.get('total_trades', 0)}")
        print(f"\nBest params:")
        for spec in PARAM_SPEC:
            name = spec["name"]
            val = best.params[name]
            fmt = f"{val:.4f}" if spec["type"] != "int" else f"{int(val)}"
            print(f"  {name:25s} = {fmt}")
    else:
        print("No valid solution found.")

    print(f"\nResearch DAG saved to: {DAG_PATH}")

    if args.apply_best:
        print("\n" + "-" * 60)
        summary = optimizer.apply_best()
        print(summary)


def main(argv: Optional[List[str]] = None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    asyncio.run(async_main(argv))


if __name__ == "__main__":
    main()
