#!/usr/bin/env python3
"""
SovereignForge - Dynamic Capital Allocator

Manages capital allocation across strategies for small-account snowballing.
Supports capital tiers, rolling Sharpe-based rebalancing, compounding,
and drawdown circuit breakers.
"""

import json
import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)


class CapitalTier(Enum):
    MICRO = "micro"       # $0 - $500
    SMALL = "small"       # $500 - $2000
    MEDIUM = "medium"     # $2000 - $5000
    STANDARD = "standard" # $5000+


@dataclass
class TierConfig:
    max_capital: Optional[float]
    max_position_pct: float
    max_positions: int
    max_strategies: int


TIER_CONFIGS = {
    CapitalTier.MICRO:    TierConfig(max_capital=500,  max_position_pct=0.04, max_positions=2, max_strategies=3),
    CapitalTier.SMALL:    TierConfig(max_capital=2000, max_position_pct=0.05, max_positions=3, max_strategies=3),
    CapitalTier.MEDIUM:   TierConfig(max_capital=5000, max_position_pct=0.03, max_positions=4, max_strategies=5),
    CapitalTier.STANDARD: TierConfig(max_capital=None, max_position_pct=0.02, max_positions=5, max_strategies=7),
}


@dataclass
class StrategyPerformance:
    """Tracks rolling performance for a single strategy."""
    name: str
    pnl_history: List[float] = field(default_factory=list)
    trade_timestamps: List[float] = field(default_factory=list)
    allocation: float = 0.0
    monthly_high: float = 0.0
    monthly_drawdown: float = 0.0
    halved: bool = False  # circuit breaker triggered

    def record_trade(self, pnl: float):
        self.pnl_history.append(pnl)
        self.trade_timestamps.append(time.time())
        # Keep last 200 trades
        if len(self.pnl_history) > 200:
            self.pnl_history = self.pnl_history[-200:]
            self.trade_timestamps = self.trade_timestamps[-200:]

    def rolling_sharpe(self, window_days: int = 30) -> float:
        """Compute Sharpe ratio over recent window."""
        cutoff = time.time() - window_days * 86400
        recent = [p for p, t in zip(self.pnl_history, self.trade_timestamps) if t >= cutoff]
        if len(recent) < 5:
            return 0.0
        returns = np.array(recent)
        mean_r = np.mean(returns)
        std_r = np.std(returns)
        if std_r == 0:
            return 0.0
        return float(mean_r / std_r * np.sqrt(len(recent)))

    def rolling_return(self, window_days: int = 30) -> float:
        """Total P&L over recent window."""
        cutoff = time.time() - window_days * 86400
        recent = [p for p, t in zip(self.pnl_history, self.trade_timestamps) if t >= cutoff]
        return sum(recent)


class CapitalAllocator:
    """
    Dynamic capital allocation across strategies.

    Features:
    - Capital tier detection (micro/small/medium/standard)
    - Rolling Sharpe-based weight rebalancing
    - Profit compounding back into strategy pools
    - Drawdown circuit breaker (5% monthly max per strategy)
    """

    MIN_CAPITAL_FLOOR = 150.0  # Halt all trading if capital drops below this (50% of $300)

    # Default persistence path (reports/capital_allocator_state.json)
    _DEFAULT_STATE_DIR = Path(__file__).resolve().parent.parent / "reports"

    def __init__(self, config: Dict[str, Any],
                 state_path: Optional[Path] = None):
        alloc_cfg = config.get('capital_allocation', {})
        self.initial_capital = alloc_cfg.get('initial_capital', 300.0)
        self.current_capital = self.initial_capital
        self.target_capital = alloc_cfg.get('target_capital', 5000.0)
        self.monthly_drawdown_limit = alloc_cfg.get('monthly_drawdown_limit_pct', 0.05)
        self.compounding_enabled = alloc_cfg.get('compounding_enabled', True)
        self.rebalance_interval_days = alloc_cfg.get('rebalance_interval_days', 90)
        self.min_allocation_pct = alloc_cfg.get('min_strategy_allocation_pct', 0.10)
        self.max_allocation_pct = alloc_cfg.get('max_strategy_allocation_pct', 0.50)

        # Persistence
        self._state_path = state_path or (self._DEFAULT_STATE_DIR / "capital_allocator_state.json")

        # Strategy tracking
        self.strategies: Dict[str, StrategyPerformance] = {}

        # Load strategy base weights from config
        self.base_weights: Dict[str, float] = {}
        for name, scfg in config.get('strategies', {}).items():
            if isinstance(scfg, dict) and scfg.get('enabled', True):
                self.base_weights[name] = scfg.get('weight', 0.1)

        self.last_rebalance = time.time()

        # Attempt to restore persisted state (non-fatal on failure)
        self.load_state()

        logger.info(f"CapitalAllocator initialized: ${self.initial_capital} capital, "
                    f"tier={self.get_tier().value}, {len(self.base_weights)} strategies")

    def get_tier(self) -> CapitalTier:
        """Determine current capital tier."""
        for tier in [CapitalTier.MICRO, CapitalTier.SMALL, CapitalTier.MEDIUM]:
            cfg = TIER_CONFIGS[tier]
            if cfg.max_capital is not None and self.current_capital <= cfg.max_capital:
                return tier
        return CapitalTier.STANDARD

    def get_tier_config(self) -> TierConfig:
        return TIER_CONFIGS[self.get_tier()]

    def get_active_strategy_count(self) -> int:
        """Max strategies allowed at current capital level."""
        return self.get_tier_config().max_strategies

    def can_trade(self) -> bool:
        """Pre-trade check: returns False when capital is below the minimum floor."""
        if self.current_capital < self.MIN_CAPITAL_FLOOR:
            logger.critical(f"Capital ${self.current_capital:.2f} below floor ${self.MIN_CAPITAL_FLOOR}. Trading BLOCKED.")
            return False
        return True

    def allocate(self) -> Dict[str, float]:
        """
        Compute dollar allocation per strategy based on tier, weights, and performance.
        Returns dict of strategy_name → allocation_usd.
        """
        if not self.can_trade():
            return {}

        tier_cfg = self.get_tier_config()
        max_strategies = tier_cfg.max_strategies

        # Get enabled strategies sorted by base weight (highest first)
        active = sorted(self.base_weights.items(), key=lambda x: -x[1])[:max_strategies]

        if not active:
            return {}

        # Compute performance-adjusted weights
        adjusted = {}
        for name, base_w in active:
            perf = self.strategies.get(name)
            if perf and perf.halved:
                # Circuit breaker: halved allocation
                adjusted[name] = base_w * 0.5
            elif perf and len(perf.pnl_history) >= 10:
                # Sharpe-adjusted: boost winners, reduce losers
                sharpe = perf.rolling_sharpe(30)
                multiplier = 1.0 + max(-0.5, min(0.5, sharpe * 0.2))
                adjusted[name] = base_w * multiplier
            else:
                adjusted[name] = base_w

        # Normalize weights to sum to 1.0, respecting min/max bounds
        total = sum(adjusted.values())
        if total <= 0:
            total = 1.0
        normalized = {k: v / total for k, v in adjusted.items()}

        # Clamp to bounds
        for name in normalized:
            normalized[name] = max(self.min_allocation_pct, min(self.max_allocation_pct, normalized[name]))

        # Re-normalize after clamping
        total = sum(normalized.values())
        normalized = {k: v / total for k, v in normalized.items()}

        # Convert to dollar amounts
        allocations = {name: self.current_capital * w for name, w in normalized.items()}

        # Update internal tracking
        for name, alloc in allocations.items():
            if name not in self.strategies:
                self.strategies[name] = StrategyPerformance(name=name)
            self.strategies[name].allocation = alloc

        self.save_state()
        return allocations

    def record_trade(self, strategy: str, pnl: float) -> None:
        """Record a trade result and compound if enabled."""
        if strategy not in self.strategies:
            self.strategies[strategy] = StrategyPerformance(name=strategy)

        perf = self.strategies[strategy]
        perf.record_trade(pnl)

        # Compound: add profit back to capital
        if self.compounding_enabled:
            self.current_capital += pnl

        # Minimum capital floor — halt all trading if breached
        if self.current_capital < self.MIN_CAPITAL_FLOOR:
            logger.critical(f"Capital ${self.current_capital:.2f} below floor ${self.MIN_CAPITAL_FLOOR}. HALTING all trading.")
            self.current_capital = max(self.current_capital, 0)
            # Halt all strategies
            for perf in self.strategies.values():
                perf.halved = True

        # Update monthly drawdown tracking
        if pnl > 0:
            perf.monthly_high = max(perf.monthly_high, perf.allocation)
        monthly_return = perf.rolling_return(30)
        if perf.allocation > 0:
            perf.monthly_drawdown = abs(min(0, monthly_return)) / perf.allocation

        # Circuit breaker check
        if perf.monthly_drawdown > self.monthly_drawdown_limit and not perf.halved:
            perf.halved = True
            logger.warning(f"Circuit breaker triggered for {strategy}: "
                          f"monthly drawdown {perf.monthly_drawdown:.1%} > {self.monthly_drawdown_limit:.1%}")

        self.save_state()

    def should_rebalance(self) -> bool:
        elapsed_days = (time.time() - self.last_rebalance) / 86400
        return elapsed_days >= self.rebalance_interval_days

    def rebalance(self):
        """Quarterly rebalance: reset circuit breakers, recalculate allocations."""
        for perf in self.strategies.values():
            perf.halved = False
            perf.monthly_high = perf.allocation
            perf.monthly_drawdown = 0.0

        self.last_rebalance = time.time()
        allocations = self.allocate()
        logger.info(f"Rebalanced allocations: {', '.join(f'{k}=${v:.0f}' for k, v in allocations.items())}")
        return allocations

    def get_position_size_pct(self) -> float:
        """Max position size as fraction of capital for current tier."""
        return self.get_tier_config().max_position_pct

    def get_max_positions(self) -> int:
        """Max open positions for current tier."""
        return self.get_tier_config().max_positions

    def get_status(self) -> Dict[str, Any]:
        tier = self.get_tier()
        tier_cfg = self.get_tier_config()
        allocations = self.allocate()
        return {
            'current_capital': self.current_capital,
            'initial_capital': self.initial_capital,
            'target_capital': self.target_capital,
            'growth_pct': ((self.current_capital - self.initial_capital) / self.initial_capital) * 100,
            'tier': tier.value,
            'max_position_pct': tier_cfg.max_position_pct,
            'max_positions': tier_cfg.max_positions,
            'max_strategies': tier_cfg.max_strategies,
            'allocations': allocations,
            'strategy_performance': {
                name: {
                    'sharpe_30d': perf.rolling_sharpe(30),
                    'return_30d': perf.rolling_return(30),
                    'trades': len(perf.pnl_history),
                    'monthly_drawdown': perf.monthly_drawdown,
                    'halved': perf.halved,
                }
                for name, perf in self.strategies.items()
            },
        }

    # ------------------------------------------------------------------
    # Persistence — save / load allocator state to JSON
    # ------------------------------------------------------------------

    def save_state(self):
        """Persist allocator state (capital, strategy performance, trade history) to disk.

        Uses atomic write-to-temp-then-rename to prevent corruption.
        """
        try:
            state = {
                'current_capital': self.current_capital,
                'initial_capital': self.initial_capital,
                'last_rebalance': self.last_rebalance,
                'strategies': {},
            }
            for name, perf in self.strategies.items():
                state['strategies'][name] = {
                    'name': perf.name,
                    'pnl_history': perf.pnl_history,
                    'trade_timestamps': perf.trade_timestamps,
                    'allocation': perf.allocation,
                    'monthly_high': perf.monthly_high,
                    'monthly_drawdown': perf.monthly_drawdown,
                    'halved': perf.halved,
                }

            self._state_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = self._state_path.with_suffix('.tmp')
            tmp_path.write_text(json.dumps(state, indent=2))
            tmp_path.replace(self._state_path)

            logger.debug(f"CapitalAllocator state saved to {self._state_path}")
        except Exception as e:
            logger.error(f"Failed to save allocator state: {e}")

    def load_state(self):
        """Restore allocator state from disk.  Non-fatal on any error."""
        if not self._state_path.exists():
            return

        try:
            with open(self._state_path) as f:
                state = json.load(f)

            self.current_capital = state.get('current_capital', self.current_capital)
            self.initial_capital = state.get('initial_capital', self.initial_capital)
            self.last_rebalance = state.get('last_rebalance', self.last_rebalance)

            for name, sdata in state.get('strategies', {}).items():
                perf = StrategyPerformance(
                    name=sdata.get('name', name),
                    pnl_history=sdata.get('pnl_history', []),
                    trade_timestamps=sdata.get('trade_timestamps', []),
                    allocation=sdata.get('allocation', 0.0),
                    monthly_high=sdata.get('monthly_high', 0.0),
                    monthly_drawdown=sdata.get('monthly_drawdown', 0.0),
                    halved=sdata.get('halved', False),
                )
                self.strategies[name] = perf

            logger.info(f"CapitalAllocator state restored: ${self.current_capital:.2f} capital, "
                        f"{len(self.strategies)} strategies")
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning(f"Corrupt allocator state file, starting fresh: {e}")
        except Exception as e:
            logger.error(f"Failed to load allocator state: {e}")
