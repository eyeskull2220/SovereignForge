#!/usr/bin/env python3
"""
SovereignForge ML Trainer - Wave 2
Advanced AI/ML training pipeline for arbitrage prediction
"""

import json
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
import torch
import torch.nn as nn
import torch.optim as optim
from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from torch.utils.data import DataLoader, Dataset

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ml_training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class ArbitrageDataset(Dataset):
    """PyTorch dataset for arbitrage training data"""

    def __init__(self, features: torch.Tensor, targets: torch.Tensor):
        self.features = features
        self.targets = targets

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        return self.features[idx], self.targets[idx]

class AdvancedArbitrageDetector(nn.Module):
    """Advanced neural network with LSTM and attention"""

    def __init__(self, input_size: int = 20, hidden_size: int = 64, num_layers: int = 2):
        super(AdvancedArbitrageDetector, self).__init__()

        self.input_size = input_size
        self.hidden_size = hidden_size
        self.num_layers = num_layers

        # LSTM for sequence processing
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=0.2 if num_layers > 1 else 0
        )

        # Attention mechanism
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
            nn.Softmax(dim=1)
        )

        # Output layers
        self.classifier = nn.Sequential(
            nn.Linear(hidden_size, 32),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(16, 1)
        )

        # Initialize weights
        self._initialize_weights()

    def _initialize_weights(self):
        """Initialize network weights"""
        for name, param in self.named_parameters():
            if 'weight' in name:
                if len(param.shape) >= 2:
                    nn.init.xavier_uniform_(param)
                else:
                    nn.init.normal_(param, 0, 0.01)
            elif 'bias' in name:
                nn.init.constant_(param, 0)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass with attention"""
        # x shape: (batch_size, seq_len, input_size)

        # LSTM processing
        lstm_out, (h_n, c_n) = self.lstm(x)

        # Attention weights
        attention_weights = self.attention(lstm_out)  # (batch_size, seq_len, 1)
        attention_weights = attention_weights.transpose(1, 2)  # (batch_size, 1, seq_len)

        # Apply attention
        attended = torch.bmm(attention_weights, lstm_out)  # (batch_size, 1, hidden_size)
        attended = attended.squeeze(1)  # (batch_size, hidden_size)

        # Classification
        output = self.classifier(attended)
        return output

class FeatureEngineer:
    """Advanced feature engineering for arbitrage detection"""

    def __init__(self):
        self.feature_names = [
            # Price features
            'price_diff_pct', 'bid_ask_spread_avg', 'bid_ask_spread_diff',

            # Volume features
            'volume_ratio', 'volume_imbalance', 'volume_trend',

            # Volatility features
            'realized_volatility', 'implied_volatility', 'volatility_ratio',

            # Market microstructure
            'order_book_depth_ratio', 'liquidity_score', 'market_impact',

            # Temporal features
            'hour_of_day', 'day_of_week', 'market_session',

            # Momentum features
            'price_momentum', 'volume_momentum', 'spread_momentum',

            # Statistical features
            'price_zscore', 'volume_zscore', 'correlation_5m', 'correlation_15m'
        ]

    def create_features(self, market_data: Dict, history: List[Dict] = None) -> torch.Tensor:
        """Create comprehensive feature set"""
        features = []

        exchanges = market_data.get('exchanges', {})

        if len(exchanges) >= 2:
            exch_list = list(exchanges.values())

            # Price features
            features.extend(self._price_features(exch_list))

            # Volume features
            features.extend(self._volume_features(exch_list))

            # Volatility features
            features.extend(self._volatility_features(market_data, history))

            # Market microstructure
            features.extend(self._microstructure_features(exch_list))

            # Temporal features
            features.extend(self._temporal_features(market_data))

            # Momentum features
            features.extend(self._momentum_features(history or []))

            # Statistical features
            features.extend(self._statistical_features(history or []))

        else:
            # Default features if insufficient data
            features = [0.0] * len(self.feature_names)

        return torch.tensor(features, dtype=torch.float32)

    def _price_features(self, exchanges: List[Dict]) -> List[float]:
        """Extract price-based features"""
        features = []

        if len(exchanges) >= 2:
            # Price difference percentage
            price1 = (exchanges[0].get('bid', 0) + exchanges[0].get('ask', 0)) / 2
            price2 = (exchanges[1].get('bid', 0) + exchanges[1].get('ask', 0)) / 2

            if price1 > 0:
                price_diff_pct = (price2 - price1) / price1
                features.append(price_diff_pct)
            else:
                features.append(0.0)

            # Bid-ask spread features
            spread1 = exchanges[0].get('ask', 0) - exchanges[0].get('bid', 0)
            spread2 = exchanges[1].get('ask', 0) - exchanges[1].get('bid', 0)

            spread_avg = (spread1 + spread2) / 2
            spread_diff = abs(spread1 - spread2)

            features.append(spread_avg)
            features.append(spread_diff)
        else:
            features.extend([0.0, 0.001, 0.0])

        return features

    def _volume_features(self, exchanges: List[Dict]) -> List[float]:
        """Extract volume-based features"""
        features = []

        volumes = [exch.get('volume', 0) for exch in exchanges]

        if len(volumes) >= 2 and volumes[1] > 0:
            volume_ratio = volumes[0] / volumes[1]
            features.append(volume_ratio)

            # Volume imbalance
            total_volume = sum(volumes)
            imbalance = (volumes[0] - volumes[1]) / total_volume
            features.append(imbalance)
        else:
            features.extend([1.0, 0.0])

        # Volume trend (placeholder - would need historical data)
        features.append(0.0)

        return features

    def _volatility_features(self, market_data: Dict, history: List[Dict]) -> List[float]:
        """Extract volatility features"""
        features = []

        # Realized volatility from price history
        if history and len(history) > 10:
            prices = [h.get('price', 45000) for h in history[-20:]]
            returns = np.diff(np.log(prices))
            realized_vol = np.std(returns) * np.sqrt(252)  # Annualized
            features.append(realized_vol)
        else:
            features.append(0.02)  # Default 2% volatility

        # Implied volatility (placeholder)
        implied_vol = market_data.get('implied_volatility', 0.025)
        features.append(implied_vol)

        # Volatility ratio
        if features[0] > 0:
            vol_ratio = features[1] / features[0]
            features.append(vol_ratio)
        else:
            features.append(1.0)

        return features

    def _microstructure_features(self, exchanges: List[Dict]) -> List[float]:
        """Extract market microstructure features"""
        features = []

        # Order book depth ratio (simplified)
        depth1 = exchanges[0].get('order_book_depth', 100)
        depth2 = exchanges[1].get('order_book_depth', 100)

        if depth2 > 0:
            depth_ratio = depth1 / depth2
            features.append(depth_ratio)
        else:
            features.append(1.0)

        # Liquidity score (based on volume and spread)
        volumes = [exch.get('volume', 0) for exch in exchanges]
        spreads = [exch.get('ask', 0) - exch.get('bid', 0) for exch in exchanges]

        liquidity_score = 0
        if volumes and spreads:
            avg_volume = np.mean(volumes)
            avg_spread = np.mean(spreads)
            if avg_spread > 0:
                liquidity_score = avg_volume / avg_spread
                liquidity_score = min(liquidity_score / 10000, 1.0)  # Normalize

        features.append(liquidity_score)

        # Market impact (simplified)
        features.append(0.001)  # Placeholder

        return features

    def _temporal_features(self, market_data: Dict) -> List[float]:
        """Extract temporal features"""
        features = []

        timestamp = market_data.get('timestamp', datetime.now())

        # Hour of day (normalized)
        hour_of_day = timestamp.hour / 24.0
        features.append(hour_of_day)

        # Day of week (normalized)
        day_of_week = timestamp.weekday() / 6.0
        features.append(day_of_week)

        # Market session (simplified: 0=off-hours, 1=active)
        hour = timestamp.hour
        is_active = 1.0 if 8 <= hour <= 20 else 0.0  # 8 AM - 8 PM
        features.append(is_active)

        return features

    def _momentum_features(self, history: List[Dict]) -> List[float]:
        """Extract momentum features"""
        features = []

        if len(history) >= 5:
            # Price momentum (5-period)
            prices = [h.get('price', 45000) for h in history[-5:]]
            if len(prices) >= 2:
                price_momentum = (prices[-1] - prices[0]) / prices[0]
                features.append(price_momentum)
            else:
                features.append(0.0)

            # Volume momentum (5-period)
            volumes = [h.get('volume', 100) for h in history[-5:]]
            if len(volumes) >= 2:
                volume_momentum = (volumes[-1] - volumes[0]) / volumes[0]
                features.append(volume_momentum)
            else:
                features.append(0.0)

            # Spread momentum (5-period)
            spreads = [h.get('spread', 10) for h in history[-5:]]
            if len(spreads) >= 2:
                spread_momentum = (spreads[-1] - spreads[0]) / spreads[0]
                features.append(spread_momentum)
            else:
                features.append(0.0)
        else:
            features.extend([0.0, 0.0, 0.0])

        return features

    def _statistical_features(self, history: List[Dict]) -> List[float]:
        """Extract statistical features"""
        features = []

        if len(history) >= 20:
            prices = [h.get('price', 45000) for h in history[-20:]]

            # Price z-score (recent vs historical mean)
            recent_prices = prices[-5:]
            hist_prices = prices[:-5]

            if hist_prices:
                hist_mean = np.mean(hist_prices)
                hist_std = np.std(hist_prices)

                if hist_std > 0:
                    current_price = np.mean(recent_prices)
                    price_zscore = (current_price - hist_mean) / hist_std
                    features.append(price_zscore)
                else:
                    features.append(0.0)
            else:
                features.append(0.0)

            # Volume z-score
            volumes = [h.get('volume', 100) for h in history[-20:]]
            recent_volumes = volumes[-5:]
            hist_volumes = volumes[:-5]

            if hist_volumes:
                hist_vol_mean = np.mean(hist_volumes)
                hist_vol_std = np.std(hist_volumes)

                if hist_vol_std > 0:
                    current_volume = np.mean(recent_volumes)
                    volume_zscore = (current_volume - hist_vol_mean) / hist_vol_std
                    features.append(volume_zscore)
                else:
                    features.append(0.0)
            else:
                features.append(0.0)

            # Short-term correlation (5-minute)
            if len(prices) >= 10:
                short_prices = prices[-10:]
                short_returns = np.diff(np.log(short_prices))
                if len(short_returns) > 1:
                    corr_5m = np.corrcoef(short_returns[:-1], short_returns[1:])[0, 1]
                    features.append(corr_5m if not np.isnan(corr_5m) else 0.0)
                else:
                    features.append(0.0)
            else:
                features.append(0.0)

            # Longer-term correlation (15-minute)
            if len(prices) >= 30:
                long_prices = prices[-30:]
                long_returns = np.diff(np.log(long_prices))
                if len(long_returns) > 1:
                    corr_15m = np.corrcoef(long_returns[:-1], long_returns[1:])[0, 1]
                    features.append(corr_15m if not np.isnan(corr_15m) else 0.0)
                else:
                    features.append(0.0)
            else:
                features.append(0.0)

        else:
            features.extend([0.0, 0.0, 0.0, 0.0])

        return features

class MLTrainer:
    """Advanced ML training pipeline"""

    def __init__(self, model: nn.Module, device: str = 'auto'):
        self.model = model
        self.device = torch.device('cuda' if torch.cuda.is_available() and device == 'auto' else device)
        self.model.to(self.device)

        # Training components
        self.criterion = nn.BCEWithLogitsLoss()  # For binary classification
        self.optimizer = optim.AdamW(model.parameters(), lr=0.001, weight_decay=1e-4)
        self.scheduler = optim.lr_scheduler.CosineAnnealingWarmRestarts(
            self.optimizer, T_0=10, T_mult=2
        )

        # Training state
        self.best_loss = float('inf')
        self.patience = 20
        self.patience_counter = 0
        self.best_model_state = None

        # Metrics tracking
        self.training_history = []

    def generate_training_data(self, n_samples: int = 50000) -> Tuple[torch.Tensor, torch.Tensor]:
        """Generate comprehensive training dataset"""
        logger.info(f"Generating {n_samples} training samples...")

        feature_engineer = FeatureEngineer()
        all_features = []
        all_targets = []

        for i in range(n_samples):
            if i % 10000 == 0:
                logger.info(f"Generated {i}/{n_samples} samples...")

            # Generate synthetic market data
            market_data = self._generate_synthetic_market_data()
            history = self._generate_price_history()

            # Create features
            features = feature_engineer.create_features(market_data, history)
            all_features.append(features)

            # Generate target (arbitrage opportunity)
            target = self._generate_arbitrage_target(market_data, history)
            all_targets.append(target)

        X = torch.stack(all_features)
        y = torch.tensor(all_targets, dtype=torch.float32).unsqueeze(1)

        logger.info(f"Generated dataset: {X.shape[0]} samples, {X.shape[1]} features")
        return X, y

    def _generate_synthetic_market_data(self) -> Dict:
        """Generate realistic synthetic market data"""
        # Base prices with some correlation
        base_price1 = 45000 + np.random.normal(0, 1000)
        base_price2 = base_price1 * (1 + np.random.normal(0, 0.005))  # Slight correlation

        # Add arbitrage opportunities occasionally
        arbitrage_factor = np.random.choice([0, 1], p=[0.85, 0.15])  # 15% arbitrage opportunities
        if arbitrage_factor:
            price_diff = np.random.uniform(0.001, 0.01)  # 0.1% to 1% arbitrage
            direction = np.random.choice([-1, 1])
            base_price2 = base_price1 * (1 + direction * price_diff)

        return {
            'exchanges': {
                'binance': {
                    'bid': base_price1 - np.random.uniform(5, 20),
                    'ask': base_price1 + np.random.uniform(5, 20),
                    'volume': np.random.uniform(50, 200),
                    'order_book_depth': np.random.uniform(80, 150)
                },
                'coinbase': {
                    'bid': base_price2 - np.random.uniform(5, 20),
                    'ask': base_price2 + np.random.uniform(5, 20),
                    'volume': np.random.uniform(40, 180),
                    'order_book_depth': np.random.uniform(70, 140)
                }
            },
            'implied_volatility': np.random.uniform(0.015, 0.05),
            'timestamp': datetime.now()
        }

    def _generate_price_history(self, length: int = 50) -> List[Dict]:
        """Generate synthetic price history"""
        history = []
        base_price = 45000

        for i in range(length):
            # Random walk with mean reversion
            price_change = np.random.normal(0, 50) - 0.1 * (base_price - 45000)  # Mean reversion
            base_price += price_change

            # Generate volume and spread
            volume = np.random.uniform(80, 150)
            spread = np.random.uniform(8, 25)

            history.append({
                'price': base_price,
                'volume': volume,
                'spread': spread,
                'timestamp': datetime.now() - timedelta(minutes=length-i)
            })

        return history

    def _generate_arbitrage_target(self, market_data: Dict, history: List[Dict]) -> float:
        """Generate arbitrage opportunity target"""
        exchanges = market_data['exchanges']
        prices = []

        for exch_data in exchanges.values():
            if 'bid' in exch_data and 'ask' in exch_data:
                mid_price = (exch_data['bid'] + exch_data['ask']) / 2
                prices.append(mid_price)

        if len(prices) >= 2:
            # Calculate price difference
            price_diff = abs(prices[0] - prices[1]) / prices[0]

            # Calculate spreads
            spreads = []
            for exch_data in exchanges.values():
                spread = exch_data['ask'] - exch_data['bid']
                spreads.append(spread)

            avg_spread = np.mean(spreads)

            # Arbitrage opportunity if price diff > average spread + buffer
            buffer = 0.001  # 0.1% buffer for transaction costs
            is_arbitrage = 1.0 if price_diff > (avg_spread / prices[0] + buffer) else 0.0

            return is_arbitrage

        return 0.0

    def train(self, train_loader: DataLoader, val_loader: DataLoader,
              epochs: int = 50) -> Dict[str, any]:
        """Complete training pipeline"""
        logger.info(f"Starting ML training on {self.device}")
        logger.info(f"   - Model: {self.model.__class__.__name__}")
        logger.info(f"   - Parameters: {sum(p.numel() for p in self.model.parameters()):,}")
        logger.info(f"   - Epochs: {epochs}")

        start_time = datetime.now()

        for epoch in range(epochs):
            # Train epoch
            train_loss, train_metrics = self._train_epoch(train_loader)

            # Validate
            val_loss, val_metrics = self._validate(val_loader)

            # Learning rate scheduling
            self.scheduler.step()

            # Early stopping
            if val_loss < self.best_loss:
                self.best_loss = val_loss
                self.patience_counter = 0
                self.best_model_state = self.model.state_dict().copy()
            else:
                self.patience_counter += 1

            # Logging
            if epoch % 5 == 0 or epoch == epochs - 1:
                current_lr = self.optimizer.param_groups[0]['lr']
                logger.info(f"Epoch {epoch:3d}: Train Loss: {train_loss:.6f}, "
                          f"Val Loss: {val_loss:.6f}, "
                          f"Val Acc: {val_metrics['accuracy']:.4f}, "
                          f"LR: {current_lr:.6f}")

            # Store metrics
            self.training_history.append({
                'epoch': epoch,
                'train_loss': train_loss,
                'val_loss': val_loss,
                'train_metrics': train_metrics,
                'val_metrics': val_metrics,
                'learning_rate': current_lr
            })

            # Early stopping check
            if self.patience_counter >= self.patience:
                logger.info(f"Early stopping at epoch {epoch}")
                break

        training_time = (datetime.now() - start_time).total_seconds()

        # Restore best model
        if self.best_model_state:
            self.model.load_state_dict(self.best_model_state)
            logger.info("Restored best model weights")

        results = {
            'training_time_seconds': training_time,
            'epochs_completed': len(self.training_history),
            'final_train_loss': self.training_history[-1]['train_loss'],
            'final_val_loss': self.training_history[-1]['val_loss'],
            'best_val_loss': self.best_loss,
            'final_metrics': self.training_history[-1]['val_metrics'],
            'training_history': self.training_history,
            'best_model_state': self.best_model_state
        }

        logger.info("ML training completed!")
        logger.info(f"   - Training time: {training_time:.1f}s")
        logger.info(f"   - Best validation loss: {self.best_loss:.6f}")
        logger.info(f"   - Final accuracy: {results['final_metrics']['accuracy']:.4f}")

        return results

    def _train_epoch(self, train_loader: DataLoader) -> Tuple[float, Dict]:
        """Train for one epoch"""
        self.model.train()
        epoch_loss = 0.0
        all_preds = []
        all_targets = []
        n_batches = 0

        for batch_X, batch_y in train_loader:
            batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)

            # Forward pass
            self.optimizer.zero_grad()
            outputs = self.model(batch_X.unsqueeze(1))  # Add sequence dimension
            loss = self.criterion(outputs, batch_y)

            # Backward pass
            loss.backward()
            torch.nn.utils.clip_grad_norm_(self.model.parameters(), max_norm=1.0)
            self.optimizer.step()

            epoch_loss += loss.item()

            # Collect predictions for metrics
            preds = torch.sigmoid(outputs).cpu().detach().numpy()
            targets = batch_y.cpu().detach().numpy()

            all_preds.extend(preds)
            all_targets.extend(targets)

            n_batches += 1

        epoch_loss /= n_batches

        # Calculate metrics
        metrics = self._calculate_metrics(np.array(all_preds), np.array(all_targets))

        return epoch_loss, metrics

    def _validate(self, val_loader: DataLoader) -> Tuple[float, Dict]:
        """Validate model"""
        self.model.eval()
        val_loss = 0.0
        all_preds = []
        all_targets = []

        with torch.no_grad():
            for batch_X, batch_y in val_loader:
                batch_X, batch_y = batch_X.to(self.device), batch_y.to(self.device)

                outputs = self.model(batch_X.unsqueeze(1))
                loss = self.criterion(outputs, batch_y)

                val_loss += loss.item()

                preds = torch.sigmoid(outputs).cpu().numpy()
                targets = batch_y.cpu().numpy()

                all_preds.extend(preds)
                all_targets.extend(targets)

        val_loss /= len(val_loader)

        # Calculate metrics
        metrics = self._calculate_metrics(np.array(all_preds), np.array(all_targets))

        return val_loss, metrics

    def _calculate_metrics(self, predictions: np.ndarray, targets: np.ndarray) -> Dict:
        """Calculate classification metrics"""
        # Convert to binary predictions
        binary_preds = (predictions > 0.5).astype(int)
        binary_targets = targets.astype(int).flatten()

        return {
            'accuracy': accuracy_score(binary_targets, binary_preds),
            'precision': precision_score(binary_targets, binary_preds, zero_division=0),
            'recall': recall_score(binary_targets, binary_preds, zero_division=0),
            'f1': f1_score(binary_targets, binary_preds, zero_division=0)
        }

def main():
    """Main ML training execution"""
    print("SovereignForge ML Trainer - Wave 2")
    print("=" * 40)

    # Set device
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"Using device: {device}")

    try:
        # Create model
        print("\nCreating advanced arbitrage detector...")
        model = AdvancedArbitrageDetector(input_size=22, hidden_size=64, num_layers=2)
        print(f"Model parameters: {sum(p.numel() for p in model.parameters()):,}")

        # Create trainer
        trainer = MLTrainer(model, device=str(device))

        # Generate training data
        print("\nGenerating training dataset...")
        X, y = trainer.generate_training_data(n_samples=25000)

        # Split data
        X_train, X_val, y_train, y_val = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y
        )

        print(f"Training samples: {len(X_train)}")
        print(f"Validation samples: {len(X_val)}")
        print(f"Arbitrage opportunities in training: {y_train.sum().item():.0f} ({y_train.mean().item()*100:.1f}%)")

        # Create data loaders
        train_dataset = ArbitrageDataset(X_train, y_train)
        val_dataset = ArbitrageDataset(X_val, y_val)

        train_loader = DataLoader(train_dataset, batch_size=128, shuffle=True)
        val_loader = DataLoader(val_dataset, batch_size=256, shuffle=False)

        # Train model
        print("\nStarting model training...")
        training_results = trainer.train(train_loader, val_loader, epochs=30)

        # Save model
        print("\nSaving trained model...")
        model_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "models", "advanced_arbitrage_detector_v2.0.pth")
        os.makedirs(os.path.dirname(model_path), exist_ok=True)

        torch.save({
            'model_state_dict': model.state_dict(),
            'training_results': training_results,
            'feature_names': FeatureEngineer().feature_names,
            'metadata': {
                'version': '2.0.0',
                'created': datetime.now().isoformat(),
                'architecture': 'AdvancedArbitrageDetector',
                'input_size': 22,
                'hidden_size': 64,
                'num_layers': 2,
                'training_samples': len(X_train),
                'final_accuracy': training_results['final_metrics']['accuracy']
            }
        }, model_path)

        print(f"Model saved to {model_path}")
        print(f"   - Final accuracy: {training_results['final_metrics']['accuracy']:.4f}")
        print(f"   - Final F1 score: {training_results['final_metrics']['f1']:.4f}")
        print(f"   - Training time: {training_results['training_time_seconds']:.1f}s")

        print("\nWave 2 ML training completed!")
        print("Ready for integration with trading engine")

        return True

    except Exception as e:
        logger.error(f"ML training failed: {e}")
        return False

if __name__ == "__main__":
    main()
