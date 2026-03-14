#!/usr/bin/env python3
"""
SovereignForge - GPU Resource Manager
Advanced GPU resource management and monitoring for ML inference

This module provides:
- GPU memory management and optimization
- Multi-GPU support and load balancing
- GPU health monitoring and diagnostics
- CUDA context management
- Performance profiling and optimization
"""

import logging
import os
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

import torch

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

logger = logging.getLogger(__name__)

@dataclass
class GPUInfo:
    """GPU device information"""
    id: int
    name: str
    memory_total: int  # MB
    memory_free: int   # MB
    memory_used: int   # MB
    utilization: float # Percentage
    temperature: float # Celsius
    power_draw: float  # Watts
    power_limit: float # Watts

@dataclass
class GPUAllocation:
    """GPU memory allocation tracking"""
    process_id: str
    gpu_id: int
    memory_allocated: int  # MB
    allocation_time: datetime
    model_name: str
    operation_type: str

class GPUManager:
    """
    Advanced GPU resource manager for ML inference operations
    """

    def __init__(self,
                 memory_fraction: float = 0.8,
                 max_memory_per_model: int = 4096,  # MB
                 enable_monitoring: bool = True):
        self.memory_fraction = memory_fraction
        self.max_memory_per_model = max_memory_per_model
        self.enable_monitoring = enable_monitoring

        # GPU state tracking
        self.available_gpus: List[int] = []
        self.gpu_allocations: Dict[str, GPUAllocation] = {}
        self.allocation_lock = threading.RLock()

        # Performance monitoring
        self.monitoring_thread: Optional[threading.Thread] = None
        self.monitoring_active = False
        self.performance_stats = {
            "total_allocations": 0,
            "active_allocations": 0,
            "memory_utilization": 0.0,
            "average_allocation_time": 0.0,
            "failed_allocations": 0
        }

        # Initialize GPU detection
        self._initialize_gpu_detection()

        # Start monitoring if enabled
        if self.enable_monitoring:
            self._start_monitoring()

        logger.info(f"GPUManager initialized with {len(self.available_gpus)} GPUs")

    def _initialize_gpu_detection(self):
        """Detect and initialize available GPUs"""
        try:
            if torch.cuda.is_available():
                gpu_count = torch.cuda.device_count()
                self.available_gpus = list(range(gpu_count))

                # Configure CUDA memory management
                for gpu_id in self.available_gpus:
                    torch.cuda.set_device(gpu_id)
                    torch.cuda.empty_cache()

                    # Set memory fraction
                    torch.cuda.set_per_process_memory_fraction(self.memory_fraction, gpu_id)

                logger.info(f"Detected {gpu_count} CUDA GPUs")
            else:
                logger.warning("CUDA not available - running in CPU mode")
                self.available_gpus = []

        except Exception as e:
            logger.error(f"GPU initialization failed: {e}")
            self.available_gpus = []

    def allocate_gpu(self,
                    process_id: str,
                    model_name: str,
                    operation_type: str,
                    preferred_gpu: Optional[int] = None,
                    memory_required: Optional[int] = None) -> Optional[int]:
        """
        Allocate GPU for model inference
        Returns GPU ID or None if allocation fails
        """
        with self.allocation_lock:
            try:
                # Determine memory requirements
                required_memory = memory_required or self.max_memory_per_model

                # Find available GPU
                gpu_id = self._find_available_gpu(preferred_gpu, required_memory)

                if gpu_id is None:
                    logger.warning(f"No GPU available for {process_id} requiring {required_memory}MB")
                    self.performance_stats["failed_allocations"] += 1
                    return None

                # Create allocation record
                allocation = GPUAllocation(
                    process_id=process_id,
                    gpu_id=gpu_id,
                    memory_allocated=required_memory,
                    allocation_time=datetime.now(),
                    model_name=model_name,
                    operation_type=operation_type
                )

                # Track allocation
                self.gpu_allocations[process_id] = allocation
                self.performance_stats["total_allocations"] += 1
                self.performance_stats["active_allocations"] += 1

                # Set CUDA device
                torch.cuda.set_device(gpu_id)

                logger.info(f"Allocated GPU {gpu_id} for {process_id} ({model_name})")
                return gpu_id

            except Exception as e:
                logger.error(f"GPU allocation failed for {process_id}: {e}")
                return None

    def deallocate_gpu(self, process_id: str) -> bool:
        """
        Deallocate GPU for process
        """
        with self.allocation_lock:
            if process_id not in self.gpu_allocations:
                logger.warning(f"No allocation found for {process_id}")
                return False

            allocation = self.gpu_allocations[process_id]

            try:
                # Clear CUDA cache for the GPU
                torch.cuda.set_device(allocation.gpu_id)
                torch.cuda.empty_cache()

                # Remove allocation record
                del self.gpu_allocations[process_id]
                self.performance_stats["active_allocations"] -= 1

                logger.info(f"Deallocated GPU {allocation.gpu_id} for {process_id}")
                return True

            except Exception as e:
                logger.error(f"GPU deallocation failed for {process_id}: {e}")
                return False

    def _find_available_gpu(self, preferred_gpu: Optional[int], required_memory: int) -> Optional[int]:
        """Find available GPU with sufficient memory"""
        if not self.available_gpus:
            return None

        # Get GPU information
        gpu_info = self.get_gpu_info()

        # Check preferred GPU first
        if preferred_gpu is not None and preferred_gpu in self.available_gpus:
            if gpu_info[preferred_gpu].memory_free >= required_memory:
                return preferred_gpu

        # Find best available GPU
        best_gpu = None
        best_memory = 0

        for gpu_id in self.available_gpus:
            info = gpu_info.get(gpu_id)
            if info and info.memory_free >= required_memory:
                # Prefer GPU with most free memory
                if info.memory_free > best_memory:
                    best_memory = info.memory_free
                    best_gpu = gpu_id

        return best_gpu

    def get_gpu_info(self) -> Dict[int, GPUInfo]:
        """Get comprehensive GPU information"""
        gpu_info = {}

        try:
            # Use GPUtil for detailed GPU info
            gpus = GPUtil.getGPUs()

            for gpu in gpus:
                info = GPUInfo(
                    id=gpu.id,
                    name=gpu.name,
                    memory_total=int(gpu.memoryTotal),
                    memory_free=int(gpu.memoryFree),
                    memory_used=int(gpu.memoryUsed),
                    utilization=gpu.load * 100,
                    temperature=gpu.temperature,
                    power_draw=getattr(gpu, 'power_draw', 0),
                    power_limit=getattr(gpu, 'power_limit', 0)
                )
                gpu_info[gpu.id] = info

        except Exception as e:
            # Fallback to basic PyTorch info
            logger.warning(f"GPUtil failed, using basic info: {e}")

            for gpu_id in self.available_gpus:
                try:
                    torch.cuda.set_device(gpu_id)
                    memory_info = torch.cuda.mem_get_info()

                    info = GPUInfo(
                        id=gpu_id,
                        name=f"CUDA GPU {gpu_id}",
                        memory_total=int(memory_info[1] / 1024 / 1024),  # Convert to MB
                        memory_free=int(memory_info[0] / 1024 / 1024),
                        memory_used=int((memory_info[1] - memory_info[0]) / 1024 / 1024),
                        utilization=0.0,  # Not available from PyTorch
                        temperature=0.0,
                        power_draw=0.0,
                        power_limit=0.0
                    )
                    gpu_info[gpu_id] = info

                except Exception as e2:
                    logger.error(f"Failed to get info for GPU {gpu_id}: {e2}")

        return gpu_info

    def get_allocation_info(self) -> Dict[str, Any]:
        """Get current GPU allocation information"""
        with self.allocation_lock:
            allocations = []
            for alloc in self.gpu_allocations.values():
                allocations.append({
                    "process_id": alloc.process_id,
                    "gpu_id": alloc.gpu_id,
                    "memory_allocated": alloc.memory_allocated,
                    "allocation_time": alloc.allocation_time.isoformat(),
                    "model_name": alloc.model_name,
                    "operation_type": alloc.operation_type
                })

            return {
                "active_allocations": allocations,
                "total_allocations": len(allocations),
                "gpu_info": self.get_gpu_info()
            }

    def optimize_memory(self, gpu_id: Optional[int] = None):
        """Optimize GPU memory usage"""
        try:
            if gpu_id is not None:
                torch.cuda.set_device(gpu_id)

            # Clear cache
            torch.cuda.empty_cache()

            # Force garbage collection
            import gc
            gc.collect()

            logger.debug(f"Optimized memory for GPU {gpu_id or 'all'}")

        except Exception as e:
            logger.error(f"Memory optimization failed: {e}")

    def _start_monitoring(self):
        """Start GPU monitoring thread"""
        if self.monitoring_thread is not None:
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="gpu-monitor",
            daemon=True
        )
        self.monitoring_thread.start()

        logger.info("GPU monitoring started")

    def _monitoring_loop(self):
        """GPU monitoring loop"""
        while self.monitoring_active:
            try:
                # Update performance stats
                gpu_info = self.get_gpu_info()
                if gpu_info:
                    total_memory = sum(info.memory_total for info in gpu_info.values())
                    used_memory = sum(info.memory_used for info in gpu_info.values())

                    if total_memory > 0:
                        self.performance_stats["memory_utilization"] = (used_memory / total_memory) * 100

                # Log warnings for high utilization
                for gpu_id, info in gpu_info.items():
                    if info.utilization > 90:
                        logger.warning(f"GPU {gpu_id} utilization: {info.utilization:.1f}%")
                    if info.memory_used / info.memory_total > 0.9:
                        logger.warning(f"GPU {gpu_id} memory usage: {info.memory_used}/{info.memory_total} MB")

            except Exception as e:
                logger.error(f"GPU monitoring error: {e}")

            time.sleep(30)  # Monitor every 30 seconds

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get GPU performance statistics"""
        stats = self.performance_stats.copy()
        stats["available_gpus"] = len(self.available_gpus)
        stats["gpu_info"] = self.get_gpu_info()
        stats["allocation_info"] = self.get_allocation_info()

        return stats

    def health_check(self) -> Dict[str, Any]:
        """Comprehensive GPU health check"""
        health = {
            "status": "healthy",
            "timestamp": datetime.now().isoformat(),
            "cuda_available": torch.cuda.is_available(),
            "gpu_count": len(self.available_gpus),
            "performance": self.get_performance_stats()
        }

        # Check GPU availability
        if not self.available_gpus:
            health["status"] = "degraded"
            health["issues"] = ["No GPUs available"]
            return health

        # Check GPU health
        gpu_info = self.get_gpu_info()
        issues = []

        for gpu_id, info in gpu_info.items():
            if info.temperature > 85:  # High temperature
                issues.append(f"GPU {gpu_id} temperature: {info.temperature}°C")
            if info.memory_used / info.memory_total > 0.95:  # Very low memory
                issues.append(f"GPU {gpu_id} memory critical: {info.memory_used}/{info.memory_total} MB")

        if issues:
            health["status"] = "warning"
            health["issues"] = issues

        return health

    def shutdown(self):
        """Graceful shutdown"""
        logger.info("Shutting down GPUManager")

        self.monitoring_active = False

        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)

        # Deallocate all GPUs
        for process_id in list(self.gpu_allocations.keys()):
            self.deallocate_gpu(process_id)

        # Final memory cleanup
        for gpu_id in self.available_gpus:
            try:
                torch.cuda.set_device(gpu_id)
                torch.cuda.empty_cache()
            except Exception:
                pass

        logger.info("GPUManager shutdown complete")

# Global GPU manager instance
_gpu_manager = None

def get_gpu_manager(memory_fraction: float = 0.8, device_id: Optional[int] = None) -> GPUManager:
    """Get or create global GPU manager instance"""
    global _gpu_manager

    if _gpu_manager is None:
        _gpu_manager = GPUManager(memory_fraction=memory_fraction)

    return _gpu_manager

def allocate_gpu_for_inference(process_id: str, model_name: str) -> Optional[int]:
    """Convenience function for GPU allocation"""
    manager = get_gpu_manager()
    return manager.allocate_gpu(
        process_id=process_id,
        model_name=model_name,
        operation_type="inference"
    )

def deallocate_gpu_for_inference(process_id: str) -> bool:
    """Convenience function for GPU deallocation"""
    manager = get_gpu_manager()
    return manager.deallocate_gpu(process_id)

def get_gpu_health() -> Dict[str, Any]:
    """Get GPU health status"""
    manager = get_gpu_manager()
    return manager.health_check()

def shutdown_gpu_manager():
    """Shutdown the global GPU manager"""
    global _gpu_manager
    if _gpu_manager is not None:
        _gpu_manager.shutdown()
        _gpu_manager = None

if __name__ == "__main__":
    # Example usage and testing
    logging.basicConfig(level=logging.INFO)

    # Initialize GPU manager
    manager = GPUManager()

    # Health check
    health = manager.health_check()
    logger.info(f"GPU health: {health['status']}")

    # Show GPU info
    gpu_info = manager.get_gpu_info()
    for gpu_id, info in gpu_info.items():
        logger.info(f"GPU {gpu_id}: {info.name}, {info.memory_free}MB free")

    # Example allocation
    gpu_id = manager.allocate_gpu(
        process_id="test_process",
        model_name="arbitrage_model",
        operation_type="inference"
    )

    if gpu_id is not None:
        logger.info(f"Allocated GPU {gpu_id}")

        # Show allocation info
        alloc_info = manager.get_allocation_info()
        logger.info(f"Active allocations: {alloc_info['total_allocations']}")

        # Deallocate
        manager.deallocate_gpu("test_process")
        logger.info("GPU deallocated")

    # Performance stats
    stats = manager.get_performance_stats()
    logger.info(f"Performance stats: {stats}")

    manager.shutdown()
