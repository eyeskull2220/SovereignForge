#!/usr/bin/env python3
"""
SovereignForge Backtester - Wave 3
Historical backtesting framework for arbitrage strategies
"""

import asyncio
import json
import logging
import os
from concurrent.futures import ProcessPoolExecutor
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from data_fetcher import RealDataFetcher
from risk_management import create_default_risk_manager

logger = logging.getLogger(__name__)

class BacktestDataProvider:
    """Provides historical market data for backtesting"""

    def __init__(self, data_directory: str = None):
        self.data_directory = data_directory or os.path.join(os.path.dirname(__file__), '..', 'data')
        self.price_data = {}
        self._load_available_data()

    def _load_available_data(self):
        """Load available historical data"""

        # For demo purposes, we'll generate synthetic historical data
        # In production, this would load real historical data from files/databases
        self._generate_synthetic_data()

    def _generate_synthetic_data(self):
        """Generate synthetic historical data for backtesting"""

        symbols = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'ADA/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC']
        exchanges = ['binance', 'coinbase', 'kraken']

        # Generate 90 days of hourly data
        start_date = datetime.now() - timedelta(days=90)
        end_date = datetime.now()

        for symbol in symbols:
            self.price_data[symbol] = {}

            for exchange in exchanges:
                # Generate price series with realistic volatility and exchange-specific noise
                prices = self._generate_price_series(symbol, start_date, end_date, exchange)
                self.price_data[symbol][exchange] = prices

        logger.info(f"Generated synthetic data for {len(symbols)} symbols across {len(exchanges)} exchanges")

    def _generate_price_series(self, symbol: str, start_date: datetime, end_date: datetime, exchange: str) -> pd.DataFrame:
        """Generate realistic price series for backtesting"""

        # Base prices for different assets
        base_prices = {
            'BTC/USDC': 45000,
            'ETH/USDC': 3000,
            'XRP/USDC': 0.50,
            'ADA/USDC': 0.45,
            'XLM/USDC': 0.12,
            'HBAR/USDC': 0.08,
            'ALGO/USDC': 0.15
        }

        base_price = base_prices.get(symbol, 100)

        # Exchange-specific price adjustments (to create arbitrage opportunities)
        exchange_multipliers = {
            'binance': 1.0,      # Reference exchange
            'coinbase': 1.002,   # 0.2% premium
            'kraken': 0.998      # 0.2% discount
        }

        base_price *= exchange_multipliers.get(exchange, 1.0)
        hours = int((end_date - start_date).total_seconds() / 3600)

        # Generate timestamps
        timestamps = [start_date + timedelta(hours=i) for i in range(hours)]

        # Generate price series with:
        # - Random walk with drift
        # - Mean reversion to base price
        # - Realistic volatility by asset
        volatility_multipliers = {
            'BTC/USDC': 0.02,   # 2% daily volatility
            'ETH/USDC': 0.025,  # 2.5% daily volatility
            'XRP/USDC': 0.04,   # 4% daily volatility
            'ADA/USDC': 0.035,  # 3.5% daily volatility
            'XLM/USDC': 0.045,  # 4.5% daily volatility
            'HBAR/USDC': 0.05,  # 5% daily volatility
            'ALGO/USDC': 0.04   # 4% daily volatility
        }

        volatility = volatility_multipliers.get(symbol, 0.03) / 16  # Hourly volatility

        prices = [base_price]
        volumes = []

        for i in range(1, hours):
            # Random return with mean reversion
            random_return = np.random.normal(0, volatility)
            mean_reversion = -0.01 * (prices[-1] - base_price) / base_price  # Mean reversion force

            total_return = random_return + mean_reversion * 0.1  # Dampened mean reversion
            new_price = prices[-1] * (1 + total_return)

            # Ensure reasonable bounds (not too extreme)
            new_price = max(new_price, base_price * 0.1)  # Minimum 10% of base
            new_price = min(new_price, base_price * 3.0)  # Maximum 300% of base

            prices.append(new_price)

            # Generate volume (correlated with price volatility)
            base_volume = {
                'BTC/USDC': 100,
                'ETH/USDC': 500,
                'XRP/USDC': 50000,
                'ADA/USDC': 30000,
                'XLM/USDC': 25000,
                'HBAR/USDC': 15000,
                'ALGO/USDC': 20000
            }.get(symbol, 1000)

            volume_multiplier = 1 + abs(random_return) * 5  # Volume increases with volatility
            volume = base_volume * volume_multiplier * (0.5 + np.random.random())  # Add randomness
            volumes.append(volume)

        # Ensure all arrays are same length
        n_points = len(prices)
        timestamps = timestamps[:n_points]
        volumes = volumes[:n_points] if len(volumes) > n_points else volumes + [volumes[-1]] * (n_points - len(volumes))

        # Create DataFrame
        df = pd.DataFrame({
            'timestamp': timestamps,
            'price': prices,
            'volume': volumes,
            'high': [p * (1 + abs(np.random.normal(0, 0.005))) for p in prices],  # Fake OHLC
            'low': [p * (1 - abs(np.random.normal(0, 0.005))) for p in prices],
            'open': prices,  # Simplified
            'close': prices
        })

        return df

    def get_price_at_time(self, symbol: str, exchange: str, timestamp: datetime) -> Optional[Dict]:
        """Get price data for specific symbol/exchange at given time"""

        if symbol not in self.price_data or exchange not in self.price_data[symbol]:
            return None

        df = self.price_data[symbol][exchange]

        # Find closest timestamp
        closest_idx = (df['timestamp'] - timestamp).abs().idxmin()
        row = df.iloc[closest_idx]

        return {
            'price': row['price'],
            'volume': row['volume'],
            'high': row['high'],
            'low': row['low'],
            'timestamp': row['timestamp']
        }

    def get_price_window(self, symbol: str, exchange: str, start_time: datetime,
                        end_time: datetime) -> pd.DataFrame:
        """Get price data window for symbol/exchange"""

        if symbol not in self.price_data or exchange not in self.price_data[symbol]:
            return pd.DataFrame()

        df = self.price_data[symbol][exchange]
        mask = (df['timestamp'] >= start_time) & (df['timestamp'] <= end_time)

        return df[mask].copy()

    def get_available_symbols(self) -> List[str]:
        """Get list of available symbols"""
        return list(self.price_data.keys())

    def get_available_exchanges(self) -> List[str]:
        """Get list of available exchanges"""
        if not self.price_data:
            return []

        # Assume all symbols have same exchanges
        first_symbol = next(iter(self.price_data.keys()))
        return list(self.price_data[first_symbol].keys())

class ArbitrageBacktester:
    """Backtesting engine for arbitrage strategies"""

    def __init__(self, data_provider: BacktestDataProvider, risk_manager=None, order_executor=None):
        self.data_provider = data_provider
        self.risk_manager = risk_manager
        self.order_executor = order_executor

        # Backtest state
        self.portfolio_value = 10000.0
        self.cash = 10000.0
        self.positions = {}
        self.trades = []
        self.daily_returns = []

        # Performance tracking
        self.start_date = None
        self.end_date = None
        self.peak_value = 10000.0

        logger.info("Arbitrage Backtester initialized")

    async def run_backtest(self, symbols: List[str], start_date: datetime, end_date: datetime,
                          strategy_config: Dict = None) -> Dict:
        """Run complete backtest"""

        self.start_date = start_date
        self.end_date = end_date
        self.portfolio_value = 10000.0
        self.cash = 10000.0
        self.positions = {}
        self.trades = []
        self.daily_returns = []
        self.peak_value = 10000.0

        logger.info(f"Starting backtest from {start_date.date()} to {end_date.date()}")

        # Generate timestamps for testing (every hour)
        current_time = start_date
        hours_tested = 0

        while current_time <= end_date:
            # Run strategy for this timestamp
            await self._run_strategy_at_time(symbols, current_time, strategy_config)

            # Update daily returns (simplified - just track portfolio value changes)
            if current_time.hour == 0:  # End of day
                daily_return = (self.portfolio_value - self.peak_value) / self.peak_value
                self.daily_returns.append({
                    'date': current_time.date(),
                    'portfolio_value': self.portfolio_value,
                    'daily_return': daily_return
                })
                self.peak_value = max(self.peak_value, self.portfolio_value)

            current_time += timedelta(hours=1)
            hours_tested += 1

            if hours_tested % 100 == 0:
                logger.info(f"Backtested {hours_tested} hours, Portfolio: ${self.portfolio_value:.2f}")

        # Calculate final results
        results = self._calculate_backtest_results()

        sharpe = results.get('sharpe_ratio', 0.0)
        logger.info(f"Backtest completed: ${self.portfolio_value:.2f} final value, "
                   f"{len(self.trades)} trades, Sharpe: {sharpe:.3f}")

        return results

    async def _run_strategy_at_time(self, symbols: List[str], timestamp: datetime,
                                   strategy_config: Dict = None):
        """Run arbitrage strategy at specific time"""

        # Get market data for all symbols
        market_snapshot = {}
        for symbol in symbols:
            symbol_data = {}
            for exchange in self.data_provider.get_available_exchanges():
                price_data = self.data_provider.get_price_at_time(symbol, exchange, timestamp)
                if price_data:
                    symbol_data[exchange] = {
                        'bid': price_data['price'] * 0.999,  # Simulate bid/ask spread
                        'ask': price_data['price'] * 1.001,
                        'volume': price_data['volume'],
                        'price': price_data['price']
                    }
            market_snapshot[symbol] = symbol_data

        # Find arbitrage opportunities
        opportunities = self._find_arbitrage_opportunities(market_snapshot, timestamp)

        # Execute trades for valid opportunities
        for opportunity in opportunities:
            if self._validate_opportunity(opportunity):
                await self._execute_backtest_trade(opportunity)

    def _find_arbitrage_opportunities(self, market_snapshot: Dict, timestamp: datetime) -> List[Dict]:
        """Find arbitrage opportunities in market snapshot"""

        opportunities = []

        for symbol, exchange_data in market_snapshot.items():
            if len(exchange_data) < 2:
                continue

            # Find best bid and ask across exchanges
            best_bid = max(exchange_data.items(), key=lambda x: x[1]['bid'])
            best_ask = min(exchange_data.items(), key=lambda x: x[1]['ask'])

            bid_exchange, bid_data = best_bid
            ask_exchange, ask_data = best_ask

            # Check for arbitrage
            spread = (ask_data['ask'] - bid_data['bid']) / bid_data['bid']

            if spread > 0.001:  # 0.1% minimum spread
                opportunity = {
                    'symbol': symbol,
                    'buy_exchange': bid_exchange,
                    'sell_exchange': ask_exchange,
                    'buy_price': bid_data['bid'],
                    'sell_price': ask_data['ask'],
                    'spread_percentage': spread,
                    'timestamp': timestamp,
                    'buy_volume': bid_data['volume'],
                    'sell_volume': ask_data['volume']
                }
                opportunities.append(opportunity)

        return opportunities

    def _validate_opportunity(self, opportunity: Dict) -> bool:
        """Validate arbitrage opportunity"""

        # Check minimum spread after estimated fees
        spread_pct = opportunity['spread_percentage']
        estimated_fees_pct = 0.001  # 0.1% total fees (buy + sell)

        if spread_pct <= estimated_fees_pct:
            return False

        # Check volume availability
        min_volume = 10  # Minimum volume threshold
        if opportunity['buy_volume'] < min_volume or opportunity['sell_volume'] < min_volume:
            return False

        # Risk manager validation (if available)
        if self.risk_manager:
            position_calc = self.risk_manager.calculate_position_size(opportunity)
            return position_calc['approved']

        return True

    async def _execute_backtest_trade(self, opportunity: Dict):
        """Execute trade in backtest environment"""

        # Calculate position size
        if self.risk_manager:
            position_calc = self.risk_manager.calculate_position_size(opportunity)
            if not position_calc['approved']:
                return

            quantity = position_calc['position_value'] / opportunity['buy_price']
        else:
            # Default position size (0.1% of portfolio)
            quantity = (self.portfolio_value * 0.001) / opportunity['buy_price']

        # Simulate trade execution
        buy_cost = opportunity['buy_price'] * quantity
        sell_revenue = opportunity['sell_price'] * quantity
        fees = buy_cost * 0.001 + sell_revenue * 0.001  # 0.1% fees each side

        pnl = sell_revenue - buy_cost - fees

        # Update portfolio
        self.portfolio_value += pnl
        self.peak_value = max(self.peak_value, self.portfolio_value)

        # Record trade
        trade = {
            'timestamp': opportunity['timestamp'],
            'symbol': opportunity['symbol'],
            'buy_exchange': opportunity['buy_exchange'],
            'sell_exchange': opportunity['sell_exchange'],
            'quantity': quantity,
            'buy_price': opportunity['buy_price'],
            'sell_price': opportunity['sell_price'],
            'pnl': pnl,
            'fees': fees,
            'portfolio_value': self.portfolio_value
        }

        self.trades.append(trade)

        # Update risk manager if available
        if self.risk_manager:
            # Simulate position opening and closing
            position_details = {
                'symbol': opportunity['symbol'],
                'side': 'buy',
                'quantity': quantity,
                'entry_price': opportunity['buy_price'],
                'position_value': buy_cost,
                'stop_loss': opportunity['buy_price'] * 0.995,
                'take_profit': opportunity['buy_price'] * 1.01
            }

            self.risk_manager.open_position(position_details)
            self.risk_manager.close_position(
                f"backtest_{len(self.trades)}",
                opportunity['sell_price'],
                'backtest_exit'
            )

    def _calculate_backtest_results(self) -> Dict:
        """Calculate comprehensive backtest results"""

        if not self.trades:
            return {'error': 'No trades executed'}

        # Basic metrics
        total_return = (self.portfolio_value - 10000.0) / 10000.0
        total_trades = len(self.trades)
        winning_trades = sum(1 for t in self.trades if t['pnl'] > 0)
        losing_trades = total_trades - winning_trades

        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # P&L metrics
        gross_profit = sum(t['pnl'] for t in self.trades if t['pnl'] > 0)
        gross_loss = abs(sum(t['pnl'] for t in self.trades if t['pnl'] < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Risk metrics
        returns = [t['pnl'] / 10000.0 for t in self.trades]  # Returns relative to initial capital

        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns)

            # Sharpe ratio (annualized, assuming daily returns)
            if std_return > 0:
                sharpe_ratio = (avg_return * 365) / (std_return * np.sqrt(365))
            else:
                sharpe_ratio = 0

            # Maximum drawdown
            cumulative = np.cumprod(1 + np.array(returns))
            running_max = np.maximum.accumulate(cumulative)
            drawdowns = (running_max - cumulative) / running_max
            max_drawdown = np.max(drawdowns)
        else:
            sharpe_ratio = 0
            max_drawdown = 0

        # Trade frequency
        days_traded = (self.end_date - self.start_date).days
        trades_per_day = total_trades / days_traded if days_traded > 0 else 0

        results = {
            'total_return': total_return,
            'total_return_pct': total_return * 100,
            'final_portfolio_value': self.portfolio_value,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'win_rate': win_rate,
            'win_rate_pct': win_rate * 100,
            'gross_profit': gross_profit,
            'gross_loss': gross_loss,
            'profit_factor': profit_factor,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown * 100,
            'trades_per_day': trades_per_day,
            'avg_trade_pnl': np.mean([t['pnl'] for t in self.trades]),
            'median_trade_pnl': np.median([t['pnl'] for t in self.trades]),
            'largest_win': max([t['pnl'] for t in self.trades]) if self.trades else 0,
            'largest_loss': min([t['pnl'] for t in self.trades]) if self.trades else 0,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'backtest_days': days_traded
        }

        return results

    def get_trades_df(self) -> pd.DataFrame:
        """Get trades as DataFrame"""
        if not self.trades:
            return pd.DataFrame()

        return pd.DataFrame(self.trades)

    def plot_performance(self, save_path: str = None):
        """Plot backtest performance"""

        if not self.trades:
            logger.warning("No trades to plot")
            return

        try:
            import matplotlib.pyplot as plt
            import seaborn as sns

            # Set style
            sns.set_style('whitegrid')

            # Create figure with subplots
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 10))

            # Portfolio value over time
            trades_df = self.get_trades_df()
            trades_df = trades_df.sort_values('timestamp')

            ax1.plot(trades_df['timestamp'], trades_df['portfolio_value'])
            ax1.set_title('Portfolio Value Over Time')
            ax1.set_ylabel('Portfolio Value ($)')
            ax1.tick_params(axis='x', rotation=45)

            # Daily returns distribution
            if self.daily_returns:
                returns = [r['daily_return'] for r in self.daily_returns]
                ax2.hist(returns, bins=50, alpha=0.7)
                ax2.set_title('Daily Returns Distribution')
                ax2.set_xlabel('Daily Return')
                ax2.set_ylabel('Frequency')

            # Trade P&L distribution
            pnl_values = [t['pnl'] for t in self.trades]
            ax3.hist(pnl_values, bins=50, alpha=0.7, color='green')
            ax3.set_title('Trade P&L Distribution')
            ax3.set_xlabel('P&L ($)')
            ax3.set_ylabel('Frequency')

            # Cumulative returns
            cumulative_returns = []
            portfolio_values = [10000.0]  # Starting value

            for trade in self.trades:
                portfolio_values.append(trade['portfolio_value'])

            cumulative_returns = [(v - 10000.0) / 10000.0 for v in portfolio_values]

            ax4.plot(range(len(cumulative_returns)), cumulative_returns)
            ax4.set_title('Cumulative Returns')
            ax4.set_xlabel('Trade Number')
            ax4.set_ylabel('Cumulative Return')

            plt.tight_layout()

            if save_path:
                plt.savefig(save_path, dpi=300, bbox_inches='tight')
                logger.info(f"Performance plot saved to {save_path}")
            else:
                plt.show()

        except ImportError:
            logger.warning("Matplotlib/seaborn not available for plotting")

class WalkForwardOptimizer:
    """Walk-forward optimization for strategy parameters"""

    def __init__(self, backtester: ArbitrageBacktester):
        self.backtester = backtester

    def optimize_parameters(self, parameter_ranges: Dict, n_splits: int = 5) -> Dict:
        """Optimize strategy parameters using walk-forward analysis"""

        # This is a simplified version - in production would test different parameter combinations
        best_params = {}
        best_sharpe = -float('inf')

        # Example: optimize position size limits
        position_sizes = [0.005, 0.01, 0.02, 0.05]  # 0.5%, 1%, 2%, 5%

        for pos_size in position_sizes:
            # Update risk manager config
            if self.backtester.risk_manager:
                self.backtester.risk_manager.config['max_single_trade'] = pos_size

            # Run backtest
            results = self.backtester.run_backtest(
                symbols=['BTC/USDC'],
                start_date=datetime.now() - timedelta(days=30),
                end_date=datetime.now()
            )

            sharpe = results.get('sharpe_ratio', 0)

            if sharpe > best_sharpe:
                best_sharpe = sharpe
                best_params = {'max_single_trade': pos_size}

        logger.info(f"Optimal parameters found: {best_params}, Sharpe: {best_sharpe:.3f}")

        return best_params

async def run_demo_backtest():
    """Run demonstration backtest with real data"""

    print("SovereignForge Real Data Backtester Demo")
    print("=" * 40)

    # Initialize components with real data
    data_provider = RealDataFetcher()
    risk_manager = create_default_risk_manager()
    backtester = ArbitrageBacktester(data_provider, risk_manager)

    # Use MiCA compliant pairs that have data
    symbols = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC']
    start_date = datetime.now() - timedelta(days=7)  # Use 7 days since we fetched 7 days
    end_date = datetime.now()

    print(f"Running backtest for {symbols}")
    print(f"Period: {start_date.date()} to {end_date.date()}")

    results = await backtester.run_backtest(symbols, start_date, end_date)

    # Display results
    print("\nBacktest Results:")
    print("-" * 20)
    print(f"Results keys: {list(results.keys())}")
    if 'error' in results:
        print(f"Error: {results['error']}")
        return results

    print(f"Final Portfolio Value: ${results['final_portfolio_value']:.2f}")
    print(f"Total Return: {results['total_return_pct']:.2f}%")
    print(f"Total Trades: {results['total_trades']}")
    print(f"Win Rate: {results['win_rate_pct']:.1f}%")
    print(f"Sharpe Ratio: {results['sharpe_ratio']:.3f}")
    print(f"Max Drawdown: {results['max_drawdown_pct']:.2f}%")
    print(f"Average Trade P&L: ${results['avg_trade_pnl']:.2f}")

    return results

if __name__ == "__main__":
    asyncio.run(run_demo_backtest())
