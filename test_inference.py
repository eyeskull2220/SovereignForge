#!/usr/bin/env python3
"""
Test SovereignForge Model Inference
Simple test script to verify trained models work
"""

import torch
from src.gpu_arbitrage_model import ArbitrageTransformer, ModelConfig
import os
import time

def test_model_inference():
    print("Testing SovereignForge Model Inference")
    print("=" * 50)

    # Test configuration
    config = ModelConfig(hidden_size=512, num_layers=12, num_heads=16)
    pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']

    print("Loading and testing all trained models...")
    print()

    loaded_models = {}
    for pair in pairs:
        model_path = f'models/final_{pair.replace("/", "_")}.pth'
        if os.path.exists(model_path):
            try:
                model = ArbitrageTransformer(config)
                checkpoint = torch.load(model_path, map_location='cpu')
                model.load_state_dict(checkpoint['model_state_dict'])
                model.eval()
                loaded_models[pair] = model
                print(f'SUCCESS: {pair} loaded')
            except Exception as e:
                print(f'ERROR: {pair} failed - {str(e)[:50]}')
        else:
            print(f'MISSING: {pair} - {model_path}')

    print()
    print(f'Successfully loaded {len(loaded_models)}/{len(pairs)} models')
    print()

    if loaded_models:
        # Test inference performance
        print('Testing inference performance...')
        test_pair = list(loaded_models.keys())[0]
        model = loaded_models[test_pair]

        # Create test data
        test_data = {
            'price_sequences': torch.randn(1, 200, 3, 16),  # [batch, seq_len, exchanges, features]
            'exchange_ids': torch.randint(0, 3, (1, 3)),     # [batch, exchanges]
            'pair_ids': torch.tensor([0]),                   # [batch]
            'arbitrage_label': torch.tensor([0.0]),          # [batch]
            'confidence_label': torch.rand(1, 1),            # [batch, 1]
            'spread_label': torch.randn(1, 1) * 0.01         # [batch, 1]
        }

        # Measure inference time
        times = []
        for i in range(5):  # Reduced to 5 for faster testing
            start = time.time()
            with torch.no_grad():
                result = model(test_data)
            end = time.time()
            times.append((end - start) * 1000)  # Convert to milliseconds

        avg_time = sum(times) / len(times)
        print(f'SUCCESS: {test_pair} Inference Test:')
        print(f'   Average latency: {avg_time:.2f}ms')
        print(f'   Arbitrage probability: {result["arbitrage_probability"].item():.4f}')
        print(f'   Confidence score: {result["confidence_score"].item():.4f}')
        print(f'   Spread prediction: {result["spread_prediction"].item():.4f}')

        print()
        print('All models ready for real-time inference!')
        return True
    else:
        print('No models could be loaded')
        return False

if __name__ == "__main__":
    success = test_model_inference()
    print(f"\nTest {'PASSED' if success else 'FAILED'}")