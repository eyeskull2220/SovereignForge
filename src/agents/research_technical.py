"""Technical Analysis Research Agent.

Fetches live OHLCV data and computes technical indicators
for all MiCA-compliant trading pairs.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

import numpy as np

logger = logging.getLogger(__name__)


class TechnicalAnalysisAgent:
    """Computes technical indicators for tracked pairs using live exchange data."""

    PAIRS = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC',
             'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC']

    def __init__(self):
        self.name = "Technical Analysis Agent"
        self.last_run = None

    def analyze(self, exchange_name: str = 'binance') -> Dict[str, Any]:
        """Run technical analysis on all pairs.

        Args:
            exchange_name: Exchange to fetch data from (default: binance)
        """
        start = time.time()

        pair_analyses = {}
        for pair in self.PAIRS:
            try:
                analysis = self._analyze_pair(pair, exchange_name)
                if analysis:
                    pair_analyses[pair] = analysis
            except Exception as e:
                logger.debug(f"Skipping {pair}: {e}")

        # Generate cross-pair signals
        signals = self._cross_pair_signals(pair_analyses)

        report = {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'exchange': exchange_name,
            'pairs_analyzed': len(pair_analyses),
            'analyses': pair_analyses,
            'cross_pair_signals': signals,
            'execution_time': round(time.time() - start, 2),
        }

        self.last_run = report
        return report

    def _analyze_pair(self, pair: str, exchange_name: str) -> Optional[Dict[str, Any]]:
        """Analyze a single pair. Tries ccxt fetch, falls back to file data."""
        ohlcv = self._fetch_ohlcv(pair, exchange_name)
        if ohlcv is None or len(ohlcv) < 30:
            return None

        close = np.array([c[4] for c in ohlcv], dtype=np.float64)
        high = np.array([c[2] for c in ohlcv], dtype=np.float64)
        low = np.array([c[3] for c in ohlcv], dtype=np.float64)
        volume = np.array([c[5] for c in ohlcv], dtype=np.float64)

        rsi = self._rsi(close)
        bb_pos = self._bb_position(close)
        macd_val = self._macd_signal(close)
        atr = self._atr(high, low, close)
        vol_trend = self._volume_trend(volume)

        current_price = close[-1]
        price_change_24h = (close[-1] - close[0]) / close[0] * 100 if close[0] > 0 else 0

        # Generate signal
        signal = 'neutral'
        strength = 0.0
        if rsi < 30 and bb_pos < -0.7:
            signal = 'oversold_buy'
            strength = min(abs(rsi - 30) / 20 + abs(bb_pos + 0.7), 1.0)
        elif rsi > 70 and bb_pos > 0.7:
            signal = 'overbought_sell'
            strength = min((rsi - 70) / 20 + (bb_pos - 0.7), 1.0)
        elif macd_val > 0 and rsi > 50:
            signal = 'bullish_momentum'
            strength = min(macd_val * 100, 1.0)
        elif macd_val < 0 and rsi < 50:
            signal = 'bearish_momentum'
            strength = min(abs(macd_val) * 100, 1.0)

        return {
            'price': round(current_price, 6),
            'change_24h_pct': round(price_change_24h, 2),
            'rsi': round(rsi, 1),
            'bb_position': round(bb_pos, 3),
            'macd': round(macd_val, 6),
            'atr_pct': round(atr / current_price * 100, 2) if current_price > 0 else 0,
            'volume_trend': vol_trend,
            'signal': signal,
            'signal_strength': round(strength, 2),
        }

    def _fetch_ohlcv(self, pair: str, exchange_name: str) -> Optional[list]:
        """Fetch OHLCV data from exchange."""
        try:
            import ccxt
            exchange_class = getattr(ccxt, exchange_name, None)
            if not exchange_class:
                return None
            exchange = exchange_class({'enableRateLimit': True})
            return exchange.fetch_ohlcv(pair, '1h', limit=48)
        except Exception as e:
            logger.debug(f"OHLCV fetch failed for {pair}: {e}")
            return None

    def _rsi(self, close: np.ndarray, period: int = 14) -> float:
        """Compute current RSI value."""
        if len(close) < period + 1:
            return 50.0
        deltas = np.diff(close)
        gains = np.where(deltas > 0, deltas, 0)
        losses = np.where(deltas < 0, -deltas, 0)
        avg_gain = np.mean(gains[-period:])
        avg_loss = np.mean(losses[-period:])
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return 100.0 - (100.0 / (1.0 + rs))

    def _bb_position(self, close: np.ndarray, period: int = 20) -> float:
        """Current position within Bollinger Bands [-1, 1]."""
        if len(close) < period:
            return 0.0
        window = close[-period:]
        mean = np.mean(window)
        std = np.std(window) + 1e-10
        return float(np.clip((close[-1] - mean) / (2 * std), -1, 1))

    def _macd_signal(self, close: np.ndarray) -> float:
        """MACD histogram value."""
        if len(close) < 26:
            return 0.0
        ema12 = self._ema(close, 12)
        ema26 = self._ema(close, 26)
        macd_line = ema12 - ema26
        signal_line = self._ema(macd_line, 9)
        return float(macd_line[-1] - signal_line[-1])

    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        result = np.zeros_like(data, dtype=np.float64)
        result[0] = data[0]
        alpha = 2.0 / (period + 1)
        for i in range(1, len(data)):
            result[i] = alpha * data[i] + (1 - alpha) * result[i - 1]
        return result

    def _atr(self, high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> float:
        """Current ATR value."""
        if len(close) < period + 1:
            return 0.0
        tr = np.maximum(high[1:] - low[1:],
                       np.maximum(np.abs(high[1:] - close[:-1]),
                                  np.abs(low[1:] - close[:-1])))
        return float(np.mean(tr[-period:]))

    def _volume_trend(self, volume: np.ndarray) -> str:
        if len(volume) < 20:
            return 'unknown'
        recent = np.mean(volume[-5:])
        baseline = np.mean(volume[-20:])
        if baseline == 0:
            return 'unknown'
        ratio = recent / baseline
        if ratio > 1.5:
            return 'surging'
        elif ratio > 1.1:
            return 'increasing'
        elif ratio < 0.7:
            return 'declining'
        return 'stable'

    def _cross_pair_signals(self, analyses: Dict) -> List[Dict]:
        """Detect cross-pair patterns."""
        signals = []
        oversold = [p for p, a in analyses.items() if a.get('signal') == 'oversold_buy']
        overbought = [p for p, a in analyses.items() if a.get('signal') == 'overbought_sell']

        if len(oversold) > 3:
            signals.append({'type': 'market_wide_oversold', 'pairs': oversold, 'action': 'Consider broad accumulation'})
        if len(overbought) > 3:
            signals.append({'type': 'market_wide_overbought', 'pairs': overbought, 'action': 'Consider reducing exposure'})

        return signals
