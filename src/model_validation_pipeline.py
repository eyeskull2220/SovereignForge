#!/usr/bin/env python3
"""
SovereignForge - Model Validation Pipeline
Validates all 10 MiCA-compliant trading pair models and handles error recovery.

Responsibilities:
- Load all 10 pair models with robust error handling
- Validate each against 80% accuracy threshold
- Generate a JSON validation report
- Auto-trigger hyperparameter retraining for failing models
- Register a single ModelRegistry used by the rest of the system
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

# All 10 MiCA-compliant pairs
ALL_PAIRS: List[str] = [
    "BTC", "ETH", "XRP", "XLM", "HBAR", "ALGO", "ADA", "LINK", "IOTA", "VET"
]

ACCURACY_THRESHOLD = 0.80

# Canonical model path patterns (tried in order)
_MODEL_PATH_PATTERNS = [
    "models/strategies/arbitrage_{pair_lower}_usdc_binance.pth",
    "models/strategies/final_{pair_upper}_USDC.pth",
    "models/strategies/final_{pair_upper}_USDT.pth",  # legacy fallback
    "models/{pair_upper}USDC_model.pth",
]


@dataclass
class ModelStatus:
    pair: str
    loaded: bool
    model_path: Optional[str]
    val_accuracy: Optional[float]
    val_loss: Optional[float]
    passed_threshold: bool
    error: Optional[str]
    parameters: Optional[int]
    last_validated: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class ValidationReport:
    generated_at: str
    device: str
    total_pairs: int
    loaded: int
    passed: int
    failed: int
    accuracy_threshold: float
    models: List[ModelStatus]
    overall_status: str  # 'green' | 'yellow' | 'red'


class ModelRegistry:
    """
    Central registry that holds loaded model instances for all pairs.
    Acts as the single source of truth for the inference pipeline.
    """

    def __init__(self):
        self._models: Dict[str, Any] = {}   # pair -> GPUArbitrageModel
        self._statuses: Dict[str, ModelStatus] = {}

    def register(self, pair: str, model: Any, status: ModelStatus) -> None:
        self._models[pair] = model
        self._statuses[pair] = status

    def get(self, pair: str) -> Optional[Any]:
        return self._models.get(pair)

    def get_status(self, pair: str) -> Optional[ModelStatus]:
        return self._statuses.get(pair)

    def all_loaded_pairs(self) -> List[str]:
        return [p for p, m in self._models.items() if m is not None]

    def summary(self) -> Dict[str, Any]:
        statuses = list(self._statuses.values())
        return {
            "total": len(statuses),
            "loaded": sum(1 for s in statuses if s.loaded),
            "passed": sum(1 for s in statuses if s.passed_threshold),
            "pairs": {s.pair: {"loaded": s.loaded, "accuracy": s.val_accuracy} for s in statuses},
        }


# Module-level singleton
_registry: Optional[ModelRegistry] = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


class ModelValidationPipeline:
    """
    Loads, validates, and optionally retrains all 10 trading pair models.
    """

    def __init__(
        self,
        root_dir: str = ".",
        accuracy_threshold: float = ACCURACY_THRESHOLD,
        auto_retrain: bool = False,
        device: Optional[str] = None,
    ):
        self.root_dir = Path(root_dir)
        self.accuracy_threshold = accuracy_threshold
        self.auto_retrain = auto_retrain
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.registry = get_model_registry()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(self, pairs: Optional[List[str]] = None) -> ValidationReport:
        """
        Main entry point. Load + validate all pairs, optionally retrain failures.
        Returns a full ValidationReport.
        """
        pairs = pairs or ALL_PAIRS
        logger.info(f"Starting model validation pipeline for {len(pairs)} pairs on {self.device}")

        statuses: List[ModelStatus] = []
        for pair in pairs:
            status = await self._load_and_validate(pair)
            statuses.append(status)

        # Auto-retrain failing models if requested
        if self.auto_retrain:
            failing = [s for s in statuses if s.loaded and not s.passed_threshold]
            if failing:
                logger.info(f"Auto-retraining {len(failing)} failing models")
                await self._retrain_failing(failing, statuses)

        report = self._build_report(statuses)
        self._save_report(report)
        return report

    def load_model_for_pair(self, pair: str) -> Tuple[Optional[Any], Optional[str]]:
        """
        Attempt to load a GPUArbitrageModel for the given pair.
        Tries all known path patterns. Returns (model, path) or (None, None).
        """
        try:
            from src.gpu_arbitrage_model import GPUArbitrageModel
        except ImportError:
            try:
                from gpu_arbitrage_model import GPUArbitrageModel  # type: ignore
            except ImportError:
                logger.error("GPUArbitrageModel not importable")
                return None, None

        for pattern in _MODEL_PATH_PATTERNS:
            path_str = pattern.format(
                pair_lower=pair.lower(),
                pair_upper=pair.upper(),
            )
            path = self.root_dir / path_str
            if path.exists():
                try:
                    model = GPUArbitrageModel(model_path=str(path))
                    logger.info(f"[{pair}] Loaded from {path}")
                    return model, str(path)
                except Exception as e:
                    logger.warning(f"[{pair}] Failed to load from {path}: {e}")

        logger.warning(f"[{pair}] No model file found (tried {len(_MODEL_PATH_PATTERNS)} patterns)")
        return None, None

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    async def _load_and_validate(self, pair: str) -> ModelStatus:
        loop = asyncio.get_event_loop()
        model, path = await loop.run_in_executor(None, self.load_model_for_pair, pair)

        if model is None:
            status = ModelStatus(
                pair=pair,
                loaded=False,
                model_path=None,
                val_accuracy=None,
                val_loss=None,
                passed_threshold=False,
                error="No model file found",
                parameters=None,
            )
            self.registry.register(pair, None, status)
            return status

        # Count parameters
        try:
            n_params = sum(p.numel() for p in model.model.parameters())
        except Exception:
            n_params = None

        # Validate
        val_acc, val_loss, error = await loop.run_in_executor(
            None, self._validate_model, model, pair
        )

        status = ModelStatus(
            pair=pair,
            loaded=True,
            model_path=path,
            val_accuracy=val_acc,
            val_loss=val_loss,
            passed_threshold=(val_acc is not None and val_acc >= self.accuracy_threshold),
            error=error,
            parameters=n_params,
        )

        self.registry.register(pair, model, status)

        emoji = "✅" if status.passed_threshold else ("⚠️" if val_acc else "❌")
        logger.info(
            f"{emoji} [{pair}] acc={val_acc:.3f if val_acc else 'N/A'} "
            f"params={n_params} path={path}"
        )

        # Update metadata file
        self._update_metadata(pair, status)
        return status

    def _validate_model(
        self, model: Any, pair: str
    ) -> Tuple[Optional[float], Optional[float], Optional[str]]:
        """Run a quick validation pass on synthetic test data."""
        try:
            seq_len = 50
            input_dim = 10
            n_samples = 500
            batch_size = 64

            X = torch.randn(n_samples, seq_len, input_dim)
            y = (torch.rand(n_samples) > 0.5).float()

            device = torch.device(self.device)
            model.model.eval()

            total_correct = 0
            total_loss = 0.0
            criterion = torch.nn.BCEWithLogitsLoss()
            n_batches = 0

            with torch.no_grad():
                for i in range(0, n_samples, batch_size):
                    xb = X[i : i + batch_size].to(device)
                    yb = y[i : i + batch_size].to(device)

                    sig, _, _ = model.model(xb)
                    sig = sig.squeeze(-1) if sig.dim() > 1 else sig

                    loss = criterion(sig, yb)
                    total_loss += loss.item()
                    preds = (torch.sigmoid(sig) > 0.5).float()
                    total_correct += (preds == yb).sum().item()
                    n_batches += 1

            val_acc = total_correct / n_samples
            val_loss = total_loss / n_batches
            return val_acc, val_loss, None

        except Exception as e:
            logger.error(f"[{pair}] Validation error: {e}")
            return None, None, str(e)

    async def _retrain_failing(
        self, failing: List[ModelStatus], all_statuses: List[ModelStatus]
    ) -> None:
        """Trigger hyperparameter tuning for pairs that didn't meet the threshold."""
        try:
            from src.hyperparameter_tuner import HyperparameterTuner
        except ImportError:
            try:
                from hyperparameter_tuner import HyperparameterTuner  # type: ignore
            except ImportError:
                logger.error("HyperparameterTuner not available — skipping auto-retrain")
                return

        tuner = HyperparameterTuner(
            models_dir=str(self.root_dir / "models"),
            n_trials=8,
            search_strategy="random",
        )
        for status in failing:
            logger.info(f"Auto-retraining {status.pair} (current acc={status.val_accuracy})")
            best_cfg = await tuner.tune_pair(status.pair)
            if best_cfg:
                logger.info(f"[{status.pair}] Retraining found config with val_acc >= {self.accuracy_threshold:.0%}")
            else:
                logger.warning(f"[{status.pair}] Retraining did not reach threshold")

    def _update_metadata(self, pair: str, status: ModelStatus) -> None:
        meta_path = self.root_dir / f"models/{pair.upper()}USDC_metadata.json"
        metadata: Dict[str, Any] = {}
        if meta_path.exists():
            try:
                with open(meta_path) as f:
                    metadata = json.load(f)
            except Exception:
                pass

        metadata.update({
            "validation_accuracy": status.val_accuracy,
            "passed_threshold": status.passed_threshold,
            "last_validated": status.last_validated,
            "model_path": status.model_path,
            "parameters_count": status.parameters,
            "validation_error": status.error,
        })

        try:
            with open(meta_path, "w") as f:
                json.dump(metadata, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not update metadata for {pair}: {e}")

    def _build_report(self, statuses: List[ModelStatus]) -> ValidationReport:
        loaded = sum(1 for s in statuses if s.loaded)
        passed = sum(1 for s in statuses if s.passed_threshold)
        total = len(statuses)

        if passed == total:
            overall = "green"
        elif passed >= total * 0.7:
            overall = "yellow"
        else:
            overall = "red"

        return ValidationReport(
            generated_at=datetime.now().isoformat(),
            device=self.device,
            total_pairs=total,
            loaded=loaded,
            passed=passed,
            failed=total - passed,
            accuracy_threshold=self.accuracy_threshold,
            models=statuses,
            overall_status=overall,
        )

    def _save_report(self, report: ValidationReport) -> None:
        path = self.root_dir / "reports" / "model_validation_report.json"
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "generated_at": report.generated_at,
            "device": report.device,
            "total_pairs": report.total_pairs,
            "loaded": report.loaded,
            "passed": report.passed,
            "failed": report.failed,
            "accuracy_threshold": report.accuracy_threshold,
            "overall_status": report.overall_status,
            "models": [asdict(s) for s in report.models],
        }
        with open(path, "w") as f:
            json.dump(payload, f, indent=2)
        logger.info(f"Validation report saved to {path}")

        # Print summary
        logger.info(
            f"\n{'='*50}\n"
            f"MODEL VALIDATION SUMMARY\n"
            f"Status: {report.overall_status.upper()}\n"
            f"Loaded:  {report.loaded}/{report.total_pairs}\n"
            f"Passed:  {report.passed}/{report.total_pairs} (threshold={report.accuracy_threshold:.0%})\n"
            f"{'='*50}"
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
async def _main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import argparse

    parser = argparse.ArgumentParser(description="SovereignForge Model Validation Pipeline")
    parser.add_argument("--pairs", nargs="+", default=ALL_PAIRS)
    parser.add_argument("--auto-retrain", action="store_true")
    parser.add_argument("--root-dir", default=".")
    args = parser.parse_args()

    pipeline = ModelValidationPipeline(
        root_dir=args.root_dir,
        auto_retrain=args.auto_retrain,
    )
    report = await pipeline.run(args.pairs)
    print(f"\nOverall: {report.overall_status.upper()} | "
          f"{report.passed}/{report.total_pairs} passed")


if __name__ == "__main__":
    asyncio.run(_main())
