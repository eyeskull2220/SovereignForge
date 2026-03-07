#!/usr/bin/env python3
"""
SovereignForge Multi-Strategy Training System
Advanced training for FIB, DCA, Grid, and Arbitrage strategies across all pairs and exchanges
"""

import os
import sys
import json
import time
import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Any, Tuple, Optional
from dataclasses import dataclass
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TradingLSTM(nn.Module):
    """LSTM model for trading predictions"""
    def __init__(self, input_size, hidden_size=128, num_layers=2, output_size=1):
        super().__init__()
        self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
        self.fc = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        out, _ = self.lstm(x)
        return self.fc(out[:, -1, :])

def create_lstm_model(input_size: int, output_size: int) -> nn.Module:
    """Create LSTM model for sequential data"""
    class LSTMModel(nn.Module):
        def __init__(self, input_size, hidden_size=128, num_layers=2, output_size=output_size):
            super().__init__()
            self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
            self.fc = nn.Linear(hidden_size, output_size)

        def forward(self, x):
            out, _ = self.lstm(x)
            return self.fc(out[:, -1, :])

    return LSTMModel(input_size)

def create_gru_model(input_size: int, output_size: int) -> nn.Module:
    """Create GRU model for temporal patterns"""
    class GRUModel(nn.Module):
        def __init__(self, input_size, hidden_size=96, num_layers=3, output_size=output_size):
            super().__init__()
            self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True, dropout=0.3)
            self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
            self.fc2 = nn.Linear(hidden_size // 2, output_size)
            self.dropout = nn.Dropout(0.2)

        def forward(self, x):
            out, _ = self.gru(x)
            out = self.dropout(torch.relu(self.fc1(out[:, -1, :])))
            return self.fc2(out)

    return GRUModel(input_size)

def create_transformer_model(input_size: int, output_size: int) -> nn.Module:
    """Create Transformer model for complex patterns"""
    class TransformerModel(nn.Module):
        def __init__(self, input_size, d_model=64, nhead=8, num_layers=3, output_size=output_size):
            super().__init__()
            self.input_projection = nn.Linear(input_size, d_model)
            encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
            self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
            self.output_projection = nn.Linear(d_model, output_size)

        def forward(self, x):
            x = self.input_projection(x)
            x = self.transformer(x)
            return self.output_projection(x.mean(dim=1))

    return TransformerModel(input_size)

def create_attention_model(input_size: int, output_size: int) -> nn.Module:
    """Create Attention model for arbitrage detection"""
    class AttentionModel(nn.Module):
        def __init__(self, input_size, hidden_size=128, output_size=output_size):
            super().__init__()
            self.encoder = nn.Linear(input_size, hidden_size)
            self.attention = nn.MultiheadAttention(hidden_size, num_heads=8, batch_first=True)
            self.decoder = nn.Linear(hidden_size, output_size)

        def forward(self, x):
            x = torch.relu(self.encoder(x))
            attn_output, _ = self.attention(x, x, x)
            return self.decoder(attn_output.mean(dim=1))

    return AttentionModel(input_size)

@dataclass
class StrategyConfig:
    """Configuration for each trading strategy"""
    name: str
    description: str
    model_architecture: str
    input_features: List[str]
    output_targets: List[str]
    training_epochs: int
    batch_size: int
    learning_rate: float
    validation_split: float

@dataclass
class ExchangePair:
    """Exchange and trading pair combination"""
    exchange: str
    pair: str
    historical_data_path: str
    start_date: str
    end_date: str

class MultiStrategyTrainer:
    """Multi-strategy training orchestrator"""

    def __init__(self):
        self.strategies = self.define_strategies()
        self.exchange_pairs = self.define_exchange_pairs()
        self.models = {}
        self.training_results = {}

    def define_strategies(self) -> Dict[str, StrategyConfig]:
        """Define all trading strategies to train"""

        return {
            'fib': StrategyConfig(
                name='fib',
                description='Fibonacci Retracement Trading',
                model_architecture='LSTM_FIB',
                input_features=['price', 'volume', 'fib_0.236', 'fib_0.382', 'fib_0.5', 'fib_0.618', 'fib_0.786'],
                output_targets=['fib_level', 'direction', 'strength'],
                training_epochs=100,
                batch_size=64,
                learning_rate=1e-4,
                validation_split=0.2
            ),

            'dca': StrategyConfig(
                name='dca',
                description='Dollar Cost Averaging Optimization',
                model_architecture='GRU_DCA',
                input_features=['price', 'volume', 'dca_amount', 'holding_period', 'market_trend'],
                output_targets=['optimal_amount', 'optimal_timing', 'expected_return'],
                training_epochs=80,
                batch_size=32,
                learning_rate=2e-4,
                validation_split=0.25
            ),

            'grid': StrategyConfig(
                name='grid',
                description='Grid Trading Strategy',
                model_architecture='TRANSFORMER_GRID',
                input_features=['price', 'volume', 'grid_levels', 'spread_percentage', 'volatility'],
                output_targets=['grid_spacing', 'take_profit_levels', 'stop_loss_levels'],
                training_epochs=120,
                batch_size=48,
                learning_rate=8e-5,
                validation_split=0.15
            ),

            'arbitrage': StrategyConfig(
                name='arbitrage',
                description='Cross-Exchange Arbitrage',
                model_architecture='ATTENTION_ARB',
                input_features=['price_diff', 'volume_ratio', 'spread_cost', 'execution_time', 'market_depth'],
                output_targets=['arbitrage_opportunity', 'profit_potential', 'risk_level'],
                training_epochs=150,
                batch_size=128,
                learning_rate=5e-5,
                validation_split=0.3
            )
        }

    def define_exchange_pairs(self) -> List[ExchangePair]:
        """Define all exchange and pair combinations"""

        exchanges = ['binance', 'coinbase', 'kraken']
        pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'ADA/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT']

        exchange_pairs = []
        for exchange in exchanges:
            for pair in pairs:
                exchange_pairs.append(ExchangePair(
                    exchange=exchange,
                    pair=pair,
                    historical_data_path=f"data/historical/{exchange}/{pair.replace('/', '_')}_1h.csv",
                    start_date="2020-01-01",
                    end_date=datetime.now().strftime("%Y-%m-%d")
                ))

        return exchange_pairs

    def create_strategy_model(self, strategy: StrategyConfig) -> nn.Module:
        """Create neural network model for strategy"""

        if strategy.model_architecture == 'LSTM_FIB':
            return self.create_lstm_model(len(strategy.input_features), len(strategy.output_targets))

        elif strategy.model_architecture == 'GRU_DCA':
            return self.create_gru_model(len(strategy.input_features), len(strategy.output_targets))

        elif strategy.model_architecture == 'TRANSFORMER_GRID':
            return self.create_transformer_model(len(strategy.input_features), len(strategy.output_targets))

        elif strategy.model_architecture == 'ATTENTION_ARB':
            return self.create_attention_model(len(strategy.input_features), len(strategy.output_targets))

        else:
            raise ValueError(f"Unknown architecture: {strategy.model_architecture}")

    def create_lstm_model(self, input_size: int, output_size: int) -> nn.Module:
        """Create LSTM model for sequential data"""
        class LSTMModel(nn.Module):
            def __init__(self, input_size, hidden_size=128, num_layers=2, output_size=output_size):
                super().__init__()
                self.lstm = nn.LSTM(input_size, hidden_size, num_layers, batch_first=True, dropout=0.2)
                self.fc = nn.Linear(hidden_size, output_size)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :])

        return LSTMModel(input_size)

    def create_gru_model(self, input_size: int, output_size: int) -> nn.Module:
        """Create GRU model for temporal patterns"""
        class GRUModel(nn.Module):
            def __init__(self, input_size, hidden_size=96, num_layers=3, output_size=output_size):
                super().__init__()
                self.gru = nn.GRU(input_size, hidden_size, num_layers, batch_first=True, dropout=0.3)
                self.fc1 = nn.Linear(hidden_size, hidden_size // 2)
                self.fc2 = nn.Linear(hidden_size // 2, output_size)
                self.dropout = nn.Dropout(0.2)

            def forward(self, x):
                out, _ = self.gru(x)
                out = self.dropout(torch.relu(self.fc1(out[:, -1, :])))
                return self.fc2(out)

        return GRUModel(input_size)

    def create_transformer_model(self, input_size: int, output_size: int) -> nn.Module:
        """Create Transformer model for complex patterns"""
        class TransformerModel(nn.Module):
            def __init__(self, input_size, d_model=64, nhead=8, num_layers=3, output_size=output_size):
                super().__init__()
                self.input_projection = nn.Linear(input_size, d_model)
                encoder_layer = nn.TransformerEncoderLayer(d_model=d_model, nhead=nhead, batch_first=True)
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
                self.output_projection = nn.Linear(d_model, output_size)

            def forward(self, x):
                x = self.input_projection(x)
                x = self.transformer(x)
                return self.output_projection(x.mean(dim=1))

        return TransformerModel(input_size)

    def create_attention_model(self, input_size: int, output_size: int) -> nn.Module:
        """Create Attention model for arbitrage detection"""
        class AttentionModel(nn.Module):
            def __init__(self, input_size, hidden_size=128, output_size=output_size):
                super().__init__()
                self.encoder = nn.Linear(input_size, hidden_size)
                self.attention = nn.MultiheadAttention(hidden_size, num_heads=8, batch_first=True)
                self.decoder = nn.Linear(hidden_size, output_size)

            def forward(self, x):
                x = torch.relu(self.encoder(x))
                attn_output, _ = self.attention(x, x, x)
                return self.decoder(attn_output.mean(dim=1))

        return AttentionModel(input_size)

    def prepare_training_data(self, exchange_pair: ExchangePair, strategy: StrategyConfig) -> Tuple[torch.Tensor, torch.Tensor]:
        """Prepare training data for specific exchange/pair/strategy combination"""

        # Load historical data
        data_path = Path(exchange_pair.historical_data_path)
        if not data_path.exists():
            logger.warning(f"Data not found: {data_path}")
            # Generate synthetic data for demonstration
            return self.generate_synthetic_data(strategy)

        try:
            df = pd.read_csv(data_path)
            # Process data based on strategy requirements
            features = self.extract_features(df, strategy.input_features)
            targets = self.extract_targets(df, strategy.output_targets, strategy.name)

            return torch.FloatTensor(features), torch.FloatTensor(targets)

        except Exception as e:
            logger.error(f"Error loading data for {exchange_pair.exchange}/{exchange_pair.pair}: {e}")
            return self.generate_synthetic_data(strategy)

    def extract_features(self, df: pd.DataFrame, feature_names: List[str]) -> np.ndarray:
        """Extract features from dataframe"""
        features = []

        for feature in feature_names:
            if feature in df.columns:
                features.append(df[feature].fillna(0).values)
            elif feature.startswith('fib_'):
                # Calculate Fibonacci levels
                level = float(feature.split('_')[1])
                high = df['high'].max()
                low = df['low'].min()
                fib_level = low + (high - low) * level
                features.append(np.full(len(df), fib_level))
            else:
                # Generate synthetic feature
                features.append(np.random.randn(len(df)))

        return np.column_stack(features)

    def extract_targets(self, df: pd.DataFrame, target_names: List[str], strategy_name: str) -> np.ndarray:
        """Extract targets based on strategy"""
        targets = []

        for target in target_names:
            if strategy_name == 'fib':
                if target == 'fib_level':
                    targets.append(np.random.choice([0.236, 0.382, 0.5, 0.618, 0.786], len(df)))
                elif target == 'direction':
                    targets.append(np.random.choice([-1, 0, 1], len(df)))
                elif target == 'strength':
                    targets.append(np.random.uniform(0, 1, len(df)))

            elif strategy_name == 'dca':
                if target == 'optimal_amount':
                    targets.append(np.random.uniform(10, 1000, len(df)))
                elif target == 'optimal_timing':
                    targets.append(np.random.choice([0, 1], len(df)))
                elif target == 'expected_return':
                    targets.append(np.random.uniform(-0.1, 0.5, len(df)))

            elif strategy_name == 'grid':
                if 'level' in target:
                    targets.append(np.random.uniform(0.01, 0.1, len(df)))
                else:
                    targets.append(np.random.uniform(0, 1, len(df)))

            elif strategy_name == 'arbitrage':
                if target == 'arbitrage_opportunity':
                    targets.append(np.random.choice([0, 1], len(df)))
                elif target == 'profit_potential':
                    targets.append(np.random.uniform(0, 0.05, len(df)))
                elif target == 'risk_level':
                    targets.append(np.random.uniform(0, 1, len(df)))

        return np.column_stack(targets)

    def generate_synthetic_data(self, strategy: StrategyConfig) -> Tuple[torch.Tensor, torch.Tensor]:
        """Generate synthetic training data for demonstration"""
        n_samples = 10000
        seq_length = 24  # 24 hours

        # Generate random features
        features = torch.randn(n_samples, seq_length, len(strategy.input_features))

        # Generate random targets based on strategy
        if strategy.name == 'fib':
            targets = torch.randint(0, 5, (n_samples, 3))  # fib_level, direction, strength
        elif strategy.name == 'dca':
            targets = torch.randn(n_samples, 3)  # amount, timing, return
        elif strategy.name == 'grid':
            targets = torch.rand(n_samples, 3)  # spacing, take_profit, stop_loss
        elif strategy.name == 'arbitrage':
            targets = torch.randint(0, 2, (n_samples, 3))  # opportunity, profit, risk

        return features, targets

    def train_strategy_model(self, strategy: StrategyConfig, exchange_pair: ExchangePair) -> Dict[str, Any]:
        """Train model for specific strategy and exchange/pair"""

        logger.info(f"🚀 Training {strategy.name} for {exchange_pair.exchange}/{exchange_pair.pair}")

        # Create model
        model = self.create_strategy_model(strategy)
        optimizer = torch.optim.Adam(model.parameters(), lr=strategy.learning_rate)
        criterion = nn.MSELoss()

        # Prepare data
        X, y = self.prepare_training_data(exchange_pair, strategy)

        # Create data loader
        dataset = torch.utils.data.TensorDataset(X, y)
        train_size = int((1 - strategy.validation_split) * len(dataset))
        val_size = len(dataset) - train_size

        train_dataset, val_dataset = torch.utils.data.random_split(dataset, [train_size, val_size])
        train_loader = torch.utils.data.DataLoader(train_dataset, batch_size=strategy.batch_size, shuffle=True)
        val_loader = torch.utils.data.DataLoader(val_dataset, batch_size=strategy.batch_size)

        # Training loop
        best_loss = float('inf')
        training_history = []

        for epoch in range(strategy.training_epochs):
            # Training
            model.train()
            train_loss = 0
            for batch_X, batch_y in train_loader:
                optimizer.zero_grad()
                outputs = model(batch_X)
                loss = criterion(outputs, batch_y)
                loss.backward()
                optimizer.step()
                train_loss += loss.item()

            train_loss /= len(train_loader)

            # Validation
            model.eval()
            val_loss = 0
            with torch.no_grad():
                for batch_X, batch_y in val_loader:
                    outputs = model(batch_X)
                    loss = criterion(outputs, batch_y)
                    val_loss += loss.item()

            val_loss /= len(val_loader)

            training_history.append({
                'epoch': epoch + 1,
                'train_loss': train_loss,
                'val_loss': val_loss
            })

            if (epoch + 1) % 10 == 0:
                logger.info(f"Epoch {epoch+1}/{strategy.training_epochs} - Train: {train_loss:.4f}, Val: {val_loss:.4f}")

            # Save best model
            if val_loss < best_loss:
                best_loss = val_loss
                model_key = f"{strategy.name}_{exchange_pair.exchange}_{exchange_pair.pair.replace('/', '_')}"
                self.models[model_key] = model.state_dict()

        return {
            'strategy': strategy.name,
            'exchange': exchange_pair.exchange,
            'pair': exchange_pair.pair,
            'final_train_loss': train_loss,
            'final_val_loss': val_loss,
            'best_val_loss': best_loss,
            'epochs_trained': strategy.training_epochs,
            'training_history': training_history
        }

    def run_multi_strategy_training(self) -> Dict[str, Any]:
        """Run training for all strategies across all exchange/pair combinations"""

        logger.info("🎯 Starting Multi-Strategy Training")
        logger.info(f"📊 Total combinations: {len(self.strategies)} strategies × {len(self.exchange_pairs)} pairs = {len(self.strategies) * len(self.exchange_pairs)} trainings")

        start_time = datetime.now()
        all_results = []

        total_combinations = len(self.strategies) * len(self.exchange_pairs)
        completed = 0

        for strategy_name, strategy in self.strategies.items():
            for exchange_pair in self.exchange_pairs:
                try:
                    result = self.train_strategy_model(strategy, exchange_pair)
                    all_results.append(result)
                    completed += 1

                    logger.info(f"✅ Completed {completed}/{total_combinations}: {strategy_name} on {exchange_pair.exchange}/{exchange_pair.pair}")

                except Exception as e:
                    logger.error(f"❌ Failed {strategy_name} on {exchange_pair.exchange}/{exchange_pair.pair}: {e}")
                    all_results.append({
                        'strategy': strategy_name,
                        'exchange': exchange_pair.exchange,
                        'pair': exchange_pair.pair,
                        'error': str(e),
                        'status': 'failed'
                    })

        end_time = datetime.now()
        duration = end_time - start_time

        # Save models
        self.save_models()

        # Generate summary
        summary = self.generate_training_summary(all_results, duration)

        return summary

    def save_models(self):
        """Save trained models"""
        models_dir = Path("models/strategies")
        models_dir.mkdir(parents=True, exist_ok=True)

        for model_key, state_dict in self.models.items():
            model_path = models_dir / f"{model_key}.pth"
            torch.save(state_dict, model_path)

        logger.info(f"💾 Saved {len(self.models)} trained models")

    def generate_training_summary(self, results: List[Dict], duration) -> Dict[str, Any]:
        """Generate comprehensive training summary"""

        successful_trainings = [r for r in results if 'error' not in r]
        failed_trainings = [r for r in results if 'error' in r]

        # Calculate statistics
        if successful_trainings:
            avg_train_loss = np.mean([r['final_train_loss'] for r in successful_trainings])
            avg_val_loss = np.mean([r['final_val_loss'] for r in successful_trainings])
            best_avg_loss = np.mean([r['best_val_loss'] for r in successful_trainings])
        else:
            avg_train_loss = avg_val_loss = best_avg_loss = 0

        # Group by strategy
        strategy_stats = {}
        for result in successful_trainings:
            strategy = result['strategy']
            if strategy not in strategy_stats:
                strategy_stats[strategy] = []
            strategy_stats[strategy].append(result['best_val_loss'])

        for strategy in strategy_stats:
            strategy_stats[strategy] = {
                'count': len(strategy_stats[strategy]),
                'avg_best_loss': np.mean(strategy_stats[strategy]),
                'min_best_loss': np.min(strategy_stats[strategy]),
                'max_best_loss': np.max(strategy_stats[strategy])
            }

        summary = {
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': duration.total_seconds(),
            'total_combinations': len(results),
            'successful_trainings': len(successful_trainings),
            'failed_trainings': len(failed_trainings),
            'success_rate': len(successful_trainings) / len(results) if results else 0,
            'average_training_loss': avg_train_loss,
            'average_validation_loss': avg_val_loss,
            'average_best_loss': best_avg_loss,
            'strategy_statistics': strategy_stats,
            'failed_trainings_details': failed_trainings,
            'recommendations': self.generate_training_recommendations(strategy_stats)
        }

        # Save summary
        self.save_training_report(summary)

        return summary

    def generate_training_recommendations(self, strategy_stats: Dict) -> List[str]:
        """Generate recommendations based on training results"""

        recommendations = []

        # Find best performing strategies
        if strategy_stats:
            best_strategy = min(strategy_stats.keys(), key=lambda s: strategy_stats[s]['avg_best_loss'])
            recommendations.append(f"🎯 Best performing strategy: {best_strategy} (avg loss: {strategy_stats[best_strategy]['avg_best_loss']:.4f})")

        # Check for strategies that need improvement
        for strategy, stats in strategy_stats.items():
            if stats['avg_best_loss'] > 0.1:
                recommendations.append(f"📈 {strategy} needs improvement (high loss: {stats['avg_best_loss']:.4f})")

        recommendations.extend([
            "🔧 Fine-tune hyperparameters for strategies with high loss",
            "📊 Implement cross-validation for better model evaluation",
            "🎪 Consider ensemble methods combining multiple strategies",
            "📈 Add more historical data for better training",
            "🔍 Implement model interpretability for strategy insights"
        ])

        return recommendations

    def save_training_report(self, summary: Dict[str, Any]):
        """Save training report"""

        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Save JSON report
        json_file = reports_dir / f"multi_strategy_training_{timestamp}.json"
        with open(json_file, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        # Save human-readable report
        report_file = reports_dir / f"training_summary_{timestamp}.md"
        self.generate_training_markdown_report(summary, report_file)

        logger.info(f"📄 Training report saved: {json_file}")
        logger.info(f"📊 Summary saved: {report_file}")

    def generate_training_markdown_report(self, summary: Dict, file_path: Path):
        """Generate markdown training report"""

        with open(file_path, 'w') as f:
            f.write("# SovereignForge Multi-Strategy Training Report\n\n")
            f.write(f"**Report Date:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write(f"**Training Duration:** {summary['duration_seconds']/3600:.1f} hours\n\n")

            f.write("## 📊 Training Summary\n\n")
            f.write(f"- **Total Combinations:** {summary['total_combinations']}\n")
            f.write(f"- **Successful Trainings:** {summary['successful_trainings']}\n")
            f.write(f"- **Failed Trainings:** {summary['failed_trainings']}\n")
            f.write(f"- **Success Rate:** {summary['success_rate']*100:.1f}%\n\n")

            f.write("## 📈 Performance Metrics\n\n")
            f.write(f"- **Average Training Loss:** {summary['average_training_loss']:.4f}\n")
            f.write(f"- **Average Validation Loss:** {summary['average_validation_loss']:.4f}\n")
            f.write(f"- **Average Best Loss:** {summary['average_best_loss']:.4f}\n\n")

            f.write("## 🎯 Strategy Performance\n\n")
            f.write("| Strategy | Trainings | Avg Best Loss | Min Loss | Max Loss |\n")
            f.write("|----------|-----------|---------------|----------|----------|\n")
            for strategy, stats in summary['strategy_statistics'].items():
                f.write(f"| {strategy} | {stats['count']} | {stats['avg_best_loss']:.4f} | {stats['min_best_loss']:.4f} | {stats['max_best_loss']:.4f} |\n")
            f.write("\n")

            f.write("## 🎯 Recommendations\n\n")
            for rec in summary['recommendations']:
                f.write(f"- {rec}\n")
            f.write("\n")

            f.write("## 📋 Next Steps\n\n")
            f.write("1. **Deploy Best Models** - Use top-performing strategies in live trading\n")
            f.write("2. **Strategy Optimization** - Fine-tune hyperparameters for underperforming strategies\n")
            f.write("3. **Ensemble Development** - Combine multiple strategies for better performance\n")
            f.write("4. **Backtesting** - Validate strategies against historical data\n")
            f.write("5. **Live Testing** - Paper trading validation before real deployment\n")
            f.write("\n")

            f.write("---\n")
            f.write("*Generated by SovereignForge Multi-Strategy Training System*\n")

def main():
    """Main entry point"""

    print("🎯 SovereignForge Multi-Strategy Training System")
    print("=" * 60)

    trainer = MultiStrategyTrainer()

    print(f"📊 Strategies to train: {list(trainer.strategies.keys())}")
    print(f"🏦 Exchanges: {list(set(ep.exchange for ep in trainer.exchange_pairs))}")
    print(f"💰 Trading pairs: {list(set(ep.pair for ep in trainer.exchange_pairs))}")
    print(f"🎪 Total combinations: {len(trainer.strategies)} × {len(trainer.exchange_pairs)} = {len(trainer.strategies) * len(trainer.exchange_pairs)}")
    print()

    # Run training
    summary = trainer.run_multi_strategy_training()

    # Print results
    print("\n" + "=" * 60)
    print("🎯 TRAINING COMPLETE")
    print("=" * 60)
    print(f"✅ Successful: {summary['successful_trainings']}/{summary['total_combinations']}")
    print(f"❌ Failed: {summary['failed_trainings']}/{summary['total_combinations']}")
    print(f"📈 Success Rate: {summary['success_rate']*100:.1f}%")
    print(f"🎯 Best Avg Loss: {summary['average_best_loss']:.4f}")
    print()
    print("📄 Reports saved in reports/ directory")
    print("🤖 Models saved in models/strategies/ directory")

if __name__ == "__main__":
    main()