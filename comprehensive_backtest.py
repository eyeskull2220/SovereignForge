#!/usr/bin/env python3
"""
SovereignForge Comprehensive Arbitrage Backtesting
Execute backtests for all MiCA pairs using retrained models
Calculate profitability metrics and generate detailed reports
"""

import asyncio
import logging
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
import matplotlib.pyplot as plt
import seaborn as sns
from concurrent.futures import ProcessPoolExecutor
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ComprehensiveBacktester:
    """
    Comprehensive arbitrage backtesting with retrained models
    """

    def __init__(self):
        self.processed_data_dir = Path('data/processed_real')
        self.backtest_results_dir = Path('reports/backtest_results')
        self.backtest_results_dir.mkdir(parents=True, exist_ok=True)

        self.mica_pairs = [
            'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC',
            'LINK/USDC', 'IOTA/USDC', 'XDC/USDC', 'ONDO/USDC', 'VET/USDC'
        ]

        self.exchanges = ['binance', 'coinbase', 'kraken']

        # Backtest parameters
        self.initial_capital = 10000  # $10,000 starting capital
        self.fee_rate = 0.001  # 0.1% trading fee
        self.slippage = 0.0005  # 0.05% slippage
        self.min_profit_threshold = 0.001  # 0.1% minimum profit
        self.max_position_size = 0.1  # 10% max position size per trade

    def load_processed_data(self, exchange: str, pair: str) -> Optional[pd.DataFrame]:
        """Load processed data for backtesting"""
        try:
            pair_filename = pair.replace('/', '_')
            filepath = self.processed_data_dir / exchange / f"{pair_filename}_processed.csv"

            if not filepath.exists():
                logger.warning(f"Processed data file not found: {filepath}")
                return None

            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.set_index('timestamp').sort_index()

            logger.info(f"Loaded {len(df)} records for {pair} from {exchange}")
            return df

        except Exception as e:
            logger.error(f"Failed to load processed data for {pair} from {exchange}: {e}")
            return None

    def detect_arbitrage_opportunities(self, df: pd.DataFrame) -> pd.DataFrame:
        """Detect arbitrage opportunities using technical indicators"""
        try:
            opportunities = []

            # Strategy 1: Mean Reversion (Bollinger Bands)
            df['bb_position'] = (df['close'] - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])

            # Fix boolean indexing - use proper pandas filtering
            bb_condition = (df['bb_position'] < 0.1) | (df['bb_position'] > 0.9)
            bb_signals = df[bb_condition & bb_condition.notna()]  # Filter out NaN

            for idx, row in bb_signals.iterrows():
                try:
                    if pd.notna(row['bb_position']) and row['bb_position'] < 0.1:  # Near lower band - potential buy
                        expected_return = (row['bb_middle'] - row['close']) / row['close']
                        if pd.notna(expected_return) and expected_return > self.min_profit_threshold:
                            opportunities.append({
                                'timestamp': idx,
                                'pair': 'N/A',  # Will be set by caller
                                'strategy': 'mean_reversion',
                                'direction': 'long',
                                'entry_price': row['close'],
                                'expected_price': row['bb_middle'],
                                'expected_return': expected_return,
                                'confidence': min(abs(row['bb_position'] - 0.5) * 2, 1.0) if pd.notna(row['bb_position']) else 0.5,
                                'indicators': {
                                    'rsi': row['rsi'] if pd.notna(row['rsi']) else 50,
                                    'bb_position': row['bb_position'] if pd.notna(row['bb_position']) else 0.5,
                                    'volume_ratio': row['volume_ratio'] if pd.notna(row['volume_ratio']) else 1.0
                                }
                            })
                except Exception as e:
                    logger.warning(f"Error processing BB signal at {idx}: {e}")
                    continue

            # Strategy 2: Momentum (RSI + MACD)
            try:
                rsi_condition = pd.notna(df['rsi']) & pd.notna(df['macd_hist'])
                oversold = (df['rsi'] < 30) & (df['macd_hist'] > 0)
                overbought = (df['rsi'] > 70) & (df['macd_hist'] < 0)
                momentum_condition = (oversold | overbought) & rsi_condition
                momentum_signals = df[momentum_condition]
            except Exception as e:
                logger.warning(f"Error creating momentum conditions: {e}")
                momentum_signals = pd.DataFrame()

            for idx, row in momentum_signals.iterrows():
                try:
                    if pd.notna(row['rsi']) and pd.notna(row['macd_hist']) and row['rsi'] < 30 and row['macd_hist'] > 0:  # Buy signal
                        expected_return = 0.02  # Assume 2% return target
                        opportunities.append({
                            'timestamp': idx,
                            'pair': 'N/A',
                            'strategy': 'momentum',
                            'direction': 'long',
                            'entry_price': row['close'],
                            'expected_price': row['close'] * (1 + expected_return),
                            'expected_return': expected_return,
                            'confidence': 0.7,  # Fixed confidence for momentum
                            'indicators': {
                                'rsi': row['rsi'],
                                'macd_hist': row['macd_hist'],
                                'momentum': row['momentum'] if pd.notna(row['momentum']) else 0
                            }
                        })
                except Exception as e:
                    logger.warning(f"Error processing momentum signal at {idx}: {e}")
                    continue

            # Strategy 3: Grid Trading (Fibonacci levels)
            try:
                fib_condition = pd.notna(df['fib_0.236']) & pd.notna(df['fib_0.382']) & pd.notna(df['close'])
                grid_buy_signals = df[(df['close'] <= df['fib_0.236']) & fib_condition]
                grid_sell_signals = df[(df['close'] >= df['fib_0.618']) & fib_condition]

                for idx, row in grid_buy_signals.iterrows():
                    try:
                        expected_return = (row['fib_0.382'] - row['close']) / row['close']
                        if pd.notna(expected_return) and expected_return > self.min_profit_threshold:
                            opportunities.append({
                                'timestamp': idx,
                                'pair': 'N/A',
                                'strategy': 'grid_fib',
                                'direction': 'long',
                                'entry_price': row['close'],
                                'expected_price': row['fib_0.382'],
                                'expected_return': expected_return,
                                'confidence': 0.6,
                                'indicators': {
                                    'fib_level': '0.236',
                                    'close': row['close'],
                                    'fib_target': row['fib_0.382']
                                }
                            })
                    except Exception as e:
                        logger.warning(f"Error processing grid buy signal at {idx}: {e}")
                        continue

            except Exception as e:
                logger.warning(f"Error in grid strategy: {e}")

            return pd.DataFrame(opportunities)

        except Exception as e:
            logger.error(f"Failed to detect arbitrage opportunities: {e}")
            return pd.DataFrame()

    def simulate_trading(self, opportunities: pd.DataFrame, df: pd.DataFrame) -> Dict[str, Any]:
        """Simulate trading with the detected opportunities"""
        try:
            capital = self.initial_capital
            trades = []
            equity_curve = []

            for idx, opportunity in opportunities.iterrows():
                try:
                    # Calculate position size (number of units)
                    max_position_value = capital * self.max_position_size
                    position_size = max_position_value / opportunity['entry_price']

                    # Apply fees and slippage
                    entry_price = opportunity['entry_price'] * (1 + self.slippage)
                    exit_price = opportunity['expected_price'] * (1 - self.slippage)

                    # Calculate P&L
                    if opportunity['direction'] == 'long':
                        gross_pnl = (exit_price - entry_price) * position_size
                    else:
                        gross_pnl = (entry_price - exit_price) * position_size

                    # Apply trading fees
                    fee = abs(gross_pnl) * self.fee_rate
                    net_pnl = gross_pnl - fee

                    # Update capital
                    capital += net_pnl

                    # Record trade
                    trade = {
                        'timestamp': opportunity['timestamp'],
                        'strategy': opportunity['strategy'],
                        'direction': opportunity['direction'],
                        'entry_price': entry_price,
                        'exit_price': exit_price,
                        'position_size': position_size,
                        'gross_pnl': gross_pnl,
                        'fee': fee,
                        'net_pnl': net_pnl,
                        'capital_after': capital,
                        'return_pct': net_pnl / (position_size * entry_price)
                    }
                    trades.append(trade)

                    # Record equity
                    equity_curve.append({
                        'timestamp': opportunity['timestamp'],
                        'capital': capital
                    })

                except Exception as e:
                    logger.warning(f"Failed to simulate trade: {e}")
                    continue

            # Calculate performance metrics
            if trades:
                trades_df = pd.DataFrame(trades)
                equity_df = pd.DataFrame(equity_curve)

                # Basic metrics
                total_return = (capital - self.initial_capital) / self.initial_capital
                total_trades = len(trades)
                winning_trades = len([t for t in trades if t['net_pnl'] > 0])
                win_rate = winning_trades / total_trades if total_trades > 0 else 0

                # Risk metrics
                returns = trades_df['return_pct'].dropna()
                if len(returns) > 1:
                    sharpe_ratio = returns.mean() / returns.std() * np.sqrt(365) if returns.std() > 0 else 0
                    max_drawdown = self.calculate_max_drawdown(equity_df['capital'])
                    volatility = returns.std() * np.sqrt(365)
                else:
                    sharpe_ratio = 0
                    max_drawdown = 0
                    volatility = 0

                # Advanced metrics
                avg_win = np.mean([t['net_pnl'] for t in trades if t['net_pnl'] > 0]) if winning_trades > 0 else 0
                avg_loss = abs(np.mean([t['net_pnl'] for t in trades if t['net_pnl'] < 0])) if winning_trades < total_trades else 0
                profit_factor = sum([t['net_pnl'] for t in trades if t['net_pnl'] > 0]) / abs(sum([t['net_pnl'] for t in trades if t['net_pnl'] < 0])) if sum([t['net_pnl'] for t in trades if t['net_pnl'] < 0]) != 0 else float('inf')

                metrics = {
                    'total_return': total_return,
                    'annualized_return': total_return * (365 / len(equity_df)) if len(equity_df) > 0 else 0,
                    'sharpe_ratio': sharpe_ratio,
                    'max_drawdown': max_drawdown,
                    'volatility': volatility,
                    'total_trades': total_trades,
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'profit_factor': profit_factor,
                    'final_capital': capital,
                    'total_fees': sum([t['fee'] for t in trades])
                }
            else:
                metrics = {
                    'total_return': 0,
                    'annualized_return': 0,
                    'sharpe_ratio': 0,
                    'max_drawdown': 0,
                    'volatility': 0,
                    'total_trades': 0,
                    'win_rate': 0,
                    'avg_win': 0,
                    'avg_loss': 0,
                    'profit_factor': 0,
                    'final_capital': self.initial_capital,
                    'total_fees': 0
                }

            return {
                'metrics': metrics,
                'trades': trades,
                'equity_curve': equity_curve
            }

        except Exception as e:
            logger.error(f"Failed to simulate trading: {e}")
            return {}

    def calculate_max_drawdown(self, capital_series: pd.Series) -> float:
        """Calculate maximum drawdown"""
        try:
            peak = capital_series.expanding().max()
            drawdown = (capital_series - peak) / peak
            return abs(drawdown.min())
        except:
            return 0

    def backtest_pair(self, exchange: str, pair: str) -> Dict[str, Any]:
        """Backtest a specific pair"""
        try:
            logger.info(f"Backtesting {pair} on {exchange}")

            # Load data
            df = self.load_processed_data(exchange, pair)
            if df is None or len(df) < 100:
                return {'error': f'No data available for {pair} on {exchange}'}

            # Detect opportunities
            opportunities = self.detect_arbitrage_opportunities(df)
            opportunities['pair'] = pair

            # Simulate trading
            results = self.simulate_trading(opportunities, df)

            # Add metadata
            results['metadata'] = {
                'exchange': exchange,
                'pair': pair,
                'data_points': len(df),
                'opportunities_detected': len(opportunities),
                'backtest_period': {
                    'start': df.index.min().isoformat(),
                    'end': df.index.max().isoformat()
                }
            }

            logger.info(f"Backtest completed for {pair} on {exchange}: {len(opportunities)} opportunities, return: {results.get('metrics', {}).get('total_return', 0):.2%}")

            return results

        except Exception as e:
            logger.error(f"Failed to backtest {pair} on {exchange}: {e}")
            return {'error': str(e)}

    def run_comprehensive_backtest(self) -> Dict[str, Any]:
        """Run comprehensive backtest across all pairs and exchanges"""
        logger.info("Starting comprehensive arbitrage backtesting")

        all_results = {}
        summary_stats = {
            'total_pairs_tested': 0,
            'successful_backtests': 0,
            'total_opportunities': 0,
            'total_trades': 0,
            'aggregate_metrics': {
                'total_return': 0,
                'sharpe_ratio': 0,
                'win_rate': 0,
                'max_drawdown': 0
            }
        }

        for exchange in self.exchanges:
            for pair in self.mica_pairs:
                result = self.backtest_pair(exchange, pair)

                if 'error' not in result:
                    all_results[f"{exchange}_{pair}"] = result
                    summary_stats['successful_backtests'] += 1
                    summary_stats['total_opportunities'] += result['metadata']['opportunities_detected']
                    summary_stats['total_trades'] += result['metrics']['total_trades']

                    # Aggregate metrics
                    summary_stats['aggregate_metrics']['total_return'] += result['metrics']['total_return']
                    summary_stats['aggregate_metrics']['sharpe_ratio'] += result['metrics']['sharpe_ratio']
                    summary_stats['aggregate_metrics']['win_rate'] += result['metrics']['win_rate']
                    summary_stats['aggregate_metrics']['max_drawdown'] = max(
                        summary_stats['aggregate_metrics']['max_drawdown'],
                        result['metrics']['max_drawdown']
                    )

                summary_stats['total_pairs_tested'] += 1

        # Calculate averages
        if summary_stats['successful_backtests'] > 0:
            for key in ['total_return', 'sharpe_ratio', 'win_rate']:
                summary_stats['aggregate_metrics'][key] /= summary_stats['successful_backtests']

        # Generate reports
        self.generate_backtest_report(all_results, summary_stats)

        logger.info("Comprehensive backtesting completed!")
        logger.info(f"Successfully backtested {summary_stats['successful_backtests']}/{summary_stats['total_pairs_tested']} pairs")
        logger.info(f"Total opportunities detected: {summary_stats['total_opportunities']}")
        logger.info(f"Aggregate return: {summary_stats['aggregate_metrics']['total_return']:.2%}")

        return {
            'results': all_results,
            'summary': summary_stats
        }

    def generate_backtest_report(self, results: Dict[str, Any], summary: Dict[str, Any]):
        """Generate comprehensive backtest report"""
        try:
            report = {
                'backtest_timestamp': datetime.now().isoformat(),
                'summary': summary,
                'detailed_results': results
            }

            # Save JSON report
            report_path = self.backtest_results_dir / 'comprehensive_backtest_report.json'
            with open(report_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)

            # Generate performance summary
            self.generate_performance_summary(results, summary)

            # Generate charts
            self.generate_performance_charts(results)

            logger.info(f"Backtest report saved to {report_path}")

        except Exception as e:
            logger.error(f"Failed to generate backtest report: {e}")

    def generate_performance_summary(self, results: Dict[str, Any], summary: Dict[str, Any]):
        """Generate performance summary"""
        try:
            summary_text = f"""
# SovereignForge Arbitrage Backtesting Results

## Executive Summary
- **Pairs Tested**: {summary['total_pairs_tested']}
- **Successful Backtests**: {summary['successful_backtests']}
- **Total Opportunities Detected**: {summary['total_opportunities']}
- **Total Trades Executed**: {summary['total_trades']}

## Aggregate Performance Metrics
- **Total Return**: {summary['aggregate_metrics']['total_return']:.2%}
- **Sharpe Ratio**: {summary['aggregate_metrics']['sharpe_ratio']:.2f}
- **Win Rate**: {summary['aggregate_metrics']['win_rate']:.2%}
- **Max Drawdown**: {summary['aggregate_metrics']['max_drawdown']:.2%}

## Top Performing Pairs
"""

            # Sort results by total return
            sorted_results = sorted(
                [(k, v) for k, v in results.items() if 'metrics' in v],
                key=lambda x: x[1]['metrics']['total_return'],
                reverse=True
            )

            for pair_key, result in sorted_results[:10]:
                metrics = result['metrics']
                summary_text += f"- **{pair_key}**: {metrics['total_return']:.2%} return, {metrics['sharpe_ratio']:.2f} Sharpe, {metrics['win_rate']:.1%} win rate\n"

            summary_text += "\n## Risk Analysis\n"
            summary_text += f"- **Maximum Drawdown**: {summary['aggregate_metrics']['max_drawdown']:.2%}\n"
            summary_text += f"- **Volatility**: {summary['aggregate_metrics']['volatility']:.2%}\n"

            # Save summary
            summary_path = self.backtest_results_dir / 'performance_summary.md'
            with open(summary_path, 'w') as f:
                f.write(summary_text)

            logger.info(f"Performance summary saved to {summary_path}")

        except Exception as e:
            logger.error(f"Failed to generate performance summary: {e}")

    def generate_performance_charts(self, results: Dict[str, Any]):
        """Generate performance visualization charts"""
        try:
            # Prepare data for plotting
            pair_returns = []
            pair_sharpe = []
            pair_win_rates = []

            for pair_key, result in results.items():
                if 'metrics' in result:
                    metrics = result['metrics']
                    pair_returns.append((pair_key, metrics['total_return']))
                    pair_sharpe.append((pair_key, metrics['sharpe_ratio']))
                    pair_win_rates.append((pair_key, metrics['win_rate']))

            # Sort by return
            pair_returns.sort(key=lambda x: x[1], reverse=True)
            pair_sharpe.sort(key=lambda x: x[1], reverse=True)
            pair_win_rates.sort(key=lambda x: x[1], reverse=True)

            # Create plots
            fig, axes = plt.subplots(2, 2, figsize=(15, 10))

            # Returns bar chart
            pairs, returns = zip(*pair_returns[:10])
            axes[0, 0].bar(range(len(pairs)), [r * 100 for r in returns])
            axes[0, 0].set_xticks(range(len(pairs)))
            axes[0, 0].set_xticklabels([p.replace('_', '/') for p in pairs], rotation=45, ha='right')
            axes[0, 0].set_title('Top 10 Pairs by Total Return (%)')
            axes[0, 0].set_ylabel('Return (%)')

            # Sharpe ratio
            pairs, sharpe = zip(*pair_sharpe[:10])
            axes[0, 1].bar(range(len(pairs)), sharpe)
            axes[0, 1].set_xticks(range(len(pairs)))
            axes[0, 1].set_xticklabels([p.replace('_', '/') for p in pairs], rotation=45, ha='right')
            axes[0, 1].set_title('Top 10 Pairs by Sharpe Ratio')
            axes[0, 1].set_ylabel('Sharpe Ratio')

            # Win rates
            pairs, win_rates = zip(*pair_win_rates[:10])
            axes[1, 0].bar(range(len(pairs)), [r * 100 for r in win_rates])
            axes[1, 0].set_xticks(range(len(pairs)))
            axes[1, 0].set_xticklabels([p.replace('_', '/') for p in pairs], rotation=45, ha='right')
            axes[1, 0].set_title('Top 10 Pairs by Win Rate (%)')
            axes[1, 0].set_ylabel('Win Rate (%)')

            # Distribution of returns
            all_returns = [result['metrics']['total_return'] for result in results.values() if 'metrics' in result]
            axes[1, 1].hist([r * 100 for r in all_returns], bins=20, alpha=0.7)
            axes[1, 1].set_title('Distribution of Returns (%)')
            axes[1, 1].set_xlabel('Return (%)')
            axes[1, 1].set_ylabel('Frequency')

            plt.tight_layout()

            # Save chart
            chart_path = self.backtest_results_dir / 'performance_charts.png'
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()

            logger.info(f"Performance charts saved to {chart_path}")

        except Exception as e:
            logger.error(f"Failed to generate performance charts: {e}")

def main():
    """Main entry point"""
    backtester = ComprehensiveBacktester()
    results = backtester.run_comprehensive_backtest()

    # Print summary
    summary = results['summary']
    print("\n" + "="*60)
    print("SOVEREIGNFORGE ARBITRAGE BACKTESTING RESULTS")
    print("="*60)
    print(f"Pairs Tested: {summary['total_pairs_tested']}")
    print(f"Successful Backtests: {summary['successful_backtests']}")
    print(f"Total Opportunities: {summary['total_opportunities']}")
    print(f"Total Trades: {summary['total_trades']}")
    print()
    print("AGGREGATE PERFORMANCE:")
    print(f"Total Return: {summary['aggregate_metrics']['total_return']:.2%}")
    print(f"Sharpe Ratio: {summary['aggregate_metrics']['sharpe_ratio']:.2f}")
    print(f"Win Rate: {summary['aggregate_metrics']['win_rate']:.1%}")
    print(f"Max Drawdown: {summary['aggregate_metrics']['max_drawdown']:.2%}")
    print("="*60)

if __name__ == "__main__":
    main()