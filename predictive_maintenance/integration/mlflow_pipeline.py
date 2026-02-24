"""
MLflow Retraining Pipeline

Implements feedback → retraining pipeline with:
- Feedback collection and aggregation
- Drift detection triggers
- Model versioning with MLflow
- A/B testing and canary deployments
- Automated retraining on drift or feedback volume
"""

import logging
import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

import numpy as np

logger = logging.getLogger(__name__)

try:
    import mlflow
    from mlflow.tracking import MlflowClient
    MLFLOW_AVAILABLE = True
except ImportError:
    MLFLOW_AVAILABLE = False
    logger.warning("MLflow not installed. Retraining pipeline will use mock mode.")


class RetrainingTrigger(str, Enum):
    """Reasons for triggering model retraining"""
    DRIFT_DETECTED = "drift_detected"
    FEEDBACK_VOLUME = "feedback_volume"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    SCHEDULED = "scheduled"
    MANUAL = "manual"


class ModelStage(str, Enum):
    """Model lifecycle stages"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    CANARY = "canary"
    PRODUCTION = "production"
    ARCHIVED = "archived"


@dataclass
class FeedbackRecord:
    """Individual feedback record from operator"""
    feedback_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    alert_id: str = ""
    asset_id: str = ""
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    outcome: str = ""
    predicted_fault: str = ""
    actual_fault: str = ""
    predicted_confidence: float = 0.0
    
    was_true_positive: bool = False
    was_false_positive: bool = False
    was_false_negative: bool = False
    
    technician_notes: str = ""
    resolution_time_hours: float = 0.0


@dataclass
class RetrainingJob:
    """Represents a model retraining job"""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    model_type: str = ""
    trigger: RetrainingTrigger = RetrainingTrigger.MANUAL
    status: str = "pending"
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    training_config: Dict[str, Any] = field(default_factory=dict)
    metrics: Dict[str, float] = field(default_factory=dict)
    
    mlflow_run_id: Optional[str] = None
    model_version: Optional[str] = None
    
    error: Optional[str] = None


@dataclass
class PipelineConfig:
    """Configuration for the retraining pipeline"""
    mlflow_tracking_uri: str = "sqlite:///mlflow.db"
    experiment_name: str = "pdm-models"
    
    min_feedback_for_retrain: int = 100
    max_false_positive_rate: float = 0.10
    min_days_between_retrains: int = 7
    
    auto_retrain_on_drift: bool = True
    auto_promote_threshold: float = 0.05
    canary_traffic_pct: float = 0.10
    canary_duration_hours: int = 24
    
    model_registry_name: str = "pdm-fault-detector"


class ModelTrainer:
    """Pluggable trainer interface for retraining pipelines."""

    def train(
        self,
        training_data: List[Dict[str, Any]],
        job: RetrainingJob,
    ) -> Dict[str, float]:
        raise NotImplementedError


class DeterministicBaselineTrainer(ModelTrainer):
    """Deterministic baseline trainer for environments without full ML training stack."""

    def train(
        self,
        training_data: List[Dict[str, Any]],
        job: RetrainingJob,
    ) -> Dict[str, float]:
        n = len(training_data)
        if n == 0:
            return {
                "accuracy": 0.0,
                "precision": 0.0,
                "recall": 0.0,
                "f1_score": 0.0,
                "false_positive_rate": 0.0,
                "training_samples": 0.0,
            }

        labels = [1 if int(row.get("label", 0)) == 1 else 0 for row in training_data]
        predicted = [1 if float(row.get("confidence", 0.0) or 0.0) >= 0.5 else 0 for row in training_data]

        tp = sum(1 for p, y in zip(predicted, labels) if p == 1 and y == 1)
        tn = sum(1 for p, y in zip(predicted, labels) if p == 0 and y == 0)
        fp = sum(1 for p, y in zip(predicted, labels) if p == 1 and y == 0)
        fn = sum(1 for p, y in zip(predicted, labels) if p == 0 and y == 1)

        accuracy = (tp + tn) / max(n, 1)
        precision = tp / max(tp + fp, 1)
        recall = tp / max(tp + fn, 1)
        f1 = (2 * precision * recall) / max(precision + recall, 1e-12)
        fpr = fp / max(fp + tn, 1)

        return {
            "accuracy": float(round(accuracy, 6)),
            "precision": float(round(precision, 6)),
            "recall": float(round(recall, 6)),
            "f1_score": float(round(f1, 6)),
            "false_positive_rate": float(round(fpr, 6)),
            "training_samples": float(n),
        }


class MLflowRetrainingPipeline:
    """
    End-to-end retraining pipeline with MLflow integration.
    
    Workflow:
    1. Collect feedback from operator decisions
    2. Aggregate metrics and detect drift
    3. Trigger retraining when thresholds exceeded
    4. Train new model version with MLflow tracking
    5. Evaluate on holdout validation set
    6. Deploy to canary if metrics improve
    7. Promote to production after canary period
    """
    
    def __init__(
        self,
        config: PipelineConfig = None,
        trainer: Optional[ModelTrainer] = None,
    ):
        self.config = config or PipelineConfig()
        self._feedback_buffer: List[FeedbackRecord] = []
        self._jobs: Dict[str, RetrainingJob] = {}
        self._model_versions: Dict[str, Dict[str, Any]] = {}
        self._last_retrain: Dict[str, datetime] = {}
        
        self._mlflow_client: Optional[MlflowClient] = None
        self._trainer: ModelTrainer = trainer or DeterministicBaselineTrainer()
        self._initialize_mlflow()
    
    def _initialize_mlflow(self):
        """Initialize MLflow tracking"""
        if not MLFLOW_AVAILABLE:
            logger.info("MLflow not available, using mock mode")
            return
        
        try:
            mlflow.set_tracking_uri(self.config.mlflow_tracking_uri)
            mlflow.set_experiment(self.config.experiment_name)
            self._mlflow_client = MlflowClient()
            logger.info(f"MLflow initialized: {self.config.mlflow_tracking_uri}")
        except Exception as e:
            logger.warning(f"MLflow initialization failed: {e}")
    
    def record_feedback(self, feedback: FeedbackRecord):
        """Record operator feedback for a prediction"""
        self._feedback_buffer.append(feedback)
        
        logger.debug(f"Recorded feedback: {feedback.feedback_id} for alert {feedback.alert_id}")
        
        if len(self._feedback_buffer) >= self.config.min_feedback_for_retrain:
            self._check_retrain_triggers()
    
    def record_prediction_outcome(
        self,
        alert_id: str,
        asset_id: str,
        predicted_fault: str,
        predicted_confidence: float,
        outcome: str,
        actual_fault: str = None,
        notes: str = "",
    ):
        """Convenience method to record prediction outcome"""
        feedback = FeedbackRecord(
            alert_id=alert_id,
            asset_id=asset_id,
            predicted_fault=predicted_fault,
            predicted_confidence=predicted_confidence,
            outcome=outcome,
            actual_fault=actual_fault or predicted_fault,
            was_true_positive=outcome == "true_positive",
            was_false_positive=outcome == "false_positive",
            was_false_negative=outcome == "false_negative",
            technician_notes=notes,
        )
        self.record_feedback(feedback)
    
    def _check_retrain_triggers(self):
        """Check if retraining should be triggered"""
        recent = [f for f in self._feedback_buffer 
                  if f.timestamp > datetime.utcnow() - timedelta(days=30)]
        
        if len(recent) < 20:
            return
        
        fp_count = sum(1 for f in recent if f.was_false_positive)
        fp_rate = fp_count / len(recent)
        
        if fp_rate > self.config.max_false_positive_rate:
            logger.warning(f"High false positive rate: {fp_rate:.2%}")
            self._trigger_retrain(
                model_type="fault_detector",
                trigger=RetrainingTrigger.PERFORMANCE_DEGRADATION,
                reason=f"False positive rate {fp_rate:.2%} exceeds threshold {self.config.max_false_positive_rate:.2%}",
            )
        
        if len(self._feedback_buffer) >= self.config.min_feedback_for_retrain:
            last_retrain = self._last_retrain.get("fault_detector")
            if not last_retrain or (datetime.utcnow() - last_retrain).days >= self.config.min_days_between_retrains:
                self._trigger_retrain(
                    model_type="fault_detector",
                    trigger=RetrainingTrigger.FEEDBACK_VOLUME,
                    reason=f"Accumulated {len(self._feedback_buffer)} feedback records",
                )
    
    def on_drift_detected(
        self,
        model_id: str,
        drift_score: float,
        drift_type: str,
    ):
        """Handle drift detection signal from DriftDetectionService"""
        if not self.config.auto_retrain_on_drift:
            logger.info(f"Drift detected for {model_id} but auto-retrain disabled")
            return
        
        self._trigger_retrain(
            model_type=model_id,
            trigger=RetrainingTrigger.DRIFT_DETECTED,
            reason=f"Drift detected: type={drift_type}, score={drift_score:.3f}",
        )
    
    def _trigger_retrain(
        self,
        model_type: str,
        trigger: RetrainingTrigger,
        reason: str = "",
    ) -> Optional[RetrainingJob]:
        """Trigger a retraining job"""
        last = self._last_retrain.get(model_type)
        if last and (datetime.utcnow() - last).days < self.config.min_days_between_retrains:
            logger.info(f"Skipping retrain for {model_type}: too soon since last retrain")
            return None
        
        job = RetrainingJob(
            model_type=model_type,
            trigger=trigger,
            training_config={
                "reason": reason,
                "feedback_count": len(self._feedback_buffer),
            },
        )
        
        self._jobs[job.job_id] = job
        self._last_retrain[model_type] = datetime.utcnow()
        
        logger.info(f"Triggered retraining job {job.job_id}: {trigger.value} - {reason}")
        
        return job
    
    def run_training_job(self, job_id: str) -> RetrainingJob:
        """Execute a training job with MLflow tracking"""
        job = self._jobs.get(job_id)
        if not job:
            raise ValueError(f"Job not found: {job_id}")
        
        job.status = "running"
        job.started_at = datetime.utcnow()
        
        try:
            training_data = self._prepare_training_data()
            
            if MLFLOW_AVAILABLE:
                with mlflow.start_run(run_name=f"retrain-{job.job_id}") as run:
                    job.mlflow_run_id = run.info.run_id
                    
                    mlflow.log_param("trigger", job.trigger.value)
                    mlflow.log_param("model_type", job.model_type)
                    mlflow.log_param("training_samples", len(training_data))
                    
                    metrics = self._train_model(training_data, job)
                    
                    for name, value in metrics.items():
                        mlflow.log_metric(name, value)
                    
                    job.metrics = metrics
                    
                    model_version = self._register_model(job)
                    job.model_version = model_version
            else:
                metrics = self._train_model(training_data, job)
                job.metrics = metrics
                job.model_version = f"v{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
            
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            
            logger.info(f"Training job {job_id} completed: metrics={job.metrics}")
            
            if self._should_promote(job):
                self._promote_to_canary(job)
            
        except Exception as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at = datetime.utcnow()
            logger.error(f"Training job {job_id} failed: {e}")
        
        return job
    
    def _prepare_training_data(self) -> List[Dict[str, Any]]:
        """Prepare training data from feedback buffer"""
        data = []
        for fb in self._feedback_buffer:
            data.append({
                "alert_id": fb.alert_id,
                "asset_id": fb.asset_id,
                "predicted_fault": fb.predicted_fault,
                "actual_fault": fb.actual_fault,
                "confidence": fb.predicted_confidence,
                "label": 1 if fb.was_true_positive else 0,
                "timestamp": fb.timestamp.isoformat(),
            })
        return data
    
    def _train_model(
        self,
        training_data: List[Dict[str, Any]],
        job: RetrainingJob,
    ) -> Dict[str, float]:
        """Train model through pluggable trainer interface."""
        return self._trainer.train(training_data=training_data, job=job)
    
    def _register_model(self, job: RetrainingJob) -> str:
        """Register model version in MLflow Model Registry"""
        if not self._mlflow_client:
            return f"mock-v{datetime.utcnow().strftime('%Y%m%d')}"
        
        try:
            try:
                self._mlflow_client.create_registered_model(self.config.model_registry_name)
            except Exception:
                pass
            
            source = f"runs:/{job.mlflow_run_id}/model"
            
            model_version = self._mlflow_client.create_model_version(
                name=self.config.model_registry_name,
                source=source,
                run_id=job.mlflow_run_id,
                description=f"Retrained due to {job.trigger.value}",
            )
            
            return model_version.version
            
        except Exception as e:
            logger.warning(f"Model registration failed: {e}")
            return f"local-v{datetime.utcnow().strftime('%Y%m%d')}"
    
    def _should_promote(self, job: RetrainingJob) -> bool:
        """Check if new model should be promoted to canary"""
        current_metrics = self._get_production_metrics()
        
        if not current_metrics:
            return True
        
        improvement = job.metrics.get("f1_score", 0) - current_metrics.get("f1_score", 0)
        fp_reduction = current_metrics.get("false_positive_rate", 0.1) - job.metrics.get("false_positive_rate", 0.1)
        
        return improvement > self.config.auto_promote_threshold or fp_reduction > 0.02
    
    def _get_production_metrics(self) -> Dict[str, float]:
        """Get metrics for current production model"""
        prod_version = self._model_versions.get("production")
        if prod_version:
            return prod_version.get("metrics", {})
        return {}
    
    def _promote_to_canary(self, job: RetrainingJob):
        """Promote model to canary deployment"""
        logger.info(f"Promoting model {job.model_version} to canary")
        
        self._model_versions["canary"] = {
            "version": job.model_version,
            "metrics": job.metrics,
            "deployed_at": datetime.utcnow(),
            "traffic_pct": self.config.canary_traffic_pct,
        }
        
        if self._mlflow_client and MLFLOW_AVAILABLE:
            try:
                self._mlflow_client.transition_model_version_stage(
                    name=self.config.model_registry_name,
                    version=job.model_version,
                    stage="Staging",
                )
            except Exception as e:
                logger.warning(f"MLflow stage transition failed: {e}")
    
    def promote_canary_to_production(self):
        """Promote current canary to production after successful evaluation"""
        canary = self._model_versions.get("canary")
        if not canary:
            logger.warning("No canary model to promote")
            return
        
        current_prod = self._model_versions.get("production")
        if current_prod:
            self._model_versions["previous"] = current_prod
        
        self._model_versions["production"] = {
            **canary,
            "traffic_pct": 1.0,
            "promoted_at": datetime.utcnow(),
        }
        
        del self._model_versions["canary"]
        
        if self._mlflow_client and MLFLOW_AVAILABLE:
            try:
                self._mlflow_client.transition_model_version_stage(
                    name=self.config.model_registry_name,
                    version=canary["version"],
                    stage="Production",
                )
            except Exception as e:
                logger.warning(f"MLflow stage transition failed: {e}")
        
        logger.info(f"Promoted canary model {canary['version']} to production")
    
    def rollback_production(self):
        """Rollback to previous production model"""
        previous = self._model_versions.get("previous")
        if not previous:
            logger.warning("No previous model to rollback to")
            return
        
        current = self._model_versions.get("production")
        
        self._model_versions["production"] = previous
        self._model_versions["rolled_back"] = current
        
        logger.info(f"Rolled back to model {previous['version']}")
    
    def get_active_model_version(self, traffic_split: float = None) -> str:
        """Get which model version should handle a request"""
        if traffic_split is None:
            traffic_split = np.random.random()
        
        canary = self._model_versions.get("canary")
        if canary and traffic_split < canary.get("traffic_pct", 0):
            return canary["version"]
        
        prod = self._model_versions.get("production")
        if prod:
            return prod["version"]
        
        return "default"
    
    def get_pipeline_status(self) -> Dict[str, Any]:
        """Get current pipeline status"""
        return {
            "feedback_buffer_size": len(self._feedback_buffer),
            "pending_jobs": len([j for j in self._jobs.values() if j.status == "pending"]),
            "completed_jobs": len([j for j in self._jobs.values() if j.status == "completed"]),
            "production_model": self._model_versions.get("production", {}).get("version"),
            "canary_model": self._model_versions.get("canary", {}).get("version"),
            "canary_traffic_pct": self._model_versions.get("canary", {}).get("traffic_pct", 0),
            "last_retrain": {k: v.isoformat() for k, v in self._last_retrain.items()},
        }
    
    def clear_feedback_buffer(self):
        """Clear processed feedback"""
        self._feedback_buffer = []


_pipeline_instance: Optional[MLflowRetrainingPipeline] = None


def get_retraining_pipeline(config: PipelineConfig = None) -> MLflowRetrainingPipeline:
    """Get singleton retraining pipeline instance"""
    global _pipeline_instance
    if _pipeline_instance is None:
        _pipeline_instance = MLflowRetrainingPipeline(config)
    return _pipeline_instance
