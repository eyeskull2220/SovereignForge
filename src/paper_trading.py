#!/usr/bin/env python3
"""
SovereignForge - Paper Trading Engine
Simulated trading using trained strategy models with live exchange data.

Usage:
    python src/paper_trading.py --start                  # Start paper trading loop
    python src/paper_trading.py --start --balance 50000  # Start with $50,000
    python src/paper_trading.py --status                 # Show portfolio & positions
    python src/paper_trading.py --history                # Show trade history
    python src/paper_trading.py --balance 25000          # Set balance (without --start, just saves config)
"""

import argparse
import asyncio
import json
import logging
import math
import os
import random
import signal
import sys
import time
import traceback
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(PROJECT_ROOT))

import torch

# Local imports (deferred where needed to avoid hard crashes)
from multi_strategy_training import (
    StrategyType,
    TradingGRU,
    TradingLSTM,
    TradingTransformer,
    create_gru_model,
    create_lstm_model,
    create_transformer_model,
)
from session_regime import compute_adx, session_one_hot

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MICA_PAIRS = [
    "BTC/USDC", "ETH/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC",
    "ALGO/USDC", "ADA/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
    "XDC/USDC", "ONDO/USDC",
]

EXCHANGES = ["binance", "coinbase", "kraken", "okx"]

STRATEGIES = ["arbitrage", "fibonacci", "grid", "dca"]

STRATEGY_MODELS = {
    "arbitrage": create_lstm_model,
    "fibonacci": create_transformer_model,
    "grid": create_gru_model,
    "dca": create_lstm_model,
}

# Strategy weights from trading_config.json
STRATEGY_WEIGHTS = {
    "arbitrage": 0.4,
    "fibonacci": 0.2,
    "grid": 0.2,
    "dca": 0.2,
}

INPUT_DIM = 17
OUTPUT_SIZE = 3  # signal, confidence, magnitude
SEQ_LEN = 128

FEE_RANGE = (0.0004, 0.0008)       # 0.04% - 0.08%
SLIPPAGE_RANGE = (0.0005, 0.0015)   # 0.05% - 0.15%

# Exchange-specific fee schedules (taker fees for market orders)
EXCHANGE_FEES = {
    "binance":  {"maker": 0.001, "taker": 0.001},
    "coinbase": {"maker": 0.004, "taker": 0.006},
    "kraken":   {"maker": 0.0016, "taker": 0.0026},
    "okx":      {"maker": 0.0008, "taker": 0.001},
}

# Network transfer fees (USDC) for cross-exchange arbitrage
TRANSFER_FEES = {
    "binance":  1.0,   # ~$1 USDC withdrawal
    "coinbase": 0.0,   # Free USDC transfers
    "kraken":   2.5,   # ~$2.50
    "okx":      1.0,   # ~$1
}

MAX_POSITION_PCT = 0.05             # 5% of portfolio per trade
MAX_POSITIONS_PER_PAIR = 3
SIGNAL_THRESHOLD = 0.3
CONFIDENCE_THRESHOLD = 0.5
STOP_LOSS_PCT = 0.02                # 2% stop loss
TAKE_PROFIT_PCT = 0.03              # 3% take profit
MAX_DAILY_LOSS_PCT = 0.05           # 5% daily loss circuit breaker

LOG_DIR = PROJECT_ROOT / "logs"
REPORT_DIR = PROJECT_ROOT / "reports"
STATE_FILE = REPORT_DIR / "paper_trading_state.json"

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

LOG_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("paper_trading")
logger.setLevel(logging.DEBUG)

_fh = logging.FileHandler(LOG_DIR / "paper_trading.log", encoding="utf-8")
_fh.setLevel(logging.DEBUG)
_fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_fh)

_ch = logging.StreamHandler()
_ch.setLevel(logging.INFO)
_ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
logger.addHandler(_ch)


# ---------------------------------------------------------------------------
# Feature engineering (self-contained replica of multi_strategy_training)
# ---------------------------------------------------------------------------

def _compute_rsi(close: np.ndarray, period: int = 14) -> np.ndarray:
    rsi = np.zeros_like(close)
    deltas = np.diff(close)
    for i in range(period, len(close)):
        gains = np.maximum(deltas[i - period:i], 0)
        losses = np.abs(np.minimum(deltas[i - period:i], 0))
        avg_gain = np.mean(gains) + 1e-10
        avg_loss = np.mean(losses) + 1e-10
        rs = avg_gain / avg_loss
        rsi[i] = (2 * rs / (1 + rs)) - 1
    return rsi


def _ema(data: np.ndarray, period: int) -> np.ndarray:
    result = np.zeros_like(data)
    result[0] = data[0]
    alpha = 2 / (period + 1)
    for i in range(1, len(data)):
        result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
    return result


def _compute_macd(close: np.ndarray) -> np.ndarray:
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    std = np.std(macd) + 1e-10
    return macd / std


def _compute_bb_position(close: np.ndarray, period: int = 20) -> np.ndarray:
    bb_pos = np.zeros_like(close)
    for i in range(period, len(close)):
        window = close[i - period:i]
        mean = np.mean(window)
        std = np.std(window) + 1e-10
        bb_pos[i] = (close[i] - mean) / (2 * std)
    return np.clip(bb_pos, -1, 1)


def engineer_features(ohlcv: np.ndarray, seq_len: int = SEQ_LEN) -> Tuple[np.ndarray, int]:
    """Build 17-feature sequences from OHLCV array.

    Input columns: [timestamp, open, high, low, close, volume]
    Returns: (sequences [N, seq_len, 17], 17)
    """
    N_FEATURES = 17
    if len(ohlcv) < seq_len + 1:
        return np.empty((0, seq_len, N_FEATURES)), N_FEATURES

    timestamps = ohlcv[:, 0].astype(float)
    open_price = ohlcv[:, 1].astype(float)
    high = ohlcv[:, 2].astype(float)
    low = ohlcv[:, 3].astype(float)
    close = ohlcv[:, 4].astype(float)
    volume = ohlcv[:, 5].astype(float)

    N = len(close)

    # Feature 1: returns
    returns = np.diff(close) / (close[:-1] + 1e-10)
    returns = np.concatenate([[0], returns])

    # Feature 2: log volume ratio
    vol_mean = np.mean(volume) + 1e-10
    log_vol_ratio = np.log(volume / vol_mean + 1e-10)

    # Feature 3: high-low range
    hl_range = (high - low) / (close + 1e-10)

    # Feature 4: close-open direction
    co_direction = (close - open_price) / (open_price + 1e-10)

    # Feature 5: RSI
    rsi = _compute_rsi(close, period=14)

    # Feature 6: MACD
    macd = _compute_macd(close)

    # Feature 7: Bollinger Band position
    bb_pos = _compute_bb_position(close, period=20)

    # Feature 8: volume momentum
    vol_cumsum = np.cumsum(np.insert(volume, 0, 0))
    vol_ma5 = np.zeros_like(volume)
    if N > 5:
        vol_ma5[5:] = (vol_cumsum[6:] - vol_cumsum[1:N - 4]) / 5.0
    vol_mom = np.where(vol_ma5 > 1e-10, (volume - vol_ma5) / vol_ma5, 0.0)

    # Feature 9: price momentum
    price_mom = np.zeros_like(close)
    if N > 10:
        price_mom[10:] = (close[10:] - close[:-10]) / (close[:-10] + 1e-10)

    # Feature 10: volatility
    ret_cumsum = np.cumsum(np.insert(returns, 0, 0))
    ret_sq_cumsum = np.cumsum(np.insert(returns ** 2, 0, 0))
    volatility = np.zeros_like(close)
    n_win = 20
    if N > n_win:
        mean_r = (ret_cumsum[n_win + 1:] - ret_cumsum[1:N - n_win + 1]) / n_win
        mean_r2 = (ret_sq_cumsum[n_win + 1:] - ret_sq_cumsum[1:N - n_win + 1]) / n_win
        volatility[n_win:] = np.sqrt(np.maximum(mean_r2 - mean_r ** 2, 0))

    # Feature 11: ADX
    adx = compute_adx(high, low, close, period=14)
    adx_normalized = adx / 100.0

    # Features 12-17: session one-hot
    sess_onehot = session_one_hot(timestamps)

    features = np.column_stack([
        returns, log_vol_ratio, hl_range, co_direction,
        rsi, macd, bb_pos, vol_mom, price_mom, volatility,
        adx_normalized, sess_onehot,
    ])

    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    # Normalize first 11 numeric features
    col_mean = features[:, :11].mean(axis=0)
    col_std = features[:, :11].std(axis=0)
    col_std[col_std < 1e-10] = 1.0
    features[:, :11] = (features[:, :11] - col_mean) / col_std

    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    sequences = []
    for i in range(seq_len, len(features)):
        sequences.append(features[i - seq_len:i])

    if not sequences:
        return np.empty((0, seq_len, N_FEATURES)), N_FEATURES
    return np.array(sequences), N_FEATURES


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PaperPosition:
    id: str
    pair: str
    exchange: str
    strategy: str
    side: str               # "buy" or "sell"
    size_usdc: float        # position value in USDC
    quantity: float          # base asset quantity
    entry_price: float
    stop_loss: float
    take_profit: float
    entry_time: str
    fee: float              # total fee paid at entry
    slippage: float         # slippage applied at entry

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class ClosedTrade:
    id: str
    pair: str
    exchange: str
    strategy: str
    side: str
    size_usdc: float
    quantity: float
    entry_price: float
    exit_price: float
    entry_time: str
    exit_time: str
    pnl: float
    pnl_pct: float
    fee_entry: float
    fee_exit: float
    slippage_entry: float
    slippage_exit: float
    reason: str             # "take_profit", "stop_loss", "signal_exit", "manual"
    duration_minutes: float

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items()}


@dataclass
class SignalResult:
    pair: str
    exchange: str
    strategy: str
    signal: float          # [-1, 1] (tanh output)
    confidence: float      # [0, 1] (sigmoid)
    magnitude: float       # [0, 1] (sigmoid)
    timestamp: str


# ---------------------------------------------------------------------------
# Paper Trading Engine
# ---------------------------------------------------------------------------

class PaperTradingEngine:
    """Simulated trading engine using trained strategy models and live OHLCV data."""

    def __init__(self, starting_balance: float = 10_000.0):
        self.starting_balance = starting_balance
        self.balance = starting_balance
        self.positions: Dict[str, PaperPosition] = {}   # id -> PaperPosition
        self.trade_history: List[ClosedTrade] = []
        self.signal_log: List[Dict[str, Any]] = []
        self.skipped_signals: List[Dict[str, Any]] = []
        self.equity_curve: List[Tuple[str, float]] = []

        # Daily tracking
        self._day_start_balance = starting_balance
        self._current_day = datetime.now(timezone.utc).date()

        # Peak tracking for drawdown
        self._peak_equity = starting_balance

        # Loaded models: (strategy, pair, exchange) -> model
        self._models: Dict[Tuple[str, str, str], torch.nn.Module] = {}
        self._device = "cuda" if torch.cuda.is_available() else "cpu"

        # OHLCV buffers: (pair, exchange) -> list of [ts, o, h, l, c, v]
        self._ohlcv_buffers: Dict[Tuple[str, str], np.ndarray] = {}

        # Model performance tracking for concept drift detection
        self._model_performance: Dict[Tuple[str, str, str], List[Dict]] = {}  # (strategy, pair, exchange) -> list of {predicted, actual, timestamp}

        # Trade counter for unique IDs
        self._trade_counter = 0

        # Shutdown flag
        self._running = False

        # Load enabled pairs/strategies/exchanges from config
        self._enabled_pairs = list(MICA_PAIRS)
        self._enabled_strategies = list(STRATEGIES)
        self._enabled_exchanges = list(EXCHANGES)
        self._reload_config()

        logger.info(
            f"PaperTradingEngine initialized: balance=${starting_balance:,.2f}, "
            f"device={self._device}, pairs={len(self._enabled_pairs)}, "
            f"strategies={len(self._enabled_strategies)}, exchanges={len(self._enabled_exchanges)}"
        )

    # ------------------------------------------------------------------
    # Config reload
    # ------------------------------------------------------------------

    def _reload_config(self) -> None:
        """Reload enabled pairs/strategies/exchanges from trading_config.json."""
        config_path = PROJECT_ROOT / "config" / "trading_config.json"
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            # Enabled pairs
            ep = cfg.get("trading", {}).get("enabled_pairs")
            if ep and isinstance(ep, list):
                self._enabled_pairs = [p for p in ep if p in MICA_PAIRS]
            # Enabled strategies
            strats = cfg.get("strategies", {})
            if strats:
                self._enabled_strategies = [
                    s for s in STRATEGIES if strats.get(s, {}).get("enabled", True)
                ]
            # Enabled exchanges
            exs = cfg.get("cross_exchange", {}).get("exchanges")
            if exs and isinstance(exs, list):
                self._enabled_exchanges = [e for e in exs if e in EXCHANGES]
            logger.info(
                f"Config reloaded: {len(self._enabled_pairs)} pairs, "
                f"{len(self._enabled_strategies)} strategies, "
                f"{len(self._enabled_exchanges)} exchanges"
            )
        except Exception as e:
            logger.warning(f"Failed to reload config: {e}, using defaults")

    # ------------------------------------------------------------------
    # Model loading
    # ------------------------------------------------------------------

    def load_models(self) -> Dict[str, bool]:
        """Load all available trained models from models/strategies/.

        Model naming: {strategy}_{coin}_usdc_{exchange}.pth
        """
        models_dir = PROJECT_ROOT / "models" / "strategies"
        results: Dict[str, bool] = {}

        for strategy in self._enabled_strategies:
            for pair in self._enabled_pairs:
                for exchange in self._enabled_exchanges:
                    coin = pair.split("/")[0].lower()
                    model_name = f"{strategy}_{coin}_usdc_{exchange}.pth"
                    model_path = models_dir / model_name
                    key = f"{strategy}:{pair}:{exchange}"

                    if not model_path.exists():
                        results[key] = False
                        continue

                    try:
                        factory = STRATEGY_MODELS[strategy]
                        model = factory(INPUT_DIM, OUTPUT_SIZE)
                        checkpoint = torch.load(
                            str(model_path),
                            map_location=self._device,
                            weights_only=True,
                        )
                        if isinstance(checkpoint, dict) and "model_state_dict" in checkpoint:
                            model.load_state_dict(checkpoint["model_state_dict"])
                        else:
                            model.load_state_dict(checkpoint)

                        model.to(self._device)
                        model.eval()
                        self._models[(strategy, pair, exchange)] = model
                        results[key] = True
                        logger.debug(f"Loaded model: {key}")

                    except Exception as exc:
                        logger.warning(f"Failed to load {key}: {exc}")
                        results[key] = False

        loaded = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"Models loaded: {loaded}/{total}")
        return results

    # ------------------------------------------------------------------
    # Live data fetching (ccxt)
    # ------------------------------------------------------------------

    async def _init_exchanges(self) -> Dict[str, Any]:
        """Create ccxt exchange instances."""
        import ccxt.async_support as ccxt

        instances: Dict[str, Any] = {}
        exchange_classes = {
            "binance": ccxt.binance,
            "coinbase": ccxt.coinbase,
            "kraken": ccxt.kraken,
            "okx": ccxt.okx,
        }

        for name, cls in exchange_classes.items():
            try:
                ex = cls({"enableRateLimit": True})
                instances[name] = ex
                logger.debug(f"Exchange {name} initialized")
            except Exception as exc:
                logger.warning(f"Failed to init {name}: {exc}")

        return instances

    async def _fetch_ohlcv(
        self,
        exchange_instance: Any,
        exchange_name: str,
        pair: str,
        limit: int = SEQ_LEN + 10,
        max_retries: int = 3,
    ) -> Optional[np.ndarray]:
        """Fetch OHLCV candles with retry + backoff. Returns array [N, 6]."""
        ccxt_symbol = pair  # ccxt uses "BTC/USDC" directly

        for attempt in range(max_retries):
            try:
                candles = await exchange_instance.fetch_ohlcv(
                    ccxt_symbol, timeframe="5m", limit=limit
                )
                if candles and len(candles) >= SEQ_LEN:
                    return np.array(candles, dtype=np.float64)
                else:
                    logger.debug(
                        f"{exchange_name} {pair}: insufficient candles "
                        f"({len(candles) if candles else 0}/{SEQ_LEN})"
                    )
                    return None

            except Exception as exc:
                wait = 2 ** attempt + random.random()
                logger.warning(
                    f"{exchange_name} {pair} fetch failed (attempt {attempt + 1}): "
                    f"{exc} — retrying in {wait:.1f}s"
                )
                await asyncio.sleep(wait)

        logger.error(f"{exchange_name} {pair}: all fetch attempts failed")
        return None

    async def fetch_all_ohlcv(self, exchanges: Dict[str, Any]) -> int:
        """Fetch OHLCV for all pair/exchange combos concurrently.

        Returns the number of successfully fetched buffers.
        """
        tasks = []
        keys = []

        for exchange_name, ex_instance in exchanges.items():
            if exchange_name not in self._enabled_exchanges:
                continue
            for pair in self._enabled_pairs:
                keys.append((pair, exchange_name))
                tasks.append(
                    self._fetch_ohlcv(ex_instance, exchange_name, pair)
                )

        results = await asyncio.gather(*tasks, return_exceptions=True)

        count = 0
        for (pair, exchange_name), result in zip(keys, results):
            if isinstance(result, Exception):
                logger.warning(f"Exception fetching {pair} on {exchange_name}: {result}")
                continue
            if result is not None:
                self._ohlcv_buffers[(pair, exchange_name)] = result
                count += 1

        logger.info(f"Fetched OHLCV for {count}/{len(keys)} pair-exchange combos")
        return count

    # ------------------------------------------------------------------
    # OHLCV validation
    # ------------------------------------------------------------------

    def _validate_ohlcv(self, candles: np.ndarray, pair: str, exchange: str) -> bool:
        """Validate OHLCV data sanity before using for inference."""
        if candles is None or len(candles) < SEQ_LEN:
            return False

        # Check for NaN/Inf
        if np.any(np.isnan(candles)) or np.any(np.isinf(candles)):
            logger.warning(f"NaN/Inf in OHLCV data for {pair}@{exchange}")
            return False

        # Columns: [timestamp, open, high, low, close, volume]
        opens = candles[:, 1]
        highs = candles[:, 2]
        lows = candles[:, 3]
        closes = candles[:, 4]
        volumes = candles[:, 5]

        # Check OHLC consistency: low <= open/close <= high
        if np.any(lows > highs):
            logger.warning(f"OHLC inconsistency (low > high) for {pair}@{exchange}")
            return False

        # Check for zero/negative prices
        if np.any(closes <= 0) or np.any(opens <= 0):
            logger.warning(f"Zero/negative prices for {pair}@{exchange}")
            return False

        # Check for extreme price gaps (>50% in a single candle)
        pct_changes = np.abs(np.diff(closes) / closes[:-1])
        if np.any(pct_changes > 0.5):
            logger.warning(f"Extreme price gap detected for {pair}@{exchange}: max={pct_changes.max():.2%}")
            return False

        return True

    # ------------------------------------------------------------------
    # Model performance / concept drift tracking
    # ------------------------------------------------------------------

    def _track_model_performance(self, strategy: str, pair: str, exchange: str,
                                  predicted_signal: float, predicted_confidence: float):
        """Track model prediction for later accuracy evaluation."""
        key = (strategy, pair, exchange)
        if key not in self._model_performance:
            self._model_performance[key] = []

        self._model_performance[key].append({
            "predicted_signal": predicted_signal,
            "predicted_confidence": predicted_confidence,
            "price_at_prediction": self._get_current_price(pair, exchange),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })

        # Keep rolling window of 100
        if len(self._model_performance[key]) > 100:
            self._model_performance[key] = self._model_performance[key][-100:]

    def _check_model_drift(self) -> List[Dict[str, Any]]:
        """Check all models for concept drift. Returns list of degraded models."""
        degraded = []
        for (strategy, pair, exchange), predictions in self._model_performance.items():
            if len(predictions) < 20:
                continue

            # Check if predictions have any predictive value
            # Compare predicted direction with actual price movement
            correct = 0
            total = 0
            for i in range(len(predictions) - 1):
                pred = predictions[i]
                next_pred = predictions[i + 1]
                if pred.get("price_at_prediction") and next_pred.get("price_at_prediction"):
                    actual_direction = 1 if next_pred["price_at_prediction"] > pred["price_at_prediction"] else -1
                    predicted_direction = 1 if pred["predicted_signal"] > 0 else -1
                    if actual_direction == predicted_direction:
                        correct += 1
                    total += 1

            if total >= 15:
                accuracy = correct / total
                if accuracy < 0.40:  # Worse than 40% — model is degraded
                    degraded.append({
                        "strategy": strategy,
                        "pair": pair,
                        "exchange": exchange,
                        "accuracy": round(accuracy, 3),
                        "samples": total,
                    })
                    logger.warning(
                        f"Model drift detected: {strategy}/{pair}@{exchange} "
                        f"accuracy={accuracy:.1%} over {total} predictions"
                    )

        return degraded

    # ------------------------------------------------------------------
    # Signal generation
    # ------------------------------------------------------------------

    def _run_inference(
        self, strategy: str, pair: str, exchange: str
    ) -> Optional[SignalResult]:
        """Run a single model inference. Returns None if model or data unavailable."""
        model = self._models.get((strategy, pair, exchange))
        if model is None:
            return None

        ohlcv = self._ohlcv_buffers.get((pair, exchange))
        if ohlcv is None or len(ohlcv) < SEQ_LEN + 1:
            return None

        # Validate OHLCV data before feature engineering
        if not self._validate_ohlcv(ohlcv, pair, exchange):
            return None

        # Engineer features (produces sequences)
        sequences, n_feat = engineer_features(ohlcv, seq_len=SEQ_LEN)
        if len(sequences) == 0:
            return None

        # Take the last sequence (most recent window)
        seq = sequences[-1:]  # [1, SEQ_LEN, 17]
        tensor = torch.from_numpy(seq).float().to(self._device)

        try:
            with torch.no_grad():
                output = model(tensor)  # [1, 3]

            if isinstance(output, tuple):
                # Some models (ArbitrageTransformer) return tuple
                raw = torch.cat([o.squeeze(-1) if o.dim() > 1 else o for o in output], dim=-1)
            else:
                raw = output

            raw = raw.cpu().numpy().flatten()

            # Interpret outputs: signal (tanh), confidence (sigmoid), magnitude (sigmoid)
            signal_val = float(np.tanh(raw[0]))       # [-1, 1]
            confidence = float(1 / (1 + np.exp(-raw[1])))  # [0, 1]
            magnitude = float(1 / (1 + np.exp(-raw[2])))   # [0, 1]

            return SignalResult(
                pair=pair,
                exchange=exchange,
                strategy=strategy,
                signal=signal_val,
                confidence=confidence,
                magnitude=magnitude,
                timestamp=datetime.now(timezone.utc).isoformat(),
            )

        except Exception as exc:
            logger.error(f"Inference failed {strategy}:{pair}:{exchange}: {exc}")
            return None

    def generate_signals(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        """Generate ensemble signals for all pair/exchange combos.

        Aggregates across strategies using confidence-weighted averaging.
        Returns: {(pair, exchange): {signal, confidence, magnitude, strategies}}
        """
        aggregated: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Reload config each cycle to pick up toggle changes
        self._reload_config()

        for pair in self._enabled_pairs:
            for exchange in self._enabled_exchanges:
                signals: List[SignalResult] = []
                for strategy in self._enabled_strategies:
                    result = self._run_inference(strategy, pair, exchange)
                    if result is not None:
                        signals.append(result)
                        # Track per-model prediction for drift detection
                        self._track_model_performance(
                            strategy, pair, exchange,
                            result.signal, result.confidence,
                        )

                if not signals:
                    continue

                # Confidence-weighted ensemble
                total_weight = 0.0
                weighted_signal = 0.0
                weighted_magnitude = 0.0
                max_confidence = 0.0
                strategy_details = []

                for sig in signals:
                    w = sig.confidence * STRATEGY_WEIGHTS.get(sig.strategy, 0.25)
                    weighted_signal += sig.signal * w
                    weighted_magnitude += sig.magnitude * w
                    total_weight += w
                    max_confidence = max(max_confidence, sig.confidence)
                    strategy_details.append({
                        "strategy": sig.strategy,
                        "signal": round(sig.signal, 4),
                        "confidence": round(sig.confidence, 4),
                        "magnitude": round(sig.magnitude, 4),
                    })

                if total_weight > 0:
                    ens_signal = weighted_signal / total_weight
                    ens_magnitude = weighted_magnitude / total_weight
                else:
                    ens_signal = 0.0
                    ens_magnitude = 0.0

                # Average confidence across strategies
                avg_confidence = sum(s.confidence for s in signals) / len(signals)

                entry = {
                    "signal": ens_signal,
                    "confidence": avg_confidence,
                    "magnitude": ens_magnitude,
                    "strategies": strategy_details,
                    "n_strategies": len(signals),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }

                aggregated[(pair, exchange)] = entry

                self.signal_log.append({
                    "pair": pair,
                    "exchange": exchange,
                    **entry,
                })

        logger.info(f"Generated ensemble signals for {len(aggregated)} pair-exchange combos")
        return aggregated

    # ------------------------------------------------------------------
    # Trade execution (simulated)
    # ------------------------------------------------------------------

    def _count_positions_for_pair(self, pair: str) -> int:
        return sum(1 for p in self.positions.values() if p.pair == pair)

    def _get_current_price(self, pair: str, exchange: str) -> Optional[float]:
        """Get latest close price from OHLCV buffer."""
        ohlcv = self._ohlcv_buffers.get((pair, exchange))
        if ohlcv is None or len(ohlcv) == 0:
            return None
        return float(ohlcv[-1, 4])  # last close

    def _log_skipped(self, pair: str, exchange: str, sig: Dict[str, Any], reason: str):
        """Record a signal that was generated but not executed."""
        self.skipped_signals.append({
            "pair": pair,
            "exchange": exchange,
            "signal": round(sig.get("signal", 0), 4),
            "confidence": round(sig.get("confidence", 0), 4),
            "magnitude": round(sig.get("magnitude", 0), 4),
            "strategies": sig.get("strategies", []),
            "reject_reason": reason,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        })
        # Cap at 200
        if len(self.skipped_signals) > 200:
            self.skipped_signals = self.skipped_signals[-200:]

    def execute_signals(self, signals: Dict[Tuple[str, str], Dict[str, Any]]) -> int:
        """Execute trades based on ensemble signals. Returns number of new trades."""
        new_trades = 0

        # Check daily loss circuit breaker
        daily_loss_pct = (self._day_start_balance - self.balance) / self._day_start_balance
        if daily_loss_pct >= MAX_DAILY_LOSS_PCT:
            logger.warning(
                f"Daily loss circuit breaker triggered: {daily_loss_pct:.2%} >= "
                f"{MAX_DAILY_LOSS_PCT:.2%}. No new trades."
            )
            # Log all signals as skipped due to circuit breaker
            for (pair, exchange), sig in signals.items():
                self._log_skipped(pair, exchange, sig, "daily_loss_limit")
            return 0

        for (pair, exchange), sig in signals.items():
            signal_val = sig["signal"]
            confidence = sig["confidence"]
            magnitude = sig["magnitude"]

            # Risk thresholds
            if abs(signal_val) < SIGNAL_THRESHOLD:
                self._log_skipped(pair, exchange, sig, "weak_signal")
                continue
            if confidence < CONFIDENCE_THRESHOLD:
                self._log_skipped(pair, exchange, sig, "low_confidence")
                continue

            # Max positions per pair
            if self._count_positions_for_pair(pair) >= MAX_POSITIONS_PER_PAIR:
                self._log_skipped(pair, exchange, sig, "max_positions_reached")
                continue

            price = self._get_current_price(pair, exchange)
            if price is None or price <= 0:
                self._log_skipped(pair, exchange, sig, "no_price_data")
                continue

            side = "buy" if signal_val > 0 else "sell"

            # Position sizing: scale by magnitude and confidence, cap at MAX_POSITION_PCT
            raw_pct = MAX_POSITION_PCT * magnitude * confidence
            position_pct = min(raw_pct, MAX_POSITION_PCT)
            size_usdc = self.balance * position_pct

            if size_usdc < 1.0:
                self._log_skipped(pair, exchange, sig, "position_too_small")
                continue

            # Use exchange-specific taker fee (market orders)
            exchange_fees = EXCHANGE_FEES.get(exchange, {"maker": 0.001, "taker": 0.002})
            fee_rate = exchange_fees["taker"]
            slippage_rate = random.uniform(*SLIPPAGE_RANGE)

            fee = size_usdc * fee_rate
            slippage_cost = size_usdc * slippage_rate

            # Adjust effective entry price for slippage
            if side == "buy":
                effective_price = price * (1 + slippage_rate)
            else:
                effective_price = price * (1 - slippage_rate)

            quantity = (size_usdc - fee) / effective_price

            # Stop loss / take profit
            if side == "buy":
                stop_loss = effective_price * (1 - STOP_LOSS_PCT)
                take_profit = effective_price * (1 + TAKE_PROFIT_PCT)
            else:
                stop_loss = effective_price * (1 + STOP_LOSS_PCT)
                take_profit = effective_price * (1 - TAKE_PROFIT_PCT)

            # Deduct from balance
            self.balance -= (size_usdc + fee)

            self._trade_counter += 1
            pos_id = f"PT-{self._trade_counter:06d}"

            # Determine dominant strategy
            best_strategy = "ensemble"
            if sig.get("strategies"):
                best_strategy = max(
                    sig["strategies"],
                    key=lambda s: abs(s["signal"]) * s["confidence"]
                )["strategy"]

            position = PaperPosition(
                id=pos_id,
                pair=pair,
                exchange=exchange,
                strategy=best_strategy,
                side=side,
                size_usdc=size_usdc,
                quantity=quantity,
                entry_price=effective_price,
                stop_loss=stop_loss,
                take_profit=take_profit,
                entry_time=datetime.now(timezone.utc).isoformat(),
                fee=fee,
                slippage=slippage_cost,
            )

            self.positions[pos_id] = position
            new_trades += 1

            logger.info(
                f"OPEN {pos_id}: {side.upper()} {pair} on {exchange} | "
                f"qty={quantity:.6f} @ ${effective_price:.4f} | "
                f"size=${size_usdc:.2f} | SL=${stop_loss:.4f} TP=${take_profit:.4f} | "
                f"strategy={best_strategy} signal={signal_val:.3f} conf={confidence:.3f}"
            )

        return new_trades

    def check_exits(self) -> int:
        """Check all open positions for stop loss / take profit exits.

        Returns number of closed positions.
        """
        closed_ids = []

        for pos_id, pos in list(self.positions.items()):
            price = self._get_current_price(pos.pair, pos.exchange)
            if price is None:
                continue

            reason = None
            exit_price = price

            if pos.side == "buy":
                if price <= pos.stop_loss:
                    reason = "stop_loss"
                elif price >= pos.take_profit:
                    reason = "take_profit"
            else:  # sell / short
                if price >= pos.stop_loss:
                    reason = "stop_loss"
                elif price <= pos.take_profit:
                    reason = "take_profit"

            if reason is not None:
                self._close_position(pos_id, exit_price, reason)
                closed_ids.append(pos_id)

        return len(closed_ids)

    def _close_position(self, pos_id: str, exit_price: float, reason: str) -> Optional[ClosedTrade]:
        """Close a position and record the trade."""
        pos = self.positions.get(pos_id)
        if pos is None:
            return None

        # Use exchange-specific taker fee (market orders)
        exchange_fees = EXCHANGE_FEES.get(pos.exchange, {"maker": 0.001, "taker": 0.002})
        fee_rate = exchange_fees["taker"]
        slippage_rate = random.uniform(*SLIPPAGE_RANGE)

        if pos.side == "buy":
            effective_exit = exit_price * (1 - slippage_rate)
            pnl = (effective_exit - pos.entry_price) * pos.quantity
        else:
            effective_exit = exit_price * (1 + slippage_rate)
            pnl = (pos.entry_price - effective_exit) * pos.quantity

        exit_fee = abs(pnl + pos.size_usdc) * fee_rate if pnl > 0 else pos.size_usdc * fee_rate
        exit_fee = min(exit_fee, abs(pnl) * 0.5) if pnl != 0 else pos.size_usdc * fee_rate
        # Simpler: fee on notional
        exit_fee = pos.quantity * effective_exit * fee_rate
        pnl -= exit_fee

        pnl_pct = pnl / pos.size_usdc if pos.size_usdc > 0 else 0.0

        entry_dt = datetime.fromisoformat(pos.entry_time)
        exit_dt = datetime.now(timezone.utc)
        duration = (exit_dt - entry_dt).total_seconds() / 60.0

        trade = ClosedTrade(
            id=pos_id,
            pair=pos.pair,
            exchange=pos.exchange,
            strategy=pos.strategy,
            side=pos.side,
            size_usdc=pos.size_usdc,
            quantity=pos.quantity,
            entry_price=pos.entry_price,
            exit_price=effective_exit,
            entry_time=pos.entry_time,
            exit_time=exit_dt.isoformat(),
            pnl=pnl,
            pnl_pct=pnl_pct,
            fee_entry=pos.fee,
            fee_exit=exit_fee,
            slippage_entry=pos.slippage,
            slippage_exit=pos.quantity * exit_price * slippage_rate,
            reason=reason,
            duration_minutes=duration,
        )

        # Credit balance
        self.balance += pos.size_usdc + pnl
        self.trade_history.append(trade)
        del self.positions[pos_id]

        emoji_map = {"take_profit": "WIN", "stop_loss": "LOSS", "signal_exit": "EXIT"}
        tag = emoji_map.get(reason, reason.upper())

        logger.info(
            f"CLOSE {pos_id} [{tag}]: {pos.pair} on {pos.exchange} | "
            f"P&L=${pnl:+.2f} ({pnl_pct:+.2%}) | dur={duration:.0f}min | "
            f"entry=${pos.entry_price:.4f} exit=${effective_exit:.4f}"
        )

        return trade

    # ------------------------------------------------------------------
    # Metrics
    # ------------------------------------------------------------------

    def _equity(self) -> float:
        """Current equity = balance + unrealized P&L of open positions."""
        equity = self.balance
        for pos in self.positions.values():
            price = self._get_current_price(pos.pair, pos.exchange)
            if price is None:
                continue
            if pos.side == "buy":
                equity += (price - pos.entry_price) * pos.quantity
            else:
                equity += (pos.entry_price - price) * pos.quantity
        return equity

    def compute_metrics(self) -> Dict[str, Any]:
        """Compute performance metrics."""
        equity = self._equity()

        # Update peak for drawdown
        if equity > self._peak_equity:
            self._peak_equity = equity

        max_drawdown = (
            (self._peak_equity - equity) / self._peak_equity
            if self._peak_equity > 0 else 0.0
        )

        total_pnl = equity - self.starting_balance
        total_pnl_pct = total_pnl / self.starting_balance if self.starting_balance > 0 else 0.0

        # Win rate
        wins = sum(1 for t in self.trade_history if t.pnl > 0)
        losses = sum(1 for t in self.trade_history if t.pnl <= 0)
        total_trades = wins + losses
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        # Average trade duration
        avg_duration = (
            sum(t.duration_minutes for t in self.trade_history) / total_trades
            if total_trades > 0 else 0.0
        )

        # Sharpe ratio (annualized, using trade returns)
        sharpe = 0.0
        if total_trades > 1:
            returns = [t.pnl_pct for t in self.trade_history]
            mean_ret = np.mean(returns)
            std_ret = np.std(returns)
            if std_ret > 0:
                # Approximate: assume ~288 5-min intervals per day, 365 days
                trades_per_year = 365 * 288 / (avg_duration if avg_duration > 0 else 5)
                sharpe = (mean_ret / std_ret) * math.sqrt(min(trades_per_year, 100_000))

        # Average P&L
        avg_pnl = (
            sum(t.pnl for t in self.trade_history) / total_trades
            if total_trades > 0 else 0.0
        )

        # Profit factor
        gross_profit = sum(t.pnl for t in self.trade_history if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in self.trade_history if t.pnl < 0))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        return {
            "equity": round(equity, 2),
            "balance": round(self.balance, 2),
            "starting_balance": round(self.starting_balance, 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_pct": round(total_pnl_pct * 100, 4),
            "win_rate": round(win_rate * 100, 2),
            "total_trades": total_trades,
            "open_positions": len(self.positions),
            "sharpe_ratio": round(sharpe, 4),
            "max_drawdown_pct": round(max_drawdown * 100, 4),
            "avg_trade_pnl": round(avg_pnl, 4),
            "avg_trade_duration_min": round(avg_duration, 1),
            "profit_factor": round(profit_factor, 4),
            "gross_profit": round(gross_profit, 2),
            "gross_loss": round(gross_loss, 2),
            "models_loaded": len(self._models),
        }

    # ------------------------------------------------------------------
    # State persistence
    # ------------------------------------------------------------------

    def save_state(self):
        """Write full state to reports/paper_trading_state.json."""
        state = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "metrics": self.compute_metrics(),
            "positions": {pid: p.to_dict() for pid, p in self.positions.items()},
            "recent_trades": [t.to_dict() for t in self.trade_history[-50:]],
            "equity_curve": self.equity_curve[-500:],
            "signals": self.signal_log[-100:],
            "skipped_signals": self.skipped_signals[-200:],
            "model_drift": self._check_model_drift(),
            "model_performance": {
                f"{s}:{p}:{e}": preds
                for (s, p, e), preds in self._model_performance.items()
            },
            "config": {
                "starting_balance": self.starting_balance,
                "signal_threshold": SIGNAL_THRESHOLD,
                "confidence_threshold": CONFIDENCE_THRESHOLD,
                "max_position_pct": MAX_POSITION_PCT,
                "max_positions_per_pair": MAX_POSITIONS_PER_PAIR,
                "stop_loss_pct": STOP_LOSS_PCT,
                "take_profit_pct": TAKE_PROFIT_PCT,
                "fee_range": list(FEE_RANGE),
                "slippage_range": list(SLIPPAGE_RANGE),
            },
        }

        try:
            STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, default=str)
            logger.debug(f"State saved to {STATE_FILE}")
        except Exception as exc:
            logger.error(f"Failed to save state: {exc}")

    def load_state(self) -> bool:
        """Restore state from disk if available."""
        if not STATE_FILE.exists():
            return False

        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                state = json.load(f)

            # Restore balance
            metrics = state.get("metrics", {})
            self.balance = metrics.get("balance", self.starting_balance)
            self.starting_balance = metrics.get("starting_balance", self.starting_balance)
            self._peak_equity = max(
                metrics.get("equity", self.balance), self.balance
            )

            # Restore positions
            for pid, pdict in state.get("positions", {}).items():
                self.positions[pid] = PaperPosition(**pdict)

            # Restore trade history
            for tdict in state.get("recent_trades", []):
                self.trade_history.append(ClosedTrade(**tdict))

            # Restore equity curve
            self.equity_curve = state.get("equity_curve", [])

            # Restore skipped signals
            self.skipped_signals = state.get("skipped_signals", [])

            # Restore model performance tracking
            for key_str, preds in state.get("model_performance", {}).items():
                parts = key_str.split(":")
                if len(parts) == 3:
                    self._model_performance[(parts[0], parts[1], parts[2])] = preds

            # Trade counter
            if self.positions:
                max_id = max(int(pid.split("-")[1]) for pid in self.positions)
                self._trade_counter = max(self._trade_counter, max_id)
            if self.trade_history:
                max_id = max(int(t.id.split("-")[1]) for t in self.trade_history)
                self._trade_counter = max(self._trade_counter, max_id)

            logger.info(
                f"State restored: balance=${self.balance:,.2f}, "
                f"{len(self.positions)} open positions, "
                f"{len(self.trade_history)} historical trades"
            )
            return True

        except Exception as exc:
            logger.error(f"Failed to load state: {exc}")
            return False

    # ------------------------------------------------------------------
    # Daily reset
    # ------------------------------------------------------------------

    def _check_day_rollover(self):
        today = datetime.now(timezone.utc).date()
        if today != self._current_day:
            logger.info(
                f"Day rollover: {self._current_day} -> {today} | "
                f"Previous day P&L: ${self._equity() - self._day_start_balance:+.2f}"
            )
            self._current_day = today
            self._day_start_balance = self._equity()

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self):
        """Main paper trading loop. Runs every 5 minutes."""
        logger.info("=" * 70)
        logger.info("PAPER TRADING ENGINE STARTING")
        logger.info("=" * 70)

        # Load models
        self.load_models()
        if not self._models:
            logger.warning(
                "No trained models found in models/strategies/. "
                "The engine will run but cannot generate signals until models are trained."
            )

        # Restore previous state
        self.load_state()

        # Initialize exchanges
        exchanges = await self._init_exchanges()
        if not exchanges:
            logger.error("No exchanges could be initialized. Exiting.")
            return

        self._running = True

        # Graceful shutdown on SIGINT/SIGTERM
        loop = asyncio.get_event_loop()
        for sig_name in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig_name, self._shutdown)
            except NotImplementedError:
                # Windows doesn't support add_signal_handler
                signal.signal(sig_name, lambda s, f: self._shutdown())

        iteration = 0
        while self._running:
            iteration += 1
            cycle_start = time.time()

            try:
                logger.info(f"--- Cycle {iteration} ---")
                self._check_day_rollover()

                # 1. Fetch live data
                fetched = await self.fetch_all_ohlcv(exchanges)
                if fetched == 0:
                    logger.warning("No data fetched this cycle, skipping signal generation")
                    await self._wait_next_cycle(cycle_start)
                    continue

                # 2. Check existing position exits
                exits = self.check_exits()
                if exits > 0:
                    logger.info(f"Closed {exits} positions (SL/TP)")

                # 3. Generate signals
                if self._models:
                    signals = self.generate_signals()

                    # 4. Execute new trades
                    new_trades = self.execute_signals(signals)
                    if new_trades > 0:
                        logger.info(f"Opened {new_trades} new positions")
                else:
                    logger.debug("No models loaded, skipping signal generation")

                # 5. Record equity
                equity = self._equity()
                self.equity_curve.append(
                    (datetime.now(timezone.utc).isoformat(), round(equity, 2))
                )

                # 6. Log metrics
                metrics = self.compute_metrics()
                logger.info(
                    f"Equity: ${metrics['equity']:,.2f} | "
                    f"P&L: ${metrics['total_pnl']:+,.2f} ({metrics['total_pnl_pct']:+.2f}%) | "
                    f"Positions: {metrics['open_positions']} | "
                    f"Trades: {metrics['total_trades']} | "
                    f"Win rate: {metrics['win_rate']:.1f}% | "
                    f"Drawdown: {metrics['max_drawdown_pct']:.2f}%"
                )

                # 7. Save state
                self.save_state()

            except Exception as exc:
                logger.error(f"Cycle {iteration} error: {exc}\n{traceback.format_exc()}")

            await self._wait_next_cycle(cycle_start)

        # Cleanup
        logger.info("Shutting down — closing exchange connections...")
        for ex in exchanges.values():
            try:
                await ex.close()
            except Exception:
                pass

        self.save_state()
        logger.info("Paper trading engine stopped.")

    async def _wait_next_cycle(self, cycle_start: float, interval: float = 300.0):
        """Wait until next 5-minute interval."""
        elapsed = time.time() - cycle_start
        remaining = max(0, interval - elapsed)
        if remaining > 0:
            logger.debug(f"Next cycle in {remaining:.0f}s")
            try:
                await asyncio.sleep(remaining)
            except asyncio.CancelledError:
                self._running = False

    def _shutdown(self):
        logger.info("Shutdown signal received")
        self._running = False


# ---------------------------------------------------------------------------
# CLI commands
# ---------------------------------------------------------------------------

def cmd_status():
    """Print current portfolio status from saved state."""
    if not STATE_FILE.exists():
        print("No paper trading state found. Run --start first.")
        return

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    metrics = state.get("metrics", {})
    positions = state.get("positions", {})
    ts = state.get("timestamp", "unknown")

    print()
    print("=" * 60)
    print("  SOVEREIGNFORGE PAPER TRADING STATUS")
    print(f"  Last updated: {ts}")
    print("=" * 60)
    print()
    print(f"  Equity:            ${metrics.get('equity', 0):>12,.2f}")
    print(f"  Cash Balance:      ${metrics.get('balance', 0):>12,.2f}")
    print(f"  Starting Balance:  ${metrics.get('starting_balance', 0):>12,.2f}")
    print(f"  Total P&L:         ${metrics.get('total_pnl', 0):>+12,.2f}  "
          f"({metrics.get('total_pnl_pct', 0):+.2f}%)")
    print()
    print(f"  Open Positions:    {metrics.get('open_positions', 0)}")
    print(f"  Total Trades:      {metrics.get('total_trades', 0)}")
    print(f"  Win Rate:          {metrics.get('win_rate', 0):.1f}%")
    print(f"  Sharpe Ratio:      {metrics.get('sharpe_ratio', 0):.4f}")
    print(f"  Max Drawdown:      {metrics.get('max_drawdown_pct', 0):.2f}%")
    print(f"  Profit Factor:     {metrics.get('profit_factor', 0):.2f}")
    print(f"  Avg Trade P&L:     ${metrics.get('avg_trade_pnl', 0):>+10,.4f}")
    print(f"  Avg Duration:      {metrics.get('avg_trade_duration_min', 0):.1f} min")
    print(f"  Models Loaded:     {metrics.get('models_loaded', 0)}")
    print()

    if positions:
        print("-" * 60)
        print("  OPEN POSITIONS")
        print("-" * 60)
        for pid, pos in positions.items():
            print(
                f"  {pid}: {pos['side'].upper()} {pos['pair']} on {pos['exchange']} | "
                f"qty={pos['quantity']:.6f} @ ${pos['entry_price']:.4f} | "
                f"${pos['size_usdc']:.2f} | {pos['strategy']}"
            )
        print()


def cmd_history():
    """Print trade history from saved state."""
    if not STATE_FILE.exists():
        print("No paper trading state found. Run --start first.")
        return

    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)

    trades = state.get("recent_trades", [])

    if not trades:
        print("No trade history yet.")
        return

    print()
    print("=" * 90)
    print("  TRADE HISTORY (most recent 50)")
    print("=" * 90)
    print(f"  {'ID':<12} {'Pair':<10} {'Exchange':<10} {'Side':<5} "
          f"{'Entry':>10} {'Exit':>10} {'P&L':>10} {'Reason':<12} {'Duration':<10}")
    print("-" * 90)

    for t in trades:
        pnl_str = f"${t['pnl']:+.2f}"
        dur_str = f"{t['duration_minutes']:.0f}m"
        print(
            f"  {t['id']:<12} {t['pair']:<10} {t['exchange']:<10} {t['side']:<5} "
            f"${t['entry_price']:>9.4f} ${t['exit_price']:>9.4f} {pnl_str:>10} "
            f"{t['reason']:<12} {dur_str:<10}"
        )

    # Summary
    total_pnl = sum(t["pnl"] for t in trades)
    wins = sum(1 for t in trades if t["pnl"] > 0)
    print("-" * 90)
    print(f"  Total: {len(trades)} trades | P&L: ${total_pnl:+,.2f} | "
          f"Wins: {wins}/{len(trades)} ({100 * wins / len(trades):.1f}%)")
    print()


def cmd_start(balance: float):
    """Start the paper trading loop."""
    engine = PaperTradingEngine(starting_balance=balance)

    try:
        asyncio.run(engine.run())
    except KeyboardInterrupt:
        logger.info("Interrupted by user")
        engine.save_state()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="SovereignForge Paper Trading Engine",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python src/paper_trading.py --start                  Start with default $10,000
  python src/paper_trading.py --start --balance 50000  Start with $50,000
  python src/paper_trading.py --status                 Show current status
  python src/paper_trading.py --history                Show trade history
        """,
    )

    parser.add_argument("--start", action="store_true", help="Start paper trading loop")
    parser.add_argument("--status", action="store_true", help="Show portfolio status")
    parser.add_argument("--history", action="store_true", help="Show trade history")
    parser.add_argument(
        "--balance", type=float, default=10_000.0,
        help="Starting USDC balance (default: 10000)",
    )

    args = parser.parse_args()

    if args.status:
        cmd_status()
    elif args.history:
        cmd_history()
    elif args.start:
        cmd_start(args.balance)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
