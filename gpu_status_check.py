#!/usr/bin/env python3
"""
Quick GPU Status Check for SovereignForge
"""

import sys
import os

def check_gpu_status():
    """Check GPU availability and status"""

    print("🔍 SovereignForge GPU Status Check")
    print("=" * 40)

    # Check if we're in the right directory
    if not os.path.exists('src/gpu_manager.py'):
        print("❌ Error: Please run from SovereignForge root directory")
        return

    try:
        # Try to import GPU monitoring libraries
        print("📦 Checking GPU libraries...")

        try:
            import torch
            print("✅ PyTorch available")
            if torch.cuda.is_available():
                print(f"✅ CUDA available - {torch.cuda.device_count()} device(s)")
                for i in range(torch.cuda.device_count()):
                    device_name = torch.cuda.get_device_name(i)
                    print(f"  GPU {i}: {device_name}")
            else:
                print("⚠️  CUDA not available - running on CPU")
        except ImportError:
            print("❌ PyTorch not available")

        try:
            import GPUtil
            print("✅ GPUtil available")
            gpus = GPUtil.getGPUs()
            if gpus:
                print(f"✅ Found {len(gpus)} GPU(s)")
                for gpu in gpus:
                    print(f"  {gpu.name}: {gpu.memoryUsed:.0f}MB / {gpu.memoryTotal:.0f}MB ({gpu.load*100:.1f}%)")
            else:
                print("⚠️  No GPUs detected by GPUtil")
        except ImportError:
            print("❌ GPUtil not available")

        try:
            from pynvml import nvmlInit
            print("✅ NVIDIA Management Library available")
            try:
                nvmlInit()
                print("✅ NVML initialized successfully")
            except Exception as e:
                print(f"⚠️  NVML initialization failed: {e}")
        except ImportError:
            print("❌ NVIDIA Management Library not available")

    except Exception as e:
        print(f"❌ Error during GPU check: {e}")

    # Check project structure
    print("\n📁 Checking project structure...")
    required_files = [
        'src/gpu_manager.py',
        'src/training_monitor.py',
        'src/gpu_training_cli.py',
        'gpu_train.py',
        'requirements-gpu.txt'
    ]

    for file in required_files:
        if os.path.exists(file):
            print(f"✅ {file}")
        else:
            print(f"❌ {file} - MISSING")

    print("\n🎯 GPU Training Readiness:")
    print("- Run demo: python test_monitor.py")
    print("- Train models: python gpu_train.py --all-pairs")
    print("- Check status: python src/gpu_training_cli.py status")

if __name__ == "__main__":
    check_gpu_status()