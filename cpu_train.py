#!/usr/bin/env python3
"""
SovereignForge CPU Training Script - NumPy/SciPy Fallback
Arbitrage model training using real exchange data (no PyTorch dependency)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import mean_squared_error, r2_score
import joblib
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Any
import json

from src.data_fetcher import RealDataFetcher

logger = logging.getLogger(__name__)

class ArbitrageModel:
    """Simple arbitrage prediction model using Random Forest"""

    def __init__(self, pair: str):
        self.pair = pair
        self.model = None
        self.scaler = None
        self.feature_names = [
            'price_spread', 'volume_ratio', 'price_volatility',
            'bid_ask_spread', 'exchange_diversity'
        ]

    def prepare_features(self, data: Dict[str, pd.DataFrame]) -> pd.DataFrame:
        """Prepare features from exchange data"""

        # Get common timestamps
        all_timestamps = set()
        for df in data.values():
            all_timestamps.update(df.index)

        common_timestamps = sorted(all_timestamps)

        features = []

        for ts in common_timestamps:
            ts_features = {}

            # Get prices at this timestamp
            prices = {}
            volumes = {}
            for exchange, df in data.items():
                # Find closest price
                if not df.empty:
                    closest_idx = df.index.get_indexer([pd.Timestamp(ts)], method='nearest')[0]
                    if closest_idx != -1:
                        row = df.iloc[closest_idx]
                        prices[exchange] = row['close']
                        volumes[exchange] = row['volume']

            if len(prices) < 2:
                continue  # Need at least 2 exchanges

            # Calculate arbitrage features
            price_values = list(prices.values())
            volume_values = list(volumes.values())

            # Price spread (max - min)
            ts_features['price_spread'] = max(price_values) - min(price_values)

            # Volume ratio (max/min)
            if min(volume_values) > 0:
                ts_features['volume_ratio'] = max(volume_values) / min(volume_values)
            else:
                ts_features['volume_ratio'] = 1.0

            # Price volatility (std dev)
            ts_features['price_volatility'] = np.std(price_values)

            # Bid-ask spread approximation
            ts_features['bid_ask_spread'] = np.mean(price_values) * 0.001  # Assume 0.1% spread

            # Exchange diversity
            ts_features['exchange_diversity'] = len(prices)

            # Target: arbitrage opportunity (1 if spread > threshold, 0 otherwise)
            threshold = np.mean(price_values) * 0.002  # 0.2% threshold
            ts_features['arbitrage_opportunity'] = 1 if ts_features['price_spread'] > threshold else 0

            features.append(ts_features)

        return pd.DataFrame(features)

    def train(self, data: Dict[str, pd.DataFrame], test_size: float = 0.2):
        """Train the model"""

        # Prepare features
        df = self.prepare_features(data)

        if df.empty or len(df) < 10:
            logger.warning(f"Insufficient data for {self.pair}")
            return None

        # Split features and target
        X = df[self.feature_names]
        y = df['arbitrage_opportunity']

        # Scale features
        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X_scaled, y, test_size=test_size, random_state=42
        )

        # Train model
        self.model = RandomForestRegressor(
            n_estimators=100,
            max_depth=10,
            random_state=42,
            n_jobs=-1
        )

        self.model.fit(X_train, y_train)

        # Evaluate
        train_pred = self.model.predict(X_train)
        test_pred = self.model.predict(X_test)

        train_mse = mean_squared_error(y_train, train_pred)
        test_mse = mean_squared_error(y_test, test_pred)
        test_r2 = r2_score(y_test, test_pred)

        results = {
            'train_mse': train_mse,
            'test_mse': test_mse,
            'test_r2': test_r2,
            'n_samples': len(df),
            'n_features': len(self.feature_names),
            'feature_importance': dict(zip(self.feature_names,
                                         self.model.feature_importances_))
        }

        logger.info(f"Trained {self.pair}: R²={test_r2:.3f}, MSE={test_mse:.4f}")

        return results

    def predict(self, features: Dict[str, float]) -> float:
        """Predict arbitrage opportunity"""
        if not self.model or not self.scaler:
            return 0.0

        # Prepare feature vector
        feature_vector = np.array([[features.get(name, 0) for name in self.feature_names]])
        feature_vector_scaled = self.scaler.transform(feature_vector)

        return self.model.predict(feature_vector_scaled)[0]

    def save(self, path: str):
        """Save model"""
        if self.model and self.scaler:
            model_data = {
                'model': self.model,
                'scaler': self.scaler,
                'feature_names': self.feature_names,
                'pair': self.pair,
                'trained_at': datetime.now().isoformat()
            }
            joblib.dump(model_data, path)
            logger.info(f"Model saved to {path}")

    def load(self, path: str):
        """Load model"""
        if os.path.exists(path):
            model_data = joblib.load(path)
            self.model = model_data['model']
            self.scaler = model_data['scaler']
            self.feature_names = model_data['feature_names']
            self.pair = model_data['pair']
            logger.info(f"Model loaded from {path}")

def train_all_pairs():
    """Train models for all available pairs"""

    print("SovereignForge CPU Training - Real Data")
    print("=" * 50)

    # Initialize data fetcher
    fetcher = RealDataFetcher()

    # Get available pairs
    available_pairs = fetcher.get_available_pairs()
    print(f"Available pairs: {len(available_pairs)}")

    if not available_pairs:
        print("No data available. Run data_fetcher.py first.")
        return

    # Train models
    results = {}
    models = {}

    for pair_file in available_pairs:
        pair = pair_file.replace('_data.json', '').replace('_', '/')
        print(f"\nTraining {pair}...")

        try:
            # Load data
            data = fetcher.load_data(pair)
            if not data:
                print(f"  No data for {pair}")
                continue

            # Create and train model
            model = ArbitrageModel(pair)
            training_results = model.train(data)

            if training_results:
                results[pair] = training_results
                models[pair] = model

                # Save model
                model_path = f"models/{pair.replace('/', '_')}_model.pkl"
                os.makedirs('models', exist_ok=True)
                model.save(model_path)

                print(f"  [OK] Trained: R2={training_results['test_r2']:.3f}")

            else:
                print(f"  [FAIL] Training failed")

        except Exception as e:
            print(f"  [ERROR] {e}")

    # Generate report
    generate_training_report(results)

    print(f"\nTraining complete! {len(results)} models trained.")
    print("Models saved to models/ directory")

    return results

def generate_training_report(results: Dict[str, Any]):
    """Generate training report"""

    report = f"""# SovereignForge CPU Training Report - Real Data

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Summary
- **Models Trained**: {len(results)}
- **Data Source**: Real exchange data (CCXT)
- **Algorithm**: Random Forest Regressor

## Model Performance

| Pair | Samples | Test R² | Test MSE | Status |
|------|---------|---------|----------|--------|
"""

    for pair, metrics in results.items():
        status = "[GOOD]" if metrics['test_r2'] > 0.5 else "[OK]" if metrics['test_r2'] > 0.2 else "[POOR]"
        report += f"| {pair} | {metrics['n_samples']} | {metrics['test_r2']:.3f} | {metrics['test_mse']:.4f} | {status} |\n"

    report += "\n## Feature Importance (Average)\n\n"

    # Calculate average feature importance
    all_importance = {}
    for pair_metrics in results.values():
        for feature, importance in pair_metrics['feature_importance'].items():
            all_importance[feature] = all_importance.get(feature, []) + [importance]

    avg_importance = {k: np.mean(v) for k, v in all_importance.items()}
    sorted_features = sorted(avg_importance.items(), key=lambda x: x[1], reverse=True)

    for feature, importance in sorted_features:
        report += f"- **{feature}**: {importance:.3f}\n"

    report += "\n## Recommendations\n"
    report += "- Deploy models with R² > 0.5 to production\n"
    report += "- Retrain models with R² < 0.2 with more data\n"
    report += "- Monitor feature importance for model interpretability\n"
    report += "- Consider ensemble methods for better performance\n"

    # Save report
    os.makedirs('reports', exist_ok=True)
    report_path = f"reports/cpu_training_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

    with open(report_path, 'w') as f:
        f.write(report)

    print(f"Report saved to {report_path}")

if __name__ == "__main__":
    train_all_pairs()