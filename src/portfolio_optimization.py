#!/usr/bin/env python3
"""
SovereignForge Portfolio Optimization Engine
Real-time portfolio optimization with Markowitz theory, risk-parity allocation,
and MiCA compliance constraints for arbitrage-enhanced portfolios.
"""

import asyncio
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta
import time
import cvxpy as cp
from scipy.optimize import minimize
import warnings

from risk_management import get_risk_management_engine, RiskManagementEngine
from compliance import get_compliance_engine, MiCAComplianceEngine as ComplianceEngine

logger = logging.getLogger(__name__)

@dataclass
class Asset:
    """Asset with market data and constraints"""
    symbol: str
    name: str
    asset_class: str  # 'crypto', 'stock', 'bond', 'commodity'
    expected_return: float
    volatility: float
    current_price: float
    market_cap: Optional[float] = None
    volume_24h: Optional[float] = None
    is_mica_compliant: bool = True
    max_weight: float = 0.20  # Maximum portfolio weight (20%)
    min_weight: float = 0.0   # Minimum portfolio weight

@dataclass
class PortfolioConstraints:
    """Portfolio optimization constraints"""
    max_weight_per_asset: float = 0.20  # 20% max per asset
    min_weight_per_asset: float = 0.0   # 0% min per asset
    max_crypto_exposure: float = 0.30   # 30% max crypto (MiCA conservative)
    max_single_asset_class: float = 0.50  # 50% max per asset class
    min_diversification: int = 5  # Minimum 5 assets
    max_assets: int = 20  # Maximum 20 assets
    target_return: Optional[float] = None
    max_volatility: float = 0.25  # 25% max volatility
    risk_free_rate: float = 0.02  # 2% risk-free rate

@dataclass
class OptimizationResult:
    """Portfolio optimization result"""
    weights: Dict[str, float]
    expected_return: float
    expected_volatility: float
    sharpe_ratio: float
    diversification_score: float
    risk_score: float
    compliance_score: float
    timestamp: float
    optimization_method: str
    constraints_satisfied: bool
    convergence_status: str

@dataclass
class ArbitrageOpportunity:
    """Arbitrage opportunity for portfolio integration"""
    pair: str
    probability: float
    expected_return: float
    risk_score: float
    time_horizon: int  # seconds
    exchanges: List[str]

class PortfolioOptimizationEngine:
    """Real-time portfolio optimization with arbitrage integration"""

    def __init__(self, initial_capital: float = 10000.0):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital

        # Core components
        self.risk_engine = get_risk_management_engine()
        self.compliance_engine = get_compliance_engine()

        # Portfolio state
        self.assets: Dict[str, Asset] = {}
        self.current_weights: Dict[str, float] = {}
        self.target_weights: Dict[str, float] = {}
        self.constraints = PortfolioConstraints()

        # Optimization history
        self.optimization_history: List[OptimizationResult] = []
        self.rebalance_history: List[Dict[str, Any]] = []

        # Arbitrage integration
        self.arbitrage_opportunities: List[ArbitrageOpportunity] = []
        self.arbitrage_weights: Dict[str, float] = {}

        # Performance tracking
        self.performance_history: List[Dict[str, Any]] = []
        self.last_optimization = 0
        self.optimization_interval = 3600  # 1 hour

        logger.info(f"Portfolio Optimization Engine initialized with ${initial_capital}")

    async def start_engine(self):
        """Start the portfolio optimization engine"""
        logger.info("Starting Portfolio Optimization Engine")

        # Initialize with basic assets
        await self._initialize_universe()

        # Start background optimization
        asyncio.create_task(self._continuous_optimization())

    async def stop_engine(self):
        """Stop the portfolio optimization engine"""
        logger.info("Stopping Portfolio Optimization Engine")

    def add_asset(self, asset: Asset):
        """Add asset to optimization universe"""
        if not asset.is_mica_compliant:
            logger.warning(f"Asset {asset.symbol} is not MiCA compliant - skipping")
            return

        self.assets[asset.symbol] = asset
        logger.info(f"Added asset {asset.symbol} to optimization universe")

    def remove_asset(self, symbol: str):
        """Remove asset from optimization universe"""
        if symbol in self.assets:
            del self.assets[symbol]
            logger.info(f"Removed asset {symbol} from optimization universe")

    def update_asset_data(self, symbol: str, price: float, volume: Optional[float] = None):
        """Update asset market data"""
        if symbol in self.assets:
            self.assets[symbol].current_price = price
            if volume is not None:
                self.assets[symbol].volume_24h = volume

    def add_arbitrage_opportunity(self, opportunity: ArbitrageOpportunity):
        """Add arbitrage opportunity to portfolio consideration"""
        self.arbitrage_opportunities.append(opportunity)

        # Calculate arbitrage allocation
        allocation = self._calculate_arbitrage_allocation(opportunity)
        if allocation > 0:
            self.arbitrage_weights[opportunity.pair] = allocation

        logger.info(f"Added arbitrage opportunity: {opportunity.pair} with {allocation:.2f}% allocation")

    def _calculate_arbitrage_allocation(self, opportunity: ArbitrageOpportunity) -> float:
        """Calculate portfolio allocation for arbitrage opportunity"""
        try:
            # Risk-adjusted allocation based on Kelly criterion
            win_prob = opportunity.probability
            risk_reward_ratio = opportunity.expected_return / max(opportunity.risk_score, 0.01)

            # Conservative Kelly fraction
            kelly_fraction = (win_prob * risk_reward_ratio - (1 - win_prob)) / risk_reward_ratio
            kelly_fraction = max(0, min(kelly_fraction * 0.5, 0.05))  # Cap at 5%

            # Scale by opportunity time horizon and portfolio size
            time_weight = min(opportunity.time_horizon / 3600, 1.0)  # Max 1 hour
            allocation = kelly_fraction * time_weight * 0.10  # Max 10% of portfolio

            return allocation

        except Exception as e:
            logger.error(f"Error calculating arbitrage allocation: {e}")
            return 0.0

    def optimize_portfolio(self, method: str = "markowitz",
                          constraints: Optional[PortfolioConstraints] = None) -> OptimizationResult:
        """Optimize portfolio using specified method"""
        try:
            if len(self.assets) < self.constraints.min_diversification:
                return self._create_error_result("Insufficient assets for optimization")

            # Use provided constraints or defaults
            opt_constraints = constraints or self.constraints

            # Prepare data
            symbols = list(self.assets.keys())
            returns = np.array([self.assets[s].expected_return for s in symbols])
            cov_matrix = self._calculate_covariance_matrix(symbols)

            if method == "markowitz":
                return self._markowitz_optimization(symbols, returns, cov_matrix, opt_constraints)
            elif method == "risk_parity":
                return self._risk_parity_optimization(symbols, returns, cov_matrix, opt_constraints)
            elif method == "min_variance":
                return self._minimum_variance_optimization(symbols, returns, cov_matrix, opt_constraints)
            else:
                return self._create_error_result(f"Unknown optimization method: {method}")

        except Exception as e:
            logger.error(f"Portfolio optimization failed: {e}")
            return self._create_error_result(f"Optimization error: {e}")

    def _markowitz_optimization(self, symbols: List[str], returns: np.ndarray,
                               cov_matrix: np.ndarray, constraints: PortfolioConstraints) -> OptimizationResult:
        """Classic Markowitz mean-variance optimization"""
        try:
            n_assets = len(symbols)

            # Variables
            weights = cp.Variable(n_assets)

            # Objective: Maximize Sharpe ratio (minimize negative Sharpe)
            portfolio_return = returns @ weights
            portfolio_volatility = cp.quad_form(weights, cov_matrix)
            sharpe_ratio = (portfolio_return - constraints.risk_free_rate) / cp.sqrt(portfolio_volatility)

            # Constraints
            constraints_list = [
                cp.sum(weights) == 1,  # Fully invested
                weights >= constraints.min_weight_per_asset,
                weights <= constraints.max_weight_per_asset,
            ]

            # Asset class constraints
            crypto_assets = [i for i, s in enumerate(symbols) if self.assets[s].asset_class == 'crypto']
            if crypto_assets:
                crypto_weight = cp.sum(weights[crypto_assets])
                constraints_list.append(crypto_weight <= constraints.max_crypto_exposure)

            # Target return constraint (if specified)
            if constraints.target_return is not None:
                constraints_list.append(portfolio_return >= constraints.target_return)

            # Volatility constraint
            constraints_list.append(portfolio_volatility <= constraints.max_volatility ** 2)

            # Solve optimization
            problem = cp.Problem(cp.Maximize(sharpe_ratio), constraints_list)
            problem.solve(solver=cp.ECOS, verbose=False)

            if problem.status not in ["optimal", "optimal_inaccurate"]:
                return self._create_error_result(f"Optimization failed: {problem.status}")

            # Extract results
            optimal_weights = weights.value
            weights_dict = dict(zip(symbols, optimal_weights))

            expected_return = float(returns @ optimal_weights)
            expected_volatility = float(np.sqrt(optimal_weights @ cov_matrix @ optimal_weights))
            sharpe = (expected_return - constraints.risk_free_rate) / expected_volatility

            return OptimizationResult(
                weights=weights_dict,
                expected_return=expected_return,
                expected_volatility=expected_volatility,
                sharpe_ratio=sharpe,
                diversification_score=self._calculate_diversification_score(optimal_weights),
                risk_score=self._calculate_risk_score(optimal_weights, cov_matrix),
                compliance_score=self._calculate_compliance_score(weights_dict),
                timestamp=time.time(),
                optimization_method="markowitz",
                constraints_satisfied=True,
                convergence_status="optimal"
            )

        except Exception as e:
            logger.error(f"Markowitz optimization failed: {e}")
            return self._create_error_result(f"Markowitz optimization error: {e}")

    def _risk_parity_optimization(self, symbols: List[str], returns: np.ndarray,
                                 cov_matrix: np.ndarray, constraints: PortfolioConstraints) -> OptimizationResult:
        """Risk parity optimization - equal risk contribution"""
        try:
            n_assets = len(symbols)

            def risk_parity_objective(weights):
                """Objective function for risk parity"""
                portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)
                marginal_risks = (cov_matrix @ weights) / portfolio_vol
                risk_contributions = weights * marginal_risks

                # Target equal risk contribution
                target_contribution = 1.0 / n_assets
                return np.sum((risk_contributions - target_contribution) ** 2)

            # Constraints for scipy minimize
            def constraint_sum_weights(x):
                return np.sum(x) - 1.0

            def constraint_bounds(x):
                return np.array([
                    x - constraints.min_weight_per_asset,  # x >= min_weight
                    constraints.max_weight_per_asset - x   # x <= max_weight
                ])

            # Initial guess: equal weights
            x0 = np.ones(n_assets) / n_assets

            # Bounds
            bounds = [(constraints.min_weight_per_asset, constraints.max_weight_per_asset)] * n_assets

            # Constraints
            scipy_constraints = [
                {'type': 'eq', 'fun': constraint_sum_weights}
            ]

            # Optimize
            result = minimize(
                risk_parity_objective,
                x0,
                method='SLSQP',
                bounds=bounds,
                constraints=scipy_constraints,
                options={'maxiter': 1000, 'ftol': 1e-9}
            )

            if not result.success:
                return self._create_error_result(f"Risk parity optimization failed: {result.message}")

            optimal_weights = result.x
            weights_dict = dict(zip(symbols, optimal_weights))

            expected_return = float(returns @ optimal_weights)
            expected_volatility = float(np.sqrt(optimal_weights @ cov_matrix @ optimal_weights))
            sharpe = (expected_return - constraints.risk_free_rate) / expected_volatility

            return OptimizationResult(
                weights=weights_dict,
                expected_return=expected_return,
                expected_volatility=expected_volatility,
                sharpe_ratio=sharpe,
                diversification_score=self._calculate_diversification_score(optimal_weights),
                risk_score=self._calculate_risk_score(optimal_weights, cov_matrix),
                compliance_score=self._calculate_compliance_score(weights_dict),
                timestamp=time.time(),
                optimization_method="risk_parity",
                constraints_satisfied=True,
                convergence_status="optimal"
            )

        except Exception as e:
            logger.error(f"Risk parity optimization failed: {e}")
            return self._create_error_result(f"Risk parity optimization error: {e}")

    def _minimum_variance_optimization(self, symbols: List[str], returns: np.ndarray,
                                     cov_matrix: np.ndarray, constraints: PortfolioConstraints) -> OptimizationResult:
        """Minimum variance portfolio optimization"""
        try:
            n_assets = len(symbols)

            # Variables
            weights = cp.Variable(n_assets)

            # Objective: Minimize portfolio variance
            portfolio_volatility = cp.quad_form(weights, cov_matrix)

            # Constraints
            constraints_list = [
                cp.sum(weights) == 1,  # Fully invested
                weights >= constraints.min_weight_per_asset,
                weights <= constraints.max_weight_per_asset,
            ]

            # Asset class constraints
            crypto_assets = [i for i, s in enumerate(symbols) if self.assets[s].asset_class == 'crypto']
            if crypto_assets:
                crypto_weight = cp.sum(weights[crypto_assets])
                constraints_list.append(crypto_weight <= constraints.max_crypto_exposure)

            # Solve optimization
            problem = cp.Problem(cp.Minimize(portfolio_volatility), constraints_list)
            problem.solve(solver=cp.ECOS, verbose=False)

            if problem.status not in ["optimal", "optimal_inaccurate"]:
                return self._create_error_result(f"Min variance optimization failed: {problem.status}")

            # Extract results
            optimal_weights = weights.value
            weights_dict = dict(zip(symbols, optimal_weights))

            expected_return = float(returns @ optimal_weights)
            expected_volatility = float(np.sqrt(optimal_weights @ cov_matrix @ optimal_weights))
            sharpe = (expected_return - constraints.risk_free_rate) / expected_volatility

            return OptimizationResult(
                weights=weights_dict,
                expected_return=expected_return,
                expected_volatility=expected_volatility,
                sharpe_ratio=sharpe,
                diversification_score=self._calculate_diversification_score(optimal_weights),
                risk_score=self._calculate_risk_score(optimal_weights, cov_matrix),
                compliance_score=self._calculate_compliance_score(weights_dict),
                timestamp=time.time(),
                optimization_method="min_variance",
                constraints_satisfied=True,
                convergence_status="optimal"
            )

        except Exception as e:
            logger.error(f"Minimum variance optimization failed: {e}")
            return self._create_error_result(f"Min variance optimization error: {e}")

    def _calculate_covariance_matrix(self, symbols: List[str]) -> np.ndarray:
        """Calculate covariance matrix from asset data"""
        try:
            n_assets = len(symbols)
            cov_matrix = np.zeros((n_assets, n_assets))

            # Simplified covariance calculation
            # In production, this would use historical price data
            for i, symbol1 in enumerate(symbols):
                asset1 = self.assets[symbol1]
                cov_matrix[i, i] = asset1.volatility ** 2  # Variance

                for j, symbol2 in enumerate(symbols):
                    if i != j:
                        asset2 = self.assets[symbol2]
                        # Simplified correlation assumption
                        correlation = 0.3 if asset1.asset_class == asset2.asset_class else 0.1
                        cov_matrix[i, j] = correlation * asset1.volatility * asset2.volatility
                        cov_matrix[j, i] = cov_matrix[i, j]

            return cov_matrix

        except Exception as e:
            logger.error(f"Error calculating covariance matrix: {e}")
            return np.eye(len(symbols)) * 0.1  # Fallback diagonal matrix

    def _calculate_diversification_score(self, weights: np.ndarray) -> float:
        """Calculate portfolio diversification score (0-1)"""
        try:
            # Herfindahl-Hirschman Index (inverse)
            hhi = np.sum(weights ** 2)
            diversification = 1.0 - hhi

            # Effective number of assets
            effective_n = 1.0 / hhi

            # Normalize to 0-1 scale
            max_diversification = min(len(weights), 10)  # Cap at 10 assets
            return min(effective_n / max_diversification, 1.0)

        except Exception:
            return 0.0

    def _calculate_risk_score(self, weights: np.ndarray, cov_matrix: np.ndarray) -> float:
        """Calculate portfolio risk score (0-1, higher = riskier)"""
        try:
            portfolio_vol = np.sqrt(weights @ cov_matrix @ weights)

            # Risk factors
            vol_risk = min(portfolio_vol / 0.3, 1.0)  # Normalize to 30% vol
            concentration_risk = np.sum(weights ** 2)  # HHI

            return (vol_risk + concentration_risk) / 2.0

        except Exception:
            return 1.0

    def _calculate_compliance_score(self, weights: Dict[str, float]) -> float:
        """Calculate compliance score (0-1, higher = more compliant)"""
        try:
            compliant_weight = 0.0
            total_weight = 0.0

            for symbol, weight in weights.items():
                if symbol in self.assets and self.assets[symbol].is_mica_compliant:
                    compliant_weight += weight
                total_weight += weight

            return compliant_weight / total_weight if total_weight > 0 else 0.0

        except Exception:
            return 0.0

    def _create_error_result(self, message: str) -> OptimizationResult:
        """Create error optimization result"""
        return OptimizationResult(
            weights={},
            expected_return=0.0,
            expected_volatility=0.0,
            sharpe_ratio=0.0,
            diversification_score=0.0,
            risk_score=1.0,
            compliance_score=0.0,
            timestamp=time.time(),
            optimization_method="error",
            constraints_satisfied=False,
            convergence_status=message
        )

    async def _initialize_universe(self):
        """Initialize asset universe with basic assets"""
        # Add major cryptocurrencies (MiCA compliant)
        mica_assets = [
            ("BTC", "Bitcoin", "crypto", 0.08, 0.45, 45000.0),
            ("ETH", "Ethereum", "crypto", 0.12, 0.55, 2800.0),
            ("XRP", "Ripple", "crypto", 0.06, 0.40, 0.55),
            ("ADA", "Cardano", "crypto", 0.10, 0.50, 0.45),
            ("SOL", "Solana", "crypto", 0.15, 0.70, 95.0),
            ("DOT", "Polkadot", "crypto", 0.09, 0.60, 7.20),
            ("LINK", "Chainlink", "crypto", 0.11, 0.65, 14.50),
        ]

        for symbol, name, asset_class, exp_return, vol, price in mica_assets:
            asset = Asset(
                symbol=symbol,
                name=name,
                asset_class=asset_class,
                expected_return=exp_return,
                volatility=vol,
                current_price=price,
                is_mica_compliant=True
            )
            self.add_asset(asset)

        logger.info(f"Initialized asset universe with {len(self.assets)} assets")

    async def _continuous_optimization(self):
        """Continuous portfolio optimization loop"""
        while True:
            try:
                current_time = time.time()

                # Check if optimization is due
                if current_time - self.last_optimization >= self.optimization_interval:
                    await self._run_optimization_cycle()
                    self.last_optimization = current_time

                # Check for rebalancing needs
                await self._check_rebalance_needed()

                await asyncio.sleep(300)  # Check every 5 minutes

            except Exception as e:
                logger.error(f"Error in continuous optimization: {e}")
                await asyncio.sleep(300)

    async def _run_optimization_cycle(self):
        """Run complete optimization cycle"""
        try:
            # Run multiple optimization methods
            methods = ["markowitz", "risk_parity", "min_variance"]
            results = []

            for method in methods:
                result = self.optimize_portfolio(method=method)
                if result.constraints_satisfied:
                    results.append(result)

            if results:
                # Select best result (highest Sharpe ratio)
                best_result = max(results, key=lambda x: x.sharpe_ratio)
                self.target_weights = best_result.weights
                self.optimization_history.append(best_result)

                logger.info(f"Optimization completed: {best_result.optimization_method}, "
                          f"Sharpe: {best_result.sharpe_ratio:.2f}, "
                          f"Return: {best_result.expected_return:.1%}")

        except Exception as e:
            logger.error(f"Optimization cycle failed: {e}")

    async def _check_rebalance_needed(self):
        """Check if portfolio rebalancing is needed"""
        try:
            if not self.current_weights or not self.target_weights:
                return

            # Calculate drift
            total_drift = 0.0
            for symbol in set(self.current_weights.keys()) | set(self.target_weights.keys()):
                current = self.current_weights.get(symbol, 0.0)
                target = self.target_weights.get(symbol, 0.0)
                total_drift += abs(current - target)

            # Rebalance threshold (5% total drift)
            if total_drift > 0.05:
                await self._execute_rebalance()
                logger.info(f"Rebalance executed: {total_drift:.1%} drift corrected")

        except Exception as e:
            logger.error(f"Rebalance check failed: {e}")

    async def _execute_rebalance(self):
        """Execute portfolio rebalancing"""
        try:
            # Calculate trades needed
            trades = {}
            for symbol in set(self.current_weights.keys()) | set(self.target_weights.keys()):
                current = self.current_weights.get(symbol, 0.0)
                target = self.target_weights.get(symbol, 0.0)
                trade_size = target - current

                if abs(trade_size) > 0.01:  # Minimum 1% change
                    trades[symbol] = trade_size

            # Record rebalance
            rebalance_record = {
                'timestamp': time.time(),
                'old_weights': self.current_weights.copy(),
                'new_weights': self.target_weights.copy(),
                'trades': trades,
                'reason': 'drift_correction'
            }

            self.rebalance_history.append(rebalance_record)
            self.current_weights = self.target_weights.copy()

        except Exception as e:
            logger.error(f"Rebalance execution failed: {e}")

    def get_portfolio_status(self) -> Dict[str, Any]:
        """Get current portfolio status"""
        return {
            'current_weights': self.current_weights,
            'target_weights': self.target_weights,
            'total_assets': len(self.assets),
            'arbitrage_opportunities': len(self.arbitrage_opportunities),
            'last_optimization': self.last_optimization,
            'performance_metrics': self._calculate_performance_metrics(),
            'risk_metrics': self.risk_engine.get_risk_report() if self.risk_engine else {}
        }

    def _calculate_performance_metrics(self) -> Dict[str, Any]:
        """Calculate portfolio performance metrics"""
        try:
            if not self.optimization_history:
                return {}

            latest = self.optimization_history[-1]

            return {
                'sharpe_ratio': latest.sharpe_ratio,
                'expected_return': latest.expected_return,
                'expected_volatility': latest.expected_volatility,
                'diversification_score': latest.diversification_score,
                'risk_score': latest.risk_score,
                'compliance_score': latest.compliance_score,
                'optimization_method': latest.optimization_method
            }

        except Exception:
            return {}

# Global portfolio engine instance
_portfolio_engine = None

def get_portfolio_optimization_engine() -> PortfolioOptimizationEngine:
    """Get global portfolio optimization engine instance"""
    global _portfolio_engine
    if _portfolio_engine is None:
        _portfolio_engine = PortfolioOptimizationEngine()
    return _portfolio_engine

async def initialize_portfolio_optimization():
    """Initialize the global portfolio optimization system"""
    engine = get_portfolio_optimization_engine()
    await engine.start_engine()
    return engine

async def shutdown_portfolio_optimization():
    """Shutdown the global portfolio optimization system"""
    engine = get_portfolio_optimization_engine()
    await engine.stop_engine()

# Convenience functions
def optimize_portfolio(method: str = "markowitz") -> OptimizationResult:
    """Optimize portfolio using specified method"""
    engine = get_portfolio_optimization_engine()
    return engine.optimize_portfolio(method=method)

def get_portfolio_status() -> Dict[str, Any]:
    """Get current portfolio status"""
    engine = get_portfolio_optimization_engine()
    return engine.get_portfolio_status()