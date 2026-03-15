#!/usr/bin/env python3
"""
SovereignForge - Multi-Strategy Training Pipeline
Defines model architectures for arbitrage, fibonacci, grid, and DCA strategies.
Provides factory functions and a unified training interface.
"""

import json
import logging
import os
import sys
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

try:
    import mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    mlflow = None
    MLFLOW_AVAILABLE = False

logger = logging.getLogger(__name__)


# ── Strategy Type Enum ────────────────────────────────────────────────────

class StrategyType(Enum):
    ARBITRAGE = "arbitrage"
    FIBONACCI = "fibonacci"
    GRID = "grid"
    DCA = "dca"
    MEAN_REVERSION = "mean_reversion"
    PAIRS_ARBITRAGE = "pairs_arbitrage"
    MOMENTUM = "momentum"


# ── Datasets ──────────────────────────────────────────────────────────────

class StrategyDataset(Dataset):
    """Generic dataset for strategy training with optional sample weights."""

    def __init__(self, features: torch.Tensor, targets: torch.Tensor,
                 weights: Optional[torch.Tensor] = None):
        self.features = features
        self.targets = targets
        self.weights = weights

    def __len__(self):
        return len(self.targets)

    def __getitem__(self, idx):
        if self.weights is not None:
            return self.features[idx], self.targets[idx], self.weights[idx]
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
                 dropout: float = 0.2):
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
    StrategyType.MEAN_REVERSION: create_gru_model,
    StrategyType.PAIRS_ARBITRAGE: create_lstm_model,
    StrategyType.MOMENTUM: create_transformer_model,
}


# ── Feature Engineering ──────────────────────────────────────────────────

def engineer_features(ohlcv: np.ndarray, seq_len: int = 128) -> Tuple[np.ndarray, int]:
    """Engineer 17 features from raw OHLCV data.

    Input: ohlcv array with columns [timestamp, open, high, low, close, volume]
    Returns: (sequences [N, seq_len, 17], num_features)

    Features 1-10: price/volume technicals
    Feature 11: ADX (regime indicator)
    Features 12-17: Session one-hot (US_OPEN, US_CLOSE, ASIA_OPEN, ASIA_CLOSE, LONDON_OPEN, LONDON_CLOSE)
    """
    N_FEATURES = 17

    if len(ohlcv) < seq_len + 1:
        return np.empty((0, seq_len, N_FEATURES)), N_FEATURES

    timestamps = ohlcv[:, 0].astype(float)
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

    # Feature 8: Volume momentum (5-period) — vectorized
    N = len(volume)
    vol_cumsum = np.cumsum(np.insert(volume, 0, 0))  # length N+1
    vol_ma5 = np.zeros_like(volume)
    if N > 5:
        vol_ma5[5:] = (vol_cumsum[6:] - vol_cumsum[1:N - 4]) / 5.0
    vol_mom = np.where(vol_ma5 > 1e-10, (volume - vol_ma5) / vol_ma5, 0.0)

    # Feature 9: Price momentum (10-period) — vectorized
    price_mom = np.zeros_like(close)
    price_mom[10:] = (close[10:] - close[:-10]) / (close[:-10] + 1e-10)

    # Feature 10: Volatility (20-period rolling std of returns) — vectorized
    ret_cumsum = np.cumsum(np.insert(returns, 0, 0))  # length N+1
    ret_sq_cumsum = np.cumsum(np.insert(returns**2, 0, 0))  # length N+1
    volatility = np.zeros_like(close)
    n_win = 20
    if N > n_win:
        mean_r = (ret_cumsum[n_win + 1:] - ret_cumsum[1:N - n_win + 1]) / n_win
        mean_r2 = (ret_sq_cumsum[n_win + 1:] - ret_sq_cumsum[1:N - n_win + 1]) / n_win
        volatility[n_win:] = np.sqrt(np.maximum(mean_r2 - mean_r**2, 0))

    # Feature 11: ADX (14-period regime indicator)
    from session_regime import compute_adx, session_one_hot
    adx = compute_adx(high, low, close, period=14)
    adx_normalized = adx / 100.0  # Normalize to [0, 1]

    # Features 12-17: Session one-hot encoding (6 sessions)
    sess_onehot = session_one_hot(timestamps)  # (N, 6)

    # Stack all 17 features
    features = np.column_stack([
        returns, log_vol_ratio, hl_range, co_direction,
        rsi, macd, bb_pos, vol_mom, price_mom, volatility,
        adx_normalized, sess_onehot,
    ])

    # Replace any inf/NaN from feature calculations with 0
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    # Normalize first 11 numeric features (skip session one-hot)
    col_mean = features[:, :11].mean(axis=0)
    col_std = features[:, :11].std(axis=0)
    col_std[col_std < 1e-10] = 1.0  # Prevent division by zero
    features[:, :11] = (features[:, :11] - col_mean) / col_std

    # Final sanitization after normalization
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    # Create sequences — pre-allocated array instead of list-append + np.array()
    n_sequences = len(features) - seq_len
    sequences = np.empty((n_sequences, seq_len, N_FEATURES), dtype=np.float32)
    for i in range(n_sequences):
        sequences[i] = features[i:i + seq_len]

    return sequences, N_FEATURES


def _compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    """Vectorized RSI computation, normalized to [-1, 1].

    Uses cumsum-based rolling mean for gains/losses instead of per-candle
    Python loop.  Output is numerically identical to the original SMA-based
    RSI with the (2*rs/(1+rs))-1 normalisation.
    """
    rsi = np.zeros_like(close, dtype=np.float64)
    deltas = np.diff(close)

    if len(deltas) < period:
        return rsi

    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)

    # Rolling mean of gains/losses via cumsum (O(n) instead of O(n*period))
    gain_cumsum = np.cumsum(np.insert(gains, 0, 0.0))
    loss_cumsum = np.cumsum(np.insert(losses, 0, 0.0))

    # avg over [i-period : i] for every valid i  (deltas is 0-indexed, close is 1-indexed)
    avg_gain = (gain_cumsum[period:] - gain_cumsum[:-period]) / period + 1e-10
    avg_loss = (loss_cumsum[period:] - loss_cumsum[:-period]) / period + 1e-10

    rs = avg_gain / avg_loss
    rsi[period:] = (2.0 * rs / (1.0 + rs)) - 1.0  # Normalize to [-1, 1]
    return rsi


def _compute_macd(close: np.ndarray) -> np.ndarray:
    """Compute MACD line (EMA12 - EMA26), normalized."""
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    std = np.std(macd) + 1e-10
    return macd / std


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    """Exponential moving average (float64 precision).

    The recurrence ``result[i] = alpha * data[i] + (1-alpha) * result[i-1]``
    has an inherent sequential dependency, so the loop remains, but we
    ensure float64 to avoid precision drift over long series.
    """
    result = np.zeros_like(data, dtype=np.float64)
    alpha = 2.0 / (period + 1)
    one_minus_alpha = 1.0 - alpha
    result[0] = data[0]
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + one_minus_alpha * result[i - 1]
    return result


def _compute_bb_position(close: np.ndarray, period: int = 20) -> np.ndarray:
    """Vectorized Bollinger Band position using cumsum-based rolling stats.

    Computes rolling mean and std in O(n) via prefix sums instead of
    O(n*period) via per-window np.mean/np.std calls.
    """
    n = len(close)
    bb_pos = np.zeros(n, dtype=np.float64)
    if n < period:
        return np.clip(bb_pos, -1, 1)

    # Rolling mean via cumsum
    # cumsum has length N+1 after insert. cumsum[period:]-cumsum[:-period] has N+1-period elements.
    # close[period:] has N-period elements. Slice rolling arrays to match.
    c = close.astype(np.float64)
    cumsum = np.cumsum(np.insert(c, 0, 0.0))       # length N+1
    rolling_sum = cumsum[period:] - cumsum[:-period] # length N+1-period
    rolling_mean = rolling_sum[:n - period] / period  # trim to N-period

    # Rolling std via cumsum of squares  (population std, matching np.std default)
    cumsum_sq = np.cumsum(np.insert(c ** 2, 0, 0.0))
    rolling_sum_sq = cumsum_sq[period:] - cumsum_sq[:-period]
    rolling_mean_sq = rolling_sum_sq[:n - period] / period
    rolling_std = np.sqrt(np.maximum(rolling_mean_sq - rolling_mean ** 2, 0.0)) + 1e-10

    # BB position: (price - mean) / (2 * std)
    bb_pos[period:] = (close[period:] - rolling_mean) / (2.0 * rolling_std)
    return np.clip(bb_pos, -1, 1)


# ── Label Generation (Strategy-Specific) ─────────────────────────────────

def generate_labels(
    ohlcv: np.ndarray,
    strategy: StrategyType,
    seq_len: int = 128,
    pair: str = "unknown",
    exchange: str = "unknown",
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
    elif strategy == StrategyType.MEAN_REVERSION:
        labels = _generate_mean_reversion_labels(close, seq_len)
    elif strategy == StrategyType.PAIRS_ARBITRAGE:
        labels = _generate_pairs_arb_labels(close, seq_len)
    elif strategy == StrategyType.MOMENTUM:
        labels = _generate_momentum_labels(close, seq_len, ohlcv)

    _log_label_diagnostics(labels, strategy.value, pair, exchange)

    return labels


def _generate_arbitrage_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Arbitrage: forward-looking spread exploitation over next 6 candles (30m at 5m).

    Predicts whether current price dislocation creates exploitable opportunity
    over the next 30 minutes. Uses only forward data for targets.
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 6  # 30 minutes at 5m candles

    for i in range(n):
        idx = seq_len + i
        if idx + forward_window >= len(close):
            continue  # Not enough forward data

        current_price = close[idx]

        # Forward-looking: best achievable return over next 30 min
        future_prices = close[idx + 1:idx + forward_window + 1]
        future_max = np.max(future_prices)
        future_min = np.min(future_prices)

        # Signal: directional opportunity — did price move enough to exploit?
        best_long = (future_max - current_price) / (current_price + 1e-10)
        best_short = (current_price - future_min) / (current_price + 1e-10)

        if best_long > best_short:
            labels[i, 0] = np.clip(best_long * 50, 0, 1)   # buy signal
        else:
            labels[i, 0] = np.clip(-best_short * 50, -1, 0)  # sell signal

        # Confidence: forward volatility — higher spread = higher confidence
        fwd_range = (future_max - future_min) / (current_price + 1e-10)
        labels[i, 1] = min(fwd_range * 30, 1.0)

        # Magnitude: absolute end-of-window return
        fwd_return = (close[idx + forward_window] - current_price) / (current_price + 1e-10)
        labels[i, 2] = min(abs(fwd_return) * 50, 1.0)

    return labels


def _generate_fibonacci_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Fibonacci: forward-looking profitability at fib retracement levels over next 18 candles (90m at 5m).

    Uses backward window for fib level identification (strategy logic) but
    targets are forward-looking: does trading at this fib level produce profit?
    """
    fib_levels = [0.236, 0.382, 0.5, 0.618, 0.786]
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 18  # 90 minutes at 5m candles

    for i in range(n):
        idx = seq_len + i
        if idx + forward_window >= len(close):
            continue  # Not enough forward data

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

        # Forward-looking: what happens over the next 90 minutes?
        current_price = close[idx]
        future_prices = close[idx + 1:idx + forward_window + 1]
        fwd_return = (close[idx + forward_window] - current_price) / (current_price + 1e-10)

        # Signal: forward return amplified by fib proximity
        # Near a fib level → stronger signal; far from any level → muted
        # Deep retracement (0.618/0.786): positive return = bounce = buy
        # Shallow retracement (0.236/0.382): negative return = continuation = sell
        proximity = max(0, 1.0 - min_dist * 10)  # 0-1, how close to a fib level
        labels[i, 0] = np.clip(fwd_return * 30 * (1 + proximity), -1, 1)

        # Confidence: combination of fib proximity and forward volatility
        fwd_volatility = np.std(future_prices) / (current_price + 1e-10)
        labels[i, 1] = min(proximity * 0.5 + fwd_volatility * 100, 1.0)

        # Magnitude: absolute forward return scaled by range context
        labels[i, 2] = min(abs(fwd_return) * 30, 1.0)

    return labels


def _generate_grid_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Grid: forward-looking mean-reversion targets over next 12 candles (1h at 5m).

    Predicts whether price reverts toward the 20-candle mean over the NEXT 12 candles.
    Uses only forward data for targets to prevent data leakage.
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 12  # 1 hour at 5m candles

    for i in range(n):
        idx = seq_len + i

        # Need backward window for mean calculation and forward window for targets
        backward_window = close[max(0, idx - 20):idx]
        if len(backward_window) < 5:
            continue
        if idx + forward_window >= len(close):
            continue  # Not enough forward data

        mean_price = np.mean(backward_window)
        current_deviation = (close[idx] - mean_price) / (mean_price + 1e-10)

        # Forward-looking: deviation at end of forward window
        future_mean = np.mean(close[idx + 1:idx + forward_window + 1])
        future_price = close[idx + forward_window]
        future_deviation = (future_price - future_mean) / (future_mean + 1e-10)

        # ATR-scaled deviation: larger ATR = stronger mean-reversion signal needed
        tr_window = close[max(0, idx - 14):idx]
        if len(tr_window) > 1:
            tr_vals = np.abs(np.diff(tr_window))
            atr_est = np.mean(tr_vals) if len(tr_vals) > 0 else 1e-10
            atr_scale = max(atr_est / (mean_price + 1e-10), 1e-10)
            deviation_normalized = current_deviation / (atr_scale * 10 + 1e-10)
        else:
            deviation_normalized = current_deviation * 20

        # Signal: did price revert toward the mean? ATR-scaled for dynamic grids
        reversion = current_deviation - future_deviation
        labels[i, 0] = np.clip(reversion * 20 * min(abs(deviation_normalized), 2.0), -1, 1)

        # Confidence: volatility regime indicator
        volatility = np.std(np.diff(backward_window) / (backward_window[:-1] + 1e-10))
        labels[i, 1] = min(volatility * 50, 1.0)

        # Magnitude: absolute forward return
        fwd_return = (close[idx + forward_window] - close[idx]) / (close[idx] + 1e-10)
        labels[i, 2] = min(abs(fwd_return) * 50, 1.0)

    return labels


def _generate_dca_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """DCA: forward-looking buy-now vs DCA-average over next 24 candles (2h at 5m).

    Predicts whether buying NOW beats dollar-cost-averaging over the next 24 candles.
    Uses only forward data for targets to prevent data leakage.
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 48  # 4 hours at 5m candles

    for i in range(n):
        idx = seq_len + i

        if idx + forward_window >= len(close):
            continue  # Not enough forward data

        buy_now_price = close[idx]
        future_prices = close[idx + 1:idx + forward_window + 1]

        # DCA average price: average of buying at each of the next 24 candles
        dca_avg_price = np.mean(future_prices)

        # Local-low detection: is current price near the minimum of the forward window?
        future_min = np.min(future_prices)
        local_low_proximity = 1.0 - min(abs(buy_now_price - future_min) / (buy_now_price + 1e-10) * 200, 1.0)

        # Signal: combine DCA advantage with local-low bonus
        dca_advantage = (dca_avg_price - buy_now_price) / (buy_now_price + 1e-10) * 30
        # If we're at a local low, boost buy signal
        if local_low_proximity > 0.5:
            dca_advantage = max(dca_advantage, local_low_proximity * 0.8)
        labels[i, 0] = np.clip(dca_advantage, -1, 1)

        # Confidence: higher when at local low + future range is large
        future_range = (np.max(future_prices) - future_min) / (buy_now_price + 1e-10)
        labels[i, 1] = min(future_range * 10 * (0.5 + 0.5 * local_low_proximity), 1.0)

        # Magnitude: absolute end-of-window return
        fwd_return = (close[idx + forward_window] - buy_now_price) / (buy_now_price + 1e-10)
        labels[i, 2] = min(abs(fwd_return) * 20, 1.0)

    return labels


def _generate_mean_reversion_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Mean Reversion: Bollinger Band + RSI-based oversold/overbought detection.

    Forward window: 10 candles (50m at 5m). Signals when price is at BB extremes
    and RSI confirms oversold/overbought, predicting reversion to mean.
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 12
    bb_period = 20

    rsi = _compute_rsi(close, period=14)
    bb_pos = _compute_bb_position(close, period=bb_period)

    for i in range(n):
        idx = seq_len + i
        if idx + forward_window >= len(close):
            continue

        current_price = close[idx]
        current_bb = bb_pos[idx]
        current_rsi = rsi[idx]

        # Forward return for target
        fwd_return = (close[idx + forward_window] - current_price) / (current_price + 1e-10)

        # Mean reversion signal: extreme BB position + RSI confirmation
        # Oversold: BB < -0.8 AND RSI < 30 → expect bounce (buy)
        # Overbought: BB > 0.8 AND RSI > 70 → expect pullback (sell)
        bb_extreme = max(0, abs(current_bb) - 0.5) * 2  # 0 when |BB|<0.5, 1 when |BB|=1

        if current_bb < -0.7 and current_rsi < 35:
            # Oversold zone: buy signal weighted by extremity
            rsi_extreme = max(0, (35 - current_rsi) / 35)
            signal = fwd_return * 40 * (1 + bb_extreme + rsi_extreme)
            labels[i, 0] = np.clip(signal, 0, 1)
        elif current_bb > 0.7 and current_rsi > 65:
            # Overbought zone: sell signal
            rsi_extreme = max(0, (current_rsi - 65) / 35)
            signal = fwd_return * 40 * (1 + bb_extreme + rsi_extreme)
            labels[i, 0] = np.clip(signal, -1, 0)
        else:
            # Neutral zone: weak signal based on forward return
            labels[i, 0] = np.clip(fwd_return * 15, -1, 1)

        # Confidence: BB extremity * RSI extremity
        rsi_conf = abs(current_rsi - 50) / 50  # 0 at RSI=50, 1 at RSI=0 or 100
        labels[i, 1] = min(bb_extreme * 0.5 + rsi_conf * 0.5, 1.0)

        # Magnitude
        labels[i, 2] = min(abs(fwd_return) * 40, 1.0)

    return labels


def _generate_pairs_arb_labels(close: np.ndarray, seq_len: int) -> np.ndarray:
    """Pairs Arbitrage: spread z-score mean-reversion over 20 candles.

    When trained on a single pair, this models spread dynamics against
    the pair's own rolling mean — suitable for detecting mean-reversion
    opportunities. For true pair trading, the spread between two assets
    would be pre-computed before calling this function.
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 15
    spread_window = 40

    for i in range(n):
        idx = seq_len + i
        if idx + forward_window >= len(close):
            continue

        # Compute spread as deviation from rolling mean (self-spread)
        lookback = close[max(0, idx - spread_window):idx]
        if len(lookback) < 20:
            continue

        mean_price = np.mean(lookback)
        std_price = np.std(lookback)
        if std_price < 1e-10:
            continue

        z_score = (close[idx] - mean_price) / std_price

        # Forward: does the z-score revert?
        future_price = close[idx + forward_window]
        future_z = (future_price - mean_price) / std_price
        z_reversion = z_score - future_z  # positive = price reverted

        # Signal: z-score extremes predict reversion
        if abs(z_score) > 2.0:
            # Strong divergence: trade the reversion
            labels[i, 0] = np.clip(-np.sign(z_score) * min(abs(z_score) / 3, 1.0), -1, 1)
        else:
            labels[i, 0] = np.clip(z_reversion * 0.3, -1, 1)

        # Confidence: higher z-score = higher confidence in reversion
        labels[i, 1] = min(abs(z_score) / 3, 1.0)

        # Magnitude: how much did z-score actually revert
        labels[i, 2] = min(abs(z_reversion) / 3, 1.0)

    return labels


def _generate_momentum_labels(close: np.ndarray, seq_len: int,
                               ohlcv: np.ndarray = None) -> np.ndarray:
    """Momentum: trend continuation prediction over 48 candles (4h at 5m).

    Signals trend continuation when price > EMA, volume above average,
    MACD positive. Confidence scaled by ADX (trend strength).
    """
    n = len(close) - seq_len
    labels = np.zeros((n, 3))
    forward_window = 36
    ema_period = 12

    # Compute EMA
    ema = np.zeros_like(close, dtype=np.float64)
    ema[0] = close[0]
    alpha = 2.0 / (ema_period + 1)
    for j in range(1, len(close)):
        ema[j] = alpha * close[j] + (1 - alpha) * ema[j - 1]

    # Compute MACD for trend confirmation
    macd = _compute_macd(close)

    # Compute volume if available
    volume = ohlcv[:, 5].astype(float) if ohlcv is not None and ohlcv.shape[1] > 5 else None

    # ADX for confidence
    if ohlcv is not None and ohlcv.shape[1] > 4:
        high = ohlcv[:, 2].astype(float)
        low = ohlcv[:, 3].astype(float)
        from session_regime import compute_adx as _adx
        adx = _adx(high, low, close, period=14)
    else:
        adx = np.zeros_like(close)

    for i in range(n):
        idx = seq_len + i
        if idx + forward_window >= len(close):
            continue

        current_price = close[idx]
        current_ema = ema[idx]
        current_macd = macd[idx]

        # Trend conditions
        above_ema = current_price > current_ema
        macd_positive = current_macd > 0

        # Volume confirmation
        vol_confirmed = True
        if volume is not None and idx >= 20:
            avg_vol = np.mean(volume[idx - 20:idx])
            vol_confirmed = volume[idx] > avg_vol * 1.0

        # Forward return (trend continuation target)
        fwd_return = (close[idx + forward_window] - current_price) / (current_price + 1e-10)

        # Signal: trend continuation
        trend_alignment = 0.0
        if above_ema and macd_positive:
            trend_alignment = 1.0  # bullish trend
        elif not above_ema and not macd_positive:
            trend_alignment = -1.0  # bearish trend

        if abs(trend_alignment) > 0:
            # In trend: signal = forward return amplified by trend strength
            labels[i, 0] = np.clip(fwd_return * 20 * trend_alignment, -1, 1)
        else:
            # Mixed signals: weak directional signal
            labels[i, 0] = np.clip(fwd_return * 8, -1, 1)

        # Confidence: ADX strength (high ADX = strong trend = high confidence)
        adx_conf = min(adx[idx] / 50, 1.0) if adx[idx] > 0 else 0.3
        vol_conf = 1.0 if vol_confirmed else 0.5
        labels[i, 1] = min(adx_conf * 0.7 + vol_conf * 0.3, 1.0)

        # Magnitude: directional forward move
        labels[i, 2] = min(abs(fwd_return) * 15, 1.0)

    return labels


def _log_label_diagnostics(
    labels: np.ndarray, strategy: str, pair: str, exchange: str
) -> None:
    """Log summary statistics for generated labels and warn on degenerate distributions."""
    col_names = ["signal", "confidence", "magnitude"]
    for col_idx, name in enumerate(col_names):
        col = labels[:, col_idx]
        mean_val = np.mean(col)
        std_val = np.std(col)
        min_val = np.min(col)
        max_val = np.max(col)
        zero_pct = 100.0 * np.mean(np.abs(col) < 1e-8)
        logger.info(
            f"  Label[{name}] {strategy}/{pair}@{exchange}: "
            f"mean={mean_val:.4f} std={std_val:.4f} "
            f"min={min_val:.4f} max={max_val:.4f} zero%={zero_pct:.1f}%"
        )
        if zero_pct > 80:
            logger.warning(
                f"  WARNING: {name} for {strategy}/{pair}@{exchange} has {zero_pct:.1f}% zeros — "
                f"labels may be degenerate"
            )
        if std_val < 0.01:
            logger.warning(
                f"  WARNING: {name} for {strategy}/{pair}@{exchange} has std={std_val:.6f} — "
                f"near-constant labels, model may not learn meaningful patterns"
            )


# ── Training Function ─────────────────────────────────────────────────────

def train_strategy_model(
    strategy: StrategyType,
    pairs: List[str],
    data_dir: str = "data/historical/binance",
    exchanges: Optional[List[str]] = None,
    epochs: int = 100,
    batch_size: int = 96,
    learning_rate: float = 8e-5,
    save_dir: str = "models/strategies",
    seq_len: int = 128,
    device: Optional[torch.device] = None,
) -> Dict[str, Any]:
    """Train a strategy model for given trading pairs across exchanges.

    Args:
        strategy: Which strategy to train
        pairs: List of trading pairs (e.g. ['XRP/USDC', 'ADA/USDC'])
        data_dir: Base directory containing OHLCV CSV files (used when exchanges is None)
        exchanges: List of exchanges to train on (e.g. ['binance', 'coinbase', 'kraken', 'okx']).
                   When provided, loads data from data/historical/{exchange}/ for each.
        epochs: Number of training epochs
        batch_size: Training batch size
        learning_rate: Learning rate for optimizer
        save_dir: Directory to save trained models
        seq_len: Sequence length for input windows
        device: torch device (auto-detected if None)

    Returns:
        Dict with per-exchange/pair training results
    """
    if device is None:
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    # GPU optimizations for 4060 Ti 16GB
    if device.type == 'cuda':
        torch.cuda.set_per_process_memory_fraction(0.82, device.index or 0)
        torch.backends.cudnn.benchmark = True
    batch_size = min(batch_size, 96)  # Cap for 4060 Ti VRAM with 5m candle seq_len=128

    Path(save_dir).mkdir(parents=True, exist_ok=True)

    model_factory = STRATEGY_MODELS[strategy]
    results = {}

    # Build list of (exchange, data_directory) pairs to train on
    if exchanges:
        exchange_dirs = [(ex, f"data/historical/{ex}") for ex in exchanges]
    else:
        # Infer exchange name from data_dir path
        exchange_name = Path(data_dir).name  # e.g. "binance"
        exchange_dirs = [(exchange_name, data_dir)]

    # Knowledge graph for recording training metadata
    try:
        from training_knowledge_graph import TrainingKnowledgeGraph
        kg = TrainingKnowledgeGraph()
    except ImportError:
        kg = None

    # MLflow experiment setup
    _mlflow_ok = False
    if MLFLOW_AVAILABLE:
        try:
            mlflow.set_experiment(f"sovereignforge-{strategy.value}")
            _mlflow_ok = True
            logger.info(f"MLflow experiment set: sovereignforge-{strategy.value}")
        except Exception as e:
            logger.warning(f"MLflow experiment setup failed: {e}")

    for exchange, ex_data_dir in exchange_dirs:
        logger.info(f"\n--- Training {strategy.value} on {exchange.upper()} ---")

        for pair in pairs:
            result_key = f"{pair}:{exchange}"
            logger.info(f"Training {strategy.value} model for {pair} on {exchange}")

            try:
                # Load data
                ohlcv = _load_pair_data(pair, ex_data_dir)
                if ohlcv is None or len(ohlcv) < seq_len + 10:
                    logger.warning(f"Insufficient data for {pair} on {exchange}, skipping")
                    results[result_key] = {"status": "skipped", "reason": "insufficient data", "exchange": exchange}
                    continue

                # Low-data handling: minimum 60 days, transfer learning below 90 days
                # 288 candles/day for 5m timeframe, 24 for 1h
                candles_per_day = 288.0 if len(ohlcv) > 5000 else 24.0
                days_of_data = len(ohlcv) / candles_per_day
                if days_of_data < 60:
                    logger.warning(f"Only {days_of_data:.0f} days for {pair}@{exchange}, below minimum 60. Skipping.")
                    results[result_key] = {"status": "skipped", "reason": f"only {days_of_data:.0f} days", "exchange": exchange}
                    continue

                use_transfer = days_of_data < 90
                effective_lr = learning_rate
                if use_transfer:
                    logger.info(f"Only {days_of_data:.0f} days for {pair}@{exchange}, attempting transfer learning")
                    effective_lr = learning_rate * 0.1  # Fine-tune at 10x lower LR

                # Engineer features and generate labels
                features, n_features = engineer_features(ohlcv, seq_len)
                labels = generate_labels(ohlcv, strategy, seq_len, pair=pair, exchange=exchange)

                # Compute session-based sample weights for loss weighting
                try:
                    from session_regime import compute_session_weights
                    timestamps = ohlcv[seq_len:seq_len + len(features), 0].astype(float)
                    high_vals = ohlcv[seq_len:seq_len + len(features), 2].astype(float)
                    low_vals = ohlcv[seq_len:seq_len + len(features), 3].astype(float)
                    close_vals = ohlcv[seq_len:seq_len + len(features), 4].astype(float)
                    sample_weights = compute_session_weights(timestamps, high_vals, low_vals, close_vals)
                except Exception as e:
                    logger.warning(f"Session weights unavailable ({e}), using uniform weights")
                    sample_weights = np.ones(len(features))

                # Align lengths (features and labels may differ by 1)
                min_len = min(len(features), len(labels), len(sample_weights))
                features = features[:min_len]
                labels = labels[:min_len]
                sample_weights = sample_weights[:min_len]

                # Trim trailing samples that lack sufficient forward data for labels
                # All strategies now use forward-looking targets
                forward_windows = {
                    StrategyType.ARBITRAGE: 6,
                    StrategyType.FIBONACCI: 18,
                    StrategyType.GRID: 12,
                    StrategyType.DCA: 48,
                    StrategyType.MEAN_REVERSION: 12,
                    StrategyType.PAIRS_ARBITRAGE: 15,
                    StrategyType.MOMENTUM: 36,
                }
                forward_window = forward_windows[strategy]
                effective_len = len(labels) - forward_window
                if effective_len > 0:
                    labels = labels[:effective_len]
                    features = features[:effective_len]
                    sample_weights = sample_weights[:effective_len]
                    min_len = effective_len

                if min_len < 10:
                    logger.warning(f"Too few samples for {pair} on {exchange} after processing")
                    results[result_key] = {"status": "skipped", "reason": "too few samples", "exchange": exchange}
                    continue

                # Train/test split: 45d train / 15d test (75/25, strict out-of-sample)
                split_idx = int(min_len * 0.75)
                # Embargo gap: prevent label leakage between train and val
                embargo = forward_window  # gap equal to forward-looking window
                train_end = split_idx - embargo

                # Re-normalize using train-only statistics (prevent normalization leakage)
                train_mean = features[:train_end, :11].mean(axis=0)
                train_std = features[:train_end, :11].std(axis=0)
                train_std[train_std < 1e-10] = 1.0
                features[:, :11] = (features[:, :11] - train_mean) / train_std
                features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

                train_features = torch.FloatTensor(features[:train_end])
                train_labels = torch.FloatTensor(labels[:train_end])
                train_weights = torch.FloatTensor(sample_weights[:train_end])
                val_features = torch.FloatTensor(features[split_idx:])
                val_labels = torch.FloatTensor(labels[split_idx:])

                train_dataset = StrategyDataset(train_features, train_labels, train_weights)
                val_dataset = StrategyDataset(val_features, val_labels)
                use_cuda = device.type == 'cuda'
                # num_workers=0 on Windows to avoid multiprocessing spawn crashes
                _workers = 0 if sys.platform == 'win32' else (4 if use_cuda else 0)
                _val_workers = 0 if sys.platform == 'win32' else (2 if use_cuda else 0)
                train_loader = DataLoader(
                    train_dataset, batch_size=batch_size, shuffle=True,
                    pin_memory=use_cuda, num_workers=_workers,
                )
                val_loader = DataLoader(
                    val_dataset, batch_size=batch_size,
                    pin_memory=use_cuda, num_workers=_val_workers,
                )

                # Create model
                output_size = 3  # signal, confidence, magnitude
                model = model_factory(n_features, output_size).to(device)

                # Transfer learning: load donor model if available
                if use_transfer:
                    donor = _load_best_donor_model(strategy, pair, exchange, exchange_dirs, save_dir, device)
                    if donor is not None:
                        try:
                            model.load_state_dict(donor, strict=False)
                            logger.info(f"Transfer learning: loaded donor model for {pair}@{exchange}")
                        except Exception as e:
                            logger.warning(f"Transfer learning load failed ({e}), training from scratch")

                optimizer = optim.AdamW(model.parameters(), lr=effective_lr, weight_decay=1e-4)
                scheduler = optim.lr_scheduler.ReduceLROnPlateau(
                    optimizer, mode='min', factor=0.5, patience=10, min_lr=1e-6
                )
                # Linear warmup over first 5 epochs before ReduceLROnPlateau takes over
                warmup_epochs = 5
                warmup_scheduler = torch.optim.lr_scheduler.LambdaLR(
                    optimizer,
                    lr_lambda=lambda epoch: min(1.0, (epoch + 1) / warmup_epochs)
                )
                # Stochastic Weight Averaging (SWA) setup
                from torch.optim.swa_utils import AveragedModel, SWALR, update_bn
                swa_model = AveragedModel(model)
                swa_start = max(40, epochs // 2)  # Start SWA halfway or at epoch 40
                swa_active = False

                # SmoothL1Loss (Huber) for all strategies — all use forward-looking
                # targets which are inherently noisy; Huber is more robust than MSE
                # beta=0.1: sharper L1→L2 transition for [-1,1] range targets
                base_criterion = nn.SmoothL1Loss(beta=0.1)
                val_criterion = nn.SmoothL1Loss(beta=0.1)

                # Trading cost constants for loss penalty
                TRADE_FEE = 0.0005     # 0.05%
                TRADE_SLIPPAGE = 0.0008  # 0.08%
                ROUND_TRIP_COST = 2 * (TRADE_FEE + TRADE_SLIPPAGE)  # 0.26%

                # Training loop with mixed precision (AMP)
                best_val_loss = float('inf')
                patience_counter = 0
                # Per-strategy early stopping patience
                strategy_patience = {
                    StrategyType.ARBITRAGE: 25,
                    StrategyType.FIBONACCI: 25,
                    StrategyType.GRID: 15,              # shorter forward window, converges faster
                    StrategyType.DCA: 25,
                    StrategyType.MEAN_REVERSION: 15,     # shorter forward window like grid
                    StrategyType.PAIRS_ARBITRAGE: 30,    # needs more exploration
                    StrategyType.MOMENTUM: 30,           # longer horizon, needs more patience
                }
                patience = strategy_patience.get(strategy, 25)
                min_delta = 0.0005
                epoch_results = []
                use_amp = use_cuda
                scaler = torch.amp.GradScaler('cuda', enabled=use_amp) if use_amp else None

                # MLflow: start run for this pair/exchange
                _mlflow_run = None
                if _mlflow_ok:
                    try:
                        _mlflow_run = mlflow.start_run(
                            run_name=f"{strategy.value}_{pair.replace('/', '_')}_{exchange}",
                            tags={
                                "strategy": strategy.value,
                                "pair": pair,
                                "exchange": exchange,
                                "version": "wave7",
                            },
                        )
                        mlflow.log_params({
                            "epochs": epochs,
                            "batch_size": batch_size,
                            "learning_rate": effective_lr,
                            "seq_len": seq_len,
                            "n_features": n_features,
                            "forward_window": forward_window,
                        })
                    except Exception as e:
                        logger.warning(f"MLflow run start failed: {e}")
                        _mlflow_run = None

                model.train()
                for epoch in range(epochs):
                    # Train
                    model.train()
                    train_loss = 0.0
                    for batch_data in train_loader:
                        if len(batch_data) == 3:
                            batch_x, batch_y, batch_w = batch_data
                            batch_w = batch_w.to(device, non_blocking=True)
                        else:
                            batch_x, batch_y = batch_data
                            batch_w = None
                        batch_x = batch_x.to(device, non_blocking=True)
                        batch_y = batch_y.to(device, non_blocking=True)
                        # Gaussian noise augmentation (training only)
                        if model.training:
                            noise = torch.randn_like(batch_x) * 0.02
                            # Don't corrupt session one-hot features (last 6 channels, indices 11-16)
                            noise[:, :, 11:] = 0
                            batch_x = batch_x + noise
                        # Temporal dropout: randomly zero 10% of timesteps during training
                        if model.training:
                            temporal_mask = (torch.rand(batch_x.shape[0], batch_x.shape[1], 1, device=device) > 0.1).float()
                            batch_x = batch_x * temporal_mask
                        optimizer.zero_grad(set_to_none=True)
                        with torch.amp.autocast('cuda', enabled=use_amp):
                            output = model(batch_x)
                            if batch_w is not None:
                                # Weighted SmoothL1 loss (session regime + ADX weighting)
                                per_elem = torch.nn.functional.smooth_l1_loss(
                                    output, batch_y, reduction='none', beta=0.1
                                )
                                mse = (batch_w.view(-1, 1) * per_elem).mean()
                            else:
                                mse = base_criterion(output, batch_y)
                            # Fee+slippage cost penalty on signal strength
                            cost_penalty = ROUND_TRIP_COST * torch.abs(output[:, 0]).mean()
                            loss = mse + cost_penalty
                        if scaler:
                            scaler.scale(loss).backward()
                            scaler.unscale_(optimizer)
                            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                            scaler.step(optimizer)
                            scaler.update()
                        else:
                            loss.backward()
                            grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
                            optimizer.step()
                        train_loss += loss.item()

                    train_loss /= max(len(train_loader), 1)

                    # Log gradient norm every 10 epochs for monitoring
                    if epoch % 10 == 0:
                        logger.info(f"  Epoch {epoch}: grad_norm={grad_norm:.4f}")

                    # Validate (with same cost penalty as training for consistency)
                    model.eval()
                    val_loss = 0.0
                    with torch.no_grad():
                        for batch_x, batch_y in val_loader:
                            batch_x, batch_y = batch_x.to(device, non_blocking=True), batch_y.to(device, non_blocking=True)
                            with torch.amp.autocast('cuda', enabled=use_amp):
                                output = model(batch_x)
                                v_mse = val_criterion(output, batch_y)
                                v_cost_penalty = ROUND_TRIP_COST * torch.abs(output[:, 0]).mean()
                                val_loss += (v_mse + v_cost_penalty).item()

                    val_loss /= max(len(val_loader), 1)

                    # Learning rate scheduling: warmup then plateau
                    if epoch < warmup_epochs:
                        warmup_scheduler.step()
                    else:
                        scheduler.step(val_loss)

                    # Stochastic Weight Averaging
                    if epoch >= swa_start:
                        swa_model.update_parameters(model)
                        swa_active = True

                    epoch_results.append({
                        "epoch": epoch + 1,
                        "train_loss": train_loss,
                        "val_loss": val_loss,
                    })

                    # MLflow: log epoch metrics
                    if _mlflow_run:
                        try:
                            current_lr = optimizer.param_groups[0]['lr']
                            mlflow.log_metrics({
                                "train_loss": train_loss,
                                "val_loss": val_loss,
                                "risk_score": _compute_training_risk_score(epoch_results),
                                "learning_rate": current_lr,
                            }, step=epoch + 1)
                        except Exception:
                            pass  # Non-blocking

                    # Risk scoring: pause if training becomes unstable
                    risk_score = _compute_training_risk_score(epoch_results)
                    if risk_score > 0.65:
                        logger.warning(
                            f"Risk score {risk_score:.3f} > 0.65 at epoch {epoch + 1} "
                            f"for {pair}@{exchange}, pausing training"
                        )
                        break

                    # Early stopping (min_delta=0.0005)
                    if val_loss < best_val_loss - min_delta:
                        best_val_loss = val_loss
                        patience_counter = 0
                        # Save best model with exchange in filename
                        pair_slug = pair.replace('/', '_').lower()
                        save_path = Path(save_dir) / f"{strategy.value}_{pair_slug}_{exchange}.pth"
                        torch.save({
                            "model_state_dict": model.state_dict(),
                            "config": {
                                "strategy": strategy.value,
                                "pair": pair,
                                "exchange": exchange,
                                "input_size": n_features,
                                "output_size": output_size,
                                "seq_len": seq_len,
                            },
                            "epoch": epoch + 1,
                            "val_loss": val_loss,
                            "timestamp": datetime.now().isoformat(),
                        }, save_path)
                        best_epoch = epoch + 1
                        # Save training metadata alongside model checkpoint
                        metadata = {
                            'strategy': strategy.value,
                            'pair': pair,
                            'exchange': exchange,
                            'best_epoch': best_epoch,
                            'best_val_loss': float(best_val_loss),
                            'total_epochs': epoch + 1,
                            'learning_rate': effective_lr,
                            'seq_len': seq_len,
                            'timestamp': datetime.now().isoformat(),
                            'forward_window': forward_window,
                        }
                        metadata_path = str(save_path).replace('.pth', '_meta.json')
                        with open(metadata_path, 'w') as f:
                            json.dump(metadata, f, indent=2)
                    else:
                        patience_counter += 1
                        if patience_counter >= patience:
                            logger.info(f"Early stopping at epoch {epoch + 1} for {pair} on {exchange}")
                            break

                    if (epoch + 1) % 20 == 0:
                        logger.info(
                            f"  {pair}@{exchange} epoch {epoch + 1}/{epochs}: "
                            f"train_loss={train_loss:.6f}, val_loss={val_loss:.6f}, "
                            f"risk={risk_score:.3f}"
                        )

                # Apply SWA if it was active
                if swa_active:
                    try:
                        update_bn(train_loader, swa_model, device=device)
                        # Use SWA model for final checkpoint
                        model = swa_model.module
                        logger.info("SWA applied to final model")
                    except Exception as e:
                        logger.warning(f"SWA BN update failed, using non-SWA model: {e}")

                # MLflow: log final metrics and model artifact, then end run
                if _mlflow_run:
                    try:
                        early_stop_epoch = len(epoch_results)
                        mlflow.log_metrics({
                            "best_val_loss": best_val_loss,
                            "total_epochs": early_stop_epoch,
                            "early_stop_epoch": early_stop_epoch,
                        })
                        # Log saved model artifact
                        pair_slug_mlf = pair.replace('/', '_').lower()
                        model_path_mlf = Path(save_dir) / f"{strategy.value}_{pair_slug_mlf}_{exchange}.pth"
                        if model_path_mlf.exists():
                            mlflow.log_artifact(str(model_path_mlf))
                    except Exception as e:
                        logger.warning(f"MLflow final logging failed: {e}")
                    try:
                        mlflow.end_run()
                    except Exception:
                        pass
                    _mlflow_run = None

                results[result_key] = {
                    "status": "trained",
                    "strategy": strategy.value,
                    "exchange": exchange,
                    "best_val_loss": best_val_loss,
                    "epochs_completed": len(epoch_results),
                    "samples": min_len,
                    "epoch_results": epoch_results,
                }
                logger.info(f"Finished {strategy.value} for {pair}@{exchange}: val_loss={best_val_loss:.6f}")

                # Record in knowledge graph
                if kg:
                    try:
                        run_id = f"{strategy.value}_{pair.replace('/', '_').lower()}_{exchange}_{datetime.now().strftime('%Y%m%d%H%M')}"
                        kg.record_training_run(
                            run_id=run_id, strategy=strategy.value,
                            pair=pair, exchange=exchange,
                            metrics={"val_loss": best_val_loss, "epochs": len(epoch_results)},
                            timestamp=datetime.now().isoformat()
                        )
                        kg.save()
                    except Exception as e:
                        logger.warning(f"Knowledge graph recording failed: {e}")

            except Exception as e:
                logger.error(f"Training failed for {pair} on {exchange}: {e}")
                results[result_key] = {"status": "failed", "error": str(e), "exchange": exchange}
                # End MLflow run on failure
                if _mlflow_ok:
                    try:
                        mlflow.end_run(status="FAILED")
                    except Exception:
                        pass

    return results


def _compute_training_risk_score(epoch_results: List[Dict]) -> float:
    """Compute training risk score (0.0-1.0) from recent epoch trajectory.

    Score > 0.65 indicates training instability and should trigger a pause.
    """
    if len(epoch_results) < 3:
        return 0.0

    recent = epoch_results[-min(5, len(epoch_results)):]
    val_losses = [e.get("val_loss", 0) for e in recent]
    train_losses = [e.get("train_loss", 0) for e in recent]

    avg_val = np.mean(val_losses) if val_losses else 0
    avg_train = np.mean(train_losses) if train_losses else 0

    # Factor 1: Val/train divergence (overfitting indicator)
    divergence = min(1.0, max(0, avg_val - avg_train) / (avg_train + 1e-10))

    # Factor 2: Val loss upward trend
    if len(val_losses) >= 3:
        trend = (val_losses[-1] - val_losses[0]) / (abs(val_losses[0]) + 1e-10)
        trend = min(1.0, max(0.0, trend))
    else:
        trend = 0.0

    # Factor 3: Absolute magnitude (high val_loss = bad)
    magnitude = min(1.0, avg_val / 1.0)

    return float(0.4 * divergence + 0.3 * trend + 0.3 * magnitude)


def _load_best_donor_model(
    strategy: 'StrategyType', pair: str, current_exchange: str,
    exchange_dirs: List[Tuple[str, str]], save_dir: str,
    device: torch.device
) -> Optional[Dict]:
    """Load the best donor model for transfer learning.

    Searches for same strategy+pair on different exchanges, returns
    the state_dict of the model with lowest val_loss.
    """
    pair_slug = pair.replace('/', '_').lower()
    best_state = None
    best_val_loss = float('inf')

    for ex_name, _ in exchange_dirs:
        if ex_name == current_exchange:
            continue
        model_path = Path(save_dir) / f"{strategy.value}_{pair_slug}_{ex_name}.pth"
        if model_path.exists():
            try:
                checkpoint = torch.load(model_path, map_location=device, weights_only=True)
                vl = checkpoint.get("val_loss", float("inf"))
                if vl < best_val_loss:
                    best_val_loss = vl
                    best_state = checkpoint["model_state_dict"]
                    logger.info(f"Found donor model: {model_path} (val_loss={vl:.6f})")
            except Exception as e:
                logger.warning(f"Failed to load donor {model_path}: {e}")

    return best_state


def _load_pair_data(pair: str, data_dir: str) -> Optional[np.ndarray]:
    """Load OHLCV data for a trading pair from CSV.

    Looks for files like: data/XRP_USDC_1h.csv or data/xrp_usdc.csv
    Expected columns: timestamp, open, high, low, close, volume
    """
    pair_slug = pair.replace('/', '_')

    candidates = [
        f"{pair_slug}_5m.csv",
        f"{pair_slug}_1h.csv",
        f"{pair_slug}.csv",
        f"{pair_slug.lower()}_5m.csv",
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
                    ohlcv = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']]
                    # Convert string timestamps to numeric
                    if ohlcv['timestamp'].dtype == object or ohlcv['timestamp'].dtype.name == 'str':
                        ohlcv = ohlcv.copy()
                        ohlcv['timestamp'] = pd.to_datetime(ohlcv['timestamp']).astype('int64') // 10**9
                    arr = ohlcv.values.astype(np.float64)
                    # Filter out rows with inf, NaN, or unrealistic prices
                    valid_mask = np.all(np.isfinite(arr[:, 1:6]), axis=1)
                    # Sanity: remove rows where OHLC prices are <= 0 or volume < 0
                    valid_mask &= np.all(arr[:, 1:5] > 0, axis=1)
                    valid_mask &= arr[:, 5] >= 0
                    # Remove exponentially blown-up synthetic data:
                    # Use first few rows as reference — if price drifts > 10x, it's synthetic
                    prices = arr[valid_mask, 4]  # close column of valid rows
                    if len(prices) > 10:
                        ref_price = np.median(prices[:10])
                        if ref_price > 0:
                            valid_mask &= arr[:, 4] < ref_price * 10
                            valid_mask &= arr[:, 4] > ref_price * 0.1
                    arr = arr[valid_mask]
                    if len(arr) < len(ohlcv):
                        logger.info(f"Filtered {len(ohlcv) - len(arr)} bad rows from {filepath.name} "
                                    f"({len(arr)} clean rows remain)")
                    if len(arr) < 50:
                        logger.warning(f"Too few clean rows ({len(arr)}) in {filepath.name}, skipping")
                        return None
                    return arr
            except Exception as e:
                logger.warning(f"Failed to load {filepath}: {e}")

    logger.warning(f"No data file found for {pair} in {data_dir}")
    return None


# ── Convenience: Train All Strategies ─────────────────────────────────────

def train_all_strategies(
    pairs: List[str],
    data_dir: str = "data/historical/binance",
    exchanges: Optional[List[str]] = None,
    epochs: int = 100,
    batch_size: int = 96,
    save_dir: str = "models/strategies",
) -> Dict[str, Dict[str, Any]]:
    """Train all 7 strategies for all pairs across all exchanges.

    Returns: {strategy_name: {pair:exchange: result}}
    """
    all_results = {}
    for strategy in StrategyType:
        logger.info(f"\n{'=' * 60}")
        logger.info(f"Training {strategy.value.upper()} strategy")
        logger.info(f"{'=' * 60}")
        results = train_strategy_model(
            strategy=strategy,
            pairs=pairs,
            data_dir=data_dir,
            exchanges=exchanges,
            epochs=epochs,
            batch_size=batch_size,
            save_dir=save_dir,
        )
        all_results[strategy.value] = results

    return all_results
