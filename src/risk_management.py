#!/usr/bin/env python3
"""
SovereignForge - Risk Management System
Position sizing, stop-loss, and portfolio risk controls for MiCA compliance
"""

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


def _fire_alert(title: str, message: str, level: str = "warning") -> None:
    """
    Fire-and-forget alert from synchronous code.
    Schedules the coroutine on the running event loop if one exists,
    otherwise logs the alert so no information is lost.
    """
    import asyncio
    try:
        from telegram_alerts import send_system_alert
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(send_system_alert(title, message, level))
        else:
            # No running loop — use multi_channel_alerts synchronous path or just log
            try:
                from multi_channel_alerts import Alert, AlertPriority, get_alert_router
                pmap = {"error": AlertPriority.HIGH, "warning": AlertPriority.MEDIUM,
                        "success": AlertPriority.LOW, "info": AlertPriority.LOW}
                priority = pmap.get(level, AlertPriority.MEDIUM)
                asyncio.run(get_alert_router().send(Alert(title=title, message=message, priority=priority)))
            except Exception:
                logger.warning(f"ALERT [{level.upper()}] {title}: {message}")
    except Exception as e:
        logger.warning(f"ALERT [{level.upper()}] {title}: {message} (send failed: {e})")

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

    def validate_opportunity(self, opportunity) -> bool:
        """
        Validate arbitrage opportunity against risk limits
        Supports both dict and ArbitrageOpportunity objects
        """
        try:
            # Handle both dict and object types
            if hasattr(opportunity, 'pair'):
                # ArbitrageOpportunity object
                pair = opportunity.pair
                exchanges = opportunity.exchanges
                prices = opportunity.prices
                spread = opportunity.spread_prediction
            else:
                # Dictionary
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

    def calculate_position_size(self, opportunity: Dict[str, Any], use_kelly: bool = True) -> float:
        """
        Calculate optimal position size based on risk limits and Kelly Criterion
        """
        try:
            spread = opportunity.get('spread_prediction', 0)
            prices = opportunity.get('prices', {})
            risk_score = opportunity.get('risk_score', 0.5)
            confidence = opportunity.get('confidence', 0.5)

            if not prices:
                return 0.0

            # Use average price for position sizing
            avg_price = sum(prices.values()) / len(prices)

            if use_kelly:
                # Use Kelly Criterion for optimal position sizing
                kelly_size = self._calculate_kelly_position_size(
                    spread=spread,
                    confidence=confidence,
                    risk_score=risk_score,
                    avg_price=avg_price
                )

                # Apply traditional risk limits as safety bounds
                max_position_value = self.portfolio_value * self.risk_limits.max_position_size_pct
                max_kelly_value = kelly_size * avg_price

                # Take the more conservative of Kelly and traditional limits
                position_value = min(max_kelly_value, max_position_value)
            else:
                # Traditional position sizing
                max_position_value = self.portfolio_value * self.risk_limits.max_position_size_pct
                risk_adjustment = 1.0 - (risk_score * 0.5)  # Reduce size by up to 50% for high risk
                position_value = max_position_value * risk_adjustment

            # Calculate position size in base currency
            position_size = position_value / avg_price

            # Apply minimum position constraints (0.001 BTC equivalent minimum)
            min_position_value = 0.001 * avg_price
            if position_value < min_position_value:
                logger.warning(f"Position size too small: ${position_value}")
                return 0.0

            # Check portfolio risk limits
            if not self._check_portfolio_risk_limits(position_size * avg_price):
                return 0.0

            return position_size

        except Exception as e:
            logger.error(f"Error calculating position size: {e}")
            return 0.0

    def _calculate_kelly_position_size(self,
                                     spread: float,
                                     confidence: float,
                                     risk_score: float,
                                     avg_price: float) -> float:
        """
        Calculate position size using Kelly Criterion
        Kelly % = (bp - q) / b
        Where:
        - b = odds (potential profit / potential loss)
        - p = probability of winning
        - q = probability of losing (1-p)
        """
        try:
            # Estimate win probability from confidence and spread
            # Higher confidence and larger spread = higher win probability
            base_win_prob = confidence
            spread_bonus = min(spread * 10, 0.3)  # Up to 30% bonus for large spreads
            win_probability = min(base_win_prob + spread_bonus, 0.95)  # Cap at 95%

            # Estimate odds ratio (potential profit / potential loss)
            # For arbitrage, profit is the spread, loss is transaction costs + slippage
            estimated_costs = 0.001  # 0.1% estimated costs (fees + slippage)
            profit_ratio = spread / max(estimated_costs, 0.0001)  # Avoid division by zero

            # Kelly fraction
            q = 1.0 - win_probability  # Probability of loss
            b = profit_ratio  # Odds ratio

            if b <= 0:
                return 0.0  # No positive expectation

            kelly_fraction = (b * win_probability - q) / b

            # Apply risk adjustments
            # Reduce Kelly fraction based on risk score and portfolio constraints
            risk_multiplier = 1.0 - (risk_score * 0.7)  # Reduce by up to 70% for high risk
            kelly_fraction *= risk_multiplier

            # Half-Kelly for safety (more conservative)
            kelly_fraction *= 0.5

            # Ensure positive and reasonable bounds
            kelly_fraction = max(0.0, min(kelly_fraction, 0.25))  # Max 25% of capital

            # Calculate position value
            position_value = self.portfolio_value * kelly_fraction

            # Additional safety checks
            if win_probability < 0.55:
                # Too low win probability, reduce position
                position_value *= 0.5

            if spread < 0.001:
                # Spread too small for profitable arbitrage
                position_value *= 0.3

            logger.info(f"Kelly position sizing: win_prob={win_probability:.3f}, "
                       f"odds={b:.3f}, kelly_fraction={kelly_fraction:.4f}, "
                       f"position_value=${position_value:.2f}")

            return position_value

        except Exception as e:
            logger.error(f"Error in Kelly calculation: {e}")
            return 0.0

    def calculate_kelly_metrics(self, opportunity: Dict[str, Any]) -> Dict[str, float]:
        """
        Calculate Kelly Criterion metrics for analysis
        """
        try:
            spread = opportunity.get('spread_prediction', 0)
            confidence = opportunity.get('confidence', 0.5)
            risk_score = opportunity.get('risk_score', 0.5)
            prices = opportunity.get('prices', {})

            if not prices:
                return {}

            avg_price = sum(prices.values()) / len(prices)

            # Calculate Kelly components
            base_win_prob = confidence
            spread_bonus = min(spread * 10, 0.3)
            win_probability = min(base_win_prob + spread_bonus, 0.95)

            estimated_costs = 0.001
            profit_ratio = spread / max(estimated_costs, 0.0001)

            q = 1.0 - win_probability
            b = profit_ratio

            kelly_fraction = (b * win_probability - q) / b if b > 0 else 0.0
            risk_multiplier = 1.0 - (risk_score * 0.7)
            adjusted_kelly = kelly_fraction * risk_multiplier * 0.5  # Half-Kelly

            # Expected value calculation
            expected_value = win_probability * spread - (1 - win_probability) * estimated_costs

            return {
                'win_probability': win_probability,
                'odds_ratio': b,
                'kelly_fraction': kelly_fraction,
                'adjusted_kelly_fraction': adjusted_kelly,
                'expected_value_per_trade': expected_value,
                'expected_value_pct': expected_value / avg_price if avg_price > 0 else 0,
                'risk_adjustment': risk_multiplier,
                'spread_bonus': spread_bonus
            }

        except Exception as e:
            logger.error(f"Error calculating Kelly metrics: {e}")
            return {}

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

            # Execute closures with alerts
            closed_pairs = []
            for pair, exit_price, reason in positions_to_close:
                if self.close_position(pair, exit_price, reason):
                    closed_pairs.append(pair)

                    # Send alert for automated position closure
                    alert_title = f"Position Closed: {reason.upper()}"
                    alert_message = f"Pair: {pair}\nExit Price: ${exit_price:.2f}\nReason: {reason.replace('_', ' ').title()}"
                    alert_level = "warning" if reason == "stop_loss" else "success" if reason == "take_profit" else "info"
                    _fire_alert(alert_title, alert_message, alert_level)

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

            # Check risk limit violations and send alerts
            risk_violations = []
            if total_exposure_pct > self.risk_limits.max_portfolio_risk_pct:
                violation_msg = f"Portfolio exposure ({total_exposure_pct:.1%}) exceeds limit ({self.risk_limits.max_portfolio_risk_pct:.1%})"
                risk_violations.append(violation_msg)

                # Send alert for risk limit breach
                _fire_alert(
                    "Risk Limit Breach: Portfolio Exposure",
                    f"Current: {total_exposure_pct:.1%}\nLimit: {self.risk_limits.max_portfolio_risk_pct:.1%}\nAction Required: Reduce exposure",
                    "error"
                )

            if abs(daily_pnl_pct) > self.risk_limits.max_daily_loss_pct:
                violation_msg = f"Daily P&L ({daily_pnl_pct:.1%}) exceeds limit ({self.risk_limits.max_daily_loss_pct:.1%})"
                risk_violations.append(violation_msg)

                # Send alert for daily loss limit breach
                _fire_alert(
                    "Risk Limit Breach: Daily Loss",
                    f"Current: {daily_pnl_pct:.1%}\nLimit: {self.risk_limits.max_daily_loss_pct:.1%}\nDaily P&L: ${self.daily_pnl:.2f}",
                    "error" if daily_pnl_pct < -self.risk_limits.max_daily_loss_pct else "warning"
                )

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

            # Send emergency stop alert
            _fire_alert(
                "EMERGENCY STOP EXECUTED",
                f"Closed {closed_count}/{len(positions_to_close)} positions\nPortfolio protected from further losses\nManual intervention required",
                "error"
            )

            logger.warning(f"Emergency stop executed: closed {closed_count}/{len(positions_to_close)} positions")
            return closed_count

        except Exception as e:
            logger.error(f"Error in emergency stop: {e}")
            return 0


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

_risk_manager: Optional[RiskManager] = None


def get_risk_manager(initial_capital: float = 10000.0) -> RiskManager:
    """Return the module-level RiskManager singleton, creating it on first call."""
    global _risk_manager
    if _risk_manager is None:
        _risk_manager = RiskManager(initial_capital=initial_capital)
    return _risk_manager


# Alias for portfolio_optimization.py backwards compatibility
RiskManagementEngine = RiskManager
get_risk_management_engine = get_risk_manager


# ---------------------------------------------------------------------------
# TradingRiskManager — config-dict-based risk manager used by main.py
# and backtester.py for position sizing, daily stats, and drawdown tracking.
# (Formerly in risk_manager.py)
# ---------------------------------------------------------------------------

class TradingRiskManager:
    """Config-dict-based risk manager for backtesting and CLI trading."""

    def __init__(self, config: Dict = None):
        self.config = config or self._default_config()

        # Risk metrics
        self.portfolio_value = self.config['initial_capital']
        self.peak_portfolio_value = self.portfolio_value
        self.current_drawdown = 0.0

        # Position tracking
        self.open_positions: Dict[str, Dict] = {}
        self.position_history: List[Dict] = []
        self.daily_stats = self._init_daily_stats()

        # Trading state
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.max_daily_loss = self.config['max_daily_loss']
        self.max_single_trade = self.config['max_single_trade']
        self.max_open_positions = self.config['max_open_positions']
        self.max_drawdown = self.config['max_drawdown']

        logger.info(f"TradingRiskManager initialized with ${self.portfolio_value} capital")

    @staticmethod
    def _default_config() -> Dict:
        return {
            'initial_capital': 10000.0,
            'max_daily_loss': 0.05,
            'max_single_trade': 0.02,
            'max_open_positions': 3,
            'max_drawdown': 0.10,
            'kelly_fraction': 0.5,
            'stop_loss_pct': 0.005,
            'take_profit_pct': 0.01,
            'min_arbitrage_spread': 0.001,
            'max_slippage': 0.002,
            'volatility_lookback': 20,
            'risk_free_rate': 0.02,
        }

    def _init_daily_stats(self) -> Dict:
        return {
            'date': datetime.now().date(),
            'starting_capital': self.portfolio_value,
            'trades': 0,
            'winning_trades': 0,
            'losing_trades': 0,
            'gross_profit': 0.0,
            'gross_loss': 0.0,
            'net_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
        }

    # ----- Asset config -----

    _ASSET_CONFIGS = {
        'BTC/USDC':  {'volatility': 0.03, 'min_order_size': 0.0001, 'volatility_multiplier': 1.0},
        'ETH/USDC':  {'volatility': 0.04, 'min_order_size': 0.001,  'volatility_multiplier': 1.0},
        'XRP/USDC':  {'volatility': 0.08, 'min_order_size': 1,      'volatility_multiplier': 1.5},
        'XLM/USDC':  {'volatility': 0.07, 'min_order_size': 1,      'volatility_multiplier': 1.4},
        'HBAR/USDC': {'volatility': 0.09, 'min_order_size': 10,     'volatility_multiplier': 1.6},
        'ALGO/USDC': {'volatility': 0.10, 'min_order_size': 1,      'volatility_multiplier': 1.7},
        'ADA/USDC':  {'volatility': 0.06, 'min_order_size': 1,      'volatility_multiplier': 1.2},
    }

    def _get_asset_config(self, symbol: str) -> Dict:
        return self._ASSET_CONFIGS.get(symbol, {
            'volatility': 0.05, 'min_order_size': 0.001, 'volatility_multiplier': 1.0,
        })

    # ----- Position sizing -----

    def calculate_position_size(self, arbitrage_opportunity: Dict, asset_config: Dict = None) -> Dict:
        """Calculate position size using Kelly criterion and risk limits."""
        if not self._can_open_position():
            return {'approved': False, 'reason': 'Risk limits exceeded'}

        spread_pct = arbitrage_opportunity.get('spread_percentage', 0)
        confidence = arbitrage_opportunity.get('confidence', 0)
        symbol = arbitrage_opportunity.get('symbol', 'BTC/USDC')

        if asset_config is None:
            asset_config = self._get_asset_config(symbol)

        volatility = asset_config.get('volatility', 0.03)
        min_order_size = asset_config.get('min_order_size', 0.0001)
        volatility_multiplier = asset_config.get('volatility_multiplier', 1.0)

        if spread_pct < self.config['min_arbitrage_spread']:
            return {'approved': False, 'reason': f'Spread {spread_pct:.4f} below minimum'}

        kelly_size = self._kelly_criterion(spread_pct, confidence, volatility)
        max_position_value = self.portfolio_value * self.config['max_single_trade']
        kelly_position_value = self.portfolio_value * kelly_size
        position_value = min(kelly_position_value, max_position_value)

        vol_adjustment = 1.0 / (1.0 + volatility * volatility_multiplier)
        position_value *= vol_adjustment

        min_position = max(
            self.portfolio_value * 0.001,
            min_order_size * arbitrage_opportunity.get('entry_price', 50000),
        )
        position_value = max(position_value, min_position)

        if position_value > max_position_value:
            return {'approved': False, 'reason': 'Position exceeds max single trade limit'}

        entry_price = arbitrage_opportunity.get('entry_price', 50000)
        quantity = max(position_value / entry_price, min_order_size)

        return {
            'approved': True,
            'position_value': position_value,
            'quantity': quantity,
            'position_size_pct': position_value / self.portfolio_value,
            'kelly_size': kelly_size,
            'volatility_adjustment': vol_adjustment,
            'asset_volatility': volatility,
            'min_order_size': min_order_size,
            'stop_loss_price': self._calculate_stop_loss(arbitrage_opportunity),
            'take_profit_price': self._calculate_take_profit(arbitrage_opportunity),
        }

    def _kelly_criterion(self, win_probability: float, win_amount: float, loss_amount: float = 1.0) -> float:
        if win_probability <= 0 or win_probability >= 1:
            return 0.0
        b = win_amount / loss_amount
        kelly = (win_probability * b - (1 - win_probability)) / b
        kelly *= self.config['kelly_fraction']
        return max(0.0, min(kelly, 0.1))

    def _can_open_position(self) -> bool:
        if self.daily_pnl < -self.portfolio_value * self.config['max_daily_loss']:
            return False
        if self.current_drawdown > self.config['max_drawdown']:
            return False
        if len(self.open_positions) >= self.config['max_open_positions']:
            return False
        return True

    def _calculate_stop_loss(self, opportunity: Dict) -> float:
        entry_price = opportunity.get('entry_price', 0)
        return entry_price * (1 - self.config['stop_loss_pct'])

    def _calculate_take_profit(self, opportunity: Dict) -> float:
        entry_price = opportunity.get('entry_price', 0)
        return entry_price * (1 + self.config['take_profit_pct'])

    # ----- Position lifecycle -----

    def open_position(self, position_details: Dict) -> Dict:
        position_id = f"pos_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.open_positions)}"
        position = {
            'id': position_id,
            'symbol': position_details['symbol'],
            'side': position_details['side'],
            'quantity': position_details['quantity'],
            'entry_price': position_details['entry_price'],
            'position_value': position_details['position_value'],
            'stop_loss': position_details['stop_loss'],
            'take_profit': position_details['take_profit'],
            'timestamp': datetime.now(),
            'status': 'open',
        }
        self.open_positions[position_id] = position
        self.daily_trades += 1
        logger.info(f"Opened position {position_id}: {position['symbol']} {position['side']} @ ${position['entry_price']:.4f}")
        return position

    def close_position(self, position_id: str, exit_price: float, reason: str = 'manual') -> Optional[Dict]:
        if position_id not in self.open_positions:
            logger.error(f"Position {position_id} not found")
            return None

        position = self.open_positions[position_id]
        if position['side'] == 'buy':
            pnl = (exit_price - position['entry_price']) * position['quantity']
        else:
            pnl = (position['entry_price'] - exit_price) * position['quantity']

        position.update({
            'exit_price': exit_price, 'pnl': pnl,
            'exit_timestamp': datetime.now(), 'exit_reason': reason, 'status': 'closed',
        })

        self.portfolio_value += pnl
        self.daily_pnl += pnl

        if self.portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = self.portfolio_value
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = (self.peak_portfolio_value - self.portfolio_value) / self.peak_portfolio_value

        self.position_history.append(position)
        del self.open_positions[position_id]
        self._update_daily_stats(position)

        logger.info(f"Closed position {position_id}: P&L ${pnl:.2f}")
        return position

    def check_stop_loss_take_profit(self, current_prices: Dict) -> List[Dict]:
        triggered = []
        for position_id, position in list(self.open_positions.items()):
            current_price = current_prices.get(position['symbol'])
            if current_price is None:
                continue
            if position['side'] == 'buy' and current_price <= position['stop_loss']:
                closed = self.close_position(position_id, current_price, 'stop_loss')
            elif position['side'] == 'sell' and current_price >= position['stop_loss']:
                closed = self.close_position(position_id, current_price, 'stop_loss')
            elif position['side'] == 'buy' and current_price >= position['take_profit']:
                closed = self.close_position(position_id, current_price, 'take_profit')
            elif position['side'] == 'sell' and current_price <= position['take_profit']:
                closed = self.close_position(position_id, current_price, 'take_profit')
            else:
                closed = None
            if closed:
                triggered.append(closed)
        return triggered

    # ----- Stats -----

    def _update_daily_stats(self, closed_position: Dict):
        pnl = closed_position['pnl']
        self.daily_stats['trades'] += 1
        if pnl > 0:
            self.daily_stats['winning_trades'] += 1
            self.daily_stats['gross_profit'] += pnl
        else:
            self.daily_stats['losing_trades'] += 1
            self.daily_stats['gross_loss'] += abs(pnl)
        self.daily_stats['net_pnl'] = self.daily_stats['gross_profit'] - self.daily_stats['gross_loss']
        total = self.daily_stats['winning_trades'] + self.daily_stats['losing_trades']
        if total > 0:
            self.daily_stats['win_rate'] = self.daily_stats['winning_trades'] / total
        self.daily_stats['max_drawdown'] = max(self.daily_stats['max_drawdown'], self.current_drawdown)

    def get_risk_metrics(self) -> Dict:
        returns = [pos['pnl'] / self.config['initial_capital'] for pos in self.position_history[-50:]]
        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            sharpe = (avg_return - self.config.get('risk_free_rate', 0.02) / 252) / std_return * np.sqrt(252) if std_return > 0 else 0.0
        else:
            sharpe = 0.0

        return {
            'portfolio_value': self.portfolio_value,
            'daily_pnl': self.daily_pnl,
            'daily_trades': self.daily_trades,
            'open_positions': len(self.open_positions),
            'current_drawdown': self.current_drawdown,
            'sharpe_ratio': sharpe,
            'win_rate': self.daily_stats['win_rate'],
            'total_trades': len(self.position_history),
            'risk_limits': {
                'daily_loss_limit': self.portfolio_value * self.config['max_daily_loss'],
                'single_trade_limit': self.portfolio_value * self.config['max_single_trade'],
                'drawdown_limit': self.config['max_drawdown'],
            },
        }

    def reset_daily_stats(self):
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_stats = self._init_daily_stats()
        logger.info("Daily statistics reset")

    def emergency_stop(self) -> List[Dict]:
        logger.warning("EMERGENCY STOP — Closing all positions")
        closed = []
        for position_id in list(self.open_positions.keys()):
            position = self.open_positions[position_id]
            exit_price = position['entry_price'] * 0.999
            result = self.close_position(position_id, exit_price, 'emergency_stop')
            if result:
                closed.append(result)
        logger.warning(f"Emergency stop completed: {len(closed)} positions closed")
        return closed


class ArbitrageRiskAssessor:
    """Specialized 5-factor risk assessment for arbitrage opportunities."""

    def __init__(self, risk_manager: TradingRiskManager):
        self.risk_manager = risk_manager

    def assess_arbitrage_risk(self, arbitrage_signal: Dict, market_data: Dict) -> Dict:
        factors = {
            'spread_stability': self._assess_spread_stability(arbitrage_signal),
            'volatility': self._assess_volatility_risk(market_data),
            'liquidity': self._assess_liquidity_risk(market_data),
            'execution': self._assess_execution_risk(arbitrage_signal),
            'market_impact': self._assess_market_impact(arbitrage_signal, market_data),
        }
        weights = {'spread_stability': 0.3, 'volatility': 0.25, 'liquidity': 0.2, 'execution': 0.15, 'market_impact': 0.1}
        overall = sum(factors[f] * weights[f] for f in factors)
        return {
            'overall_risk_score': overall,
            'risk_factors': factors,
            'recommendations': self._recommendations(factors),
            'approved': overall < 0.6,
        }

    @staticmethod
    def _assess_spread_stability(signal: Dict) -> float:
        spread = signal.get('spread_percentage', 0)
        if spread > 0.01:
            return 0.8
        return 0.4 if spread > 0.005 else 0.1

    @staticmethod
    def _assess_volatility_risk(market_data: Dict) -> float:
        vol = market_data.get('volatility', 0.02)
        if vol > 0.05:
            return 0.9
        return 0.6 if vol > 0.03 else 0.2

    @staticmethod
    def _assess_liquidity_risk(market_data: Dict) -> float:
        total_volume = sum(e.get('volume', 0) for e in market_data.get('exchanges', {}).values())
        if total_volume < 100:
            return 0.9
        return 0.6 if total_volume < 500 else 0.2

    @staticmethod
    def _assess_execution_risk(signal: Dict) -> float:
        conf = signal.get('confidence', 0)
        if conf < 0.5:
            return 0.8
        return 0.5 if conf < 0.7 else 0.1

    def _assess_market_impact(self, signal: Dict, market_data: Dict) -> float:
        pos_pct = signal.get('position_size_pct', 0)
        total_vol = sum(e.get('volume', 0) for e in market_data.get('exchanges', {}).values())
        if total_vol > 0 and pos_pct * self.risk_manager.portfolio_value > total_vol * 0.01:
            return 0.8
        return 0.6 if pos_pct > 0.05 else 0.2

    @staticmethod
    def _recommendations(factors: Dict) -> List[str]:
        msgs = {
            'spread_stability': "Reduce position size — spread may not persist",
            'volatility': "Consider wider stop loss due to high volatility",
            'liquidity': "Monitor order book depth — low liquidity detected",
            'execution': "Wait for higher confidence signal",
            'market_impact': "Reduce position size to minimize market impact",
        }
        return [msgs[k] for k, v in factors.items() if v > 0.6]


def create_default_risk_manager(config: Dict = None) -> TradingRiskManager:
    """Create a TradingRiskManager with default settings."""
    return TradingRiskManager(config)
