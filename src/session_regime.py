#!/usr/bin/env python3
"""
SovereignForge - Session Regime Detection & Cross-Exchange Spread Analysis

Detects trading session windows (US, Asia, London) and computes ADX-based
regime weights for training loss weighting. Also provides cross-exchange
spread computation for comparative arbitrage analysis.
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class SessionRegime(Enum):
    US_OPEN = "us_open"          # 13:30-16:00 UTC
    US_CLOSE = "us_close"        # 19:00-21:00 UTC
    ASIA_OPEN = "asia_open"      # 00:00-02:00 UTC
    ASIA_CLOSE = "asia_close"    # 05:00-06:30 UTC
    LONDON_OPEN = "london_open"  # 07:00-09:00 UTC
    LONDON_CLOSE = "london_close"  # 15:00-16:30 UTC
    OVERLAP = "overlap"          # Multiple sessions active
    OFF_HOURS = "off_hours"      # Low activity


# Session windows in UTC hours (start, end)
SESSION_WINDOWS = {
    SessionRegime.US_OPEN: (13.5, 16.0),
    SessionRegime.US_CLOSE: (19.0, 21.0),
    SessionRegime.ASIA_OPEN: (0.0, 2.0),
    SessionRegime.ASIA_CLOSE: (5.0, 6.5),
    SessionRegime.LONDON_OPEN: (7.0, 9.0),
    SessionRegime.LONDON_CLOSE: (15.0, 16.5),
}

# One-hot index for each session (6 sessions)
SESSION_INDEX = {
    SessionRegime.US_OPEN: 0,
    SessionRegime.US_CLOSE: 1,
    SessionRegime.ASIA_OPEN: 2,
    SessionRegime.ASIA_CLOSE: 3,
    SessionRegime.LONDON_OPEN: 4,
    SessionRegime.LONDON_CLOSE: 5,
}


def detect_session(timestamp_utc: datetime) -> SessionRegime:
    """Classify a UTC timestamp into a trading session regime."""
    hour = timestamp_utc.hour + timestamp_utc.minute / 60.0

    active_sessions = []
    for session, (start, end) in SESSION_WINDOWS.items():
        if start <= hour < end:
            active_sessions.append(session)

    if len(active_sessions) > 1:
        return SessionRegime.OVERLAP
    elif len(active_sessions) == 1:
        return active_sessions[0]
    return SessionRegime.OFF_HOURS


def session_one_hot(timestamps: np.ndarray) -> np.ndarray:
    """Convert array of Unix timestamps to 6-column one-hot session encoding.

    Args:
        timestamps: Array of Unix timestamps (seconds or milliseconds)

    Returns:
        np.ndarray of shape (len(timestamps), 6) with one-hot session encoding
    """
    n = len(timestamps)
    encoding = np.zeros((n, 6), dtype=np.float32)

    for i, ts in enumerate(timestamps):
        # Handle both seconds and milliseconds
        ts_val = float(ts)
        if ts_val > 1e12:
            ts_val /= 1000.0
        dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
        session = detect_session(dt)

        if session in SESSION_INDEX:
            encoding[i, SESSION_INDEX[session]] = 1.0
        elif session == SessionRegime.OVERLAP:
            # Mark all active sessions for overlap
            hour = dt.hour + dt.minute / 60.0
            for s, (start, end) in SESSION_WINDOWS.items():
                if start <= hour < end:
                    encoding[i, SESSION_INDEX[s]] = 1.0

    return encoding


def compute_adx(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int = 14) -> np.ndarray:
    """Compute Average Directional Index (ADX).

    Args:
        high, low, close: Price arrays
        period: ADX period (default 14)

    Returns:
        ADX array same length as input (first `period*2` values are 0)
    """
    n = len(close)
    adx = np.zeros(n, dtype=np.float64)

    if n < period * 2 + 1:
        return adx

    # True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    # Directional Movement
    plus_dm = np.zeros(n)
    minus_dm = np.zeros(n)
    for i in range(1, n):
        up_move = high[i] - high[i - 1]
        down_move = low[i - 1] - low[i]
        if up_move > down_move and up_move > 0:
            plus_dm[i] = up_move
        if down_move > up_move and down_move > 0:
            minus_dm[i] = down_move

    # Smoothed TR, +DM, -DM using Wilder's smoothing
    atr = np.zeros(n)
    smooth_plus = np.zeros(n)
    smooth_minus = np.zeros(n)

    atr[period] = np.sum(tr[1:period + 1])
    smooth_plus[period] = np.sum(plus_dm[1:period + 1])
    smooth_minus[period] = np.sum(minus_dm[1:period + 1])

    for i in range(period + 1, n):
        atr[i] = atr[i - 1] - atr[i - 1] / period + tr[i]
        smooth_plus[i] = smooth_plus[i - 1] - smooth_plus[i - 1] / period + plus_dm[i]
        smooth_minus[i] = smooth_minus[i - 1] - smooth_minus[i - 1] / period + minus_dm[i]

    # DI+ and DI-
    with np.errstate(divide='ignore', invalid='ignore'):
        plus_di = np.where(atr > 0, 100 * smooth_plus / atr, 0.0)
        minus_di = np.where(atr > 0, 100 * smooth_minus / atr, 0.0)

        # DX
        di_sum = plus_di + minus_di
        dx = np.where(di_sum > 0, 100 * np.abs(plus_di - minus_di) / di_sum, 0.0)

    # ADX (smoothed DX)
    start = period * 2
    if start < n:
        adx[start] = np.mean(dx[period:start + 1])
        for i in range(start + 1, n):
            adx[i] = (adx[i - 1] * (period - 1) + dx[i]) / period

    return adx


def compute_session_weights(timestamps: np.ndarray, high: np.ndarray,
                            low: np.ndarray, close: np.ndarray,
                            adx_threshold: int = 25) -> np.ndarray:
    """Compute per-sample training weights based on ADX regime and session.

    Low-vol ranging periods (ADX < threshold) get higher weight to emphasize
    learning during difficult market conditions.

    Args:
        timestamps: Unix timestamps
        high, low, close: Price arrays
        adx_threshold: ADX value below which market is considered ranging

    Returns:
        Weight array same length as input, values in [0.8, 2.0]
    """
    n = len(close)
    weights = np.ones(n, dtype=np.float64)

    adx = compute_adx(high, low, close, period=14)

    # ADX-based weighting: upweight ranging periods
    for i in range(n):
        if adx[i] > 0:  # Only weight where ADX is computed
            if adx[i] < adx_threshold:
                # Ranging: weight 1.5-2.0 (linearly scale by how low ADX is)
                weights[i] = 1.5 + 0.5 * (1.0 - adx[i] / adx_threshold)
            else:
                # Trending: weight 0.8-1.0
                weights[i] = 1.0 - 0.2 * min(1.0, (adx[i] - adx_threshold) / 50.0)

    # Session modifiers: overlap periods get slight boost
    for i, ts in enumerate(timestamps):
        ts_val = float(ts)
        if ts_val > 1e12:
            ts_val /= 1000.0
        try:
            dt = datetime.fromtimestamp(ts_val, tz=timezone.utc)
            session = detect_session(dt)
            if session == SessionRegime.OVERLAP:
                weights[i] *= 1.1  # 10% boost for overlap
        except (ValueError, OSError):
            pass

    return np.clip(weights, 0.8, 2.0)


def compute_cross_exchange_spreads(
    exchange_prices: Dict[str, np.ndarray]
) -> Dict[Tuple[str, str], np.ndarray]:
    """Compute pairwise cross-exchange spread time series.

    Args:
        exchange_prices: Dict mapping exchange name to close price array.
            All arrays must be aligned and same length.

    Returns:
        Dict mapping (exchange_a, exchange_b) to spread array (a - b) / b
    """
    spreads = {}
    exchanges = list(exchange_prices.keys())

    for i, ex_a in enumerate(exchanges):
        for ex_b in exchanges[i + 1:]:
            prices_a = exchange_prices[ex_a].astype(float)
            prices_b = exchange_prices[ex_b].astype(float)
            min_len = min(len(prices_a), len(prices_b))
            prices_a = prices_a[:min_len]
            prices_b = prices_b[:min_len]
            spread = np.where(
                prices_b > 0,
                (prices_a - prices_b) / prices_b,
                0.0
            )
            spreads[(ex_a, ex_b)] = spread

    return spreads
