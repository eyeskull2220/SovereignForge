#!/usr/bin/env python3
"""
SovereignForge Paper Trading Simulator
Real-time paper trading simulation using live market data
Tests all strategies across MiCA-compliant pairs
"""

import asyncio
import logging
import time
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_DOWN
import numpy as np

from live_data_fetcher import get_live_data_fetcher, TickerData
from fib_dca_strategy import FibonacciDCAStrategy
from grid_trading_strategy import GridTradingStrategy
from arbitrage_detector import ArbitrageDetector
from strategy_orchestrator import StrategyOrchestrator

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Paper trading position"""
    pair: str
    strategy: str
    side: str  # 'buy' or 'sell'
    entry_price: float
    quantity: float
    timestamp: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    pnl: float = 0.0
    pnl_pct: float = 0.0
    status: str = 'open'  # 'open', 'closed', 'stopped'

@dataclass
class TradeResult:
    """Trade execution result"""
    pair: str
    strategy: str
    side: str
    price: float
    quantity: float
    timestamp: float
    reason: str  # 'entry', 'exit', 'stop_loss', 'take_profit'

@dataclass
class PaperPortfolio:
    """Paper trading portfolio"""
    initial_balance: float = 10000.0  # USDC
    balance: float = 10000.0
    positions: Dict[str, List[Position]] = field(default_factory=dict)
    trade_history: List[TradeResult] = field(default_factory=list)
    daily_pnl: List[float] = field(default_factory=list)
    start_time: float = field(default_factory=time.time)

    def get_total_value(self, current_prices: Dict[str, float]) -> float:
        """Calculate total portfolio value"""
        total_value = self.balance

        for pair, positions in self.positions.items():
            for position in positions:
                if position.status == 'open':
                    current_price = current_prices.get(pair, position.entry_price)
                    if position.side == 'buy':
                        total_value += position.quantity * current_price
                    else:  # short position
                        total_value += position.quantity * (2 * position.entry_price - current_price)

        return total_value

    def get_pnl(self, current_prices: Dict[str, float]) -> Tuple[float, float]:
        """Get total P&L (absolute and percentage)"""
        current_value = self.get_total_value(current_prices)
        pnl = current_value - self.initial_balance
        pnl_pct = (pnl / self.initial_balance) * 100
        return pnl, pnl_pct

class PaperTradingSimulator:
    """
    Real-time paper trading simulator
    Tests strategies on live market data without risking real funds
    """

    def __init__(self):
        self.portfolio = PaperPortfolio()
        self.current_prices: Dict[str, float] = {}
        self.price_history: Dict[str, List[Tuple[float, float]]] = {}  # (timestamp, price)

        # Strategy instances
        self.strategies = {
            'fib_dca': FibonacciDCAStrategy('XRP/USDC', {}),
            'grid': GridTradingStrategy('XRP/USDC', {}),
            'arbitrage': ArbitrageDetector()
        }

        # Strategy orchestrator
        self.orchestrator = StrategyOrchestrator({'initial_portfolio_value': self.portfolio.initial_balance})

        # Live data fetcher
        self.data_fetcher = get_live_data_fetcher()
        self.data_fetcher.add_data_callback(self._on_price_update)

        # Trading parameters
        self.min_trade_size = 10.0  # Minimum trade size in USDC
        self.max_position_size = 1000.0  # Maximum position size per pair
        self.max_open_positions = 20  # Maximum open positions across all pairs

        # Risk management
        self.max_daily_loss = 500.0  # Stop trading if daily loss exceeds this
        self.daily_loss = 0.0

        # Statistics
        self.stats = {
            'trades_executed': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'total_pnl': 0.0,
            'best_trade': 0.0,
            'worst_trade': 0.0,
            'start_time': time.time()
        }

        logger.info("Paper Trading Simulator initialized")

    async def start(self):
        """Start the paper trading simulation"""
        logger.info("Starting paper trading simulation...")

        # Start live data fetcher
        await self.data_fetcher.start()

        # Start trading loop
        await self._trading_loop()

    async def stop(self):
        """Stop the simulation"""
        logger.info("Stopping paper trading simulation...")

        await self.data_fetcher.stop()

        # Generate final report
        self._generate_report()

    def _on_price_update(self, ticker: TickerData):
        """Handle incoming price updates"""
        pair = ticker.pair
        price = ticker.price
        timestamp = ticker.timestamp

        # Update current prices
        self.current_prices[pair] = price

        # Store price history (keep last 1000 points)
        if pair not in self.price_history:
            self.price_history[pair] = []
        self.price_history[pair].append((timestamp, price))
        if len(self.price_history[pair]) > 1000:
            self.price_history[pair].pop(0)

        # Update open positions P&L
        self._update_positions_pnl(pair, price)

        # Check for trading signals
        self._check_trading_signals(pair, price, timestamp)

    def _update_positions_pnl(self, pair: str, current_price: float):
        """Update P&L for open positions"""
        if pair not in self.portfolio.positions:
            return

        for position in self.portfolio.positions[pair]:
            if position.status == 'open':
                if position.side == 'buy':
                    position.pnl = (current_price - position.entry_price) * position.quantity
                else:  # short
                    position.pnl = (position.entry_price - current_price) * position.quantity

                position.pnl_pct = (position.pnl / (position.entry_price * position.quantity)) * 100

    def _check_trading_signals(self, pair: str, price: float, timestamp: float):
        """Check for trading signals from all strategies"""
        if len(self.price_history.get(pair, [])) < 50:  # Need some history
            return

        # Get recent price data
        prices = [p for t, p in self.price_history[pair][-100:]]
        volumes = [1.0] * len(prices)  # Placeholder volumes

        # Check each strategy
        for strategy_name, strategy in self.strategies.items():
            try:
                signal = self._get_strategy_signal(strategy_name, strategy, pair, prices, volumes)

                if signal:
                    self._execute_trade(pair, strategy_name, signal, price, timestamp)

            except Exception as e:
                logger.error(f"Error checking {strategy_name} signals for {pair}: {e}")

    def _get_strategy_signal(self, strategy_name: str, strategy, pair: str, prices: List[float], volumes: List[float]) -> Optional[Dict[str, Any]]:
        """Get trading signal from a strategy"""
        try:
            if strategy_name == 'fib_dca':
                # Fib DCA strategy
                signal = strategy.analyze_market(prices, volumes)
                if signal and signal.get('action') in ['buy', 'sell']:
                    return {
                        'action': signal['action'],
                        'quantity': signal.get('quantity', self.min_trade_size / prices[-1]),
                        'reason': 'fib_dca_signal'
                    }

            elif strategy_name == 'grid':
                # Grid trading strategy
                signal = strategy.generate_signal(prices[-1], prices)
                if signal:
                    return {
                        'action': signal.get('side', 'buy'),
                        'quantity': signal.get('quantity', self.min_trade_size / prices[-1]),
                        'reason': 'grid_signal'
                    }

            elif strategy_name == 'arbitrage':
                # Arbitrage detector
                opportunities = strategy.detect_arbitrage(self.current_prices)
                if opportunities:
                    for opp in opportunities:
                        if pair in [opp['pair1'], opp['pair2']]:
                            return {
                                'action': 'buy' if opp['direction'] == 'long' else 'sell',
                                'quantity': opp.get('quantity', self.min_trade_size / prices[-1]),
                                'reason': 'arbitrage_opportunity'
                            }

        except Exception as e:
            logger.error(f"Error getting signal from {strategy_name}: {e}")

        return None

    def _execute_trade(self, pair: str, strategy: str, signal: Dict[str, Any], price: float, timestamp: float):
        """Execute a paper trade"""
        action = signal['action']
        quantity = signal.get('quantity', self.min_trade_size / price)
        reason = signal.get('reason', 'signal')

        # Risk checks
        if not self._check_risk_limits(pair, action, quantity, price):
            return

        # Calculate trade value
        trade_value = quantity * price

        # Execute trade
        if action == 'buy':
            if self.portfolio.balance >= trade_value:
                self.portfolio.balance -= trade_value

                position = Position(
                    pair=pair,
                    strategy=strategy,
                    side='buy',
                    entry_price=price,
                    quantity=quantity,
                    timestamp=timestamp
                )

                if pair not in self.portfolio.positions:
                    self.portfolio.positions[pair] = []
                self.portfolio.positions[pair].append(position)

                logger.info(f"BUY {quantity:.4f} {pair} @ ${price:.4f} (Total: ${trade_value:.2f})")

        elif action == 'sell':
            # Find open buy positions to close
            if pair in self.portfolio.positions:
                for position in self.portfolio.positions[pair]:
                    if position.status == 'open' and position.side == 'buy':
                        # Close position
                        position.status = 'closed'
                        position.pnl = (price - position.entry_price) * position.quantity
                        position.pnl_pct = (position.pnl / (position.entry_price * position.quantity)) * 100

                        # Return capital
                        self.portfolio.balance += position.quantity * price

                        logger.info(f"SELL {position.quantity:.4f} {pair} @ ${price:.4f} (PnL: ${position.pnl:.2f})")
                        break

        # Record trade
        trade = TradeResult(
            pair=pair,
            strategy=strategy,
            side=action,
            price=price,
            quantity=quantity,
            timestamp=timestamp,
            reason=reason
        )
        self.portfolio.trade_history.append(trade)

        # Update statistics
        self._update_stats(trade)

    def _check_risk_limits(self, pair: str, action: str, quantity: float, price: float) -> bool:
        """Check risk management limits"""
        trade_value = quantity * price

        # Check minimum trade size
        if trade_value < self.min_trade_size:
            return False

        # Check maximum position size
        current_position_value = 0
        if pair in self.portfolio.positions:
            for position in self.portfolio.positions[pair]:
                if position.status == 'open':
                    current_position_value += position.quantity * position.entry_price

        if current_position_value + trade_value > self.max_position_size:
            return False

        # Check maximum open positions
        total_open_positions = sum(
            len(positions) for positions in self.portfolio.positions.values()
            if any(p.status == 'open' for p in positions)
        )

        if total_open_positions >= self.max_open_positions:
            return False

        # Check daily loss limit
        if self.daily_loss <= -self.max_daily_loss:
            logger.warning("Daily loss limit reached, stopping trading")
            return False

        return True

    def _update_stats(self, trade: TradeResult):
        """Update trading statistics"""
        self.stats['trades_executed'] += 1

        # This would be updated when positions are closed
        # For now, just count executed trades

    async def _trading_loop(self):
        """Main trading loop"""
        logger.info("Paper trading simulation running...")

        try:
            while True:
                await asyncio.sleep(60)  # Check every minute

                # Update daily P&L
                current_value = self.portfolio.get_total_value(self.current_prices)
                daily_pnl = current_value - self.portfolio.initial_balance
                self.portfolio.daily_pnl.append(daily_pnl)

                # Update daily loss for risk management
                if self.portfolio.daily_pnl:
                    self.daily_loss = self.portfolio.daily_pnl[-1] - (self.portfolio.daily_pnl[-2] if len(self.portfolio.daily_pnl) > 1 else 0)

                # Log status
                pnl, pnl_pct = self.portfolio.get_pnl(self.current_prices)
                logger.info(f"Portfolio: ${current_value:.2f} | PnL: ${pnl:.2f} ({pnl_pct:.2f}%) | "
                           f"Open Positions: {sum(len([p for p in positions if p.status == 'open']) for positions in self.portfolio.positions.values())}")

        except asyncio.CancelledError:
            logger.info("Trading loop cancelled")

    def _generate_report(self):
        """Generate final trading report"""
        print("\n" + "=" * 60)
        print("PAPER TRADING SIMULATION REPORT")
        print("=" * 60)

        # Portfolio summary
        final_value = self.portfolio.get_total_value(self.current_prices)
        pnl, pnl_pct = self.portfolio.get_pnl(self.current_prices)

        print("Portfolio Summary:")
        print(f"  Initial Balance: ${self.portfolio.initial_balance:.2f}")
        print(f"  Final Value: ${final_value:.2f}")
        print(f"  Total P&L: ${pnl:.2f} ({pnl_pct:.2f}%)")
        print(f"  Duration: {(time.time() - self.portfolio.start_time) / 3600:.1f} hours")

        # Trading statistics
        print("\nTrading Statistics:")
        print(f"  Total Trades: {len(self.portfolio.trade_history)}")
        print(f"  Open Positions: {sum(len([p for p in positions if p.status == 'open']) for positions in self.portfolio.positions.values())}")

        # Best/Worst trades
        closed_positions = []
        for positions in self.portfolio.positions.values():
            closed_positions.extend([p for p in positions if p.status == 'closed'])

        if closed_positions:
            best_trade = max(closed_positions, key=lambda p: p.pnl)
            worst_trade = min(closed_positions, key=lambda p: p.pnl)

            print(f"  Best Trade: ${best_trade.pnl:.2f} ({best_trade.pair})")
            print(f"  Worst Trade: ${worst_trade.pnl:.2f} ({worst_trade.pair})")

        # Strategy performance
        strategy_pnl = {}
        for positions in self.portfolio.positions.values():
            for position in positions:
                if position.status == 'closed':
                    if position.strategy not in strategy_pnl:
                        strategy_pnl[position.strategy] = 0
                    strategy_pnl[position.strategy] += position.pnl

        print("\nStrategy Performance:")
        for strategy, pnl in strategy_pnl.items():
            print(f"  {strategy}: ${pnl:.2f}")

        print("\n" + "=" * 60)

# Global simulator instance
_simulator = None

def get_paper_trading_simulator() -> PaperTradingSimulator:
    """Get or create global paper trading simulator"""
    global _simulator
    if _simulator is None:
        _simulator = PaperTradingSimulator()
    return _simulator

async def test_paper_trading():
    """Test the paper trading simulator"""

    print("Paper Trading Simulator Test")
    print("=" * 50)

    simulator = get_paper_trading_simulator()

    try:
        # Start simulator
        await simulator.start()

        # Run for 5 minutes
        print("Running paper trading simulation (5 minutes)...")
        await asyncio.sleep(300)

    except KeyboardInterrupt:
        print("\nTest interrupted")

    finally:
        await simulator.stop()

        print("\n" + "=" * 50)
        print("Paper Trading Test Complete")

if __name__ == '__main__':
    asyncio.run(test_paper_trading())