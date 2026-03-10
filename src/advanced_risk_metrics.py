#!/usr/bin/env python3
"""
SovereignForge - Advanced Risk Metrics Module
Implements sophisticated risk calculations for crypto arbitrage trading

This module provides:
- Historical Simulation VaR and Expected Shortfall
- Monte Carlo VaR with volatility clustering
- Stress testing frameworks for crypto scenarios
- Scenario analysis for market crashes and exchange outages
- Dynamic risk adjustment algorithms
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging
from scipy import stats
from scipy.stats import norm, t
import torch
import torch.nn as nn

logger = logging.getLogger(__name__)

@dataclass
class RiskMetrics:
    """Container for comprehensive risk metrics"""
    var_95_hs: float  # Historical Simulation VaR 95%
    var_99_hs: float  # Historical Simulation VaR 99%
    es_95_hs: float   # Historical Simulation ES 95%
    es_99_hs: float   # Historical Simulation ES 99%
    var_95_mc: float  # Monte Carlo VaR 95%
    var_99_mc: float  # Monte Carlo VaR 99%
    es_95_mc: float   # Monte Carlo ES 95%
    es_99_mc: float   # Monte Carlo ES 99%
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    volatility: float
    skewness: float
    kurtosis: float
    stress_test_loss: float
    scenario_analysis: Dict[str, float]

@dataclass
class StressTestScenario:
    """Definition of a stress test scenario"""
    name: str
    description: str
    price_shocks: Dict[str, float]  # Asset -> shock percentage
    volatility_multiplier: float
    correlation_breakdown: bool
    liquidity_dryup: float  # Percentage of volume lost

class AdvancedRiskMetrics:
    """
    Advanced risk metrics calculator using multiple methodologies
    """

    def __init__(self,
                 confidence_levels: List[float] = [0.95, 0.99],
                 time_horizon_days: int = 1,
                 monte_carlo_sims: int = 10000):
        self.confidence_levels = confidence_levels
        self.time_horizon_days = time_horizon_days
        self.monte_carlo_sims = monte_carlo_sims

        # Pre-defined stress test scenarios
        self.stress_scenarios = self._initialize_stress_scenarios()

    def _initialize_stress_scenarios(self) -> Dict[str, StressTestScenario]:
        """Initialize pre-defined stress test scenarios"""
        return {
            'crypto_crash': StressTestScenario(
                name='crypto_crash',
                description='Severe crypto market crash with correlation breakdown',
                price_shocks={'BTC': -0.5, 'ETH': -0.6, 'XRP': -0.7, 'ADA': -0.65,
                            'XLM': -0.65, 'HBAR': -0.7, 'ALGO': -0.6},
                volatility_multiplier=2.5,
                correlation_breakdown=True,
                liquidity_dryup=0.4
            ),
            'btc_dominance': StressTestScenario(
                name='btc_dominance',
                description='BTC outperforms while alts crash',
                price_shocks={'BTC': -0.2, 'ETH': -0.5, 'XRP': -0.6, 'ADA': -0.55,
                            'XLM': -0.55, 'HBAR': -0.6, 'ALGO': -0.5},
                volatility_multiplier=1.8,
                correlation_breakdown=True,
                liquidity_dryup=0.2
            ),
            'exchange_outage': StressTestScenario(
                name='exchange_outage',
                description='Major exchange outage reducing liquidity',
                price_shocks={},  # No direct price shocks
                volatility_multiplier=1.5,
                correlation_breakdown=False,
                liquidity_dryup=0.6
            ),
            'correlation_breakdown': StressTestScenario(
                name='correlation_breakdown',
                description='BTC-altcoin correlation completely breaks down',
                price_shocks={},  # No direct price shocks
                volatility_multiplier=2.0,
                correlation_breakdown=True,
                liquidity_dryup=0.1
            )
        }

    def calculate_historical_var(self,
                               returns: np.ndarray,
                               confidence_level: float = 0.95) -> Tuple[float, float]:
        """
        Calculate Historical Simulation VaR and Expected Shortfall

        Args:
            returns: Array of historical returns
            confidence_level: Confidence level (0.95, 0.99, etc.)

        Returns:
            Tuple of (VaR, Expected Shortfall) as positive values
        """
        if len(returns) < 100:
            logger.warning(f"Insufficient data for HS VaR: {len(returns)} observations")
            return 0.0, 0.0

        # Sort returns in ascending order (worst to best)
        sorted_returns = np.sort(returns)

        # Find the VaR percentile
        var_index = int((1 - confidence_level) * len(sorted_returns))
        var = -sorted_returns[var_index]  # Make positive (loss amount)

        # Calculate Expected Shortfall (average of losses beyond VaR)
        tail_losses = sorted_returns[:var_index]
        es = -np.mean(tail_losses) if len(tail_losses) > 0 else var

        return var, es

    def calculate_monte_carlo_var(self,
                                returns: np.ndarray,
                                confidence_level: float = 0.95,
                                volatility_clustering: bool = True) -> Tuple[float, float]:
        """
        Calculate Monte Carlo VaR with optional volatility clustering

        Args:
            returns: Historical returns array
            confidence_level: Confidence level
            volatility_clustering: Whether to model volatility clustering (GARCH-like)

        Returns:
            Tuple of (VaR, Expected Shortfall)
        """
        if len(returns) < 30:
            logger.warning(f"Insufficient data for MC VaR: {len(returns)} observations")
            return 0.0, 0.0

        # Estimate parameters
        mu = np.mean(returns)
        sigma = np.std(returns)

        if volatility_clustering:
            # Simple GARCH(1,1) style volatility clustering
            alpha = 0.1  # ARCH parameter
            beta = 0.85  # GARCH parameter

            # Generate clustered volatility paths
            simulated_returns = []
            current_vol = sigma

            for _ in range(self.monte_carlo_sims):
                # Update volatility with clustering
                shock = np.random.normal(0, 1)
                current_vol = np.sqrt(alpha * shock**2 + beta * current_vol**2)

                # Generate return with current volatility
                ret = mu + current_vol * np.random.normal(0, 1)
                simulated_returns.append(ret)
        else:
            # Standard Monte Carlo
            simulated_returns = np.random.normal(mu, sigma, self.monte_carlo_sims)

        simulated_returns = np.array(simulated_returns)

        # Calculate VaR and ES from simulated returns
        var, es = self.calculate_historical_var(simulated_returns, confidence_level)

        return var, es

    def calculate_comprehensive_risk_metrics(self,
                                           returns: np.ndarray,
                                           portfolio_weights: Optional[np.ndarray] = None) -> RiskMetrics:
        """
        Calculate comprehensive risk metrics using multiple methodologies

        Args:
            returns: Historical returns array (can be portfolio or individual asset)
            portfolio_weights: Optional portfolio weights for portfolio-level analysis

        Returns:
            RiskMetrics object with all calculated metrics
        """
        if len(returns) == 0:
            logger.error("Empty returns array provided")
            return self._get_empty_risk_metrics()

        # Basic statistical metrics
        volatility = np.std(returns) * np.sqrt(252)  # Annualized
        skewness = stats.skew(returns)
        kurtosis = stats.kurtosis(returns)

        # Sharpe and Sortino ratios (assuming risk-free rate of 0 for crypto)
        excess_returns = returns  # Risk-free rate ≈ 0 for crypto
        sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) if np.std(excess_returns) > 0 else 0

        # Sortino ratio (downside deviation)
        downside_returns = returns[returns < 0]
        downside_deviation = np.std(downside_returns) if len(downside_returns) > 0 else 0.0001
        sortino_ratio = np.mean(excess_returns) / downside_deviation

        # Maximum drawdown
        cumulative = np.cumprod(1 + returns)
        running_max = np.maximum.accumulate(cumulative)
        drawdowns = (cumulative - running_max) / running_max
        max_drawdown = -np.min(drawdowns) if len(drawdowns) > 0 else 0

        # Historical Simulation VaR/ES
        var_95_hs, es_95_hs = self.calculate_historical_var(returns, 0.95)
        var_99_hs, es_99_hs = self.calculate_historical_var(returns, 0.99)

        # Monte Carlo VaR/ES
        var_95_mc, es_95_mc = self.calculate_monte_carlo_var(returns, 0.95)
        var_99_mc, es_99_mc = self.calculate_monte_carlo_var(returns, 0.99)

        # Stress testing
        stress_test_loss = self.run_stress_test_battery(returns)

        # Scenario analysis
        scenario_analysis = self.run_scenario_analysis(returns)

        return RiskMetrics(
            var_95_hs=var_95_hs,
            var_99_hs=var_99_hs,
            es_95_hs=es_95_hs,
            es_99_hs=es_99_hs,
            var_95_mc=var_95_mc,
            var_99_mc=var_99_mc,
            es_95_mc=es_95_mc,
            es_99_mc=es_99_mc,
            max_drawdown=max_drawdown,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            volatility=volatility,
            skewness=skewness,
            kurtosis=kurtosis,
            stress_test_loss=stress_test_loss,
            scenario_analysis=scenario_analysis
        )

    def run_stress_test_battery(self, returns: np.ndarray) -> float:
        """
        Run comprehensive stress test battery

        Returns the maximum loss across all stress scenarios
        """
        max_loss = 0.0

        for scenario_name, scenario in self.stress_scenarios.items():
            loss = self._calculate_scenario_loss(returns, scenario)
            max_loss = max(max_loss, loss)

        return max_loss

    def run_scenario_analysis(self, returns: np.ndarray) -> Dict[str, float]:
        """
        Run scenario analysis for all pre-defined scenarios

        Returns dict of scenario_name -> loss_amount
        """
        results = {}

        for scenario_name, scenario in self.stress_scenarios.items():
            loss = self._calculate_scenario_loss(returns, scenario)
            results[scenario_name] = loss

        return results

    def _calculate_scenario_loss(self, returns: np.ndarray, scenario: StressTestScenario) -> float:
        """
        Calculate portfolio loss under a specific stress scenario

        This is a simplified implementation - in production, this would use
        more sophisticated modeling of price shocks, volatility changes, etc.
        """
        # Simplified scenario loss calculation
        # In production, this would use proper scenario modeling

        base_volatility = np.std(returns)
        scenario_volatility = base_volatility * scenario.volatility_multiplier

        # Estimate loss based on scenario parameters
        if scenario.price_shocks:
            # Direct price shock scenarios
            avg_shock = np.mean(list(scenario.price_shocks.values()))
            loss = abs(avg_shock) * scenario_volatility
        else:
            # Volatility-only scenarios
            loss = scenario_volatility * 2.0  # Conservative estimate

        # Adjust for liquidity dry-up
        loss *= (1 + scenario.liquidity_dryup)

        # Adjust for correlation breakdown (increases diversification risk)
        if scenario.correlation_breakdown:
            loss *= 1.5

        return loss

    def _get_empty_risk_metrics(self) -> RiskMetrics:
        """Return empty RiskMetrics object for error cases"""
        return RiskMetrics(
            var_95_hs=0.0, var_99_hs=0.0, es_95_hs=0.0, es_99_hs=0.0,
            var_95_mc=0.0, var_99_mc=0.0, es_95_mc=0.0, es_99_mc=0.0,
            max_drawdown=0.0, sharpe_ratio=0.0, sortino_ratio=0.0,
            volatility=0.0, skewness=0.0, kurtosis=0.0,
            stress_test_loss=0.0, scenario_analysis={}
        )

    def get_risk_limits(self, risk_metrics: RiskMetrics) -> Dict[str, float]:
        """
        Calculate dynamic risk limits based on current risk metrics

        Returns dict of limit_name -> limit_value
        """
        # Dynamic position size limits based on volatility
        base_limit = 0.02  # 2% base limit
        volatility_adjustment = min(risk_metrics.volatility * 10, 0.01)  # Cap at 1%
        position_limit = base_limit - volatility_adjustment

        # VaR-based limits
        var_limit = min(risk_metrics.var_95_hs * 2, 0.05)  # Max 5% limit

        # Stress test limits
        stress_limit = min(risk_metrics.stress_test_loss * 1.5, 0.08)  # Max 8% limit

        return {
            'position_limit': max(position_limit, 0.005),  # Min 0.5%
            'var_limit': var_limit,
            'stress_limit': stress_limit,
            'daily_loss_limit': 0.03,  # Fixed 3% daily loss limit
            'max_drawdown_limit': 0.15  # Fixed 15% max drawdown limit
        }


# Convenience functions for integration with existing risk management
def calculate_portfolio_var(returns: np.ndarray,
                          weights: np.ndarray,
                          confidence_level: float = 0.95,
                          method: str = 'historical') -> float:
    """
    Calculate portfolio-level VaR

    Args:
        returns: T x N array of asset returns (T periods, N assets)
        weights: N array of portfolio weights
        confidence_level: VaR confidence level
        method: 'historical' or 'monte_carlo'

    Returns:
        Portfolio VaR as positive value
    """
    if method == 'historical':
        # Simple historical simulation for portfolio
        portfolio_returns = np.dot(returns, weights)
        calculator = AdvancedRiskMetrics()
        var, _ = calculator.calculate_historical_var(portfolio_returns, confidence_level)
        return var
    else:
        # Monte Carlo approach would be more complex
        logger.warning("Monte Carlo portfolio VaR not yet implemented")
        return 0.0


def run_portfolio_stress_test(returns: np.ndarray,
                            weights: np.ndarray,
                            scenario: str = 'crypto_crash') -> float:
    """
    Run stress test on portfolio

    Args:
        returns: Historical returns data
        weights: Portfolio weights
        scenario: Stress scenario name

    Returns:
        Portfolio loss under stress scenario
    """
    calculator = AdvancedRiskMetrics()

    # For now, return the worst-case scenario loss
    # In production, this would be more sophisticated
    metrics = calculator.calculate_comprehensive_risk_metrics(
        np.dot(returns, weights) if len(returns.shape) > 1 else returns
    )

    return metrics.stress_test_loss


if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Generate sample crypto returns data
    np.random.seed(42)
    sample_returns = np.random.normal(0.001, 0.02, 1000)  # 1000 days of returns

    calculator = AdvancedRiskMetrics()

    # Calculate comprehensive risk metrics
    metrics = calculator.calculate_comprehensive_risk_metrics(sample_returns)

    print("Advanced Risk Metrics Results:")
    print(f"Historical VaR 95%: {metrics.var_95_hs:.4f}")
    print(f"Historical VaR 99%: {metrics.var_99_hs:.4f}")
    print(f"Monte Carlo VaR 95%: {metrics.var_95_mc:.4f}")
    print(f"Monte Carlo VaR 99%: {metrics.var_99_mc:.4f}")
    print(f"Max Drawdown: {metrics.max_drawdown:.4f}")
    print(f"Sharpe Ratio: {metrics.sharpe_ratio:.4f}")
    print(f"Volatility (annual): {metrics.volatility:.4f}")
    print(f"Stress Test Loss: {metrics.stress_test_loss:.4f}")

    print("\nScenario Analysis:")
    for scenario, loss in metrics.scenario_analysis.items():
        print(f"  {scenario}: {loss:.4f}")

    # Get dynamic risk limits
    limits = calculator.get_risk_limits(metrics)
    print(f"\nDynamic Risk Limits: {limits}")