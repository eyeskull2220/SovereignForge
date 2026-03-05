#!/usr/bin/env python3
"""
Inspect SovereignForge Model Checkpoint Structure
"""

import torch
import sys

def inspect_checkpoint():
    model_path = r'E:\Users\Gino\Downloads\SovereignForge\models\final_BTC_USDT.pth'

    try:
        print(f"Inspecting checkpoint: {model_path}")
        print("=" * 50)

        # Load checkpoint
        checkpoint = torch.load(model_path, map_location='cpu', weights_only=False)

        print("Checkpoint type:", type(checkpoint))
        print("Checkpoint keys:", list(checkpoint.keys()))

        # Check for model_state_dict
        if 'model_state_dict' in checkpoint:
            state_dict = checkpoint['model_state_dict']
            print("\nModel State Dict:")
            print(f"  Type: {type(state_dict)}")
            print(f"  Parameters: {len(state_dict)}")
            print(f"  First 5 keys: {list(state_dict.keys())[:5]}")

            # Check parameter shapes
            print("\nParameter shapes (first 5):")
            for i, (key, param) in enumerate(state_dict.items()):
                if i >= 5:
                    break
                print(f"  {key}: {param.shape}")

        else:
            print("\nDirect state dict (no wrapper):")
            print(f"  Parameters: {len(checkpoint)}")
            print(f"  First 5 keys: {list(checkpoint.keys())[:5]}")

        # Check other metadata
        print("\nMetadata:")
        for key, value in checkpoint.items():
            if key != 'model_state_dict':
                if isinstance(value, (str, int, float, bool)):
                    print(f"  {key}: {value}")
                else:
                    print(f"  {key}: {type(value)}")

        print("\nSUCCESS: Checkpoint inspection complete")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    inspect_checkpoint()