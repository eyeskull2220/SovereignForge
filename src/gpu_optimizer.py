#!/usr/bin/env python3
"""
SovereignForge - GPU Optimization System
Advanced GPU memory management, inference batching, and performance optimization

This module provides:
- Advanced GPU memory pooling and allocation
- Intelligent inference batching for multiple models
- Model quantization and optimization
- GPU utilization monitoring and optimization
- Memory defragmentation and cleanup
"""

import asyncio
import gc
import logging
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

import torch
import torch.nn as nn

from gpu_arbitrage_model import GPUArbitrageModel

# Import existing components
from gpu_manager import GPUManager, get_gpu_manager

logger = logging.getLogger(__name__)

@dataclass
class MemoryBlock:
    """GPU memory block for pooling"""
    gpu_id: int
    size_mb: int
    offset: int
    allocated: bool
    allocation_time: Optional[datetime]
    model_name: Optional[str]

@dataclass
class InferenceBatch:
    """Batch of inference requests"""
    batch_id: str
    model_name: str
    gpu_id: int
    inputs: List[torch.Tensor]
    callbacks: List[Callable]
    priority: int
    created_time: datetime

@dataclass
class QuantizedModel:
    """Quantized model information"""
    original_model: GPUArbitrageModel
    quantized_model: Any
    quantization_type: str  # 'dynamic', 'static', 'qat'
    memory_reduction: float
    speed_improvement: float
    accuracy_drop: float

class GPUOptimizer:
    """
    Advanced GPU optimization system for ML inference
    """

    def __init__(self,
                 memory_pool_size_mb: int = 4096,
                 max_batch_size: int = 16,
                 enable_quantization: bool = True,
                 enable_memory_pooling: bool = True):
        self.memory_pool_size_mb = memory_pool_size_mb
        self.max_batch_size = max_batch_size
        self.enable_quantization = enable_quantization
        self.enable_memory_pooling = enable_memory_pooling

        # Memory pooling
        self.memory_pools: Dict[int, List[MemoryBlock]] = {}  # gpu_id -> blocks
        self.memory_lock = threading.RLock()

        # Inference batching
        self.inference_queue: asyncio.Queue[InferenceBatch] = asyncio.Queue()
        self.batch_processing_tasks: Dict[str, asyncio.Task] = {}
        self.batch_lock = asyncio.Lock()

        # Model quantization
        self.quantized_models: Dict[str, QuantizedModel] = {}

        # Performance monitoring
        self.performance_stats = {
            "total_inferences": 0,
            "batched_inferences": 0,
            "memory_efficiency": 0.0,
            "average_batch_size": 0.0,
            "quantization_savings": 0.0
        }

        # GPU manager integration
        self.gpu_manager = get_gpu_manager()

        # Background optimization
        self.optimization_thread: Optional[threading.Thread] = None
        self.optimization_active = False

        logger.info("GPUOptimizer initialized")

    def initialize_memory_pools(self):
        """Initialize GPU memory pools for efficient allocation"""
        try:
            available_gpus = self.gpu_manager.available_gpus

            for gpu_id in available_gpus:
                # Get GPU memory info
                gpu_info = self.gpu_manager.get_gpu_info()
                if gpu_id in gpu_info:
                    total_memory = gpu_info[gpu_id].memory_total

                    # Reserve 80% of GPU memory for pooling
                    pool_size = min(self.memory_pool_size_mb, int(total_memory * 0.8))

                    # Create memory blocks (divide into 256MB chunks)
                    block_size = 256
                    num_blocks = pool_size // block_size

                    self.memory_pools[gpu_id] = []
                    for i in range(num_blocks):
                        block = MemoryBlock(
                            gpu_id=gpu_id,
                            size_mb=block_size,
                            offset=i * block_size,
                            allocated=False,
                            allocation_time=None,
                            model_name=None
                        )
                        self.memory_pools[gpu_id].append(block)

                    logger.info(f"Initialized memory pool for GPU {gpu_id}: {num_blocks} blocks of {block_size}MB each")

        except Exception as e:
            logger.error(f"Failed to initialize memory pools: {e}")

    def allocate_memory_block(self, gpu_id: int, size_mb: int, model_name: str) -> Optional[MemoryBlock]:
        """Allocate memory block from pool"""
        with self.memory_lock:
            if gpu_id not in self.memory_pools:
                return None

            # Find suitable block (first-fit algorithm)
            for block in self.memory_pools[gpu_id]:
                if not block.allocated and block.size_mb >= size_mb:
                    block.allocated = True
                    block.allocation_time = datetime.now()
                    block.model_name = model_name

                    logger.debug(f"Allocated memory block {block.offset}-{block.offset + block.size_mb}MB on GPU {gpu_id} for {model_name}")
                    return block

            logger.warning(f"No suitable memory block found for {size_mb}MB on GPU {gpu_id}")
            return None

    def deallocate_memory_block(self, block: MemoryBlock):
        """Deallocate memory block back to pool"""
        with self.memory_lock:
            if block.gpu_id in self.memory_pools:
                block.allocated = False
                block.allocation_time = None
                block.model_name = None

                logger.debug(f"Deallocated memory block {block.offset}-{block.offset + block.size_mb}MB on GPU {block.gpu_id}")

    async def submit_inference_batch(self,
                                   model_name: str,
                                   inputs: List[torch.Tensor],
                                   callbacks: List[Callable],
                                   priority: int = 1) -> str:
        """
        Submit inference request for batching
        """
        batch_id = f"batch_{model_name}_{int(time.time() * 1000)}_{len(inputs)}"

        batch = InferenceBatch(
            batch_id=batch_id,
            model_name=model_name,
            gpu_id=self._select_gpu_for_model(model_name),
            inputs=inputs,
            callbacks=callbacks,
            priority=priority,
            created_time=datetime.now()
        )

        await self.inference_queue.put(batch)

        # Start processing if not already running
        if model_name not in self.batch_processing_tasks or self.batch_processing_tasks[model_name].done():
            self.batch_processing_tasks[model_name] = asyncio.create_task(
                self._process_model_batches(model_name)
            )

        return batch_id

    def _select_gpu_for_model(self, model_name: str) -> int:
        """Select optimal GPU for model inference"""
        available_gpus = self.gpu_manager.available_gpus
        if not available_gpus:
            return 0

        # Simple load balancing - select GPU with most free memory
        gpu_info = self.gpu_manager.get_gpu_info()
        best_gpu = available_gpus[0]
        best_memory = 0

        for gpu_id in available_gpus:
            if gpu_id in gpu_info:
                free_memory = gpu_info[gpu_id].memory_free
                if free_memory > best_memory:
                    best_memory = free_memory
                    best_gpu = gpu_id

        return best_gpu

    async def _process_model_batches(self, model_name: str):
        """Process batches for a specific model"""
        try:
            batch_buffer = []
            buffer_size = 0

            while True:
                try:
                    # Wait for next batch with timeout
                    batch = await asyncio.wait_for(
                        self.inference_queue.get(),
                        timeout=1.0
                    )

                    if batch.model_name != model_name:
                        # Put back in queue if not for this model
                        await self.inference_queue.put(batch)
                        continue

                    batch_buffer.append(batch)
                    buffer_size += len(batch.inputs)

                    # Process when buffer is full or high priority batch arrives
                    should_process = (
                        buffer_size >= self.max_batch_size or
                        any(b.priority >= 3 for b in batch_buffer) or
                        len(batch_buffer) >= 3  # Process every 3 batches minimum
                    )

                    if should_process:
                        await self._execute_batch_inference(batch_buffer)
                        batch_buffer = []
                        buffer_size = 0

                except asyncio.TimeoutError:
                    # Process remaining batches
                    if batch_buffer:
                        await self._execute_batch_inference(batch_buffer)
                        batch_buffer = []
                        buffer_size = 0
                    break

        except Exception as e:
            logger.error(f"Error processing batches for {model_name}: {e}")

    async def _execute_batch_inference(self, batches: List[InferenceBatch]):
        """Execute batched inference"""
        if not batches:
            return

        try:
            model_name = batches[0].model_name
            gpu_id = batches[0].gpu_id

            # Collect all inputs
            all_inputs = []
            all_callbacks = []
            batch_indices = []

            for batch in batches:
                batch_start_idx = len(all_inputs)
                all_inputs.extend(batch.inputs)
                all_callbacks.extend(batch.callbacks)

                # Track which results belong to which batch
                batch_indices.extend([batch_start_idx + i for i in range(len(batch.inputs))])

            # Convert to batched tensor
            if all_inputs:
                try:
                    # Stack inputs along batch dimension
                    batched_input = torch.stack(all_inputs, dim=0)

                    # Move to GPU
                    batched_input = batched_input.to(f'cuda:{gpu_id}' if torch.cuda.is_available() else 'cpu')

                    # Get model (use quantized if available)
                    model = self.quantized_models.get(model_name)
                    if model:
                        inference_model = model.quantized_model
                    else:
                        # Fallback to regular model (would need model registry)
                        inference_model = None

                    if inference_model:
                        # Perform inference
                        with torch.no_grad():
                            signal, confidence, spread = inference_model(batched_input)

                        # Split results back to individual batches
                        results = []
                        for i, (sig, conf, spr) in enumerate(zip(signal, confidence, spread)):
                            results.append((sig.item(), conf.item(), spr.item()))

                        # Call callbacks with results
                        result_idx = 0
                        for batch in batches:
                            batch_results = results[result_idx:result_idx + len(batch.inputs)]
                            result_idx += len(batch.inputs)

                            for callback, result in zip(batch.callbacks, batch_results):
                                try:
                                    await callback(result)
                                except Exception as e:
                                    logger.error(f"Error in inference callback: {e}")

                        # Update stats
                        self.performance_stats["total_inferences"] += len(all_inputs)
                        self.performance_stats["batched_inferences"] += len(all_inputs)
                        self.performance_stats["average_batch_size"] = (
                            (self.performance_stats["average_batch_size"] * 0.9) +
                            (len(all_inputs) * 0.1)
                        )

                        logger.debug(f"Processed batched inference: {len(batches)} batches, {len(all_inputs)} total inputs")

                except Exception as e:
                    logger.error(f"Batch inference failed: {e}")

        except Exception as e:
            logger.error(f"Error executing batch inference: {e}")

    def quantize_model(self, model_name: str, model: GPUArbitrageModel, quantization_type: str = 'dynamic') -> bool:
        """
        Quantize model for improved performance and memory efficiency
        """
        try:
            if not self.enable_quantization:
                return False

            original_model = model.model

            if quantization_type == 'dynamic':
                # Dynamic quantization
                quantized_model = torch.quantization.quantize_dynamic(
                    original_model,
                    {nn.Linear},  # Quantize linear layers
                    dtype=torch.qint8
                )
            elif quantization_type == 'static':
                # Static quantization (more complex, requires calibration)
                # This is a simplified version
                quantized_model = torch.quantization.quantize_dynamic(
                    original_model,
                    {nn.Linear},
                    dtype=torch.qint8
                )
            else:
                logger.warning(f"Unsupported quantization type: {quantization_type}")
                return False

            # Estimate memory reduction and performance improvement
            original_params = sum(p.numel() for p in original_model.parameters())
            quantized_params = sum(p.numel() for p in quantized_model.parameters())

            memory_reduction = 1.0 - (quantized_params / original_params)
            speed_improvement = 1.5  # Estimated 1.5x speedup for quantized models
            accuracy_drop = 0.02  # Estimated 2% accuracy drop

            quantized_info = QuantizedModel(
                original_model=model,
                quantized_model=quantized_model,
                quantization_type=quantization_type,
                memory_reduction=memory_reduction,
                speed_improvement=speed_improvement,
                accuracy_drop=accuracy_drop
            )

            self.quantized_models[model_name] = quantized_info

            # Update performance stats
            self.performance_stats["quantization_savings"] = (
                (self.performance_stats["quantization_savings"] * 0.9) +
                (memory_reduction * 0.1)
            )

            logger.info(f"Quantized model {model_name}: {memory_reduction:.1%} memory reduction, "
                       f"{speed_improvement:.1f}x speedup estimated")

            return True

        except Exception as e:
            logger.error(f"Model quantization failed for {model_name}: {e}")
            return False

    def optimize_memory_usage(self):
        """Perform memory optimization operations"""
        try:
            # Clear PyTorch cache
            if torch.cuda.is_available():
                torch.cuda.empty_cache()

            # Run garbage collection
            gc.collect()

            # Defragment memory pools
            self._defragment_memory_pools()

            # Optimize GPU memory allocation
            for gpu_id in self.gpu_manager.available_gpus:
                self.gpu_manager.optimize_memory(gpu_id)

            logger.debug("Memory optimization completed")

        except Exception as e:
            logger.error(f"Memory optimization failed: {e}")

    def _defragment_memory_pools(self):
        """Defragment memory pools to reduce fragmentation"""
        with self.memory_lock:
            for gpu_id, blocks in self.memory_pools.items():
                # Simple defragmentation: sort blocks by allocation status
                # In a real implementation, this would be more sophisticated
                allocated_blocks = [b for b in blocks if b.allocated]
                free_blocks = [b for b in blocks if not b.allocated]

                # Reorganize: allocated blocks first, then free blocks
                self.memory_pools[gpu_id] = allocated_blocks + free_blocks

                logger.debug(f"Defragmented memory pool for GPU {gpu_id}")

    def get_memory_utilization(self) -> Dict[str, Any]:
        """Get memory utilization statistics"""
        with self.memory_lock:
            utilization = {}

            for gpu_id, blocks in self.memory_pools.items():
                total_blocks = len(blocks)
                allocated_blocks = sum(1 for b in blocks if b.allocated)
                total_memory = sum(b.size_mb for b in blocks)
                allocated_memory = sum(b.size_mb for b in blocks if b.allocated)

                utilization[f"gpu_{gpu_id}"] = {
                    "total_blocks": total_blocks,
                    "allocated_blocks": allocated_blocks,
                    "utilization_pct": allocated_blocks / total_blocks if total_blocks > 0 else 0,
                    "total_memory_mb": total_memory,
                    "allocated_memory_mb": allocated_memory,
                    "memory_utilization_pct": allocated_memory / total_memory if total_memory > 0 else 0
                }

            return utilization

    def get_performance_stats(self) -> Dict[str, Any]:
        """Get performance statistics"""
        stats = self.performance_stats.copy()

        # Add memory stats
        stats["memory_utilization"] = self.get_memory_utilization()

        # Add quantization stats
        stats["quantized_models"] = len(self.quantized_models)
        stats["quantization_info"] = {
            name: {
                "type": info.quantization_type,
                "memory_reduction": info.memory_reduction,
                "speed_improvement": info.speed_improvement,
                "accuracy_drop": info.accuracy_drop
            }
            for name, info in self.quantized_models.items()
        }

        return stats

    def start_optimization(self):
        """Start background optimization"""
        if self.optimization_thread is not None:
            return

        self.optimization_active = True
        self.optimization_thread = threading.Thread(
            target=self._optimization_loop,
            name="gpu-optimizer",
            daemon=True
        )
        self.optimization_thread.start()

        logger.info("GPU optimization started")

    def stop_optimization(self):
        """Stop background optimization"""
        self.optimization_active = False

        if self.optimization_thread:
            self.optimization_thread.join(timeout=5)

        logger.info("GPU optimization stopped")

    def _optimization_loop(self):
        """Background optimization loop"""
        while self.optimization_active:
            try:
                # Memory optimization
                self.optimize_memory_usage()

                # Monitor and log performance
                stats = self.get_performance_stats()
                memory_efficiency = stats.get("memory_utilization", {})

                # Log warnings for low efficiency
                for gpu_key, gpu_stats in memory_efficiency.items():
                    if gpu_stats.get("memory_utilization_pct", 0) > 0.9:
                        logger.warning(f"High memory utilization on {gpu_key}: {gpu_stats['memory_utilization_pct']:.1%}")

                # Update overall efficiency metric
                total_allocated = 0
                total_capacity = 0

                for gpu_stats in memory_efficiency.values():
                    total_allocated += gpu_stats.get("allocated_memory_mb", 0)
                    total_capacity += gpu_stats.get("total_memory_mb", 0)

                if total_capacity > 0:
                    self.performance_stats["memory_efficiency"] = total_allocated / total_capacity

            except Exception as e:
                logger.error(f"Optimization loop error: {e}")

            time.sleep(60)  # Optimize every minute

# Global optimizer instance
_optimizer_instance = None

def get_gpu_optimizer() -> GPUOptimizer:
    """Get or create global GPU optimizer instance"""
    global _optimizer_instance

    if _optimizer_instance is None:
        _optimizer_instance = GPUOptimizer()

    return _optimizer_instance

async def initialize_gpu_optimizer() -> GPUOptimizer:
    """Initialize the global GPU optimizer"""
    optimizer = get_gpu_optimizer()
    optimizer.initialize_memory_pools()
    optimizer.start_optimization()
    return optimizer

def shutdown_gpu_optimizer():
    """Shutdown the global GPU optimizer"""
    optimizer = get_gpu_optimizer()
    optimizer.stop_optimization()

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    async def test_optimizer():
        optimizer = GPUOptimizer()
        optimizer.initialize_memory_pools()

        # Test memory allocation
        block = optimizer.allocate_memory_block(0, 512, "test_model")
        if block:
            logger.info(f"Allocated memory block: {block.size_mb}MB at offset {block.offset}")
            optimizer.deallocate_memory_block(block)

        # Test batch submission
        async def test_callback(result):
            logger.info(f"Inference result: {result}")

        test_input = torch.randn(1, 50, 10)
        batch_id = await optimizer.submit_inference_batch(
            model_name="test_model",
            inputs=[test_input],
            callbacks=[test_callback],
            priority=1
        )

        logger.info(f"Submitted batch: {batch_id}")

        # Get stats
        stats = optimizer.get_performance_stats()
        logger.info(f"Performance stats: {stats}")

        optimizer.stop_optimization()

    # Run test
    asyncio.run(test_optimizer())
