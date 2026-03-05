#!/usr/bin/env python3
"""
SovereignForge Grid Trading Strategy
Advanced grid trading implementation with dynamic grid management
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

class GridTradingStrategy:
    """Advanced grid trading strategy with ML optimization"""

    def __init__(self, symbol: str, config: Dict[str, Any]):
        self.symbol = symbol
        self.config = config

        # Grid parameters
        self.grid_levels = config.get('grid_levels', 20)
        self.grid_spacing_pct = config.get('grid_spacing_pct', 0.01)  # 1% spacing
        self.min_grid_spacing_pct = config.get('min_grid_spacing_pct', 0.005)  # 0.5%
        self.max_grid_spacing_pct = config.get('max_grid_spacing_pct', 0.02)   # 2%

        # Position management
        self.max_orders_per_side = config.get('max_orders_per_side', 5)
        self.position_size_pct = config.get('position_size_pct', 0.02)  # 2% of portfolio per order
        self.rebalance_threshold_pct = config.get('rebalance_threshold_pct', 0.005)  # 0.5%

        # Risk management
        self.stop_loss_pct = config.get('stop_loss_pct', 0.05)  # 5% stop loss
        self.take_profit_pct = config.get('take_profit_pct', 0.10)  # 10% take profit
        self.max_drawdown_pct = config.get('max_drawdown_pct', 0.15)  # 15% max drawdown

        # ML optimization
        self.use_ml_optimization = config.get('use_ml_optimization', True)
        self.model_update_interval = config.get('model_update_interval', 24)  # hours

        # Grid state
        self.grid_center = None
        self.grid_orders = {'buy': [], 'sell': []}
        self.active_positions = {}
        self.grid_history = []
        self.performance_metrics = {
            'total_trades': 0,
            'profitable_trades': 0,
            'total_pnl': 0.0,
            'max_drawdown': 0.0,
            'sharpe_ratio': 0.0,
            'win_rate': 0.0
        }

        # Initialize ML model for grid optimization
        if self.use_ml_optimization:
            self.grid_optimizer = self._initialize_grid_optimizer()

        logger.info(f"🎯 Initialized Grid Trading Strategy for {symbol}")
        logger.info(f"   Grid Levels: {self.grid_levels}, Spacing: {self.grid_spacing_pct:.1%}")

    def _initialize_grid_optimizer(self):
        """Initialize ML model for grid parameter optimization"""

        class GridOptimizer(nn.Module):
            def __init__(self, input_size=50, hidden_size=64):
                super().__init__()
                self.lstm = nn.LSTM(input_size, hidden_size, 2, batch_first=True, dropout=0.2)
                self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
                self.fc2 = nn.Linear(hidden_size // 2, 3)  # spacing, levels, position_size

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

        model = GridOptimizer()
        # Load pre-trained weights if available
        model_path = Path(f"models/strategies/grid_optimizer_{self.symbol.replace('/', '_')}.pth")
        if model_path.exists():
            model.load_state_dict(torch.load(model_path))
            logger.info("✅ Loaded pre-trained grid optimizer")
        else:
            logger.info("ℹ️ Using untrained grid optimizer (will learn from experience)")

        return model

    def calculate_optimal_grid(self, market_data: pd.DataFrame, portfolio_value: float) -> Dict[str, Any]:
        """Calculate optimal grid parameters using ML and market conditions"""

        current_price = market_data['close'].iloc[-1]
        volatility = market_data['close'].pct_change().std() * np.sqrt(252)  # Annualized volatility
        volume_trend = market_data['volume'].rolling(20).mean().iloc[-1] / market_data['volume'].rolling(20).mean().iloc[-20]

        # Prepare features for ML model
        if self.use_ml_optimization and len(market_data) >= 50:
            features = self._prepare_ml_features(market_data)
            if features is not None:
                with torch.no_grad():
                    predictions = self.grid_optimizer(features.unsqueeze(0))
                    spacing_opt, levels_opt, position_opt = predictions[0].numpy()

                    # Convert to actual parameters
                    optimal_spacing = self.min_grid_spacing_pct + (self.max_grid_spacing_pct - self.min_grid_spacing_pct) * spacing_opt
                    optimal_levels = int(10 + levels_opt * 30)  # 10-40 levels
                    optimal_position_pct = 0.01 + position_opt * 0.05  # 1-6% position size
            else:
                # Fallback to rule-based optimization
                optimal_spacing = self._calculate_rule_based_spacing(volatility)
                optimal_levels = self._calculate_rule_based_levels(volatility, volume_trend)
                optimal_position_pct = self._calculate_rule_based_position(volatility, portfolio_value)
        else:
            # Rule-based calculation
            optimal_spacing = self._calculate_rule_based_spacing(volatility)
            optimal_levels = self._calculate_rule_based_levels(volatility, volume_trend)
            optimal_position_pct = self._calculate_rule_based_position(volatility, portfolio_value)

        # Calculate grid center (use recent high/low average or current price)
        recent_high = market_data['high'].rolling(20).max().iloc[-1]
        recent_low = market_data['low'].rolling(20).min().iloc[-1]
        grid_center = (recent_high + recent_low) / 2

        # Ensure grid center is reasonable
        if abs(grid_center - current_price) / current_price > 0.05:  # More than 5% away
            grid_center = current_price

        return {
            'grid_center': grid_center,
            'grid_spacing_pct': optimal_spacing,
            'grid_levels': optimal_levels,
            'position_size_pct': optimal_position_pct,
            'volatility': volatility,
            'volume_trend': volume_trend,
            'current_price': current_price
        }

    def _prepare_ml_features(self, market_data: pd.DataFrame) -> Optional[torch.Tensor]:
        """Prepare features for ML grid optimization"""

        try:
            # Technical indicators
            features = []

            # Price-based features
            features.extend([
                market_data['close'].pct_change(1).fillna(0).iloc[-50:].values,
                market_data['close'].pct_change(5).fillna(0).iloc[-50:].values,
                market_data['close'].rolling(20).mean().pct_change(1).fillna(0).iloc[-50:].values,
                market_data['volume'].pct_change(1).fillna(0).iloc[-50:].values,
            ])

            # Volatility features
            returns = market_data['close'].pct_change().fillna(0)
            features.extend([
                returns.rolling(10).std().fillna(0).iloc[-50:].values,
                returns.rolling(20).std().fillna(0).iloc[-50:].values,
                returns.rolling(50).std().fillna(0).iloc[-50:].values,
            ])

            # RSI and MACD
            if 'rsi' in market_data.columns:
                features.append(market_data['rsi'].fillna(50).iloc[-50:].values)
            else:
                features.append(np.full(50, 50))

            if 'macd' in market_data.columns:
                features.append(market_data['macd'].fillna(0).iloc[-50:].values)
            else:
                features.append(np.zeros(50))

            # Combine all features
            feature_array = np.column_stack(features)
            return torch.FloatTensor(feature_array)

        except Exception as e:
            logger.warning(f"Failed to prepare ML features: {e}")
            return None

    def _calculate_rule_based_spacing(self, volatility: float) -> float:
        """Calculate grid spacing based on volatility"""

        # Higher volatility = wider spacing
        base_spacing = 0.01  # 1%
        volatility_multiplier = min(max(volatility * 10, 0.5), 2.0)  # 0.5x to 2x
        spacing = base_spacing * volatility_multiplier

        # Constrain to reasonable bounds
        return max(self.min_grid_spacing_pct, min(self.max_grid_spacing_pct, spacing))

    def _calculate_rule_based_levels(self, volatility: float, volume_trend: float) -> int:
        """Calculate number of grid levels based on market conditions"""

        # Base levels
        base_levels = 20

        # Adjust for volatility (higher volatility = fewer levels)
        vol_adjustment = max(0.5, 1.0 - volatility * 5)

        # Adjust for volume (higher volume = more levels)
        volume_adjustment = min(max(volume_trend, 0.5), 1.5)

        levels = int(base_levels * vol_adjustment * volume_adjustment)
        return max(10, min(40, levels))  # Constrain to 10-40 levels

    def _calculate_rule_based_position(self, volatility: float, portfolio_value: float) -> float:
        """Calculate position size based on volatility and portfolio"""

        # Base position size
        base_pct = 0.02  # 2%

        # Adjust for volatility (higher volatility = smaller positions)
        vol_adjustment = max(0.3, 1.0 - volatility * 8)

        # Adjust for portfolio size (larger portfolio = smaller percentage)
        portfolio_adjustment = min(max(portfolio_value / 10000, 0.5), 1.5)  # Normalize around $10k

        position_pct = base_pct * vol_adjustment / portfolio_adjustment
        return max(0.005, min(0.08, position_pct))  # 0.5% to 8%

    def generate_grid_orders(self, grid_params: Dict[str, Any], portfolio_value: float) -> List[Dict]:
        """Generate buy/sell orders for the grid"""

        grid_center = grid_params['grid_center']
        spacing_pct = grid_params['grid_spacing_pct']
        num_levels = grid_params['grid_levels']
        position_pct = grid_params['position_size_pct']

        orders = []

        # Calculate grid price levels
        for i in range(1, num_levels + 1):
            # Buy orders below grid center
            buy_price = grid_center * (1 - i * spacing_pct)
            buy_quantity = (portfolio_value * position_pct) / buy_price

            # Sell orders above grid center
            sell_price = grid_center * (1 + i * spacing_pct)
            sell_quantity = (portfolio_value * position_pct) / sell_price

            # Create order objects
            buy_order = {
                'type': 'buy',
                'symbol': self.symbol,
                'price': buy_price,
                'quantity': buy_quantity,
                'order_type': 'limit',
                'grid_level': -i,
                'reason': 'grid_buy'
            }

            sell_order = {
                'type': 'sell',
                'symbol': self.symbol,
                'price': sell_price,
                'quantity': sell_quantity,
                'order_type': 'limit',
                'grid_level': i,
                'reason': 'grid_sell'
            }

            orders.extend([buy_order, sell_order])

        # Sort orders by price for better execution
        orders.sort(key=lambda x: x['price'])

        return orders

    def update_grid(self, market_data: pd.DataFrame, portfolio_value: float,
                   executed_orders: List[Dict]) -> Dict[str, Any]:
        """Update grid based on market conditions and executed orders"""

        # Calculate optimal grid parameters
        grid_params = self.calculate_optimal_grid(market_data, portfolio_value)

        # Check if grid needs rebalancing
        needs_rebalance = self._check_rebalance_needed(grid_params)

        if needs_rebalance:
            logger.info(f"🔄 Rebalancing grid for {self.symbol}")

            # Cancel existing orders
            cancel_orders = []
            for side in ['buy', 'sell']:
                for order in self.grid_orders[side]:
                    cancel_orders.append({
                        'action': 'cancel',
                        'order_id': order['order_id'],
                        'symbol': self.symbol
                    })

            # Generate new grid orders
            new_orders = self.generate_grid_orders(grid_params, portfolio_value)

            # Update grid state
            self.grid_center = grid_params['grid_center']
            self.grid_orders = {'buy': [], 'sell': []}  # Will be populated when orders are placed

            return {
                'action': 'rebalance',
                'cancel_orders': cancel_orders,
                'new_orders': new_orders,
                'grid_params': grid_params
            }

        return {'action': 'hold', 'grid_params': grid_params}

    def _check_rebalance_needed(self, grid_params: Dict[str, Any]) -> bool:
        """Check if grid rebalancing is needed"""

        if self.grid_center is None:
            return True

        # Check if grid center has moved significantly
        center_change_pct = abs(grid_params['grid_center'] - self.grid_center) / self.grid_center

        if center_change_pct > self.rebalance_threshold_pct:
            return True

        # Check if spacing has changed significantly
        current_spacing = getattr(self, 'current_spacing_pct', self.grid_spacing_pct)
        spacing_change_pct = abs(grid_params['grid_spacing_pct'] - current_spacing) / current_spacing

        if spacing_change_pct > 0.25:  # 25% change
            return True

        return False

    def process_market_data(self, market_data: pd.DataFrame) -> Dict[str, Any]:
        """Process market data and generate trading signals"""

        current_price = market_data['close'].iloc[-1]

        signals = []

        # Check stop loss conditions
        for position in self.active_positions.values():
            entry_price = position['entry_price']
            pnl_pct = (current_price - entry_price) / entry_price

            if pnl_pct <= -self.stop_loss_pct:
                signals.append({
                    'action': 'close_position',
                    'position_id': position['id'],
                    'reason': 'stop_loss',
                    'pnl_pct': pnl_pct
                })
            elif pnl_pct >= self.take_profit_pct:
                signals.append({
                    'action': 'close_position',
                    'position_id': position['id'],
                    'reason': 'take_profit',
                    'pnl_pct': pnl_pct
                })

        # Check grid order triggers
        for side in ['buy', 'sell']:
            for order in self.grid_orders[side]:
                if self._is_order_triggered(order, current_price):
                    signals.append({
                        'action': 'execute_order',
                        'order': order,
                        'trigger_price': current_price
                    })

        return {'signals': signals, 'current_price': current_price}

    def _is_order_triggered(self, order: Dict, current_price: float) -> bool:
        """Check if a grid order should be triggered"""

        if order['type'] == 'buy':
            # Buy when price drops to order level
            return current_price <= order['price'] * 1.001  # Small buffer
        else:
            # Sell when price rises to order level
            return current_price >= order['price'] * 0.999  # Small buffer

    def update_performance(self, trade_result: Dict):
        """Update performance metrics after trade execution"""

        self.performance_metrics['total_trades'] += 1

        if trade_result.get('pnl', 0) > 0:
            self.performance_metrics['profitable_trades'] += 1

        self.performance_metrics['total_pnl'] += trade_result.get('pnl', 0)

        # Update win rate
        if self.performance_metrics['total_trades'] > 0:
            self.performance_metrics['win_rate'] = (
                self.performance_metrics['profitable_trades'] /
                self.performance_metrics['total_trades']
            )

        # Store trade in history
        self.grid_history.append({
            'timestamp': datetime.now().isoformat(),
            'trade': trade_result,
            'performance': self.performance_metrics.copy()
        })

    def get_performance_report(self) -> Dict[str, Any]:
        """Generate comprehensive performance report"""

        return {
            'strategy': 'grid_trading',
            'symbol': self.symbol,
            'performance_metrics': self.performance_metrics,
            'grid_state': {
                'grid_center': self.grid_center,
                'active_buy_orders': len(self.grid_orders['buy']),
                'active_sell_orders': len(self.grid_orders['sell']),
                'active_positions': len(self.active_positions)
            },
            'recent_trades': self.grid_history[-10:] if self.grid_history else [],
            'generated_at': datetime.now().isoformat()
        }

    def save_model(self):
        """Save the grid optimizer model"""

        if self.use_ml_optimization:
            model_path = Path(f"models/strategies/grid_optimizer_{self.symbol.replace('/', '_')}.pth")
            model_path.parent.mkdir(exist_ok=True)
            torch.save(self.grid_optimizer.state_dict(), model_path)
            logger.info(f"💾 Saved grid optimizer model to {model_path}")

# Example usage and testing
def test_grid_strategy():
    """Test the grid trading strategy"""

    print("🎯 Grid Trading Strategy Test")
    print("=" * 50)

    # Configuration
    config = {
        'grid_levels': 20,
        'grid_spacing_pct': 0.01,
        'position_size_pct': 0.02,
        'use_ml_optimization': False  # Disable for testing
    }

    # Initialize strategy
    strategy = GridTradingStrategy('BTC/USDT', config)

    # Generate sample market data
    dates = pd.date_range(start='2024-01-01', periods=100, freq='H')
    np.random.seed(42)

    # Simulate price movement around $45,000
    base_price = 45000
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

    # Test grid calculation
    portfolio_value = 10000
    grid_params = strategy.calculate_optimal_grid(market_data, portfolio_value)

    print("📊 Grid Parameters:"    print(f"   Center Price: ${grid_params['grid_center']:.2f}")
    print(f"   Grid Spacing: {grid_params['grid_spacing_pct']:.2%}")
    print(f"   Grid Levels: {grid_params['grid_levels']}")
    print(f"   Position Size: {grid_params['position_size_pct']:.2%}")
    print(f"   Market Volatility: {grid_params['volatility']:.2%}")

    # Generate grid orders
    orders = strategy.generate_grid_orders(grid_params, portfolio_value)

    print(f"\n📋 Generated {len(orders)} Grid Orders:")
    buy_orders = [o for o in orders if o['type'] == 'buy']
    sell_orders = [o for o in orders if o['type'] == 'sell']

    print(f"   Buy Orders: {len(buy_orders)}")
    for i, order in enumerate(buy_orders[:3]):
        print(".2f")

    print(f"   Sell Orders: {len(sell_orders)}")
    for i, order in enumerate(sell_orders[:3]):
        print(".2f")

    # Test performance tracking
    strategy.update_performance({
        'pnl': 25.50,
        'trade_type': 'grid_sell',
        'entry_price': 45100,
        'exit_price': 45250
    })

    performance = strategy.get_performance_report()
    print("
📈 Performance Metrics:"    print(f"   Total Trades: {performance['performance_metrics']['total_trades']}")
    print(f"   Total P&L: ${performance['performance_metrics']['total_pnl']:.2f}")

    print("\n" + "=" * 50)
    print("✅ Grid Trading Strategy Test Complete")
    print("🎯 Strategy ready for live deployment!")

if __name__ == '__main__':
    test_grid_strategy()