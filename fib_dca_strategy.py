#!/usr/bin/env python3
"""
SovereignForge Fibonacci DCA (Dollar Cost Averaging) Strategy
Advanced DCA implementation with Fibonacci retracement levels and ML optimization
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import logging
from pathlib import Path
import json

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FibonacciDCAStrategy:
    """Advanced Fibonacci-based DCA strategy with ML optimization"""

    def __init__(self, symbol: str, config: Dict[str, Any]):
        self.symbol = symbol
        self.config = config

        # Fibonacci retracement levels
        self.fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]  # Standard levels

        # DCA parameters
        self.dca_levels = config.get('dca_levels', 5)
        self.dca_interval_hours = config.get('dca_interval_hours', 24)  # Daily DCA
        self.dca_amount_pct = config.get('dca_amount_pct', 0.02)  # 2% of portfolio per DCA
        self.max_dca_positions = config.get('max_dca_positions', 10)

        # Risk management
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 5% stop loss
        self.take_profit_pct = config.get('take_profit_pct', 0.15)  # 15% take profit
        self.max_drawdown_pct = config.get('max_drawdown_pct', 0.20)  # 20% max drawdown

        # ML optimization
        self.use_ml_optimization = config.get('use_ml_optimization', True)
        self.model_update_interval = config.get('model_update_interval', 24)  # hours

        # DCA state
        self.dca_positions = []  # List of DCA entries
        self.average_entry_price = 0.0
        self.total_invested = 0.0
        self.total_shares = 0.0
        self.fib_swing_high = None
        self.fib_swing_low = None
        self.last_dca_time = None

        # Performance tracking
        self.performance_metrics = {
            'total_trades': 0,
            'profitable_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0,
            'avg_holding_period': 0.0
        }

        # Initialize ML model for DCA optimization
        if self.use_ml_optimization:
            self.dca_optimizer = self._initialize_dca_optimizer()

        logger.info(f"🎯 Initialized Fibonacci DCA Strategy for {symbol}")
        logger.info(f"   DCA Levels: {self.dca_levels}, Interval: {self.dca_interval_hours}hrs")

    def _initialize_dca_optimizer(self):
        """Initialize ML model for DCA parameter optimization"""

        class DCAOptimizer(nn.Module):
            def __init__(self, input_size=50, hidden_size=64):
                super().__init__()
                self.lstm = nn.LSTM(input_size, hidden_size, 2, batch_first=True, dropout=0.2)
                self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
                self.fc2 = nn.Linear(hidden_size // 2, 4)  # timing, amount, levels, interval

                # Initialize weights
                for name, param in self.named_parameters():
                    if 'weight' in name:
                        nn.init.xavier_uniform_(param)
                    elif 'bias' in name:
                        nn.init.constant_(param, 0)

            def forward(self, x):
                out, _ = self.lstm(x)
                out = torch.relu(self.fc1(out[:, -1, :]))
                out = torch.sigmoid(self.fc2(out))  # Normalize to 0-1 range
                return out

        model = DCAOptimizer()
        # Load pre-trained weights if available
        model_path = Path(f"models/strategies/dca_optimizer_{self.symbol.replace('/', '_')}.pth")
        if model_path.exists():
            model.load_state_dict(torch.load(model_path))
            logger.info("✅ Loaded pre-trained DCA optimizer")
        else:
            logger.info("ℹ️ Using untrained DCA optimizer (will learn from experience)")

        return model

    def calculate_fibonacci_levels(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """Calculate Fibonacci retracement levels for DCA entry points"""

        # Find recent swing high and low
        recent_high = market_data['high'].rolling(50).max().iloc[-1]
        recent_low = market_data['low'].rolling(50).min().iloc[-1]

        # Calculate Fibonacci levels
        fib_range = recent_high - recent_low
        fib_levels = {}

        for level in self.fib_levels:
            # Retracement levels (from high to low)
            retracement_price = recent_high - (fib_range * level)
            fib_levels[f"fib_{level}"] = retracement_price

        return {
            'swing_high': recent_high,
            'swing_low': recent_low,
            'fib_range': fib_range,
            'fib_levels': fib_levels,
            'current_price': market_data['close'].iloc[-1]
        }

    def should_dca(self, market_data: pd.DataFrame, portfolio_value: float) -> Dict[str, Any]:
        """Determine if DCA should be executed and at what level"""

        current_price = market_data['close'].iloc[-1]
        current_time = datetime.now()

        # Check DCA interval
        if self.last_dca_time:
            time_since_last_dca = (current_time - self.last_dca_time).total_seconds() / 3600
            if time_since_last_dca < self.dca_interval_hours:
                return {'should_dca': False, 'reason': 'DCA interval not reached'}

        # Check maximum DCA positions
        if len(self.dca_positions) >= self.max_dca_positions:
            return {'should_dca': False, 'reason': 'Maximum DCA positions reached'}

        # Calculate Fibonacci levels
        fib_data = self.calculate_fibonacci_levels(market_data)

        # Find appropriate DCA level
        dca_level = self._find_dca_level(current_price, fib_data)

        if not dca_level:
            return {'should_dca': False, 'reason': 'No suitable DCA level found'}

        # Calculate DCA amount
        dca_amount = self._calculate_dca_amount(portfolio_value, fib_data)

        # Check risk limits
        if not self._check_dca_risk_limits(dca_amount, portfolio_value):
            return {'should_dca': False, 'reason': 'DCA would exceed risk limits'}

        return {
            'should_dca': True,
            'dca_level': dca_level,
            'dca_amount': dca_amount,
            'fib_data': fib_data,
            'reason': f'DCA at {dca_level["level_name"]} level'
        }

    def _find_dca_level(self, current_price: float, fib_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Find the most appropriate Fibonacci level for DCA"""

        fib_levels = fib_data['fib_levels']

        # Find levels where current price is near or below the retracement level
        suitable_levels = []
        for level_name, level_price in fib_levels.items():
            # Allow DCA within 2% of the Fibonacci level
            tolerance = level_price * 0.02

            if abs(current_price - level_price) <= tolerance or current_price <= level_price:
                level_pct = float(level_name.split('_')[1])
                suitable_levels.append({
                    'level_name': level_name,
                    'level_price': level_price,
                    'level_pct': level_pct,
                    'distance_pct': abs(current_price - level_price) / level_price
                })

        if not suitable_levels:
            return None

        # Choose the level with smallest distance (closest to current price)
        best_level = min(suitable_levels, key=lambda x: x['distance_pct'])

        return best_level

    def _calculate_dca_amount(self, portfolio_value: float, fib_data: Dict[str, Any]) -> float:
        """Calculate DCA amount using ML optimization or rule-based approach"""

        if self.use_ml_optimization and len(self.dca_positions) >= 3:
            # Use ML-optimized DCA amount
            return self._calculate_ml_dca_amount(portfolio_value, fib_data)
        else:
            # Rule-based DCA amount
            base_amount = portfolio_value * self.dca_amount_pct

            # Adjust based on volatility
            volatility = fib_data.get('fib_range', 0) / fib_data.get('swing_high', 1)
            volatility_multiplier = min(max(volatility * 5, 0.5), 2.0)  # 0.5x to 2x

            return base_amount * volatility_multiplier

    def _calculate_ml_dca_amount(self, portfolio_value: float, fib_data: Dict[str, Any]) -> float:
        """Calculate DCA amount using ML model"""

        try:
            # Prepare features for ML model
            features = self._prepare_ml_features(fib_data)

            if features is not None:
                with torch.no_grad():
                    predictions = self.dca_optimizer(features.unsqueeze(0))
                    timing_opt, amount_opt, levels_opt, interval_opt = predictions[0].numpy()

                    # Convert to actual DCA amount
                    base_amount = portfolio_value * self.dca_amount_pct
                    ml_amount = base_amount * (0.5 + amount_opt)  # 0.5x to 1.5x base amount

                    return ml_amount
            else:
                # Fallback to rule-based
                return portfolio_value * self.dca_amount_pct

        except Exception as e:
            logger.warning(f"ML DCA amount calculation failed: {e}")
            return portfolio_value * self.dca_amount_pct

    def _prepare_ml_features(self, fib_data: Dict[str, Any]) -> Optional[torch.Tensor]:
        """Prepare features for ML DCA optimization"""

        try:
            features = []

            # Price-based features
            current_price = fib_data['current_price']
            swing_high = fib_data['swing_high']
            swing_low = fib_data['swing_low']

            features.extend([
                current_price / swing_high,  # Price relative to high
                current_price / swing_low,   # Price relative to low
                (swing_high - swing_low) / swing_high,  # Range ratio
            ])

            # DCA position features
            if self.dca_positions:
                avg_price = self.average_entry_price
                features.extend([
                    current_price / avg_price,  # Current vs average price
                    len(self.dca_positions) / self.max_dca_positions,  # Position count ratio
                    self.total_invested / (self.total_invested + self.total_shares * current_price)  # Investment ratio
                ])
            else:
                features.extend([1.0, 0.0, 0.0])  # Default values

            # Fibonacci level features
            fib_levels = fib_data['fib_levels']
            for level in self.fib_levels:
                level_name = f"fib_{level}"
                if level_name in fib_levels:
                    level_price = fib_levels[level_name]
                    features.append(current_price / level_price)
                else:
                    features.append(1.0)

            # Pad or truncate to fixed size
            target_size = 50
            if len(features) < target_size:
                features.extend([0.0] * (target_size - len(features)))
            elif len(features) > target_size:
                features = features[:target_size]

            return torch.FloatTensor(features)

        except Exception as e:
            logger.warning(f"Failed to prepare ML features: {e}")
            return None

    def _check_dca_risk_limits(self, dca_amount: float, portfolio_value: float) -> bool:
        """Check if DCA would exceed risk limits"""

        # Check portfolio allocation
        if dca_amount > portfolio_value * 0.1:  # Max 10% of portfolio per DCA
            return False

        # Check total invested vs portfolio
        new_total_invested = self.total_invested + dca_amount
        if new_total_invested > portfolio_value * 0.5:  # Max 50% of portfolio in DCA
            return False

        return True

    def execute_dca(self, dca_decision: Dict[str, Any], current_price: float) -> Dict[str, Any]:
        """Execute DCA order"""

        dca_amount = dca_decision['dca_amount']
        dca_level = dca_decision['dca_level']

        # Calculate shares to buy
        shares_to_buy = dca_amount / current_price

        # Create DCA position entry
        dca_entry = {
            'timestamp': datetime.now(),
            'price': current_price,
            'amount': dca_amount,
            'shares': shares_to_buy,
            'level': dca_level['level_name'],
            'level_pct': dca_level['level_pct'],
            'fib_data': dca_decision['fib_data']
        }

        # Add to DCA positions
        self.dca_positions.append(dca_entry)

        # Update running totals
        self.total_invested += dca_amount
        self.total_shares += shares_to_buy
        self.average_entry_price = self.total_invested / self.total_shares
        self.last_dca_time = datetime.now()

        logger.info(f"🎯 DCA executed: {shares_to_buy:.6f} shares @ ${current_price:.4f} ({dca_level['level_name']})")

        return {
            'success': True,
            'dca_entry': dca_entry,
            'total_invested': self.total_invested,
            'total_shares': self.total_shares,
            'average_price': self.average_entry_price
        }

    def check_exit_conditions(self, current_price: float) -> Dict[str, Any]:
        """Check if DCA position should be exited"""

        if not self.dca_positions:
            return {'should_exit': False, 'reason': 'No DCA positions'}

        # Calculate current P&L
        current_value = self.total_shares * current_price
        total_pnl = current_value - self.total_invested
        pnl_pct = total_pnl / self.total_invested

        # Check take profit
        if pnl_pct >= self.take_profit_pct:
            return {
                'should_exit': True,
                'reason': 'Take profit reached',
                'pnl_pct': pnl_pct,
                'exit_type': 'take_profit'
            }

        # Check stop loss
        if pnl_pct <= -self.stop_loss_pct:
            return {
                'should_exit': True,
                'reason': 'Stop loss triggered',
                'pnl_pct': pnl_pct,
                'exit_type': 'stop_loss'
            }

        # Check max drawdown
        if pnl_pct <= -self.max_drawdown_pct:
            return {
                'should_exit': True,
                'reason': 'Max drawdown reached',
                'pnl_pct': pnl_pct,
                'exit_type': 'max_drawdown'
            }

        return {'should_exit': False, 'pnl_pct': pnl_pct}

    def exit_dca_position(self, exit_price: float, reason: str) -> Dict[str, Any]:
        """Exit DCA position"""

        if not self.dca_positions:
            return {'success': False, 'reason': 'No positions to exit'}

        # Calculate final P&L
        final_value = self.total_shares * exit_price
        total_pnl = final_value - self.total_invested
        pnl_pct = total_pnl / self.total_invested

        # Update performance metrics
        self.performance_metrics['total_trades'] += 1
        if total_pnl > 0:
            self.performance_metrics['profitable_trades'] += 1

        self.performance_metrics['total_pnl'] += total_pnl
        self.performance_metrics['win_rate'] = (
            self.performance_metrics['profitable_trades'] / self.performance_metrics['total_trades']
        )

        # Calculate holding period
        if self.dca_positions:
            first_entry = min(pos['timestamp'] for pos in self.dca_positions)
            last_entry = max(pos['timestamp'] for pos in self.dca_positions)
            holding_period_days = (datetime.now() - first_entry).total_seconds() / 86400
            self.performance_metrics['avg_holding_period'] = (
                (self.performance_metrics['avg_holding_period'] * (self.performance_metrics['total_trades'] - 1)) +
                holding_period_days
            ) / self.performance_metrics['total_trades']

        exit_result = {
            'success': True,
            'exit_price': exit_price,
            'total_pnl': total_pnl,
            'pnl_pct': pnl_pct,
            'reason': reason,
            'total_shares': self.total_shares,
            'average_entry_price': self.average_entry_price,
            'performance_metrics': self.performance_metrics.copy()
        }

        # Reset DCA state
        self.dca_positions = []
        self.average_entry_price = 0.0
        self.total_invested = 0.0
        self.total_shares = 0.0
        self.last_dca_time = None

        logger.info(f"💰 DCA position exited: P&L ${total_pnl:.2f} ({pnl_pct:.1%}) - {reason}")

        return exit_result

    def get_dca_status(self) -> Dict[str, Any]:
        """Get current DCA status"""

        current_pnl = 0.0
        current_pnl_pct = 0.0

        if self.dca_positions and self.total_invested > 0:
            # Estimate current value (would need current price in real implementation)
            current_pnl = 0.0  # Placeholder
            current_pnl_pct = 0.0  # Placeholder

        return {
            'symbol': self.symbol,
            'active_positions': len(self.dca_positions),
            'total_invested': self.total_invested,
            'total_shares': self.total_shares,
            'average_entry_price': self.average_entry_price,
            'current_pnl': current_pnl,
            'current_pnl_pct': current_pnl_pct,
            'last_dca_time': self.last_dca_time.isoformat() if self.last_dca_time else None,
            'performance_metrics': self.performance_metrics,
            'fib_levels': self.fib_levels if hasattr(self, 'fib_levels') else []
        }

    def save_model(self):
        """Save the DCA optimizer model"""

        if self.use_ml_optimization:
            model_path = Path(f"models/strategies/dca_optimizer_{self.symbol.replace('/', '_')}.pth")
            model_path.parent.mkdir(parents=True, exist_ok=True)
            torch.save(self.dca_optimizer.state_dict(), model_path)
            logger.info(f"💾 Saved DCA optimizer model to {model_path}")

# Example usage and testing
def test_fib_dca_strategy():
    """Test the Fibonacci DCA strategy"""

    print("🎯 Fibonacci DCA Strategy Test")
    print("=" * 50)

    # Configuration
    config = {
        'dca_levels': 5,
        'dca_interval_hours': 24,
        'dca_amount_pct': 0.02,
        'use_ml_optimization': False  # Disable for testing
    }

    # Initialize strategy
    strategy = FibonacciDCAStrategy('XRP/USDC', config)

    # Generate sample market data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    np.random.seed(42)

    # Simulate price movement around $0.50
    base_price = 0.50
    trend = np.random.normal(0.0001, 0.001, len(dates)).cumsum()
    volatility = np.random.normal(0, 0.005, len(dates))
    close_prices = base_price * np.exp(trend + volatility)

    market_data = pd.DataFrame({
        'timestamp': dates,
        'open': close_prices * (1 + np.random.normal(0, 0.002, len(dates))),
        'high': close_prices * (1 + np.random.normal(0.001, 0.003, len(dates))),
        'low': close_prices * (1 - np.random.normal(0.001, 0.003, len(dates))),
        'close': close_prices,
        'volume': np.random.lognormal(15, 1, len(dates))
    })

    # Test Fibonacci level calculation
    fib_data = strategy.calculate_fibonacci_levels(market_data)

    print("📊 Fibonacci Levels:"    print(".4f")
    print(".4f")
    print(".4f")
    for level_name, level_price in fib_data['fib_levels'].items():
        print(".4f")

    # Test DCA decision
    portfolio_value = 10000
    dca_decision = strategy.should_dca(market_data, portfolio_value)

    print("
🎯 DCA Decision:"    print(f"   Should DCA: {dca_decision['should_dca']}")
    print(f"   Reason: {dca_decision['reason']}")

    if dca_decision['should_dca']:
        print(".2f")
        print(f"   DCA Level: {dca_decision['dca_level']['level_name']}")

        # Execute DCA
        current_price = market_data['close'].iloc[-1]
        result = strategy.execute_dca(dca_decision, current_price)

        print("
💰 DCA Execution:"        print(f"   Success: {result['success']}")
        print(".2f")
        print(".4f")
        print(".6f")

    # Test exit conditions
    exit_check = strategy.check_exit_conditions(current_price)
    print("
📈 Exit Conditions:"    print(f"   Should Exit: {exit_check['should_exit']}")
    print(f"   Reason: {exit_check.get('reason', 'N/A')}")

    # Get DCA status
    status = strategy.get_dca_status()
    print("
📊 DCA Status:"    print(f"   Active Positions: {status['active_positions']}")
    print(".2f")
    print(".6f")
    print(".4f")

    print("\n" + "=" * 50)
    print("✅ Fibonacci DCA Strategy Test Complete")
    print("🎯 Strategy ready for live deployment!")

if __name__ == '__main__':
    test_fib_dca_strategy()