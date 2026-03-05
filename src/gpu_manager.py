# SovereignForge GPU Manager - Wave 7
# Safe GPU-accelerated training infrastructure with monitoring and error handling

import os
import logging
import torch
import torch.nn as nn
import torch.cuda as cuda
from torch.cuda import amp
import gc
import psutil
import time
from typing import Dict, List, Optional, Any, Tuple
from contextlib import contextmanager
import threading
import signal
import numpy as np
from dataclasses import dataclass
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

@dataclass
class GPUConfig:
    """GPU configuration settings"""
    device: torch.device
    memory_fraction: float = 0.8
    enable_mixed_precision: bool = True
    gradient_accumulation_steps: int = 1
    max_grad_norm: float = 1.0
    memory_monitoring: bool = True
    watchdog_timeout: int = 300  # 5 minutes
    cleanup_interval: int = 60    # 1 minute

@dataclass
class GPUMetrics:
    """GPU performance metrics"""
    memory_allocated: int
    memory_reserved: int
    memory_free: int
    memory_total: int
    gpu_utilization: float
    temperature: float
    power_usage: float
    fan_speed: float
    last_updated: datetime

class GPUSafetyManager:
    """GPU safety and monitoring manager"""

    def __init__(self, config: GPUConfig):
        self.config = config
        self.metrics = GPUMetrics(0, 0, 0, 0, 0.0, 0.0, 0.0, 0.0, datetime.now())
        self.watchdog_timer = None
        self.memory_history = []
        self.error_count = 0
        self.last_cleanup = datetime.now()
        self.monitoring_active = False
        self.emergency_stop = False

    def start_monitoring(self):
        """Start GPU monitoring thread"""
        if self.monitoring_active:
            return

        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

        # Start watchdog timer
        self._reset_watchdog()

        logger.info("GPU safety monitoring started")

    def stop_monitoring(self):
        """Stop GPU monitoring"""
        self.monitoring_active = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=5.0)

        if self.watchdog_timer:
            self.watchdog_timer.cancel()

        logger.info("GPU safety monitoring stopped")

    def _monitor_loop(self):
        """Main monitoring loop"""
        while self.monitoring_active and not self.emergency_stop:
            try:
                self._update_metrics()
                self._check_safety_limits()
                self._periodic_cleanup()

                time.sleep(5.0)  # Check every 5 seconds

            except Exception as e:
                logger.error(f"GPU monitoring error: {e}")
                self.error_count += 1
                if self.error_count > 10:
                    self._emergency_shutdown("Too many monitoring errors")

    def _update_metrics(self):
        """Update GPU metrics"""
        try:
            if torch.cuda.is_available():
                self.metrics.memory_allocated = torch.cuda.memory_allocated(self.config.device)
                self.metrics.memory_reserved = torch.cuda.memory_reserved(self.config.device)
                memory_info = torch.cuda.mem_get_info(self.config.device)
                self.metrics.memory_free = memory_info[0]
                self.metrics.memory_total = memory_info[1]

                # Get GPU utilization (if available)
                try:
                    import nvidia_ml_py as nvml
                    if not hasattr(self, '_nvml_initialized'):
                        nvml.nvmlInit()
                        self._nvml_initialized = True

                    handle = nvml.nvmlDeviceGetHandleByIndex(self.config.device.index)
                    util = nvml.nvmlDeviceGetUtilizationRates(handle)
                    self.metrics.gpu_utilization = util.gpu

                    # Temperature and power
                    temp = nvml.nvmlDeviceGetTemperature(handle, nvml.NVML_TEMPERATURE_GPU)
                    self.metrics.temperature = temp

                    power = nvml.nvmlDeviceGetPowerUsage(handle)
                    self.metrics.power_usage = power / 1000.0  # Convert to watts

                    # Fan speed (if available)
                    try:
                        fan = nvml.nvmlDeviceGetFanSpeed(handle)
                        self.metrics.fan_speed = fan
                    except:
                        self.metrics.fan_speed = 0.0

                except ImportError:
                    # nvidia-ml-py not available, use basic metrics
                    pass
                except Exception as e:
                    logger.debug(f"NVML metrics error: {e}")

                self.metrics.last_updated = datetime.now()

                # Store memory history for leak detection
                self.memory_history.append(self.metrics.memory_allocated)
                if len(self.memory_history) > 100:  # Keep last 100 readings
                    self.memory_history.pop(0)

        except Exception as e:
            logger.error(f"Failed to update GPU metrics: {e}")

    def _check_safety_limits(self):
        """Check GPU safety limits"""
        # Memory usage limit
        memory_usage_pct = self.metrics.memory_allocated / self.metrics.memory_total
        if memory_usage_pct > self.config.memory_fraction:
            logger.warning(f"GPU memory usage high: {memory_usage_pct:.1f}")
            self._emergency_cleanup()

        # Temperature limit (if available)
        if self.metrics.temperature > 85:  # 85°C threshold
            logger.warning(f"GPU temperature high: {self.metrics.temperature:.1f}°C")
            self._emergency_cleanup()

        # Memory leak detection
        if len(self.memory_history) >= 50:
            recent_avg = np.mean(self.memory_history[-10:])
            older_avg = np.mean(self.memory_history[-50:-40])
            if recent_avg > older_avg * 1.5:  # 50% increase
                logger.warning("Potential GPU memory leak detected")
                self._emergency_cleanup()

    def _periodic_cleanup(self):
        """Periodic GPU cleanup"""
        now = datetime.now()
        if (now - self.last_cleanup).seconds >= self.config.cleanup_interval:
            self._cleanup_gpu_memory()
            self.last_cleanup = now

    def _cleanup_gpu_memory(self):
        """Clean up GPU memory"""
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                gc.collect()
                logger.debug("GPU memory cleanup completed")
        except Exception as e:
            logger.error(f"GPU cleanup error: {e}")

    def _emergency_cleanup(self):
        """Emergency GPU cleanup"""
        logger.warning("Performing emergency GPU cleanup")
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
                torch.cuda.synchronize()
                gc.collect()
        except Exception as e:
            logger.error(f"Emergency cleanup error: {e}")

    def _emergency_shutdown(self, reason: str):
        """Emergency shutdown"""
        logger.critical(f"GPU EMERGENCY SHUTDOWN: {reason}")
        self.emergency_stop = True
        self._emergency_cleanup()

    def _reset_watchdog(self):
        """Reset watchdog timer"""
        if self.watchdog_timer:
            self.watchdog_timer.cancel()

        self.watchdog_timer = threading.Timer(self.config.watchdog_timeout, self._watchdog_timeout)
        self.watchdog_timer.start()

    def _watchdog_timeout(self):
        """Watchdog timeout handler"""
        logger.critical("GPU watchdog timeout - possible hang detected")
        self._emergency_shutdown("Watchdog timeout")

    def get_metrics(self) -> GPUMetrics:
        """Get current GPU metrics"""
        return self.metrics

    def is_safe(self) -> bool:
        """Check if GPU is in safe state"""
        if self.emergency_stop:
            return False

        memory_usage_pct = self.metrics.memory_allocated / self.metrics.memory_total
        return memory_usage_pct < self.config.memory_fraction and self.metrics.temperature < 90

class GPUManager:
    """Main GPU manager for safe GPU operations"""

    def __init__(self, device_id: int = 0, memory_fraction: float = 1.0):
        self.device_id = device_id
        self.memory_fraction = memory_fraction
        self.device = None
        self.safety_manager = None
        self.scaler = None
        self.initialized = False

    def initialize(self) -> bool:
        """Initialize GPU manager"""
        try:
            if not torch.cuda.is_available():
                logger.warning("CUDA not available, falling back to CPU")
                self.device = torch.device('cpu')
                return True

            if self.device_id >= torch.cuda.device_count():
                logger.error(f"GPU device {self.device_id} not available")
                return False

            self.device = torch.device(f'cuda:{self.device_id}')

            # Set memory fraction
            torch.cuda.set_per_process_memory_fraction(self.memory_fraction, self.device_id)
            torch.cuda.empty_cache()

            # Initialize safety manager
            config = GPUConfig(
                device=self.device,
                memory_fraction=self.memory_fraction
            )
            self.safety_manager = GPUSafetyManager(config)
            self.safety_manager.start_monitoring()

            # Initialize mixed precision scaler
            self.scaler = torch.amp.GradScaler('cuda')

            self.initialized = True
            logger.info(f"GPU Manager initialized on {torch.cuda.get_device_name(self.device)}")
            return True

        except Exception as e:
            logger.error(f"Failed to initialize GPU manager: {e}")
            return False

    def shutdown(self):
        """Shutdown GPU manager"""
        if self.safety_manager:
            self.safety_manager.stop_monitoring()

        if torch.cuda.is_available():
            torch.cuda.empty_cache()

        self.initialized = False
        logger.info("GPU Manager shutdown")

    @contextmanager
    def safe_context(self):
        """Context manager for safe GPU operations"""
        if not self.initialized:
            raise RuntimeError("GPU Manager not initialized")

        try:
            yield self.device
        except Exception as e:
            logger.error(f"GPU operation error: {e}")
            self.safety_manager._emergency_cleanup()
            raise
        finally:
            # Reset watchdog on successful operation
            if self.safety_manager:
                self.safety_manager._reset_watchdog()

    def get_device(self) -> torch.device:
        """Get GPU device"""
        return self.device

    def get_safety_manager(self) -> GPUSafetyManager:
        """Get safety manager"""
        return self.safety_manager

    def is_available(self) -> bool:
        """Check if GPU is available and safe"""
        return (self.initialized and
                torch.cuda.is_available() and
                self.safety_manager and
                self.safety_manager.is_safe())

    def get_memory_info(self) -> Dict[str, Any]:
        """Get GPU memory information"""
        if not self.safety_manager:
            return {}

        metrics = self.safety_manager.get_metrics()
        return {
            'allocated_mb': metrics.memory_allocated / 1024 / 1024,
            'reserved_mb': metrics.memory_reserved / 1024 / 1024,
            'free_mb': metrics.memory_free / 1024 / 1024,
            'total_mb': metrics.memory_total / 1024 / 1024,
            'utilization_pct': metrics.gpu_utilization,
            'temperature_c': metrics.temperature,
            'power_watts': metrics.power_usage
        }

    def optimize_for_inference(self, model: nn.Module) -> nn.Module:
        """Optimize model for inference"""
        if not self.is_available():
            return model

        try:
            model = model.to(self.device)
            model.eval()

            # Enable cuDNN optimization
            torch.backends.cudnn.benchmark = True

            return model
        except Exception as e:
            logger.error(f"Failed to optimize model for inference: {e}")
            return model

    def create_data_loader(self, dataset, batch_size: int, shuffle: bool = True, num_workers: int = 0):
        """Create optimized data loader for GPU"""
        if not self.is_available():
            num_workers = 0  # CPU fallback

        return torch.utils.data.DataLoader(
            dataset,
            batch_size=batch_size,
            shuffle=shuffle,
            num_workers=num_workers,
            pin_memory=self.is_available(),  # GPU memory pinning
            persistent_workers=num_workers > 0
        )

# Global GPU manager instance
_gpu_manager = None

def get_gpu_manager(device_id: int = 0, memory_fraction: float = 1.0) -> GPUManager:
    """Get or create global GPU manager instance"""
    global _gpu_manager
    if _gpu_manager is None:
        _gpu_manager = GPUManager(device_id, memory_fraction)
        if not _gpu_manager.initialize():
            logger.warning("Failed to initialize GPU manager, using CPU fallback")
            _gpu_manager = None

    return _gpu_manager

def shutdown_gpu_manager():
    """Shutdown global GPU manager"""
    global _gpu_manager
    if _gpu_manager:
        _gpu_manager.shutdown()
        _gpu_manager = None

# Signal handler for clean shutdown
def _signal_handler(signum, frame):
    logger.info(f"Received signal {signum}, shutting down GPU manager")
    shutdown_gpu_manager()

signal.signal(signal.SIGINT, _signal_handler)
signal.signal(signal.SIGTERM, _signal_handler)

# Cleanup on exit
import atexit
atexit.register(shutdown_gpu_manager)