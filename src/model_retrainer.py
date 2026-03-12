#!/usr/bin/env python3
"""
SovereignForge - Automated Model Retraining Pipeline
Monitors model performance and triggers retraining with new market data

This module provides:
- Performance drift detection
- Automated retraining triggers
- Data quality validation
- Model versioning and rollback
- Continuous learning pipeline
"""

import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime, timedelta
import torch
import numpy as np
import json
from pathlib import Path
import threading
import time

# Import existing components
from gpu_arbitrage_model import GPUArbitrageModel, run_gpu_arbitrage_training
from gpu_manager import get_gpu_manager

logger = logging.getLogger(__name__)

@dataclass
class RetrainingTrigger:
    """Retraining trigger conditions"""
    model_name: str
    trigger_type: str  # 'performance_drift', 'data_drift', 'scheduled', 'manual'
    trigger_reason: str
    current_metric: float
    threshold: float
    timestamp: datetime

@dataclass
class RetrainingJob:
    """Retraining job specification"""
    job_id: str
    model_name: str
    pair: str
    trigger: RetrainingTrigger
    status: str  # 'pending', 'running', 'completed', 'failed'
    start_time: Optional[datetime]
    end_time: Optional[datetime]
    new_model_path: Optional[str]
    performance_improvement: Optional[float]
    error_message: Optional[str]

@dataclass
class DataQualityMetrics:
    """Data quality assessment metrics"""
    completeness: float
    consistency: float
    timeliness: float
    accuracy: float
    overall_score: float

class ModelRetrainer:
    """
    Automated model retraining system with performance monitoring
    """

    def __init__(self,
                 models_dir: str = "models",
                 retraining_interval_hours: int = 24,
                 performance_threshold: float = 0.7,
                 min_training_samples: int = 1000,
                 enable_auto_retraining: bool = True):
        self.models_dir = Path(models_dir)
        self.retraining_interval_hours = retraining_interval_hours
        self.performance_threshold = performance_threshold
        self.min_training_samples = min_training_samples
        self.enable_auto_retraining = enable_auto_retraining

        # Model tracking
        self.model_performance_history: Dict[str, List[Dict[str, Any]]] = {}
        self.active_models: Dict[str, GPUArbitrageModel] = {}
        self.model_versions: Dict[str, List[Dict[str, Any]]] = {}

        # Retraining management
        self.retraining_jobs: Dict[str, RetrainingJob] = {}
        self.pending_triggers: List[RetrainingTrigger] = []

        # Data quality monitoring
        self.data_quality_history: List[DataQualityMetrics] = []

        # Background monitoring
        self.monitoring_thread: Optional[threading.Thread] = None
        self.monitoring_active = False
        self._stop_event = threading.Event()

        # GPU management
        self.gpu_manager = get_gpu_manager()

        logger.info("ModelRetrainer initialized")

    def register_model(self, model_name: str, model: GPUArbitrageModel):
        """Register a model for monitoring and retraining"""
        self.active_models[model_name] = model

        # Initialize performance history
        if model_name not in self.model_performance_history:
            self.model_performance_history[model_name] = []

        # Initialize versions
        if model_name not in self.model_versions:
            self.model_versions[model_name] = []

        logger.info(f"Registered model: {model_name}")

    def update_model_performance(self,
                                model_name: str,
                                metrics: Dict[str, Any],
                                actual_outcome: Optional[bool] = None):
        """
        Update model performance metrics
        """
        try:
            performance_record = {
                'timestamp': datetime.now(),
                'metrics': metrics,
                'actual_outcome': actual_outcome
            }

            if model_name not in self.model_performance_history:
                self.model_performance_history[model_name] = []

            self.model_performance_history[model_name].append(performance_record)

            # Keep only recent history (last 1000 records)
            if len(self.model_performance_history[model_name]) > 1000:
                self.model_performance_history[model_name] = self.model_performance_history[model_name][-500:]

            # Check for retraining triggers
            self._check_performance_triggers(model_name)

            logger.debug(f"Updated performance for {model_name}: {metrics}")

        except Exception as e:
            logger.error(f"Failed to update model performance: {e}")

    def _check_performance_triggers(self, model_name: str):
        """Check if model performance triggers retraining"""
        try:
            if not self.enable_auto_retraining:
                return

            history = self.model_performance_history.get(model_name, [])
            if len(history) < 10:  # Need minimum history
                return

            # Calculate recent performance metrics
            recent_records = history[-50:]  # Last 50 predictions
            accuracies = [r['metrics'].get('accuracy', 0.5) for r in recent_records if 'accuracy' in r['metrics']]

            if not accuracies:
                return

            current_accuracy = np.mean(accuracies[-10:])  # Last 10 predictions
            overall_accuracy = np.mean(accuracies)

            # Performance drift detection
            if current_accuracy < self.performance_threshold:
                trigger = RetrainingTrigger(
                    model_name=model_name,
                    trigger_type='performance_drift',
                    trigger_reason=f'Accuracy dropped below threshold: {current_accuracy:.3f} < {self.performance_threshold:.3f}',
                    current_metric=current_accuracy,
                    threshold=self.performance_threshold,
                    timestamp=datetime.now()
                )
                self.pending_triggers.append(trigger)
                logger.warning(f"Performance trigger for {model_name}: {trigger.trigger_reason}")

            # Accuracy degradation over time
            elif len(accuracies) >= 20:
                recent_avg = np.mean(accuracies[-10:])
                older_avg = np.mean(accuracies[-20:-10])

                degradation = older_avg - recent_avg
                if degradation > 0.1:  # 10% degradation
                    trigger = RetrainingTrigger(
                        model_name=model_name,
                        trigger_type='performance_drift',
                        trigger_reason=f'Accuracy degraded by {degradation:.3f} over recent predictions',
                        current_metric=recent_avg,
                        threshold=older_avg - 0.05,  # Allow small degradation
                        timestamp=datetime.now()
                    )
                    self.pending_triggers.append(trigger)
                    logger.warning(f"Degradation trigger for {model_name}: {trigger.trigger_reason}")

        except Exception as e:
            logger.error(f"Error checking performance triggers: {e}")

    def check_data_quality(self, market_data: Dict[str, Any]) -> DataQualityMetrics:
        """Assess data quality for retraining"""
        try:
            # Completeness check
            required_fields = ['price', 'volume', 'bid_price', 'ask_price', 'timestamp']
            completeness = sum(1 for field in required_fields if field in market_data) / len(required_fields)

            # Consistency check (price relationships)
            consistency = 1.0
            if 'bid_price' in market_data and 'ask_price' in market_data:
                bid = market_data['bid_price']
                ask = market_data['ask_price']
                if bid >= ask:  # Bid should be less than ask
                    consistency = 0.5

            # Timeliness check (data freshness)
            timeliness = 1.0
            if 'timestamp' in market_data:
                data_age = time.time() - market_data['timestamp']
                if data_age > 300:  # Older than 5 minutes
                    timeliness = max(0.1, 1.0 - (data_age - 300) / 3600)  # Degrade over hour

            # Accuracy check (reasonable value ranges)
            accuracy = 1.0
            if 'price' in market_data:
                price = market_data['price']
                if price <= 0 or price > 1000000:  # Unreasonable price
                    accuracy = 0.1

            # Overall score
            overall_score = (completeness + consistency + timeliness + accuracy) / 4

            metrics = DataQualityMetrics(
                completeness=completeness,
                consistency=consistency,
                timeliness=timeliness,
                accuracy=accuracy,
                overall_score=overall_score
            )

            # Track data quality
            self.data_quality_history.append(metrics)
            if len(self.data_quality_history) > 100:
                self.data_quality_history = self.data_quality_history[-50:]

            return metrics

        except Exception as e:
            logger.error(f"Data quality check failed: {e}")
            return DataQualityMetrics(0.0, 0.0, 0.0, 0.0, 0.0)

    def trigger_retraining(self,
                          model_name: str,
                          trigger_type: str = 'manual',
                          trigger_reason: str = 'Manual retraining') -> Optional[str]:
        """
        Manually trigger retraining for a model
        Returns job ID if successful
        """
        try:
            if model_name not in self.active_models:
                logger.error(f"Model {model_name} not registered")
                return None

            trigger = RetrainingTrigger(
                model_name=model_name,
                trigger_type=trigger_type,
                trigger_reason=trigger_reason,
                current_metric=0.0,
                threshold=0.0,
                timestamp=datetime.now()
            )

            job_id = self._create_retraining_job(trigger)
            logger.info(f"Manual retraining triggered for {model_name}, job: {job_id}")

            return job_id

        except Exception as e:
            logger.error(f"Failed to trigger retraining: {e}")
            return None

    def _create_retraining_job(self, trigger: RetrainingTrigger) -> str:
        """Create a retraining job"""
        job_id = f"retrain_{trigger.model_name}_{int(time.time())}"

        # Extract pair from model name (e.g., 'final_BTC_USDC' -> 'BTC/USDC')
        pair = self._extract_pair_from_model_name(trigger.model_name)

        job = RetrainingJob(
            job_id=job_id,
            model_name=trigger.model_name,
            pair=pair,
            trigger=trigger,
            status='pending',
            start_time=None,
            end_time=None,
            new_model_path=None,
            performance_improvement=None,
            error_message=None
        )

        self.retraining_jobs[job_id] = job
        return job_id

    def _extract_pair_from_model_name(self, model_name: str) -> str:
        """Extract trading pair from model name"""
        # Handle different naming conventions
        if 'BTC' in model_name and 'USDC' in model_name:
            return 'BTC/USDC'
        elif 'ETH' in model_name and 'USDC' in model_name:
            return 'ETH/USDC'
        elif 'XRP' in model_name and 'USDC' in model_name:
            return 'XRP/USDC'
        elif 'XLM' in model_name and 'USDC' in model_name:
            return 'XLM/USDC'
        elif 'HBAR' in model_name and 'USDC' in model_name:
            return 'HBAR/USDC'
        elif 'ALGO' in model_name and 'USDC' in model_name:
            return 'ALGO/USDC'
        elif 'ADA' in model_name and 'USDC' in model_name:
            return 'ADA/USDC'
        elif 'LINK' in model_name and 'USDC' in model_name:
            return 'LINK/USDC'
        elif 'IOTA' in model_name and 'USDC' in model_name:
            return 'IOTA/USDC'
        else:
            return 'UNKNOWN/USDC'

    async def process_pending_jobs(self):
        """Process pending retraining jobs"""
        try:
            pending_jobs = [job for job in self.retraining_jobs.values() if job.status == 'pending']

            for job in pending_jobs:
                await self._execute_retraining_job(job)

        except Exception as e:
            logger.error(f"Error processing pending jobs: {e}")

    async def _execute_retraining_job(self, job: RetrainingJob):
        """Execute a retraining job"""
        try:
            logger.info(f"Starting retraining job: {job.job_id}")

            job.status = 'running'
            job.start_time = datetime.now()

            # Prepare training data
            training_data = await self._prepare_training_data(job.pair)
            if not training_data or len(training_data) < self.min_training_samples:
                raise ValueError(f"Insufficient training data: {len(training_data) if training_data else 0} < {self.min_training_samples}")

            # Validate data quality
            avg_quality = self._assess_training_data_quality(training_data)
            if avg_quality < 0.7:
                logger.warning(f"Low data quality for {job.pair}: {avg_quality:.3f}")

            # Execute training
            new_model_path = await self._run_model_training(job, training_data)

            # Validate new model
            performance_improvement = await self._validate_new_model(job, new_model_path)

            # Update job status
            job.status = 'completed'
            job.end_time = datetime.now()
            job.new_model_path = new_model_path
            job.performance_improvement = performance_improvement

            # Deploy new model if improved
            if performance_improvement > 0.02:  # At least 2% improvement
                await self._deploy_new_model(job)
                logger.info(f"Deployed improved model for {job.model_name} (+{performance_improvement:.1%})")
            else:
                logger.info(f"New model for {job.model_name} did not show significant improvement")

        except Exception as e:
            logger.error(f"Retraining job {job.job_id} failed: {e}")
            job.status = 'failed'
            job.end_time = datetime.now()
            job.error_message = str(e)

    async def _prepare_training_data(self, pair: str) -> Optional[List[Dict[str, Any]]]:
        """Prepare training data for the model"""
        try:
            # This would integrate with data collection systems
            # For now, simulate data preparation
            logger.info(f"Preparing training data for {pair}")

            # Simulate data collection (would be real data in production)
            training_samples = []
            for i in range(self.min_training_samples):
                sample = {
                    'timestamp': time.time() - (i * 60),  # One sample per minute
                    'price': 45000 + np.random.normal(0, 1000),
                    'volume': 100 + np.random.normal(0, 50),
                    'bid_price': 44950 + np.random.normal(0, 500),
                    'ask_price': 45050 + np.random.normal(0, 500),
                    'bid_volume': 50 + np.random.normal(0, 25),
                    'ask_volume': 50 + np.random.normal(0, 25),
                    'arbitrage_signal': np.random.choice([0, 1], p=[0.7, 0.3])  # Simulate labels
                }
                training_samples.append(sample)

            return training_samples

        except Exception as e:
            logger.error(f"Failed to prepare training data: {e}")
            return None

    def _assess_training_data_quality(self, training_data: List[Dict[str, Any]]) -> float:
        """Assess quality of training data"""
        if not training_data:
            return 0.0

        quality_scores = []
        for sample in training_data[:100]:  # Check first 100 samples
            metrics = self.check_data_quality(sample)
            quality_scores.append(metrics.overall_score)

        return np.mean(quality_scores) if quality_scores else 0.0

    async def _run_model_training(self, job: RetrainingJob, training_data: List[Dict[str, Any]]) -> str:
        """Run model training"""
        try:
            logger.info(f"Running training for {job.model_name}")

            # Prepare training parameters
            pairs = [job.pair]
            exchanges = ['binance', 'coinbase', 'kraken']  # Use multiple exchanges for robustness
            num_epochs = 5  # Limited epochs for quick retraining
            batch_size = 32

            # Run training
            results = run_gpu_arbitrage_training(
                pairs=pairs,
                exchanges=exchanges,
                num_epochs=num_epochs,
                batch_size=batch_size,
                save_models=True
            )

            # Generate model path
            model_path = f"models/retrained_{job.model_name}_{int(time.time())}.pth"

            # In a real implementation, this would save the trained model
            # For now, copy the existing model as a placeholder
            import shutil
            source_path = f"models/final_{job.pair.replace('/', '_')}.pth"
            if Path(source_path).exists():
                shutil.copy2(source_path, model_path)
                logger.info(f"Created retrained model: {model_path}")
            else:
                raise FileNotFoundError(f"Source model not found: {source_path}")

            return model_path

        except Exception as e:
            logger.error(f"Model training failed: {e}")
            raise

    async def _validate_new_model(self, job: RetrainingJob, model_path: str) -> float:
        """Validate the newly trained model"""
        try:
            # Load new model
            new_model = GPUArbitrageModel(model_path=model_path)

            # Load current model for comparison
            current_model = self.active_models.get(job.model_name)
            if not current_model:
                return 0.0  # Can't compare

            # Generate validation data
            validation_data = []
            for i in range(100):  # 100 validation samples
                sample = torch.randn(1, 50, 10)  # Batch size 1, 50 timesteps, 10 features
                validation_data.append(sample)

            # Test both models
            current_scores = []
            new_scores = []

            for data in validation_data:
                # Current model prediction
                curr_signal, curr_conf, curr_spread = current_model.predict(data)
                current_scores.append(curr_conf.item())

                # New model prediction
                new_signal, new_conf, new_spread = new_model.predict(data)
                new_scores.append(new_conf.item())

            # Calculate improvement
            current_avg = np.mean(current_scores)
            new_avg = np.mean(new_scores)
            improvement = new_avg - current_avg

            logger.info(f"Model validation: current={current_avg:.3f}, new={new_avg:.3f}, improvement={improvement:.3f}")

            return improvement

        except Exception as e:
            logger.error(f"Model validation failed: {e}")
            return 0.0

    async def _deploy_new_model(self, job: RetrainingJob):
        """Deploy the new model"""
        try:
            if not job.new_model_path:
                return

            # Backup current model
            current_path = f"models/final_{job.pair.replace('/', '_')}.pth"
            backup_path = f"models/backup_{job.model_name}_{int(time.time())}.pth"

            if Path(current_path).exists():
                import shutil
                shutil.copy2(current_path, backup_path)
                logger.info(f"Backed up current model: {backup_path}")

            # Deploy new model
            import shutil
            shutil.copy2(job.new_model_path, current_path)

            # Update active model
            new_model = GPUArbitrageModel(model_path=current_path)
            self.active_models[job.model_name] = new_model

            # Update model version history
            version_info = {
                'version': len(self.model_versions.get(job.model_name, [])) + 1,
                'timestamp': datetime.now(),
                'model_path': job.new_model_path,
                'performance_improvement': job.performance_improvement,
                'trigger': job.trigger.trigger_reason
            }

            if job.model_name not in self.model_versions:
                self.model_versions[job.model_name] = []
            self.model_versions[job.model_name].append(version_info)

            logger.info(f"Successfully deployed new model for {job.model_name}")

        except Exception as e:
            logger.error(f"Model deployment failed: {e}")

    def start_monitoring(self):
        """Start background monitoring"""
        if self.monitoring_thread is not None:
            return

        self.monitoring_active = True
        self.monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            name="model-retrainer-monitor",
            daemon=True
        )
        self.monitoring_thread.start()

        logger.info("Model retrainer monitoring started")

    def stop_monitoring(self):
        """Stop background monitoring"""
        self.monitoring_active = False
        self._stop_event.set()

        if self.monitoring_thread:
            self.monitoring_thread.join(timeout=5)

        logger.info("Model retrainer monitoring stopped")

    def _monitoring_loop(self):
        """Background monitoring loop"""
        while self.monitoring_active:
            try:
                # Process pending retraining jobs
                asyncio.run(self.process_pending_jobs())

                # Check for scheduled retraining
                self._check_scheduled_retraining()

                # Clean up old jobs
                self._cleanup_old_jobs()

            except Exception as e:
                logger.error(f"Monitoring loop error: {e}")

            self._stop_event.wait(timeout=300)  # Check every 5 minutes

    def _check_scheduled_retraining(self):
        """Check for scheduled retraining"""
        try:
            current_time = datetime.now()

            for model_name in self.active_models.keys():
                last_retraining = self._get_last_retraining_time(model_name)

                if last_retraining is None or \
                   (current_time - last_retraining) > timedelta(hours=self.retraining_interval_hours):

                    trigger = RetrainingTrigger(
                        model_name=model_name,
                        trigger_type='scheduled',
                        trigger_reason=f'Scheduled retraining (every {self.retraining_interval_hours}h)',
                        current_metric=0.0,
                        threshold=0.0,
                        timestamp=current_time
                    )

                    self.pending_triggers.append(trigger)
                    logger.info(f"Scheduled retraining trigger for {model_name}")

        except Exception as e:
            logger.error(f"Scheduled retraining check failed: {e}")

    def _get_last_retraining_time(self, model_name: str) -> Optional[datetime]:
        """Get the last retraining time for a model"""
        jobs = [job for job in self.retraining_jobs.values()
                if job.model_name == model_name and job.status == 'completed']

        if jobs:
            return max(job.end_time for job in jobs if job.end_time)

        return None

    def _cleanup_old_jobs(self):
        """Clean up old completed/failed jobs"""
        try:
            cutoff_time = datetime.now() - timedelta(days=7)  # Keep last 7 days

            jobs_to_remove = []
            for job_id, job in self.retraining_jobs.items():
                if job.end_time and job.end_time < cutoff_time:
                    jobs_to_remove.append(job_id)

            for job_id in jobs_to_remove:
                del self.retraining_jobs[job_id]

            if jobs_to_remove:
                logger.info(f"Cleaned up {len(jobs_to_remove)} old retraining jobs")

        except Exception as e:
            logger.error(f"Job cleanup failed: {e}")

    def get_retraining_status(self) -> Dict[str, Any]:
        """Get retraining system status"""
        return {
            "active_models": list(self.active_models.keys()),
            "pending_triggers": len(self.pending_triggers),
            "active_jobs": len([j for j in self.retraining_jobs.values() if j.status == 'running']),
            "completed_jobs": len([j for j in self.retraining_jobs.values() if j.status == 'completed']),
            "failed_jobs": len([j for j in self.retraining_jobs.values() if j.status == 'failed']),
            "monitoring_active": self.monitoring_active,
            "data_quality_score": np.mean([m.overall_score for m in self.data_quality_history[-10:]]) if self.data_quality_history else 0.0
        }

    def save_retraining_state(self, save_path: str):
        """Save retraining system state"""
        try:
            state = {
                "model_performance_history": self.model_performance_history,
                "model_versions": self.model_versions,
                "retraining_jobs": {
                    job_id: {
                        "job_id": job.job_id,
                        "model_name": job.model_name,
                        "pair": job.pair,
                        "status": job.status,
                        "start_time": job.start_time.isoformat() if job.start_time else None,
                        "end_time": job.end_time.isoformat() if job.end_time else None,
                        "new_model_path": job.new_model_path,
                        "performance_improvement": job.performance_improvement,
                        "error_message": job.error_message,
                        "trigger": {
                            "model_name": job.trigger.model_name,
                            "trigger_type": job.trigger.trigger_type,
                            "trigger_reason": job.trigger.trigger_reason,
                            "timestamp": job.trigger.timestamp.isoformat()
                        }
                    }
                    for job_id, job in self.retraining_jobs.items()
                },
                "pending_triggers": [
                    {
                        "model_name": t.model_name,
                        "trigger_type": t.trigger_type,
                        "trigger_reason": t.trigger_reason,
                        "current_metric": t.current_metric,
                        "threshold": t.threshold,
                        "timestamp": t.timestamp.isoformat()
                    }
                    for t in self.pending_triggers
                ],
                "saved_at": datetime.now().isoformat()
            }

            with open(save_path, 'w') as f:
                json.dump(state, f, indent=2, default=str)

            logger.info(f"Retraining state saved to {save_path}")

        except Exception as e:
            logger.error(f"Failed to save retraining state: {e}")

    def load_retraining_state(self, load_path: str) -> bool:
        """Load retraining system state"""
        try:
            with open(load_path, 'r') as f:
                state = json.load(f)

            # Restore performance history
            self.model_performance_history = state.get("model_performance_history", {})

            # Restore model versions
            self.model_versions = state.get("model_versions", {})

            # Restore jobs
            for job_data in state.get("retraining_jobs", {}).values():
                trigger_data = job_data["trigger"]
                trigger = RetrainingTrigger(
                    model_name=trigger_data["model_name"],
                    trigger_type=trigger_data["trigger_type"],
                    trigger_reason=trigger_data["trigger_reason"],
                    current_metric=trigger_data.get("current_metric", 0.0),
                    threshold=trigger_data.get("threshold", 0.0),
                    timestamp=datetime.fromisoformat(trigger_data["timestamp"])
                )

                job = RetrainingJob(
                    job_id=job_data["job_id"],
                    model_name=job_data["model_name"],
                    pair=job_data["pair"],
                    trigger=trigger,
                    status=job_data["status"],
                    start_time=datetime.fromisoformat(job_data["start_time"]) if job_data.get("start_time") else None,
                    end_time=datetime.fromisoformat(job_data["end_time"]) if job_data.get("end_time") else None,
                    new_model_path=job_data.get("new_model_path"),
                    performance_improvement=job_data.get("performance_improvement"),
                    error_message=job_data.get("error_message")
                )

                self.retraining_jobs[job.job_id] = job

            # Restore pending triggers
            for trigger_data in state.get("pending_triggers", []):
                trigger = RetrainingTrigger(
                    model_name=trigger_data["model_name"],
                    trigger_type=trigger_data["trigger_type"],
                    trigger_reason=trigger_data["trigger_reason"],
                    current_metric=trigger_data.get("current_metric", 0.0),
                    threshold=trigger_data.get("threshold", 0.0),
                    timestamp=datetime.fromisoformat(trigger_data["timestamp"])
                )
                self.pending_triggers.append(trigger)

            logger.info(f"Retraining state loaded from {load_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to load retraining state: {e}")
            return False

# Global retrainer instance
_retrainer_instance = None

def get_model_retrainer() -> ModelRetrainer:
    """Get or create global model retrainer instance"""
    global _retrainer_instance

    if _retrainer_instance is None:
        _retrainer_instance = ModelRetrainer()

    return _retrainer_instance

async def initialize_retraining_system() -> ModelRetrainer:
    """Initialize the global retraining system"""
    retrainer = get_model_retrainer()
    retrainer.start_monitoring()
    return retrainer

def shutdown_retraining_system():
    """Shutdown the global retraining system"""
    retrainer = get_model_retrainer()
    retrainer.stop_monitoring()

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)

    async def test_retraining():
        retrainer = ModelRetrainer()

        # Register a test model
        test_model = GPUArbitrageModel()
        retrainer.register_model("test_model", test_model)

        # Simulate performance updates
        for i in range(20):
            metrics = {
                'accuracy': 0.5 + 0.1 * np.sin(i / 5),  # Oscillating performance
                'loss': 0.5 - 0.1 * np.sin(i / 5)
            }
            retrainer.update_model_performance("test_model", metrics)

        # Check status
        status = retrainer.get_retraining_status()
        logger.info(f"Retraining status: {status}")

        # Trigger manual retraining
        job_id = retrainer.trigger_retraining("test_model", "manual", "Test retraining")
        if job_id:
            logger.info(f"Triggered retraining job: {job_id}")

        # Process jobs
        await retrainer.process_pending_jobs()

        # Final status
        final_status = retrainer.get_retraining_status()
        logger.info(f"Final status: {final_status}")

    # Run test
    asyncio.run(test_retraining())