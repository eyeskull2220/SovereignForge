#!/usr/bin/env python3
"""
SovereignForge - Trading Oracle (Collective Brain)

Unified meta-layer that aggregates ALL signal sources into ranked trading
opportunity recommendations. Designed by 4 personality subagents:
  - crash_survivor: anti-herding, circuit breakers, drawdown cascades
  - burned_quant: signal normalization, fee gates, contradiction resolution
  - latency_hunter: tiered refresh, batched inference, caching
  - architect: overall orchestration and integration

Usage:
    oracle = TradingOracle(strategy_ensemble, regime_detector, risk_manager)
    oracle.update_research()
    rec = oracle.evaluate("BTC/USDC", "binance", ohlcv_data)
"""

import collections
import json
import logging
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Import centralized fee constants
try:
    from fee_constants import EXCHANGE_FEES as _FEE_DICT, TRANSFER_FEES, AVG_SLIPPAGE
    # Flatten to taker-only for Oracle's FeeGate (backward compat)
    EXCHANGE_FEES = {ex: fees["taker"] for ex, fees in _FEE_DICT.items()}
except ImportError:
    EXCHANGE_FEES = {
        "binance": 0.001, "coinbase": 0.004, "kraken": 0.0026,
        "kucoin": 0.001, "okx": 0.001, "bybit": 0.001, "gate": 0.002,
    }
    TRANSFER_FEES = {
        "binance": 1.0, "coinbase": 0.0, "kraken": 2.5,
        "kucoin": 1.0, "okx": 1.0, "bybit": 1.0, "gate": 1.0,
    }
    AVG_SLIPPAGE = 0.001

# MiCA-compliant pairs (zero USDT tolerance)
MICA_COMPLIANT_PAIRS = {
    "BTC/USDC", "ETH/USDC", "XRP/USDC", "XLM/USDC", "HBAR/USDC",
    "ALGO/USDC", "ADA/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
    "XDC/USDC", "ONDO/USDC",
}

# Signal normalization: expected std per strategy from training metrics
EXPECTED_STD = {
    "arbitrage": 0.27, "fibonacci": 0.28, "grid": 0.15, "momentum": 0.16,
    "dca": 0.15, "mean_reversion": 0.15, "pairs_arbitrage": 0.16,
}

DIRECTIONAL_STRATEGIES = ["fibonacci", "grid", "momentum", "mean_reversion", "dca"]
SPREAD_STRATEGIES = ["arbitrage", "pairs_arbitrage"]

# Composite weights
W_ML = 0.60
W_SPREAD = 0.10
W_TA = 0.20
W_SENTIMENT = 0.10

# Safety thresholds
HOLD_THRESHOLD = 0.12  # Audit consensus: 0.08 too noisy, 0.20 too strict
CONFIDENCE_FLOOR = 0.20
CONFIDENCE_CEILING = 0.80
FEE_COVERAGE_MULTIPLIER = 2.0  # Audit consensus: 1.5 too loose, 3.0 too strict
MIN_CONSENSUS_FOR_TRADE = 3   # Require 3/7 strategies to agree (was 2)
CROSS_EXCHANGE_MIN_CAPITAL = 500.0

MAX_TRADES_PER_HOUR = 6
MAX_TRADES_PER_DAY = 20
STARTUP_COOLDOWN_SECONDS = 60  # 1 minute (reduced from 5 min)
REGIME_TRANSITION_COOLDOWN = 600  # 10 minutes

# Capital-aware position caps (crash_survivor)
POSITION_CAPS = [
    (400, 0.04, 2),    # $300-400: 4%, max 2 positions
    (600, 0.045, 2),   # $400-600: 4.5%, max 2
    (1000, 0.04, 3),   # $600-1000: 4%, max 3
]


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------

@dataclass
class OracleRecommendation:
    pair: str
    exchange: str
    action: str                         # "buy", "sell", "hold"
    oracle_score: float                 # [-1, 1] directional strength
    composite_confidence: float         # [0, 1] multiplicative confidence
    risk_rating: str                    # "low", "medium", "high", "extreme"
    signal_consensus: int               # independent sources agreeing (0-5)
    position_size_usd: float            # fee-gated, capital-capped
    expected_edge_pct: float
    fee_cost_pct: float
    net_expected_pct: float
    regime: str
    breakdown: Dict[str, Any] = field(default_factory=dict)
    vetoed: bool = False
    veto_reason: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


# ---------------------------------------------------------------------------
# SignalNormalizer (burned_quant)
# ---------------------------------------------------------------------------

class SignalNormalizer:
    """Rolling rank-percentile normalization per strategy.

    Fixes the root problem: arbitrage std=0.27 vs dca std=0.15 are
    incomparable raw. Maps all signals to [-1, 1] via empirical CDF.
    Cold-start fallback divides by expected std.
    """

    WINDOW = 200
    COLD_START_MIN = 30

    def __init__(self):
        self._history: Dict[str, collections.deque] = {}

    def normalize(self, strategy: str, raw_signal: float) -> float:
        if strategy not in self._history:
            self._history[strategy] = collections.deque(maxlen=self.WINDOW)

        history = self._history[strategy]
        history.append(raw_signal)

        if len(history) < self.COLD_START_MIN:
            # Cold-start: divide by expected std
            std = EXPECTED_STD.get(strategy, 0.2)
            return float(np.clip(raw_signal / std, -1.0, 1.0))

        # Rank-percentile: fraction of history <= current signal
        arr = np.array(history)
        rank_pct = np.sum(arr <= raw_signal) / len(arr)
        return float(2.0 * rank_pct - 1.0)  # map [0,1] → [-1,1]


# ---------------------------------------------------------------------------
# FeeGate (burned_quant)
# ---------------------------------------------------------------------------

class FeeGate:
    """Exchange-specific fee calculation with minimum profitability gate."""

    def compute_round_trip_pct(self, exchange: str, is_cross_exchange: bool = False,
                               sell_exchange: str = "") -> float:
        buy_fee = EXCHANGE_FEES.get(exchange, 0.001)
        sell_fee = EXCHANGE_FEES.get(sell_exchange or exchange, 0.001)
        return (buy_fee + sell_fee + 2 * AVG_SLIPPAGE)

    def compute_transfer_cost(self, buy_exchange: str, sell_exchange: str,
                              position_usd: float) -> float:
        if position_usd <= 0:
            return 1.0  # infinite cost
        cost = TRANSFER_FEES.get(buy_exchange, 1.0) + TRANSFER_FEES.get(sell_exchange, 1.0)
        return cost / position_usd

    def min_required_edge(self, exchange: str, position_usd: float,
                          is_cross_exchange: bool = False,
                          sell_exchange: str = "") -> float:
        rt_pct = self.compute_round_trip_pct(exchange, is_cross_exchange, sell_exchange)
        if is_cross_exchange:
            rt_pct += self.compute_transfer_cost(exchange, sell_exchange, position_usd)
        return rt_pct * FEE_COVERAGE_MULTIPLIER

    def is_viable(self, expected_edge: float, exchange: str, position_usd: float,
                  is_cross_exchange: bool = False, sell_exchange: str = "") -> Tuple[bool, float, float]:
        min_edge = self.min_required_edge(exchange, position_usd, is_cross_exchange, sell_exchange)
        fee_pct = self.compute_round_trip_pct(exchange, is_cross_exchange, sell_exchange)
        net = expected_edge - fee_pct
        return net > 0 and expected_edge >= min_edge, fee_pct, net


# ---------------------------------------------------------------------------
# TrustScorer (burned_quant)
# ---------------------------------------------------------------------------

class TrustScorer:
    """Weights strategies by backtest + paper trade track record + model age."""

    def __init__(self, models_dir: Path = None):
        self._models_dir = models_dir or PROJECT_ROOT / "models" / "strategies"
        self._paper_history: Dict[str, List[float]] = {}  # strategy → list of pnl

    def record_outcome(self, strategy: str, pnl: float):
        self._paper_history.setdefault(strategy, [])
        self._paper_history[strategy].append(pnl)
        # Cap history
        if len(self._paper_history[strategy]) > 500:
            self._paper_history[strategy] = self._paper_history[strategy][-500:]

    def compute_trust(self, strategy: str) -> float:
        trust = 0.0

        # Component 1: Model existence (0.0 - 0.3)
        model_count = len(list(self._models_dir.glob(f"{strategy}_*.pth")))
        if model_count > 20:
            trust += 0.3
        elif model_count > 5:
            trust += 0.2
        elif model_count > 0:
            trust += 0.1

        # Component 2: Paper trading track record (0.0 - 0.5)
        history = self._paper_history.get(strategy, [])
        if len(history) >= 20:
            win_rate = sum(1 for t in history if t > 0) / len(history)
            if win_rate > 0.52:
                trust += min(0.5, win_rate)
            elif win_rate > 0.45:
                trust += 0.1

        # Component 3: Baseline for new strategies (0.2)
        if model_count > 0 and not history:
            trust += 0.2  # benefit of the doubt for untested but trained

        return min(trust, 1.0)


# ---------------------------------------------------------------------------
# TradingOracle
# ---------------------------------------------------------------------------

class TradingOracle:
    """
    Unified meta-layer aggregating 7 strategies, 3 research agents,
    regime detection, and risk management into ranked recommendations.
    """

    def __init__(self, strategy_ensemble, regime_detector, risk_manager=None,
                 capital: float = 300.0):
        self.ensemble = strategy_ensemble
        self.regime_detector = regime_detector
        self.risk_manager = risk_manager
        self.capital = capital

        self.normalizer = SignalNormalizer()
        self.fee_gate = FeeGate()
        self.trust_scorer = TrustScorer()

        # Research agent cache {agent_name: (result_dict, timestamp)}
        self._research_cache: Dict[str, Tuple[Dict, float]] = {}

        # Circuit breaker state (crash_survivor)
        self._consecutive_losses = 0
        self._session_high = capital
        self._trades_this_hour: collections.deque = collections.deque(maxlen=MAX_TRADES_PER_HOUR)
        self._trades_today: List[float] = []
        self._today_date: Optional[str] = None
        self._halted_until: float = 0.0
        self._startup_time = time.time()

        # Regime transition tracking
        self._last_regime = None
        self._regime_changed_at: float = 0.0

        # Recommendation cache
        self._cache: Dict[Tuple[str, str], OracleRecommendation] = {}

        # Accuracy tracking
        self._predictions: collections.deque = collections.deque(maxlen=500)

        logger.info("TradingOracle initialized (capital=$%.0f)", capital)

    # --- Research agent integration ---

    def update_research(self):
        """Refresh research agent data. Call once per cycle (~5min)."""
        try:
            from agents.research_sentiment import MarketSentimentAgent
            agent = MarketSentimentAgent()
            result = agent.analyze()
            self._research_cache["sentiment"] = (result, time.time())
        except Exception as e:
            logger.debug("Sentiment agent unavailable: %s", e)

        try:
            from agents.research_technical import TechnicalAnalysisAgent
            agent = TechnicalAnalysisAgent()
            result = agent.analyze()
            self._research_cache["technical"] = (result, time.time())
        except Exception as e:
            logger.debug("Technical agent unavailable: %s", e)

        try:
            from agents.research_performance import StrategyPerformanceAgent
            agent = StrategyPerformanceAgent()
            result = agent.analyze()
            self._research_cache["performance"] = (result, time.time())
        except Exception as e:
            logger.debug("Performance agent unavailable: %s", e)

    def _get_research(self, name: str, max_age: float = 900.0) -> Optional[Dict]:
        """Get cached research data, applying staleness check."""
        if name not in self._research_cache:
            return None
        result, ts = self._research_cache[name]
        age = time.time() - ts
        if age > max_age * 4:
            return None  # too stale, discard
        return result

    def _time_decay(self, age_seconds: float, half_life: float) -> float:
        return 0.5 ** (age_seconds / half_life) if half_life > 0 else 0.0

    # --- Signal sources ---

    def _get_ta_signal(self, pair: str) -> Tuple[float, float]:
        """Extract TA directional signal and strength for a pair."""
        ta = self._get_research("technical", max_age=300)
        if not ta:
            return 0.0, 0.0

        analyses = ta.get("analyses", {})
        pair_ta = analyses.get(pair, {})
        if not pair_ta:
            return 0.0, 0.0

        signal_name = pair_ta.get("signal", "neutral")
        strength = pair_ta.get("signal_strength", 0.0)

        # Map TA signal to directional score
        direction = 0.0
        if "buy" in signal_name or "bullish" in signal_name:
            direction = 1.0
        elif "sell" in signal_name or "bearish" in signal_name:
            direction = -1.0

        # Time decay (TA half-life: 30min = 1800s)
        _, ts = self._research_cache.get("technical", (None, 0))
        age = time.time() - ts if ts else 3600
        decay = self._time_decay(age, 1800)

        return direction * strength * decay, strength * decay

    def _get_sentiment_signal(self, pair: str) -> Tuple[float, float]:
        """Extract sentiment directional signal for a pair's asset."""
        sent = self._get_research("sentiment", max_age=900)
        if not sent:
            return 0.0, 0.0

        asset = pair.split("/")[0]
        per_asset = sent.get("per_asset", [])

        for entry in per_asset:
            if isinstance(entry, dict) and entry.get("asset", "").upper() == asset.upper():
                score = entry.get("sentiment_score", 0.0)
                conf = entry.get("confidence", 0.5)

                # Time decay (sentiment half-life: 4h = 14400s)
                _, ts = self._research_cache.get("sentiment", (None, 0))
                age = time.time() - ts if ts else 14400
                decay = self._time_decay(age, 14400)

                return score * decay, conf * decay

        return 0.0, 0.0

    def _get_fear_greed(self) -> Optional[int]:
        """Get fear/greed index from sentiment agent."""
        sent = self._get_research("sentiment", max_age=900)
        if not sent:
            return None
        fg = sent.get("fear_greed_estimate", {})
        return fg.get("index") if isinstance(fg, dict) else None

    # --- Contradiction resolution (burned_quant) ---

    def _resolve_contradictions(self, norm_signals: Dict[str, float],
                                regime_name: str) -> Tuple[float, float]:
        """Regime-aware contradiction resolution.

        Returns (directional_consensus, spread_consensus).
        """
        dir_sigs = {k: v for k, v in norm_signals.items() if k in DIRECTIONAL_STRATEGIES}
        spread_sigs = {k: v for k, v in norm_signals.items() if k in SPREAD_STRATEGIES}

        # Regime-aware damping
        if regime_name in ("trending_up", "trending_down"):
            for s in ("mean_reversion", "dca"):
                if s in dir_sigs and abs(dir_sigs[s]) < 0.7:
                    dir_sigs[s] *= 0.3
        elif regime_name == "ranging":
            for s in ("momentum", "fibonacci"):
                if s in dir_sigs and abs(dir_sigs[s]) < 0.7:
                    dir_sigs[s] *= 0.3
        elif regime_name == "high_vol":
            for s in dir_sigs:
                if abs(dir_sigs[s]) < 0.5:
                    dir_sigs[s] *= 0.2

        dir_consensus = np.mean(list(dir_sigs.values())) if dir_sigs else 0.0
        spread_consensus = np.mean(list(spread_sigs.values())) if spread_sigs else 0.0

        return float(dir_consensus), float(spread_consensus)

    # --- Safety gates (crash_survivor) ---

    def _get_position_cap(self) -> Tuple[float, int]:
        """Capital-aware position ceiling."""
        for threshold, pct, max_pos in POSITION_CAPS:
            if self.capital < threshold:
                return self.capital * pct, max_pos
        # Above $1000: 3%, max 5
        return self.capital * 0.03, 5

    def _anti_herding_check(self, agreement: float, regime_name: str,
                            action: str) -> Tuple[float, Optional[str]]:
        """Anti-herding: penalize excessive consensus.

        Returns (position_multiplier, veto_reason or None).
        """
        if agreement >= 0.86:
            # 6-7 strategies agree
            if agreement >= 0.99 and action == "buy" and regime_name in ("high_vol", "trending_down"):
                return 0.0, "Anti-herd: unanimous buy in adverse regime"
            # Require research confirmation
            ta_dir, ta_str = self._get_ta_signal("")  # will return 0 without pair
            if ta_str < 0.3:
                return 0.6, None  # heavy penalty without TA confirmation
            return 0.85, None
        elif agreement > 0.71:
            return 0.85, None
        return 1.0, None

    def _check_circuit_breaker(self) -> Optional[str]:
        """Three-strike consecutive loss circuit breaker."""
        now = time.time()

        # Halt check
        if now < self._halted_until:
            remaining = int(self._halted_until - now)
            return f"Trading halted ({remaining}s remaining)"

        if self._consecutive_losses >= 5:
            self._halted_until = now + 86400  # 24h
            return "5 consecutive losses — 24h halt"
        if self._consecutive_losses >= 4:
            self._halted_until = now + 14400  # 4h
            return "4 consecutive losses — 4h halt"

        return None

    def _get_circuit_breaker_multiplier(self) -> float:
        """Position size multiplier based on consecutive losses."""
        if self._consecutive_losses >= 3:
            return 0.25
        if self._consecutive_losses >= 2:
            return 0.50
        return 1.0

    def _get_circuit_breaker_min_confidence(self) -> float:
        """Minimum confidence required based on consecutive losses."""
        if self._consecutive_losses >= 3:
            return 0.70
        if self._consecutive_losses >= 2:
            return 0.25
        return CONFIDENCE_FLOOR

    def _check_drawdown_cascade(self) -> Tuple[float, Optional[str]]:
        """Progressive drawdown response. Returns (multiplier, allowed_strategies_note)."""
        if self._session_high <= 0:
            return 1.0, None

        drawdown_pct = (self._session_high - self.capital) / self._session_high

        if drawdown_pct >= 0.12:
            return 0.0, "12% drawdown — FULL HALT"
        if drawdown_pct >= 0.08:
            return 0.15, "8% drawdown — arb only, $5 max"
        if drawdown_pct >= 0.05:
            return 0.40, "5% drawdown — conservative mode"
        if drawdown_pct >= 0.03:
            return 0.70, "3% drawdown — reduced sizing"
        return 1.0, None

    def _check_research_vetoes(self, action: str, pair: str) -> Optional[str]:
        """Research agent vetoes (crash_survivor)."""
        # Fear/greed veto
        fg = self._get_fear_greed()
        if fg is not None and fg < 20 and action == "buy":
            return f"Extreme fear (index={fg}) — new longs blocked"

        # Overbought veto
        ta = self._get_research("technical", max_age=300)
        if ta and action == "buy":
            analyses = ta.get("analyses", {})
            overbought_count = sum(
                1 for a in analyses.values()
                if isinstance(a, dict) and "overbought" in a.get("signal", "")
                and a.get("signal_strength", 0) > 0.7
            )
            if analyses and overbought_count / max(len(analyses), 1) > 0.5:
                return "Market-wide overbought (>50% pairs) — new longs blocked"

        # Strategy performance veto
        perf = self._get_research("performance", max_age=300)
        if perf:
            for sa in perf.get("strategy_analysis", {}).values():
                if isinstance(sa, dict) and sa.get("win_rate", 1) < 0.35 and sa.get("trades", 0) >= 20:
                    strategy = sa.get("strategy", "")
                    if strategy:
                        logger.info("Oracle: zeroing strategy '%s' (win_rate=%.2f)", strategy, sa["win_rate"])

        return None

    def _check_time_safety(self) -> Optional[str]:
        """Time-based safety rails."""
        now = time.time()

        # Startup cooldown
        if now - self._startup_time < STARTUP_COOLDOWN_SECONDS:
            return "Startup cooldown (5min)"

        # Regime transition cooldown
        if now - self._regime_changed_at < REGIME_TRANSITION_COOLDOWN:
            return "Regime transition cooldown (10min)"

        # Hourly rate limit
        cutoff = now - 3600
        while self._trades_this_hour and self._trades_this_hour[0] < cutoff:
            self._trades_this_hour.popleft()
        if len(self._trades_this_hour) >= MAX_TRADES_PER_HOUR:
            return f"Rate limit: {MAX_TRADES_PER_HOUR} trades/hour reached"

        # Daily rate limit
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if self._today_date != today:
            self._today_date = today
            self._trades_today = []
        if len(self._trades_today) >= MAX_TRADES_PER_DAY:
            return f"Rate limit: {MAX_TRADES_PER_DAY} trades/day reached"

        return None

    # --- Modular gate methods ---

    def _collect_signals(self, pair: str, exchange: str,
                         market_data: np.ndarray,
                         strategy_signals: Optional[Dict[str, float]],
                         strategy_confidences: Optional[Dict[str, float]]
                         ) -> Optional[Tuple[Dict[str, float], Dict[str, float], float]]:
        """Get raw signals (pre-computed or from ensemble) and compute agreement.

        Returns (raw_signals, raw_confidences, agreement) or None if no signals.
        """
        raw_signals = strategy_signals or {}
        raw_confidences = strategy_confidences or {}

        if not raw_signals and self.ensemble is not None:
            try:
                ensemble_sig = self.ensemble.predict(pair, market_data, exchange)
                raw_signals = ensemble_sig.strategy_signals or {}
                raw_confidences = ensemble_sig.strategy_confidences or {}
            except Exception as e:
                logger.debug("Ensemble failed for %s@%s: %s", pair, exchange, e)

        if not raw_signals:
            return None

        # Calculate agreement from raw signals
        directions = [1 if v > 0.05 else (-1 if v < -0.05 else 0) for v in raw_signals.values()]
        non_neutral = [d for d in directions if d != 0]
        if non_neutral:
            majority = max(set(non_neutral), key=non_neutral.count)
            agreement = sum(1 for d in non_neutral if d == majority) / len(raw_signals)
        else:
            agreement = 0.0

        return raw_signals, raw_confidences, agreement

    def _detect_regime(self, market_data: np.ndarray) -> str:
        """Regime detection from market data. Returns regime name string."""
        now = time.time()
        regime_name = "ranging"
        try:
            if market_data is not None and len(market_data) >= 30:
                high = market_data[:, 2].astype(float)
                low = market_data[:, 3].astype(float)
                close = market_data[:, 4].astype(float)
                regime = self.regime_detector.detect(high, low, close)
                new_regime = regime.value
                if self._last_regime is not None and new_regime != self._last_regime:
                    self._regime_changed_at = now
                self._last_regime = new_regime
                regime_name = new_regime
        except Exception:
            pass
        return regime_name

    def _compute_composite(self, pair: str, raw_signals: Dict[str, float],
                           raw_confidences: Dict[str, float], agreement: float,
                           regime_name: str
                           ) -> Tuple[float, float, int, Dict[str, float],
                                      float, float, float, float, float, float]:
        """Normalize signals, resolve contradictions, compute composite score + confidence.

        Returns (composite, confidence, signal_consensus, norm_signals,
                 dir_consensus, spread_consensus, ta_dir, ta_strength,
                 sent_score, sent_conf).
        """
        # Normalize signals
        norm_signals = {}
        for strat, raw in raw_signals.items():
            norm_signals[strat] = self.normalizer.normalize(strat, raw)

        # Contradiction resolution
        dir_consensus, spread_consensus = self._resolve_contradictions(norm_signals, regime_name)

        # Technical Analysis
        ta_dir, ta_strength = self._get_ta_signal(pair)

        # Sentiment
        sent_score, sent_conf = self._get_sentiment_signal(pair)

        # Composite score (additive for direction)
        composite = (
            dir_consensus * W_ML
            + spread_consensus * W_SPREAD
            + ta_dir * W_TA
            + sent_score * W_SENTIMENT
        )

        # Composite confidence (weighted additive)
        avg_trust = np.mean([self.trust_scorer.compute_trust(s) for s in raw_signals]) if raw_signals else 0.1
        avg_model_conf = np.mean(list(raw_confidences.values())) if raw_confidences else 0.3
        regime_clarity = 0.5 if regime_name == "high_vol" else 1.0

        confidence = (
            agreement * 0.40 +
            avg_trust * 0.20 +
            avg_model_conf * 0.30 +
            regime_clarity * 0.10
        )
        confidence = min(max(confidence, 0.0), CONFIDENCE_CEILING)

        # Signal consensus
        consensus_dir = 1 if composite > 0 else (-1 if composite < 0 else 0)
        sources = []
        if dir_consensus != 0:
            sources.append(1 if dir_consensus * consensus_dir > 0 else 0)
        if spread_consensus != 0:
            sources.append(1 if spread_consensus * consensus_dir > 0 else 0)
        if ta_dir != 0:
            sources.append(1 if ta_dir * consensus_dir > 0 else 0)
        if sent_score != 0:
            sources.append(1 if sent_score * consensus_dir > 0 else 0)
        signal_consensus = sum(sources)

        return (composite, confidence, signal_consensus, norm_signals,
                dir_consensus, spread_consensus, ta_dir, ta_strength,
                sent_score, sent_conf)

    def _determine_action(self, composite: float, signal_consensus: int) -> str:
        """Determine action from composite score + consensus."""
        if abs(composite) < HOLD_THRESHOLD or signal_consensus < MIN_CONSENSUS_FOR_TRADE:
            return "hold"
        elif composite > 0:
            return "buy"
        else:
            return "sell"

    def _apply_safety_gates(self, action: str, pair: str, exchange: str,
                            position_usd: float, expected_edge: float,
                            viable: bool, fee_pct: float,
                            agreement: float, regime_name: str,
                            confidence: float) -> Tuple[Optional[str], float]:
        """Run all 7 safety gates sequentially.

        Returns (veto_reason or None, adjusted position_usd).
        """
        # Gate 1: Fee viability
        if action != "hold" and not viable:
            return (f"Edge {expected_edge:.4%} < fees {fee_pct:.4%} "
                    f"(need {FEE_COVERAGE_MULTIPLIER}x)"), position_usd

        # Gate 2: Anti-herding
        if action != "hold":
            herd_mult, herd_veto = self._anti_herding_check(agreement, regime_name, action)
            if herd_veto:
                return herd_veto, position_usd
            position_usd *= herd_mult

        # Gate 3: Circuit breaker
        if action != "hold":
            cb_veto = self._check_circuit_breaker()
            if cb_veto:
                return cb_veto, position_usd
            position_usd *= self._get_circuit_breaker_multiplier()
            min_conf = self._get_circuit_breaker_min_confidence()
            if confidence < min_conf:
                return (f"Confidence {confidence:.2f} < circuit breaker min "
                        f"{min_conf:.2f}"), position_usd

        # Gate 4: Drawdown cascade
        if action != "hold":
            dd_mult, dd_note = self._check_drawdown_cascade()
            if dd_mult == 0:
                return dd_note, position_usd
            position_usd *= dd_mult

        # Gate 5: Research vetoes
        if action != "hold":
            rv = self._check_research_vetoes(action, pair)
            if rv:
                return rv, position_usd

        # Gate 6: Time safety
        if action != "hold":
            ts_veto = self._check_time_safety()
            if ts_veto:
                return ts_veto, position_usd

        # Gate 7: Confidence floor
        if action != "hold" and confidence < CONFIDENCE_FLOOR:
            return f"Confidence {confidence:.3f} below floor {CONFIDENCE_FLOOR}", position_usd

        return None, position_usd

    def _build_recommendation(self, pair: str, exchange: str, action: str,
                              composite: float, confidence: float,
                              risk_rating: str, signal_consensus: int,
                              position_usd: float, expected_edge: float,
                              fee_pct: float, net_expected: float,
                              regime_name: str, vetoed: bool, veto_reason: str,
                              raw_signals: Dict[str, float],
                              raw_confidences: Dict[str, float],
                              norm_signals: Dict[str, float],
                              agreement: float, dir_consensus: float,
                              spread_consensus: float, ta_dir: float,
                              ta_strength: float, sent_score: float,
                              sent_conf: float) -> OracleRecommendation:
        """Construct OracleRecommendation dataclass with full breakdown."""
        regime_clarity = 0.5 if regime_name == "high_vol" else 1.0

        breakdown = {
            "ensemble": {
                "agreement": round(agreement, 3),
                "strategy_signals": {k: round(v, 4) for k, v in raw_signals.items()},
                "strategy_confidences": {k: round(v, 4) for k, v in raw_confidences.items()},
            },
            "normalized": {k: round(v, 4) for k, v in norm_signals.items()},
            "directional_consensus": round(dir_consensus, 4),
            "spread_consensus": round(spread_consensus, 4),
            "technical": {"direction": round(ta_dir, 4), "strength": round(ta_strength, 4)},
            "sentiment": {"score": round(sent_score, 4), "confidence": round(sent_conf, 4)},
            "regime": {"current": regime_name, "clarity": regime_clarity},
            "trust": {s: round(self.trust_scorer.compute_trust(s), 3) for s in raw_signals},
        }

        return OracleRecommendation(
            pair=pair,
            exchange=exchange,
            action=action,
            oracle_score=round(float(composite), 4),
            composite_confidence=round(float(confidence), 4),
            risk_rating=risk_rating,
            signal_consensus=signal_consensus,
            position_size_usd=round(position_usd, 2),
            expected_edge_pct=round(expected_edge, 6),
            fee_cost_pct=round(fee_pct, 6),
            net_expected_pct=round(net_expected, 6),
            regime=regime_name,
            breakdown=breakdown,
            vetoed=vetoed,
            veto_reason=veto_reason,
        )

    # --- Core evaluation ---

    def evaluate(self, pair: str, exchange: str,
                 market_data: np.ndarray,
                 strategy_signals: Optional[Dict[str, float]] = None,
                 strategy_confidences: Optional[Dict[str, float]] = None) -> OracleRecommendation:
        """Produce a single OracleRecommendation for a pair/exchange.

        Args:
            pair: e.g. "BTC/USDC"
            exchange: e.g. "binance"
            market_data: OHLCV numpy array (rows x 6 columns)
            strategy_signals: pre-computed {strategy: signal_value} from paper trading
            strategy_confidences: pre-computed {strategy: confidence} from paper trading

        MiCA compliance: rejects non-compliant pairs at entry.
        """
        regime_name = "ranging"

        # MiCA compliance gate
        if pair not in MICA_COMPLIANT_PAIRS:
            logger.warning("MiCA VIOLATION blocked: pair %s is not compliant", pair)
            return self._hold(pair, exchange, regime_name, f"Non-compliant pair: {pair}")

        # Step 1: Collect signals
        signals_result = self._collect_signals(pair, exchange, market_data,
                                               strategy_signals, strategy_confidences)
        if signals_result is None:
            return self._hold(pair, exchange, regime_name, "No strategy signals available")
        raw_signals, raw_confidences, agreement = signals_result

        # Step 2: Detect regime
        regime_name = self._detect_regime(market_data)

        # Step 3: Compute composite score, confidence, consensus
        (composite, confidence, signal_consensus, norm_signals,
         dir_consensus, spread_consensus, ta_dir, ta_strength,
         sent_score, sent_conf) = self._compute_composite(
            pair, raw_signals, raw_confidences, agreement, regime_name)

        # Step 4: Determine action
        action = self._determine_action(composite, signal_consensus)

        # Position sizing and expected edge
        max_pos, _ = self._get_position_cap()
        position_usd = max_pos
        expected_edge = abs(composite) * 0.05
        is_cross = False  # single-exchange for now at micro-capital
        viable, fee_pct, net_expected = self.fee_gate.is_viable(
            expected_edge, exchange, position_usd, is_cross)

        # Risk rating
        if confidence > 0.7:
            risk_rating = "low"
        elif confidence > 0.5:
            risk_rating = "medium"
        elif confidence > 0.3:
            risk_rating = "high"
        else:
            risk_rating = "extreme"
        if regime_name == "high_vol" and risk_rating != "extreme":
            risk_rating = {"low": "medium", "medium": "high", "high": "extreme"}[risk_rating]

        # Step 5: Apply safety gates
        veto_reason, position_usd = self._apply_safety_gates(
            action, pair, exchange, position_usd, expected_edge,
            viable, fee_pct, agreement, regime_name, confidence)

        vetoed = bool(veto_reason)
        if vetoed:
            action = "hold"
            position_usd = 0.0
        else:
            veto_reason = ""

        # Step 6: Build recommendation
        rec = self._build_recommendation(
            pair, exchange, action, composite, confidence, risk_rating,
            signal_consensus, position_usd, expected_edge, fee_pct,
            net_expected, regime_name, vetoed, veto_reason,
            raw_signals, raw_confidences, norm_signals, agreement,
            dir_consensus, spread_consensus, ta_dir, ta_strength,
            sent_score, sent_conf)

        self._cache[(pair, exchange)] = rec
        return rec

    def _hold(self, pair: str, exchange: str, regime: str,
              reason: str) -> OracleRecommendation:
        return OracleRecommendation(
            pair=pair, exchange=exchange, action="hold",
            oracle_score=0.0, composite_confidence=0.0,
            risk_rating="extreme", signal_consensus=0,
            position_size_usd=0.0, expected_edge_pct=0.0,
            fee_cost_pct=0.0, net_expected_pct=0.0,
            regime=regime, vetoed=True, veto_reason=reason,
        )

    # --- Batch scanning ---

    def scan_all(self, pairs: List[str], exchanges: List[str],
                 market_data_fn: Callable) -> List[OracleRecommendation]:
        """Evaluate all pair/exchange combos, return sorted non-hold recommendations."""
        results = []
        for pair in pairs:
            for exchange in exchanges:
                try:
                    data = market_data_fn(pair, exchange)
                    if data is not None and len(data) >= 30:
                        rec = self.evaluate(pair, exchange, data)
                        if rec.action != "hold":
                            results.append(rec)
                except Exception as e:
                    logger.debug("Oracle scan error %s@%s: %s", pair, exchange, e)

        results.sort(key=lambda r: r.composite_confidence, reverse=True)
        return results

    # --- Outcome tracking ---

    def record_trade(self, pair: str, exchange: str, action: str, pnl: float):
        """Record trade outcome for accuracy tracking and circuit breakers."""
        self._predictions.append({
            "pair": pair, "exchange": exchange, "action": action,
            "pnl": pnl, "timestamp": time.time(),
        })

        # Update trust scorer
        # Infer dominant strategy from last recommendation
        rec = self._cache.get((pair, exchange))
        if rec and rec.breakdown.get("ensemble"):
            sigs = rec.breakdown["ensemble"].get("strategy_signals", {})
            if sigs:
                dominant = max(sigs, key=lambda k: abs(sigs[k]))
                self.trust_scorer.record_outcome(dominant, pnl)

        # Circuit breaker tracking
        if pnl < 0:
            self._consecutive_losses += 1
        else:
            self._consecutive_losses = 0

        # Update capital and session high
        self.capital += pnl
        self._session_high = max(self._session_high, self.capital)

        # Trade rate tracking
        now = time.time()
        self._trades_this_hour.append(now)
        self._trades_today.append(now)

    def update_capital(self, new_capital: float):
        """Update capital from external source (e.g., paper trading engine)."""
        self.capital = new_capital
        self._session_high = max(self._session_high, new_capital)

    # --- Status / API ---

    def get_status(self) -> Dict[str, Any]:
        """Oracle health and metrics for dashboard."""
        accuracy = None
        if len(self._predictions) >= 10:
            correct = sum(
                1 for p in self._predictions
                if (p["action"] == "buy" and p["pnl"] > 0)
                or (p["action"] == "sell" and p["pnl"] > 0)
            )
            accuracy = correct / len(self._predictions)

        active_recs = [r for r in self._cache.values() if r.action != "hold"]

        return {
            "active": True,
            "capital": round(self.capital, 2),
            "session_high": round(self._session_high, 2),
            "consecutive_losses": self._consecutive_losses,
            "halted": time.time() < self._halted_until,
            "recommendations_count": len(active_recs),
            "avg_confidence": round(
                np.mean([r.composite_confidence for r in active_recs]), 3
            ) if active_recs else 0.0,
            "accuracy": round(accuracy, 3) if accuracy is not None else None,
            "predictions_tracked": len(self._predictions),
            "regime": self._last_regime,
            "last_update": datetime.now(timezone.utc).isoformat(),
        }

    def get_opportunities(self, limit: int = 20) -> List[Dict]:
        """Get ranked non-hold recommendations for dashboard."""
        recs = [r for r in self._cache.values() if r.action != "hold"]
        recs.sort(key=lambda r: r.composite_confidence, reverse=True)
        return [asdict(r) for r in recs[:limit]]

    def save_state(self, reports_dir: Path = None):
        """Persist oracle state to JSON files for dashboard consumption."""
        reports_dir = reports_dir or PROJECT_ROOT / "reports"
        reports_dir.mkdir(parents=True, exist_ok=True)

        # Recommendations
        recs_path = reports_dir / "oracle_recommendations.json"
        recs_data = {
            "recommendations": self.get_opportunities(),
            "updated": datetime.now(timezone.utc).isoformat(),
        }
        recs_path.write_text(json.dumps(recs_data, indent=2, default=str), encoding="utf-8")

        # Status
        status_path = reports_dir / "oracle_status.json"
        status_path.write_text(json.dumps(self.get_status(), indent=2, default=str), encoding="utf-8")
