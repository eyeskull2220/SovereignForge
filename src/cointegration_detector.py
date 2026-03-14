#!/usr/bin/env python3
"""
SovereignForge - Cointegration Detector for Pairs Arbitrage

Identifies cointegrated crypto pairs using the Augmented Dickey-Fuller (ADF) test,
computes spread z-scores, hedge ratios, and half-lives for mean-reversion trading.

Natural candidates from MiCA-compliant pairs:
- XRP/USDC vs XLM/USDC (both Ripple ecosystem)
- ADA/USDC vs ALGO/USDC (both PoS L1s)
- LINK/USDC vs HBAR/USDC (enterprise utility)
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

# Try importing statsmodels for ADF test; fall back to manual implementation
try:
    from statsmodels.tsa.stattools import adfuller, coint
    STATSMODELS_AVAILABLE = True
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available. Using simplified cointegration tests.")


@dataclass
class CointegratedPair:
    """Represents a cointegrated pair for pairs trading."""
    pair_a: str                  # e.g., "XRP/USDC"
    pair_b: str                  # e.g., "XLM/USDC"
    correlation: float           # Pearson correlation
    cointegration_pvalue: float  # ADF p-value (< 0.05 = cointegrated)
    half_life: float             # Mean-reversion half-life in periods
    hedge_ratio: float           # OLS hedge ratio for spread construction
    spread_mean: float = 0.0     # Long-run spread mean
    spread_std: float = 0.0      # Spread standard deviation
    is_valid: bool = True        # Whether pair passes all checks


class CointegrationDetector:
    """Detects and monitors cointegrated pairs for statistical arbitrage."""

    # Default pair candidates to test (MiCA-compliant USDC pairs)
    DEFAULT_CANDIDATES = [
        ('XRP/USDC', 'XLM/USDC'),      # Ripple ecosystem
        ('ADA/USDC', 'ALGO/USDC'),      # PoS Layer 1s
        ('LINK/USDC', 'HBAR/USDC'),     # Enterprise utility
        ('XRP/USDC', 'ADA/USDC'),       # Top altcoins
        ('XLM/USDC', 'ALGO/USDC'),      # Mid-cap L1s
        ('VET/USDC', 'IOTA/USDC'),      # IoT/supply chain
        ('LINK/USDC', 'ALGO/USDC'),     # Utility tokens
        ('HBAR/USDC', 'ALGO/USDC'),     # Enterprise L1s
    ]

    def __init__(self, min_correlation: float = 0.6,
                 max_pvalue: float = 0.05,
                 min_half_life: float = 2.0,
                 max_half_life: float = 50.0,
                 lookback_periods: int = 500):
        self.min_correlation = min_correlation
        self.max_pvalue = max_pvalue
        self.min_half_life = min_half_life
        self.max_half_life = max_half_life
        self.lookback_periods = lookback_periods
        self._cached_pairs: List[CointegratedPair] = []

    def find_cointegrated_pairs(
        self, price_data: Dict[str, np.ndarray],
        candidates: Optional[List[Tuple[str, str]]] = None,
    ) -> List[CointegratedPair]:
        """Find cointegrated pairs from price data.

        Args:
            price_data: Dict mapping pair name (e.g., "XRP/USDC") to close price array.
                       All arrays must be same length and time-aligned.
            candidates: Optional list of (pair_a, pair_b) tuples to test.
                       Defaults to DEFAULT_CANDIDATES.

        Returns:
            List of CointegratedPair objects that pass all criteria.
        """
        if candidates is None:
            candidates = self.DEFAULT_CANDIDATES

        results = []
        for pair_a, pair_b in candidates:
            if pair_a not in price_data or pair_b not in price_data:
                continue

            prices_a = price_data[pair_a].astype(np.float64)
            prices_b = price_data[pair_b].astype(np.float64)

            # Align lengths
            min_len = min(len(prices_a), len(prices_b))
            if min_len < 50:  # Need sufficient data
                continue
            prices_a = prices_a[-min_len:]
            prices_b = prices_b[-min_len:]

            # Use only lookback window
            if min_len > self.lookback_periods:
                prices_a = prices_a[-self.lookback_periods:]
                prices_b = prices_b[-self.lookback_periods:]

            result = self._test_pair(pair_a, pair_b, prices_a, prices_b)
            if result and result.is_valid:
                results.append(result)

        # Sort by p-value (most cointegrated first)
        results.sort(key=lambda x: x.cointegration_pvalue)
        self._cached_pairs = results

        logger.info(f"Found {len(results)} cointegrated pairs from {len(candidates)} candidates")
        return results

    def _test_pair(self, pair_a: str, pair_b: str,
                   prices_a: np.ndarray, prices_b: np.ndarray) -> Optional[CointegratedPair]:
        """Test a single pair for cointegration."""
        # Step 1: Correlation check
        correlation = float(np.corrcoef(prices_a, prices_b)[0, 1])
        if abs(correlation) < self.min_correlation:
            return None

        # Step 2: OLS hedge ratio (prices_a = beta * prices_b + alpha + epsilon)
        hedge_ratio = self._compute_hedge_ratio(prices_a, prices_b)

        # Step 3: Compute spread
        spread = prices_a - hedge_ratio * prices_b
        spread_mean = float(np.mean(spread))
        spread_std = float(np.std(spread))

        if spread_std < 1e-10:
            return None

        # Step 4: Cointegration test (ADF on spread)
        pvalue = self._adf_test(spread)

        # Step 5: Half-life of mean reversion
        half_life = self._compute_half_life(spread)

        # Validity check
        is_valid = (
            pvalue < self.max_pvalue and
            self.min_half_life <= half_life <= self.max_half_life
        )

        return CointegratedPair(
            pair_a=pair_a,
            pair_b=pair_b,
            correlation=round(correlation, 4),
            cointegration_pvalue=round(pvalue, 6),
            half_life=round(half_life, 1),
            hedge_ratio=round(hedge_ratio, 6),
            spread_mean=round(spread_mean, 6),
            spread_std=round(spread_std, 6),
            is_valid=is_valid,
        )

    def _compute_hedge_ratio(self, prices_a: np.ndarray, prices_b: np.ndarray) -> float:
        """OLS regression: prices_a = beta * prices_b + alpha."""
        # Using numpy lstsq for numerical stability
        X = np.column_stack([prices_b, np.ones(len(prices_b))])
        beta, _ = np.linalg.lstsq(X, prices_a, rcond=None)[:2]
        return float(beta[0])

    def _adf_test(self, spread: np.ndarray) -> float:
        """Augmented Dickey-Fuller test for stationarity of spread."""
        if STATSMODELS_AVAILABLE:
            try:
                result = adfuller(spread, autolag='AIC')
                return float(result[1])  # p-value
            except Exception:
                pass

        # Fallback: simplified Dickey-Fuller (no augmentation)
        return self._simple_df_test(spread)

    def _simple_df_test(self, spread: np.ndarray) -> float:
        """Simplified Dickey-Fuller test when statsmodels unavailable.

        Tests H0: unit root exists (non-stationary)
        DF statistic: t-stat of gamma in: delta_y = gamma * y_{t-1} + epsilon
        """
        n = len(spread)
        if n < 20:
            return 1.0  # Not enough data

        y_lag = spread[:-1]
        dy = np.diff(spread)

        # OLS: dy = gamma * y_lag
        gamma = float(np.sum(dy * y_lag) / (np.sum(y_lag ** 2) + 1e-10))
        residuals = dy - gamma * y_lag
        se_gamma = float(np.sqrt(np.sum(residuals ** 2) / (n - 2)) /
                        (np.sqrt(np.sum(y_lag ** 2)) + 1e-10))

        if se_gamma < 1e-10:
            return 1.0

        t_stat = gamma / se_gamma

        # Approximate p-value from DF critical values
        # Critical values: 1%: -3.43, 5%: -2.86, 10%: -2.57
        if t_stat < -3.43:
            return 0.01
        elif t_stat < -2.86:
            return 0.05
        elif t_stat < -2.57:
            return 0.10
        elif t_stat < -1.94:
            return 0.20
        else:
            return 0.50

    def _compute_half_life(self, spread: np.ndarray) -> float:
        """Compute mean-reversion half-life using AR(1) model.

        Half-life = -ln(2) / ln(phi) where spread_t = phi * spread_{t-1} + noise
        """
        spread_lag = spread[:-1]
        spread_now = spread[1:]

        # OLS: spread_now = phi * spread_lag + c
        X = np.column_stack([spread_lag, np.ones(len(spread_lag))])
        result = np.linalg.lstsq(X, spread_now, rcond=None)
        phi = float(result[0][0])

        if phi >= 1.0 or phi <= 0:
            return float('inf')  # No mean reversion

        half_life = -np.log(2) / np.log(phi)
        return max(half_life, 0.1)

    def compute_spread(self, prices_a: np.ndarray, prices_b: np.ndarray,
                       hedge_ratio: float) -> np.ndarray:
        """Compute the spread between two price series."""
        return prices_a - hedge_ratio * prices_b

    def compute_zscore(self, spread: np.ndarray, window: int = 20) -> np.ndarray:
        """Compute rolling z-score of the spread."""
        n = len(spread)
        zscore = np.zeros(n)

        if n < window:
            return zscore

        # Rolling mean and std via cumsum
        cumsum = np.cumsum(np.insert(spread, 0, 0))
        rolling_mean = (cumsum[window:] - cumsum[:-window]) / window

        cumsum_sq = np.cumsum(np.insert(spread ** 2, 0, 0))
        rolling_mean_sq = (cumsum_sq[window:] - cumsum_sq[:-window]) / window
        rolling_std = np.sqrt(np.maximum(rolling_mean_sq - rolling_mean ** 2, 0)) + 1e-10

        zscore[window:] = (spread[window:] - rolling_mean) / rolling_std
        return zscore

    def is_spread_diverged(self, zscore: float, threshold: float = 2.0) -> bool:
        """Check if the current z-score indicates divergence."""
        return abs(zscore) > threshold

    def get_trading_signal(self, zscore: float, threshold: float = 2.0) -> Tuple[str, float]:
        """Generate trading signal from z-score.

        Returns:
            (signal, strength): signal is 'long_a_short_b', 'short_a_long_b', or 'neutral'
        """
        if zscore < -threshold:
            # Spread is below mean -- buy pair_a, sell pair_b
            return 'long_a_short_b', min(abs(zscore) / (threshold * 2), 1.0)
        elif zscore > threshold:
            # Spread is above mean -- sell pair_a, buy pair_b
            return 'short_a_long_b', min(abs(zscore) / (threshold * 2), 1.0)
        return 'neutral', 0.0

    @property
    def cached_pairs(self) -> List[CointegratedPair]:
        return self._cached_pairs

    def get_status(self) -> Dict:
        return {
            'cached_pairs': len(self._cached_pairs),
            'pairs': [
                {
                    'pair_a': p.pair_a, 'pair_b': p.pair_b,
                    'correlation': p.correlation,
                    'pvalue': p.cointegration_pvalue,
                    'half_life': p.half_life,
                    'hedge_ratio': p.hedge_ratio,
                }
                for p in self._cached_pairs
            ],
            'statsmodels_available': STATSMODELS_AVAILABLE,
        }
