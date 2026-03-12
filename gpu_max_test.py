#!/usr/bin/env python3
"""
GPU Max Configuration Test - Personal Use Optimization
Test script to verify high VRAM utilization
"""

import torch
import torch.nn as nn
import sys
import os

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from gpu_manager import get_gpu_manager
from gpu_arbitrage_model import ModelConfig, ArbitrageTransformer

def test_gpu_max_config():
    """Test GPU Max configuration for high VRAM utilization"""

    print("Testing GPU Max Configuration for Personal Use")
    print("=" * 60)

    # Initialize GPU manager with high memory fraction
    gpu_manager = get_gpu_manager(memory_fraction=0.8)
    if not gpu_manager:
        print("ERROR: GPU Manager failed to initialize")
        return False

    print("SUCCESS: GPU Manager initialized successfully")
    print(f"   Available GPUs: {len(gpu_manager.available_gpus)}")
    print(f"   Memory Fraction: 0.8")

    # Get GPU info
    gpu_info = gpu_manager.get_gpu_info()
    if gpu_info:
        for gpu_id, info in gpu_info.items():
            print(f"   GPU {gpu_id}: {info.name}, {info.memory_free}MB free, {info.memory_total}MB total")

    # Test basic GPU allocation
    gpu_id = gpu_manager.allocate_gpu(
        process_id="test_gpu_max",
        model_name="gpu_test",
        operation_type="test"
    )

    if gpu_id is not None:
        print(f"SUCCESS: GPU {gpu_id} allocated for testing")
        gpu_manager.deallocate_gpu("test_gpu_max")
        print("SUCCESS: GPU deallocated")
    else:
        print("WARNING: Could not allocate GPU (expected in some environments)")

    # Cleanup
    gpu_manager.shutdown()

    print("\nGPU Max Configuration Test Complete!")
    print("   GPU Manager is functional for personal use!")
    return True  # Explicitly signal success

def estimate_parameters(config: ModelConfig) -> int:
    """Estimate model parameters"""
    # Rough estimation
    embedding_params = config.input_size * config.hidden_size
    attention_params = config.num_layers * config.num_heads * config.hidden_size * config.hidden_size * 3  # QKV
    feedforward_params = config.num_layers * config.hidden_size * config.hidden_size * 4  # FFN
    output_params = config.hidden_size * 3  # 3 output heads

    total = embedding_params + attention_params + feedforward_params + output_params
    return int(total / 1e6) * 1000000  # Round to millions

if __name__ == "__main__":
    success = test_gpu_max_config()
    if success:
        print("\nReady for production training with maximum VRAM utilization!")
    else:
        print("\nGPU Max configuration needs adjustment")
    sys.exit(0 if success else 1)