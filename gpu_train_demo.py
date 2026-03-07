#!/usr/bin/env python3
"""
SovereignForge GPU Training Demo - Wave 7
Demonstrates the beautiful training monitor with progress bars and GPU metrics

Usage:
    python gpu_train_demo.py --demo-mode
    python gpu_train_demo.py --real-training --pairs BTC/USDT ETH/USDT
"""

import os
import sys
import argparse
import time
import threading
from typing import List

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from training_monitor import create_training_monitor, display_training_monitor

def run_demo_training(pairs: List[str], epochs: int = 10):
    """Run a demo training session with simulated progress"""

    print("Starting SovereignForge GPU Training Demo")
    print("=" * 60)

    # Create training monitor
    monitor = create_training_monitor(pairs, epochs)

    try:
        # Start display in background thread
        display_thread = threading.Thread(target=display_training_monitor, args=(monitor,), daemon=True)
        display_thread.start()

        # Simulate training progress
        import random

        for epoch in range(1, epochs + 1):
            print(f"\nEpoch {epoch}/{epochs} - Training Progress:")

            for pair in pairs:
                # Simulate realistic training progress
                progress = epoch / epochs

                # Simulate loss decreasing over time
                base_loss = 2.0 - (epoch / epochs) * 1.5
                loss = base_loss + random.uniform(-0.2, 0.2)
                loss = max(0.1, loss)  # Minimum loss

                # Simulate accuracy increasing over time
                base_acc = 0.4 + (epoch / epochs) * 0.5
                accuracy = base_acc + random.uniform(-0.05, 0.05)
                accuracy = min(0.95, max(0.3, accuracy))  # Clamp accuracy

                # Update monitor
                monitor.update_pair_progress(
                    pair=pair,
                    status='training',
                    progress=progress,
                    current_epoch=epoch,
                    loss=loss,
                    accuracy=accuracy
                )

                print(f"  {pair}: loss={loss:.4f}, acc={accuracy:.4f}")
            # Simulate training time per epoch
            time.sleep(1.5)

        # Mark all pairs as completed
        print("\nTraining completed! Marking pairs as finished...")
        for pair in pairs:
            monitor.update_pair_progress(
                pair=pair,
                status='completed',
                progress=1.0,
                current_epoch=epochs,
                loss=0.15 + random.uniform(-0.05, 0.05),
                accuracy=0.85 + random.uniform(-0.05, 0.05)
            )

        # Keep display active for a few seconds to show final results
        time.sleep(3)

    except KeyboardInterrupt:
        print("\nDemo interrupted by user")
    finally:
        monitor.stop_monitoring()
        print("\nDemo completed! Check the training monitor display above.")

def run_real_training(pairs: List[str], epochs: int = 50):
    """Run actual GPU training with monitoring"""

    print("Starting SovereignForge Real GPU Training")
    print("=" * 60)

    # Create training monitor
    monitor = create_training_monitor(pairs, epochs)

    try:
        # Import and run actual training
        from gpu_train import GPUTrainingOrchestrator

        # Create args object for training
        class Args:
            def __init__(self):
                self.pairs = pairs
                self.epochs = epochs
                self.batch_size = 32
                self.gpu_device = 0
                self.memory_fraction = 0.8
                self.learning_rate = 1e-4
                self.gradient_clip = 1.0
                self.tensorboard = True
                self.wandb = False
                self.gpu_monitor = True
                self.mixed_precision = False

        args = Args()

        # Start display in background thread
        display_thread = threading.Thread(target=display_training_monitor, args=(monitor,), daemon=True)
        display_thread.start()

        # Run actual training
        orchestrator = GPUTrainingOrchestrator(args)
        results = orchestrator.run_training()

        if results:
            print("\nReal GPU training completed successfully!")
            print(f"Trained {len(results)} pairs")
            print("Check models/ and reports/ directories for results")
        else:
            print("\nTraining failed or was interrupted")
    except KeyboardInterrupt:
        print("\nTraining interrupted by user")
    finally:
        monitor.stop_monitoring()

def main():
    """Main demo entry point"""

    parser = argparse.ArgumentParser(
        description='SovereignForge GPU Training Demo - Wave 7',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run demo with simulated training
  python gpu_train_demo.py --demo-mode

  # Run real GPU training
  python gpu_train_demo.py --real-training --pairs BTC/USDT ETH/USDT

  # Custom demo settings
  python gpu_train_demo.py --demo-mode --pairs BTC/USDT ETH/USDT XRP/USDT --epochs 5
        """
    )

    parser.add_argument('--demo-mode', action='store_true',
                       help='Run demo mode with simulated training progress')
    parser.add_argument('--real-training', action='store_true',
                       help='Run actual GPU training (requires GPU and dependencies)')
    parser.add_argument('--pairs', nargs='+',
                       default=['BTC/USDT', 'ETH/USDT', 'XRP/USDT'],
                       help='Trading pairs for training/demo')
    parser.add_argument('--epochs', type=int, default=10,
                       help='Number of epochs for demo (default: 10)')

    args = parser.parse_args()

    # Validate arguments
    if not args.demo_mode and not args.real_training:
        parser.error("Must specify either --demo-mode or --real-training")

    if args.demo_mode and args.real_training:
        parser.error("Cannot specify both --demo-mode and --real-training")

    # Check if we're in the right directory
    if not os.path.exists('src/training_monitor.py'):
        print("Error: Please run this script from the SovereignForge root directory")
        print("Expected: E:\\SovereignForge\\")
        sys.exit(1)

    # Run selected mode
    if args.demo_mode:
        print("Running GPU Training Demo Mode")
        print("This will show the beautiful progress monitoring interface")
        print("with simulated training data.\n")

        run_demo_training(args.pairs, args.epochs)

    elif args.real_training:
        print("Running Real GPU Training")
        print("This will perform actual GPU-accelerated arbitrage training.")
        print("Make sure you have:")
        print("  - GPU with CUDA support")
        print("  - Installed requirements-gpu.txt dependencies")
        print("  - Sufficient GPU memory\n")

        confirm = input("Continue with real training? (y/N): ")
        if confirm.lower() not in ['y', 'yes']:
            print("Training cancelled.")
            sys.exit(0)

        run_real_training(args.pairs, args.epochs)

if __name__ == "__main__":
    main()