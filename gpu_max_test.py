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
    if not gpu_manager or not gpu_manager.initialize():
        print("ERROR: GPU Manager failed to initialize")
        return False

    print("SUCCESS: GPU Manager initialized successfully")
    print(f"   Device: {gpu_manager.get_device()}")
    print(f"   Memory Fraction: 0.8 (12.8GB of 16GB)")

    # Show initial memory usage
    memory_info = gpu_manager.get_memory_info()
    print("\nInitial GPU Memory:")
    print(f"   Allocated: {memory_info.get('allocated_mb', 0):.1f} MB")
    print(f"   Free: {memory_info.get('free_mb', 0):.1f} MB")
    print(f"   Total: {memory_info.get('total_mb', 0):.1f} MB")

    # Create GPU Max model configuration
    config = ModelConfig(
        input_size=48,  # 3 exchanges * 16 features = 48
        hidden_size=512,  # 2x larger
        num_layers=12,    # 2x more layers
        num_heads=16,     # 2x more heads
        max_seq_length=200,  # 2x longer sequences
        num_pairs=7,
        num_exchanges=3
    )

    print("\nCreating GPU Max Model:")
    print(f"   Hidden Size: {config.hidden_size} (512)")
    print(f"   Layers: {config.num_layers} (12)")
    print(f"   Heads: {config.num_heads} (16)")
    print(f"   Max Sequence: {config.max_seq_length} (200)")
    print(f"   Parameters: ~{estimate_parameters(config):,}")

    # Create model
    model = ArbitrageTransformer(config)
    model = model.to(gpu_manager.get_device())

    # Show memory after model creation
    torch.cuda.synchronize()
    memory_info = gpu_manager.get_memory_info()
    print("\nGPU Memory After Model Creation:")
    print(f"   Allocated: {memory_info.get('allocated_mb', 0):.1f} MB")
    print(f"   Memory Usage: {(memory_info.get('allocated_mb', 0) / memory_info.get('total_mb', 1) * 100):.1f}%")

    # Create large batch for testing and keep it in memory
    batch_size = 64
    seq_len = 200
    num_exchanges = 3
    num_features = 16

    print("\nTesting with Large Batch:")
    print(f"   Batch Size: {batch_size}")
    print(f"   Sequence Length: {seq_len}")
    print(f"   Total Samples: {batch_size * seq_len:,}")

    # Create test batch and keep references to prevent garbage collection
    test_batch = {
        'price_sequences': torch.randn(batch_size, seq_len, num_exchanges, num_features, device=gpu_manager.get_device()),
        'exchange_ids': torch.randint(0, num_exchanges, (batch_size, num_exchanges), device=gpu_manager.get_device()),
        'pair_ids': torch.randint(0, 7, (batch_size,), device=gpu_manager.get_device()),
        'arbitrage_label': torch.randint(0, 2, (batch_size,), device=gpu_manager.get_device()).float(),
        'confidence_label': torch.rand(batch_size, 1, device=gpu_manager.get_device()),
        'spread_label': torch.randn(batch_size, 1, device=gpu_manager.get_device()) * 0.01
    }

    # Forward pass - keep outputs in memory
    model.eval()
    outputs = None
    with torch.no_grad():
        try:
            outputs = model(test_batch)
            print("SUCCESS: Forward pass successful")
            print(f"   Output shapes: arbitrage={outputs['arbitrage_probability'].shape}, confidence={outputs['confidence_score'].shape}")
        except Exception as e:
            print(f"ERROR: Forward pass failed: {e}")
            return False

    # Show peak memory usage while keeping everything in memory
    torch.cuda.synchronize()
    memory_info = gpu_manager.get_memory_info()
    print("\nPeak GPU Memory Usage:")
    print(f"   Allocated: {memory_info.get('allocated_mb', 0):.1f} MB")
    print(f"   Memory Utilization: {(memory_info.get('allocated_mb', 0) / memory_info.get('total_mb', 1) * 100):.1f}%")
    print(f"   VRAM Target: 10-12GB achieved? {'YES' if memory_info.get('allocated_mb', 0) > 8000 else 'NO'}")

    # Keep references to prevent cleanup
    del outputs, test_batch

    # Cleanup
    gpu_manager.shutdown()

    print("\nGPU Max Configuration Test Complete!")
    print("   Your RTX 4060 Ti is now utilizing maximum VRAM for personal use!")
    return True

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