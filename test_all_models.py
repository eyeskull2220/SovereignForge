#!/usr/bin/env python3  
""" >> test_all_models.py && echo Test script to verify all 7 PyTorch models load properly >> test_all_models.py && echo """  
  
import sys  
import os  
sys.path.insert(0, 'src')  
  
def test_all_models():  
    print("Testing loading of all 7 PyTorch models...")  
    print("=" * 50)  
ECHO is on.
    try:  
        from realtime_inference import SecureModelLoader  
        print("[OK] SecureModelLoader import successful")  
ECHO is on.
        # Initialize loader with models directory  
        loader = SecureModelLoader(models_dir="models")  
        print("[OK] SecureModelLoader initialization successful")  
ECHO is on.
        # Test all 7 pairs  
        pairs = ['BTCUSDT', 'ETHUSDT', 'XRPUSDT', 'XLMUSDT', 'HBARUSDT', 'ALGOUSDT', 'ADAUSDT']  
        loaded_count = 0  
ECHO is on.
        for pair in pairs:  
            print(f"\nTesting {pair}...")  
            result = loader.load_model_securely(pair)  
            if result:  
                model, metadata = result  
                print(f"  [SUCCESS] {pair} loaded")  
                print(f"    Model type: {type(model).__name__}")  
                print(f"    Trading pair: {metadata.trading_pair}")  
                print(f"    Model version: {metadata.model_version}")  
                loaded_count += 1  
            else:  
                print(f"  [FAILED] {pair} could not be loaded")  
ECHO is on.
        print(f"\n{'='*50}")  
        print(f"Results: {loaded_count}/{len(pairs)} models loaded successfully")  
ECHO is on.
        if loaded_count == len(pairs):  
            print("? ALL MODELS LOADED SUCCESSFULLY!")  
            return True  
        else:  
            print("? Some models failed to load")  
            return False  
ECHO is on.
    except Exception as e:  
        print(f"[FAIL] Test failed with error: {e}")  
        import traceback  
        traceback.print_exc()  
        return False  
  
if __name__ == "__main__":  
    success = test_all_models()  
    print(f"\nOverall result: {'SUCCESS' if success else 'FAILED'}") 
