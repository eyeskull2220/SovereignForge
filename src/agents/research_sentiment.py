"""Market Sentiment Research Agent.

Analyzes crypto market sentiment from available data sources.
Produces structured intelligence for the trading system.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class MarketSentimentAgent:
    """Gathers and analyzes market sentiment for MiCA-compliant pairs."""

    TRACKED_ASSETS = ['XRP', 'XLM', 'HBAR', 'ALGO', 'ADA', 'LINK', 'IOTA', 'VET', 'XDC', 'ONDO', 'BTC', 'ETH']

    def __init__(self):
        self.name = "Market Sentiment Agent"
        self.last_run = None

    def analyze(self) -> Dict[str, Any]:
        """Run sentiment analysis and return structured report.

        In production this would fetch from news APIs, social media,
        and fear/greed indices. Currently provides framework + local analysis.
        """
        start = time.time()

        report = {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'market_mood': self._assess_overall_mood(),
            'per_asset': {asset: self._analyze_asset(asset) for asset in self.TRACKED_ASSETS},
            'fear_greed_estimate': self._estimate_fear_greed(),
            'actionable_signals': self._generate_signals(),
            'execution_time': round(time.time() - start, 2),
        }

        self.last_run = report
        return report

    def _assess_overall_mood(self) -> Dict[str, Any]:
        """Assess overall crypto market mood from available indicators."""
        # Read recent trading data if available
        try:
            state_path = Path(__file__).parent.parent.parent / "reports" / "pipeline_state.json"
            if state_path.exists():
                with open(state_path) as f:
                    state = json.load(f)
                opportunities = state.get('opportunities_detected', 0)
                executed = state.get('opportunities_executed', 0)
                pnl = state.get('total_pnl', 0)
                return {
                    'source': 'pipeline_state',
                    'activity_level': 'high' if opportunities > 100 else 'medium' if opportunities > 20 else 'low',
                    'execution_rate': round(executed / max(opportunities, 1), 2),
                    'pnl_direction': 'bullish' if pnl > 0 else 'bearish' if pnl < 0 else 'neutral',
                }
        except Exception:
            pass
        return {'source': 'default', 'activity_level': 'unknown', 'pnl_direction': 'neutral'}

    def _analyze_asset(self, asset: str) -> Dict[str, Any]:
        """Per-asset sentiment derived from local OHLCV price action.

        Computes momentum, volume trend, and volatility from historical data
        as a sentiment proxy.  External API integration (CoinGecko, LunarCrush)
        can be added later for richer signals.
        """
        try:
            import csv
            import math
            data_dir = Path(__file__).parent.parent.parent / "data" / "historical"
            # Try multiple exchange sources
            ohlcv = None
            for exchange in ('binance', 'okx', 'kucoin', 'coinbase', 'kraken', 'bybit', 'gate'):
                csv_path = data_dir / exchange / f"{asset}_USDC_5m.csv"
                if csv_path.exists():
                    with open(csv_path) as f:
                        reader = csv.reader(f)
                        rows = list(reader)
                    # Need at least header + 288 rows (1 day of 5m candles)
                    if len(rows) > 288:
                        ohlcv = rows
                        break

            if ohlcv is None:
                return {
                    'asset': asset, 'sentiment_score': 0.0, 'confidence': 0.0,
                    'sources': [], 'note': 'No OHLCV data available',
                }

            # Parse last 288 rows (~ 1 day) and last 2016 rows (~ 1 week)
            header = ohlcv[0] if not ohlcv[0][0].replace('.', '').isdigit() else None
            data_rows = ohlcv[1:] if header else ohlcv

            def parse_row(row):
                return {'close': float(row[4]), 'volume': float(row[5])}

            recent = [parse_row(r) for r in data_rows[-288:]]
            week = [parse_row(r) for r in data_rows[-2016:]] if len(data_rows) >= 2016 else recent

            # 24h momentum: (last close - close 24h ago) / close 24h ago
            momentum_24h = (recent[-1]['close'] - recent[0]['close']) / max(recent[0]['close'], 1e-10)

            # 7d momentum
            momentum_7d = (week[-1]['close'] - week[0]['close']) / max(week[0]['close'], 1e-10)

            # Volume trend: avg volume last 6h vs avg volume prior 18h
            vol_recent = sum(r['volume'] for r in recent[-72:]) / 72 if len(recent) >= 72 else 0
            vol_prior = sum(r['volume'] for r in recent[:-72]) / max(len(recent) - 72, 1) if len(recent) > 72 else vol_recent
            vol_ratio = (vol_recent / max(vol_prior, 1e-10)) - 1.0  # >0 = increasing volume

            # Volatility (std of 24h returns)
            returns = []
            for i in range(1, len(recent)):
                prev = recent[i-1]['close']
                if prev > 0:
                    returns.append((recent[i]['close'] - prev) / prev)
            volatility = (sum(r**2 for r in returns) / max(len(returns), 1)) ** 0.5 if returns else 0.0

            # Composite sentiment: momentum-weighted, vol-adjusted
            # Positive momentum + rising volume = bullish
            raw_score = (momentum_24h * 0.5 + momentum_7d * 0.3 + vol_ratio * 0.2)
            sentiment_score = max(-1.0, min(1.0, raw_score * 10))  # Scale to [-1, 1]

            # Confidence based on data availability and volatility
            confidence = min(0.8, 0.4 + (len(recent) / 288) * 0.2 + (1.0 - min(volatility * 100, 1.0)) * 0.2)

            return {
                'asset': asset,
                'sentiment_score': round(sentiment_score, 3),
                'confidence': round(confidence, 3),
                'momentum_24h': round(momentum_24h, 4),
                'momentum_7d': round(momentum_7d, 4),
                'volume_trend': round(vol_ratio, 4),
                'volatility_24h': round(volatility, 6),
                'sources': ['local_ohlcv'],
            }
        except Exception as e:
            logger.warning(f"Sentiment analysis failed for {asset}: {e}")
            return {
                'asset': asset, 'sentiment_score': 0.0, 'confidence': 0.0,
                'sources': [], 'note': f'Analysis error: {e}',
            }

    def _estimate_fear_greed(self) -> Dict[str, Any]:
        """Estimate fear/greed from available pipeline data."""
        try:
            paper_path = Path(__file__).parent.parent.parent / "reports" / "paper_trading_state.json"
            if paper_path.exists():
                with open(paper_path) as f:
                    pt = json.load(f)
                win_rate = pt.get('win_rate', 0.5)
                # High win rate suggests greed (easy market), low suggests fear
                index = int(win_rate * 100)
                label = 'extreme_greed' if index > 75 else 'greed' if index > 55 else 'neutral' if index > 45 else 'fear' if index > 25 else 'extreme_fear'
                return {'index': index, 'label': label, 'source': 'paper_trading_proxy'}
        except Exception:
            pass
        return {'index': 50, 'label': 'neutral', 'source': 'default'}

    def _generate_signals(self) -> List[Dict[str, str]]:
        """Generate actionable signals from sentiment data."""
        return [
            {'signal': 'Sentiment analysis requires API integration', 'priority': 'info',
             'action': 'Configure CoinGecko API key for live sentiment data'},
        ]
