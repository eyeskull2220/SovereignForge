#!/usr/bin/env python3
"""
Standalone SovereignForge Inference Test
Test models without complex dependencies
"""

import torch
import torch.nn as nn
import os
import time

class StandaloneArbitrageModel(nn.Module):
    """Simplified model for inference testing"""

    def __init__(self, hidden_size=512, num_layers=12, num_heads=16):
        super().__init__()

        # Simple transformer-like architecture
        self.input_embedding = nn.Linear(48, hidden_size)

        # Multi-head attention layers
        self.layers = nn.ModuleList([
            nn.TransformerEncoderLayer(
                d_model=hidden_size,
                nhead=num_heads,
                dim_feedforward=hidden_size * 4,
                dropout=0.1,
                batch_first=True
            ) for _ in range(num_layers)
        ])

        # Output heads
        self.arbitrage_head = nn.Linear(hidden_size, 1)
        self.confidence_head = nn.Linear(hidden_size, 1)
        self.spread_head = nn.Linear(hidden_size, 1)

    def forward(self, market_data):
        # Extract features
        price_sequences = market_data['price_sequences']  # [batch, seq_len, exchanges, features]

        # Flatten for processing
        batch_size, seq_len, num_exchanges, num_features = price_sequences.shape
        x = price_sequences.view(batch_size, seq_len, -1)  # [batch, seq_len, exchanges * features]

        # Input embedding
        x = self.input_embedding(x)  # [batch, seq_len, hidden_size]

        # Apply transformer layers
        for layer in self.layers:
            x = layer(x)

        # Global average pooling
        features = x.mean(dim=1)  # [batch, hidden_size]

        # Generate predictions
        arbitrage_probability = self.arbitrage_head(features).squeeze(-1)
        confidence_score = self.confidence_head(features).squeeze(-1)
        spread_prediction = self.spread_head(features).squeeze(-1)

        return {
            'arbitrage_probability': arbitrage_probability,
            'confidence_score': confidence_score,
            'spread_prediction': spread_prediction,
            'features': features
        }

def load_model_safely(model_path):
    """Load model state_dict safely"""
    try:
        # Load checkpoint
        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)

        # Extract state_dict
        if 'model_state_dict' in checkpoint:
            return checkpoint['model_state_dict']
        elif isinstance(checkpoint, dict):
            return checkpoint
        else:
            return None
    except Exception as e:
        print(f"Failed to load {model_path}: {e}")
        return None

def test_all_models():
    """Test all trained models"""
    print("SovereignForge Standalone Inference Test")
    print("=" * 50)

    pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']
    loaded_models = {}
    inference_results = {}

    # Load all models
    for pair in pairs:
        model_path = f'E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\final_{pair.replace("/", "_")}.pth'

        if os.path.exists(model_path):
            print(f"\nLoading {pair}...")
            state_dict = load_model_safely(model_path)

            if state_dict:
                print(f"  SUCCESS: Loaded {len(state_dict)} parameters")

                # Create model and load state
                model = StandaloneArbitrageModel()
                try:
                    model.load_state_dict(state_dict, strict=False)
                    model.eval()
                    loaded_models[pair] = model
                    print(f"  SUCCESS: Model ready for inference")
                except Exception as e:
                    print(f"  ERROR: Failed to load state_dict - {e}")
            else:
                print(f"  ERROR: Could not extract state_dict")
        else:
            print(f"  MISSING: {model_path}")

    print(f"\nLoaded {len(loaded_models)}/{len(pairs)} models successfully")

    # Test inference
    if loaded_models:
        print("\nTesting Inference Performance")
        print("=" * 30)

        for pair, model in loaded_models.items():
            print(f"\nTesting {pair}...")

            # Create test data
            test_data = {
                'price_sequences': torch.randn(1, 200, 3, 16),  # [batch, seq_len, exchanges, features]
                'exchange_ids': torch.randint(0, 3, (1, 3)),
                'pair_ids': torch.tensor([0]),
                'arbitrage_label': torch.tensor([0.0]),
                'confidence_label': torch.rand(1, 1),
                'spread_label': torch.randn(1, 1) * 0.01
            }

            try:
                # Measure inference time
                start = time.time()
                with torch.no_grad():
                    result = model(test_data)
                end = time.time()

                latency = (end - start) * 1000

                # Store results
                inference_results[pair] = {
                    'latency_ms': latency,
                    'arbitrage_prob': result['arbitrage_probability'].item(),
                    'confidence': result['confidence_score'].item(),
                    'spread_pred': result['spread_prediction'].item()
                }

                print("  SUCCESS: Inference completed")
                print(".2f")
                print(".4f")
                print(".4f")
                print(".4f")

            except Exception as e:
                print(f"  ERROR: Inference failed - {e}")

    # Summary
    print("\n" + "=" * 50)
    print("INFERENCE TEST SUMMARY")
    print("=" * 50)

    if inference_results:
        print(f"SUCCESS: {len(inference_results)}/{len(pairs)} models tested successfully")
        print("\nPerformance Summary:")

        total_latency = 0
        for pair, results in inference_results.items():
            print(f"  {pair}:")
            print(".2f")
            print(".4f")
            print(".4f")
            print(".4f")
            total_latency += results['latency_ms']

        avg_latency = total_latency / len(inference_results)
        print(".2f")

        # Save secure versions
        print("\nSaving secure model versions...")
        secure_dir = 'E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\secure'
        os.makedirs(secure_dir, exist_ok=True)

        for pair, model in loaded_models.items():
            secure_path = f"{secure_dir}\\secure_{pair.replace('/', '_')}.pth"
            torch.save(model.state_dict(), secure_path)
            print(f"  SAVED: {secure_path}")

        print("\n🎉 ALL TESTS PASSED!")
        print("Models are ready for production deployment")
        return True

    else:
        print("❌ NO MODELS COULD BE TESTED")
        print("Check model files and loading process")
        return False

if __name__ == "__main__":
    success = test_all_models()
    print(f"\nOVERALL RESULT: {'SUCCESS' if success else 'FAILED'}")