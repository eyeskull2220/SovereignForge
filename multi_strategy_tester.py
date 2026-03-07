#!/usr/bin/env python3
"""
SovereignForge Multi-Strategy Tester
24-hour live validation of all strategies across MiCA-compliant pairs
Comprehensive performance analysis before model retraining
"""

import asyncio
import logging
import time
import json
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from collections import defaultdict
import numpy as np

from live_data_fetcher import get_live_data_fetcher, TickerData
from fib_dca_strategy import FibonacciDCAStrategy
from grid_trading_strategy import GridTradingStrategy
from arbitrage_detector import ArbitrageDetector
from paper_trading_simulator import PaperTradingSimulator, Position, TradeResult

logger = logging.getLogger(__name__)

@dataclass
class StrategyMetrics:
    """Performance metrics for a strategy"""
    strategy_name: str
    pair: str
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    total_pnl: float = 0.0
    total_pnl_pct: float = 0.0
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    win_rate: float = 0.0
    avg_trade_pnl: float = 0.0
    best_trade: float = 0.0
    worst_trade: float = 0.0
    total_volume: float = 0.0
    start_time: float = field(default_factory=time.time)
    end_time: float = 0.0

    def calculate_metrics(self, trades: List[TradeResult], price_history: List[Tuple[float, float]]):
        """Calculate performance metrics"""
        if not trades:
            return

        self.end_time = time.time()

        # Basic trade metrics
        self.total_trades = len(trades)
        pnls = []

        for trade in trades:
            if trade.side == 'sell':  # Assuming we track closing trades
                # This is simplified - in real implementation, match buy/sell pairs
                pnl = (trade.price - trades[max(0, trades.index(trade)-1)].price) * trade.quantity
                pnls.append(pnl)
                self.total_pnl += pnl

        if pnls:
            self.winning_trades = sum(1 for pnl in pnls if pnl > 0)
            self.losing_trades = sum(1 for pnl in pnls if pnl < 0)
            self.win_rate = self.winning_trades / self.total_trades
            self.avg_trade_pnl = np.mean(pnls)
            self.best_trade = max(pnls)
            self.worst_trade = min(pnls)

        # Calculate Sharpe ratio from price returns
        if price_history:
            prices = [price for _, price in price_history]
            returns = np.diff(np.log(prices))
            if len(returns) > 1:
                self.sharpe_ratio = np.mean(returns) / np.std(returns) * np.sqrt(252)  # Annualized

        # Calculate drawdown
        if price_history:
            prices = [price for _, price in price_history]
            peak = prices[0]
            self.max_drawdown = 0
            for price in prices:
                if price > peak:
                    peak = price
                drawdown = (peak - price) / peak
                self.max_drawdown = max(self.max_drawdown, drawdown)

@dataclass
class TestSession:
    """Multi-strategy test session"""
    session_id: str
    start_time: float
    duration_hours: int
    strategies: List[str]
    pairs: List[str]
    metrics: Dict[str, Dict[str, StrategyMetrics]] = field(default_factory=lambda: defaultdict(dict))
    market_conditions: Dict[str, Any] = field(default_factory=dict)

class MultiStrategyTester:
    """
    Comprehensive testing framework for all trading strategies
    Runs 24-hour live validation across all MiCA pairs
    """

    def __init__(self, duration_hours: int = 24):
        self.duration_hours = duration_hours
        self.session = TestSession(
            session_id=f"test_{int(time.time())}",
            start_time=time.time(),
            duration_hours=duration_hours,
            strategies=['fib_dca', 'grid', 'arbitrage'],
            pairs=[
                'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC',
                'LINK/USDC', 'IOTA/USDC', 'ONDO/USDC', 'VET/USDC'
            ]
        )

        # Individual strategy simulators
        self.strategy_simulators: Dict[str, Dict[str, PaperTradingSimulator]] = {}

        # Live data fetcher
        self.data_fetcher = get_live_data_fetcher()

        # Market data collection
        self.market_data: Dict[str, List[Tuple[float, float]]] = defaultdict(list)

        # Initialize simulators for each strategy/pair combination
        self._init_simulators()

        logger.info(f"Multi-Strategy Tester initialized for {duration_hours}h test across {len(self.session.strategies)} strategies and {len(self.session.pairs)} pairs")

    def _init_simulators(self):
        """Initialize paper trading simulators for each strategy/pair"""
        for strategy in self.session.strategies:
            self.strategy_simulators[strategy] = {}

            for pair in self.session.pairs:
                simulator = PaperTradingSimulator()
                # Modify simulator to focus on single strategy and pair
                simulator.strategies = {strategy: self._get_strategy_instance(strategy)}
                simulator.portfolio.initial_balance = 1000.0  # Smaller balance per test

                # Override data callback to collect market data
                simulator.data_fetcher = None  # Don't start its own fetcher
                simulator._on_price_update = self._create_price_callback(strategy, pair, simulator)

                self.strategy_simulators[strategy][pair] = simulator

    def _get_strategy_instance(self, strategy_name: str):
        """Get strategy instance"""
        if strategy_name == 'fib_dca':
            return FibonacciDCAStrategy('XRP/USDC', {})  # Default config
        elif strategy_name == 'grid':
            return GridTradingStrategy('XRP/USDC', {})  # Default config
        elif strategy_name == 'arbitrage':
            return ArbitrageDetector()
        return None

    def _create_price_callback(self, strategy: str, pair: str, simulator: PaperTradingSimulator):
        """Create price update callback for specific strategy/pair"""
        def callback(ticker: TickerData):
            if ticker.pair == pair:
                # Update market data
                self.market_data[pair].append((ticker.timestamp, ticker.price))

                # Keep only last 1000 points
                if len(self.market_data[pair]) > 1000:
                    self.market_data[pair].pop(0)

                # Call simulator's price update
                simulator._on_price_update(ticker)

        return callback

    async def start_test(self):
        """Start the multi-strategy test"""
        logger.info(f"Starting {self.duration_hours}h multi-strategy test...")

        # Start live data fetcher
        await self.data_fetcher.start()

        # Start all simulators
        for strategy, pair_simulators in self.strategy_simulators.items():
            for pair, simulator in pair_simulators.items():
                # Add data callback
                self.data_fetcher.add_data_callback(simulator._on_price_update)

        # Run test for specified duration
        logger.info(f"Running test for {self.duration_hours} hours...")
        await asyncio.sleep(self.duration_hours * 3600)

        # Stop test
        await self.stop_test()

    async def stop_test(self):
        """Stop the test and generate reports"""
        logger.info("Stopping multi-strategy test...")

        # Stop data fetcher
        await self.data_fetcher.stop()

        # Calculate final metrics
        self._calculate_final_metrics()

        # Generate reports
        self._generate_reports()

    def _calculate_final_metrics(self):
        """Calculate final performance metrics for all strategies"""
        for strategy_name, pair_simulators in self.strategy_simulators.items():
            for pair, simulator in pair_simulators.items():
                metrics = StrategyMetrics(
                    strategy_name=strategy_name,
                    pair=pair
                )

                # Get trades and price history
                trades = simulator.portfolio.trade_history
                price_history = self.market_data.get(pair, [])

                # Calculate metrics
                metrics.calculate_metrics(trades, price_history)

                # Store metrics
                self.session.metrics[strategy_name][pair] = metrics

    def _generate_reports(self):
        """Generate comprehensive test reports"""
        print("\n" + "=" * 80)
        print("MULTI-STRATEGY TEST REPORT")
        print("=" * 80)
        print(f"Session ID: {self.session.session_id}")
        print(f"Duration: {self.duration_hours} hours")
        print(f"Strategies Tested: {', '.join(self.session.strategies)}")
        print(f"Pairs Tested: {', '.join(self.session.pairs)}")
        print(f"Total Strategy/Pair Combinations: {len(self.session.strategies) * len(self.session.pairs)}")

        # Overall summary
        self._print_overall_summary()

        # Strategy-by-strategy analysis
        self._print_strategy_analysis()

        # Pair-by-pair analysis
        self._print_pair_analysis()

        # Recommendations
        self._print_recommendations()

        print("\n" + "=" * 80)

    def _print_overall_summary(self):
        """Print overall test summary"""
        print("\nOVERALL SUMMARY:")

        total_trades = 0
        total_pnl = 0.0
        best_strategy = None
        best_pnl = float('-inf')

        for strategy, pair_metrics in self.session.metrics.items():
            strategy_trades = 0
            strategy_pnl = 0.0

            for pair, metrics in pair_metrics.items():
                strategy_trades += metrics.total_trades
                strategy_pnl += metrics.total_pnl

            total_trades += strategy_trades
            total_pnl += strategy_pnl

            if strategy_pnl > best_pnl:
                best_pnl = strategy_pnl
                best_strategy = strategy

        print(f"  Total Trades Executed: {total_trades}")
        print(f"  Total P&L: ${total_pnl:.2f}")
        print(f"  Best Performing Strategy: {best_strategy} (${best_pnl:.2f})")

    def _print_strategy_analysis(self):
        """Print strategy-by-strategy performance analysis"""
        print("\nSTRATEGY PERFORMANCE:")

        for strategy in self.session.strategies:
            print(f"\n  {strategy.upper()}:")
            pair_metrics = self.session.metrics[strategy]

            total_trades = sum(m.total_trades for m in pair_metrics.values())
            total_pnl = sum(m.total_pnl for m in pair_metrics.values())
            avg_win_rate = np.mean([m.win_rate for m in pair_metrics.values() if m.total_trades > 0])
            avg_sharpe = np.mean([m.sharpe_ratio for m in pair_metrics.values() if m.total_trades > 0])

            print(f"    Total Trades: {total_trades}")
            print(f"    Total P&L: ${total_pnl:.2f}")
            print(f"    Average Win Rate: {avg_win_rate:.1%}")
            print(f"    Average Sharpe Ratio: {avg_sharpe:.2f}")

            # Best/worst pairs for this strategy
            if pair_metrics:
                best_pair = max(pair_metrics.items(), key=lambda x: x[1].total_pnl)
                worst_pair = min(pair_metrics.items(), key=lambda x: x[1].total_pnl)

                print(f"    Best Pair: {best_pair[0]} (${best_pair[1].total_pnl:.2f})")
                print(f"    Worst Pair: {worst_pair[0]} (${worst_pair[1].total_pnl:.2f})")

    def _print_pair_analysis(self):
        """Print pair-by-pair performance analysis"""
        print("\nPAIR PERFORMANCE:")

        for pair in self.session.pairs:
            print(f"\n  {pair}:")
            pair_pnl = 0.0
            pair_trades = 0

            for strategy in self.session.strategies:
                if pair in self.session.metrics[strategy]:
                    metrics = self.session.metrics[strategy][pair]
                    pair_pnl += metrics.total_pnl
                    pair_trades += metrics.total_trades

            print(f"    Total Trades: {pair_trades}")
            print(f"    Total P&L: ${pair_pnl:.2f}")

            # Best strategy for this pair
            best_strategy = None
            best_pnl = float('-inf')

            for strategy in self.session.strategies:
                if pair in self.session.metrics[strategy]:
                    pnl = self.session.metrics[strategy][pair].total_pnl
                    if pnl > best_pnl:
                        best_pnl = pnl
                        best_strategy = strategy

            if best_strategy:
                print(f"    Best Strategy: {best_strategy} (${best_pnl:.2f})")

    def _print_recommendations(self):
        """Print retraining recommendations based on test results"""
        print("\nRETRAINING RECOMMENDATIONS:")

        # Find best performing strategy/pair combinations
        top_performers = []
        for strategy in self.session.strategies:
            for pair in self.session.pairs:
                if pair in self.session.metrics[strategy]:
                    metrics = self.session.metrics[strategy][pair]
                    if metrics.total_trades > 0:
                        top_performers.append((strategy, pair, metrics.total_pnl, metrics.win_rate))

        # Sort by P&L
        top_performers.sort(key=lambda x: x[2], reverse=True)

        print("  Top 5 Strategy/Pair Combinations for Retraining:")
        for i, (strategy, pair, pnl, win_rate) in enumerate(top_performers[:5]):
            print(f"    {i+1}. {strategy} on {pair}: ${pnl:.2f} (Win Rate: {win_rate:.1%})")

        # Identify strategies needing improvement
        poor_performers = [p for p in top_performers if p[2] < 0][-3:]  # Bottom 3

        if poor_performers:
            print("\n  Strategies Needing Optimization:")
            for strategy, pair, pnl, win_rate in poor_performers:
                print(f"    {strategy} on {pair}: ${pnl:.2f} (Win Rate: {win_rate:.1%})")

    def save_results(self, filename: str = None):
        """Save test results to JSON file"""
        if not filename:
            filename = f"multi_strategy_test_{self.session.session_id}.json"

        results = {
            'session': {
                'id': self.session.session_id,
                'start_time': self.session.start_time,
                'duration_hours': self.session.duration_hours,
                'strategies': self.session.strategies,
                'pairs': self.session.pairs
            },
            'metrics': {}
        }

        for strategy, pair_metrics in self.session.metrics.items():
            results['metrics'][strategy] = {}
            for pair, metrics in pair_metrics.items():
                results['metrics'][strategy][pair] = {
                    'total_trades': metrics.total_trades,
                    'winning_trades': metrics.winning_trades,
                    'losing_trades': metrics.losing_trades,
                    'total_pnl': metrics.total_pnl,
                    'win_rate': metrics.win_rate,
                    'sharpe_ratio': metrics.sharpe_ratio,
                    'max_drawdown': metrics.max_drawdown,
                    'avg_trade_pnl': metrics.avg_trade_pnl,
                    'best_trade': metrics.best_trade,
                    'worst_trade': metrics.worst_trade
                }

        with open(filename, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        logger.info(f"Test results saved to {filename}")

# Global tester instance
_tester = None

def get_multi_strategy_tester(duration_hours: int = 24) -> MultiStrategyTester:
    """Get or create global multi-strategy tester"""
    global _tester
    if _tester is None:
        _tester = MultiStrategyTester(duration_hours)
    return _tester

async def run_multi_strategy_test(duration_hours: int = 1):
    """Run multi-strategy test (short duration for testing)"""

    print("Multi-Strategy Tester")
    print("=" * 50)
    print(f"Running {duration_hours}h comprehensive strategy validation...")

    tester = get_multi_strategy_tester(duration_hours)

    try:
        await tester.start_test()

    except KeyboardInterrupt:
        print("\nTest interrupted by user")

    finally:
        # Save results
        tester.save_results()

        print(f"\nTest completed. Results saved to multi_strategy_test_{tester.session.session_id}.json")
        print("=" * 50)

if __name__ == '__main__':
    # Run 1-hour test for demonstration (change to 24 for full test)
    asyncio.run(run_multi_strategy_test(duration_hours=1))