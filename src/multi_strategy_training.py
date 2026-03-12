#!/usr/bin/env python3
"""
SovereignForge - Multi-Strategy Training Pipeline
Defines model architectures for arbitrage, fibonacci, grid, and DCA strategies.
Provides factory functions and a unified training interface.
"""

import json
import logging
import os
import time
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim
from torch.utils.data import DataLoader, Dataset

logger = logging.getLogger(__name__)


# ── Strategy Type Enum ────────────────────────────────────────────────────

class StrategyType(Enum):
    ARBITRAGE = "arbitrage"
    FIBONACCI = "fibonacci"
    GRID = "grid"
    DCA = "dca"


# ── Datasets ──────────────────────────────────────────────────────────────

class StrategyDataset(Dataset):
    """Generic dataset for strategy training."""

    def __init__(self, features: torch.Tensor, targets: torch.Tensor):
        self.features = features
        self.targets = targets

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        return self.features[idx], self.targets[idx]


# ── Model Architectures ──────────────────────────────────────────────────

class TradingLSTM(nn.Module):
    """LSTM model for arbitrage and DCA strategies.

    Input:  [batch, seq_len, input_size]
    Output: [batch, output_size]
    """

    def __init__(self, input_size: int, output_size: int,
                 hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.lstm = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, output_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        lstm_out, _ = self.lstm(x)
        last_hidden = lstm_out[:, -1, :]
        return self.fc(last_hidden)


class TradingGRU(nn.Module):
    """GRU model for grid strategy — fast inference for frequent grid updates.

    Input:  [batch, seq_len, input_size]
    Output: [batch, output_size]
    """

    def __init__(self, input_size: int, output_size: int,
                 hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.gru = nn.GRU(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.fc1 = nn.Linear(hidden_size, 64)
        self.relu = nn.ReLU()
        self.dropout = nn.Dropout(dropout)
        self.fc2 = nn.Linear(64, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        gru_out, _ = self.gru(x)
        last_hidden = gru_out[:, -1, :]
        out = self.dropout(self.relu(self.fc1(last_hidden)))
        return self.fc2(out)


class TradingTransformer(nn.Module):
    """Transformer model for fibonacci strategy — pattern recognition over long sequences.

    Input:  [batch, seq_len, input_size]
    Output: [batch, output_size]
    """

    def __init__(self, input_size: int, output_size: int,
                 d_model: int = 128, nhead: int = 4, num_layers: int = 3,
                 dropout: float = 0.1):
        super().__init__()
        self.input_projection = nn.Linear(input_size, d_model)
        encoder_layer = nn.TransformerEncoderLayer(
            d_model=d_model,
            nhead=nhead,
            dim_feedforward=d_model * 4,
            dropout=dropout,
            batch_first=True,
        )
        self.transformer = nn.TransformerEncoder(encoder_layer, num_layers=num_layers)
        self.output_head = nn.Linear(d_model, output_size)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        projected = self.input_projection(x)
        encoded = self.transformer(projected)
        pooled = encoded.mean(dim=1)  # Mean pooling over sequence
        return self.output_head(pooled)


class TradingAttention(nn.Module):
    """LSTM + attention model for ensemble/collective brain.

    Input:  [batch, seq_len, input_size]
    Output: [batch, output_size]
    """

    def __init__(self, input_size: int, output_size: int,
                 hidden_size: int = 128, num_layers: int = 2, dropout: float = 0.2):
        super().__init__()
        self.encoder = nn.LSTM(
            input_size=input_size,
            hidden_size=hidden_size,
            num_layers=num_layers,
            batch_first=True,
            dropout=dropout if num_layers > 1 else 0,
        )
        self.attention = nn.Sequential(
            nn.Linear(hidden_size, hidden_size),
            nn.Tanh(),
            nn.Linear(hidden_size, 1),
        )
        self.output_head = nn.Sequential(
            nn.Linear(hidden_size, 64),
            nn.ReLU(),
            nn.Dropout(dropout),
            nn.Linear(64, output_size),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        encoded, _ = self.encoder(x)  # [batch, seq, hidden]
        attn_scores = self.attention(encoded)  # [batch, seq, 1]
        attn_weights = torch.softmax(attn_scores, dim=1)
        context = (attn_weights * encoded).sum(dim=1)  # [batch, hidden]
        return self.output_head(context)


# ── Factory Functions ─────────────────────────────────────────────────────

def create_lstm_model(input_size: int, output_size: int, **kwargs) -> TradingLSTM:
    """Create LSTM model (arbitrage/DCA strategy)."""
    return TradingLSTM(input_size, output_size, **kwargs)


def create_gru_model(input_size: int, output_size: int, **kwargs) -> TradingGRU:
    """Create GRU model (grid strategy)."""
    return TradingGRU(input_size, output_size, **kwargs)


def create_transformer_model(input_size: int, output_size: int, **kwargs) -> TradingTransformer:
    """Create Transformer model (fibonacci strategy)."""
    return TradingTransformer(input_size, output_size, **kwargs)


def create_attention_model(input_size: int, output_size: int, **kwargs) -> TradingAttention:
    """Create Attention model (ensemble/collective brain)."""
    return TradingAttention(input_size, output_size, **kwargs)


# ── Strategy ↔ Model Registry ────────────────────────────────────────────

STRATEGY_MODELS = {
    StrategyType.ARBITRAGE: create_lstm_model,
    StrategyType.FIBONACCI: create_transformer_model,
    StrategyType.GRID: create_gru_model,
    StrategyType.DCA: create_lstm_model,
}


# ── Feature Engineering ──────────────────────────────────────────────────

def engineer_features(ohlcv: np.ndarray, seq_len: int = 24) -> Tuple[np.ndarray, int]:
    """Engineer 10 features from raw OHLCV data.

    Input: ohlcv array with columns [timestamp, open, high, low, close, volume]
    Returns: (sequences [N, seq_len, 10], num_features)
    """
    if len(ohlcv) < seq_len + 1:
        return np.empty((0, seq_len, 10)), 10

    close = ohlcv[:, 4].astype(float)
    high = ohlcv[:, 2].astype(float)
    low = ohlcv[:, 3].astype(float)
    volume = ohlcv[:, 5].astype(float)
    open_price = ohlcv[:, 1].astype(float)

    # Feature 1: Price returns
    returns = np.diff(close) / (close[:-1] + 1e-10)
    returns = np.concatenate([[0], returns])

    # Feature 2: Log volume ratio
    vol_mean = np.mean(volume) + 1e-10
    log_vol_ratio = np.log(volume / vol_mean + 1e-10)

    # Feature 3: High-low range (volatility proxy)
    hl_range = (high - low) / (close + 1e-10)

    # Feature 4: Close-open direction
    co_direction = (close - open_price) / (open_price + 1e-10)

    # Feature 5: RSI (14-period)
    rsi = _compute_rsi(close, period=14)

    # Feature 6: MACD signal
    macd = _compute_macd(close)

    # Feature 7: Bollinger Band position
    bb_pos = _compute_bb_position(close, period=20)

    # Feature 8: Volume momentum (5-period)
    vol_mom = np.zeros_like(volume)
    for i in range(5, len(volume)):
        vol_mom[i] = (volume[i] - np.mean(volume[i - 5:i])) / (np.mean(volume[i - 5:i]) + 1e-10)

    # Feature 9: Price momentum (10-period)
    price_mom = np.zeros_like(close)
    for i in range(10, len(close)):
        price_mom[i] = (close[i] - close[i - 10]) / (close[i - 10] + 1e-10)

    # Feature 10: Volatility (20-period rolling std of returns)
    volatility = np.zeros_like(close)
    for i in range(20, len(close)):
        volatility[i] = np.std(returns[i - 20:i])

    # Stack features
    features = np.column_stack([
        returns, log_vol_ratio, hl_range, co_direction,
        rsi, macd, bb_pos, vol_mom, price_mom, volatility,
    ])

    # Normalize each feature
    for col in range(features.shape[1]):
        col_std = np.std(features[:, col])
        if col_std > 1e-10:
            features[:, col] = (features[:, col] - np.mean(features[:, col])) / col_std

    # Create sequences
    sequences = []
    for i in range(seq_len, len(features)):
        sequences.append(features[i - seq_len:i])

    return np.array(sequences), 10


def _compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Compute RSI, normalized to [-1, 1]."""
    rsi = np.zeros_like(close)
    deltas = np.diff(close)
    for i in range(period, len(close)):
        gains = np.maximum(deltas[i - period:i], 0)
        losses = np.abs(np.minimum(deltas[i - period:i], 0))
        avg_gain = np.mean(gains) + 1e-10
        avg_loss = np.mean(losses) + 1e-10
        rs = avg_gain / avg_loss
        rsi[i] = (2 * rs / (1 + rs)) - 1  # Normalize to [-1, 1]
    return rsi


def _compute_macd(close: np.ndarray) -> np.ndarray:
    """Compute MACD line (EMA12 - EMA26), normalized."""
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    std = np.std(macd) + 1e-10
    return macd / std


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average."""
    result = np.zeros_like(data)
    result[0] = data[0]
    alpha = 2 / (period + 1)
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _compute_bb_position(close: np.ndarray, period: int = 20) -> np.ndarray:
    """Compute position within Bollinger Bands, normalized to [-1, 1]."""
    bb_pos = np.zeros_like(close)
    for i in range(period, len(close)):
        window = close[i - period:i]
        mean = np.mean(window)
        std = np.std(window) + 1e-10
        bb_pos[i] = (close[i] - mean) / (2 * std)  # Normalized
    return np.clip(bb_pos, -1, 1)


# ── Label Generation (Strategy-Specific) ─────────────────────────────────

def generate_labels(
    ohlcv: np.ndarray,
    strategy: StrategyType,
    seq_len: int = 24,
) -> np.ndarray:
    """Generate strategy-specific training labels.

    Returns: labels [N, output_size=3] where:
      - col 0: signal strength [-1, 1] (buy positive, sell negative)
      - col 1: confidence [0, 1]
      - col 2: predicted magnitude [0, 1]
    """
    close = ohlcv[:, 4].astype(float)
    n_samples = len(close) - seq_len
    if n_samples <= 0:
        return np.empty((0, 3))

    labels = np.zeros((n_samples, 3))

    if strategy == StrategyType.ARBITRAGE:
        labels = _generate_arbitrage_labels(close, seq_len)
    elif strategy == StrategyType.FIBONACCI:
        labels = _generate_fibonacci_labels(close, seq_len)
    elif strategy == StrategyType.GRID:
        labels = _generate_grid_labels(close, seq_len)
    elif strategy == StrategyType.DCA:
        labels = _generate_dca_labels(close, seq_len)

    return labels


def _generate_arbitrage_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Arbitrage: forward return > threshold → buy signal."""
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    for i in range(n):
        idx = seq_len + i
        if idx + 1 < len(close):
            fwd_return = (close[idx + 1] - close[idx]) / (close[idx] + 1e-10)
            labels[i, 0] = np.clip(fwd_return * 100, -1, 1)  # signal
            labels[i, 1] = min(abs(fwd_return) * 200, 1.0)   # confidence
            labels[i, 2] = min(abs(fwd_return) * 100, 1.0)   # magnitude
    return labels


def _generate_fibonacci_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Fibonacci: signal based on proximity to fib retracement levels."""
    fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
    n = len(close) - seq_len
    labels = np.zeros((n, 3))

    for i in range(n):
        idx = seq_len + i
        window = close[max(0, idx - 50):idx]
        if len(window) < 10:
            continue
        high = np.max(window)
        low = np.min(window)
        rng = high - low
        if rng < 1e-10:
            continue

        retracement = (high - close[idx]) / rng

        # Find nearest fib level
        distances = [abs(retracement - lvl) for lvl in fib_levels]
        min_dist = min(distances)
        nearest_level = fib_levels[distances.index(min_dist)]

        # Signal: buy near 0.618/0.786 (deep retracement), sell near 0.236/0.382
        if min_dist < 0.05:  # Near a fib level
            if nearest_level >= 0.5:
                labels[i, 0] = 1.0 - min_dist * 10  # Buy signal
            else:
                labels[i, 0] = -(1.0 - min_dist * 10)  # Sell signal
            labels[i, 1] = 1.0 - min_dist * 10  # Confidence
            labels[i, 2] = rng / close[idx]  # Magnitude

    return labels


def _generate_grid_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Grid: optimal grid spacing based on volatility regime."""
    n = len(close) - seq_len
    labels = np.zeros((n, 3))

    for i in range(n):
        idx = seq_len + i
        window = close[max(0, idx - 20):idx]
        if len(window) < 5:
            continue

        volatility = np.std(np.diff(window) / (window[:-1] + 1e-10))
        mean_price = np.mean(window)

        # Grid signal: mean reversion strength
        deviation = (close[idx] - mean_price) / (mean_price + 1e-10)
        labels[i, 0] = np.clip(-deviation * 10, -1, 1)  # Buy below mean, sell above
        labels[i, 1] = min(volatility * 50, 1.0)  # Higher vol → more confidence in grid
        labels[i, 2] = min(volatility * 20, 1.0)  # Grid spacing magnitude

    return labels


def _generate_dca_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """DCA: buy-the-dip score based on drawdown from recent high."""
    n = len(close) - seq_len
    labels = np.zeros((n, 3))

    for i in range(n):
        idx = seq_len + i
        window = close[max(0, idx - 30):idx]
        if len(window) < 5:
            continue

        recent_high = np.max(window)
        drawdown = (recent_high - close[idx]) / (recent_high + 1e-10)

        # DCA: buy more when price is further from recent high
        if drawdown > 0.02:  # 2%+ drawdown triggers DCA
            labels[i, 0] = min(drawdown * 5, 1.0)  # Stronger buy on deeper dip
            labels[i, 1] = min(drawdown * 3, 1.0)  # Confidence scales with drawdown
            labels[i, 2] = drawdown  # Magnitude = drawdown itself

    return labels


# ── Training Function ─────────────────────────────────────────────────────

def train_strategy_model(
    strategy: StrategyType,
    pairs: List[str],
    data_dir: str = "data",
    epochs: int = 100,
    batch_size: int = 64,
    learning_rate: float = 1e-4,
    save_dir: str = "models/strategies",
    seq_len: int = 24,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """Train a strategy model for given trading pairs.

    Args:
        strategy: Which strategy to train
        pairs: List of trading pairs (e.g. ['XRP/USDC', 'ADA/USDC'])
        data_dir: Directory containing OHLCV CSV files
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate for optimizer
        save_dir: Directory to save trained models
        seq_len: Sequence length for input windows
        device: torch device (auto-detected if None)

    Returns:
        Dict with per-pair training results
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    Path(save_dir).mkdir(parents=True, exist_ok=True)

    model_factory = STRATEGY_MODELS[strategy]
    results = {}

    for pair in pairs:
        logger.info(f"Training {strategy.value} model for {pair}")

        try:
            # Load data
            ohlcv = _load_pair_data(pair, data_dir)
            if ohlcv is None or len(ohlcv) < seq_len + 10:
                logger.warning(f"Insufficient data for {pair}, skipping")
                results[pair] = {"status": "skipped", "reason": "insufficient data"}
                continue

            # Engineer features and generate labels
            features, n_features = engineer_features(ohlcv, seq_len)
            labels = generate_labels(ohlcv, strategy, seq_len)

            # Align lengths (features and labels may differ by 1)
            min_len = min(len(features), len(labels))
            features = features[:min_len]
            labels = labels[:min_len]

            if min_len < 10:
                logger.warning(f"Too few samples for {pair} after processing")
                results[pair] = {"status": "skipped", "reason": "too few samples"}
                continue

            # Train/val split (80/20)
            split_idx = int(min_len * 0.8)
            train_features = torch.FloatTensor(features[:split_idx])
            train_labels = torch.FloatTensor(labels[:split_idx])
            val_features = torch.FloatTensor(features[split_idx:])
            val_labels = torch.FloatTensor(labels[split_idx:])

            train_dataset = StrategyDataset(train_features, train_labels)
            val_dataset = StrategyDataset(val_features, val_labels)
            train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
            val_loader = DataLoader(val_dataset, batch_size=batch_size)

            # Create model
            output_size = 3  # signal, confidence, magnitude
            model = model_factory(n_features, output_size).to(device)
            optimizer = optim.AdamW(model.parameters(), lr=learning_rate, weight_decay=1e-5)
            scheduler = optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)
            criterion = nn.MSELoss()

            # Training loop
            best_val_loss = float('inf')
            patience_counter = 0
            patience = 20
            epoch_results = []

            for epoch in range(epochs):
                # Train
                model.train()
                train_loss = 0.0
                for batch_x, batch_y in train_loader:
                    batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                    optimizer.zero_grad()
                    output = model(batch_x)
                    loss = criterion(output, batch_y)
                    loss.backward()
                    torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                    optimizer.step()
                    train_loss += loss.item()

                train_loss /= max(len(train_loader), 1)

                # Validate
                model.eval()
                val_loss = 0.0
                with torch.no_grad():
                    for batch_x, batch_y in val_loader:
                        batch_x, batch_y = batch_x.to(device), batch_y.to(device)
                        output = model(batch_x)
                        val_loss += criterion(output, batch_y).item()

                val_loss /= max(len(val_loader), 1)
                scheduler.step()

                epoch_results.append({
                    "epoch": epoch + 1,
                    "train_loss": train_loss,
                    "val_loss": val_loss,
                })

                # Early stopping
                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    patience_counter = 0
                    # Save best model
                    pair_slug = pair.replace('/', '_').lower()
                    save_path = Path(save_dir) / f"{strategy.value}_{pair_slug}.pth"
                    torch.save({
                        "model_state_dict": model.state_dict(),
                        "config": {
                            "strategy": strategy.value,
                            "pair": pair,
                            "input_size": n_features,
                            "output_size": output_size,
                            "seq_len": seq_len,
                        },
                        "epoch": epoch + 1,
                        "val_loss": val_loss,
                        "timestamp": datetime.now().isoformat(),
                    }, save_path)
                else:
                    patience_counter += 1
                    if patience_counter >= patience:
                        logger.info(f"Early stopping at epoch {epoch + 1} for {pair}")
                        break

                if (epoch + 1) % 20 == 0:
                    logger.info(
                        f"  {pair} epoch {epoch + 1}/{epochs}: "
                        f"train_loss={train_loss:.6f}, val_loss={val_loss:.6f}"
                    )

            results[pair] = {
                "status": "trained",
                "strategy": strategy.value,
                "best_val_loss": best_val_loss,
                "epochs_completed": len(epoch_results),
                "samples": min_len,
                "epoch_results": epoch_results,
            }
            logger.info(f"Finished {strategy.value} for {pair}: val_loss={best_val_loss:.6f}")

        except Exception as e:
            logger.error(f"Training failed for {pair}: {e}")
            results[pair] = {"status": "failed", "error": str(e)}

    return results


def _load_pair_data(pair: str, data_dir: str) -> Optional[np.ndarray]:
    """Load OHLCV data for a trading pair from CSV.

    Looks for files like: data/XRP_USDC_1h.csv or data/xrp_usdc.csv
    Expected columns: timestamp, open, high, low, close, volume
    """
    pair_slug = pair.replace('/', '_')

    candidates = [
        f"{pair_slug}_1h.csv",
        f"{pair_slug}.csv",
        f"{pair_slug.lower()}_1h.csv",
        f"{pair_slug.lower()}.csv",
    ]

    for filename in candidates:
        filepath = Path(data_dir) / filename
        if filepath.exists():
            try:
                import pandas as pd
                df = pd.read_csv(filepath)
                required = ['open', 'high', 'low', 'close', 'volume']
                if all(col in df.columns for col in required):
                    # Ensure timestamp column
                    if 'timestamp' not in df.columns:
                        df['timestamp'] = range(len(df))
                    return df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")

    logger.warning(f"No data file found for {pair} in {data_dir}")
    return None


# ── Convenience: Train All Strategies ─────────────────────────────────────

def train_all_strategies(
    pairs: List[str],
    data_dir: str = "data",
    epochs: int = 100,
    batch_size: int = 64,
    save_dir: str = "models/strategies",
) -> Dict[str, Dict[str, Any]]:
    """Train all 4 strategies for all pairs.

    Returns: {strategy_name: {pair: result}}
    """
    all_results = {}
    for strategy in StrategyType:
        logger.info(f"\n{'=' * 50}")
        logger.info(f"Training {strategy.value.upper()} strategy")
        logger.info(f"{'=' * 50}")
        results = train_strategy_model(
            strategy=strategy,
            pairs=pairs,
            data_dir=data_dir,
            epochs=epochs,
            batch_size=batch_size,
            save_dir=save_dir,
        )
        all_results[strategy.value] = results

    return all_results
