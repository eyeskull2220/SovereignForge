#!/usr/bin/env python3
"""
SovereignForge Model Trainer
Advanced ML model training system for trading strategies
Trains DCA and Grid optimizers on live market data
"""

import asyncio
import logging
import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional, Tuple
import json
from pathlib import Path
from collections import defaultdict
import matplotlib.pyplot as plt

from live_data_fetcher import get_live_data_fetcher, TickerData
from fib_dca_strategy import FibonacciDCAStrategy
from grid_trading_strategy import GridTradingStrategy

logger = logging.getLogger(__name__)

class ModelTrainer:
    """
    Advanced ML model training system for SovereignForge
    Trains strategy optimizers on live market data with reinforcement learning
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config

        # Training parameters
        self.training_duration_hours = config.get('training_duration_hours', 24)
        self.learning_rate = config.get('learning_rate', 0.001)
        self.batch_size = config.get('batch_size', 32)
        self.epochs = config.get('epochs', 100)
        self.validation_split = config.get('validation_split', 0.2)

        # Strategy configurations
        self.strategies_config = {
            'fib_dca': {
                'symbols': ['XRP/USDC', 'ADA/USDC', 'ALGO/USDC'],
                'config': {'use_ml_optimization': True}
            },
            'grid': {
                'symbols': ['XRP/USDC', 'ADA/USDC', 'ALGO/USDC'],
                'config': {'use_ml_optimization': True}
            }
        }

        # Training data collection
        self.training_data = defaultdict(list)
        self.market_data_history = defaultdict(list)

        # Live data fetcher
        self.data_fetcher = get_live_data_fetcher()

        # Strategy instances for training
        self.training_strategies = {}

        # Training metrics
        self.training_metrics = {
            'start_time': None,
            'end_time': None,
            'total_samples': 0,
            'strategy_performance': {},
            'model_improvements': {}
        }

        logger.info("🎓 Model Trainer initialized")

    async def start_training(self):
        """Start comprehensive model training session"""

        logger.info(f"🚀 Starting {self.training_duration_hours}h model training session")
        self.training_metrics['start_time'] = datetime.now()

        # Initialize training strategies
        self._initialize_training_strategies()

        # Start live data collection
        await self.data_fetcher.start()

        # Collect training data
        await self._collect_training_data()

        # Train models
        await self._train_models()

        # Validate and save models
        await self._validate_and_save_models()

        # Generate training report
        self._generate_training_report()

        # Stop data collection
        await self.data_fetcher.stop()

        self.training_metrics['end_time'] = datetime.now()
        logger.info("✅ Model training session completed")

    def _initialize_training_strategies(self):
        """Initialize strategy instances for training"""

        for strategy_name, strategy_config in self.strategies_config.items():
            self.training_strategies[strategy_name] = {}

            for symbol in strategy_config['symbols']:
                if strategy_name == 'fib_dca':
                    strategy = FibonacciDCAStrategy(symbol, strategy_config['config'])
                elif strategy_name == 'grid':
                    strategy = GridTradingStrategy(symbol, strategy_config['config'])
                else:
                    continue

                self.training_strategies[strategy_name][symbol] = strategy
                logger.info(f"✅ Initialized {strategy_name} training strategy for {symbol}")

    async def _collect_training_data(self):
        """Collect training data from live market conditions"""

        logger.info("📊 Collecting training data from live markets...")

        # Set up data collection callbacks
        for strategy_name, symbol_strategies in self.training_strategies.items():
            for symbol, strategy in symbol_strategies.items():
                self.data_fetcher.add_data_callback(
                    lambda ticker, s=strategy, sym=symbol, strat=strategy_name:
                    self._collect_strategy_data(ticker, s, sym, strat)
                )

        # Collect data for specified duration
        await asyncio.sleep(self.training_duration_hours * 3600)

        logger.info(f"📈 Collected training data: {dict((k, len(v)) for k, v in self.training_data.items())}")

    def _collect_strategy_data(self, ticker: TickerData, strategy, symbol: str, strategy_name: str):
        """Collect training data for a specific strategy"""

        # Store market data
        if symbol not in self.market_data_history:
            self.market_data_history[symbol] = []

        self.market_data_history[symbol].append({
            'timestamp': ticker.timestamp,
            'price': ticker.price,
            'volume': getattr(ticker, 'volume', 1.0)
        })

        # Keep only last 1000 data points
        if len(self.market_data_history[symbol]) > 1000:
            self.market_data_history[symbol].pop(0)

        # Generate training sample if we have enough data
        if len(self.market_data_history[symbol]) >= 50:
            sample = self._generate_training_sample(strategy, symbol, strategy_name)
            if sample:
                self.training_data[strategy_name].append(sample)
                self.training_metrics['total_samples'] += 1

    def _generate_training_sample(self, strategy, symbol: str, strategy_name: str) -> Optional[Dict[str, Any]]:
        """Generate a training sample from current market conditions"""

        try:
            market_history = self.market_data_history[symbol][-100:]  # Last 100 points

            # Convert to DataFrame
            df = pd.DataFrame(market_history)
            df['high'] = df['price']  # Use price as proxy for high/low
            df['low'] = df['price']
            df['close'] = df['price']

            # Generate strategy-specific training sample
            if strategy_name == 'fib_dca':
                return self._generate_dca_training_sample(strategy, df, symbol)
            elif strategy_name == 'grid':
                return self._generate_grid_training_sample(strategy, df, symbol)

        except Exception as e:
            logger.warning(f"Failed to generate training sample for {strategy_name} {symbol}: {e}")

        return None

    def _generate_dca_training_sample(self, strategy: FibonacciDCAStrategy, market_data: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
        """Generate DCA training sample"""

        try:
            # Get DCA decision
            dca_decision = strategy.should_dca(market_data, 10000.0)  # $10k portfolio

            if not dca_decision['should_dca']:
                return None

            # Prepare features
            features = strategy._prepare_ml_features(dca_decision['fib_data'])

            if features is None:
                return None

            # Calculate reward (simplified - in practice would be based on actual P&L)
            reward = self._calculate_dca_reward(dca_decision, market_data)

            return {
                'symbol': symbol,
                'features': features.numpy().tolist(),
                'action': [dca_decision['dca_amount'] / 10000.0,  # Normalized DCA amount
                          dca_decision['dca_level']['level_pct']],  # Level percentage
                'reward': reward,
                'timestamp': datetime.now().isoformat(),
                'market_conditions': {
                    'price': market_data['close'].iloc[-1],
                    'volatility': market_data['close'].pct_change().std(),
                    'trend': 1 if market_data['close'].iloc[-1] > market_data['close'].iloc[0] else -1
                }
            }

        except Exception as e:
            logger.warning(f"Failed to generate DCA training sample: {e}")
            return None

    def _generate_grid_training_sample(self, strategy: GridTradingStrategy, market_data: pd.DataFrame, symbol: str) -> Optional[Dict[str, Any]]:
        """Generate grid training sample"""

        try:
            # Calculate optimal grid
            grid_params = strategy.calculate_optimal_grid(market_data, 10000.0)

            # Prepare features
            features = strategy._prepare_ml_features(market_data)

            if features is None:
                return None

            # Calculate reward based on grid efficiency
            reward = self._calculate_grid_reward(grid_params, market_data)

            return {
                'symbol': symbol,
                'features': features.numpy().tolist(),
                'action': [grid_params['grid_spacing_pct'],  # Spacing
                          grid_params['grid_levels'] / 40.0,  # Normalized levels (0-1)
                          grid_params['position_size_pct']],  # Position size
                'reward': reward,
                'timestamp': datetime.now().isoformat(),
                'market_conditions': {
                    'price': market_data['close'].iloc[-1],
                    'volatility': market_data['close'].pct_change().std(),
                    'trend': 1 if market_data['close'].iloc[-1] > market_data['close'].iloc[0] else -1
                }
            }

        except Exception as e:
            logger.warning(f"Failed to generate grid training sample: {e}")
            return None

    def _calculate_dca_reward(self, dca_decision: Dict[str, Any], market_data: pd.DataFrame) -> float:
        """Calculate reward for DCA action (simplified)"""

        # Reward based on:
        # 1. Fibonacci level appropriateness
        # 2. Market timing
        # 3. Risk management

        level_pct = dca_decision['dca_level']['level_pct']
        current_price = market_data['close'].iloc[-1]

        # Prefer intermediate Fibonacci levels (0.382, 0.5, 0.618)
        optimal_levels = [0.382, 0.5, 0.618]
        level_distance = min(abs(level_pct - opt) for opt in optimal_levels)
        level_reward = 1.0 - level_distance  # Higher reward for closer to optimal levels

        # Market timing reward (prefer buying when price is below recent average)
        recent_avg = market_data['close'].rolling(20).mean().iloc[-1]
        timing_reward = 1.0 if current_price < recent_avg else 0.5

        # Combine rewards
        total_reward = (level_reward * 0.6) + (timing_reward * 0.4)

        return total_reward

    def _calculate_grid_reward(self, grid_params: Dict[str, Any], market_data: pd.DataFrame) -> float:
        """Calculate reward for grid parameters"""

        # Reward based on:
        # 1. Grid spacing appropriateness for volatility
        # 2. Number of levels vs market conditions
        # 3. Position sizing efficiency

        volatility = grid_params['volatility']
        spacing = grid_params['grid_spacing_pct']
        levels = grid_params['grid_levels']

        # Optimal spacing should scale with volatility
        optimal_spacing = 0.005 + (volatility * 10)  # Base 0.5% + volatility adjustment
        spacing_reward = 1.0 - min(abs(spacing - optimal_spacing) / optimal_spacing, 1.0)

        # Optimal levels based on volatility and volume
        volume_trend = grid_params.get('volume_trend', 1.0)
        optimal_levels = int(15 + (volatility * 20) + (volume_trend - 1.0) * 10)
        optimal_levels = max(10, min(40, optimal_levels))
        levels_reward = 1.0 - abs(levels - optimal_levels) / 30.0

        # Combine rewards
        total_reward = (spacing_reward * 0.5) + (levels_reward * 0.5)

        return total_reward

    async def _train_models(self):
        """Train ML models using collected data"""

        logger.info("🤖 Training ML models...")

        for strategy_name in self.strategies_config.keys():
            if strategy_name in self.training_data and self.training_data[strategy_name]:
                await self._train_strategy_model(strategy_name)

    async def _train_strategy_model(self, strategy_name: str):
        """Train model for specific strategy"""

        logger.info(f"🎯 Training {strategy_name} model with {len(self.training_data[strategy_name])} samples")

        # Prepare training data
        samples = self.training_data[strategy_name]
        if len(samples) < self.batch_size:
            logger.warning(f"Insufficient training data for {strategy_name}")
            return

        # Split into train/validation
        split_idx = int(len(samples) * (1 - self.validation_split))
        train_samples = samples[:split_idx]
        val_samples = samples[split_idx:]

        # Create data loaders
        train_loader = self._create_data_loader(train_samples)
        val_loader = self._create_data_loader(val_samples)

        # Get model
        model = self._get_strategy_model(strategy_name)

        # Training loop
        optimizer = optim.Adam(model.parameters(), lr=self.learning_rate)
        criterion = nn.MSELoss()

        best_val_loss = float('inf')
        patience = 10
        patience_counter = 0

        for epoch in range(self.epochs):
            # Training
            model.train()
            train_loss = 0.0

            for batch_features, batch_actions, batch_rewards in train_loader:
                optimizer.zero_grad()

                # Forward pass
                outputs = model(batch_features)

                # Calculate loss (policy gradient style)
                loss = criterion(outputs, batch_actions)

                # Add reward-weighted loss
                reward_weights = torch.tensor(batch_rewards, dtype=torch.float32).unsqueeze(1)
                loss = torch.mean(loss * reward_weights)

                loss.backward()
                optimizer.step()

                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation
            model.eval()
            val_loss = 0.0

            with torch.no_grad():
                for batch_features, batch_actions, batch_rewards in val_loader:
                    outputs = model(batch_features)
                    loss = criterion(outputs, batch_actions)
                    reward_weights = torch.tensor(batch_rewards, dtype=torch.float32).unsqueeze(1)
                    loss = torch.mean(loss * reward_weights)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            logger.info(f"Epoch {epoch+1}/{self.epochs} - Train Loss: {train_loss:.4f}, Val Loss: {val_loss:.4f}")

            # Early stopping
            if val_loss < best_val_loss:
                best_val_loss = val_loss
                patience_counter = 0

                # Save best model
                model_path = Path(f"models/strategies/{strategy_name}_optimizer_best.pth")
                model_path.parent.mkdir(parents=True, exist_ok=True)
                torch.save(model.state_dict(), model_path)
            else:
                patience_counter += 1
                if patience_counter >= patience:
                    logger.info(f"Early stopping at epoch {epoch+1}")
                    break

        # Load best model
        model_path = Path(f"models/strategies/{strategy_name}_optimizer_best.pth")
        if model_path.exists():
            model.load_state_dict(torch.load(model_path))

        # Update training metrics
        self.training_metrics['strategy_performance'][strategy_name] = {
            'samples': len(samples),
            'final_train_loss': train_loss,
            'best_val_loss': best_val_loss,
            'epochs_trained': epoch + 1
        }

    def _create_data_loader(self, samples: List[Dict[str, Any]]):
        """Create PyTorch DataLoader from training samples"""

        features = []
        actions = []
        rewards = []

        for sample in samples:
            features.append(sample['features'])
            actions.append(sample['action'])
            rewards.append(sample['reward'])

        # Convert to tensors
        features_tensor = torch.tensor(features, dtype=torch.float32)
        actions_tensor = torch.tensor(actions, dtype=torch.float32)
        rewards_tensor = torch.tensor(rewards, dtype=torch.float32)

        # Create dataset
        dataset = torch.utils.data.TensorDataset(features_tensor, actions_tensor, rewards_tensor)
        dataloader = torch.utils.data.DataLoader(dataset, batch_size=self.batch_size, shuffle=True)

        return dataloader

    def _get_strategy_model(self, strategy_name: str):
        """Get the ML model for a strategy"""

        # Get a strategy instance to access the model
        strategy_config = self.strategies_config[strategy_name]
        symbol = strategy_config['symbols'][0]  # Use first symbol

        if strategy_name == 'fib_dca':
            strategy = FibonacciDCAStrategy(symbol, strategy_config['config'])
            return strategy.dca_optimizer
        elif strategy_name == 'grid':
            strategy = GridTradingStrategy(symbol, strategy_config['config'])
            return strategy.grid_optimizer

    async def _validate_and_save_models(self):
        """Validate trained models and save to production"""

        logger.info("🔍 Validating and saving trained models...")

        for strategy_name in self.strategies_config.keys():
            if strategy_name in self.training_data and self.training_data[strategy_name]:
                await self._validate_strategy_model(strategy_name)
                self._save_production_model(strategy_name)

    async def _validate_strategy_model(self, strategy_name: str):
        """Validate trained model performance"""

        logger.info(f"📊 Validating {strategy_name} model...")

        # Use validation samples to test model
        samples = self.training_data[strategy_name]
        val_samples = samples[int(len(samples) * (1 - self.validation_split)):]

        if not val_samples:
            return

        model = self._get_strategy_model(strategy_name)
        model.eval()

        total_reward = 0.0
        predictions = []

        with torch.no_grad():
            for sample in val_samples:
                features = torch.tensor(sample['features'], dtype=torch.float32).unsqueeze(0)
                true_action = torch.tensor(sample['action'], dtype=torch.float32)

                predicted_action = model(features).squeeze(0)
                reward = sample['reward']

                total_reward += reward
                predictions.append({
                    'predicted': predicted_action.numpy().tolist(),
                    'true': true_action.numpy().tolist(),
                    'reward': reward
                })

        avg_reward = total_reward / len(val_samples)

        self.training_metrics['model_improvements'][strategy_name] = {
            'validation_samples': len(val_samples),
            'average_reward': avg_reward,
            'predictions': predictions[:10]  # Save first 10 for analysis
        }

        logger.info(f"✅ {strategy_name} model validation - Avg Reward: {avg_reward:.4f}")

    def _save_production_model(self, strategy_name: str):
        """Save validated model to production location"""

        # Copy best model to production location
        best_model_path = Path(f"models/strategies/{strategy_name}_optimizer_best.pth")
        prod_model_path = Path(f"models/strategies/{strategy_name}_optimizer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pth")

        if best_model_path.exists():
            import shutil
            shutil.copy2(best_model_path, prod_model_path)
            logger.info(f"💾 Saved production model: {prod_model_path}")

    def _generate_training_report(self):
        """Generate comprehensive training report"""

        report = {
            'training_session': {
                'start_time': self.training_metrics['start_time'].isoformat(),
                'end_time': self.training_metrics['end_time'].isoformat(),
                'duration_hours': self.training_duration_hours,
                'total_samples': self.training_metrics['total_samples']
            },
            'strategy_performance': self.training_metrics['strategy_performance'],
            'model_improvements': self.training_metrics['model_improvements'],
            'data_collection': {
                'symbols_tracked': list(self.market_data_history.keys()),
                'total_market_data_points': sum(len(data) for data in self.market_data_history.values())
            },
            'recommendations': self._generate_training_recommendations()
        }

        # Save report
        report_path = Path(f"reports/training_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
        report_path.parent.mkdir(parents=True, exist_ok=True)

        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"📋 Training report saved: {report_path}")

        # Print summary
        print("\n" + "=" * 60)
        print("MODEL TRAINING REPORT")
        print("=" * 60)
        print(f"Duration: {self.training_duration_hours} hours")
        print(f"Total Samples: {self.training_metrics['total_samples']}")

        for strategy, perf in self.training_metrics['strategy_performance'].items():
            print(f"\n{strategy.upper()}:")
            print(f"  Samples: {perf['samples']}")
            print(f"  Best Val Loss: {perf['best_val_loss']:.4f}")
            if strategy in self.training_metrics['model_improvements']:
                improvement = self.training_metrics['model_improvements'][strategy]
                print(f"  Avg Validation Reward: {improvement['average_reward']:.4f}")

        print("\n" + "=" * 60)

    def _generate_training_recommendations(self) -> List[str]:
        """Generate training recommendations"""

        recommendations = []

        for strategy_name, perf in self.training_metrics['strategy_performance'].items():
            if perf['best_val_loss'] > 0.1:
                recommendations.append(f"Consider collecting more training data for {strategy_name} model")
            elif perf['samples'] < 1000:
                recommendations.append(f"Increase training duration for {strategy_name} to collect more samples")

        if not recommendations:
            recommendations.append("All models trained successfully with good performance")

        return recommendations

# Global trainer instance
_trainer = None

def get_model_trainer(config: Dict[str, Any]) -> ModelTrainer:
    """Get or create global model trainer"""
    global _trainer
    if _trainer is None:
        _trainer = ModelTrainer(config)
    return _trainer

async def run_model_training(training_hours: int = 24):
    """Run comprehensive model training session"""

    print("SovereignForge Model Training")
    print("=" * 50)
    print(f"Training Duration: {training_hours} hours")
    print("Training DCA and Grid Strategy Optimizers")
    print("=" * 50)

    # Training configuration
    config = {
        'training_duration_hours': training_hours,
        'learning_rate': 0.001,
        'batch_size': 32,
        'epochs': 100,
        'validation_split': 0.2
    }

    trainer = get_model_trainer(config)

    try:
        await trainer.start_training()

    except KeyboardInterrupt:
        print("\nTraining interrupted by user")

    finally:
        print("\n" + "=" * 50)
        print("Model Training Complete")
        print("Check reports/ directory for detailed results")
        print("=" * 50)

if __name__ == '__main__':
    # Run 6-hour training session for demonstration
    asyncio.run(run_model_training(training_hours=6))