#!/usr/bin/env python3
"""
SovereignForge Risk Manager - Wave 3
Comprehensive risk management system for arbitrage trading
"""

import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging
import json
import os

logger = logging.getLogger(__name__)

class RiskManager:
    """Comprehensive risk management for arbitrage trading"""

    def __init__(self, config: Dict = None):
        self.config = config or self._default_config()

        # Risk metrics (initialize first)
        self.portfolio_value = self.config['initial_capital']
        self.peak_portfolio_value = self.portfolio_value
        self.current_drawdown = 0.0

        # Position tracking
        self.open_positions = {}
        self.position_history = []
        self.daily_stats = self._init_daily_stats()

        # Trading state
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.max_daily_loss = self.config['max_daily_loss']
        self.max_single_trade = self.config['max_single_trade']
        self.max_open_positions = self.config['max_open_positions']
        self.max_drawdown = self.config['max_drawdown']

        logger.info(f"Risk Manager initialized with ${self.portfolio_value} capital")

    def _default_config(self) -> Dict:
        """Default risk management configuration"""
        return {
            'initial_capital': 10000.0,  # $10,000 starting capital
            'max_daily_loss': 0.05,      # 5% max daily loss
            'max_single_trade': 0.02,    # 2% max per trade
            'max_open_positions': 3,     # Max 3 concurrent positions
            'max_drawdown': 0.10,        # 10% max drawdown
            'kelly_fraction': 0.5,       # 50% Kelly criterion
            'stop_loss_pct': 0.005,      # 0.5% stop loss
            'take_profit_pct': 0.01,     # 1% take profit
            'min_arbitrage_spread': 0.001,  # 0.1% min spread
            'max_slippage': 0.002,       # 0.2% max slippage
            'volatility_lookback': 20,   # 20 periods for volatility
            'risk_free_rate': 0.02       # 2% risk-free rate
        }

    def _init_daily_stats(self) -> Dict:
        """Initialize daily statistics tracking"""
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
            'win_rate': 0.0
        }

    def calculate_position_size(self, arbitrage_opportunity: Dict, asset_config: Dict = None) -> Dict:
        """Calculate position size using Kelly criterion and risk limits with asset-specific adjustments"""

        if not self._can_open_position():
            return {'approved': False, 'reason': 'Risk limits exceeded'}

        # Extract opportunity details
        spread_pct = arbitrage_opportunity.get('spread_percentage', 0)
        confidence = arbitrage_opportunity.get('confidence', 0)
        symbol = arbitrage_opportunity.get('symbol', 'BTC/USDT')

        # Get asset-specific configuration
        if asset_config is None:
            asset_config = self._get_asset_config(symbol)

        volatility = asset_config.get('volatility', 0.03)
        min_order_size = asset_config.get('min_order_size', 0.0001)
        volatility_multiplier = asset_config.get('volatility_multiplier', 1.0)

        # Minimum spread check
        if spread_pct < self.config['min_arbitrage_spread']:
            return {'approved': False, 'reason': f'Spread {spread_pct:.4f} below minimum {self.config["min_arbitrage_spread"]:.4f}'}

        # Calculate Kelly position size
        kelly_size = self._kelly_criterion(spread_pct, confidence, volatility)

        # Apply risk limits
        max_position_value = self.portfolio_value * self.config['max_single_trade']
        kelly_position_value = self.portfolio_value * kelly_size

        # Take the minimum of Kelly and max single trade
        position_value = min(kelly_position_value, max_position_value)

        # Apply asset-specific volatility adjustment
        vol_adjustment = 1.0 / (1.0 + volatility * volatility_multiplier)
        position_value *= vol_adjustment

        # Ensure minimum position size (asset-specific)
        min_position = max(
            self.portfolio_value * 0.001,  # 0.1% of portfolio minimum
            min_order_size * arbitrage_opportunity.get('entry_price', 50000)  # Minimum order value
        )
        position_value = max(position_value, min_position)

        # Final approval check
        if position_value > max_position_value:
            return {'approved': False, 'reason': f'Position size ${position_value:.2f} exceeds max single trade limit'}

        # Calculate quantity based on position value and entry price
        entry_price = arbitrage_opportunity.get('entry_price', 50000)
        quantity = position_value / entry_price

        # Ensure minimum quantity
        quantity = max(quantity, min_order_size)

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
            'take_profit_price': self._calculate_take_profit(arbitrage_opportunity)
        }

    def _get_asset_config(self, symbol: str) -> Dict:
        """Get asset-specific configuration parameters"""
        # Default asset configurations for multi-asset support
        asset_configs = {
            'BTC/USDT': {
                'volatility': 0.03,  # 3% daily volatility
                'min_order_size': 0.0001,  # 0.0001 BTC minimum
                'volatility_multiplier': 1.0
            },
            'ETH/USDT': {
                'volatility': 0.04,  # 4% daily volatility
                'min_order_size': 0.001,  # 0.001 ETH minimum
                'volatility_multiplier': 1.0
            },
            'XRP/USDT': {
                'volatility': 0.08,  # 8% daily volatility (high)
                'min_order_size': 1,  # 1 XRP minimum
                'volatility_multiplier': 1.5  # Higher risk adjustment
            },
            'XLM/USDT': {
                'volatility': 0.07,  # 7% daily volatility
                'min_order_size': 1,  # 1 XLM minimum
                'volatility_multiplier': 1.4
            },
            'HBAR/USDT': {
                'volatility': 0.09,  # 9% daily volatility (very high)
                'min_order_size': 10,  # 10 HBAR minimum
                'volatility_multiplier': 1.6
            },
            'ALGO/USDT': {
                'volatility': 0.10,  # 10% daily volatility (very high)
                'min_order_size': 1,  # 1 ALGO minimum
                'volatility_multiplier': 1.7
            },
            'ADA/USDT': {
                'volatility': 0.06,  # 6% daily volatility
                'min_order_size': 1,  # 1 ADA minimum
                'volatility_multiplier': 1.2
            }
        }

        # Return asset config or default
        return asset_configs.get(symbol, {
            'volatility': 0.05,  # Default 5% volatility
            'min_order_size': 0.001,  # Default minimum order
            'volatility_multiplier': 1.0
        })

    def _kelly_criterion(self, win_probability: float, win_amount: float, loss_amount: float = 1.0) -> float:
        """Calculate Kelly criterion position size"""
        # Simplified Kelly for arbitrage (win_amount is the spread, loss_amount is transaction costs)
        if win_probability <= 0 or win_probability >= 1:
            return 0.0

        # Kelly formula: f = (p * b - q) / b
        # where p = win probability, q = loss probability, b = win/loss ratio
        b = win_amount / loss_amount
        kelly = (win_probability * b - (1 - win_probability)) / b

        # Apply fraction of Kelly for safety
        kelly *= self.config['kelly_fraction']

        # Ensure positive and reasonable size
        kelly = max(0.0, min(kelly, 0.1))  # Max 10% of portfolio

        return kelly

    def _can_open_position(self) -> bool:
        """Check if we can open a new position"""

        # Check daily loss limit
        if self.daily_pnl < -self.portfolio_value * self.config['max_daily_loss']:
            logger.warning(f"Daily loss limit reached: ${self.daily_pnl:.2f}")
            return False

        # Check drawdown limit
        if self.current_drawdown > self.config['max_drawdown']:
            logger.warning(f"Drawdown limit reached: {self.current_drawdown:.4f}")
            return False

        # Check open positions limit
        if len(self.open_positions) >= self.config['max_open_positions']:
            logger.warning(f"Open positions limit reached: {len(self.open_positions)}")
            return False

        return True

    def _calculate_stop_loss(self, opportunity: Dict) -> float:
        """Calculate stop loss price"""
        entry_price = opportunity.get('entry_price', 0)
        stop_loss_pct = self.config['stop_loss_pct']

        # For arbitrage, stop loss is based on spread compression
        return entry_price * (1 - stop_loss_pct)

    def _calculate_take_profit(self, opportunity: Dict) -> float:
        """Calculate take profit price"""
        entry_price = opportunity.get('entry_price', 0)
        take_profit_pct = self.config['take_profit_pct']

        # For arbitrage, take profit is based on target spread capture
        return entry_price * (1 + take_profit_pct)

    def open_position(self, position_details: Dict) -> Dict:
        """Open a new position"""

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
            'status': 'open'
        }

        self.open_positions[position_id] = position
        self.daily_trades += 1

        logger.info(f"Opened position {position_id}: {position['symbol']} {position['side']} {position['quantity']} @ ${position['entry_price']:.4f}")

        return position

    def close_position(self, position_id: str, exit_price: float, reason: str = 'manual') -> Dict:
        """Close an existing position"""

        if position_id not in self.open_positions:
            logger.error(f"Position {position_id} not found")
            return None

        position = self.open_positions[position_id]

        # Calculate P&L
        if position['side'] == 'buy':
            pnl = (exit_price - position['entry_price']) * position['quantity']
        else:  # sell
            pnl = (position['entry_price'] - exit_price) * position['quantity']

        # Update position
        position.update({
            'exit_price': exit_price,
            'pnl': pnl,
            'exit_timestamp': datetime.now(),
            'exit_reason': reason,
            'status': 'closed'
        })

        # Update portfolio
        self.portfolio_value += pnl
        self.daily_pnl += pnl

        # Update drawdown
        if self.portfolio_value > self.peak_portfolio_value:
            self.peak_portfolio_value = self.portfolio_value
            self.current_drawdown = 0.0
        else:
            self.current_drawdown = (self.peak_portfolio_value - self.portfolio_value) / self.peak_portfolio_value

        # Move to history
        self.position_history.append(position)
        del self.open_positions[position_id]

        # Update daily stats
        self._update_daily_stats(position)

        logger.info(f"Closed position {position_id}: P&L ${pnl:.2f}, Portfolio: ${self.portfolio_value:.2f}")

        return position

    def check_stop_loss_take_profit(self, current_prices: Dict) -> List[Dict]:
        """Check for stop loss/take profit triggers"""

        triggered_positions = []

        for position_id, position in list(self.open_positions.items()):
            symbol = position['symbol']
            current_price = current_prices.get(symbol)

            if current_price is None:
                continue

            # Check stop loss
            if position['side'] == 'buy' and current_price <= position['stop_loss']:
                logger.info(f"Stop loss triggered for {position_id}: {current_price:.4f} <= {position['stop_loss']:.4f}")
                closed = self.close_position(position_id, current_price, 'stop_loss')
                if closed:
                    triggered_positions.append(closed)

            elif position['side'] == 'sell' and current_price >= position['stop_loss']:
                logger.info(f"Stop loss triggered for {position_id}: {current_price:.4f} >= {position['stop_loss']:.4f}")
                closed = self.close_position(position_id, current_price, 'stop_loss')
                if closed:
                    triggered_positions.append(closed)

            # Check take profit
            elif position['side'] == 'buy' and current_price >= position['take_profit']:
                logger.info(f"Take profit triggered for {position_id}: {current_price:.4f} >= {position['take_profit']:.4f}")
                closed = self.close_position(position_id, current_price, 'take_profit')
                if closed:
                    triggered_positions.append(closed)

            elif position['side'] == 'sell' and current_price <= position['take_profit']:
                logger.info(f"Take profit triggered for {position_id}: {current_price:.4f} <= {position['take_profit']:.4f}")
                closed = self.close_position(position_id, current_price, 'take_profit')
                if closed:
                    triggered_positions.append(closed)

        return triggered_positions

    def _update_daily_stats(self, closed_position: Dict):
        """Update daily statistics"""

        pnl = closed_position['pnl']

        self.daily_stats['trades'] += 1

        if pnl > 0:
            self.daily_stats['winning_trades'] += 1
            self.daily_stats['gross_profit'] += pnl
        else:
            self.daily_stats['losing_trades'] += 1
            self.daily_stats['gross_loss'] += abs(pnl)

        self.daily_stats['net_pnl'] = self.daily_stats['gross_profit'] - self.daily_stats['gross_loss']

        # Calculate win rate
        total_trades = self.daily_stats['winning_trades'] + self.daily_stats['losing_trades']
        if total_trades > 0:
            self.daily_stats['win_rate'] = self.daily_stats['winning_trades'] / total_trades

        # Update max drawdown
        self.daily_stats['max_drawdown'] = max(self.daily_stats['max_drawdown'], self.current_drawdown)

    def get_risk_metrics(self) -> Dict:
        """Get current risk metrics"""

        # Calculate Sharpe ratio (simplified)
        returns = [pos['pnl'] / self.config['initial_capital'] for pos in self.position_history[-50:]]
        if len(returns) > 1:
            avg_return = np.mean(returns)
            std_return = np.std(returns)
            if std_return > 0:
                sharpe = (avg_return - self.config['risk_free_rate']/252) / std_return * np.sqrt(252)
            else:
                sharpe = 0.0
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
                'drawdown_limit': self.config['max_drawdown']
            }
        }

    def reset_daily_stats(self):
        """Reset daily statistics (call at start of new trading day)"""

        # Save previous day stats
        if self.daily_stats['trades'] > 0:
            self._save_daily_stats()

        # Reset for new day
        self.daily_pnl = 0.0
        self.daily_trades = 0
        self.daily_stats = self._init_daily_stats()

        logger.info("Daily statistics reset for new trading day")

    def _save_daily_stats(self):
        """Save daily statistics to file"""

        stats_file = "E:\\SovereignForge\\data\\daily_stats.json"

        try:
            # Load existing stats
            if os.path.exists(stats_file):
                with open(stats_file, 'r') as f:
                    all_stats = json.load(f)
            else:
                all_stats = []

            # Add current stats
            all_stats.append(self.daily_stats)

            # Keep only last 90 days
            all_stats = all_stats[-90:]

            # Save
            with open(stats_file, 'w') as f:
                json.dump(all_stats, f, indent=2, default=str)

        except Exception as e:
            logger.error(f"Failed to save daily stats: {e}")

    def emergency_stop(self):
        """Emergency stop - close all positions immediately"""

        logger.warning("EMERGENCY STOP ACTIVATED - Closing all positions")

        closed_positions = []

        for position_id in list(self.open_positions.keys()):
            # Close at current market price (simplified - would need real prices)
            position = self.open_positions[position_id]
            exit_price = position['entry_price'] * 0.999  # Assume slight loss

            closed = self.close_position(position_id, exit_price, 'emergency_stop')
            if closed:
                closed_positions.append(closed)

        logger.warning(f"Emergency stop completed: {len(closed_positions)} positions closed")

        return closed_positions

class ArbitrageRiskAssessor:
    """Specialized risk assessment for arbitrage opportunities"""

    def __init__(self, risk_manager: RiskManager):
        self.risk_manager = risk_manager

    def assess_arbitrage_risk(self, arbitrage_signal: Dict, market_data: Dict) -> Dict:
        """Comprehensive risk assessment for arbitrage opportunity"""

        assessment = {
            'overall_risk_score': 0.0,
            'risk_factors': {},
            'recommendations': [],
            'approved': False
        }

        # Factor 1: Spread stability
        spread_stability = self._assess_spread_stability(arbitrage_signal, market_data)
        assessment['risk_factors']['spread_stability'] = spread_stability

        # Factor 2: Market volatility
        volatility_risk = self._assess_volatility_risk(market_data)
        assessment['risk_factors']['volatility'] = volatility_risk

        # Factor 3: Liquidity risk
        liquidity_risk = self._assess_liquidity_risk(market_data)
        assessment['risk_factors']['liquidity'] = liquidity_risk

        # Factor 4: Execution risk
        execution_risk = self._assess_execution_risk(arbitrage_signal)
        assessment['risk_factors']['execution'] = execution_risk

        # Factor 5: Market impact
        market_impact = self._assess_market_impact(arbitrage_signal, market_data)
        assessment['risk_factors']['market_impact'] = market_impact

        # Calculate overall risk score (weighted average)
        weights = {
            'spread_stability': 0.3,
            'volatility': 0.25,
            'liquidity': 0.2,
            'execution': 0.15,
            'market_impact': 0.1
        }

        overall_score = sum(
            assessment['risk_factors'][factor] * weights[factor]
            for factor in assessment['risk_factors']
        )

        assessment['overall_risk_score'] = overall_score

        # Generate recommendations
        assessment['recommendations'] = self._generate_recommendations(assessment['risk_factors'])

        # Final approval (risk score < 0.6 is acceptable)
        assessment['approved'] = overall_score < 0.6

        return assessment

    def _assess_spread_stability(self, signal: Dict, market_data: Dict) -> float:
        """Assess spread stability risk (0-1, lower is better)"""

        spread_pct = signal.get('spread_percentage', 0)

        # Very wide spreads are risky (might not persist)
        if spread_pct > 0.01:  # >1%
            return 0.8
        elif spread_pct > 0.005:  # >0.5%
            return 0.4
        else:
            return 0.1

    def _assess_volatility_risk(self, market_data: Dict) -> float:
        """Assess volatility risk"""

        volatility = market_data.get('volatility', 0.02)

        # High volatility increases risk
        if volatility > 0.05:  # >5% volatility
            return 0.9
        elif volatility > 0.03:  # >3% volatility
            return 0.6
        else:
            return 0.2

    def _assess_liquidity_risk(self, market_data: Dict) -> float:
        """Assess liquidity risk"""

        exchanges = market_data.get('exchanges', {})
        total_volume = sum(exch.get('volume', 0) for exch in exchanges.values())

        # Low volume increases execution risk
        if total_volume < 100:  # Very low volume
            return 0.9
        elif total_volume < 500:  # Low volume
            return 0.6
        else:
            return 0.2

    def _assess_execution_risk(self, signal: Dict) -> float:
        """Assess execution risk"""

        confidence = signal.get('confidence', 0)

        # Low confidence increases execution risk
        if confidence < 0.5:
            return 0.8
        elif confidence < 0.7:
            return 0.5
        else:
            return 0.1

    def _assess_market_impact(self, signal: Dict, market_data: Dict) -> float:
        """Assess market impact risk"""

        position_size_pct = signal.get('position_size_pct', 0)
        total_volume = sum(exch.get('volume', 0) for exch in market_data.get('exchanges', {}).values())

        # Large position relative to market volume
        if total_volume > 0 and position_size_pct * self.risk_manager.portfolio_value > total_volume * 0.01:  # >1% of volume
            return 0.8
        elif position_size_pct > 0.05:  # >5% of portfolio
            return 0.6
        else:
            return 0.2

    def _generate_recommendations(self, risk_factors: Dict) -> List[str]:
        """Generate risk mitigation recommendations"""

        recommendations = []

        if risk_factors['spread_stability'] > 0.6:
            recommendations.append("Reduce position size - spread may not persist")

        if risk_factors['volatility'] > 0.6:
            recommendations.append("Consider wider stop loss due to high volatility")

        if risk_factors['liquidity'] > 0.6:
            recommendations.append("Monitor order book depth - low liquidity detected")

        if risk_factors['execution'] > 0.6:
            recommendations.append("Wait for higher confidence signal")

        if risk_factors['market_impact'] > 0.6:
            recommendations.append("Reduce position size to minimize market impact")

        return recommendations

def create_default_risk_manager() -> RiskManager:
    """Create risk manager with default settings"""

    config = {
        'initial_capital': 10000.0,
        'max_daily_loss': 0.05,
        'max_single_trade': 0.02,
        'max_open_positions': 3,
        'max_drawdown': 0.10,
        'kelly_fraction': 0.5,
        'stop_loss_pct': 0.005,
        'take_profit_pct': 0.01,
        'min_arbitrage_spread': 0.001,
        'max_slippage': 0.002
    }

    return RiskManager(config)

# Example usage
if __name__ == "__main__":
    # Create risk manager
    risk_mgr = create_default_risk_manager()

    # Example arbitrage opportunity
    opportunity = {
        'spread_percentage': 0.003,  # 0.3%
        'confidence': 0.8,
        'entry_price': 45000,
        'symbol': 'BTC/USDT'
    }

    # Calculate position size
    position_calc = risk_mgr.calculate_position_size(opportunity)

    print("Risk Management Test")
    print("=" * 30)
    print(f"Portfolio Value: ${risk_mgr.portfolio_value:.2f}")
    print(f"Opportunity: {opportunity['spread_percentage']:.3f} spread, {opportunity['confidence']:.1f} confidence")
    print(f"Position Approved: {position_calc['approved']}")

    if position_calc['approved']:
        print(f"Position Size: ${position_calc['position_value']:.2f} ({position_calc['position_size_pct']:.3f})")
        print(f"Kelly Size: {position_calc['kelly_size']:.4f}")
        print(f"Stop Loss: ${position_calc['stop_loss_price']:.2f}")
        print(f"Take Profit: ${position_calc['take_profit_price']:.2f}")

    # Get risk metrics
    metrics = risk_mgr.get_risk_metrics()
    print(f"\nRisk Metrics:")
    print(f"Open Positions: {metrics['open_positions']}")
    print(f"Current Drawdown: {metrics['current_drawdown']:.4f}")
    print(f"Daily P&L: ${metrics['daily_pnl']:.2f}")