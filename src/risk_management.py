#!/usr/bin/env python3
"""
SovereignForge - Risk Management System
Position sizing, stop-loss, and portfolio risk controls for MiCA compliance
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
import math

logger = logging.getLogger(__name__)

@dataclass
class Position:
    """Represents a trading position"""
    pair: str
    exchange: str
    side: str  # 'buy' or 'sell'
    size: float
    entry_price: float
    current_price: float
    stop_loss: float
    take_profit: float
    timestamp: datetime
    unrealized_pnl: float = 0.0

@dataclass
class RiskLimits:
    """Risk management limits"""
    max_position_size_pct: float = 0.02  # 2% of portfolio per position
    max_portfolio_risk_pct: float = 0.05  # 5% max portfolio risk
    max_single_pair_exposure_pct: float = 0.10  # 10% max per pair
    max_daily_loss_pct: float = 0.03  # 3% max daily loss
    max_open_positions: int = 5
    min_liquidity_ratio: float = 2.0  # Minimum bid/ask liquidity ratio

class RiskManager:
    """
    Comprehensive risk management for arbitrage trading
    """

    def __init__(self, initial_capital: float = 10000.0, risk_limits: Optional[RiskLimits] = None):
        self.initial_capital = initial_capital
        self.current_capital = initial_capital
        self.risk_limits = risk_limits or RiskLimits()

        # Portfolio tracking
        self.positions: Dict[str, Position] = {}
        self.daily_pnl = 0.0
        self.daily_start_capital = initial_capital

        # Risk metrics
        self.portfolio_value = initial_capital
        self.total_exposure = 0.0
        self.max_drawdown = 0.0
        self.sharpe_ratio = 0.0

        # Trading history
        self.trade_history: List[Dict[str, Any]] = []

        logger.info(f"RiskManager initialized with ${initial_capital} capital")

    def validate_opportunity(self, opportunity: Dict[str, Any]) -> bool:
        """
        Validate arbitrage opportunity against risk limits
        """
        try:
            pair = opportunity.get('pair', '')
            exchanges = opportunity.get('exchanges', [])
            prices = opportunity.get('prices', {})
            spread = opportunity.get('spread_prediction', 0)

            # Check if we already have position in this pair
            if pair in self.positions:
                logger.warning(f"Position already exists for {pair}")
                return False

            # Check maximum open positions
            if len(self.positions) >= self.risk_limits.max_open_positions:
                logger.warning(f"Maximum open positions ({self.risk_limits.max_open_positions}) reached")
                return False

            # Check pair exposure limit
            pair_exposure = sum(pos.size * pos.entry_price for pos in self.positions.values() if pos.pair == pair)
            pair_exposure_pct = pair_exposure / self.portfolio_value
            if pair_exposure_pct >= self.risk_limits.max_single_pair_exposure_pct:
                logger.warning(f"Pair exposure limit ({self.risk_limits.max_single_pair_exposure_pct*100}%) exceeded for {pair}")
                return False

            # Check liquidity requirements
            if not self._check_liquidity_requirements(prices):
                logger.warning(f"Liquidity requirements not met for {pair}")
                return False

            # Check spread requirements (minimum profitable spread)
            if spread < 0.001:  # 0.1% minimum spread
                logger.warning(f"Spread too low for profitable arbitrage: {spread}")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating opportunity: {e}")
            return False

    def calculate_position_size(self, opportunity: Dict[str, Any]) -> float:
        """
        Calculate optimal position size based on risk limits
        """
        try:
            spread = opportunity.get('spread_prediction', 0)
            prices = opportunity.get('prices', {})
            risk_score = opportunity.get('risk_score', 0.5)

            if not prices:
                return 0.0

            # Use average price for position sizing
            avg_price = sum(prices.values()) / len(prices)

            # Base position size on risk limits
            max_position_value = self.portfolio_value * self.risk_limits.max_position_size_pct

            # Adjust for risk score (higher risk = smaller position)
            risk_adjustment = 1.0 - (risk_score * 0.5)  # Reduce size by up to 50% for high risk
            adjusted_position_value = max_position_value * risk_adjustment

            # Calculate position size in base currency
            position_size = adjusted_position_value / avg_price

            # Apply minimum position constraints (0.001 BTC equivalent minimum)
            min_position_value = 0.001 * avg_price
            if adjusted_position_value < min_position_value:
                logger.warning(f"Position size too small: ${adjusted_position_value}")
                return 0.0

            # Check portfolio risk limits
            if not self._check_portfolio_risk_limits(position_size * avg_price):
                return 0.0

            return position_size

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.0

    def open_position(self, opportunity: Dict[str, Any]) -> Optional[Position]:
        """
        Open a new arbitrage position
        """
        try:
            if not self.validate_opportunity(opportunity):
                return None

            pair = opportunity.get('pair', '')
            exchanges = opportunity.get('exchanges', [])
            prices = opportunity.get('prices', {})

            if not pair or not exchanges or not prices:
                return None

            # Calculate position size
            position_size = self.calculate_position_size(opportunity)
            if position_size <= 0:
                return None

            # Use first exchange and price for simplicity
            exchange = exchanges[0]
            entry_price = prices[exchange]

            # Calculate stop loss and take profit
            spread = opportunity.get('spread_prediction', 0.002)
            stop_loss = entry_price * (1.0 - spread * 2)  # 2x spread as stop loss
            take_profit = entry_price * (1.0 + spread * 0.8)  # 80% of spread as profit target

            # Create position
            position = Position(
                pair=pair,
                exchange=exchange,
                side='buy',  # Arbitrage typically starts with buy
                size=position_size,
                entry_price=entry_price,
                current_price=entry_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                timestamp=datetime.now()
            )

            # Add to portfolio
            self.positions[pair] = position
            self.total_exposure += position_size * entry_price

            logger.info(f"Opened position: {pair} {position_size:.6f} @ ${entry_price:.2f}")
            return position

        except Exception as e:
            logger.error(f"Error opening position: {e}")
            return None

    def close_position(self, pair: str, exit_price: float, reason: str = "manual") -> bool:
        """
        Close an existing position
        """
        try:
            if pair not in self.positions:
                logger.warning(f"No position found for {pair}")
                return False

            position = self.positions[pair]

            # Calculate P&L
            if position.side == 'buy':
                pnl = (exit_price - position.entry_price) * position.size
            else:
                pnl = (position.entry_price - exit_price) * position.size

            # Update capital and metrics
            self.current_capital += pnl
            self.daily_pnl += pnl
            self.total_exposure -= position.size * position.entry_price

            # Record trade
            trade_record = {
                'pair': pair,
                'side': position.side,
                'entry_price': position.entry_price,
                'exit_price': exit_price,
                'size': position.size,
                'pnl': pnl,
                'reason': reason,
                'timestamp': datetime.now()
            }
            self.trade_history.append(trade_record)

            # Remove position
            del self.positions[pair]

            logger.info(f"Closed position: {pair} P&L: ${pnl:.2f} ({reason})")
            return True

        except Exception as e:
            logger.error(f"Error closing position: {e}")
            return False

    def check_stop_losses(self, current_prices: Dict[str, float]) -> List[str]:
        """
        Check and execute stop losses for all positions
        """
        positions_to_close = []

        try:
            for pair, position in self.positions.items():
                if pair in current_prices:
                    current_price = current_prices[pair]
                    position.current_price = current_price

                    # Calculate unrealized P&L
                    if position.side == 'buy':
                        position.unrealized_pnl = (current_price - position.entry_price) * position.size
                    else:
                        position.unrealized_pnl = (position.entry_price - current_price) * position.size

                    # Check stop loss
                    if current_price <= position.stop_loss:
                        positions_to_close.append((pair, current_price, "stop_loss"))

                    # Check take profit
                    elif current_price >= position.take_profit:
                        positions_to_close.append((pair, current_price, "take_profit"))

            # Execute closures
            closed_pairs = []
            for pair, exit_price, reason in positions_to_close:
                if self.close_position(pair, exit_price, reason):
                    closed_pairs.append(pair)

            return closed_pairs

        except Exception as e:
            logger.error(f"Error checking stop losses: {e}")
            return []

    def get_portfolio_status(self) -> Dict[str, Any]:
        """
        Get current portfolio status and risk metrics
        """
        try:
            # Calculate current portfolio value
            portfolio_value = self.current_capital
            for position in self.positions.values():
                portfolio_value += position.unrealized_pnl

            # Calculate risk metrics
            total_exposure_pct = self.total_exposure / portfolio_value if portfolio_value > 0 else 0
            daily_pnl_pct = self.daily_pnl / self.daily_start_capital if self.daily_start_capital > 0 else 0

            # Check risk limit violations
            risk_violations = []
            if total_exposure_pct > self.risk_limits.max_portfolio_risk_pct:
                risk_violations.append(f"Portfolio exposure ({total_exposure_pct:.1%}) exceeds limit ({self.risk_limits.max_portfolio_risk_pct:.1%})")

            if abs(daily_pnl_pct) > self.risk_limits.max_daily_loss_pct:
                risk_violations.append(f"Daily P&L ({daily_pnl_pct:.1%}) exceeds limit ({self.risk_limits.max_daily_loss_pct:.1%})")

            return {
                'portfolio_value': portfolio_value,
                'current_capital': self.current_capital,
                'total_exposure': self.total_exposure,
                'exposure_pct': total_exposure_pct,
                'daily_pnl': self.daily_pnl,
                'daily_pnl_pct': daily_pnl_pct,
                'open_positions': len(self.positions),
                'positions': list(self.positions.keys()),
                'risk_violations': risk_violations,
                'max_drawdown': self.max_drawdown,
                'sharpe_ratio': self.sharpe_ratio
            }

        except Exception as e:
            logger.error(f"Error getting portfolio status: {e}")
            return {}

    def _check_liquidity_requirements(self, prices: Dict[str, float]) -> bool:
        """
        Check if liquidity requirements are met
        """
        try:
            if len(prices) < 2:
                return False

            # Calculate bid/ask spread ratio (simplified)
            price_values = list(prices.values())
            avg_price = sum(price_values) / len(price_values)
            price_spread = max(price_values) - min(price_values)
            spread_ratio = price_spread / avg_price

            return spread_ratio <= (1.0 / self.risk_limits.min_liquidity_ratio)

        except Exception:
            return False

    def _check_portfolio_risk_limits(self, position_value: float) -> bool:
        """
        Check if adding this position would violate portfolio risk limits
        """
        try:
            new_exposure = self.total_exposure + position_value
            new_exposure_pct = new_exposure / self.portfolio_value

            return new_exposure_pct <= self.risk_limits.max_portfolio_risk_pct

        except Exception:
            return False

    def emergency_stop(self):
        """
        Emergency stop - close all positions immediately
        """
        try:
            positions_to_close = list(self.positions.keys())
            closed_count = 0

            for pair in positions_to_close:
                position = self.positions[pair]
                # Use current price as exit price (simplified)
                if self.close_position(pair, position.current_price, "emergency_stop"):
                    closed_count += 1

            logger.warning(f"Emergency stop executed: closed {closed_count}/{len(positions_to_close)} positions")
            return closed_count

        except Exception as e:
            logger.error(f"Error in emergency stop: {e}")
            return 0