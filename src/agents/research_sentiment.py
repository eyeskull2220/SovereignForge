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
        """Per-asset sentiment stub. Override with real data sources."""
        return {
            'asset': asset,
            'sentiment_score': 0.0,  # -1 to 1
            'confidence': 0.0,
            'sources': [],
            'note': 'Requires API integration (CoinGecko, LunarCrush, etc.)',
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
