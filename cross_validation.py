#!/usr/bin/env python3
"""
SovereignForge Cross-Validation Framework
Comprehensive model validation and performance assessment
"""

import torch
import torch.nn as nn
import numpy as np
import pandas as pd
from sklearn.model_selection import KFold, TimeSeriesSplit
from sklearn.metrics import mean_squared_error, mean_absolute_error, r2_score
import json
from pathlib import Path
from datetime import datetime
import logging
from typing import Dict, List, Any, Tuple, Optional
import matplotlib.pyplot as plt
import seaborn as sns

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class CrossValidator:
    """Cross-validation framework for trading models"""

    def __init__(self, n_splits: int = 5, time_series: bool = True):
        self.n_splits = n_splits
        self.time_series = time_series
        self.cv_results = {}

        if time_series:
            self.cv = TimeSeriesSplit(n_splits=n_splits)
        else:
            self.cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)

    def validate_model(self, model_factory, X: torch.Tensor, y: torch.Tensor,
                      strategy_name: str, epochs: int = 50) -> Dict[str, Any]:
        """Perform cross-validation on a model"""

        logger.info(f"🔬 Starting {self.n_splits}-fold cross-validation for {strategy_name}")

        fold_results = []
        fold_predictions = []
        fold_actuals = []

        for fold, (train_idx, val_idx) in enumerate(self.cv.split(X)):
            logger.info(f"📊 Fold {fold + 1}/{self.n_splits}")

            # Split data
            X_train, X_val = X[train_idx], X[val_idx]
            y_train, y_val = y[train_idx], y[val_idx]

            # Create model
            model = model_factory()

            # Train model
            model, training_history = self._train_fold_model(model, X_train, y_train, epochs)

            # Evaluate
            model.eval()
            with torch.no_grad():
                predictions = model(X_val)
                predictions = predictions.numpy()
                actuals = y_val.numpy()

            # Calculate metrics
            mse = mean_squared_error(actuals, predictions)
            mae = mean_absolute_error(actuals, predictions)
            r2 = r2_score(actuals, predictions)

            fold_result = {
                'fold': fold + 1,
                'mse': mse,
                'mae': mae,
                'r2': r2,
                'training_history': training_history,
                'n_train_samples': len(train_idx),
                'n_val_samples': len(val_idx)
            }

            fold_results.append(fold_result)
            fold_predictions.extend(predictions.flatten())
            fold_actuals.extend(actuals.flatten())

        # Aggregate results
        cv_summary = self._calculate_cv_summary(fold_results, fold_predictions, fold_actuals, strategy_name)

        self.cv_results[strategy_name] = cv_summary

        return cv_summary

    def _train_fold_model(self, model, X_train, y_train, epochs):
        """Train model for one fold"""
        optimizer = torch.optim.Adam(model.parameters(), lr=1e-3)
        criterion = nn.MSELoss()
        training_history = []

        for epoch in range(epochs):
            model.train()
            optimizer.zero_grad()

            outputs = model(X_train)
            loss = criterion(outputs, y_train)
            loss.backward()
            optimizer.step()

            training_history.append({
                'epoch': epoch + 1,
                'loss': loss.item()
            })

        return model, training_history

    def _calculate_cv_summary(self, fold_results, predictions, actuals, strategy_name):
        """Calculate cross-validation summary statistics"""

        # Extract metrics
        mses = [r['mse'] for r in fold_results]
        maes = [r['mae'] for r in fold_results]
        r2s = [r['r2'] for r in fold_results]

        # Overall metrics
        overall_mse = mean_squared_error(actuals, predictions)
        overall_mae = mean_absolute_error(actuals, predictions)
        overall_r2 = r2_score(actuals, predictions)

        summary = {
            'strategy': strategy_name,
            'n_folds': self.n_splits,
            'fold_results': fold_results,
            'summary_stats': {
                'mse': {
                    'mean': np.mean(mses),
                    'std': np.std(mses),
                    'min': np.min(mses),
                    'max': np.max(mses)
                },
                'mae': {
                    'mean': np.mean(maes),
                    'std': np.std(maes),
                    'min': np.min(maes),
                    'max': np.max(maes)
                },
                'r2': {
                    'mean': np.mean(r2s),
                    'std': np.std(r2s),
                    'min': np.min(r2s),
                    'max': np.max(r2s)
                }
            },
            'overall_metrics': {
                'mse': overall_mse,
                'mae': overall_mae,
                'r2': overall_r2
            },
            'predictions': predictions,
            'actuals': actuals,
            'timestamp': datetime.now().isoformat()
        }

        return summary

    def validate_all_strategies(self, strategies_config, data_generators):
        """Validate all trading strategies"""

        logger.info("🎯 Starting comprehensive strategy validation")

        all_results = {}

        for strategy_name, config in strategies_config.items():
            logger.info(f"🔬 Validating {strategy_name} strategy")

            # Generate data for this strategy
            if strategy_name in data_generators:
                X, y = data_generators[strategy_name]()
            else:
                # Default data generation
                X = torch.randn(1000, 24, 10)  # 1000 samples, 24 timesteps, 10 features
                y = torch.randn(1000, len(config.get('output_targets', [1])))

            # Create model factory
            def model_factory():
                if config['model_architecture'] == 'LSTM_FIB':
                    return self._create_lstm_model(10, len(config.get('output_targets', [1])))
                elif config['model_architecture'] == 'GRU_DCA':
                    return self._create_gru_model(10, len(config.get('output_targets', [1])))
                elif config['model_architecture'] == 'TRANSFORMER_GRID':
                    return self._create_transformer_model(10, len(config.get('output_targets', [1])))
                elif config['model_architecture'] == 'ATTENTION_ARB':
                    return self._create_attention_model(10, len(config.get('output_targets', [1])))
                else:
                    raise ValueError(f"Unknown architecture: {config['model_architecture']}")

            # Validate strategy
            result = self.validate_model(model_factory, X, y, strategy_name, config.get('training_epochs', 50))
            all_results[strategy_name] = result

        return all_results

    def _create_lstm_model(self, input_size, output_size):
        """Create LSTM model for validation"""
        class LSTMModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm = nn.LSTM(input_size, 64, 2, batch_first=True, dropout=0.2)
                self.fc = nn.Linear(64, output_size)

            def forward(self, x):
                out, _ = self.lstm(x)
                return self.fc(out[:, -1, :])

        return LSTMModel()

    def _create_gru_model(self, input_size, output_size):
        """Create GRU model for validation"""
        class GRUModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.gru = nn.GRU(input_size, 64, 2, batch_first=True, dropout=0.2)
                self.fc = nn.Linear(64, output_size)

            def forward(self, x):
                out, _ = self.gru(x)
                return self.fc(out[:, -1, :])

        return GRUModel()

    def _create_transformer_model(self, input_size, output_size):
        """Create Transformer model for validation"""
        class TransformerModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.input_projection = nn.Linear(input_size, 64)
                encoder_layer = nn.TransformerEncoderLayer(d_model=64, nhead=8, batch_first=True)
                self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=2)
                self.output_projection = nn.Linear(64, output_size)

            def forward(self, x):
                x = self.input_projection(x)
                x = self.transformer(x)
                return self.output_projection(x.mean(dim=1))

        return TransformerModel()

    def _create_attention_model(self, input_size, output_size):
        """Create Attention model for validation"""
        class AttentionModel(nn.Module):
            def __init__(self):
                super().__init__()
                self.encoder = nn.Linear(input_size, 64)
                self.attention = nn.MultiheadAttention(64, num_heads=8, batch_first=True)
                self.decoder = nn.Linear(64, output_size)

            def forward(self, x):
                x = torch.relu(self.encoder(x))
                attn_output, _ = self.attention(x, x, x)
                return self.decoder(attn_output.mean(dim=1))

        return AttentionModel()

    def generate_validation_report(self, results: Dict[str, Any]):
        """Generate comprehensive validation report"""

        report = {
            'validation_summary': {
                'timestamp': datetime.now().isoformat(),
                'n_strategies': len(results),
                'cv_method': 'TimeSeriesSplit' if self.time_series else 'KFold',
                'n_folds': self.n_splits
            },
            'strategy_results': results,
            'performance_comparison': self._compare_strategies(results),
            'recommendations': self._generate_recommendations(results)
        }

        # Save report
        self._save_validation_report(report)

        return report

    def _compare_strategies(self, results):
        """Compare strategy performance"""

        comparison = {}
        for strategy, result in results.items():
            metrics = result['summary_stats']
            comparison[strategy] = {
                'mean_r2': metrics['r2']['mean'],
                'std_r2': metrics['r2']['std'],
                'mean_mse': metrics['mse']['mean'],
                'std_mse': metrics['mse']['std'],
                'overall_r2': result['overall_metrics']['r2']
            }

        # Rank strategies by performance
        ranked = sorted(comparison.items(), key=lambda x: x[1]['mean_r2'], reverse=True)
        comparison['ranking'] = [{'strategy': s, 'rank': i+1, 'r2_score': data['mean_r2']}
                                for i, (s, data) in enumerate(ranked)]

        return comparison

    def _generate_recommendations(self, results):
        """Generate validation recommendations"""

        recommendations = []

        # Find best performing strategy
        if results:
            best_strategy = max(results.keys(),
                              key=lambda s: results[s]['summary_stats']['r2']['mean'])
            recommendations.append(f"🎯 Best performing strategy: {best_strategy} "
                                f"(R² = {results[best_strategy]['summary_stats']['r2']['mean']:.3f})")

        # Check for strategies needing improvement
        for strategy, result in results.items():
            r2_mean = result['summary_stats']['r2']['mean']
            r2_std = result['summary_stats']['r2']['std']

            if r2_mean < 0.5:
                recommendations.append(f"📈 {strategy} needs improvement (low R²: {r2_mean:.3f})")

            if r2_std > 0.2:
                recommendations.append(f"🔄 {strategy} has high variance (R² std: {r2_std:.3f}) - consider regularization")

        recommendations.extend([
            "🔧 Fine-tune hyperparameters for strategies with high variance",
            "📊 Implement early stopping to prevent overfitting",
            "🎪 Consider ensemble methods combining top strategies",
            "📈 Add more diverse training data for better generalization",
            "🔍 Implement model interpretability for strategy insights"
        ])

        return recommendations

    def _save_validation_report(self, report):
        """Save validation report"""

        reports_dir = Path("reports")
        reports_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"cross_validation_report_{timestamp}.json"
        filepath = reports_dir / filename

        with open(filepath, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        logger.info(f"📄 Cross-validation report saved: {filepath}")

def main():
    """Main entry point for cross-validation"""

    print("🔬 SovereignForge Cross-Validation Framework")
    print("=" * 50)

    # Initialize validator
    validator = CrossValidator(n_splits=5, time_series=True)

    # Define strategies to validate
    strategies_config = {
        'fib': {
            'model_architecture': 'LSTM_FIB',
            'output_targets': ['fib_level', 'direction', 'strength'],
            'training_epochs': 30
        },
        'dca': {
            'model_architecture': 'GRU_DCA',
            'output_targets': ['optimal_amount', 'optimal_timing', 'expected_return'],
            'training_epochs': 25
        },
        'grid': {
            'model_architecture': 'TRANSFORMER_GRID',
            'output_targets': ['grid_spacing', 'take_profit_levels', 'stop_loss_levels'],
            'training_epochs': 35
        },
        'arbitrage': {
            'model_architecture': 'ATTENTION_ARB',
            'output_targets': ['arbitrage_opportunity', 'profit_potential', 'risk_level'],
            'training_epochs': 40
        }
    }

    # Data generators for each strategy
    def fib_data_generator():
        X = torch.randn(500, 24, 10)
        y = torch.randint(0, 5, (500, 3)).float()  # fib_level, direction, strength
        return X, y

    def dca_data_generator():
        X = torch.randn(500, 24, 10)
        y = torch.randn(500, 3)  # amount, timing, return
        return X, y

    def grid_data_generator():
        X = torch.randn(500, 24, 10)
        y = torch.rand(500, 3)  # spacing, take_profit, stop_loss
        return X, y

    def arbitrage_data_generator():
        X = torch.randn(500, 24, 10)
        y = torch.randint(0, 2, (500, 3)).float()  # opportunity, profit, risk
        return X, y

    data_generators = {
        'fib': fib_data_generator,
        'dca': dca_data_generator,
        'grid': grid_data_generator,
        'arbitrage': arbitrage_data_generator
    }

    # Run validation
    results = validator.validate_all_strategies(strategies_config, data_generators)

    # Generate report
    report = validator.generate_validation_report(results)

    # Print summary
    print("\n" + "=" * 50)
    print("🎯 CROSS-VALIDATION COMPLETE")
    print("=" * 50)

    for strategy, result in results.items():
        metrics = result['summary_stats']
        print(f"\n🎯 {strategy.upper()} Strategy:")
        print(".3f")
        print(".3f")
        print(".3f")

    print("
📄 Detailed report saved in reports/ directory"    print("📊 Strategy comparison and recommendations included"
if __name__ == '__main__':
    main()