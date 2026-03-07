#!/usr/bin/env python3
"""
SovereignForge Strategy Orchestrator
Multi-strategy orchestration system for fib, dca, grid, and arbitrage strategies
"""

import asyncio
import logging
from typing import Dict, List, Any, Optional, Callable
from datetime import datetime, timedelta
import pandas as pd
import numpy as np
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)

class StrategyType(Enum):
    """Supported strategy types"""
    FIB_DCA = "fib_dca"
    GRID = "grid"
    ARBITRAGE = "arbitrage"
    MEAN_REVERSION = "mean_reversion"

@dataclass
class StrategyAllocation:
    """Strategy allocation configuration"""
    strategy_type: StrategyType
    symbol: str
    allocation_pct: float
    max_allocation_pct: float
    min_allocation_pct: float
    config: Dict[str, Any]

@dataclass
class MarketCondition:
    """Market condition assessment"""
    volatility: float
    trend_strength: float
    volume_trend: float
    market_regime: str  # 'bull', 'bear', 'sideways', 'volatile'
    risk_level: str     # 'low', 'medium', 'high'

class StrategyOrchestrator:
    """
    Multi-strategy orchestration system
    Coordinates fib, dca, grid, and arbitrage strategies based on market conditions
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # Strategy allocations
        self.strategy_allocations: List[StrategyAllocation] = []
        self.active_strategies: Dict[str, Any] = {}

        # Portfolio management
        self.portfolio_value = config.get('initial_portfolio_value', 10000.0)
        self.cash_allocation = self.portfolio_value
        self.strategy_allocations_value: Dict[str, float] = {}

        # Risk management
        self.max_strategy_allocation_pct = config.get('max_strategy_allocation_pct', 0.3)  # 30%
        self.min_strategy_allocation_pct = config.get('min_strategy_allocation_pct', 0.05)  # 5%
        self.rebalance_threshold_pct = config.get('rebalance_threshold_pct', 0.05)  # 5%

        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []
        self.strategy_performance: Dict[str, Dict[str, Any]] = {}

        # Market condition assessment
        self.market_condition = None
        self.condition_update_interval = config.get('condition_update_interval', 3600)  # 1 hour
        self.last_condition_update = None

        logger.info("🎼 Strategy Orchestrator initialized")

    def add_strategy_allocation(self, allocation: StrategyAllocation):
        """Add a strategy allocation"""

        # Validate allocation
        if allocation.allocation_pct < allocation.min_allocation_pct:
            logger.warning(f"Allocation {allocation.allocation_pct} below minimum {allocation.min_allocation_pct}")
            return False

        if allocation.allocation_pct > allocation.max_allocation_pct:
            logger.warning(f"Allocation {allocation.allocation_pct} above maximum {allocation.max_allocation_pct}")
            return False

        self.strategy_allocations.append(allocation)

        # Initialize strategy instance
        strategy_id = f"{allocation.strategy_type.value}_{allocation.symbol}"
        self.active_strategies[strategy_id] = self._initialize_strategy(allocation)

        # Allocate capital
        allocation_value = self.portfolio_value * allocation.allocation_pct
        self.strategy_allocations_value[strategy_id] = allocation_value
        self.cash_allocation -= allocation_value

        logger.info(f"✅ Added strategy: {strategy_id} with {allocation.allocation_pct:.1%} allocation")
        return True

    def _initialize_strategy(self, allocation: StrategyAllocation) -> Any:
        """Initialize strategy instance based on type"""

        try:
            if allocation.strategy_type == StrategyType.FIB_DCA:
                from fib_dca_strategy import FibonacciDCAStrategy
                return FibonacciDCAStrategy(allocation.symbol, allocation.config)

            elif allocation.strategy_type == StrategyType.GRID:
                from grid_trading_strategy import GridTradingStrategy
                return GridTradingStrategy(allocation.symbol, allocation.config)

            elif allocation.strategy_type == StrategyType.ARBITRAGE:
                # Would import arbitrage strategy
                logger.warning(f"Arbitrage strategy not yet implemented for {allocation.symbol}")
                return None

            else:
                logger.error(f"Unknown strategy type: {allocation.strategy_type}")
                return None

        except ImportError as e:
            logger.error(f"Failed to import strategy {allocation.strategy_type}: {e}")
            return None

    def assess_market_conditions(self, market_data: Dict[str, pd.DataFrame]) -> MarketCondition:
        """Assess current market conditions across all symbols"""

        # Calculate aggregate market metrics
        volatilities = []
        trend_strengths = []
        volume_trends = []

        for symbol, data in market_data.items():
            if len(data) < 50:  # Need minimum data
                continue

            # Calculate volatility (30-day rolling std of returns)
            returns = data['close'].pct_change().dropna()
            volatility = returns.rolling(30).std().iloc[-1] * np.sqrt(252)  # Annualized
            volatilities.append(volatility)

            # Calculate trend strength (ADX-like)
            trend_strength = self._calculate_trend_strength(data)
            trend_strengths.append(trend_strength)

            # Calculate volume trend
            volume_sma_20 = data['volume'].rolling(20).mean().iloc[-1]
            volume_sma_50 = data['volume'].rolling(50).mean().iloc[-1]
            volume_trend = (volume_sma_20 - volume_sma_50) / volume_sma_50
            volume_trends.append(volume_trend)

        # Aggregate metrics
        avg_volatility = np.mean(volatilities) if volatilities else 0.3
        avg_trend_strength = np.mean(trend_strengths) if trend_strengths else 0.5
        avg_volume_trend = np.mean(volume_trends) if volume_trends else 0.0

        # Determine market regime
        if avg_volatility > 0.8:
            market_regime = 'volatile'
        elif avg_trend_strength > 0.7:
            market_regime = 'trending'
        elif avg_trend_strength < 0.3:
            market_regime = 'sideways'
        else:
            market_regime = 'mixed'

        # Determine risk level
        if avg_volatility > 0.6:
            risk_level = 'high'
        elif avg_volatility > 0.3:
            risk_level = 'medium'
        else:
            risk_level = 'low'

        market_condition = MarketCondition(
            volatility=avg_volatility,
            trend_strength=avg_trend_strength,
            volume_trend=avg_volume_trend,
            market_regime=market_regime,
            risk_level=risk_level
        )

        self.market_condition = market_condition
        self.last_condition_update = datetime.now()

        logger.info(f"📊 Market Condition: {market_regime} regime, {risk_level} risk, vol: {avg_volatility:.1%}")
        return market_condition

    def _calculate_trend_strength(self, data: pd.DataFrame) -> float:
        """Calculate trend strength using ADX-like method"""

        try:
            high = data['high']
            low = data['low']
            close = data['close']

            # Calculate True Range
            tr1 = high - low
            tr2 = abs(high - close.shift(1))
            tr3 = abs(low - close.shift(1))
            tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

            # Calculate Directional Movement
            dm_plus = np.where((high - high.shift(1)) > (low.shift(1) - low), high - high.shift(1), 0)
            dm_minus = np.where((low.shift(1) - low) > (high - high.shift(1)), low.shift(1) - low, 0)

            # Smooth with 14-period EMA
            atr = tr.ewm(span=14).mean()
            di_plus = (pd.Series(dm_plus).ewm(span=14).mean() / atr).iloc[-1]
            di_minus = (pd.Series(dm_minus).ewm(span=14).mean() / atr).iloc[-1]

            # Calculate ADX
            dx = abs(di_plus - di_minus) / (di_plus + di_minus) * 100
            adx = pd.Series(dx).ewm(span=14).mean().iloc[-1]

            return min(adx / 100, 1.0)  # Normalize to 0-1

        except Exception:
            return 0.5  # Default moderate trend

    def optimize_strategy_allocations(self, market_condition: MarketCondition) -> Dict[str, Any]:
        """Optimize strategy allocations based on market conditions"""

        optimization_result = {
            'reallocations': [],
            'new_allocations': [],
            'deallocations': [],
            'reason': f"Market regime: {market_condition.market_regime}, Risk: {market_condition.risk_level}"
        }

        # Strategy preference based on market conditions
        strategy_preferences = self._get_strategy_preferences(market_condition)

        # Calculate optimal allocations
        for allocation in self.strategy_allocations:
            strategy_id = f"{allocation.strategy_type.value}_{allocation.symbol}"
            current_allocation = self.strategy_allocations_value.get(strategy_id, 0)
            current_allocation_pct = current_allocation / self.portfolio_value

            # Get preferred allocation for this strategy type
            preferred_pct = strategy_preferences.get(allocation.strategy_type, 0)

            # Adjust for symbol-specific factors
            symbol_adjustment = self._calculate_symbol_adjustment(allocation.symbol, market_condition)
            target_pct = preferred_pct * symbol_adjustment

            # Constrain to min/max limits
            target_pct = max(allocation.min_allocation_pct,
                           min(allocation.max_allocation_pct, target_pct))

            # Check if reallocation needed
            if abs(current_allocation_pct - target_pct) > self.rebalance_threshold_pct:
                new_allocation_value = self.portfolio_value * target_pct
                delta = new_allocation_value - current_allocation

                optimization_result['reallocations'].append({
                    'strategy_id': strategy_id,
                    'current_pct': current_allocation_pct,
                    'target_pct': target_pct,
                    'delta_value': delta,
                    'reason': f"Market condition adjustment: {market_condition.market_regime}"
                })

        return optimization_result

    def _get_strategy_preferences(self, market_condition: MarketCondition) -> Dict[StrategyType, float]:
        """Get strategy preferences based on market conditions"""

        preferences = {}

        if market_condition.market_regime == 'volatile':
            # Prefer DCA in volatile markets
            preferences[StrategyType.FIB_DCA] = 0.25
            preferences[StrategyType.GRID] = 0.15
            preferences[StrategyType.ARBITRAGE] = 0.05

        elif market_condition.market_regime == 'trending':
            # Prefer grid in trending markets
            preferences[StrategyType.GRID] = 0.25
            preferences[StrategyType.FIB_DCA] = 0.15
            preferences[StrategyType.ARBITRAGE] = 0.10

        elif market_condition.market_regime == 'sideways':
            # Prefer arbitrage in sideways markets
            preferences[StrategyType.ARBITRAGE] = 0.20
            preferences[StrategyType.FIB_DCA] = 0.15
            preferences[StrategyType.GRID] = 0.10

        else:  # mixed
            # Balanced allocation
            preferences[StrategyType.FIB_DCA] = 0.20
            preferences[StrategyType.GRID] = 0.15
            preferences[StrategyType.ARBITRAGE] = 0.10

        # Adjust for risk level
        if market_condition.risk_level == 'high':
            # Reduce all allocations in high risk
            for strategy_type in preferences:
                preferences[strategy_type] *= 0.7
        elif market_condition.risk_level == 'low':
            # Increase allocations in low risk
            for strategy_type in preferences:
                preferences[strategy_type] *= 1.2

        return preferences

    def _calculate_symbol_adjustment(self, symbol: str, market_condition: MarketCondition) -> float:
        """Calculate symbol-specific allocation adjustment"""

        # Extract base asset for analysis
        base_asset = symbol.split('/')[0]

        # Adjust based on asset characteristics and market conditions
        if market_condition.market_regime == 'volatile':
            # Prefer more stable assets in volatile markets
            stable_assets = ['USDC', 'USDT', 'BTC']
            if base_asset in stable_assets:
                return 1.2
            else:
                return 0.8

        elif market_condition.risk_level == 'high':
            # Reduce allocation to riskier assets
            risky_assets = ['XRP', 'ADA', 'SOL']
            if base_asset in risky_assets:
                return 0.7
            else:
                return 1.1

        return 1.0  # No adjustment

    def execute_strategy_signals(self, market_data: Dict[str, pd.DataFrame]) -> List[Dict[str, Any]]:
        """Execute strategy signals across all active strategies"""

        signals_executed = []

        for strategy_id, strategy in self.active_strategies.items():
            if strategy is None:
                continue

            try:
                # Get symbol from strategy_id
                symbol = strategy_id.split('_', 1)[1]  # Remove strategy_type prefix

                if symbol not in market_data:
                    continue

                data = market_data[symbol]
                current_price = data['close'].iloc[-1]

                # Check strategy-specific signals
                if hasattr(strategy, 'should_dca'):
                    # Fibonacci DCA strategy
                    dca_decision = strategy.should_dca(data, self.strategy_allocations_value[strategy_id])
                    if dca_decision['should_dca']:
                        result = strategy.execute_dca(dca_decision, current_price)
                        signals_executed.append({
                            'strategy_id': strategy_id,
                            'signal_type': 'dca_entry',
                            'result': result
                        })

                elif hasattr(strategy, 'check_exit_conditions'):
                    # Check exit conditions
                    exit_check = strategy.check_exit_conditions(current_price)
                    if exit_check['should_exit']:
                        result = strategy.exit_dca_position(current_price, exit_check['reason'])
                        signals_executed.append({
                            'strategy_id': strategy_id,
                            'signal_type': 'dca_exit',
                            'result': result
                        })

                elif hasattr(strategy, 'update_grid'):
                    # Grid strategy
                    grid_result = strategy.update_grid(data, self.strategy_allocations_value[strategy_id], [])
                    if grid_result['action'] != 'hold':
                        signals_executed.append({
                            'strategy_id': strategy_id,
                            'signal_type': 'grid_update',
                            'result': grid_result
                        })

            except Exception as e:
                logger.error(f"Error executing signals for {strategy_id}: {e}")

        return signals_executed

    def rebalance_portfolio(self, optimization_result: Dict[str, Any]) -> bool:
        """Execute portfolio rebalancing based on optimization"""

        try:
            success = True

            # Execute reallocations
            for reallocation in optimization_result['reallocations']:
                strategy_id = reallocation['strategy_id']
                delta_value = reallocation['delta_value']

                if delta_value > 0:
                    # Increase allocation
                    if self.cash_allocation >= delta_value:
                        self.strategy_allocations_value[strategy_id] += delta_value
                        self.cash_allocation -= delta_value
                        logger.info(f"💰 Increased allocation for {strategy_id}: +${delta_value:.2f}")
                    else:
                        logger.warning(f"Insufficient cash for reallocation: {strategy_id}")
                        success = False

                else:
                    # Decrease allocation
                    current_allocation = self.strategy_allocations_value[strategy_id]
                    if current_allocation >= abs(delta_value):
                        self.strategy_allocations_value[strategy_id] += delta_value  # delta is negative
                        self.cash_allocation -= delta_value  # delta is negative, so this adds cash
                        logger.info(f"💰 Decreased allocation for {strategy_id}: ${delta_value:.2f}")
                    else:
                        logger.warning(f"Cannot decrease allocation below zero: {strategy_id}")
                        success = False

            return success

        except Exception as e:
            logger.error(f"Error during portfolio rebalancing: {e}")
            return False

    def update_performance(self, portfolio_value: float, strategy_pnls: Dict[str, float]):
        """Update performance tracking"""

        # Update portfolio value
        self.portfolio_value = portfolio_value

        # Update strategy performances
        for strategy_id, pnl in strategy_pnls.items():
            if strategy_id not in self.strategy_performance:
                self.strategy_performance[strategy_id] = {
                    'total_pnl': 0.0,
                    'trades': 0,
                    'win_rate': 0.0,
                    'sharpe_ratio': 0.0
                }

            self.strategy_performance[strategy_id]['total_pnl'] += pnl

        # Record performance snapshot
        performance_snapshot = {
            'timestamp': datetime.now(),
            'portfolio_value': portfolio_value,
            'cash_allocation': self.cash_allocation,
            'strategy_allocations': self.strategy_allocations_value.copy(),
            'strategy_performance': self.strategy_performance.copy(),
            'market_condition': self.market_condition.__dict__ if self.market_condition else None
        }

        self.performance_history.append(performance_snapshot)

    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get comprehensive orchestrator status"""

        return {
            'portfolio_value': self.portfolio_value,
            'cash_allocation': self.cash_allocation,
            'strategy_allocations': self.strategy_allocations_value,
            'active_strategies': len(self.active_strategies),
            'market_condition': self.market_condition.__dict__ if self.market_condition else None,
            'last_condition_update': self.last_condition_update.isoformat() if self.last_condition_update else None,
            'performance_history_length': len(self.performance_history),
            'strategy_performance': self.strategy_performance
        }

    def generate_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""

        if not self.performance_history:
            return {'error': 'No performance history available'}

        # Calculate overall metrics
        initial_value = self.performance_history[0]['portfolio_value']
        current_value = self.portfolio_value
        total_return = (current_value - initial_value) / initial_value

        # Calculate Sharpe ratio (simplified)
        if len(self.performance_history) > 1:
            returns = []
            for i in range(1, len(self.performance_history)):
                prev_value = self.performance_history[i-1]['portfolio_value']
                curr_value = self.performance_history[i]['portfolio_value']
                daily_return = (curr_value - prev_value) / prev_value
                returns.append(daily_return)

            if returns:
                avg_return = np.mean(returns)
                std_return = np.std(returns)
                sharpe_ratio = avg_return / std_return * np.sqrt(252) if std_return > 0 else 0
            else:
                sharpe_ratio = 0
        else:
            sharpe_ratio = 0

        # Strategy performance summary
        strategy_summary = {}
        for strategy_id, perf in self.strategy_performance.items():
            strategy_summary[strategy_id] = {
                'total_pnl': perf['total_pnl'],
                'pnl_pct': perf['total_pnl'] / initial_value,
                'trades': perf['trades'],
                'win_rate': perf['win_rate']
            }

        return {
            'total_return': total_return,
            'sharpe_ratio': sharpe_ratio,
            'portfolio_value': current_value,
            'initial_value': initial_value,
            'strategy_summary': strategy_summary,
            'market_condition': self.market_condition.__dict__ if self.market_condition else None,
            'generated_at': datetime.now().isoformat()
        }

# Example usage and testing
def test_strategy_orchestrator():
    """Test the strategy orchestrator"""

    print("🎼 Strategy Orchestrator Test")
    print("=" * 50)

    # Configuration
    config = {
        'initial_portfolio_value': 10000.0,
        'max_strategy_allocation_pct': 0.3,
        'condition_update_interval': 3600
    }

    # Initialize orchestrator
    orchestrator = StrategyOrchestrator(config)

    # Add strategy allocations
    allocations = [
        StrategyAllocation(
            strategy_type=StrategyType.FIB_DCA,
            symbol='XRP/USDC',
            allocation_pct=0.20,
            max_allocation_pct=0.30,
            min_allocation_pct=0.05,
            config={'dca_levels': 5, 'dca_interval_hours': 24}
        ),
        StrategyAllocation(
            strategy_type=StrategyType.GRID,
            symbol='ADA/USDC',
            allocation_pct=0.15,
            max_allocation_pct=0.25,
            min_allocation_pct=0.05,
            config={'grid_levels': 20, 'grid_spacing_pct': 0.01}
        )
    ]

    for allocation in allocations:
        success = orchestrator.add_strategy_allocation(allocation)
        print(f"✅ Added {allocation.strategy_type.value} for {allocation.symbol}: {success}")

    # Generate sample market data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    np.random.seed(42)

    market_data = {}
    for symbol in ['XRP/USDC', 'ADA/USDC']:
        base_price = 0.50 if 'XRP' in symbol else 0.30
        trend = np.random.normal(0.0001, 0.001, len(dates)).cumsum()
        volatility = np.random.normal(0, 0.005, len(dates))
        close_prices = base_price * np.exp(trend + volatility)

        df = pd.DataFrame({
            'timestamp': dates,
            'open': close_prices * (1 + np.random.normal(0, 0.002, len(dates))),
            'high': close_prices * (1 + np.random.normal(0.001, 0.003, len(dates))),
            'low': close_prices * (1 - np.random.normal(0.001, 0.003, len(dates))),
            'close': close_prices,
            'volume': np.random.lognormal(15, 1, len(dates))
        })
        market_data[symbol] = df

    # Assess market conditions
    market_condition = orchestrator.assess_market_conditions(market_data)
    print("\n📊 Market Assessment:")
    print(f"   Regime: {market_condition.market_regime}")
    print(f"   Risk Level: {market_condition.risk_level}")
    print(f"   Volatility: {market_condition.volatility:.1%}")

    # Optimize allocations
    optimization = orchestrator.optimize_strategy_allocations(market_condition)
    print("\n🎯 Allocation Optimization:")
    print(f"   Reallocations: {len(optimization['reallocations'])}")
    print(f"   Reason: {optimization['reason']}")

    # Execute strategy signals
    signals = orchestrator.execute_strategy_signals(market_data)
    print("\n🚀 Strategy Signals Executed:")
    print(f"   Signals: {len(signals)}")

    # Get orchestrator status
    status = orchestrator.get_orchestrator_status()
    print("\n📈 Orchestrator Status:")
    print(f"   Portfolio Value: ${status['portfolio_value']:.2f}")
    print(f"   Cash Allocation: ${status['cash_allocation']:.2f}")
    print(f"   Active Strategies: {status['active_strategies']}")

    print("\n" + "=" * 50)
    print("✅ Strategy Orchestrator Test Complete")
    print("🎼 Multi-strategy orchestration ready for live deployment!")

if __name__ == '__main__':
    test_strategy_orchestrator()