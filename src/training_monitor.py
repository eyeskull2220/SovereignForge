#!/usr/bin/env python3
"""
SovereignForge - Training Monitor
Real-time monitoring and visualization for GPU model training

This module provides:
- Real-time training metrics collection
- GPU utilization monitoring
- Loss curve visualization
- Training progress tracking
- Alert system for training issues
"""

import os
import sys
import logging
import threading
import time
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass
from datetime import datetime
import json

# Optional imports with fallbacks
try:
    import psutil
    has_psutil = True
except ImportError:
    psutil = None  # type: ignore
    has_psutil = False

try:
    import GPUtil
    has_gputil = True
except ImportError:
    GPUtil = None  # type: ignore
    has_gputil = False

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logger = logging.getLogger(__name__)

@dataclass
class TrainingMetrics:
    """Training metrics snapshot"""
    timestamp: datetime
    epoch: int
    step: int
    loss: float
    learning_rate: float
    gpu_utilization: float
    gpu_memory_used: float
    gpu_memory_total: float
    cpu_percent: float
    ram_used_gb: float
    ram_total_gb: float

@dataclass
class TrainingAlert:
    """Training alert information"""
    alert_type: str
    severity: str  # 'info', 'warning', 'error', 'critical'
    message: str
    timestamp: datetime
    metrics: Optional[Dict[str, Any]] = None

class TrainingMonitor:
    """
    Real-time training monitoring and alerting system
    """

    def __init__(self,
                 log_dir: str = "./training_logs",
                 alert_callbacks: Optional[List[Callable]] = None,
                 gpu_monitoring: bool = True):
        self.log_dir = log_dir
        self.alert_callbacks = alert_callbacks or []
        self.gpu_monitoring = gpu_monitoring

        # Metrics storage
        self.metrics_history: List[TrainingMetrics] = []
        self.alerts_history: List[TrainingAlert] = []

        # Monitoring state
        self.monitoring_active = False
        self.monitoring_thread: Optional[threading.Thread] = None

        # Training state
        self.current_epoch = 0
        self.current_step = 0
        self.start_time = None

        # Thresholds for alerts
        self.alert_thresholds = {
            'max_loss': 10.0,
            'min_lr': 1e-8,
            'max_gpu_memory_percent': 95.0,
            'max_cpu_percent': 90.0,
            'max_ram_percent': 90.0
        }

        # Setup logging
        os.makedirs(log_dir, exist_ok=True)
        self._setup_monitoring_logger()

        logger.info("TrainingMonitor initialized")

    def _setup_monitoring_logger(self):
        """Setup dedicated monitoring logger"""
        self.monitor_logger = logging.getLogger('training_monitor')
        self.monitor_logger.setLevel(logging.INFO)

        # File handler for metrics
        metrics_handler = logging.FileHandler(os.path.join(self.log_dir, 'training_metrics.log'))
        metrics_handler.setFormatter(logging.Formatter(
            '%(asctime)s - METRICS - %(message)s'
        ))
        self.monitor_logger.addHandler(metrics_handler)

        # File handler for alerts
        alerts_handler = logging.FileHandler(os.path.join(self.log_dir, 'training_alerts.log'))
        alerts_handler.setFormatter(logging.Formatter(
            '%(asctime)s - ALERT - %(levelname)s - %(message)s'
        ))
        self.monitor_logger.addHandler(alerts_handler)

        self.monitor_logger.propagate = False

    def start_monitoring(self):
        """Start the monitoring system"""
        if self.monitoring_thread is not None:
            logger.warning("Monitoring already active")
            return

        self.monitoring_active = True
        self.start_time = datetime.now()

        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="training-monitor",
            daemon=True
        )
        self.monitoring_thread.start()

        logger.info("Training monitoring started")

    def stop_monitoring(self):
        """Stop the monitoring system"""
        self.monitoring_active = False

        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)

        # Save final metrics
        self._save_metrics_summary()

        logger.info("Training monitoring stopped")

    def log_metrics(self,
                   epoch: int,
                   step: int,
                   loss: float,
                   learning_rate: float,
                   additional_metrics: Optional[Dict[str, Any]] = None):
        """Log training metrics"""
        # Get system metrics
        system_metrics = self._get_system_metrics()

        # Create metrics snapshot
        metrics = TrainingMetrics(
            timestamp=datetime.now(),
            epoch=epoch,
            step=step,
            loss=loss,
            learning_rate=learning_rate,
            gpu_utilization=system_metrics.get('gpu_utilization', 0.0),
            gpu_memory_used=system_metrics.get('gpu_memory_used', 0.0),
            gpu_memory_total=system_metrics.get('gpu_memory_total', 0.0),
            cpu_percent=system_metrics.get('cpu_percent', 0.0),
            ram_used_gb=system_metrics.get('ram_used_gb', 0.0),
            ram_total_gb=system_metrics.get('ram_total_gb', 0.0)
        )

        # Add additional metrics
        if additional_metrics:
            for key, value in additional_metrics.items():
                setattr(metrics, key, value)

        # Store metrics
        self.metrics_history.append(metrics)
        self.current_epoch = epoch
        self.current_step = step

        # Log to file
        metrics_dict = {
            'epoch': epoch,
            'step': step,
            'loss': loss,
            'learning_rate': learning_rate,
            **system_metrics
        }
        if additional_metrics:
            metrics_dict.update(additional_metrics)

        self.monitor_logger.info(json.dumps(metrics_dict))

        # Check for alerts
        self._check_alerts(metrics)

    def _get_system_metrics(self) -> Dict[str, float]:
        """Get current system metrics"""
        metrics = {}

        # CPU metrics
        if psutil is not None:
            try:
                metrics['cpu_percent'] = psutil.cpu_percent(interval=0.1)

                # RAM metrics
                ram = psutil.virtual_memory()
                metrics['ram_used_gb'] = ram.used / (1024**3)
                metrics['ram_total_gb'] = ram.total / (1024**3)
            except Exception as e:
                logger.warning(f"Failed to get system metrics: {e}")
                metrics['cpu_percent'] = 0.0
                metrics['ram_used_gb'] = 0.0
                metrics['ram_total_gb'] = 0.0
        else:
            metrics['cpu_percent'] = 0.0
            metrics['ram_used_gb'] = 0.0
            metrics['ram_total_gb'] = 0.0

        # GPU metrics (if available)
        if self.gpu_monitoring:
            try:
                import GPUtil
                gpus = GPUtil.getGPUs()
                if gpus:
                    gpu = gpus[0]  # Primary GPU
                    metrics['gpu_utilization'] = gpu.load * 100
                    metrics['gpu_memory_used'] = gpu.memoryUsed
                    metrics['gpu_memory_total'] = gpu.memoryTotal
            except ImportError:
                # Fallback to basic GPU info
                try:
                    import torch
                    if torch.cuda.is_available():
                        gpu_id = torch.cuda.current_device()
                        memory_info = torch.cuda.mem_get_info()
                        metrics['gpu_memory_used'] = (memory_info[1] - memory_info[0]) / (1024**2)  # MB
                        metrics['gpu_memory_total'] = memory_info[1] / (1024**2)  # MB
                        # Utilization not available from PyTorch
                        metrics['gpu_utilization'] = 0.0
                except:
                    metrics['gpu_utilization'] = 0.0
                    metrics['gpu_memory_used'] = 0.0
                    metrics['gpu_memory_total'] = 0.0

        return metrics

    def _check_alerts(self, metrics: TrainingMetrics):
        """Check for alert conditions"""
        alerts = []

        # Loss alerts
        if metrics.loss > self.alert_thresholds['max_loss']:
            alerts.append(TrainingAlert(
                alert_type="high_loss",
                severity="warning",
                message=f"Training loss too high: {metrics.loss:.4f}",
                timestamp=datetime.now(),
                metrics={"loss": metrics.loss}
            ))

        # Learning rate alerts
        if metrics.learning_rate < self.alert_thresholds['min_lr']:
            alerts.append(TrainingAlert(
                alert_type="low_learning_rate",
                severity="info",
                message=f"Learning rate very low: {metrics.learning_rate:.2e}",
                timestamp=datetime.now(),
                metrics={"learning_rate": metrics.learning_rate}
            ))

        # GPU memory alerts
        if metrics.gpu_memory_total > 0:
            memory_percent = (metrics.gpu_memory_used / metrics.gpu_memory_total) * 100
            if memory_percent > self.alert_thresholds['max_gpu_memory_percent']:
                alerts.append(TrainingAlert(
                    alert_type="high_gpu_memory",
                    severity="warning",
                    message=f"GPU memory usage high: {memory_percent:.1f}%",
                    timestamp=datetime.now(),
                    metrics={"gpu_memory_percent": memory_percent}
                ))

        # CPU alerts
        if metrics.cpu_percent > self.alert_thresholds['max_cpu_percent']:
            alerts.append(TrainingAlert(
                alert_type="high_cpu",
                severity="warning",
                message=f"CPU usage high: {metrics.cpu_percent:.1f}%",
                timestamp=datetime.now(),
                metrics={"cpu_percent": metrics.cpu_percent}
            ))

        # RAM alerts
        if metrics.ram_total_gb > 0:
            ram_percent = (metrics.ram_used_gb / metrics.ram_total_gb) * 100
            if ram_percent > self.alert_thresholds['max_ram_percent']:
                alerts.append(TrainingAlert(
                    alert_type="high_ram",
                    severity="warning",
                    message=f"RAM usage high: {ram_percent:.1f}%",
                    timestamp=datetime.now(),
                    metrics={"ram_percent": ram_percent}
                ))

        # Process alerts
        for alert in alerts:
            self._process_alert(alert)

    def _process_alert(self, alert: TrainingAlert):
        """Process and distribute alerts"""
        # Store alert
        self.alerts_history.append(alert)

        # Log alert
        self.monitor_logger.log(
            getattr(logging, alert.severity.upper(), logging.INFO),
            f"{alert.alert_type}: {alert.message}"
        )

        # Call alert callbacks
        for callback in self.alert_callbacks:
            try:
                callback(alert)
            except Exception as e:
                logger.error(f"Alert callback failed: {e}")

    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Periodic health check
                system_metrics = self._get_system_metrics()

                # Log system status every 60 seconds
                if int(time.time()) % 60 == 0:
                    self.monitor_logger.info(f"SYSTEM_STATUS: {json.dumps(system_metrics)}")

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

            time.sleep(10)  # Check every 10 seconds

    def _save_metrics_summary(self):
        """Save training metrics summary"""
        if not self.metrics_history:
            return

        summary_path = os.path.join(self.log_dir, 'training_summary.json')

        # Calculate summary statistics
        losses = [m.loss for m in self.metrics_history]
        learning_rates = [m.learning_rate for m in self.metrics_history]

        summary = {
            "training_duration_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0,
            "total_steps": len(self.metrics_history),
            "final_epoch": self.current_epoch,
            "final_step": self.current_step,
            "loss_stats": {
                "min": min(losses),
                "max": max(losses),
                "mean": sum(losses) / len(losses),
                "final": losses[-1] if losses else None
            },
            "learning_rate_stats": {
                "min": min(learning_rates),
                "max": max(learning_rates),
                "mean": sum(learning_rates) / len(learning_rates),
                "final": learning_rates[-1] if learning_rates else None
            },
            "alerts_count": len(self.alerts_history),
            "alerts_by_type": {}
        }

        # Count alerts by type
        for alert in self.alerts_history:
            summary["alerts_by_type"][alert.alert_type] = summary["alerts_by_type"].get(alert.alert_type, 0) + 1

        # Save summary
        with open(summary_path, 'w') as f:
            json.dump(summary, f, indent=2, default=str)

        logger.info(f"Training summary saved to {summary_path}")

    def get_training_stats(self) -> Dict[str, Any]:
        """Get current training statistics"""
        if not self.metrics_history:
            return {"status": "no_metrics"}

        latest = self.metrics_history[-1]

        return {
            "status": "active" if self.monitoring_active else "stopped",
            "current_epoch": self.current_epoch,
            "current_step": self.current_step,
            "latest_loss": latest.loss,
            "latest_learning_rate": latest.learning_rate,
            "gpu_utilization": latest.gpu_utilization,
            "gpu_memory_percent": (latest.gpu_memory_used / latest.gpu_memory_total * 100) if latest.gpu_memory_total > 0 else 0,
            "cpu_percent": latest.cpu_percent,
            "ram_percent": (latest.ram_used_gb / latest.ram_total_gb * 100) if latest.ram_total_gb > 0 else 0,
            "total_alerts": len(self.alerts_history),
            "training_duration_seconds": (datetime.now() - self.start_time).total_seconds() if self.start_time else 0
        }

    def get_metrics_history(self, limit: int = 1000) -> List[Dict[str, Any]]:
        """Get metrics history"""
        recent_metrics = self.metrics_history[-limit:] if limit > 0 else self.metrics_history

        return [{
            "timestamp": m.timestamp.isoformat(),
            "epoch": m.epoch,
            "step": m.step,
            "loss": m.loss,
            "learning_rate": m.learning_rate,
            "gpu_utilization": m.gpu_utilization,
            "gpu_memory_used": m.gpu_memory_used,
            "cpu_percent": m.cpu_percent,
            "ram_used_gb": m.ram_used_gb
        } for m in recent_metrics]

    def get_alerts_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Get alerts history"""
        recent_alerts = self.alerts_history[-limit:] if limit > 0 else self.alerts_history

        return [{
            "timestamp": a.timestamp.isoformat(),
            "alert_type": a.alert_type,
            "severity": a.severity,
            "message": a.message,
            "metrics": a.metrics
        } for a in recent_alerts]

    def update_pair_progress(self, pair: str, status: str, progress: float,
                           current_epoch: int, loss: float, accuracy: float):
        """Update progress for a trading pair (for compatibility)"""
        # Log as training metrics
        self.log_metrics(current_epoch, int(progress * 100), loss, 1e-3,
                        {"pair": pair, "status": status, "accuracy": accuracy})

# Global monitor instance
_monitor = None

def get_training_monitor() -> TrainingMonitor:
    """Get or create global training monitor instance"""
    global _monitor

    if _monitor is None:
        _monitor = TrainingMonitor()

    return _monitor

def log_training_metrics(epoch: int, step: int, loss: float, learning_rate: float):
    """Convenience function for logging training metrics"""
    monitor = get_training_monitor()
    monitor.log_metrics(epoch, step, loss, learning_rate)

def start_training_monitor():
    """Convenience function to start monitoring"""
    monitor = get_training_monitor()
    monitor.start_monitoring()

def stop_training_monitor():
    """Convenience function to stop monitoring"""
    monitor = get_training_monitor()
    monitor.stop_monitoring()

def create_training_monitor(pairs: List[str], epochs: int = 50) -> TrainingMonitor:
    """Create and initialize a training monitor"""
    return TrainingMonitor()

def display_training_monitor(monitor: TrainingMonitor):
    """Display the training monitor interface"""
    # Simple console display
    stats = monitor.get_training_stats()
    print(f"Training Status: {stats.get('status', 'unknown')}")
    print(f"Current Epoch: {stats.get('current_epoch', 0)}")
    print(f"Current Step: {stats.get('current_step', 0)}")
    print(f"Latest Loss: {stats.get('latest_loss', 0):.4f}")
    print(f"GPU Utilization: {stats.get('gpu_utilization', 0):.1f}%")
    print(f"Total Alerts: {stats.get('total_alerts', 0)}")

class GPUTrainingMonitor:
    """GPU-specific training monitor with GPU metrics"""

    def __init__(self, gpu_id: int = 0):
        self.gpu_id = gpu_id
        self.base_monitor = TrainingMonitor(gpu_monitoring=True)

    def start_monitoring(self):
        """Start GPU monitoring"""
        self.base_monitor.start_monitoring()

    def stop_monitoring(self):
        """Stop GPU monitoring"""
        self.base_monitor.stop_monitoring()

    def log_metrics(self, epoch: int, step: int, loss: float, learning_rate: float):
        """Log training metrics with GPU info"""
        self.base_monitor.log_metrics(epoch, step, loss, learning_rate)

    def get_gpu_stats(self) -> Dict[str, Any]:
        """Get GPU-specific statistics"""
        stats = self.base_monitor.get_training_stats()
        # Add GPU-specific metrics
        return stats

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    # Create monitor
    monitor = TrainingMonitor()

    # Start monitoring
    monitor.start_monitoring()

    # Simulate training metrics
    for epoch in range(2):
        for step in range(10):
            loss = 1.0 / (step + 1) + 0.1 * epoch  # Decreasing loss
            lr = 1e-3 * (0.9 ** epoch)  # Decreasing learning rate

            monitor.log_metrics(epoch, step, loss, lr)
            time.sleep(0.1)

    # Stop monitoring
    monitor.stop_monitoring()

    # Show stats
    stats = monitor.get_training_stats()
    logger.info(f"Training stats: {stats}")

    # Show recent metrics
    metrics = monitor.get_metrics_history(5)
    logger.info(f"Recent metrics: {len(metrics)} entries")

    # Show alerts
    alerts = monitor.get_alerts_history()
    logger.info(f"Total alerts: {len(alerts)}")