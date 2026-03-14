"""Strategy Performance Research Agent.

Reviews paper trading results and recommends weight adjustments.
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional

logger = logging.getLogger(__name__)


class StrategyPerformanceAgent:
    """Analyzes strategy performance and recommends weight rebalancing."""

    def __init__(self):
        self.name = "Strategy Performance Agent"
        self.last_run = None

    def analyze(self) -> Dict[str, Any]:
        """Analyze strategy performance from available data."""
        start = time.time()

        # Load current config weights
        config_weights = self._load_config_weights()

        # Load paper trading state
        pt_state = self._load_paper_trading_state()

        # Load pipeline state
        pipeline_state = self._load_pipeline_state()

        # Analyze per-strategy performance
        strategy_analysis = self._analyze_strategies(pt_state, pipeline_state, config_weights)

        # Generate rebalancing recommendations
        recommendations = self._generate_recommendations(strategy_analysis, config_weights)

        report = {
            'agent': self.name,
            'timestamp': datetime.now().isoformat(),
            'current_weights': config_weights,
            'strategy_analysis': strategy_analysis,
            'recommendations': recommendations,
            'execution_time': round(time.time() - start, 2),
        }

        self.last_run = report
        return report

    def _load_config_weights(self) -> Dict[str, float]:
        try:
            config_path = Path(__file__).parent.parent.parent / "config" / "trading_config.json"
            with open(config_path) as f:
                cfg = json.load(f)
            return {name: s.get('weight', 0) for name, s in cfg.get('strategies', {}).items() if isinstance(s, dict)}
        except Exception:
            return {}

    def _load_paper_trading_state(self) -> Optional[Dict]:
        try:
            path = Path(__file__).parent.parent.parent / "reports" / "paper_trading_state.json"
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _load_pipeline_state(self) -> Optional[Dict]:
        try:
            path = Path(__file__).parent.parent.parent / "reports" / "pipeline_state.json"
            if path.exists():
                with open(path) as f:
                    return json.load(f)
        except Exception:
            pass
        return None

    def _analyze_strategies(self, pt_state: Optional[Dict], pipeline_state: Optional[Dict],
                           config_weights: Dict) -> Dict[str, Dict]:
        """Analyze each strategy's performance."""
        analysis = {}

        for strategy in config_weights:
            strat_data = {
                'current_weight': config_weights.get(strategy, 0),
                'trades': 0,
                'wins': 0,
                'losses': 0,
                'total_pnl': 0.0,
                'win_rate': 0.0,
                'avg_pnl': 0.0,
                'status': 'no_data',
            }

            # Try to extract from paper trading state
            if pt_state and 'strategy_performance' in pt_state:
                sp = pt_state['strategy_performance'].get(strategy, {})
                if sp:
                    strat_data['trades'] = sp.get('total_trades', 0)
                    strat_data['wins'] = sp.get('winning_trades', 0)
                    strat_data['losses'] = sp.get('losing_trades', 0)
                    strat_data['total_pnl'] = sp.get('total_pnl', 0)
                    if strat_data['trades'] > 0:
                        strat_data['win_rate'] = strat_data['wins'] / strat_data['trades']
                        strat_data['avg_pnl'] = strat_data['total_pnl'] / strat_data['trades']
                        strat_data['status'] = 'active'

            analysis[strategy] = strat_data

        return analysis

    def _generate_recommendations(self, analysis: Dict, current_weights: Dict) -> List[Dict]:
        """Generate weight adjustment recommendations."""
        recs = []

        active = {k: v for k, v in analysis.items() if v['status'] == 'active' and v['trades'] >= 10}

        if not active:
            recs.append({
                'type': 'info',
                'message': 'Insufficient trading data for rebalancing. Run paper trading for at least 2 weeks.',
            })
            return recs

        # Sort by win_rate * avg_pnl (composite performance score)
        scores = {k: v['win_rate'] * max(v['avg_pnl'], 0.01) for k, v in active.items()}
        sorted_strats = sorted(scores, key=scores.get, reverse=True)

        # Top performer
        if sorted_strats:
            top = sorted_strats[0]
            top_data = analysis[top]
            if top_data['win_rate'] > 0.6:
                recs.append({
                    'type': 'increase_weight',
                    'strategy': top,
                    'reason': f"Top performer: {top_data['win_rate']:.0%} win rate, ${top_data['avg_pnl']:.2f} avg P&L",
                    'suggested_weight': min(current_weights.get(top, 0.1) * 1.3, 0.35),
                })

        # Bottom performer
        if len(sorted_strats) > 1:
            bottom = sorted_strats[-1]
            bottom_data = analysis[bottom]
            if bottom_data['win_rate'] < 0.4 or bottom_data['total_pnl'] < 0:
                recs.append({
                    'type': 'decrease_weight',
                    'strategy': bottom,
                    'reason': f"Underperforming: {bottom_data['win_rate']:.0%} win rate, ${bottom_data['total_pnl']:.2f} total P&L",
                    'suggested_weight': max(current_weights.get(bottom, 0.1) * 0.5, 0.05),
                })

        # Strategies with no data need paper trading
        no_data = [k for k, v in analysis.items() if v['status'] == 'no_data']
        if no_data:
            recs.append({
                'type': 'info',
                'message': f"Strategies without data: {', '.join(no_data)}. Train models and enable paper trading.",
            })

        return recs
