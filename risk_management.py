#!/usr/bin/env python3
"""
Risk Management System for SovereignForge
Implements position sizing, portfolio optimization, and risk controls
"""

import numpy as np
import pandas as pd
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass
from datetime import datetime, timedelta
import math
from scipy.optimize import minimize

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Trading position container"""
    symbol: str
    side: str  # 'buy' or 'sell'
    quantity: float
    entry_price: float
    current_price: float
    timestamp: datetime
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None

@dataclass
class RiskMetrics:
    """Risk metrics container"""
    total_portfolio_value: float
    total_risk: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    value_at_risk: float  # 95% VaR
    expected_shortfall: float  # 95% ES
    volatility: float

@dataclass
class PositionSizingResult:
    """Position sizing calculation result"""
    symbol: str
    recommended_quantity: float
    risk_amount: float
    confidence_level: float
    kelly_fraction: float

class RiskManager:
    """Comprehensive risk management system"""

    def __init__(self,
                 max_portfolio_risk: float = 0.02,  # 2% max risk per trade
                 max_total_risk: float = 0.10,      # 10% max total portfolio risk
                 risk_free_rate: float = 0.02,      # 2% risk-free rate
                 confidence_level: float = 0.95):   # 95% confidence for VaR

        self.max_portfolio_risk = max_portfolio_risk
        self.max_total_risk = max_total_risk
        self.risk_free_rate = risk_free_rate
        self.confidence_level = confidence_level

        self.positions: Dict[str, Position] = {}
        self.portfolio_history: List[Dict[str, Any]] = []
        self.risk_limits: Dict[str, float] = {}

        # Initialize risk limits for supported pairs
        self._initialize_risk_limits()

    def _initialize_risk_limits(self):
        """Initialize risk limits for trading pairs"""
        # Conservative limits based on pair volatility
        self.risk_limits = {
            'btc_usdt': 0.015,  # 1.5% max risk per BTC trade
            'eth_usdt': 0.020,  # 2.0% max risk per ETH trade
            'xrp_usdt': 0.030,  # 3.0% max risk per XRP trade
            'xlm_usdt': 0.030,  # 3.0% max risk per XLM trade
            'hbar_usdt': 0.035, # 3.5% max risk per HBAR trade
            'algo_usdt': 0.035, # 3.5% max risk per ALGO trade
            'ada_usdt': 0.025,  # 2.5% max risk per ADA trade
        }

    def calculate_kelly_criterion(self,
                                 win_probability: float,
                                 win_loss_ratio: float,
                                 current_portfolio: float) -> float:
        """Calculate Kelly Criterion for position sizing"""
        try:
            if win_probability <= 0 or win_probability >= 1:
                return 0.0

            # Kelly formula: f = (bp - q) / b
            # where: b = odds (win_loss_ratio), p = win probability, q = loss probability
            b = win_loss_ratio
            p = win_probability
            q = 1 - p

            kelly_fraction = (b * p - q) / b

            # Apply half-Kelly for safety
            kelly_fraction *= 0.5

            # Ensure reasonable bounds
            kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # Max 25% of portfolio

            return kelly_fraction

        except Exception as e:
            logger.error(f"Kelly calculation failed: {e}")
            return 0.0

    def calculate_position_size(self,
                              symbol: str,
                              entry_price: float,
                              stop_loss_price: float,
                              portfolio_value: float,
                              win_probability: float = 0.55,
                              win_loss_ratio: float = 2.0) -> PositionSizingResult:
        """Calculate optimal position size using Kelly Criterion and risk limits"""

        try:
            # Calculate risk per share
            risk_per_unit = abs(entry_price - stop_loss_price)

            if risk_per_unit <= 0:
                logger.error("Invalid stop loss price")
                return PositionSizingResult(symbol, 0, 0, 0, 0)

            # Get risk limit for this symbol
            max_risk_pct = self.risk_limits.get(symbol, self.max_portfolio_risk)

            # Calculate maximum risk amount
            max_risk_amount = portfolio_value * max_risk_pct

            # Calculate Kelly fraction
            kelly_fraction = self.calculate_kelly_criterion(win_probability, win_loss_ratio, portfolio_value)

            # Calculate position size based on Kelly
            kelly_risk_amount = portfolio_value * kelly_fraction

            # Use the more conservative of Kelly and max risk limit
            risk_amount = min(kelly_risk_amount, max_risk_amount)

            # Calculate quantity
            quantity = risk_amount / risk_per_unit

            # Ensure minimum order sizes (approximate)
            min_order_sizes = {
                'btc_usdt': 0.0001,
                'eth_usdt': 0.001,
                'xrp_usdt': 1.0,
                'xlm_usdt': 1.0,
                'hbar_usdt': 1.0,
                'algo_usdt': 1.0,
                'ada_usdt': 1.0,
            }

            min_quantity = min_order_sizes.get(symbol, 0.001)
            quantity = max(quantity, min_quantity)

            # Calculate confidence level based on risk parameters
            confidence_level = min(win_probability * 100, 95.0)

            return PositionSizingResult(
                symbol=symbol,
                recommended_quantity=quantity,
                risk_amount=risk_amount,
                confidence_level=confidence_level,
                kelly_fraction=kelly_fraction
            )

        except Exception as e:
            logger.error(f"Position sizing calculation failed: {e}")
            return PositionSizingResult(symbol, 0, 0, 0, 0)

    def calculate_portfolio_risk(self, positions: Dict[str, Position]) -> RiskMetrics:
        """Calculate comprehensive portfolio risk metrics"""

        try:
            if not positions:
                return RiskMetrics(0, 0, 0, 0, 0, 0, 0, 0)

            # Calculate current portfolio value
            total_value = sum(pos.current_price * pos.quantity for pos in positions.values())

            # Calculate returns history (simplified - would need real price history)
            # For now, use placeholder calculations
            returns = np.random.normal(0.001, 0.02, 252)  # 252 trading days

            # Calculate Sharpe ratio
            excess_returns = returns - self.risk_free_rate / 252
            sharpe_ratio = np.mean(excess_returns) / np.std(excess_returns) * np.sqrt(252)

            # Calculate Sortino ratio (downside deviation)
            downside_returns = returns[returns < 0]
            sortino_ratio = np.mean(excess_returns) / np.std(downside_returns) * np.sqrt(252)

            # Calculate maximum drawdown
            cumulative = np.cumprod(1 + returns)
            running_max = np.maximum.accumulate(cumulative)
            drawdown = (cumulative - running_max) / running_max
            max_drawdown = abs(np.min(drawdown))

            # Calculate VaR (95% confidence)
            value_at_risk = np.percentile(returns, (1 - self.confidence_level) * 100)

            # Calculate Expected Shortfall (CVaR)
            tail_losses = returns[returns <= value_at_risk]
            expected_shortfall = np.mean(tail_losses) if len(tail_losses) > 0 else value_at_risk

            # Calculate volatility (annualized)
            volatility = np.std(returns) * np.sqrt(252)

            # Calculate total risk (simplified)
            total_risk = sum(pos.quantity * pos.entry_price * 0.02 for pos in positions.values())  # 2% risk per position

            return RiskMetrics(
                total_portfolio_value=total_value,
                total_risk=total_risk,
                sharpe_ratio=sharpe_ratio,
                sortino_ratio=sortino_ratio,
                max_drawdown=max_drawdown,
                value_at_risk=value_at_risk,
                expected_shortfall=expected_shortfall,
                volatility=volatility
            )

        except Exception as e:
            logger.error(f"Portfolio risk calculation failed: {e}")
            return RiskMetrics(0, 0, 0, 0, 0, 0, 0, 0)

    def check_risk_limits(self, positions: Dict[str, Position], new_position: Optional[Position] = None) -> bool:
        """Check if current positions are within risk limits"""

        try:
            all_positions = positions.copy()
            if new_position:
                all_positions[new_position.symbol] = new_position

            # Calculate current risk metrics
            risk_metrics = self.calculate_portfolio_risk(all_positions)

            # Check total portfolio risk
            if risk_metrics.total_risk > self.max_total_risk * risk_metrics.total_portfolio_value:
                logger.warning(f"Total portfolio risk limit exceeded: {risk_metrics.total_risk}")
                return False

            # Check individual position concentrations
            for symbol, position in all_positions.items():
                position_value = position.current_price * position.quantity
                if position_value > risk_metrics.total_portfolio_value * 0.25:  # Max 25% in single position
                    logger.warning(f"Position concentration limit exceeded for {symbol}")
                    return False

            return True

        except Exception as e:
            logger.error(f"Risk limit check failed: {e}")
            return False

    def optimize_portfolio(self,
                          symbols: List[str],
                          expected_returns: Dict[str, float],
                          covariance_matrix: pd.DataFrame,
                          target_return: Optional[float] = None) -> Dict[str, float]:
        """Optimize portfolio weights using Modern Portfolio Theory"""

        try:
            n_assets = len(symbols)

            # Objective function: minimize portfolio variance
            def portfolio_variance(weights):
                return np.dot(weights.T, np.dot(covariance_matrix.values, weights))

            # Constraints
            constraints = [
                {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},  # Weights sum to 1
            ]

            # Add target return constraint if specified
            if target_return is not None:
                expected_returns_array = np.array([expected_returns[s] for s in symbols])
                constraints.append({
                    'type': 'eq',
                    'fun': lambda x: np.dot(expected_returns_array, x) - target_return
                })

            # Bounds: 0 to 1 for each weight (no short selling)
            bounds = tuple((0, 1) for _ in range(n_assets))

            # Initial guess: equal weights
            initial_weights = np.array([1/n_assets] * n_assets)

            # Optimize
            result = minimize(
                portfolio_variance,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints=constraints
            )

            if result.success:
                optimal_weights = result.x
                return dict(zip(symbols, optimal_weights))
            else:
                logger.error(f"Portfolio optimization failed: {result.message}")
                # Return equal weights as fallback
                equal_weight = 1.0 / n_assets
                return {symbol: equal_weight for symbol in symbols}

        except Exception as e:
            logger.error(f"Portfolio optimization failed: {e}")
            # Return equal weights as fallback
            equal_weight = 1.0 / len(symbols)
            return {symbol: equal_weight for symbol in symbols}

    def update_position(self, symbol: str, current_price: float):
        """Update position with current price"""
        if symbol in self.positions:
            self.positions[symbol].current_price = current_price

            # Check stop loss
            position = self.positions[symbol]
            if position.stop_loss and current_price <= position.stop_loss:
                logger.warning(f"Stop loss triggered for {symbol} at {current_price}")
                # Would trigger position closure here

            # Check take profit
            if position.take_profit and current_price >= position.take_profit:
                logger.info(f"Take profit triggered for {symbol} at {current_price}")
                # Would trigger position closure here

    def add_position(self, position: Position) -> bool:
        """Add a new position with risk checks"""
        if not self.check_risk_limits(self.positions, position):
            logger.error("Risk limits would be exceeded by new position")
            return False

        self.positions[position.symbol] = position
        logger.info(f"Position added: {position.symbol} {position.side} {position.quantity}")
        return True

    def remove_position(self, symbol: str):
        """Remove a position"""
        if symbol in self.positions:
            del self.positions[symbol]
            logger.info(f"Position removed: {symbol}")

    def get_portfolio_summary(self) -> Dict[str, Any]:
        """Get comprehensive portfolio summary"""
        try:
            risk_metrics = self.calculate_portfolio_risk(self.positions)

            return {
                'positions': {
                    symbol: {
                        'side': pos.side,
                        'quantity': pos.quantity,
                        'entry_price': pos.entry_price,
                        'current_price': pos.current_price,
                        'pnl': (pos.current_price - pos.entry_price) * pos.quantity,
                        'pnl_pct': ((pos.current_price - pos.entry_price) / pos.entry_price) * 100
                    }
                    for symbol, pos in self.positions.items()
                },
                'risk_metrics': {
                    'total_portfolio_value': risk_metrics.total_portfolio_value,
                    'total_risk': risk_metrics.total_risk,
                    'sharpe_ratio': risk_metrics.sharpe_ratio,
                    'sortino_ratio': risk_metrics.sortino_ratio,
                    'max_drawdown': risk_metrics.max_drawdown,
                    'value_at_risk_95': risk_metrics.value_at_risk,
                    'expected_shortfall_95': risk_metrics.expected_shortfall,
                    'volatility': risk_metrics.volatility
                },
                'risk_limits': {
                    'max_portfolio_risk_pct': self.max_portfolio_risk,
                    'max_total_risk_pct': self.max_total_risk,
                    'symbol_limits': self.risk_limits
                }
            }

        except Exception as e:
            logger.error(f"Portfolio summary generation failed: {e}")
            return {}

# Global risk manager instance
_risk_manager = None

def get_risk_manager() -> RiskManager:
    """Get or create risk manager instance"""
    global _risk_manager

    if _risk_manager is None:
        _risk_manager = RiskManager()

    return _risk_manager