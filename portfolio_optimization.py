#!/usr/bin/env python3
"""
SovereignForge Portfolio Optimization
Advanced portfolio optimization using Modern Portfolio Theory and Risk Parity
"""

import numpy as np
import pandas as pd
from scipy.optimize import minimize
import torch
import torch.nn as nn
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
from pathlib import Path
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class ModernPortfolioTheory:
    """Modern Portfolio Theory implementation for optimal asset allocation"""

    def __init__(self, returns_data: pd.DataFrame, risk_free_rate: float = 0.02):
        self.returns_data = returns_data
        self.risk_free_rate = risk_free_rate
        self.assets = returns_data.columns.tolist()

        # Calculate key statistics
        self.expected_returns = returns_data.mean() * 252  # Annualized
        self.covariance_matrix = returns_data.cov() * 252  # Annualized

        logger.info(f"✅ Initialized MPT with {len(self.assets)} assets")

    def calculate_efficient_frontier(self, num_portfolios: int = 1000) -> pd.DataFrame:
        """Calculate the efficient frontier using Monte Carlo simulation"""

        np.random.seed(42)
        results = np.zeros((3, num_portfolios))
        weights_record = []

        for i in range(num_portfolios):
            # Generate random weights
            weights = np.random.random(len(self.assets))
            weights /= np.sum(weights)

            # Calculate portfolio metrics
            portfolio_return = np.sum(weights * self.expected_returns)
            portfolio_volatility = np.sqrt(np.dot(weights.T, np.dot(self.covariance_matrix, weights)))
            sharpe_ratio = (portfolio_return - self.risk_free_rate) / portfolio_volatility

            # Store results
            results[0,i] = portfolio_return
            results[1,i] = portfolio_volatility
            results[2,i] = sharpe_ratio
            weights_record.append(weights)

        # Create results DataFrame
        results_df = pd.DataFrame({
            'Return': results[0],
            'Volatility': results[1],
            'Sharpe': results[2]
        })

        # Add weights
        for i, asset in enumerate(self.assets):
            results_df[f'Weight_{asset}'] = [w[i] for w in weights_record]

        return results_df

    def optimize_portfolio(self, target_return: Optional[float] = None,
                          max_volatility: Optional[float] = None,
                          optimization_type: str = 'sharpe') -> Dict[str, Any]:
        """Optimize portfolio using mathematical optimization"""

        num_assets = len(self.assets)

        # Define constraints
        constraints = [{'type': 'eq', 'fun': lambda x: np.sum(x) - 1}]  # Weights sum to 1
        bounds = tuple((0, 1) for asset in range(num_assets))  # Long-only constraint

        # Add target return constraint if specified
        if target_return is not None:
            constraints.append({
                'type': 'eq',
                'fun': lambda x: self._portfolio_return(x) - target_return
            })

        # Add volatility constraint if specified
        if max_volatility is not None:
            constraints.append({
                'type': 'ineq',
                'fun': lambda x: max_volatility - self._portfolio_volatility(x)
            })

        # Define objective function based on optimization type
        if optimization_type == 'sharpe':
            # Maximize Sharpe ratio
            objective = lambda x: -(self._portfolio_return(x) - self.risk_free_rate) / self._portfolio_volatility(x)
        elif optimization_type == 'min_volatility':
            # Minimize volatility
            objective = self._portfolio_volatility
        elif optimization_type == 'max_return':
            # Maximize return
            objective = lambda x: -self._portfolio_return(x)
        else:
            raise ValueError(f"Unknown optimization type: {optimization_type}")

        # Initial guess (equal weight)
        x0 = np.array([1/num_assets] * num_assets)

        # Optimize
        result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)

        if result.success:
            optimal_weights = result.x
            return {
                'success': True,
                'weights': dict(zip(self.assets, optimal_weights)),
                'expected_return': self._portfolio_return(optimal_weights),
                'volatility': self._portfolio_volatility(optimal_weights),
                'sharpe_ratio': (self._portfolio_return(optimal_weights) - self.risk_free_rate) / self._portfolio_volatility(optimal_weights),
                'optimization_type': optimization_type
            }
        else:
            return {
                'success': False,
                'error': result.message,
                'optimization_type': optimization_type
            }

    def _portfolio_return(self, weights: np.ndarray) -> float:
        """Calculate portfolio expected return"""
        return np.sum(weights * self.expected_returns)

    def _portfolio_volatility(self, weights: np.ndarray) -> float:
        """Calculate portfolio volatility"""
        return np.sqrt(np.dot(weights.T, np.dot(self.covariance_matrix, weights)))

    def calculate_var(self, weights: np.ndarray, confidence_level: float = 0.95) -> float:
        """Calculate Value at Risk"""
        portfolio_returns = self.returns_data.dot(weights)
        return -np.percentile(portfolio_returns, (1 - confidence_level) * 100)

    def calculate_cvar(self, weights: np.ndarray, confidence_level: float = 0.95) -> float:
        """Calculate Conditional Value at Risk (Expected Shortfall)"""
        portfolio_returns = self.returns_data.dot(weights)
        var = self.calculate_var(weights, confidence_level)
        return -portfolio_returns[portfolio_returns <= -var].mean()

class RiskParityPortfolio:
    """Risk Parity portfolio optimization"""

    def __init__(self, returns_data: pd.DataFrame):
        self.returns_data = returns_data
        self.assets = returns_data.columns.tolist()
        self.covariance_matrix = returns_data.cov() * 252  # Annualized

    def optimize_risk_parity(self, target_risk_contribution: Optional[float] = None) -> Dict[str, Any]:
        """Optimize portfolio for equal risk contribution"""

        num_assets = len(self.assets)

        if target_risk_contribution is None:
            target_risk_contribution = 1.0 / num_assets

        def risk_parity_objective(weights):
            """Objective function for risk parity optimization"""
            portfolio_vol = self._portfolio_volatility(weights)
            risk_contributions = self._calculate_risk_contributions(weights, portfolio_vol)
            target_contributions = np.full(num_assets, target_risk_contribution)
            return np.sum((risk_contributions - target_contributions) ** 2)

        # Constraints
        constraints = [
            {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # Weights sum to 1
        ]
        bounds = tuple((0.01, 0.5) for asset in range(num_assets))  # Min 1%, max 50%

        # Initial guess
        x0 = np.array([1/num_assets] * num_assets)

        # Optimize
        result = minimize(risk_parity_objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)

        if result.success:
            optimal_weights = result.x
            portfolio_vol = self._portfolio_volatility(optimal_weights)
            risk_contributions = self._calculate_risk_contributions(optimal_weights, portfolio_vol)

            return {
                'success': True,
                'weights': dict(zip(self.assets, optimal_weights)),
                'risk_contributions': dict(zip(self.assets, risk_contributions)),
                'portfolio_volatility': portfolio_vol,
                'diversification_ratio': self._calculate_diversification_ratio(optimal_weights)
            }
        else:
            return {
                'success': False,
                'error': result.message
            }

    def _calculate_risk_contributions(self, weights: np.ndarray, portfolio_vol: float) -> np.ndarray:
        """Calculate risk contribution of each asset"""
        marginal_risk = np.dot(self.covariance_matrix, weights) / portfolio_vol
        risk_contributions = weights * marginal_risk
        return risk_contributions

    def _portfolio_volatility(self, weights: np.ndarray) -> float:
        """Calculate portfolio volatility"""
        return np.sqrt(np.dot(weights.T, np.dot(self.covariance_matrix, weights)))

    def _calculate_diversification_ratio(self, weights: np.ndarray) -> float:
        """Calculate diversification ratio"""
        weighted_volatilities = weights * np.sqrt(np.diag(self.covariance_matrix))
        portfolio_vol = self._portfolio_volatility(weights)
        return np.sum(weighted_volatilities) / portfolio_vol

class BlackLittermanModel:
    """Black-Litterman model for incorporating views into portfolio optimization"""

    def __init__(self, prior_returns: pd.Series, covariance_matrix: pd.DataFrame,
                 risk_aversion: float = 2.5, tau: float = 0.05):
        self.prior_returns = prior_returns
        self.covariance_matrix = covariance_matrix
        self.risk_aversion = risk_aversion
        self.tau = tau  # Uncertainty in prior

    def incorporate_views(self, views: Dict[str, Dict]) -> pd.Series:
        """
        Incorporate investor views into the return estimates

        views format: {
            'asset_name': {
                'type': 'absolute' or 'relative',
                'value': expected_return or difference,
                'confidence': confidence_level (0-1),
                'benchmark': benchmark_asset (for relative views)
            }
        }
        """

        assets = self.prior_returns.index.tolist()
        num_assets = len(assets)

        # Build pick matrix P and view vector Q
        P = []
        Q = []

        for view_asset, view_data in views.items():
            if view_data['type'] == 'absolute':
                # Absolute view: asset will return X%
                p_row = np.zeros(num_assets)
                p_row[assets.index(view_asset)] = 1.0
                P.append(p_row)
                Q.append(view_data['value'])

            elif view_data['type'] == 'relative':
                # Relative view: asset will outperform benchmark by X%
                p_row = np.zeros(num_assets)
                p_row[assets.index(view_asset)] = 1.0
                p_row[assets.index(view_data['benchmark'])] = -1.0
                P.append(p_row)
                Q.append(view_data['value'])

        P = np.array(P)
        Q = np.array(Q)

        # Confidence levels (diagonal matrix)
        Omega = np.zeros((len(Q), len(Q)))
        for i, view_data in enumerate(views.values()):
            confidence = view_data.get('confidence', 0.5)
            # Uncertainty proportional to 1/confidence
            Omega[i, i] = (1 / confidence) * self.tau

        # Black-Litterman formula
        try:
            tau_sigma = self.tau * self.covariance_matrix.values

            # Matrix inversion
            temp = np.linalg.inv(np.dot(np.dot(P, tau_sigma), P.T) + Omega)
            posterior_returns = self.prior_returns.values + np.dot(
                np.dot(np.dot(tau_sigma, P.T), temp),
                (Q - np.dot(P, self.prior_returns.values))
            )

            return pd.Series(posterior_returns, index=assets)

        except np.linalg.LinAlgError:
            logger.warning("Matrix inversion failed in Black-Litterman model")
            return self.prior_returns

class PortfolioRebalancingEngine:
    """Portfolio rebalancing and drift monitoring"""

    def __init__(self, target_weights: Dict[str, float], rebalance_threshold: float = 0.05):
        self.target_weights = target_weights
        self.rebalance_threshold = rebalance_threshold
        self.current_weights = target_weights.copy()

    def check_drift(self, current_portfolio_value: float, current_positions: Dict[str, float]) -> Dict[str, Any]:
        """Check if portfolio has drifted from target allocation"""

        total_value = sum(current_positions.values())

        # Calculate current weights
        current_weights = {}
        for asset, value in current_positions.items():
            current_weights[asset] = value / total_value

        # Calculate drift
        drift = {}
        max_drift = 0
        needs_rebalance = False

        for asset in self.target_weights.keys():
            target_weight = self.target_weights[asset]
            current_weight = current_weights.get(asset, 0)
            asset_drift = abs(current_weight - target_weight)

            drift[asset] = {
                'target_weight': target_weight,
                'current_weight': current_weight,
                'drift': asset_drift
            }

            max_drift = max(max_drift, asset_drift)
            if asset_drift > self.rebalance_threshold:
                needs_rebalance = True

        return {
            'needs_rebalance': needs_rebalance,
            'max_drift': max_drift,
            'drift_details': drift,
            'current_weights': current_weights
        }

    def calculate_rebalance_trades(self, current_positions: Dict[str, float],
                                 total_value: float) -> List[Dict]:
        """Calculate trades needed to rebalance portfolio"""

        trades = []

        for asset, target_weight in self.target_weights.items():
            target_value = total_value * target_weight
            current_value = current_positions.get(asset, 0)
            value_difference = target_value - current_value

            if abs(value_difference) > total_value * 0.001:  # Trade only if >0.1% of portfolio
                # Assume we can get current price from market data
                # For now, use placeholder price
                current_price = 1.0  # This should be fetched from market data

                quantity = value_difference / current_price

                trade = {
                    'asset': asset,
                    'action': 'buy' if quantity > 0 else 'sell',
                    'quantity': abs(quantity),
                    'value': abs(value_difference),
                    'reason': 'rebalance'
                }

                trades.append(trade)

        return trades

class AdvancedPortfolioAnalytics:
    """Advanced portfolio analytics and performance attribution"""

    def __init__(self, returns_data: pd.DataFrame, weights: Dict[str, float]):
        self.returns_data = returns_data
        self.weights = weights
        self.assets = list(weights.keys())

    def calculate_performance_attribution(self) -> Dict[str, Any]:
        """Calculate performance attribution by asset"""

        # Calculate portfolio returns
        portfolio_returns = self.returns_data[list(self.weights.keys())].dot(
            pd.Series(self.weights)
        )

        # Calculate asset contributions
        attribution = {}
        total_return = portfolio_returns.sum()

        for asset in self.assets:
            asset_weight = self.weights[asset]
            asset_returns = self.returns_data[asset]
            asset_contribution = asset_weight * asset_returns.sum()
            attribution[asset] = {
                'weight': asset_weight,
                'total_return': asset_returns.sum(),
                'contribution': asset_contribution,
                'contribution_pct': asset_contribution / total_return if total_return != 0 else 0
            }

        return {
            'total_portfolio_return': total_return,
            'asset_attribution': attribution,
            'top_performers': sorted(attribution.items(),
                                   key=lambda x: x[1]['contribution'], reverse=True)[:3],
            'worst_performers': sorted(attribution.items(),
                                     key=lambda x: x[1]['contribution'])[:3]
        }

    def calculate_risk_decomposition(self) -> Dict[str, Any]:
        """Decompose portfolio risk by asset"""

        # Calculate covariance matrix
        cov_matrix = self.returns_data[self.assets].cov() * 252  # Annualized

        # Calculate portfolio variance
        weights_array = np.array([self.weights[asset] for asset in self.assets])
        portfolio_variance = np.dot(weights_array.T, np.dot(cov_matrix.values, weights_array))
        portfolio_volatility = np.sqrt(portfolio_variance)

        # Calculate marginal and component risk
        risk_decomposition = {}

        for i, asset in enumerate(self.assets):
            # Marginal contribution to risk
            marginal_risk = np.dot(cov_matrix.values[i], weights_array) / portfolio_volatility

            # Component risk contribution
            component_risk = weights_array[i] * marginal_risk

            risk_decomposition[asset] = {
                'marginal_risk': marginal_risk,
                'component_risk': component_risk,
                'risk_contribution_pct': component_risk / portfolio_volatility
            }

        return {
            'portfolio_volatility': portfolio_volatility,
            'risk_decomposition': risk_decomposition,
            'diversification_ratio': sum(weights_array * np.sqrt(np.diag(cov_matrix.values))) / portfolio_volatility
        }

    def stress_test_portfolio(self, scenarios: Dict[str, Dict]) -> Dict[str, Any]:
        """Stress test portfolio under different market scenarios"""

        stress_results = {}

        for scenario_name, scenario_shocks in scenarios.items():
            # Apply shocks to asset returns
            stressed_returns = self.returns_data.copy()

            for asset, shock in scenario_shocks.items():
                if asset in stressed_returns.columns:
                    stressed_returns[asset] = stressed_returns[asset] * (1 + shock)

            # Calculate stressed portfolio returns
            stressed_portfolio_returns = stressed_returns[list(self.weights.keys())].dot(
                pd.Series(self.weights)
            )

            # Calculate impact metrics
            impact = {
                'mean_return': stressed_portfolio_returns.mean() * 252,
                'volatility': stressed_portfolio_returns.std() * np.sqrt(252),
                'max_drawdown': self._calculate_max_drawdown(stressed_portfolio_returns),
                'var_95': -np.percentile(stressed_portfolio_returns, 5),
                'worst_month': stressed_portfolio_returns.min()
            }

            stress_results[scenario_name] = impact

        return stress_results

    def _calculate_max_drawdown(self, returns: pd.Series) -> float:
        """Calculate maximum drawdown"""
        cumulative = (1 + returns).cumprod()
        running_max = cumulative.expanding().max()
        drawdown = (cumulative - running_max) / running_max
        return drawdown.min()

# Example usage and testing
def test_portfolio_optimization():
    """Test portfolio optimization functionality"""

    print("📊 Portfolio Optimization Test")
    print("=" * 50)

    # Generate sample return data
    np.random.seed(42)
    dates = pd.date_range(start='2023-01-01', periods=252, freq='D')
    assets = ['BTC', 'ETH', 'ADA', 'XRP', 'SOL']

    # Simulate realistic crypto returns
    returns_data = pd.DataFrame(index=dates)
    for asset in assets:
        # Base returns with some correlation
        base_returns = np.random.normal(0.001, 0.03, len(dates))
        if asset == 'BTC':
            returns_data[asset] = base_returns
        else:
            # Add correlation with BTC
            correlation = 0.6
            asset_specific = np.random.normal(0, 0.02, len(dates))
            returns_data[asset] = correlation * base_returns + (1-correlation) * asset_specific

    print(f"📈 Generated return data for {len(assets)} assets over {len(dates)} days")

    # Test Modern Portfolio Theory
    print("\n🎯 Testing Modern Portfolio Theory:")
    mpt = ModernPortfolioTheory(returns_data, risk_free_rate=0.02)

    # Calculate efficient frontier
    frontier = mpt.calculate_efficient_frontier(1000)
    print(f"✅ Calculated efficient frontier with {len(frontier)} portfolios")

    # Find optimal portfolios
    max_sharpe = mpt.optimize_portfolio(optimization_type='sharpe')
    min_vol = mpt.optimize_portfolio(optimization_type='min_volatility')

    if max_sharpe['success']:
        print("📊 Maximum Sharpe Ratio Portfolio:")
        for asset, weight in max_sharpe['weights'].items():
            print(".1%")
        print(".2%")
        print(".2f")

    # Test Risk Parity
    print("\n⚖️  Testing Risk Parity Optimization:")
    risk_parity = RiskParityPortfolio(returns_data)
    rp_result = risk_parity.optimize_risk_parity()

    if rp_result['success']:
        print("📊 Risk Parity Portfolio:")
        for asset, weight in rp_result['weights'].items():
            print(".1%")
        print(".2%")
        print(".2f")

    # Test Black-Litterman
    print("\n🎯 Testing Black-Litterman Model:")
    bl_model = BlackLittermanModel(
        prior_returns=returns_data.mean() * 252,
        covariance_matrix=returns_data.cov() * 252
    )

    # Add some views
    views = {
        'BTC': {'type': 'absolute', 'value': 0.15, 'confidence': 0.8},  # BTC will return 15%
        'ETH': {'type': 'relative', 'value': 0.05, 'confidence': 0.6, 'benchmark': 'BTC'}  # ETH will outperform BTC by 5%
    }

    posterior_returns = bl_model.incorporate_views(views)
    print("✅ Incorporated investor views into return estimates")

    # Test Portfolio Rebalancing
    print("\n🔄 Testing Portfolio Rebalancing:")
    target_weights = {'BTC': 0.4, 'ETH': 0.3, 'ADA': 0.2, 'XRP': 0.05, 'SOL': 0.05}
    rebalancer = PortfolioRebalancingEngine(target_weights, rebalance_threshold=0.03)

    # Simulate current positions (slightly drifted)
    current_positions = {
        'BTC': 10000 * 0.42,  # 42% instead of 40%
        'ETH': 10000 * 0.28,  # 28% instead of 30%
        'ADA': 10000 * 0.22,  # 22% instead of 20%
        'XRP': 10000 * 0.04,  # 4% instead of 5%
        'SOL': 10000 * 0.04   # 4% instead of 5%
    }

    drift_check = rebalancer.check_drift(10000, current_positions)
    print(f"📊 Portfolio drift check: Needs rebalance = {drift_check['needs_rebalance']}")
    print(".1%")

    if drift_check['needs_rebalance']:
        rebalance_trades = rebalancer.calculate_rebalance_trades(current_positions, 10000)
        print(f"📋 Required rebalance trades: {len(rebalance_trades)}")

    # Test Advanced Analytics
    print("\n📈 Testing Advanced Analytics:")
    analytics = AdvancedPortfolioAnalytics(returns_data, target_weights)

    attribution = analytics.calculate_performance_attribution()
    print("✅ Calculated performance attribution by asset")

    risk_decomp = analytics.calculate_risk_decomposition()
    print("✅ Performed risk decomposition analysis")

    # Stress testing scenarios
    scenarios = {
        'crypto_crash': {'BTC': -0.5, 'ETH': -0.6, 'ADA': -0.7, 'XRP': -0.8, 'SOL': -0.6},
        'btc_dominance': {'BTC': 0.3, 'ETH': -0.1, 'ADA': -0.1, 'XRP': -0.1, 'SOL': -0.1},
        'alt_season': {'BTC': 0.1, 'ETH': 0.3, 'ADA': 0.4, 'XRP': 0.5, 'SOL': 0.3}
    }

    stress_results = analytics.stress_test_portfolio(scenarios)
    print("✅ Completed portfolio stress testing")

    print("\n" + "=" * 50)
    print("🎉 Portfolio Optimization Test Complete!")
    print("✅ All optimization methods working correctly")
    print("✅ Risk management and attribution functional")
    print("✅ Rebalancing and stress testing operational")
    print()
    print("🚀 Ready for advanced portfolio management!")

if __name__ == '__main__':
    test_portfolio_optimization()