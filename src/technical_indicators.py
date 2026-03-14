"""
Technical indicators utility for SovereignForge.

Computes enriched technical indicators from OHLCV data using the `ta` library.
Designed as an importable utility for:
  - Paper trading signal enrichment
  - Dashboard API indicator display
  - Future training runs with expanded feature sets

NOTE: Does NOT modify the existing 17-feature engineer_features() pipeline.
      The 76 trained models remain compatible.

Usage:
    from technical_indicators import compute_indicators
    indicators = compute_indicators(ohlcv_array)
    # indicators["rsi_14"] -> np.ndarray normalized to [0, 1]

CLI test:
    python src/technical_indicators.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd
import ta


def compute_indicators(ohlcv: np.ndarray) -> Dict[str, np.ndarray]:
    """Compute technical indicators from raw OHLCV data.

    Parameters
    ----------
    ohlcv : np.ndarray
        Array with columns [timestamp, open, high, low, close, volume].
        Minimum length ~50 rows for meaningful indicator values.

    Returns
    -------
    Dict[str, np.ndarray]
        Indicator name -> 1-D array (same length as input).
        All values normalized to roughly [-1, 1] or [0, 1].
        NaNs are forward-filled then zero-filled.
    """
    n = len(ohlcv)
    if n < 2:
        return {name: np.zeros(n) for name in _INDICATOR_NAMES}

    # Build a pandas DataFrame for the ta library
    df = pd.DataFrame({
        "open": ohlcv[:, 1].astype(float),
        "high": ohlcv[:, 2].astype(float),
        "low": ohlcv[:, 3].astype(float),
        "close": ohlcv[:, 4].astype(float),
        "volume": ohlcv[:, 5].astype(float),
    })

    results: Dict[str, np.ndarray] = {}

    # ── RSI(14) ──────────────────────────────────────────────────────────
    # Raw RSI is 0-100; normalize to [0, 1]
    rsi_raw = ta.momentum.RSIIndicator(close=df["close"], window=14).rsi()
    results["rsi_14"] = _normalize_01(rsi_raw, 0.0, 100.0)

    # ── MACD(12,26,9) ───────────────────────────────────────────────────
    macd_obj = ta.trend.MACD(close=df["close"], window_slow=26, window_fast=12, window_sign=9)

    # MACD signal line — normalize by rolling price scale
    macd_signal = macd_obj.macd_signal()
    results["macd_signal"] = _normalize_zscore(macd_signal)

    # MACD histogram — normalize by rolling price scale
    macd_hist = macd_obj.macd_diff()
    results["macd_histogram"] = _normalize_zscore(macd_hist)

    # ── Bollinger Band %B(20) ────────────────────────────────────────────
    bb_obj = ta.volatility.BollingerBands(close=df["close"], window=20, window_dev=2)
    bb_pband = bb_obj.bollinger_pband()  # already (close - lower) / (upper - lower)
    # Clip to [-0.5, 1.5] then rescale to [0, 1]
    results["bb_pctb_20"] = _normalize_01(bb_pband, -0.5, 1.5)

    # ── Stochastic %K(14) ───────────────────────────────────────────────
    stoch = ta.momentum.StochasticOscillator(
        high=df["high"], low=df["low"], close=df["close"],
        window=14, smooth_window=3,
    )
    results["stoch_k_14"] = _normalize_01(stoch.stoch(), 0.0, 100.0)

    # ── ATR(14) ──────────────────────────────────────────────────────────
    # Normalize ATR as fraction of close price -> roughly [0, ~0.1]
    atr_raw = ta.volatility.AverageTrueRange(
        high=df["high"], low=df["low"], close=df["close"], window=14,
    ).average_true_range()
    atr_pct = atr_raw / (df["close"] + 1e-10)
    # Typical crypto ATR% is 0-10%; clip to [0, 0.15] and rescale to [0, 1]
    results["atr_14"] = _normalize_01(atr_pct, 0.0, 0.15)

    # ── CCI(20) ──────────────────────────────────────────────────────────
    # Raw CCI is unbounded; typical range ~ [-200, 200]
    cci_raw = ta.trend.CCIIndicator(
        high=df["high"], low=df["low"], close=df["close"], window=20,
    ).cci()
    results["cci_20"] = _normalize_tanh(cci_raw, scale=200.0)

    # ── OBV ──────────────────────────────────────────────────────────────
    # OBV is cumulative and unbounded — take z-score of rate of change
    obv_raw = ta.volume.OnBalanceVolumeIndicator(
        close=df["close"], volume=df["volume"],
    ).on_balance_volume()
    obv_roc = obv_raw.diff() / (obv_raw.abs().rolling(20).mean() + 1e-10)
    results["obv_roc"] = _normalize_tanh(obv_roc, scale=2.0)

    # ── Williams %R(14) ──────────────────────────────────────────────────
    # Raw range is [-100, 0]; normalize to [-1, 0] then shift to [0, 1]
    willr_raw = ta.momentum.WilliamsRIndicator(
        high=df["high"], low=df["low"], close=df["close"], lbp=14,
    ).williams_r()
    results["williams_r_14"] = _normalize_01(willr_raw, -100.0, 0.0)

    # ── NaN handling: forward fill then zero fill ────────────────────────
    for name in results:
        arr = results[name]
        if isinstance(arr, pd.Series):
            arr = arr.ffill().fillna(0.0).values
        arr = np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)
        results[name] = arr.astype(np.float32)

    return results


# ── Normalization helpers ────────────────────────────────────────────────

def _normalize_01(series: pd.Series, lo: float, hi: float) -> pd.Series:
    """Linearly scale from [lo, hi] to [0, 1], clipped."""
    return ((series - lo) / (hi - lo + 1e-10)).clip(0.0, 1.0)


def _normalize_zscore(series: pd.Series, window: int = 100) -> pd.Series:
    """Rolling z-score, then tanh to bound to [-1, 1]."""
    mean = series.rolling(window, min_periods=1).mean()
    std = series.rolling(window, min_periods=1).std().fillna(1.0).replace(0.0, 1.0)
    z = (series - mean) / std
    return np.tanh(z)


def _normalize_tanh(series: pd.Series, scale: float = 1.0) -> pd.Series:
    """Divide by scale then apply tanh to bound to [-1, 1]."""
    return np.tanh(series / scale)


# ── Public list of indicator names (stable ordering) ─────────────────────

_INDICATOR_NAMES = [
    "rsi_14",
    "macd_signal",
    "macd_histogram",
    "bb_pctb_20",
    "stoch_k_14",
    "atr_14",
    "cci_20",
    "obv_roc",
    "williams_r_14",
]

INDICATOR_NAMES = list(_INDICATOR_NAMES)  # public copy


def indicators_to_array(indicators: Dict[str, np.ndarray]) -> np.ndarray:
    """Stack indicators into a 2-D array [N, num_indicators] in canonical order."""
    return np.column_stack([indicators[name] for name in _INDICATOR_NAMES])


# ── CLI test ─────────────────────────────────────────────────────────────

def _cli_test() -> None:
    """Load a sample CSV and print indicator summary statistics."""
    # Resolve data directory relative to project root
    src_dir = Path(__file__).resolve().parent
    project_root = src_dir.parent
    data_dir = project_root / "data" / "real_historical" / "binance"

    # Fall back to synthetic backup if real data absent
    if not data_dir.exists():
        data_dir = project_root / "data" / "historical_synthetic_backup" / "binance"

    if not data_dir.exists():
        print(f"[ERROR] No data directory found at {data_dir}")
        sys.exit(1)

    csv_files = sorted(data_dir.glob("*.csv"))
    if not csv_files:
        print(f"[ERROR] No CSV files in {data_dir}")
        sys.exit(1)

    csv_path = csv_files[0]
    print(f"Loading: {csv_path.name}")
    df = pd.read_csv(csv_path)
    print(f"Rows: {len(df)}")

    # Convert to OHLCV numpy array
    # Expected columns: timestamp, open, high, low, close, volume
    # Timestamp may be string — convert to epoch seconds
    if df["timestamp"].dtype == object:
        df["timestamp"] = pd.to_datetime(df["timestamp"]).astype(np.int64) // 10**9
    ohlcv = df[["timestamp", "open", "high", "low", "close", "volume"]].values

    indicators = compute_indicators(ohlcv)

    print(f"\n{'Indicator':<20} {'Min':>8} {'Max':>8} {'Mean':>8} {'Std':>8} {'NaN%':>6}")
    print("-" * 60)
    for name in _INDICATOR_NAMES:
        arr = indicators[name]
        nan_pct = 100.0 * np.isnan(arr).sum() / len(arr)
        clean = arr[~np.isnan(arr)] if np.isnan(arr).any() else arr
        print(
            f"{name:<20} {clean.min():>8.4f} {clean.max():>8.4f} "
            f"{clean.mean():>8.4f} {clean.std():>8.4f} {nan_pct:>5.1f}%"
        )

    print(f"\nTotal indicators: {len(_INDICATOR_NAMES)}")
    stacked = indicators_to_array(indicators)
    print(f"Stacked shape: {stacked.shape}")
    print("\nAll indicators computed successfully.")


if __name__ == "__main__":
    _cli_test()
