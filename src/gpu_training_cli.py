# SovereignForge GPU Training CLI - Wave 7
# Command-line interface for GPU-accelerated arbitrage training

import argparse
import asyncio
import logging
import os
import sys
import time
from typing import Dict, List, Any, Optional
import json
from datetime import datetime

# Add src directory to path
sys.path.insert(0, os.path.dirname(__file__))

from gpu_manager import get_gpu_manager, shutdown_gpu_manager
from gpu_arbitrage_model import run_gpu_arbitrage_training, setup_gpu_training
from training_monitor import create_training_monitor, display_training_monitor
from monitoring import MetricsCollector

logger = logging.getLogger(__name__)

class GPUTrainingCLI:
    """CLI for GPU-accelerated arbitrage training"""

    def __init__(self):
        self.gpu_manager = None
        self.metrics_collector = MetricsCollector()
        self.training_active = False

    def initialize(self):
        """Initialize GPU training environment"""
        try:
            # Initialize GPU manager
            self.gpu_manager = get_gpu_manager()

            if self.gpu_manager and self.gpu_manager.is_available():
                logger.info("GPU training environment initialized successfully")
                return True
            else:
                logger.warning("GPU not available, using CPU training")
                return True

        except Exception as e:
            logger.error(f"Failed to initialize GPU training environment: {e}")
            return False

    def run_gpu_training(self, pairs: List[str] = None, exchanges: List[str] = None,
                        num_epochs: int = 50, batch_size: int = 32,
                        save_models: bool = True, monitor_training: bool = True):
        """Run GPU-accelerated arbitrage training"""

        if not self.initialize():
            logger.error("Failed to initialize training environment")
            return None

        logger.info("Starting GPU-accelerated arbitrage training")
        logger.info(f"Pairs: {pairs or 'default 7 pairs'}")
        logger.info(f"Exchanges: {exchanges or 'default 3 exchanges'}")
        logger.info(f"Epochs: {num_epochs}, Batch size: {batch_size}")

        # GPU status
        if self.gpu_manager and self.gpu_manager.is_available():
            gpu_info = self.gpu_manager.get_memory_info()
            logger.info(f"GPU Memory - Allocated: {gpu_info.get('allocated_mb', 0):.1f}MB, "
                       f"Free: {gpu_info.get('free_mb', 0):.1f}MB")
        else:
            logger.info("Running on CPU")

        # Start training monitoring
        if monitor_training:
            # Note: Async monitoring disabled for CLI compatibility
            logger.info("Training monitoring enabled (basic)")

        try:
            self.training_active = True

            # Run training
            start_time = time.time()
            training_history = run_gpu_arbitrage_training(
                pairs=pairs,
                exchanges=exchanges,
                num_epochs=num_epochs,
                batch_size=batch_size
            )

            training_time = time.time() - start_time

            # Save training results
            if save_models:
                self._save_training_results(training_history, training_time)

            logger.info(f"Training completed in {training_time:.2f} seconds")
            return training_history

        except KeyboardInterrupt:
            logger.info("Training interrupted by user")
            return None
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return None
        finally:
            self.training_active = False
            shutdown_gpu_manager()

    async def _monitor_training(self):
        """Monitor training progress and GPU status"""

        while self.training_active:
            try:
                if self.gpu_manager and self.gpu_manager.is_available():
                    gpu_info = self.gpu_manager.get_memory_info()

                    # Record GPU metrics
                    await self.metrics_collector.record_metric(
                        'gpu_memory_allocated_mb',
                        gpu_info.get('allocated_mb', 0),
                        {'component': 'training'}
                    )

                    await self.metrics_collector.record_metric(
                        'gpu_utilization_pct',
                        gpu_info.get('utilization_pct', 0),
                        {'component': 'training'}
                    )

                    await self.metrics_collector.record_metric(
                        'gpu_temperature_c',
                        gpu_info.get('temperature_c', 0),
                        {'component': 'training'}
                    )

                await asyncio.sleep(10)  # Update every 10 seconds

            except Exception as e:
                logger.error(f"Training monitoring error: {e}")
                await asyncio.sleep(30)  # Wait longer on error

    def _save_training_results(self, training_history: Dict[str, List[Dict[str, float]]],
                              training_time: float):
        """Save training results and statistics"""

        try:
            results_dir = "E:\\Users\\Gino\\Downloads\\SovereignForge\\models\\training_results"
            os.makedirs(results_dir, exist_ok=True)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

            # Save detailed results
            results_file = os.path.join(results_dir, f"training_results_{timestamp}.json")
            with open(results_file, 'w') as f:
                json.dump({
                    'training_history': training_history,
                    'training_time_seconds': training_time,
                    'timestamp': timestamp,
                    'gpu_available': self.gpu_manager.is_available() if self.gpu_manager else False,
                    'pairs_trained': list(training_history.keys())
                }, f, indent=2, default=str)

            # Save summary statistics
            summary = self._calculate_training_summary(training_history, training_time)
            summary_file = os.path.join(results_dir, f"training_summary_{timestamp}.json")
            with open(summary_file, 'w') as f:
                json.dump(summary, f, indent=2, default=str)

            logger.info(f"Training results saved to {results_dir}")

        except Exception as e:
            logger.error(f"Failed to save training results: {e}")

    def _calculate_training_summary(self, training_history: Dict[str, List[Dict[str, float]]],
                                   training_time: float) -> Dict[str, Any]:
        """Calculate training summary statistics"""

        summary = {
            'total_training_time_seconds': training_time,
            'total_training_time_hours': training_time / 3600,
            'pairs_trained': len(training_history),
            'total_epochs': 0,
            'pair_summaries': {}
        }

        for pair, history in training_history.items():
            if not history:
                continue

            summary['total_epochs'] = max(summary['total_epochs'], len(history))

            # Calculate pair statistics
            final_epoch = history[-1]
            best_epoch = max(history, key=lambda x: x.get('val_arbitrage_acc', 0))

            pair_summary = {
                'epochs_completed': len(history),
                'final_train_loss': final_epoch.get('train_loss', 0),
                'final_train_accuracy': final_epoch.get('train_arbitrage_acc', 0),
                'final_val_loss': final_epoch.get('val_loss', 0),
                'final_val_accuracy': final_epoch.get('val_arbitrage_acc', 0),
                'best_val_accuracy': best_epoch.get('val_arbitrage_acc', 0),
                'best_epoch': history.index(best_epoch) + 1,
                'training_curve': {
                    'train_loss': [epoch.get('train_loss', 0) for epoch in history],
                    'val_loss': [epoch.get('val_loss', 0) for epoch in history],
                    'train_accuracy': [epoch.get('train_arbitrage_acc', 0) for epoch in history],
                    'val_accuracy': [epoch.get('val_arbitrage_acc', 0) for epoch in history]
                }
            }

            summary['pair_summaries'][pair] = pair_summary

        # Calculate overall statistics
        if summary['pair_summaries']:
            accuracies = [pair_data['final_val_accuracy']
                         for pair_data in summary['pair_summaries'].values()]
            summary['overall_average_accuracy'] = sum(accuracies) / len(accuracies)
            summary['best_pair_accuracy'] = max(accuracies)
            summary['worst_pair_accuracy'] = min(accuracies)

        return summary

    def show_gpu_status(self):
        """Display current GPU status"""

        print("GPU Training Status")
        print("=" * 40)

        if not self.gpu_manager:
            print("GPU manager not initialized")
            return

        if self.gpu_manager.is_available():
            gpu_info = self.gpu_manager.get_memory_info()

            print(f"GPU Device: {torch.cuda.get_device_name(self.gpu_manager.get_device()) if torch.cuda.is_available() else 'Unknown'}")
            print(f"CUDA Available: Yes")
            print(f"Memory Allocated: {gpu_info.get('allocated_mb', 0):.1f} MB")
            print(f"Memory Reserved: {gpu_info.get('reserved_mb', 0):.1f} MB")
            print(f"Memory Free: {gpu_info.get('free_mb', 0):.1f} MB")
            print(f"Memory Total: {gpu_info.get('total_mb', 0):.1f} MB")
            print(f"GPU Utilization: {gpu_info.get('utilization_pct', 0):.1f}%")
            print(f"Temperature: {gpu_info.get('temperature_c', 0):.1f}°C")
            print(f"Power Usage: {gpu_info.get('power_watts', 0):.1f} W")

            # Safety status
            safety_manager = self.gpu_manager.get_safety_manager()
            if safety_manager:
                print(f"Safety Status: {'Safe' if safety_manager.is_safe() else 'Warning'}")
                print(f"Monitoring: {'Active' if safety_manager.monitoring_active else 'Inactive'}")

        else:
            print("GPU not available - using CPU")

        print(f"Training Active: {self.training_active}")

    def list_saved_models(self):
        """List saved model checkpoints"""

        models_dir = "E:\\Users\\Gino\\Downloads\\SovereignForge\\models"
        if not os.path.exists(models_dir):
            print("No models directory found")
            return

        print("Saved Model Checkpoints")
        print("=" * 40)

        model_files = [f for f in os.listdir(models_dir) if f.endswith('.pth')]

        if not model_files:
            print("No saved models found")
            return

        for model_file in sorted(model_files):
            filepath = os.path.join(models_dir, model_file)
            file_size = os.path.getsize(filepath) / (1024 * 1024)  # MB
            modified_time = datetime.fromtimestamp(os.path.getmtime(filepath))

            print(f"{model_file}")
            print(f"  Size: {file_size:.1f} MB")
            print(f"  Modified: {modified_time.strftime('%Y-%m-%d %H:%M:%S')}")
            print()

def main():
    """Main CLI entry point for GPU training"""

    parser = argparse.ArgumentParser(
        description='SovereignForge GPU Training CLI - Wave 7',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train all default pairs
  python gpu_training_cli.py train

  # Train specific pairs with custom settings
  python gpu_training_cli.py train --pairs BTC/USDT ETH/USDT --epochs 100 --batch-size 64

  # Check GPU status
  python gpu_training_cli.py status

  # List saved models
  python gpu_training_cli.py models
        """
    )

    parser.add_argument('command', choices=['train', 'status', 'models'],
                       help='Command to run')
    parser.add_argument('--pairs', nargs='+',
                       default=['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT'],
                       help='Trading pairs to train (default: all 7 pairs)')
    parser.add_argument('--exchanges', nargs='+',
                       default=['binance', 'coinbase', 'kraken'],
                       help='Exchanges to include (default: binance coinbase kraken)')
    parser.add_argument('--epochs', type=int, default=50,
                       help='Number of training epochs (default: 50)')
    parser.add_argument('--batch-size', type=int, default=32,
                       help='Training batch size (default: 32)')
    parser.add_argument('--no-save', action='store_true',
                       help='Do not save trained models')
    parser.add_argument('--no-monitor', action='store_true',
                       help='Disable training monitoring')

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )

    # Initialize CLI
    cli = GPUTrainingCLI()

    # Execute command
    if args.command == 'train':
        # Run GPU training
        logger.info("Starting GPU arbitrage training...")

        training_results = cli.run_gpu_training(
            pairs=args.pairs,
            exchanges=args.exchanges,
            num_epochs=args.epochs,
            batch_size=args.batch_size,
            save_models=not args.no_save,
            monitor_training=not args.no_monitor
        )

        if training_results:
            print("\nTraining completed successfully!")
            print(f"Trained {len(training_results)} pairs")
            print("Check the models directory for saved checkpoints")
        else:
            print("\nTraining failed or was interrupted")
            sys.exit(1)

    elif args.command == 'status':
        cli.show_gpu_status()

    elif args.command == 'models':
        cli.list_saved_models()

if __name__ == "__main__":
    main()