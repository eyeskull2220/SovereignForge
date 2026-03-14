#!/usr/bin/env python3
"""
SovereignForge - Strategy Ensemble (Collective Brain)
Combines signals from all strategy models into unified trading decisions.
Uses confidence-weighted aggregation across arbitrage, fibonacci, grid, and DCA.

Includes CrossExchangeScorer for detecting cross-exchange arbitrage opportunities
by comparing ML signals for the same pair across different exchanges.
"""

import gc
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
import torch
import torch.nn as nn

from multi_strategy_training import (
    STRATEGY_MODELS,
    StrategyType,
    engineer_features,
)

logger = logging.getLogger(__name__)


@dataclass
class EnsembleSignal:
    """Unified trading signal from the collective brain."""
    pair: str
    action: str  # "buy", "sell", "hold"
    confidence: float  # Overall confidence [0, 1]
    agreement_score: float  # Fraction of strategies agreeing on direction [0, 1]
    strategy_signals: Dict[str, float] = field(default_factory=dict)  # per-strategy raw signals
    strategy_confidences: Dict[str, float] = field(default_factory=dict)  # per-strategy confidence
    timestamp: datetime = field(default_factory=datetime.now)


class StrategyEnsemble:
    """
    Collective brain — loads models for all 4 strategies and combines
    their predictions using confidence-weighted aggregation.

    Each strategy produces (signal, confidence, magnitude).
    The final decision weights each signal by: config_weight * model_confidence.
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        models_dir: str = "models/strategies",
        hold_threshold: float = 0.15,
    ):
        self.models_dir = Path(models_dir)
        self.hold_threshold = hold_threshold  # Below this, signal is "hold"

        # Parse strategy weights from config
        strategies_config = (config or {}).get("strategies", {})
        self.strategy_weights: Dict[StrategyType, float] = {}
        self.strategy_enabled: Dict[StrategyType, bool] = {}

        for st in StrategyType:
            st_config = strategies_config.get(st.value, {})
            self.strategy_weights[st] = st_config.get("weight", 0.25)
            self.strategy_enabled[st] = st_config.get("enabled", True)

        # Normalize weights so enabled strategies sum to 1.0
        total_weight = sum(
            w for st, w in self.strategy_weights.items()
            if self.strategy_enabled.get(st, True)
        )
        if total_weight > 0:
            for st in StrategyType:
                if self.strategy_enabled.get(st, True):
                    self.strategy_weights[st] /= total_weight

            # Model storage: strategy → {pair:exchange: model}
        self.models: Dict[StrategyType, Dict[str, nn.Module]] = {
            st: {} for st in StrategyType
        }
        self.exchanges: List[str] = []  # Populated during load

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        logger.info(
            f"StrategyEnsemble initialized: "
            f"weights={{{', '.join(f'{s.value}: {w:.2f}' for s, w in self.strategy_weights.items())}}}"
        )

    def load_all_models(
        self,
        pairs: List[str],
        exchanges: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """Load models for all enabled strategies, pairs, and exchanges.

        Args:
            pairs: Trading pairs to load models for
            exchanges: Exchanges to load models for. If None, loads exchange-agnostic models.

        Returns: {strategy:pair:exchange: loaded_successfully}
        """
        if exchanges:
            self.exchanges = exchanges

        results = {}

        for strategy in StrategyType:
            if not self.strategy_enabled.get(strategy, True):
                logger.info(f"Skipping disabled strategy: {strategy.value}")
                continue

            model_factory = STRATEGY_MODELS[strategy]

            for pair in pairs:
                pair_slug = pair.replace('/', '_').lower()

                # Determine which exchange-specific models to look for
                exchange_list = exchanges or [None]

                for exchange in exchange_list:
                    if exchange:
                        key = f"{strategy.value}:{pair}:{exchange}"
                        model_path = self.models_dir / f"{strategy.value}_{pair_slug}_{exchange}.pth"
                    else:
                        key = f"{strategy.value}:{pair}"
                        model_path = self.models_dir / f"{strategy.value}_{pair_slug}.pth"

                    if not model_path.exists():
                        results[key] = False
                        continue

                    try:
                        checkpoint = torch.load(
                            model_path, map_location=self.device, weights_only=True
                        )
                        config = checkpoint.get("config", {})
                        input_size = config.get("input_size", 10)
                        output_size = config.get("output_size", 3)

                        model = model_factory(input_size, output_size)
                        state_dict = checkpoint.get("model_state_dict", checkpoint)
                        model.load_state_dict(state_dict, strict=False)
                        model.to(self.device)
                        model.eval()

                        model_key = f"{pair}:{exchange}" if exchange else pair
                        self.models[strategy][model_key] = model
                        del checkpoint
                        gc.collect()
                        results[key] = True
                        logger.info(f"Loaded {strategy.value} model for {pair}@{exchange or 'default'}")

                    except Exception as e:
                        logger.error(f"Failed to load {strategy.value} model for {pair}@{exchange}: {e}")
                        results[key] = False

        loaded_count = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"Loaded {loaded_count}/{total} strategy models")
        return results

    def predict(self, pair: str, market_data: np.ndarray, exchange: Optional[str] = None) -> EnsembleSignal:
        """Run all strategy models and combine signals weighted by confidence.

        Args:
            pair: Trading pair (e.g. 'XRP/USDC')
            market_data: OHLCV array [N, 6] (timestamp, open, high, low, close, volume)
            exchange: Optional exchange name for exchange-specific models

        Returns:
            EnsembleSignal with combined action, confidence, and per-strategy breakdown
        """
        strategy_signals: Dict[str, float] = {}
        strategy_confidences: Dict[str, float] = {}
        weighted_signal = 0.0
        total_effective_weight = 0.0

        # Engineer features from raw OHLCV
        features, _ = engineer_features(market_data, seq_len=24)
        if len(features) == 0:
            return EnsembleSignal(
                pair=pair, action="hold", confidence=0.0,
                agreement_score=0.0,
            )

        # Use the last sequence for prediction — single tensor allocation
        input_tensor = torch.FloatTensor(features[-1:]).to(self.device)

        with torch.no_grad():
            for strategy in StrategyType:
                if not self.strategy_enabled.get(strategy, True):
                    continue

                # Try exchange-specific model first, then fall back to generic
                model_key = f"{pair}:{exchange}" if exchange else pair
                model = self.models.get(strategy, {}).get(model_key)
                if model is None and exchange:
                    model = self.models.get(strategy, {}).get(pair)  # Fallback to generic
                if model is None:
                    continue

                try:
                    assert not model.training, f"{strategy.value} model not in eval mode"
                    output = model(input_tensor)  # [1, 3]: signal, confidence, magnitude

                    raw_signal = output[0, 0].item()  # [-1, 1]
                    model_confidence = float(torch.sigmoid(output[0, 1]).item())

                    label = f"{strategy.value}@{exchange}" if exchange else strategy.value
                    strategy_signals[label] = raw_signal
                    strategy_confidences[label] = model_confidence

                    # Effective weight = config_weight * model_confidence
                    effective_weight = self.strategy_weights[strategy] * model_confidence
                    weighted_signal += raw_signal * effective_weight
                    total_effective_weight += effective_weight

                except Exception as e:
                    logger.error(f"Prediction failed for {strategy.value}/{pair}@{exchange}: {e}")

        # Determine action
        if total_effective_weight > 0:
            final_signal = weighted_signal / total_effective_weight
        else:
            final_signal = 0.0

        if abs(final_signal) < self.hold_threshold:
            action = "hold"
        elif final_signal > 0:
            action = "buy"
        else:
            action = "sell"

        # Calculate agreement score
        agreement_score = self._calculate_agreement(strategy_signals)

        # Overall confidence = weighted confidence * agreement
        overall_confidence = min(total_effective_weight * agreement_score, 1.0)

        return EnsembleSignal(
            pair=pair,
            action=action,
            confidence=overall_confidence,
            agreement_score=agreement_score,
            strategy_signals=strategy_signals,
            strategy_confidences=strategy_confidences,
        )

    def _calculate_agreement(self, signals: Dict[str, float]) -> float:
        """Calculate how many strategies agree on direction [0, 1]."""
        if not signals:
            return 0.0

        directions = []
        for signal in signals.values():
            if signal > 0.05:
                directions.append(1)
            elif signal < -0.05:
                directions.append(-1)
            else:
                directions.append(0)

        if not directions:
            return 0.0

        # Agreement = fraction of non-neutral strategies that agree with majority
        non_neutral = [d for d in directions if d != 0]
        if not non_neutral:
            return 0.5  # All neutral = moderate agreement on hold

        majority = max(set(non_neutral), key=non_neutral.count)
        agreeing = sum(1 for d in non_neutral if d == majority)
        return agreeing / len(non_neutral)

    def get_strategy_agreement(self, pair: str, market_data: np.ndarray) -> float:
        """Convenience: just return the agreement score."""
        signal = self.predict(pair, market_data)
        return signal.agreement_score

    def get_loaded_summary(self) -> Dict[str, Any]:
        """Get summary of loaded models."""
        summary = {}
        for strategy in StrategyType:
            pairs = list(self.models.get(strategy, {}).keys())
            summary[strategy.value] = {
                "enabled": self.strategy_enabled.get(strategy, True),
                "weight": self.strategy_weights.get(strategy, 0.0),
                "loaded_pairs": pairs,
                "count": len(pairs),
            }
        return summary


@dataclass
class CrossExchangeSignal:
    """Cross-exchange arbitrage signal comparing ML predictions across exchanges."""
    pair: str
    opportunity_score: float       # 0-1, how strong the arbitrage signal is
    risk_score: float              # 0-1, how risky (higher = riskier)
    reward_risk_ratio: float       # opportunity / risk
    buy_exchange: str              # exchange where ML says "buy" strongest
    sell_exchange: str             # exchange where ML says "sell" strongest
    signal_spread: float           # max(signal) - min(signal) across exchanges
    per_exchange: Dict[str, EnsembleSignal] = field(default_factory=dict)
    recommended_position_pct: float = 0.0
    timestamp: datetime = field(default_factory=datetime.now)


class CrossExchangeScorer:
    """
    Compares ML ensemble signals for the same pair across multiple exchanges
    to detect cross-exchange arbitrage opportunities.

    When exchange A's models say "buy" and exchange B's models say "sell",
    there may be a price divergence worth exploiting.
    """

    def __init__(
        self,
        ensemble: StrategyEnsemble,
        risk_manager=None,
        min_signal_spread: float = 0.2,
        min_confidence: float = 0.3,
    ):
        self.ensemble = ensemble
        self.risk_manager = risk_manager
        self.min_signal_spread = min_signal_spread
        self.min_confidence = min_confidence

    def score_pair(
        self,
        pair: str,
        exchange_data: Dict[str, np.ndarray],
    ) -> Optional[CrossExchangeSignal]:
        """Run ensemble on each exchange's data and compare signals.

        Args:
            pair: Trading pair (e.g. 'BTC/USDC')
            exchange_data: {exchange_name: OHLCV array [N, 6]}

        Returns:
            CrossExchangeSignal if opportunity detected, None otherwise
        """
        if len(exchange_data) < 2:
            return None

        # Get ensemble prediction per exchange
        signals: Dict[str, EnsembleSignal] = {}
        for exchange, data in exchange_data.items():
            if data is None or len(data) < 25:
                continue
            sig = self.ensemble.predict(pair, data, exchange=exchange)
            if sig.confidence >= self.min_confidence:
                signals[exchange] = sig

        if len(signals) < 2:
            return None

        # Extract the weighted signal value per exchange
        exchange_values = {}
        for exchange, sig in signals.items():
            # Reconstruct the final weighted signal from strategy_signals
            if sig.strategy_signals:
                vals = list(sig.strategy_signals.values())
                exchange_values[exchange] = sum(vals) / len(vals)
            else:
                exchange_values[exchange] = 0.0

        # Find most bullish and most bearish exchanges
        most_bullish = max(exchange_values, key=exchange_values.get)
        most_bearish = min(exchange_values, key=exchange_values.get)

        signal_spread = exchange_values[most_bullish] - exchange_values[most_bearish]

        if signal_spread < self.min_signal_spread:
            return None

        # Directional divergence: do exchanges disagree on direction?
        actions = {ex: sig.action for ex, sig in signals.items()}
        has_buy = any(a == "buy" for a in actions.values())
        has_sell = any(a == "sell" for a in actions.values())
        directional_divergence = has_buy and has_sell

        # Opportunity score: spread × avg confidence × divergence bonus
        avg_confidence = np.mean([s.confidence for s in signals.values()])
        avg_agreement = np.mean([s.agreement_score for s in signals.values()])
        divergence_bonus = 1.5 if directional_divergence else 1.0

        opportunity_score = min(
            signal_spread * avg_confidence * avg_agreement * divergence_bonus, 1.0
        )

        # Risk score (5-factor)
        risk_score = self._calculate_risk_score(
            signals, signal_spread, avg_confidence, exchange_data
        )

        # Reward/risk ratio
        reward_risk = opportunity_score / max(risk_score, 0.01)

        # Position sizing via RiskManager if available
        recommended_pct = 0.0
        if self.risk_manager is not None:
            opp_dict = {
                'pair': pair,
                'spread_prediction': signal_spread,
                'confidence': avg_confidence,
                'risk_score': risk_score,
                'prices': {ex: float(data[-1, 4]) for ex, data in exchange_data.items()
                           if data is not None and len(data) > 0},
            }
            if hasattr(self.risk_manager, 'calculate_position_size'):
                pos_size = self.risk_manager.calculate_position_size(opp_dict)
                if isinstance(pos_size, dict):
                    recommended_pct = pos_size.get('position_size_pct', 0.0)
                elif isinstance(pos_size, (int, float)):
                    # RiskManager returns raw size; convert to % of portfolio
                    portfolio = getattr(self.risk_manager, 'portfolio_value',
                                        getattr(self.risk_manager, 'current_capital', 10000))
                    avg_price = np.mean([float(d[-1, 4]) for d in exchange_data.values()
                                         if d is not None and len(d) > 0])
                    recommended_pct = (pos_size * avg_price / portfolio) if portfolio > 0 else 0.0

        # Buy on the exchange with most bullish signal, sell on most bearish
        buy_exchange = most_bullish
        sell_exchange = most_bearish

        return CrossExchangeSignal(
            pair=pair,
            opportunity_score=round(opportunity_score, 4),
            risk_score=round(risk_score, 4),
            reward_risk_ratio=round(reward_risk, 2),
            buy_exchange=buy_exchange,
            sell_exchange=sell_exchange,
            signal_spread=round(signal_spread, 4),
            per_exchange=signals,
            recommended_position_pct=round(recommended_pct * 100, 2),
        )

    def _calculate_risk_score(
        self,
        signals: Dict[str, EnsembleSignal],
        signal_spread: float,
        avg_confidence: float,
        exchange_data: Dict[str, np.ndarray],
    ) -> float:
        """5-factor risk assessment for cross-exchange arbitrage."""

        # 1. Confidence risk: low confidence = higher risk
        confidence_risk = 1.0 - avg_confidence

        # 2. Agreement risk: low intra-strategy agreement = higher risk
        avg_agreement = np.mean([s.agreement_score for s in signals.values()])
        agreement_risk = 1.0 - avg_agreement

        # 3. Volatility risk: high volatility across exchanges = higher risk
        volatilities = []
        for data in exchange_data.values():
            if data is not None and len(data) > 20:
                returns = np.diff(np.log(data[-20:, 4] + 1e-10))
                volatilities.append(np.std(returns))
        vol_risk = min(np.mean(volatilities) / 0.05, 1.0) if volatilities else 0.5

        # 4. Data quality risk: fewer exchanges or small data = higher risk
        data_risk = max(0.0, 1.0 - len(signals) / 4.0)

        # 5. Spread stability risk: very large spread may be anomalous
        spread_risk = min(signal_spread / 1.0, 1.0) * 0.3  # Small weight

        # Weighted average
        weights = {
            'confidence': 0.25,
            'agreement': 0.25,
            'volatility': 0.25,
            'data_quality': 0.15,
            'spread_stability': 0.10,
        }
        risk = (
            confidence_risk * weights['confidence']
            + agreement_risk * weights['agreement']
            + vol_risk * weights['volatility']
            + data_risk * weights['data_quality']
            + spread_risk * weights['spread_stability']
        )
        return min(max(risk, 0.0), 1.0)

    def scan_all_pairs(
        self,
        pairs: List[str],
        all_exchange_data: Dict[str, Dict[str, np.ndarray]],
    ) -> List[CrossExchangeSignal]:
        """Scan all pairs across all exchanges and return sorted opportunities.

        Args:
            pairs: List of trading pairs
            all_exchange_data: {pair: {exchange: OHLCV array}}

        Returns:
            List of CrossExchangeSignal sorted by reward_risk_ratio descending
        """
        results = []
        for pair in pairs:
            exchange_data = all_exchange_data.get(pair, {})
            if len(exchange_data) < 2:
                continue
            signal = self.score_pair(pair, exchange_data)
            if signal is not None:
                results.append(signal)

        results.sort(key=lambda s: s.reward_risk_ratio, reverse=True)
        return results


def create_ensemble_from_config(config_path: str = "config/trading_config.json") -> StrategyEnsemble:
    """Create a StrategyEnsemble from the trading config file."""
    config = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)

    return StrategyEnsemble(config=config)
