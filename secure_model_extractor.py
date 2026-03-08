#!/usr/bin/env python3
"""
Secure Model Extractor for SovereignForge
Handles secure loading and validation of PyTorch models with integrity checks
"""

import torch
import hashlib
import logging
import os
from pathlib import Path
from typing import Dict, Optional, Any, Tuple, List
import json
import pickle
from dataclasses import dataclass
from gpu_manager import get_gpu_manager, GPUManager

logger = logging.getLogger(__name__)

@dataclass
class ModelMetadata:
    """Model metadata container"""
    name: str
    version: str
    trading_pair: str
    created_at: str
    accuracy: float
    model_hash: str
    config_hash: str
    model_size_mb: float

@dataclass
class ModelValidationResult:
    """Model validation result"""
    is_valid: bool
    model_hash_matches: bool
    config_hash_matches: bool
    model_loadable: bool
    errors: List[str]

class SecureModelExtractor:
    """Secure model loading and validation system"""

    SUPPORTED_PAIRS = [
        'btc_usdt', 'eth_usdt', 'xrp_usdt', 'xlm_usdt', 'hbar_usdt', 'algo_usdt', 'ada_usdt',
        'link_usdt', 'iota_usdt'  # Added missing pairs for 7-pair requirement
    ]

    def __init__(self, models_dir: str = "models/strategies", gpu_manager: Optional[GPUManager] = None):
        self.models_dir = Path(models_dir)
        self.models_dir.mkdir(exist_ok=True)
        self.gpu_manager = gpu_manager or get_gpu_manager()
        self.loaded_models: Dict[str, Tuple[torch.nn.Module, ModelMetadata]] = {}

        # Create metadata directory
        self.metadata_dir = self.models_dir.parent / "metadata"
        self.metadata_dir.mkdir(exist_ok=True)

    def _calculate_file_hash(self, file_path: Path) -> str:
        """Calculate SHA256 hash of file"""
        hash_sha256 = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_sha256.update(chunk)
        return hash_sha256.hexdigest()

    def _validate_model_file(self, model_path: Path) -> bool:
        """Basic validation of model file"""
        try:
            # Check file exists and is readable
            if not model_path.exists():
                logger.error(f"Model file does not exist: {model_path}")
                return False

            # Check file size (reasonable limits)
            file_size = model_path.stat().st_size
            if file_size < 1024:  # Less than 1KB
                logger.error(f"Model file too small: {file_size} bytes")
                return False
            if file_size > 500 * 1024 * 1024:  # More than 500MB
                logger.error(f"Model file too large: {file_size} bytes")
                return False

            # Try to load as PyTorch model (basic check)
            try:
                # Just check if it's a valid pickle file
                with open(model_path, 'rb') as f:
                    pickle.load(f)
            except Exception as e:
                logger.error(f"Model file is not a valid pickle: {e}")
                return False

            return True

        except Exception as e:
            logger.error(f"Model validation failed: {e}")
            return False

    def _load_model_metadata(self, trading_pair: str) -> Optional[ModelMetadata]:
        """Load model metadata from JSON file"""
        metadata_path = self.metadata_dir / f"{trading_pair}_metadata.json"

        if not metadata_path.exists():
            logger.warning(f"Metadata file not found: {metadata_path}")
            return None

        try:
            with open(metadata_path, 'r') as f:
                data = json.load(f)

            return ModelMetadata(
                name=data['name'],
                version=data['version'],
                trading_pair=data['trading_pair'],
                created_at=data['created_at'],
                accuracy=data['accuracy'],
                model_hash=data['model_hash'],
                config_hash=data['config_hash'],
                model_size_mb=data['model_size_mb']
            )

        except Exception as e:
            logger.error(f"Failed to load metadata: {e}")
            return None

    def _save_model_metadata(self, metadata: ModelMetadata):
        """Save model metadata to JSON file"""
        metadata_path = self.metadata_dir / f"{metadata.trading_pair}_metadata.json"

        try:
            data = {
                'name': metadata.name,
                'version': metadata.version,
                'trading_pair': metadata.trading_pair,
                'created_at': metadata.created_at,
                'accuracy': metadata.accuracy,
                'model_hash': metadata.model_hash,
                'config_hash': metadata.config_hash,
                'model_size_mb': metadata.model_size_mb
            }

            with open(metadata_path, 'w') as f:
                json.dump(data, f, indent=2)

            logger.info(f"Metadata saved: {metadata_path}")

        except Exception as e:
            logger.error(f"Failed to save metadata: {e}")

    def validate_model(self, trading_pair: str) -> ModelValidationResult:
        """Comprehensive model validation"""
        errors = []
        # Use actual model file naming convention
        pair_upper = trading_pair.upper().replace('_', '')
        model_path = Path("models") / f"final_{pair_upper}.pth"

        # Check if model file exists
        if not model_path.exists():
            errors.append(f"Model file not found: {model_path}")
            return ModelValidationResult(False, False, False, False, errors)

        # Load metadata
        metadata = self._load_model_metadata(trading_pair)
        if not metadata:
            errors.append("Model metadata not found")
            return ModelValidationResult(False, False, False, False, errors)

        # Validate file integrity
        if not self._validate_model_file(model_path):
            errors.append("Model file validation failed")
            return ModelValidationResult(False, False, False, False, errors)

        # Check model hash
        actual_hash = self._calculate_file_hash(model_path)
        model_hash_matches = actual_hash == metadata.model_hash
        if not model_hash_matches:
            errors.append(f"Model hash mismatch: expected {metadata.model_hash}, got {actual_hash}")

        # Try to load model
        model_loadable = False
        try:
            # Load model state dict to check if it's valid
            state_dict = torch.load(model_path, map_location='cpu', weights_only=True)
            model_loadable = isinstance(state_dict, dict) and len(state_dict) > 0
            if not model_loadable:
                errors.append("Model state dict is invalid")
        except Exception as e:
            errors.append(f"Model loading failed: {e}")

        # Config hash validation (if config file exists)
        config_path = self.models_dir / f"arbitrage_{trading_pair}_config.json"
        config_hash_matches = True
        if config_path.exists():
            try:
                actual_config_hash = self._calculate_file_hash(config_path)
                config_hash_matches = actual_config_hash == metadata.config_hash
                if not config_hash_matches:
                    errors.append(f"Config hash mismatch: expected {metadata.config_hash}, got {actual_config_hash}")
            except Exception as e:
                errors.append(f"Config validation failed: {e}")
                config_hash_matches = False

        is_valid = model_hash_matches and config_hash_matches and model_loadable

        return ModelValidationResult(
            is_valid=is_valid,
            model_hash_matches=model_hash_matches,
            config_hash_matches=config_hash_matches,
            model_loadable=model_loadable,
            errors=errors
        )

    def load_model(self, trading_pair: str, force_cpu: bool = False) -> Optional[torch.nn.Module]:
        """Securely load a model with validation"""
        if trading_pair not in self.SUPPORTED_PAIRS:
            logger.error(f"Unsupported trading pair: {trading_pair}")
            return None

        # Check if already loaded
        if trading_pair in self.loaded_models:
            model, _ = self.loaded_models[trading_pair]
            logger.info(f"Model {trading_pair} already loaded")
            return model

        # Validate model
        validation = self.validate_model(trading_pair)
        if not validation.is_valid:
            logger.error(f"Model validation failed for {trading_pair}: {validation.errors}")
            return None

        # Use actual model file naming convention
        pair_upper = trading_pair.upper().replace('_', '')
        model_path = Path("models") / f"final_{pair_upper}.pth"

        try:
            # Determine device
            device = torch.device('cpu') if force_cpu else self.gpu_manager.device

            # Load full checkpoint (not just weights_only due to ModelConfig class)
            checkpoint = torch.load(model_path, map_location=device, weights_only=False)
            model_state = checkpoint['model_state_dict']

            # Create model architecture (assuming transformer-based model)
            # This would need to be adjusted based on actual model architecture
            from gpu_arbitrage_model import GPUArbitrageModel

            # Load config if available
            config_path = self.models_dir / f"arbitrage_{trading_pair}_config.json"
            config = {}
            if config_path.exists():
                with open(config_path, 'r') as f:
                    config = json.load(f)

            # Create model with config
            model = GPUArbitrageModel(**config)
            model.load_state_dict(model_state)
            model.to(device)
            model.eval()

            # Store loaded model
            metadata = self._load_model_metadata(trading_pair)
            self.loaded_models[trading_pair] = (model, metadata)

            model_size_mb = model_path.stat().st_size / 1024 / 1024
            logger.info(f"Model {trading_pair} loaded successfully ({model_size_mb:.1f}MB)")

            return model

        except Exception as e:
            logger.error(f"Failed to load model {trading_pair}: {e}")
            return None

    def unload_model(self, trading_pair: str):
        """Unload a model from memory"""
        if trading_pair in self.loaded_models:
            del self.loaded_models[trading_pair]
            logger.info(f"Model {trading_pair} unloaded")

            # Force garbage collection
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def get_loaded_models(self) -> Dict[str, ModelMetadata]:
        """Get information about currently loaded models"""
        return {pair: metadata for pair, (_, metadata) in self.loaded_models.items()}

    def preload_models(self, trading_pairs: List[str], force_cpu: bool = False):
        """Preload multiple models for faster inference"""
        logger.info(f"Preloading models: {trading_pairs}")

        for pair in trading_pairs:
            if pair in self.SUPPORTED_PAIRS:
                self.load_model(pair, force_cpu)
            else:
                logger.warning(f"Skipping unsupported pair: {pair}")

    def get_model_info(self, trading_pair: str) -> Optional[Dict[str, Any]]:
        """Get detailed information about a model"""
        metadata = self._load_model_metadata(trading_pair)
        if not metadata:
            return None

        validation = self.validate_model(trading_pair)
        # Use actual model file naming convention
        pair_upper = trading_pair.upper().replace('_', '')
        model_path = Path("models") / f"final_{pair_upper}.pth"

        return {
            'metadata': metadata,
            'validation': {
                'is_valid': validation.is_valid,
                'model_hash_matches': validation.model_hash_matches,
                'config_hash_matches': validation.config_hash_matches,
                'model_loadable': validation.model_loadable,
                'errors': validation.errors
            },
            'file_info': {
                'path': str(model_path),
                'exists': model_path.exists(),
                'size_mb': model_path.stat().st_size / 1024 / 1024 if model_path.exists() else 0
            },
            'loaded': trading_pair in self.loaded_models
        }

# Global instance
_secure_extractor = None

def get_secure_extractor(models_dir: str = "models/strategies") -> SecureModelExtractor:
    """Get or create secure model extractor instance"""
    global _secure_extractor

    if _secure_extractor is None:
        _secure_extractor = SecureModelExtractor(models_dir)

    return _secure_extractor