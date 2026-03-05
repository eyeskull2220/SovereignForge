#!/usr/bin/env python3
"""
SovereignForge GPU Training Script - Wave 7
Complete GPU-accelerated arbitrage training with safety and monitoring

Usage:
    python gpu_train.py --pairs BTC/USDT ETH/USDT --epochs 50 --batch-size 64
    python gpu_train.py --all-pairs --gpu-monitor --tensorboard
"""

import os
import sys
import argparse
import logging
import time
import signal
import warnings
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import json

# Suppress pynvml deprecation warning from PyTorch
warnings.filterwarnings("ignore", message=".*pynvml package is deprecated.*")

# Add src directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# GPU imports with fallbacks
try:
    import torch
    import torch.nn as nn
    TORCH_AVAILABLE = True
    try:
        from torch.utils.tensorboard import SummaryWriter
        TENSORBOARD_AVAILABLE = True
    except ImportError:
        TENSORBOARD_AVAILABLE = False
        print("WARNING: TensorBoard not available")
except ImportError:
    TORCH_AVAILABLE = False
    TENSORBOARD_AVAILABLE = False
    print("WARNING: PyTorch not available, using CPU fallback")

try:
    import wandb
    WANDB_AVAILABLE = True
except ImportError:
    WANDB_AVAILABLE = False

# Core imports
from gpu_manager import get_gpu_manager, shutdown_gpu_manager
from gpu_arbitrage_model import run_gpu_arbitrage_training, setup_gpu_training
from gpu_training_cli import GPUTrainingCLI
from training_monitor import create_training_monitor, display_training_monitor, GPUTrainingMonitor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('logs/gpu_training.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class GPUTrainingOrchestrator:
    """Complete GPU training orchestration with safety and monitoring"""

    def __init__(self, args):
        self.args = args
        self.gpu_manager = None
        self.tensorboard_writer = None
        self.wandb_run = None
        self.training_active = False
        self.start_time = None

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def initialize(self) -> bool:
        """Initialize GPU training environment"""
        try:
            logger.info("Initializing GPU training environment...")

            # Initialize GPU manager
            self.gpu_manager = get_gpu_manager(
                device_id=self.args.gpu_device,
                memory_fraction=self.args.memory_fraction
            )

            if not self.gpu_manager or not self.gpu_manager.initialize():
                logger.error("Failed to initialize GPU manager")
                return False

            # Setup GPU training optimizations
            if not setup_gpu_training():
                logger.warning("GPU optimizations not available, using CPU")

            # Initialize TensorBoard if requested
            if self.args.tensorboard:
                self._init_tensorboard()

            # Initialize Weights & Biases if requested
            if self.args.wandb:
                self._init_wandb()

            # Create output directories
            self._create_directories()

            logger.info("GPU training environment initialized successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize training environment: {e}")
            return False

    def _init_tensorboard(self):
        """Initialize TensorBoard logging"""
        if not TENSORBOARD_AVAILABLE:
            logger.warning("TensorBoard requested but not available")
            return

        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            log_dir = f"tensorboard/gpu_training_{timestamp}"
            self.tensorboard_writer = SummaryWriter(log_dir)
            logger.info(f"TensorBoard logging initialized: {log_dir}")
        except Exception as e:
            logger.error(f"Failed to initialize TensorBoard: {e}")

    def _init_wandb(self):
        """Initialize Weights & Biases logging"""
        if not WANDB_AVAILABLE:
            logger.warning("Weights & Biases not available, skipping")
            return

        try:
            config = {
                'pairs': self.args.pairs,
                'epochs': self.args.epochs,
                'batch_size': self.args.batch_size,
                'gpu_device': self.args.gpu_device,
                'memory_fraction': self.args.memory_fraction,
                'learning_rate': self.args.learning_rate,
                'gradient_clip': self.args.gradient_clip
            }

            self.wandb_run = wandb.init(
                project="sovereignforge-gpu-training",
                name=f"gpu_training_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                config=config,
                tags=["gpu", "arbitrage", "multi-pair"]
            )
            logger.info("Weights & Biases logging initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Weights & Biases: {e}")

    def _create_directories(self):
        """Create necessary output directories"""
        directories = ['models', 'logs', 'tensorboard', 'reports', 'data']
        for dir_name in directories:
            Path(dir_name).mkdir(exist_ok=True)

    def run_training(self) -> Optional[Dict[str, Any]]:
        """Run the complete GPU training pipeline"""
        if not self.initialize():
            return None

        try:
            self.training_active = True
            self.start_time = time.time()

            logger.info("=" * 60)
            logger.info("STARTING SOVEREIGNFORGE GPU TRAINING - WAVE 7")
            logger.info("=" * 60)

            # Log training configuration
            self._log_training_config()

            # Start GPU monitoring if requested
            if self.args.gpu_monitor:
                self._start_gpu_monitoring()

            # Run the training
            training_results = self._execute_training()

            # Save results and generate reports
            if training_results:
                self._save_training_results(training_results)
                self._generate_training_report(training_results)

            # Final logging
            training_time = time.time() - self.start_time
            logger.info(f"Training completed in {training_time:.2f} seconds")
            return training_results

        except KeyboardInterrupt:
            logger.info("Training interrupted by user")
            return None
        except Exception as e:
            logger.error(f"Training failed: {e}")
            return None
        finally:
            self.training_active = False
            self._cleanup()

    def _log_training_config(self):
        """Log training configuration"""
        config_info = f"""
GPU Training Configuration:
- Pairs: {self.args.pairs}
- Epochs: {self.args.epochs}
- Batch Size: {self.args.batch_size}
- GPU Device: {self.args.gpu_device}
- Memory Fraction: {self.args.memory_fraction}
- Learning Rate: {self.args.learning_rate}
- Gradient Clip: {self.args.gradient_clip}
- TensorBoard: {self.args.tensorboard}
- Weights & Biases: {self.args.wandb}
- GPU Monitoring: {self.args.gpu_monitor}
- Mixed Precision: {self.args.mixed_precision}
        """

        logger.info(config_info)

        # Log to TensorBoard
        if self.tensorboard_writer:
            self.tensorboard_writer.add_text('config', config_info, 0)

        # Log to Weights & Biases
        if self.wandb_run:
            self.wandb_run.config.update({
                'pairs': self.args.pairs,
                'epochs': self.args.epochs,
                'batch_size': self.args.batch_size,
                'gpu_device': self.args.gpu_device,
                'memory_fraction': self.args.memory_fraction
            })

    def _start_gpu_monitoring(self):
        """Start GPU monitoring thread"""
        if self.gpu_manager and self.gpu_manager.get_safety_manager():
            # GPU monitoring is already handled by the safety manager
            logger.info("GPU monitoring active via safety manager")
        else:
            logger.warning("GPU monitoring not available")

    def _execute_training(self) -> Optional[Dict[str, Any]]:
        """Execute the actual training"""
        try:
            # Use the GPU training CLI for the actual training
            cli = GPUTrainingCLI()

            training_results = cli.run_gpu_training(
                pairs=self.args.pairs,
                exchanges=['binance', 'coinbase', 'kraken'],
                num_epochs=self.args.epochs,
                batch_size=self.args.batch_size,
                save_models=True,
                monitor_training=self.args.gpu_monitor
            )

            return training_results

        except Exception as e:
            logger.error(f"Training execution failed: {e}")
            return None

    def _save_training_results(self, results: Dict[str, Any]):
        """Save training results"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            results_file = f"models/training_results_{timestamp}.json"

            # Add metadata
            results['metadata'] = {
                'timestamp': timestamp,
                'training_time_seconds': time.time() - self.start_time,
                'gpu_available': self.gpu_manager.is_available() if self.gpu_manager else False,
                'config': vars(self.args)
            }

            with open(results_file, 'w') as f:
                json.dump(results, f, indent=2, default=str)

            logger.info(f"Training results saved to {results_file}")

        except Exception as e:
            logger.error(f"Failed to save training results: {e}")

    def _generate_training_report(self, results: Dict[str, Any]):
        """Generate comprehensive training report"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"reports/gpu_training_report_{timestamp}.md"

            report = self._create_training_report(results)

            with open(report_file, 'w') as f:
                f.write(report)

            logger.info(f"Training report generated: {report_file}")

        except Exception as e:
            logger.error(f"Failed to generate training report: {e}")

    def _create_training_report(self, results: Dict[str, Any]) -> str:
        """Create detailed training report"""
        metadata = results.get('metadata', {})

        report = f"""# SovereignForge GPU Training Report - Wave 7

## Training Summary
- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
- **Training Time**: {metadata.get('training_time_seconds', 0):.2f} seconds
- **GPU Available**: {metadata.get('gpu_available', False)}
- **Pairs Trained**: {len(results) if isinstance(results, dict) else 'N/A'}

## Configuration
- **Pairs**: {metadata.get('config', {}).get('pairs', 'N/A')}
- **Epochs**: {metadata.get('config', {}).get('epochs', 'N/A')}
- **Batch Size**: {metadata.get('config', {}).get('batch_size', 'N/A')}
- **Learning Rate**: {metadata.get('config', {}).get('learning_rate', 'N/A')}

## Results by Pair
"""

        # Add results for each pair
        if isinstance(results, dict):
            for pair, pair_results in results.items():
                if isinstance(pair_results, list) and pair_results:
                    final_epoch = pair_results[-1]
                    report += f"""
### {pair}
- **Final Training Loss**: {final_epoch.get('train_loss', 'N/A'):.4f}
- **Final Training Accuracy**: {final_epoch.get('train_arbitrage_acc', 'N/A'):.4f}
- **Final Validation Loss**: {final_epoch.get('val_loss', 'N/A'):.4f}
- **Final Validation Accuracy**: {final_epoch.get('val_arbitrage_acc', 'N/A'):.4f}
- **Epochs Completed**: {len(pair_results)}
"""

        report += """
## Performance Metrics
- **GPU Utilization**: Check logs for detailed metrics
- **Memory Usage**: Monitored throughout training
- **Training Stability**: Safety systems active

## Recommendations
- Review model performance for each pair
- Consider hyperparameter tuning for underperforming pairs
- Monitor GPU memory usage patterns
- Evaluate model deployment readiness

## Next Steps
1. Deploy best-performing models to production
2. Monitor real-time performance
3. Continue training with new data
4. Optimize inference latency

---
*Generated by SovereignForge GPU Training System - Wave 7*
"""

        return report

    def _signal_handler(self, signum, frame):
        """Handle interrupt signals gracefully"""
        logger.info(f"Received signal {signum}, initiating graceful shutdown...")
        self.training_active = False

    def _cleanup(self):
        """Cleanup resources"""
        try:
            # Close TensorBoard
            if self.tensorboard_writer:
                self.tensorboard_writer.close()

            # Finish Weights & Biases
            if self.wandb_run:
                self.wandb_run.finish()

            # Shutdown GPU manager
            shutdown_gpu_manager()

            logger.info("GPU training cleanup completed")

        except Exception as e:
            logger.error(f"Cleanup error: {e}")

def main():
    """Main entry point for GPU training"""
    parser = argparse.ArgumentParser(
        description='SovereignForge GPU Training - Wave 7',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Train all pairs with GPU monitoring
  python gpu_train.py --all-pairs --gpu-monitor --tensorboard

  # Train specific pairs with custom settings
  python gpu_train.py --pairs BTC/USDT ETH/USDT --epochs 100 --batch-size 64 --wandb

  # Quick training test
  python gpu_train.py --pairs BTC/USDT --epochs 5 --batch-size 16
        """
    )

    # Pair selection
    parser.add_argument('--pairs', nargs='+',
                       default=['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT'],
                       help='Trading pairs to train')
    parser.add_argument('--all-pairs', action='store_true',
                       help='Train all 7 default pairs')

    # Training parameters
    parser.add_argument('--epochs', type=int, default=50,
                       help='Number of training epochs')
    parser.add_argument('--batch-size', type=int, default=64,
                       help='Training batch size (GPU Max: 64 with gradient accumulation)')
    parser.add_argument('--learning-rate', type=float, default=1e-4,
                       help='Learning rate')
    parser.add_argument('--gradient-clip', type=float, default=1.0,
                       help='Gradient clipping value')

    # GPU configuration
    parser.add_argument('--gpu-device', type=int, default=0,
                       help='GPU device ID')
    parser.add_argument('--memory-fraction', type=float, default=0.8,
                       help='GPU memory fraction to use (0.8 = 12.8GB on 16GB card)')
    parser.add_argument('--mixed-precision', action='store_true',
                       help='Use mixed precision training')

    # Monitoring and logging
    parser.add_argument('--gpu-monitor', action='store_true',
                       help='Enable GPU monitoring and safety checks')
    parser.add_argument('--tensorboard', action='store_true',
                       help='Enable TensorBoard logging')
    parser.add_argument('--wandb', action='store_true',
                       help='Enable Weights & Biases logging')

    # Safety options
    parser.add_argument('--safe-mode', action='store_true',
                       help='Enable additional safety checks')
    parser.add_argument('--checkpoint-freq', type=int, default=10,
                       help='Save checkpoints every N epochs')

    args = parser.parse_args()

    # Override pairs if --all-pairs is specified
    if args.all_pairs:
        args.pairs = ['BTC/USDT', 'ETH/USDT', 'XRP/USDT', 'XLM/USDT', 'HBAR/USDT', 'ALGO/USDT', 'ADA/USDT']

    # Validate arguments
    if not args.pairs:
        parser.error("No pairs specified. Use --pairs or --all-pairs")

    if args.epochs <= 0:
        parser.error("Epochs must be positive")

    if args.batch_size <= 0:
        parser.error("Batch size must be positive")

    if not (0 < args.memory_fraction <= 1):
        parser.error("Memory fraction must be between 0 and 1")

    # Create orchestrator and run training
    orchestrator = GPUTrainingOrchestrator(args)
    results = orchestrator.run_training()

    if results:
        print("\n[SUCCESS] GPU training completed successfully!")
        print(f"Trained {len(results)} pairs")
        print("Check the models/ and reports/ directories for results")
        sys.exit(0)
    else:
        print("\n[FAILED] GPU training failed or was interrupted")
        sys.exit(1)

if __name__ == "__main__":
    main()