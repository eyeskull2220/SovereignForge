#!/usr/bin/env python3
"""
GPU Manager for SovereignForge
Handles CUDA memory management, GPU monitoring, and safety features
"""

import torch
import logging
import psutil
import GPUtil
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from contextlib import contextmanager
import time
import threading
import os

logger = logging.getLogger(__name__)

@dataclass
class GPUInfo:
    """GPU information container"""
    device_id: int
    name: str
    memory_total: float  # MB
    memory_free: float   # MB
    memory_used: float   # MB
    utilization: float   # percentage
    temperature: float   # Celsius

@dataclass
class GPUMemoryStats:
    """GPU memory statistics"""
    allocated: float  # MB
    reserved: float   # MB
    peak_allocated: float  # MB
    peak_reserved: float   # MB

class GPUManager:
    """Manages GPU resources and memory for SovereignForge"""

    def __init__(self, device_id: int = 0, memory_limit_mb: Optional[float] = None):
        self.device_id = device_id
        self.memory_limit_mb = memory_limit_mb
        self.device = torch.device(f'cuda:{device_id}' if torch.cuda.is_available() else 'cpu')
        self._lock = threading.Lock()
        self._memory_stats = GPUMemoryStats(0, 0, 0, 0)

        # Verify CUDA availability
        if not torch.cuda.is_available():
            logger.warning("CUDA not available, falling back to CPU")
            self.device = torch.device('cpu')
        else:
            torch.cuda.set_device(device_id)
            logger.info(f"GPU Manager initialized for device {device_id}")

    def get_gpu_info(self) -> GPUInfo:
        """Get current GPU information"""
        try:
            if not torch.cuda.is_available():
                return GPUInfo(0, "CPU", 0, 0, 0, 0, 0)

            gpus = GPUtil.getGPUs()
            if self.device_id >= len(gpus):
                raise ValueError(f"GPU device {self.device_id} not available")

            gpu = gpus[self.device_id]

            return GPUInfo(
                device_id=self.device_id,
                name=gpu.name,
                memory_total=gpu.memoryTotal,
                memory_free=gpu.memoryFree,
                memory_used=gpu.memoryUsed,
                utilization=gpu.load * 100,
                temperature=gpu.temperature
            )
        except Exception as e:
            logger.error(f"Failed to get GPU info: {e}")
            return GPUInfo(0, "Unknown", 0, 0, 0, 0, 0)

    def get_memory_stats(self) -> GPUMemoryStats:
        """Get current GPU memory statistics"""
        if not torch.cuda.is_available():
            return GPUMemoryStats(0, 0, 0, 0)

        with self._lock:
            try:
                allocated = torch.cuda.memory_allocated(self.device_id) / 1024 / 1024  # MB
                reserved = torch.cuda.memory_reserved(self.device_id) / 1024 / 1024   # MB

                self._memory_stats.allocated = allocated
                self._memory_stats.reserved = reserved
                self._memory_stats.peak_allocated = max(self._memory_stats.peak_allocated, allocated)
                self._memory_stats.peak_reserved = max(self._memory_stats.peak_reserved, reserved)

                return self._memory_stats

            except Exception as e:
                logger.error(f"Failed to get memory stats: {e}")
                return GPUMemoryStats(0, 0, 0, 0)

    def check_memory_limit(self, required_mb: float) -> bool:
        """Check if required memory is available within limits"""
        if not torch.cuda.is_available():
            return True  # CPU has no memory limits

        gpu_info = self.get_gpu_info()
        memory_stats = self.get_memory_stats()

        available_memory = gpu_info.memory_free
        if self.memory_limit_mb:
            available_memory = min(available_memory, self.memory_limit_mb - memory_stats.allocated)

        return available_memory >= required_mb

    @contextmanager
    def memory_guard(self, required_mb: float = 0):
        """Context manager for memory-safe operations"""
        if not self.check_memory_limit(required_mb):
            raise MemoryError(f"Insufficient GPU memory. Required: {required_mb}MB, Available: {self.get_gpu_info().memory_free}MB")

        try:
            yield
        finally:
            # Force garbage collection
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

    def optimize_memory(self):
        """Optimize GPU memory usage"""
        if not torch.cuda.is_available():
            return

        try:
            # Empty cache
            torch.cuda.empty_cache()

            # Synchronize
            torch.cuda.synchronize(self.device_id)

            logger.info("GPU memory optimized")

        except Exception as e:
            logger.error(f"Failed to optimize GPU memory: {e}")

    def monitor_resources(self, interval_seconds: float = 5.0):
        """Monitor GPU resources in a separate thread"""
        def monitor_loop():
            while True:
                try:
                    gpu_info = self.get_gpu_info()
                    memory_stats = self.get_memory_stats()

                    logger.info(f"GPU {gpu_info.device_id} ({gpu_info.name}): "
                              f"Memory {memory_stats.allocated:.1f}/{gpu_info.memory_total:.1f}MB, "
                              f"Util: {gpu_info.utilization:.1f}%, "
                              f"Temp: {gpu_info.temperature:.1f}°C")

                    time.sleep(interval_seconds)

                except Exception as e:
                    logger.error(f"Resource monitoring error: {e}")
                    time.sleep(interval_seconds)

        monitor_thread = threading.Thread(target=monitor_loop, daemon=True)
        monitor_thread.start()
        logger.info("GPU resource monitoring started")

    def safe_tensor_operation(self, operation_func, *args, **kwargs):
        """Execute tensor operations with memory safety"""
        with self.memory_guard():
            try:
                return operation_func(*args, **kwargs)
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    logger.warning("GPU out of memory, attempting recovery")
                    self.optimize_memory()
                    # Retry once after memory optimization
                    return operation_func(*args, **kwargs)
                else:
                    raise

    def get_optimal_batch_size(self, model_size_mb: float, safety_factor: float = 0.8) -> int:
        """Calculate optimal batch size based on available memory"""
        if not torch.cuda.is_available():
            return 32  # Default for CPU

        gpu_info = self.get_gpu_info()
        available_memory = gpu_info.memory_free * safety_factor

        # Estimate batch size (rough approximation)
        # Assume model needs ~2x its size for forward/backward pass
        memory_per_sample = model_size_mb * 2

        if memory_per_sample == 0:
            return 32

        optimal_batch = int(available_memory / memory_per_sample)
        return max(1, min(optimal_batch, 1024))  # Clamp between 1 and 1024

    def create_model_safely(self, model_class, *args, **kwargs):
        """Create model with memory safety checks"""
        with self.memory_guard():
            try:
                model = model_class(*args, **kwargs)
                if torch.cuda.is_available():
                    model = model.to(self.device)
                return model
            except RuntimeError as e:
                if "out of memory" in str(e).lower():
                    logger.error("Insufficient memory to create model")
                    raise MemoryError("Model creation failed due to insufficient GPU memory")
                else:
                    raise

def get_available_gpus() -> List[int]:
    """Get list of available GPU device IDs"""
    if not torch.cuda.is_available():
        return []

    return list(range(torch.cuda.device_count()))

def select_best_gpu() -> int:
    """Select the GPU with most available memory"""
    if not torch.cuda.is_available():
        return 0

    gpus = GPUtil.getGPUs()
    if not gpus:
        return 0

    # Find GPU with most free memory
    best_gpu = max(range(len(gpus)), key=lambda i: gpus[i].memoryFree)
    return best_gpu

# Global GPU manager instance
_default_gpu_manager = None

def get_gpu_manager(device_id: Optional[int] = None) -> GPUManager:
    """Get or create default GPU manager instance"""
    global _default_gpu_manager

    if _default_gpu_manager is None:
        if device_id is None:
            device_id = select_best_gpu()
        _default_gpu_manager = GPUManager(device_id=device_id)

    return _default_gpu_manager