"""SovereignForge System Monitor - Real-time system monitoring for production deployment.

Delegates to src/gpu_manager.py for GPU monitoring and adds basic system metrics.
"""

import logging
import time
import threading
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


class SystemMonitor:
    """Lightweight system monitor for CPU, memory, disk, and GPU metrics."""

    def __init__(self, interval_seconds: int = 30):
        self.interval = interval_seconds
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def get_system_metrics(self) -> Dict[str, Any]:
        """Collect current system metrics."""
        metrics: Dict[str, Any] = {"timestamp": time.time()}

        if PSUTIL_AVAILABLE:
            metrics["cpu_percent"] = psutil.cpu_percent(interval=0.1)
            mem = psutil.virtual_memory()
            metrics["memory_used_gb"] = round(mem.used / (1024 ** 3), 2)
            metrics["memory_total_gb"] = round(mem.total / (1024 ** 3), 2)
            metrics["memory_percent"] = mem.percent
            disk = psutil.disk_usage("/")
            metrics["disk_used_gb"] = round(disk.used / (1024 ** 3), 2)
            metrics["disk_percent"] = disk.percent

        if TORCH_AVAILABLE and torch.cuda.is_available():
            metrics["gpu_available"] = True
            metrics["gpu_name"] = torch.cuda.get_device_name(0)
            metrics["gpu_memory_allocated_gb"] = round(
                torch.cuda.memory_allocated(0) / (1024 ** 3), 2
            )
            metrics["gpu_memory_total_gb"] = round(
                torch.cuda.get_device_properties(0).total_memory / (1024 ** 3), 2
            )
        else:
            metrics["gpu_available"] = False

        return metrics

    def start(self):
        """Start background monitoring."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._thread.start()
        logger.info(f"System monitor started (interval={self.interval}s)")

    def stop(self):
        """Stop background monitoring."""
        self._running = False

    def _monitor_loop(self):
        while self._running:
            try:
                metrics = self.get_system_metrics()
                logger.debug(f"System metrics: {metrics}")
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
            time.sleep(self.interval)
