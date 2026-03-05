#!/usr/bin/env python3
"""
Quick test of the GPU Training Monitor interface
"""

import sys
import os
import time
import threading

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

def test_monitor():
    """Test the training monitor interface"""

    from training_monitor import create_training_monitor, display_training_monitor

    print("🎯 Testing SovereignForge GPU Training Monitor")
    print("=" * 50)

    # Create monitor for 3 pairs
    pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT']
    monitor = create_training_monitor(pairs, 10)

    print("📊 Created training monitor for pairs:", pairs)
    print("🚀 Starting display interface...")

    # Start display in background
    display_thread = threading.Thread(target=display_training_monitor, args=(monitor,), daemon=True)
    display_thread.start()

    # Simulate some training progress
    print("\n🔄 Simulating training progress...")

    for epoch in range(1, 6):
        print(f"Epoch {epoch}/10")

        for pair in pairs:
            progress = epoch / 10.0
            loss = 2.0 - (epoch * 0.15) + (hash(pair) % 10) * 0.1  # Pseudo-random
            accuracy = 0.4 + (epoch * 0.08) + (hash(pair) % 10) * 0.02

            monitor.update_pair_progress(
                pair=pair,
                status='training',
                progress=progress,
                current_epoch=epoch,
                loss=max(0.1, loss),
                accuracy=min(0.95, accuracy)
            )

        time.sleep(2)  # Show progress for 2 seconds

    # Mark pairs as completed
    print("\n✅ Marking pairs as completed...")
    for pair in pairs:
        monitor.update_pair_progress(
            pair=pair,
            status='completed',
            progress=1.0,
            current_epoch=10,
            loss=0.15,
            accuracy=0.85
        )

    # Keep display active for viewing
    print("📈 Display active - check the monitor interface above!")
    print("Press Ctrl+C to exit...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n⏹️  Test completed!")

    monitor.stop_monitoring()

if __name__ == "__main__":
    test_monitor()