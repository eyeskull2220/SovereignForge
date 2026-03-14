#!/usr/bin/env python3
"""
SovereignForge - Market Regime Detector

Classifies market conditions as trending/ranging/volatile to dynamically
adjust strategy weights. Uses ADX (trend strength), ATR (volatility),
and EMA slope (direction).
"""

import logging
from enum import Enum
from typing import Dict, Optional

import numpy as np

from session_regime import compute_adx

logger = logging.getLogger(__name__)


class MarketRegime(Enum):
    TRENDING_UP = "trending_up"
    TRENDING_DOWN = "trending_down"
    RANGING = "ranging"
    HIGH_VOLATILITY = "high_vol"
    LOW_VOLATILITY = "low_vol"


# Weight multipliers per regime per strategy
# Values > 1.0 boost the strategy, < 1.0 dampen it
REGIME_WEIGHTS: Dict[MarketRegime, Dict[str, float]] = {
    MarketRegime.TRENDING_UP: {
        'arbitrage': 0.8, 'fibonacci': 1.2, 'grid': 0.5,
        'dca': 0.7, 'mean_reversion': 0.4, 'pairs_arbitrage': 0.8, 'momentum': 1.6,
    },
    MarketRegime.TRENDING_DOWN: {
        'arbitrage': 0.8, 'fibonacci': 1.0, 'grid': 0.5,
        'dca': 1.5, 'mean_reversion': 0.4, 'pairs_arbitrage': 1.0, 'momentum': 1.4,
    },
    MarketRegime.RANGING: {
        'arbitrage': 1.2, 'fibonacci': 0.7, 'grid': 1.6,
        'dca': 0.8, 'mean_reversion': 1.6, 'pairs_arbitrage': 1.3, 'momentum': 0.4,
    },
    MarketRegime.HIGH_VOLATILITY: {
        'arbitrage': 1.4, 'fibonacci': 0.6, 'grid': 0.6,
        'dca': 0.5, 'mean_reversion': 1.0, 'pairs_arbitrage': 0.7, 'momentum': 0.6,
    },
    MarketRegime.LOW_VOLATILITY: {
        'arbitrage': 0.7, 'fibonacci': 1.0, 'grid': 1.3,
        'dca': 1.2, 'mean_reversion': 1.0, 'pairs_arbitrage': 1.1, 'momentum': 0.7,
    },
}


def compute_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                period: int = 14) -> np.ndarray:
    """Compute Average True Range (ATR).

    Uses the True Range computation already present in compute_adx
    but exposed as a standalone function.
    """
    n = len(close)
    atr = np.zeros(n, dtype=np.float64)

    if n < period + 1:
        return atr

    # True Range
    tr = np.zeros(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(
            high[i] - low[i],
            abs(high[i] - close[i - 1]),
            abs(low[i] - close[i - 1])
        )

    # Wilder's smoothing for ATR
    atr[period] = np.mean(tr[1:period + 1])
    for i in range(period + 1, n):
        atr[i] = (atr[i - 1] * (period - 1) + tr[i]) / period

    return atr


def compute_ema(data: np.ndarray, period: int) -> np.ndarray:
    """Compute Exponential Moving Average."""
    ema = np.zeros_like(data, dtype=np.float64)
    if len(data) < period:
        return ema
    ema[period - 1] = np.mean(data[:period])
    multiplier = 2.0 / (period + 1)
    for i in range(period, len(data)):
        ema[i] = (data[i] - ema[i - 1]) * multiplier + ema[i - 1]
    return ema


class RegimeDetector:
    """
    Detects market regime from OHLCV data.

    Uses:
    - ADX for trend strength (>25 = trending, <20 = ranging)
    - ATR / price for volatility level
    - EMA(50) slope for trend direction
    """

    def __init__(self, adx_trend_threshold: float = 22.0,
                 adx_range_threshold: float = 18.0,
                 atr_vol_high_pct: float = 0.04,
                 atr_vol_low_pct: float = 0.008,
                 ema_period: int = 50):
        self.adx_trend_threshold = adx_trend_threshold
        self.adx_range_threshold = adx_range_threshold
        self.atr_vol_high_pct = atr_vol_high_pct
        self.atr_vol_low_pct = atr_vol_low_pct
        self.ema_period = ema_period
        self._last_regime: Optional[MarketRegime] = None

    def detect(self, high: np.ndarray, low: np.ndarray,
               close: np.ndarray) -> MarketRegime:
        """Detect current market regime from price data.

        Args:
            high, low, close: Price arrays (minimum ~60 candles recommended)

        Returns:
            MarketRegime classification
        """
        n = len(close)
        if n < 30:
            return MarketRegime.RANGING  # default for insufficient data

        # Compute indicators
        adx = compute_adx(high, low, close, period=14)
        atr = compute_atr(high, low, close, period=14)
        ema = compute_ema(close, self.ema_period)

        # Use the latest values
        current_adx = adx[-1] if adx[-1] > 0 else adx[adx > 0][-1] if np.any(adx > 0) else 0
        current_atr = atr[-1] if atr[-1] > 0 else 0
        current_price = close[-1]

        # ATR as percentage of price
        atr_pct = current_atr / current_price if current_price > 0 else 0

        # EMA slope (normalized): compare last EMA to 5 candles ago
        ema_slope = 0.0
        if n > self.ema_period + 5 and ema[-1] > 0 and ema[-6] > 0:
            ema_slope = (ema[-1] - ema[-6]) / ema[-6]

        # Classification logic
        regime = self._classify(current_adx, atr_pct, ema_slope)
        self._last_regime = regime
        return regime

    def _classify(self, adx: float, atr_pct: float, ema_slope: float) -> MarketRegime:
        """Classify regime from indicator values."""
        # High volatility overrides
        if atr_pct > self.atr_vol_high_pct:
            return MarketRegime.HIGH_VOLATILITY

        # Low volatility
        if atr_pct < self.atr_vol_low_pct:
            return MarketRegime.LOW_VOLATILITY

        # Trending
        if adx > self.adx_trend_threshold:
            return MarketRegime.TRENDING_UP if ema_slope > 0 else MarketRegime.TRENDING_DOWN

        # Ranging
        if adx < self.adx_range_threshold:
            return MarketRegime.RANGING

        # Ambiguous zone (20-25 ADX): use volatility as tiebreaker
        if atr_pct > (self.atr_vol_high_pct + self.atr_vol_low_pct) / 2:
            return MarketRegime.TRENDING_UP if ema_slope > 0 else MarketRegime.TRENDING_DOWN
        return MarketRegime.RANGING

    def get_strategy_weights(self, regime: Optional[MarketRegime] = None) -> Dict[str, float]:
        """Get strategy weight multipliers for a regime.

        Args:
            regime: MarketRegime to use, or None to use last detected regime
        """
        r = regime or self._last_regime or MarketRegime.RANGING
        return REGIME_WEIGHTS.get(r, {})

    @property
    def last_regime(self) -> Optional[MarketRegime]:
        return self._last_regime
