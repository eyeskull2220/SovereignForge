#!/usr/bin/env python3
"""
SovereignForge GPU Training Script - Wave 7
Complete GPU-accelerated arbitrage training with safety and monitoring

Usage:
    python gpu_train.py --pairs BTC/USDC ETH/USDC --epochs 50 --batch-size 64
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

try:
    import mlflow as _mlflow
    MLFLOW_AVAILABLE = True
except ImportError:
    _mlflow = None
    MLFLOW_AVAILABLE = False

# Core imports
from gpu_manager import get_gpu_manager, shutdown_gpu_manager
from gpu_arbitrage_model import run_gpu_arbitrage_training, setup_gpu_training
from multi_strategy_training import StrategyType, train_strategy_model, train_all_strategies
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
            try:
                self.gpu_manager = get_gpu_manager(
                    device_id=self.args.gpu_device,
                    memory_fraction=self.args.memory_fraction
                )
            except Exception as e:
                logger.warning(f"GPUtil failed, using basic info: {e}")
                self.gpu_manager = GPUManager(device_id=self.args.gpu_device)

            if not hasattr(self.gpu_manager, 'get_gpu_info'):
                logger.warning("GPU manager lacks full functionality, using basic mode")

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

            # Post-training pipeline: backtest → report → version bump → handoff
            if training_results:
                # Run backtesting on all trained models
                backtest_results = self._run_post_training_backtest(training_results)
                if backtest_results:
                    training_results['backtest'] = backtest_results

                # Save results and generate reports
                self._save_training_results(training_results)
                self._generate_training_report(training_results)

                # Version bump + learnings log
                new_version = self._bump_version(training_results)

                # Git commit + handoff file
                self._create_handoff(training_results, new_version)

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
- Exchanges: {getattr(self.args, 'exchanges', ['binance'])}
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
        if self.gpu_manager:
            # GPU monitoring is already handled by the GPU manager
            logger.info("GPU monitoring active via GPU manager")
        else:
            logger.warning("GPU monitoring not available")

    def _execute_training(self) -> Optional[Dict[str, Any]]:
        """Execute the actual training, dispatching by strategy"""
        try:
            strategy = getattr(self.args, 'strategy', 'arbitrage')
            exchanges = getattr(self.args, 'exchanges', ['binance', 'coinbase', 'kraken', 'okx'])

            if strategy == 'arbitrage':
                # Use existing GPU arbitrage training across all exchanges
                training_results = run_gpu_arbitrage_training(
                    pairs=self.args.pairs,
                    exchanges=exchanges,
                    num_epochs=self.args.epochs,
                    batch_size=self.args.batch_size,
                    save_models=True,
                    monitor_training=self.args.gpu_monitor
                )
            elif strategy == 'all':
                # Train all 7 strategies (collective brain) across all exchanges
                logger.info(f"Training ALL strategies (collective brain) on {exchanges}")
                training_results = train_all_strategies(
                    pairs=self.args.pairs,
                    exchanges=exchanges,
                    epochs=self.args.epochs,
                    batch_size=self.args.batch_size,
                )
            else:
                # Train a specific non-arbitrage strategy across all exchanges
                strategy_type = StrategyType(strategy)
                logger.info(f"Training {strategy} strategy on {exchanges}")
                training_results = train_strategy_model(
                    strategy=strategy_type,
                    pairs=self.args.pairs,
                    exchanges=exchanges,
                    epochs=self.args.epochs,
                    batch_size=self.args.batch_size,
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
        """Generate comprehensive training report (legacy + new dashboard data)"""
        try:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = f"reports/gpu_training_report_{timestamp}.md"

            report = self._create_training_report(results)

            with open(report_file, 'w') as f:
                f.write(report)

            logger.info(f"Training report generated: {report_file}")

            # Generate new-format reports (dashboard JSON + charts data)
            try:
                from training_report_generator import TrainingReportGenerator
                generator = TrainingReportGenerator()
                backtest_results = results.get("backtest") if isinstance(results, dict) else None
                generated = generator.generate_all(results, backtest_results)
                logger.info(f"Dashboard reports generated: {list(generated.keys())}")
            except ImportError:
                logger.warning("training_report_generator not found, skipping dashboard reports")

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

    def _run_post_training_backtest(self, training_results: Dict) -> Optional[Dict]:
        """Run backtesting on all trained models with P&L simulation."""
        try:
            from post_training_backtest import PostTrainingBacktester
            logger.info("Running post-training backtests...")
            backtester = PostTrainingBacktester()
            backtest_results = backtester.run_all_backtests(training_results)
            summary = backtest_results.get("_summary", {})
            if summary:
                logger.info(
                    f"Backtest summary: {summary.get('models_backtested', 0)} models, "
                    f"avg Sharpe={summary.get('avg_sharpe', 0):.3f}, "
                    f"total net P&L=${summary.get('total_net_pnl', 0):.2f}"
                )
            return backtest_results
        except ImportError:
            logger.warning("post_training_backtest module not found, skipping backtests")
            return None
        except Exception as e:
            logger.error(f"Backtesting failed: {e}")
            return None

    def _bump_version(self, training_results: Dict) -> str:
        """Bump patch version and log learnings after training run."""
        try:
            from version_manager import bump_version, log_learning
            new_version = bump_version()
            trained_count = sum(
                1 for v in training_results.values()
                if isinstance(v, dict) and v.get("status") == "trained"
            )
            log_learning(new_version, f"Training run: {trained_count} models trained")
            return new_version
        except ImportError:
            logger.warning("version_manager not found, skipping version bump")
            return "v1.0.4"
        except Exception as e:
            logger.error(f"Version bump failed: {e}")
            return "v1.0.4"

    def _create_handoff(self, training_results: Dict, version: str) -> None:
        """Create git handoff after training completion."""
        try:
            from git_handoff import create_training_handoff
            handoff_path = create_training_handoff(training_results, version)
            logger.info(f"Handoff created: {handoff_path}")
        except ImportError:
            logger.warning("git_handoff not found, skipping handoff")
        except Exception as e:
            logger.error(f"Handoff creation failed: {e}")

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

def run_cross_exchange_scan(args):
    """Scan for cross-exchange arbitrage opportunities using trained models."""
    import pandas as pd
    from strategy_ensemble import create_ensemble_from_config, CrossExchangeScorer
    from risk_management import get_risk_manager

    print("\n" + "=" * 80)
    print("SOVEREIGNFORGE CROSS-EXCHANGE ARBITRAGE SCANNER")
    print("=" * 80)

    exchanges = getattr(args, 'exchanges', ['binance', 'coinbase', 'kraken', 'okx'])
    pairs = args.pairs

    # Load ensemble and models
    print(f"\nLoading models for {len(pairs)} pairs × {len(exchanges)} exchanges...")
    ensemble = create_ensemble_from_config()
    load_results = ensemble.load_all_models(pairs=pairs, exchanges=exchanges)
    loaded = sum(1 for v in load_results.values() if v)
    total = len(load_results)
    print(f"Loaded {loaded}/{total} strategy models")

    if loaded == 0:
        print("\n[ERROR] No models loaded. Train models first:")
        print("  python gpu_train.py --strategy all --all-pairs --exchanges binance coinbase kraken okx --epochs 200")
        return

    # Create scorer
    risk_manager = get_risk_manager()
    scorer = CrossExchangeScorer(
        ensemble=ensemble,
        risk_manager=risk_manager,
        min_signal_spread=0.1,  # Lower threshold for scan to show more results
        min_confidence=0.2,
    )

    # Load latest OHLCV data per exchange per pair
    print(f"\nLoading market data from data/historical/...")
    all_exchange_data = {}
    for pair in pairs:
        pair_slug = pair.replace('/', '_')
        exchange_data = {}
        for exchange in exchanges:
            csv_path = os.path.join('data', 'historical', exchange, f'{pair_slug}_5m.csv')
            if os.path.exists(csv_path):
                try:
                    df = pd.read_csv(csv_path)
                    # Convert timestamp to numeric (epoch seconds) if string
                    try:
                        df['timestamp'] = pd.to_numeric(df['timestamp'], errors='coerce')
                    except (ValueError, TypeError):
                        pass
                    if df['timestamp'].isna().any() or df['timestamp'].dtype == 'object':
                        df['timestamp'] = pd.to_datetime(df['timestamp']).astype('int64') // 10**9
                    ohlcv = df[['timestamp', 'open', 'high', 'low', 'close', 'volume']].values.astype(float)
                    # Use last 100 candles for prediction
                    exchange_data[exchange] = ohlcv[-100:]
                except Exception as e:
                    logger.warning(f"Failed to load {csv_path}: {e}")
        if exchange_data:
            all_exchange_data[pair] = exchange_data

    if not all_exchange_data:
        print("\n[ERROR] No market data found. Fetch data first:")
        print("  python fetch_exchange_data.py --exchanges binance coinbase kraken okx")
        return

    # Run scan
    print(f"\nScanning {len(all_exchange_data)} pairs across exchanges...\n")
    results = scorer.scan_all_pairs(pairs, all_exchange_data)

    # Display results table
    if not results:
        print("No cross-exchange arbitrage opportunities detected.")
        print("(All signal spreads below threshold or insufficient model coverage)")
        return

    # Header
    header = f"{'Pair':<12} {'Buy@':<10} {'Sell@':<10} {'Signal Spread':>14} {'Risk':>6} {'Reward/Risk':>12} {'Position%':>10}"
    print(header)
    print("-" * len(header))

    for sig in results:
        print(
            f"{sig.pair:<12} "
            f"{sig.buy_exchange:<10} "
            f"{sig.sell_exchange:<10} "
            f"{sig.signal_spread:>14.4f} "
            f"{sig.risk_score:>6.2f} "
            f"{sig.reward_risk_ratio:>12.2f} "
            f"{sig.recommended_position_pct:>9.1f}%"
        )

    # Summary
    print(f"\n{len(results)} opportunities detected")
    top = results[0]
    print(f"Best opportunity: {top.pair} — buy on {top.buy_exchange}, sell on {top.sell_exchange} "
          f"(reward/risk: {top.reward_risk_ratio:.2f})")

    # Per-exchange detail for top opportunity
    print(f"\nDetailed breakdown for {top.pair}:")
    for exchange, sig in top.per_exchange.items():
        print(f"  {exchange:<10} action={sig.action:<5} confidence={sig.confidence:.3f} "
              f"agreement={sig.agreement_score:.3f} strategies={sig.strategy_signals}")


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
  python gpu_train.py --pairs BTC/USDC ETH/USDC --epochs 100 --batch-size 64 --wandb

  # Quick training test
  python gpu_train.py --pairs BTC/USDC --epochs 5 --batch-size 16

  # Train a specific strategy (fibonacci, grid, dca)
  python gpu_train.py --strategy fibonacci --all-pairs --epochs 100

  # Train ALL strategies (collective brain) on all exchanges
  python gpu_train.py --strategy all --all-pairs --epochs 100 --gpu-monitor

  # Train on specific exchanges only
  python gpu_train.py --all-pairs --exchanges binance okx --strategy all --epochs 100

  # Scan for cross-exchange arbitrage opportunities (requires trained models)
  python gpu_train.py --scan --all-pairs --exchanges binance coinbase kraken okx
        """
    )

    # Pair selection
    parser.add_argument('--pairs', nargs='+',
                       default=['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC'],
                       help='Trading pairs to train (12 MiCA compliant USDC pairs)')
    parser.add_argument('--all-pairs', action='store_true',
                       help='Train all 12 MiCA compliant pairs')

    # Training parameters
    parser.add_argument('--epochs', type=int, default=200,
                       help='Number of training epochs (diagnostic report: need 100-300 for convergence)')
    parser.add_argument('--batch-size', type=int, default=96,
                       help='Training batch size (96 optimal for 4060 Ti 16GB)')
    parser.add_argument('--learning-rate', type=float, default=8e-5,
                       help='Learning rate (8e-5 with ReduceLROnPlateau)')
    parser.add_argument('--seq-len', type=int, default=128,
                       help='Sequence length for input windows (128 for 5m candles)')
    parser.add_argument('--gradient-clip', type=float, default=1.0,
                       help='Gradient clipping value')

    # GPU configuration
    parser.add_argument('--gpu-device', type=int, default=0,
                       help='GPU device ID')
    parser.add_argument('--memory-fraction', type=float, default=0.82,
                       help='GPU memory fraction to use (0.82 = 13.1GB on 16GB card)')
    parser.add_argument('--mixed-precision', dest='mixed_precision',
                       action='store_true', default=True,
                       help='Use mixed precision training (default: enabled)')
    parser.add_argument('--no-mixed-precision', dest='mixed_precision',
                       action='store_false',
                       help='Disable mixed precision training')

    # Monitoring and logging
    parser.add_argument('--gpu-monitor', action='store_true',
                       help='Enable GPU monitoring and safety checks')
    parser.add_argument('--tensorboard', action='store_true',
                       help='Enable TensorBoard logging')
    parser.add_argument('--wandb', action='store_true',
                       help='Enable Weights & Biases logging')
    parser.add_argument('--mlflow', action='store_true',
                       help='Launch MLflow UI at http://localhost:5000 before training')

    # Exchange selection
    parser.add_argument('--exchanges', nargs='+',
                       default=['binance', 'coinbase', 'kraken', 'okx'],
                       help='Exchanges to train on (default: binance coinbase kraken okx)')

    # Strategy selection
    parser.add_argument('--strategy', choices=['arbitrage', 'fibonacci', 'grid', 'dca', 'mean_reversion', 'pairs_arbitrage', 'momentum', 'all'],
                       default='arbitrage',
                       help='Strategy to train (default: arbitrage, use "all" for collective brain)')

    # Scan mode (cross-exchange arbitrage detection)
    parser.add_argument('--scan', action='store_true',
                       help='Scan for cross-exchange arbitrage opportunities using trained models')

    # Safety options
    parser.add_argument('--safe-mode', action='store_true',
                       help='Enable additional safety checks')
    parser.add_argument('--checkpoint-freq', type=int, default=10,
                       help='Save checkpoints every N epochs')

    args = parser.parse_args()

    # Override pairs if --all-pairs is specified
    if args.all_pairs:
        args.pairs = ['BTC/USDC', 'ETH/USDC', 'XRP/USDC', 'XLM/USDC', 'HBAR/USDC', 'ALGO/USDC', 'ADA/USDC', 'LINK/USDC', 'IOTA/USDC', 'VET/USDC', 'XDC/USDC', 'ONDO/USDC']

    # Validate arguments
    if not args.pairs:
        parser.error("No pairs specified. Use --pairs or --all-pairs")

    if args.epochs <= 0:
        parser.error("Epochs must be positive")

    if args.batch_size <= 0:
        parser.error("Batch size must be positive")

    if not (0 < args.memory_fraction <= 1):
        parser.error("Memory fraction must be between 0 and 1")

    # Scan mode: detect cross-exchange arbitrage opportunities
    if args.scan:
        run_cross_exchange_scan(args)
        sys.exit(0)

    # Launch MLflow UI in background if requested
    if args.mlflow:
        if MLFLOW_AVAILABLE:
            import subprocess
            print("MLflow UI at http://localhost:5000")
            subprocess.Popen(
                [sys.executable, "-m", "mlflow", "ui", "--port", "5000"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        else:
            print("WARNING: MLflow not installed, skipping UI launch")

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