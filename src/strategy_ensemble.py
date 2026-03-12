#!/usr/bin/env python3
"""
SovereignForge - Strategy Ensemble (Collective Brain)
Combines signals from all strategy models into unified trading decisions.
Uses confidence-weighted aggregation across arbitrage, fibonacci, grid, and DCA.
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

        # Model storage: strategy → {pair: model}
        self.models: Dict[StrategyType, Dict[str, nn.Module]] = {
            st: {} for st in StrategyType
        }

        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

        logger.info(
            f"StrategyEnsemble initialized: "
            f"weights={{{', '.join(f'{s.value}: {w:.2f}' for s, w in self.strategy_weights.items())}}}"
        )

    def load_all_models(self, pairs: List[str]) -> Dict[str, bool]:
        """Load models for all enabled strategies and pairs.

        Returns: {strategy_pair: loaded_successfully}
        """
        results = {}

        for strategy in StrategyType:
            if not self.strategy_enabled.get(strategy, True):
                logger.info(f"Skipping disabled strategy: {strategy.value}")
                continue

            model_factory = STRATEGY_MODELS[strategy]

            for pair in pairs:
                key = f"{strategy.value}:{pair}"
                pair_slug = pair.replace('/', '_').lower()
                model_path = self.models_dir / f"{strategy.value}_{pair_slug}.pth"

                if not model_path.exists():
                    # Also try legacy naming for arbitrage
                    if strategy == StrategyType.ARBITRAGE:
                        alt_path = self.models_dir / f"arbitrage_{pair_slug}_binance.pth"
                        if alt_path.exists():
                            model_path = alt_path
                        else:
                            results[key] = False
                            continue
                    else:
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

                    self.models[strategy][pair] = model
                    del checkpoint  # Free checkpoint memory
                    gc.collect()
                    results[key] = True
                    logger.info(f"Loaded {strategy.value} model for {pair}")

                except Exception as e:
                    logger.error(f"Failed to load {strategy.value} model for {pair}: {e}")
                    results[key] = False

        loaded_count = sum(1 for v in results.values() if v)
        total = len(results)
        logger.info(f"Loaded {loaded_count}/{total} strategy models")
        return results

    def predict(self, pair: str, market_data: np.ndarray) -> EnsembleSignal:
        """Run all strategy models and combine signals weighted by confidence.

        Args:
            pair: Trading pair (e.g. 'XRP/USDC')
            market_data: OHLCV array [N, 6] (timestamp, open, high, low, close, volume)

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

                model = self.models.get(strategy, {}).get(pair)
                if model is None:
                    continue

                try:
                    assert not model.training, f"{strategy.value} model not in eval mode"
                    output = model(input_tensor)  # [1, 3]: signal, confidence, magnitude

                    raw_signal = output[0, 0].item()  # [-1, 1]
                    model_confidence = float(torch.sigmoid(output[0, 1]).item())

                    strategy_signals[strategy.value] = raw_signal
                    strategy_confidences[strategy.value] = model_confidence

                    # Effective weight = config_weight * model_confidence
                    effective_weight = self.strategy_weights[strategy] * model_confidence
                    weighted_signal += raw_signal * effective_weight
                    total_effective_weight += effective_weight

                except Exception as e:
                    logger.error(f"Prediction failed for {strategy.value}/{pair}: {e}")

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


def create_ensemble_from_config(config_path: str = "config/trading_config.json") -> StrategyEnsemble:
    """Create a StrategyEnsemble from the trading config file."""
    config = {}
    config_file = Path(config_path)
    if config_file.exists():
        with open(config_file) as f:
            config = json.load(f)

    return StrategyEnsemble(config=config)
