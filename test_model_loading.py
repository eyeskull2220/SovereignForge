#!/usr/bin/env python3
"""
Test script for model loading fixes
"""

import sys
import os
sys.path.insert(0, 'src')

def test_model_loading():
    print("Testing model loading...")

    try:
        from arbitrage_detector import LegacyArbitrageDetector
        print("[OK] LegacyArbitrageDetector import successful")
    except ImportError as e:
        print(f"[FAIL] LegacyArbitrageDetector import failed: {e}")
        return False

    try:
        from realtime_inference import SecureModelLoader
        print("[OK] SecureModelLoader import successful")

        # Test model loader
        loader = SecureModelLoader(models_dir="models")
        print("[OK] SecureModelLoader initialization successful")

        # Try to load BTC model
        result = loader.load_model_securely("BTCUSDT")
        if result:
            print("[OK] BTC model loading successful")
            model, metadata = result
            print(f"  Model type: {type(model)}")
            print(f"  Metadata: {metadata.trading_pair}")
            return True
        else:
            print("[FAIL] BTC model loading failed")
            return False

    except Exception as e:
        print(f"[FAIL] SecureModelLoader test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_model_loading()
    print(f"\nOverall result: {'SUCCESS' if success else 'FAILED'}")