#!/usr/bin/env python3
"""
SovereignForge - Model Integrity Fix Script
Fixes critical model metadata issues for production deployment

Issues to fix:
1. USDT -> USDC path mismatches in metadata
2. Placeholder checksums
3. Incorrect parameter counts
4. Trading pair mismatches
"""

import os
import sys
import json
import hashlib
import torch
from pathlib import Path
from typing import Dict, Any

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def calculate_file_checksum(file_path: str) -> str:
    """Calculate SHA256 checksum of a file"""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(4096), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception as e:
        print(f"Error calculating checksum for {file_path}: {e}")
        return "checksum_error"

def get_model_parameters(model_path: str) -> int:
    """Get actual parameter count from PyTorch model"""
    try:
        # Load model state dict to count parameters
        state_dict = torch.load(model_path, map_location='cpu', weights_only=True)
        total_params = sum(p.numel() for p in state_dict.values())
        return total_params
    except Exception as e:
        print(f"Error loading model {model_path}: {e}")
        return 0

def fix_metadata_file(metadata_path: str, models_dir: str) -> bool:
    """Fix a single metadata file"""
    try:
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)

        original_path = metadata.get('model_path', '')
        trading_pair = metadata.get('trading_pair', '')

        # Fix USDT -> USDC in paths
        if 'USDT' in original_path:
            corrected_path = original_path.replace('USDT', 'USDC')
            metadata['model_path'] = corrected_path

        # Fix trading pair
        if trading_pair.endswith('USDT'):
            metadata['trading_pair'] = trading_pair.replace('USDT', 'USDC')

        # Calculate real checksum
        model_filename = os.path.basename(metadata['model_path'])
        actual_model_path = os.path.join(models_dir, model_filename)

        if os.path.exists(actual_model_path):
            real_checksum = calculate_file_checksum(actual_model_path)
            metadata['security_checksum'] = real_checksum

            # Get real parameter count
            real_params = get_model_parameters(actual_model_path)
            if real_params > 0:
                metadata['parameters_count'] = real_params
        else:
            print(f"Warning: Model file not found: {actual_model_path}")
            return False

        # Write back fixed metadata
        with open(metadata_path, 'w') as f:
            json.dump(metadata, f, indent=2)

        print(f"Fixed: {os.path.basename(metadata_path)}")
        print(f"  Path: {original_path} -> {metadata['model_path']}")
        print(f"  Pair: {trading_pair} -> {metadata['trading_pair']}")
        print(f"  Checksum: placeholder -> {metadata['security_checksum'][:16]}...")
        print(f"  Params: {metadata.get('parameters_count', 0)}")
        print()

        return True

    except Exception as e:
        print(f"Error fixing {metadata_path}: {e}")
        return False

def main():
    """Main fix function"""
    models_dir = 'models'

    if not os.path.exists(models_dir):
        print(f"Models directory not found: {models_dir}")
        return False

    print("SovereignForge Model Integrity Fix")
    print("=" * 50)

    # Find all metadata files
    metadata_files = list(Path(models_dir).glob('*_metadata.json'))

    if not metadata_files:
        print("No metadata files found!")
        return False

    print(f"Found {len(metadata_files)} metadata files to fix:")
    for mf in metadata_files:
        print(f"  - {mf.name}")
    print()

    fixed_count = 0
    for metadata_file in metadata_files:
        if fix_metadata_file(str(metadata_file), models_dir):
            fixed_count += 1

    print(f"Fixed {fixed_count}/{len(metadata_files)} metadata files")

    # Verify all models exist
    print("\nVerifying model file existence:")
    missing_models = []
    for metadata_file in metadata_files:
        try:
            with open(metadata_file, 'r') as f:
                metadata = json.load(f)

            model_path = metadata.get('model_path', '')
            if model_path.startswith('models\\'):
                model_path = model_path.replace('models\\', '')

            full_path = os.path.join(models_dir, model_path)
            if not os.path.exists(full_path):
                missing_models.append(model_path)
                print(f"  MISSING: {model_path}")
            else:
                print(f"  FOUND: {model_path}")
        except Exception as e:
            print(f"  ERROR checking {metadata_file}: {e}")

    if missing_models:
        print(f"\nWARNING: {len(missing_models)} model files are missing!")
        print("These need to be retrained with proper USDC pairs.")
    else:
        print("\nAll model files exist!")

    return fixed_count == len(metadata_files)

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)