#!/usr/bin/env python3
"""
Fix SovereignForge Model Loading
Add the src directory to path and load models properly
"""

import sys
import os
import torch

# Add the src directory to Python path
src_path = os.path.join(os.path.dirname(__file__), 'src')
sys.path.insert(0, src_path)

print("Fixed SovereignForge Model Loading")
print("=" * 40)

def load_models_safely():
    """Load all trained models with proper imports"""
    pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']
    loaded_models = {}

    for pair in pairs:
        model_path = f'E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\final_{pair.replace("/", "_")}.pth'

        if os.path.exists(model_path):
            try:
                # Load checkpoint with proper imports available
                checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)

                if 'model_state_dict' in checkpoint:
                    state_dict = checkpoint['model_state_dict']
                    print(f'SUCCESS: {pair} loaded ({len(state_dict)} parameters)')
                    loaded_models[pair] = state_dict
                else:
                    print(f'WARNING: {pair} has no model_state_dict')
            except Exception as e:
                print(f'ERROR: {pair} failed - {str(e)[:50]}')
        else:
            print(f'MISSING: {pair}')

    return loaded_models

def save_secure_models(loaded_models):
    """Save models in secure format (weights_only=True)"""
    if not loaded_models:
        print("No models to save securely")
        return

    secure_dir = 'models/secure'
    os.makedirs(secure_dir, exist_ok=True)

    print(f"\nSaving {len(loaded_models)} models securely...")

    for pair, state_dict in loaded_models.items():
        secure_path = f"{secure_dir}/secure_{pair.replace('/', '_')}.pth"

        # Save with weights_only=True for security
        torch.save(state_dict, secure_path, _use_new_zipfile_serialization=True)
        print(f"SAVED: {secure_path}")

    print("All models saved securely!")

def test_inference(loaded_models):
    """Test inference with loaded models"""
    if not loaded_models:
        return False

    print("\nTesting Inference Performance")
    print("=" * 30)

    # Import the model class now that path is set
    try:
        from src.gpu_arbitrage_model import ArbitrageTransformer, ModelConfig

        config = ModelConfig(hidden_size=512, num_layers=12, num_heads=16)

        # Test first model
        test_pair = list(loaded_models.keys())[0]
        state_dict = loaded_models[test_pair]

        print(f"Testing {test_pair}...")

        # Create model and load state
        model = ArbitrageTransformer(config)
        model.load_state_dict(state_dict)
        model.eval()

        # Test inference
        test_data = {
            'price_sequences': torch.randn(1, 200, 3, 16),
            'exchange_ids': torch.randint(0, 3, (1, 3)),
            'pair_ids': torch.tensor([0]),
            'arbitrage_label': torch.tensor([0.0]),
            'confidence_label': torch.rand(1, 1),
            'spread_label': torch.randn(1, 1) * 0.01
        }

        import time
        start = time.time()
        with torch.no_grad():
            result = model(test_data)
        end = time.time()

        latency = (end - start) * 1000

        print("SUCCESS: Inference test passed")
        print(".2f")
        print(".4f")
        print(".4f")
        print(".4f")

        return True

    except Exception as e:
        print(f"ERROR: Inference test failed - {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    print(f"Python path includes: {src_path}")
    print(f"Available in sys.path: {src_path in sys.path}")

    # Load models
    loaded_models = load_models_safely()

    print(f"\nLoaded {len(loaded_models)}/{7} models")

    if loaded_models:
        # Save securely
        save_secure_models(loaded_models)

        # Test inference
        inference_success = test_inference(loaded_models)

        print("\n" + "=" * 40)
        if inference_success:
            print("RESULT: SUCCESS")
            print("Models loaded, secured, and tested!")
        else:
            print("RESULT: ISSUES DETECTED")
            print("Models loaded but inference failed")
    else:
        print("RESULT: FAILED")
        print("Could not load any models")

    print("=" * 40)