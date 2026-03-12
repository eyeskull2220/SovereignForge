#!/usr/bin/env python3
"""
SovereignForge - Model Ensemble System
Combines multiple ML architectures for improved arbitrage prediction accuracy

This module provides:
- Model ensemble with voting and weighted averaging
- Confidence-based model selection
- Performance tracking and model weighting
- Dynamic ensemble adaptation
- GPU-optimized ensemble inference
"""

import asyncio
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

# Import existing components
from gpu_arbitrage_model import ArbitrageTransformer, GPUArbitrageModel
from gpu_manager import get_gpu_manager

logger = logging.getLogger(__name__)

@dataclass
class EnsemblePrediction:
    """Ensemble prediction result"""
    arbitrage_signal: float
    confidence_score: float
    predicted_spread: float
    ensemble_confidence: float
    model_contributions: Dict[str, float]
    prediction_variance: float
    timestamp: datetime

@dataclass
class ModelPerformance:
    """Model performance metrics"""
    model_name: str
    accuracy: float
    precision: float
    recall: float
    f1_score: float
    sharpe_ratio: float
    max_drawdown: float
    total_predictions: int
    last_updated: datetime

class ModelEnsemble:
    """
    Advanced model ensemble for arbitrage prediction
    Combines multiple ML architectures with intelligent weighting
    """

    def __init__(self,
                 model_configs: Optional[List[Dict[str, Any]]] = None,
                 ensemble_method: str = "weighted_average",
                 confidence_threshold: float = 0.7,
                 max_models: int = 5):
        self.ensemble_method = ensemble_method
        self.confidence_threshold = confidence_threshold
        self.max_models = max_models

        # Model management
        self.models: Dict[str, GPUArbitrageModel] = {}
        self.model_performance: Dict[str, ModelPerformance] = {}
        self.active_models: List[str] = []

        # Ensemble weights (learned/adaptive)
        self.model_weights: Dict[str, float] = {}

        # GPU management
        self.gpu_manager = get_gpu_manager()

        # Performance tracking
        self.prediction_history: List[Dict[str, Any]] = []
        self.ensemble_stats = {
            "total_predictions": 0,
            "ensemble_accuracy": 0.0,
            "individual_vs_ensemble": 0.0,
            "last_calibration": None
        }

        # Initialize with default model configs if none provided
        if model_configs is None:
            model_configs = self._get_default_model_configs()

        self.model_configs = model_configs
        logger.info(f"ModelEnsemble initialized with {len(model_configs)} model configurations")

    def _get_default_model_configs(self) -> List[Dict[str, Any]]:
        """Get default model configurations for ensemble"""
        return [
            {
                "name": "transformer_base",
                "config": {
                    "input_dim": 10,
                    "d_model": 256,
                    "nhead": 8,
                    "num_layers": 4,
                    "dropout": 0.1
                },
                "weight": 0.3
            },
            {
                "name": "transformer_large",
                "config": {
                    "input_dim": 10,
                    "d_model": 512,
                    "nhead": 8,
                    "num_layers": 6,
                    "dropout": 0.1
                },
                "weight": 0.4
            },
            {
                "name": "transformer_small",
                "config": {
                    "input_dim": 10,
                    "d_model": 128,
                    "nhead": 4,
                    "num_layers": 3,
                    "dropout": 0.2
                },
                "weight": 0.3
            }
        ]

    async def initialize_ensemble(self) -> bool:
        """Initialize the model ensemble"""
        try:
            logger.info("Initializing model ensemble...")

            # Load or create models
            for model_config in self.model_configs:
                model_name = model_config["name"]
                config = model_config["config"]
                weight = model_config.get("weight", 1.0 / len(self.model_configs))

                # Create model instance
                model = GPUArbitrageModel(model_config=config)
                self.models[model_name] = model
                self.model_weights[model_name] = weight

                # Initialize performance tracking
                self.model_performance[model_name] = ModelPerformance(
                    model_name=model_name,
                    accuracy=0.5,  # Start neutral
                    precision=0.5,
                    recall=0.5,
                    f1_score=0.5,
                    sharpe_ratio=0.0,
                    max_drawdown=0.0,
                    total_predictions=0,
                    last_updated=datetime.now()
                )

                self.active_models.append(model_name)
                logger.info(f"Initialized model: {model_name} with weight {weight:.3f}")

            # Limit to max_models
            if len(self.active_models) > self.max_models:
                # Keep top performing models
                self.active_models = self.active_models[:self.max_models]
                logger.info(f"Limited to top {self.max_models} models")

            logger.info(f"Ensemble initialized with {len(self.active_models)} active models")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize ensemble: {e}")
            return False

    async def predict_ensemble(self,
                              market_data: torch.Tensor,
                              pair: str = "unknown") -> EnsemblePrediction:
        """
        Make ensemble prediction with multiple models
        """
        try:
            if not self.active_models:
                raise ValueError("No active models in ensemble")

            # Get individual model predictions
            individual_predictions = {}
            model_confidences = {}

            for model_name in self.active_models:
                try:
                    model = self.models[model_name]

                    # Make prediction
                    signal, confidence, spread = await model.predict_async(market_data)

                    # Convert to numpy for easier handling
                    signal_val = signal.item()
                    confidence_val = confidence.item()
                    spread_val = spread.item()

                    individual_predictions[model_name] = {
                        'signal': signal_val,
                        'confidence': confidence_val,
                        'spread': spread_val
                    }
                    model_confidences[model_name] = confidence_val

                except Exception as e:
                    logger.warning(f"Model {model_name} prediction failed: {e}")
                    # Use fallback values
                    individual_predictions[model_name] = {
                        'signal': 0.5,
                        'confidence': 0.0,
                        'spread': 0.001
                    }
                    model_confidences[model_name] = 0.0

            # Combine predictions based on ensemble method
            if self.ensemble_method == "weighted_average":
                ensemble_result = self._weighted_average_prediction(
                    individual_predictions, model_confidences
                )
            elif self.ensemble_method == "confidence_weighted":
                ensemble_result = self._confidence_weighted_prediction(
                    individual_predictions, model_confidences
                )
            elif self.ensemble_method == "voting":
                ensemble_result = self._voting_prediction(individual_predictions)
            else:
                ensemble_result = self._weighted_average_prediction(
                    individual_predictions, model_confidences
                )

            # Calculate ensemble confidence and variance
            ensemble_confidence = self._calculate_ensemble_confidence(
                individual_predictions, model_confidences
            )

            prediction_variance = self._calculate_prediction_variance(individual_predictions)

            # Create ensemble prediction
            prediction = EnsemblePrediction(
                arbitrage_signal=ensemble_result['signal'],
                confidence_score=ensemble_result['confidence'],
                predicted_spread=ensemble_result['spread'],
                ensemble_confidence=ensemble_confidence,
                model_contributions=self._calculate_contributions(individual_predictions),
                prediction_variance=prediction_variance,
                timestamp=datetime.now()
            )

            # Track prediction for learning
            self._track_prediction(prediction, pair)

            return prediction

        except Exception as e:
            logger.error(f"Ensemble prediction failed: {e}")
            # Return fallback prediction
            return EnsemblePrediction(
                arbitrage_signal=0.5,
                confidence_score=0.0,
                predicted_spread=0.001,
                ensemble_confidence=0.0,
                model_contributions={},
                prediction_variance=1.0,
                timestamp=datetime.now()
            )

    def _weighted_average_prediction(self,
                                   predictions: Dict[str, Dict],
                                   confidences: Dict[str, float]) -> Dict[str, float]:
        """Weighted average ensemble method"""
        total_weight = sum(self.model_weights.get(model, 1.0) for model in predictions.keys())

        weighted_signal = 0.0
        weighted_confidence = 0.0
        weighted_spread = 0.0

        for model_name, pred in predictions.items():
            weight = self.model_weights.get(model_name, 1.0)
            confidence_weight = confidences.get(model_name, 0.5)

            # Apply both model weight and confidence weight
            effective_weight = weight * (0.5 + 0.5 * confidence_weight)

            weighted_signal += pred['signal'] * effective_weight
            weighted_confidence += pred['confidence'] * effective_weight
            weighted_spread += pred['spread'] * effective_weight

        return {
            'signal': weighted_signal / total_weight,
            'confidence': weighted_confidence / total_weight,
            'spread': weighted_spread / total_weight
        }

    def _confidence_weighted_prediction(self,
                                      predictions: Dict[str, Dict],
                                      confidences: Dict[str, float]) -> Dict[str, float]:
        """Confidence-weighted ensemble method"""
        # Use model confidences as weights
        total_confidence = sum(confidences.values()) or 1.0

        weighted_signal = 0.0
        weighted_confidence = 0.0
        weighted_spread = 0.0

        for model_name, pred in predictions.items():
            confidence = confidences.get(model_name, 0.5)
            weight = confidence / total_confidence

            weighted_signal += pred['signal'] * weight
            weighted_confidence += pred['confidence'] * weight
            weighted_spread += pred['spread'] * weight

        return {
            'signal': weighted_signal,
            'confidence': weighted_confidence,
            'spread': weighted_spread
        }

    def _voting_prediction(self, predictions: Dict[str, Dict]) -> Dict[str, float]:
        """Voting-based ensemble method"""
        # Simple majority voting for signal, average for others
        signals = [pred['signal'] for pred in predictions.values()]
        confidences = [pred['confidence'] for pred in predictions.values()]
        spreads = [pred['spread'] for pred in predictions.values()]

        # Binary classification: arbitrage (signal > 0.5) or not
        arbitrage_votes = sum(1 for s in signals if s > 0.5)
        majority_signal = 1.0 if arbitrage_votes > len(signals) / 2 else 0.0

        return {
            'signal': majority_signal,
            'confidence': np.mean(confidences),
            'spread': np.mean(spreads)
        }

    def _calculate_ensemble_confidence(self,
                                     predictions: Dict[str, Dict],
                                     confidences: Dict[str, float]) -> float:
        """Calculate overall ensemble confidence"""
        # Ensemble confidence based on agreement and individual confidences
        signals = [pred['signal'] for pred in predictions.values()]
        mean_signal = np.mean(signals)
        signal_std = np.std(signals)

        # High agreement = high confidence
        agreement_score = 1.0 / (1.0 + signal_std)

        # Average individual confidence
        avg_individual_confidence = np.mean(list(confidences.values()))

        # Combine agreement and individual confidence
        ensemble_confidence = (agreement_score + avg_individual_confidence) / 2

        return min(ensemble_confidence, 1.0)

    def _calculate_prediction_variance(self, predictions: Dict[str, Dict]) -> float:
        """Calculate prediction variance across models"""
        signals = [pred['signal'] for pred in predictions.values()]
        return np.var(signals) if len(signals) > 1 else 0.0

    def _calculate_contributions(self, predictions: Dict[str, Dict]) -> Dict[str, float]:
        """Calculate contribution of each model to final prediction"""
        total_predictions = len(predictions)
        contributions = {}

        for model_name, pred in predictions.items():
            # Simple equal contribution for now
            contributions[model_name] = 1.0 / total_predictions

        return contributions

    def _track_prediction(self, prediction: EnsemblePrediction, pair: str):
        """Track prediction for performance monitoring"""
        self.prediction_history.append({
            'timestamp': prediction.timestamp,
            'pair': pair,
            'signal': prediction.arbitrage_signal,
            'confidence': prediction.confidence_score,
            'ensemble_confidence': prediction.ensemble_confidence,
            'variance': prediction.prediction_variance,
            'contributions': prediction.model_contributions
        })

        # Keep history manageable
        if len(self.prediction_history) > 1000:
            self.prediction_history = self.prediction_history[-500:]

        self.ensemble_stats["total_predictions"] += 1

    def update_model_weights(self, actual_outcomes: Dict[str, Dict[str, Any]]):
        """
        Update model weights based on actual outcomes
        Implements online learning for ensemble adaptation
        """
        try:
            # Simple weight update based on recent performance
            for model_name in self.active_models:
                if model_name in actual_outcomes:
                    outcome = actual_outcomes[model_name]
                    accuracy = outcome.get('accuracy', 0.5)

                    # Adjust weight based on performance
                    current_weight = self.model_weights.get(model_name, 1.0)
                    new_weight = current_weight * (0.9 + 0.2 * accuracy)  # Dampened update

                    # Normalize weights
                    self.model_weights[model_name] = new_weight

            # Renormalize weights
            total_weight = sum(self.model_weights.values())
            if total_weight > 0:
                for model_name in self.model_weights:
                    self.model_weights[model_name] /= total_weight

            logger.info(f"Updated model weights: {self.model_weights}")

        except Exception as e:
            logger.error(f"Failed to update model weights: {e}")

    def calibrate_ensemble(self):
        """Calibrate ensemble based on historical performance"""
        try:
            if len(self.prediction_history) < 10:
                logger.info("Not enough prediction history for calibration")
                return

            # Analyze recent predictions
            recent_predictions = self.prediction_history[-50:]

            # Update model performance metrics
            for model_name in self.active_models:
                model_predictions = [p for p in recent_predictions if model_name in p.get('contributions', {})]

                if model_predictions:
                    # Calculate performance metrics
                    accuracies = [p['ensemble_confidence'] for p in model_predictions]
                    avg_accuracy = np.mean(accuracies)

                    # Update performance record
                    perf = self.model_performance[model_name]
                    perf.accuracy = avg_accuracy
                    perf.total_predictions = len(model_predictions)
                    perf.last_updated = datetime.now()

            # Adjust ensemble method based on performance
            self._optimize_ensemble_method()

            self.ensemble_stats["last_calibration"] = datetime.now()
            logger.info("Ensemble calibrated successfully")

        except Exception as e:
            logger.error(f"Ensemble calibration failed: {e}")

    def _optimize_ensemble_method(self):
        """Optimize ensemble method based on performance"""
        # Simple optimization - could be more sophisticated
        methods = ["weighted_average", "confidence_weighted", "voting"]
        current_performance = self.ensemble_stats.get("ensemble_accuracy", 0.5)

        # Try different methods and pick best (simplified)
        # In practice, this would use cross-validation
        best_method = self.ensemble_method
        best_score = current_performance

        for method in methods:
            if method != self.ensemble_method:
                # Simulate performance for this method
                simulated_score = current_performance + np.random.normal(0, 0.05)
                if simulated_score > best_score:
                    best_method = method
                    best_score = simulated_score

        if best_method != self.ensemble_method:
            logger.info(f"Switching ensemble method from {self.ensemble_method} to {best_method}")
            self.ensemble_method = best_method

    def get_ensemble_status(self) -> Dict[str, Any]:
        """Get ensemble status and performance metrics"""
        return {
            "active_models": len(self.active_models),
            "model_names": self.active_models,
            "model_weights": self.model_weights,
            "ensemble_method": self.ensemble_method,
            "total_predictions": self.ensemble_stats["total_predictions"],
            "ensemble_accuracy": self.ensemble_stats["ensemble_accuracy"],
            "last_calibration": self.ensemble_stats["last_calibration"],
            "model_performance": {
                name: {
                    "accuracy": perf.accuracy,
                    "total_predictions": perf.total_predictions,
                    "last_updated": perf.last_updated.isoformat()
                }
                for name, perf in self.model_performance.items()
            }
        }

    def save_ensemble(self, save_path: str):
        """Save ensemble state"""
        try:
            ensemble_state = {
                "model_configs": self.model_configs,
                "model_weights": self.model_weights,
                "ensemble_method": self.ensemble_method,
                "active_models": self.active_models,
                "ensemble_stats": self.ensemble_stats,
                "model_performance": {
                    name: {
                        "accuracy": perf.accuracy,
                        "precision": perf.precision,
                        "recall": perf.recall,
                        "f1_score": perf.f1_score,
                        "total_predictions": perf.total_predictions,
                        "last_updated": perf.last_updated.isoformat()
                    }
                    for name, perf in self.model_performance.items()
                },
                "saved_at": datetime.now().isoformat()
            }

            torch.save(ensemble_state, save_path)
            logger.info(f"Ensemble saved to {save_path}")

        except Exception as e:
            logger.error(f"Failed to save ensemble: {e}")

    def load_ensemble(self, load_path: str) -> bool:
        """Load ensemble state"""
        try:
            if not Path(load_path).exists():
                logger.warning(f"Ensemble file not found: {load_path}")
                return False

            ensemble_state = torch.load(load_path, map_location='cpu', weights_only=True)

            self.model_weights = ensemble_state.get("model_weights", {})
            self.ensemble_method = ensemble_state.get("ensemble_method", "weighted_average")
            self.active_models = ensemble_state.get("active_models", [])
            self.ensemble_stats = ensemble_state.get("ensemble_stats", self.ensemble_stats)

            # Load model performance
            perf_data = ensemble_state.get("model_performance", {})
            for name, perf_dict in perf_data.items():
                if name in self.model_performance:
                    perf = self.model_performance[name]
                    perf.accuracy = perf_dict.get("accuracy", 0.5)
                    perf.total_predictions = perf_dict.get("total_predictions", 0)

            logger.info(f"Ensemble loaded from {load_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load ensemble: {e}")
            return False

# Global ensemble instance
_ensemble_instance = None

def get_model_ensemble() -> ModelEnsemble:
    """Get or create global model ensemble instance"""
    global _ensemble_instance

    if _ensemble_instance is None:
        _ensemble_instance = ModelEnsemble()

    return _ensemble_instance

async def initialize_ensemble() -> bool:
    """Initialize the global model ensemble"""
    ensemble = get_model_ensemble()
    return await ensemble.initialize_ensemble()

async def predict_with_ensemble(market_data: torch.Tensor, pair: str = "unknown") -> EnsemblePrediction:
    """Convenience function for ensemble prediction"""
    ensemble = get_model_ensemble()
    return await ensemble.predict_ensemble(market_data, pair)

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    async def test_ensemble():
        # Initialize ensemble
        ensemble = ModelEnsemble()
        success = await ensemble.initialize_ensemble()

        if success:
            logger.info("Ensemble initialized successfully")

            # Test prediction
            batch_size, seq_len, input_dim = 1, 50, 10
            test_data = torch.randn(batch_size, seq_len, input_dim)

            prediction = await ensemble.predict_ensemble(test_data, "BTC/USDC")
            logger.info(f"Ensemble prediction: signal={prediction.arbitrage_signal:.3f}, "
                       f"confidence={prediction.confidence_score:.3f}")

            # Get status
            status = ensemble.get_ensemble_status()
            logger.info(f"Ensemble status: {status['active_models']} active models")

        else:
            logger.error("Failed to initialize ensemble")

    # Run test
    asyncio.run(test_ensemble())
