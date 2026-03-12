#!/usr/bin/env python3
"""
SovereignForge Performance Analyzer - Wave 4
Comprehensive analytics and performance metrics for arbitrage trading
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats

logger = logging.getLogger(__name__)

class PerformanceAnalyzer:
    """Comprehensive performance analysis for arbitrage trading"""

    def __init__(self, risk_manager=None, backtester=None):
        self.risk_manager = risk_manager
        self.backtester = backtester
        self.performance_history = []
        self.daily_metrics = []

        logger.info("Performance Analyzer initialized")

    def analyze_portfolio_performance(self, trades: List[Dict], start_date: datetime = None,
                                    end_date: datetime = None) -> Dict:
        """Comprehensive portfolio performance analysis"""

        if not trades:
            return {'error': 'No trades available for analysis'}

        # Convert to DataFrame for analysis
        df = pd.DataFrame(trades)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp')

        # Filter by date range if specified
        if start_date:
            df = df[df['timestamp'] >= start_date]
        if end_date:
            df = df[df['timestamp'] <= end_date]

        if df.empty:
            return {'error': 'No trades in specified date range'}

        # Basic metrics
        total_trades = len(df)
        winning_trades = len(df[df['pnl'] > 0])
        losing_trades = len(df[df['pnl'] < 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0

        # P&L metrics
        total_pnl = df['pnl'].sum()
        avg_trade_pnl = df['pnl'].mean()
        median_trade_pnl = df['pnl'].median()
        largest_win = df['pnl'].max()
        largest_loss = df['pnl'].min()

        # Calculate returns
        initial_capital = 10000.0  # Assume $10k starting capital
        returns = df['pnl'] / initial_capital

        # Risk metrics
        if len(returns) > 1:
            # Sharpe ratio (annualized, assuming daily returns)
            avg_return = returns.mean()
            std_return = returns.std()
            if std_return > 0:
                sharpe_ratio = (avg_return * np.sqrt(365)) / std_return
            else:
                sharpe_ratio = 0

            # Sortino ratio (downside deviation)
            downside_returns = returns[returns < 0]
            if len(downside_returns) > 0:
                downside_std = downside_returns.std()
                sortino_ratio = (avg_return * np.sqrt(365)) / downside_std if downside_std > 0 else 0
            else:
                sortino_ratio = 0

            # Maximum drawdown
            cumulative = (1 + returns).cumprod()
            running_max = cumulative.expanding().max()
            drawdowns = (cumulative - running_max) / running_max
            max_drawdown = drawdowns.min()

            # Calmar ratio
            calmar_ratio = abs(avg_return * 365 / max_drawdown) if max_drawdown != 0 else 0

        else:
            sharpe_ratio = sortino_ratio = max_drawdown = calmar_ratio = 0

        # Profit factor
        gross_profit = df[df['pnl'] > 0]['pnl'].sum()
        gross_loss = abs(df[df['pnl'] < 0]['pnl'].sum())
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

        # Recovery factor
        recovery_factor = total_pnl / abs(max_drawdown * initial_capital) if max_drawdown != 0 else float('inf')

        # Trade frequency
        date_range = (df['timestamp'].max() - df['timestamp'].min()).days
        trades_per_day = total_trades / date_range if date_range > 0 else 0

        # Expectancy
        expectancy = (win_rate * avg_trade_pnl) - ((1 - win_rate) * abs(avg_trade_pnl))

        # Kelly criterion
        if win_rate > 0 and win_rate < 1:
            kelly = win_rate - ((1 - win_rate) / (avg_trade_pnl / abs(avg_trade_pnl)))
            kelly = max(0, kelly)  # Ensure non-negative
        else:
            kelly = 0

        # Risk-adjusted return metrics
        total_return_pct = (total_pnl / initial_capital) * 100

        # Monthly breakdown
        monthly_returns = self._calculate_monthly_returns(df)

        # Symbol performance
        symbol_performance = self._analyze_symbol_performance(df)

        # Exchange performance
        exchange_performance = self._analyze_exchange_performance(df)

        # Time-based analysis
        time_analysis = self._analyze_time_performance(df)

        # Additional metrics
        avg_holding_time = self._calculate_avg_holding_time(df)
        best_worst_streaks = self._calculate_win_loss_streaks(df)
        volatility_metrics = self._calculate_volatility_metrics(returns)

        performance_report = {
            'overview': {
                'total_trades': total_trades,
                'winning_trades': winning_trades,
                'losing_trades': losing_trades,
                'win_rate': win_rate,
                'win_rate_pct': win_rate * 100,
                'total_pnl': total_pnl,
                'total_return_pct': total_return_pct,
                'avg_trade_pnl': avg_trade_pnl,
                'median_trade_pnl': median_trade_pnl,
                'largest_win': largest_win,
                'largest_loss': largest_loss
            },
            'risk_metrics': {
                'sharpe_ratio': sharpe_ratio,
                'sortino_ratio': sortino_ratio,
                'max_drawdown': max_drawdown,
                'max_drawdown_pct': max_drawdown * 100,
                'calmar_ratio': calmar_ratio,
                'profit_factor': profit_factor,
                'recovery_factor': recovery_factor,
                'expectancy': expectancy,
                'kelly_criterion': kelly
            },
            'trading_metrics': {
                'trades_per_day': trades_per_day,
                'gross_profit': gross_profit,
                'gross_loss': gross_loss,
                'avg_win': df[df['pnl'] > 0]['pnl'].mean() if winning_trades > 0 else 0,
                'avg_loss': df[df['pnl'] < 0]['pnl'].mean() if losing_trades > 0 else 0,
                'win_loss_ratio': (df[df['pnl'] > 0]['pnl'].mean() /
                                 abs(df[df['pnl'] < 0]['pnl'].mean())) if losing_trades > 0 else float('inf')
            },
            'breakdown': {
                'monthly_returns': monthly_returns,
                'symbol_performance': symbol_performance,
                'exchange_performance': exchange_performance,
                'time_analysis': time_analysis
            },
            'additional_metrics': {
                'avg_holding_time_minutes': avg_holding_time,
                'best_win_streak': best_worst_streaks['best_win_streak'],
                'worst_loss_streak': best_worst_streaks['worst_loss_streak'],
                'return_volatility': volatility_metrics['volatility'],
                'value_at_risk_95': volatility_metrics['var_95']
            },
            'metadata': {
                'analysis_period_days': date_range,
                'start_date': df['timestamp'].min().isoformat() if not df.empty else None,
                'end_date': df['timestamp'].max().isoformat() if not df.empty else None,
                'generated_at': datetime.now().isoformat()
            }
        }

        return performance_report

    def _calculate_monthly_returns(self, df: pd.DataFrame) -> List[Dict]:
        """Calculate monthly return breakdown"""

        if df.empty:
            return []

        # Group by month
        df['month'] = df['timestamp'].dt.to_period('M')
        monthly = df.groupby('month').agg({
            'pnl': 'sum',
            'timestamp': 'count'
        }).rename(columns={'timestamp': 'trades'})

        monthly_returns = []
        for period, row in monthly.iterrows():
            monthly_returns.append({
                'month': str(period),
                'pnl': row['pnl'],
                'trades': row['trades'],
                'return_pct': (row['pnl'] / 10000.0) * 100  # Assuming $10k base
            })

        return monthly_returns

    def _analyze_symbol_performance(self, df: pd.DataFrame) -> List[Dict]:
        """Analyze performance by trading symbol"""

        if df.empty:
            return []

        symbol_stats = []
        for symbol in df['symbol'].unique():
            symbol_df = df[df['symbol'] == symbol]

            symbol_stats.append({
                'symbol': symbol,
                'trades': len(symbol_df),
                'total_pnl': symbol_df['pnl'].sum(),
                'avg_pnl': symbol_df['pnl'].mean(),
                'win_rate': len(symbol_df[symbol_df['pnl'] > 0]) / len(symbol_df),
                'best_trade': symbol_df['pnl'].max(),
                'worst_trade': symbol_df['pnl'].min()
            })

        return symbol_stats

    def _analyze_exchange_performance(self, df: pd.DataFrame) -> Dict:
        """Analyze performance by exchange"""

        if df.empty:
            return {}

        exchange_stats = {}

        # Buy exchanges
        buy_exchanges = df.groupby('buy_exchange').agg({
            'pnl': ['count', 'sum', 'mean'],
            'quantity': 'sum'
        })

        for exchange, ex_stats in buy_exchanges.iterrows():
            exchange_stats[f"{exchange}_buy"] = {
                'trades': ex_stats[('pnl', 'count')],
                'total_pnl': ex_stats[('pnl', 'sum')],
                'avg_pnl': ex_stats[('pnl', 'mean')],
                'total_volume': ex_stats[('quantity', 'sum')]
            }

        # Sell exchanges
        sell_exchanges = df.groupby('sell_exchange').agg({
            'pnl': ['count', 'sum', 'mean'],
            'quantity': 'sum'
        })

        for exchange, ex_stats in sell_exchanges.iterrows():
            exchange_stats[f"{exchange}_sell"] = {
                'trades': ex_stats[('pnl', 'count')],
                'total_pnl': ex_stats[('pnl', 'sum')],
                'avg_pnl': ex_stats[('pnl', 'mean')],
                'total_volume': ex_stats[('quantity', 'sum')]
            }

        return exchange_stats

    def _analyze_time_performance(self, df: pd.DataFrame) -> Dict:
        """Analyze performance by time of day"""

        if df.empty:
            return {}

        # Add hour of day
        df['hour'] = df['timestamp'].dt.hour

        hourly_stats = []
        for hour in range(24):
            hour_df = df[df['hour'] == hour]
            if not hour_df.empty:
                hourly_stats.append({
                    'hour': hour,
                    'trades': len(hour_df),
                    'total_pnl': hour_df['pnl'].sum(),
                    'avg_pnl': hour_df['pnl'].mean(),
                    'win_rate': len(hour_df[hour_df['pnl'] > 0]) / len(hour_df)
                })

        # Day of week analysis
        df['day_of_week'] = df['timestamp'].dt.day_name()
        daily_stats = []
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']:
            day_df = df[df['day_of_week'] == day]
            if not day_df.empty:
                daily_stats.append({
                    'day': day,
                    'trades': len(day_df),
                    'total_pnl': day_df['pnl'].sum(),
                    'avg_pnl': day_df['pnl'].mean(),
                    'win_rate': len(day_df[day_df['pnl'] > 0]) / len(day_df)
                })

        return {
            'hourly_performance': hourly_stats,
            'daily_performance': daily_stats
        }

    def _calculate_avg_holding_time(self, df: pd.DataFrame) -> float:
        """Calculate average holding time in minutes"""

        if df.empty or 'exit_timestamp' not in df.columns:
            return 0.0

        # Calculate holding times
        df['holding_time'] = (pd.to_datetime(df['exit_timestamp']) - df['timestamp']).dt.total_seconds() / 60
        return df['holding_time'].mean()

    def _calculate_win_loss_streaks(self, df: pd.DataFrame) -> Dict:
        """Calculate best and worst win/loss streaks"""

        if df.empty:
            return {'best_win_streak': 0, 'worst_loss_streak': 0}

        # Calculate win/loss streaks
        pnl_signs = np.sign(df['pnl'])
        streaks = []
        current_streak = 1

        for i in range(1, len(pnl_signs)):
            if pnl_signs[i] == pnl_signs[i-1]:
                current_streak += 1
            else:
                streaks.append((pnl_signs[i-1], current_streak))
                current_streak = 1

        streaks.append((pnl_signs.iloc[-1], current_streak))

        win_streaks = [streak for sign, streak in streaks if sign > 0]
        loss_streaks = [streak for sign, streak in streaks if sign < 0]

        return {
            'best_win_streak': max(win_streaks) if win_streaks else 0,
            'worst_loss_streak': max(loss_streaks) if loss_streaks else 0
        }

    def _calculate_volatility_metrics(self, returns: pd.Series) -> Dict:
        """Calculate volatility and risk metrics"""

        if len(returns) < 2:
            return {'volatility': 0.0, 'var_95': 0.0, 'skewness': 0.0, 'kurtosis': 0.0}

        return {
            'volatility': returns.std() * np.sqrt(365),  # Annualized volatility
            'var_95': np.percentile(returns, 5),  # 95% VaR (5th percentile)
            'skewness': stats.skew(returns),
            'kurtosis': stats.kurtosis(returns)
        }

    def generate_performance_report(self, trades: List[Dict], output_format: str = 'json') -> str:
        """Generate formatted performance report"""

        analysis = self.analyze_portfolio_performance(trades)

        if 'error' in analysis:
            return json.dumps(analysis, indent=2)

        if output_format == 'json':
            return json.dumps(analysis, indent=2, default=str)

        elif output_format == 'text':
            return self._format_text_report(analysis)

        elif output_format == 'html':
            return self._format_html_report(analysis)

        else:
            return json.dumps(analysis, indent=2, default=str)

    def _format_text_report(self, analysis: Dict) -> str:
        """Format analysis as readable text report"""

        report = []
        report.append("=" * 60)
        report.append("SOVEREIGNFORGE PERFORMANCE REPORT")
        report.append("=" * 60)

        # Overview
        overview = analysis['overview']
        report.append("\nTRADING OVERVIEW:")
        report.append(f"Total Trades: {overview['total_trades']}")
        report.append(f"Win Rate: {overview['win_rate_pct']:.1f}%")
        report.append(f"Total P&L: ${overview['total_pnl']:.2f}")
        report.append(f"Total Return: {overview['total_return_pct']:.2f}%")
        report.append(f"Average Trade: ${overview['avg_trade_pnl']:.2f}")

        # Risk Metrics
        risk = analysis['risk_metrics']
        report.append("\nRISK METRICS:")
        report.append(f"Sharpe Ratio: {risk['sharpe_ratio']:.3f}")
        report.append(f"Sortino Ratio: {risk['sortino_ratio']:.3f}")
        report.append(f"Max Drawdown: {risk['max_drawdown_pct']:.2f}%")
        report.append(f"Calmar Ratio: {risk['calmar_ratio']:.3f}")
        report.append(f"Profit Factor: {risk['profit_factor']:.3f}")
        report.append(f"Recovery Factor: {risk['recovery_factor']:.3f}")

        # Trading Metrics
        trading = analysis['trading_metrics']
        report.append("\nTRADING METRICS:")
        report.append(f"Trades per Day: {trading['trades_per_day']:.2f}")
        report.append(f"Gross Profit: ${trading['gross_profit']:.2f}")
        report.append(f"Gross Loss: ${trading['gross_loss']:.2f}")
        report.append(f"Average Win: ${trading['avg_win']:.2f}")
        report.append(f"Average Loss: ${trading['avg_loss']:.2f}")

        # Additional Metrics
        additional = analysis.get('additional_metrics', {})
        if additional:
            report.append("\nADDITIONAL METRICS:")
            report.append(f"Avg Holding Time: {additional.get('avg_holding_time_minutes', 0):.1f} minutes")
            report.append(f"Best Win Streak: {additional.get('best_win_streak', 0)}")
            report.append(f"Worst Loss Streak: {additional.get('worst_loss_streak', 0)}")
            report.append(f"Return Volatility: {additional.get('return_volatility', 0):.4f}")
            report.append(f"Value at Risk (95%): {additional.get('value_at_risk_95', 0):.4f}")

        report.append("\n" + "=" * 60)
        return "\n".join(report)

    def _format_html_report(self, analysis: Dict) -> str:
        """Format analysis as HTML report"""

        html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>SovereignForge Performance Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .metric {{ background: #f5f5f5; padding: 10px; margin: 10px 0; border-radius: 5px; }}
                .positive {{ color: green; }}
                .negative {{ color: red; }}
                h1, h2 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #f2f2f2; }}
            </style>
        </head>
        <body>
            <h1>SovereignForge Performance Report</h1>
            <p><strong>Generated:</strong> {analysis['metadata']['generated_at']}</p>
            <p><strong>Period:</strong> {analysis['metadata']['start_date']} to {analysis['metadata']['end_date']}</p>

            <h2>Trading Overview</h2>
            <div class="metric">
                <p><strong>Total Trades:</strong> {analysis['overview']['total_trades']}</p>
                <p><strong>Win Rate:</strong> <span class="positive">{analysis['overview']['win_rate_pct']:.1f}%</span></p>
                <p><strong>Total P&L:</strong> <span class="{'positive' if analysis['overview']['total_pnl'] >= 0 else 'negative'}">${analysis['overview']['total_pnl']:.2f}</span></p>
                <p><strong>Total Return:</strong> <span class="{'positive' if analysis['overview']['total_return_pct'] >= 0 else 'negative'}">{analysis['overview']['total_return_pct']:.2f}%</span></p>
            </div>

            <h2>Risk Metrics</h2>
            <div class="metric">
                <p><strong>Sharpe Ratio:</strong> {analysis['risk_metrics']['sharpe_ratio']:.3f}</p>
                <p><strong>Sortino Ratio:</strong> {analysis['risk_metrics']['sortino_ratio']:.3f}</p>
                <p><strong>Max Drawdown:</strong> <span class="negative">{analysis['risk_metrics']['max_drawdown_pct']:.2f}%</span></p>
                <p><strong>Calmar Ratio:</strong> {analysis['risk_metrics']['calmar_ratio']:.3f}</p>
            </div>

            <h2>Monthly Performance</h2>
            <table>
                <tr><th>Month</th><th>Trades</th><th>P&L</th><th>Return %</th></tr>
        """

        for month in analysis['breakdown']['monthly_returns']:
            html += f"""
                <tr>
                    <td>{month['month']}</td>
                    <td>{month['trades']}</td>
                    <td class="{'positive' if month['pnl'] >= 0 else 'negative'}">${month['pnl']:.2f}</td>
                    <td class="{'positive' if month['return_pct'] >= 0 else 'negative'}">{month['return_pct']:.2f}%</td>
                </tr>
            """

        html += """
            </table>
        </body>
        </html>
        """

        return html

    def save_report(self, analysis: Dict, filename: str, format: str = 'json'):
        """Save performance report to file"""

        report_content = self.generate_performance_report([], format)
        if 'error' not in analysis:
            report_content = self.generate_performance_report([], format)

        # Create reports directory if it doesn't exist
        reports_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "reports")
        os.makedirs(reports_dir, exist_ok=True)

        filepath = os.path.join(reports_dir, filename)

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(report_content)

        logger.info(f"Performance report saved to {filepath}")
        return filepath

    def get_real_time_metrics(self) -> Dict:
        """Get real-time performance metrics"""

        if not self.risk_manager:
            return {'error': 'Risk manager not available'}

        metrics = self.risk_manager.get_risk_metrics()

        # Add additional real-time metrics
        current_time = datetime.now()

        return {
            'timestamp': current_time.isoformat(),
            'portfolio_value': metrics['portfolio_value'],
            'daily_pnl': metrics['daily_pnl'],
            'open_positions': metrics['open_positions'],
            'current_drawdown': metrics['current_drawdown'],
            'sharpe_ratio': metrics['sharpe_ratio'],
            'win_rate': metrics['win_rate'],
            'total_trades': metrics['total_trades'],
            'status': 'active' if metrics['open_positions'] > 0 else 'idle'
        }

class PerformanceDashboard:
    """Web dashboard for performance visualization"""

    def __init__(self, analyzer: PerformanceAnalyzer):
        self.analyzer = analyzer

    def generate_dashboard_data(self, trades: List[Dict]) -> Dict:
        """Generate data for dashboard visualization"""

        analysis = self.analyzer.analyze_portfolio_performance(trades)

        if 'error' in analysis:
            return analysis

        # Prepare chart data
        dashboard_data = {
            'summary': {
                'total_pnl': analysis['overview']['total_pnl'],
                'win_rate': analysis['overview']['win_rate_pct'],
                'total_trades': analysis['overview']['total_trades'],
                'sharpe_ratio': analysis['risk_metrics']['sharpe_ratio']
            },
            'charts': {
                'monthly_returns': [
                    {'month': m['month'], 'pnl': m['pnl'], 'return_pct': m['return_pct']}
                    for m in analysis['breakdown']['monthly_returns']
                ],
                'symbol_performance': analysis['breakdown']['symbol_performance'],
                'hourly_performance': analysis['breakdown']['time_analysis']['hourly_performance']
            },
            'risk_indicators': {
                'current_drawdown': analysis['risk_metrics']['max_drawdown_pct'],
                'volatility': analysis.get('additional_metrics', {}).get('return_volatility', 0),
                'var_95': analysis.get('additional_metrics', {}).get('value_at_risk_95', 0)
            }
        }

        return dashboard_data

def create_performance_analyzer(risk_manager=None, backtester=None) -> PerformanceAnalyzer:
    """Create performance analyzer instance"""

    return PerformanceAnalyzer(risk_manager, backtester)

# Example usage and testing
if __name__ == "__main__":
    # Create analyzer
    analyzer = create_performance_analyzer()

    # Sample trades for testing
    sample_trades = [
        {
            'timestamp': datetime.now() - timedelta(days=30),
            'symbol': 'BTC/USDC',
            'buy_exchange': 'binance',
            'sell_exchange': 'coinbase',
            'quantity': 0.01,
            'buy_price': 45000,
            'sell_price': 45050,
            'pnl': 0.5,
            'fees': 0.05
        },
        {
            'timestamp': datetime.now() - timedelta(days=25),
            'symbol': 'ETH/USDC',
            'buy_exchange': 'kraken',
            'sell_exchange': 'binance',
            'quantity': 0.1,
            'buy_price': 3000,
            'sell_price': 2995,
            'pnl': -0.5,
            'fees': 0.03
        }
    ]

    # Generate analysis
    analysis = analyzer.analyze_portfolio_performance(sample_trades)

    if 'error' not in analysis:
        print("Performance Analysis Results:")
        print(f"Total Trades: {analysis['overview']['total_trades']}")
        print(f"Win Rate: {analysis['overview']['win_rate_pct']:.1f}%")
        print(f"Total P&L: ${analysis['overview']['total_pnl']:.2f}")
        print(f"Sharpe Ratio: {analysis['risk_metrics']['sharpe_ratio']:.3f}")
        print(f"Max Drawdown: {analysis['risk_metrics']['max_drawdown_pct']:.2f}%")

        # Save text report
        analyzer.save_report(analysis, 'performance_report.txt', 'text')
        print("Report saved to reports/performance_report.txt")
    else:
        print(f"Analysis error: {analysis['error']}")
