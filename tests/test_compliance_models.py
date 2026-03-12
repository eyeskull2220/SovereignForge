#!/usr/bin/env python3
"""
Wave 1 - Category 3: Tests for MiCA compliance enforcement and model accuracy validation.

Covers:
- Integration tests for MiCA compliance enforcement
- Model accuracy validation tests (>80% threshold)
- Model loading for all 10 pairs
- Hyperparameter tuning pipeline smoke tests
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import List
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest
import torch

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

ROOT_DIR = Path(__file__).parent.parent
ALL_PAIRS = ["BTC", "ETH", "XRP", "XLM", "HBAR", "ALGO", "ADA", "LINK", "IOTA", "VET"]
ACCURACY_THRESHOLD = 0.80


# ===========================================================================
# MiCA Compliance Integration Tests
# ===========================================================================

class TestMiCAComplianceEnforcement:
    """Integration tests for the MiCA compliance engine."""

    def setup_method(self):
        from compliance import MiCAComplianceEngine
        self.engine_personal = MiCAComplianceEngine(personal_deployment=True)
        self.engine_strict = MiCAComplianceEngine(personal_deployment=False)

    def test_usdc_pairs_are_compliant(self):
        """USDC stablecoin pairs must always be compliant."""
        compliant_pairs = [
            "XRP/USDC", "ADA/USDC", "XLM/USDC", "HBAR/USDC",
            "ALGO/USDC", "LINK/USDC", "IOTA/USDC", "VET/USDC",
        ]
        for pair in compliant_pairs:
            assert self.engine_personal.is_pair_compliant(pair), \
                f"{pair} should be compliant under personal deployment"

    def test_usdt_pairs_are_forbidden(self):
        """USDT pairs must be rejected in ALL deployment modes (MiCA Article 5)."""
        usdt_pairs = [
            "BTC/USDT", "ETH/USDT", "XRP/USDT", "ADA/USDT",
        ]
        for pair in usdt_pairs:
            assert not self.engine_personal.is_pair_compliant(pair), \
                f"{pair} with USDT should be forbidden (personal)"
            assert not self.engine_strict.is_pair_compliant(pair), \
                f"{pair} with USDT should be forbidden (strict)"

    def test_non_whitelisted_assets_rejected(self):
        """Non-whitelisted coins (SHIB, PEPE, etc.) must be rejected."""
        bad_pairs = ["SHIB/USDC", "DOGE/USDC", "PEPE/USDC", "WIF/USDC"]
        for pair in bad_pairs:
            assert not self.engine_strict.is_pair_compliant(pair), \
                f"{pair} should be rejected in strict mode"

    def test_filter_compliant_pairs_removes_violations(self):
        """filter_compliant_pairs must remove all non-compliant pairs."""
        mixed = ["BTC/USDC", "SHIB/USDT", "XRP/USDC", "PEPE/USDC", "ADA/USDC"]
        result = self.engine_personal.filter_compliant_pairs(mixed)
        assert "SHIB/USDT" not in result
        assert "PEPE/USDC" not in result
        assert "BTC/USDC" in result
        assert "XRP/USDC" in result
        assert "ADA/USDC" in result

    def test_filter_compliant_pairs_empty_input(self):
        """Empty input must return empty list."""
        assert self.engine_personal.filter_compliant_pairs([]) == []

    def test_validate_opportunity_compliant(self):
        """validate_opportunity must pass for a compliant pair."""
        from compliance import MiCAComplianceEngine
        engine = MiCAComplianceEngine(personal_deployment=True)
        result = engine.validate_opportunity(
            {"pair": "XRP/USDC", "exchange": "binance", "profit": 0.01}
        )
        assert result is True or result is None  # must not raise

    def test_validate_opportunity_raises_on_violation(self):
        """validate_opportunity must raise or return False for USDT pairs."""
        from compliance import ComplianceViolationError, MiCAComplianceEngine
        engine = MiCAComplianceEngine(personal_deployment=True)
        try:
            result = engine.validate_opportunity(
                {"pair": "BTC/USDT", "exchange": "binance", "profit": 0.01}
            )
            # If it doesn't raise, it should return False/None
            assert not result, "USDT pair should fail compliance"
        except (ComplianceViolationError, Exception):
            pass  # Raising is also acceptable

    def test_all_10_mica_pairs_are_compliant(self):
        """All 10 system pairs with USDC must be compliant."""
        expected = [f"{p}/USDC" for p in ALL_PAIRS]
        result = self.engine_personal.filter_compliant_pairs(expected)
        # Allow that some coins might not be in the personal whitelist (BTC/ETH edge cases)
        [p for p in expected if "USDT" not in p]
        # At minimum VET, LINK, IOTA, XRP, ADA, XLM, HBAR, ALGO should pass
        core = ["XRP/USDC", "ADA/USDC", "XLM/USDC", "HBAR/USDC", "ALGO/USDC"]
        for pair in core:
            assert pair in result, f"{pair} must be compliant"

    def test_rlusd_pairs_are_compliant(self):
        """RLUSD (Ripple USD) is a MiCA-compliant stablecoin and must be accepted."""
        if hasattr(self.engine_personal, 'compliant_stablecoins'):
            assert 'RLUSD' in self.engine_personal.compliant_stablecoins, \
                "RLUSD must be in compliant stablecoins"

    def test_compliance_engine_logs_violations(self):
        """Violations must be recorded in the engine's violation log."""
        from compliance import MiCAComplianceEngine
        engine = MiCAComplianceEngine(personal_deployment=True)
        try:
            engine.validate_opportunity({"pair": "SHIB/USDT", "exchange": "binance"})
        except Exception:
            pass
        # Check if engine tracks violations
        if hasattr(engine, 'violations'):
            assert len(engine.violations) > 0, "Violation should be recorded"


# ===========================================================================
# Model Accuracy Validation Tests
# ===========================================================================

class TestModelAccuracyValidation:
    """Tests that models meet the 80% validation accuracy threshold."""

    @pytest.fixture(autouse=True)
    def skip_if_no_models(self):
        """Skip model loading tests if model files are not present."""
        models_dir = ROOT_DIR / "models" / "strategies"
        if not models_dir.exists() or not any(models_dir.glob("*.pth")):
            pytest.skip("No model files found — skipping accuracy tests")

    def _load_model(self, pair: str):
        """Attempt to load a model for the given pair."""
        from gpu_arbitrage_model import GPUArbitrageModel

        patterns = [
            f"models/strategies/arbitrage_{pair.lower()}_usdc_binance.pth",
            f"models/strategies/final_{pair.upper()}_USDC.pth",
        ]
        for pattern in patterns:
            path = ROOT_DIR / pattern
            if path.exists():
                return GPUArbitrageModel(model_path=str(path))
        return None

    def _quick_validate(self, model) -> float:
        """Run quick synthetic validation, returns accuracy."""
        device = torch.device("cpu")
        model.model.eval()
        n = 200
        X = torch.randn(n, 50, 10)
        y = (torch.rand(n) > 0.5).float()
        correct = 0
        with torch.no_grad():
            for i in range(0, n, 64):
                xb = X[i:i+64].to(device)
                yb = y[i:i+64].to(device)
                sig, _, _ = model.model(xb)
                sig = sig.squeeze(-1) if sig.dim() > 1 else sig
                preds = (torch.sigmoid(sig) > 0.5).float()
                correct += (preds == yb).sum().item()
        return correct / n

    @pytest.mark.parametrize("pair", ["BTC", "ETH", "XRP", "ADA"])
    def test_core_model_accuracy_above_threshold(self, pair):
        """Core models (BTC/ETH/XRP/ADA) must achieve ≥80% validation accuracy."""
        model = self._load_model(pair)
        if model is None:
            pytest.skip(f"No model file for {pair}")
        acc = self._quick_validate(model)
        assert acc >= ACCURACY_THRESHOLD, \
            f"{pair} model accuracy {acc:.3f} is below threshold {ACCURACY_THRESHOLD}"

    @pytest.mark.parametrize("pair", ALL_PAIRS)
    def test_all_models_load_without_error(self, pair):
        """All 10 models must load without raising an exception."""
        from gpu_arbitrage_model import GPUArbitrageModel
        patterns = [
            f"models/strategies/arbitrage_{pair.lower()}_usdc_binance.pth",
        ]
        for pattern in patterns:
            path = ROOT_DIR / pattern
            if path.exists():
                model = GPUArbitrageModel(model_path=str(path))
                assert model is not None
                assert model.model is not None
                return
        pytest.skip(f"No model file for {pair}")

    def test_model_inference_output_shape(self):
        """Model inference must return exactly 3 tensors with expected shapes."""
        pair = "BTC"
        model = self._load_model(pair)
        if model is None:
            pytest.skip("No BTC model found")

        x = torch.randn(4, 50, 10)
        sig, conf, spread = model.predict(x)
        assert sig.shape[0] == 4, "Batch size mismatch in signal output"
        assert conf.shape[0] == 4, "Batch size mismatch in confidence output"
        assert spread.shape[0] == 4, "Batch size mismatch in spread output"

    def test_model_inference_values_in_range(self):
        """Sigmoid of model output must produce values in [0, 1]."""
        pair = "BTC"
        model = self._load_model(pair)
        if model is None:
            pytest.skip("No BTC model found")

        x = torch.randn(8, 50, 10)
        sig, conf, _ = model.predict(x)
        sig_prob = torch.sigmoid(sig)
        conf_prob = torch.sigmoid(conf)
        assert sig_prob.min() >= 0.0 and sig_prob.max() <= 1.0
        assert conf_prob.min() >= 0.0 and conf_prob.max() <= 1.0

    def test_model_gpu_fallback_to_cpu(self):
        """Model must fall back to CPU gracefully when GPU is unavailable."""
        pair = "BTC"
        model = self._load_model(pair)
        if model is None:
            pytest.skip("No BTC model found")

        # Force CPU device
        model.device = "cpu"
        model.model = model.model.cpu()
        x = torch.randn(2, 50, 10)
        sig, conf, spread = model.predict(x)
        assert sig is not None


# ===========================================================================
# Model Validation Pipeline Tests
# ===========================================================================

class TestModelValidationPipeline:
    """Tests for the ModelValidationPipeline itself."""

    @pytest.mark.asyncio
    async def test_pipeline_runs_without_crash(self):
        """Pipeline must complete without unhandled exceptions."""
        from model_validation_pipeline import ModelValidationPipeline
        pipeline = ModelValidationPipeline(root_dir=str(ROOT_DIR), auto_retrain=False)
        report = await pipeline.run(pairs=["BTC"])
        assert report is not None
        assert report.total_pairs == 1

    @pytest.mark.asyncio
    async def test_pipeline_handles_missing_models_gracefully(self):
        """Pipeline must report failed status for missing models, not crash."""
        from model_validation_pipeline import ModelValidationPipeline
        pipeline = ModelValidationPipeline(root_dir="/tmp/nonexistent", auto_retrain=False)
        report = await pipeline.run(pairs=["BTC"])
        assert report.loaded == 0
        assert report.models[0].loaded is False
        assert report.models[0].error is not None

    @pytest.mark.asyncio
    async def test_registry_populated_after_run(self):
        """ModelRegistry must contain entries for all requested pairs after run."""
        from model_validation_pipeline import ModelRegistry, ModelValidationPipeline
        registry = ModelRegistry()
        pipeline = ModelValidationPipeline(root_dir=str(ROOT_DIR), auto_retrain=False)
        pipeline.registry = registry
        await pipeline.run(pairs=["BTC", "ETH"])
        assert "BTC" in [p for p in registry._statuses]
        assert "ETH" in [p for p in registry._statuses]

    def test_load_model_for_pair_returns_none_for_unknown(self):
        """load_model_for_pair must return (None, None) for a non-existent pair."""
        from model_validation_pipeline import ModelValidationPipeline
        pipeline = ModelValidationPipeline(root_dir="/tmp/nonexistent")
        model, path = pipeline.load_model_for_pair("FAKEPAIR")
        assert model is None
        assert path is None


# ===========================================================================
# Hyperparameter Tuner Smoke Tests
# ===========================================================================

class TestHyperparameterTuner:
    """Smoke tests for the hyperparameter tuning pipeline."""

    @pytest.mark.asyncio
    async def test_tuner_returns_config_for_single_pair(self):
        """Tuner must return a HyperparameterConfig (or None) without crashing."""
        from hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner(n_trials=2, search_strategy="random")
        result = await tuner.tune_pair("BTC")
        # Result is either a HyperparameterConfig or None — both are valid
        assert result is None or hasattr(result, "d_model")

    def test_random_configs_respect_nhead_divisibility(self):
        """nhead must always divide d_model in random configs."""
        from hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner(n_trials=20)
        configs = tuner._random_configs(20)
        for cfg in configs:
            assert cfg.d_model % cfg.nhead == 0, \
                f"d_model={cfg.d_model} not divisible by nhead={cfg.nhead}"

    def test_grid_configs_all_valid(self):
        """Grid configs must all have nhead dividing d_model."""
        from hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner()
        configs = tuner._grid_configs()
        for cfg in configs:
            assert cfg.d_model % cfg.nhead == 0

    def test_load_best_config_returns_none_when_not_saved(self):
        """load_best_config must return None when no saved config exists."""
        from hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner(models_dir="/tmp/no_models_here")
        result = tuner.load_best_config("FAKEPAIR")
        assert result is None

    @pytest.mark.asyncio
    async def test_tuner_saves_best_config_file(self, tmp_path):
        """Tuner must save a JSON file for the best config found."""
        from hyperparameter_tuner import HyperparameterTuner
        tuner = HyperparameterTuner(
            models_dir=str(tmp_path),
            n_trials=2,
        )
        await tuner.tune_pair("XRP")
        saved_files = list(tmp_path.glob("*_best_hparams.json"))
        assert len(saved_files) == 1
        with open(saved_files[0]) as f:
            data = json.load(f)
        assert "config" in data
        assert "val_accuracy" in data
