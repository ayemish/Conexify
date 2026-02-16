"""
ML Learning Loop - Automated Retraining Pipeline

Automated retraining triggers and pipeline execution.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np

from .learning_loop_models import (
    ApprovalStatus,
    ModelType,
    PerformanceMetrics,
    RetrainingJob,
    RetrainingTrigger,
    RetrainingTriggerType,
)
from .learning_loop_registry import ModelRegistry
from .governance import AuditLogger

logger = logging.getLogger(__name__)


class RetrainingPipeline:
    """
    Automated retraining triggers and pipeline execution.
    """
    
    def __init__(self, model_registry: ModelRegistry, 
                 audit_logger: Optional[AuditLogger] = None):
        self.model_registry = model_registry
        self.audit_logger = audit_logger or AuditLogger()
        self.triggers: Dict[str, RetrainingTrigger] = {}
        self.jobs: Dict[str, RetrainingJob] = {}
        self.metrics_history: Dict[str, List[PerformanceMetrics]] = {}
        self.feedback_buffer: Dict[str, List[Dict]] = {}
        self.data_volume_tracker: Dict[str, int] = {}
        self._training_callbacks: Dict[str, Callable] = {}
    
    def register_trigger(self, trigger: RetrainingTrigger):
        """Register a retraining trigger"""
        self.triggers[trigger.trigger_id] = trigger
        logger.info(f"Registered trigger: {trigger.trigger_name} for {trigger.model_name}")
    
    def unregister_trigger(self, trigger_id: str):
        """Unregister a retraining trigger"""
        if trigger_id in self.triggers:
            del self.triggers[trigger_id]
            logger.info(f"Unregistered trigger: {trigger_id}")
    
    def enable_trigger(self, trigger_id: str):
        """Enable a trigger"""
        if trigger_id in self.triggers:
            self.triggers[trigger_id].is_active = True
    
    def disable_trigger(self, trigger_id: str):
        """Disable a trigger"""
        if trigger_id in self.triggers:
            self.triggers[trigger_id].is_active = False
    
    def register_training_callback(self, model_name: str, callback: Callable):
        """Register training function for a model"""
        self._training_callbacks[model_name] = callback
        logger.info(f"Registered training callback for {model_name}")
    
    def record_metrics(self, model_name: str, metrics: PerformanceMetrics):
        """Record production metrics for drift/degradation detection"""
        if model_name not in self.metrics_history:
            self.metrics_history[model_name] = []
        self.metrics_history[model_name].append(metrics)
        
        max_history = 1000
        if len(self.metrics_history[model_name]) > max_history:
            self.metrics_history[model_name] = self.metrics_history[model_name][-max_history:]
    
    def record_feedback(self, model_name: str, case_id: str, 
                        feedback_type: str, feedback_value: Any):
        """Record case-level feedback for models"""
        if model_name not in self.feedback_buffer:
            self.feedback_buffer[model_name] = []
        
        self.feedback_buffer[model_name].append({
            "case_id": case_id,
            "feedback_type": feedback_type,
            "feedback_value": feedback_value,
            "recorded_at": datetime.utcnow().isoformat(),
        })
    
    def record_new_data(self, model_name: str, n_samples: int):
        """Record new data samples for volume-based triggers"""
        if model_name not in self.data_volume_tracker:
            self.data_volume_tracker[model_name] = 0
        self.data_volume_tracker[model_name] += n_samples
    
    def reset_data_volume(self, model_name: str):
        """Reset data volume tracker after retraining"""
        self.data_volume_tracker[model_name] = 0
    
    def evaluate_triggers(self) -> List[RetrainingTrigger]:
        """Evaluate all triggers and return those that should fire"""
        triggered = []
        now = datetime.utcnow()
        
        for trigger in self.triggers.values():
            if not trigger.is_active:
                continue
            
            if trigger.last_triggered_at:
                cooldown_end = trigger.last_triggered_at + timedelta(hours=trigger.cooldown_hours)
                if now < cooldown_end:
                    continue
            
            should_trigger = False
            trigger_reason = ""
            
            if trigger.trigger_type == RetrainingTriggerType.PERFORMANCE_DEGRADATION:
                should_trigger, trigger_reason = self._check_performance_degradation(trigger)
            
            elif trigger.trigger_type == RetrainingTriggerType.DRIFT_DETECTED:
                should_trigger, trigger_reason = self._check_drift(trigger)
            
            elif trigger.trigger_type == RetrainingTriggerType.CASE_FEEDBACK:
                should_trigger, trigger_reason = self._check_feedback(trigger)
            
            elif trigger.trigger_type == RetrainingTriggerType.NEW_DATA_VOLUME:
                should_trigger, trigger_reason = self._check_data_volume(trigger)
            
            elif trigger.trigger_type == RetrainingTriggerType.SCHEDULED:
                should_trigger, trigger_reason = self._check_schedule(trigger)
            
            if should_trigger:
                logger.info(f"Trigger fired: {trigger.trigger_name}. Reason: {trigger_reason}")
                triggered.append(trigger)
        
        return triggered
    
    def _check_performance_degradation(self, trigger: RetrainingTrigger) -> Tuple[bool, str]:
        """Check if model performance has degraded"""
        metrics = self.metrics_history.get(trigger.model_name, [])
        if len(metrics) < 10:
            return False, ""
        
        baseline_cutoff = datetime.utcnow() - timedelta(hours=trigger.baseline_window_hours)
        baseline = [m for m in metrics if m.computed_at < baseline_cutoff]
        recent = [m for m in metrics if m.computed_at >= baseline_cutoff]
        
        if not baseline or not recent:
            return False, ""
        
        metric_attr = trigger.performance_metric
        baseline_values = [getattr(m, metric_attr, None) for m in baseline]
        recent_values = [getattr(m, metric_attr, None) for m in recent]
        
        baseline_values = [v for v in baseline_values if v is not None]
        recent_values = [v for v in recent_values if v is not None]
        
        if not baseline_values or not recent_values:
            return False, ""
        
        baseline_avg = np.mean(baseline_values)
        recent_avg = np.mean(recent_values)
        
        if baseline_avg == 0:
            return False, ""
        
        degradation_pct = ((baseline_avg - recent_avg) / baseline_avg) * 100
        
        if degradation_pct >= trigger.degradation_threshold_pct:
            return True, f"{metric_attr} degraded {degradation_pct:.1f}% (threshold: {trigger.degradation_threshold_pct}%)"
        
        return False, ""
    
    def _check_drift(self, trigger: RetrainingTrigger) -> Tuple[bool, str]:
        """Check for data/concept drift using PSI approximation"""
        metrics = self.metrics_history.get(trigger.model_name, [])
        if len(metrics) < 20:
            return False, ""
        
        recent = metrics[-10:]
        older = metrics[-20:-10]
        
        recent_acc = [m.accuracy for m in recent if m.accuracy is not None]
        older_acc = [m.accuracy for m in older if m.accuracy is not None]
        
        if not recent_acc or not older_acc:
            return False, ""
        
        diff = abs(np.mean(recent_acc) - np.mean(older_acc))
        
        # Calculate PSI approximation
        psi = self._calculate_psi(older_acc, recent_acc)
        
        if psi > trigger.drift_threshold:
            return True, f"PSI={psi:.3f} (threshold: {trigger.drift_threshold})"
        
        return False, ""
    
    def _calculate_psi(self, expected: List[float], actual: List[float], bins: int = 10) -> float:
        """Calculate Population Stability Index"""
        if len(expected) < bins or len(actual) < bins:
            return 0.0
        
        # Create bins from expected distribution
        min_val = min(min(expected), min(actual))
        max_val = max(max(expected), max(actual))
        bin_edges = np.linspace(min_val, max_val, bins + 1)
        
        expected_hist, _ = np.histogram(expected, bins=bin_edges)
        actual_hist, _ = np.histogram(actual, bins=bin_edges)
        
        # Normalize to proportions
        expected_prop = (expected_hist + 0.001) / (sum(expected_hist) + 0.001 * bins)
        actual_prop = (actual_hist + 0.001) / (sum(actual_hist) + 0.001 * bins)
        
        # Calculate PSI
        psi = np.sum((actual_prop - expected_prop) * np.log(actual_prop / expected_prop))
        return psi
    
    def _check_feedback(self, trigger: RetrainingTrigger) -> Tuple[bool, str]:
        """Check case feedback for retraining signal"""
        feedback = self.feedback_buffer.get(trigger.model_name, [])
        if len(feedback) < trigger.min_feedback_count:
            return False, ""
        
        negative_count = sum(
            1 for f in feedback 
            if f.get("feedback_type") == "negative" or f.get("feedback_value") == False
        )
        
        negative_pct = (negative_count / len(feedback)) * 100
        
        if negative_pct >= trigger.negative_feedback_threshold_pct:
            return True, f"Negative feedback: {negative_pct:.1f}% (threshold: {trigger.negative_feedback_threshold_pct}%)"
        
        return False, ""
    
    def _check_data_volume(self, trigger: RetrainingTrigger) -> Tuple[bool, str]:
        """Check if enough new data has accumulated"""
        volume = self.data_volume_tracker.get(trigger.model_name, 0)
        
        if volume >= trigger.min_new_samples:
            return True, f"New data: {volume} samples (threshold: {trigger.min_new_samples})"
        
        return False, ""
    
    def _check_schedule(self, trigger: RetrainingTrigger) -> Tuple[bool, str]:
        """Check scheduled retraining (simplified cron check)"""
        if not trigger.cron_expression:
            return False, ""
        
        # Simplified: check if enough time has passed since last trigger
        if trigger.last_triggered_at:
            # Parse simple cron patterns
            parts = trigger.cron_expression.split()
            if len(parts) >= 5:
                # Check day of week (0 = Sunday)
                day_of_week = parts[4]
                if day_of_week == "*" or str(datetime.utcnow().weekday()) == day_of_week:
                    hours_since = (datetime.utcnow() - trigger.last_triggered_at).total_seconds() / 3600
                    if hours_since >= 168:  # Weekly
                        return True, "Scheduled retraining"
        else:
            return True, "Initial scheduled retraining"
        
        return False, ""
    
    def create_retraining_job(self, trigger: RetrainingTrigger, 
                              manual_by: Optional[str] = None) -> RetrainingJob:
        """Create a new retraining job"""
        current_prod = self.model_registry.get_production_model(trigger.model_name)
        
        job = RetrainingJob(
            job_id=str(uuid.uuid4())[:12],
            model_name=trigger.model_name,
            trigger_id=trigger.trigger_id if not manual_by else None,
            trigger_type=trigger.trigger_type if not manual_by else RetrainingTriggerType.MANUAL,
            created_at=datetime.utcnow(),
            parent_version_id=current_prod.version_id if current_prod else None,
        )
        
        if current_prod and current_prod.production_metrics:
            job.baseline_metrics = current_prod.production_metrics
        
        self.jobs[job.job_id] = job
        
        if not manual_by:
            trigger.last_triggered_at = datetime.utcnow()
        
        self.audit_logger.log(
            action_type="retraining_job_created",
            actor_id=manual_by or "system",
            parameters={
                "job_id": job.job_id,
                "model_name": trigger.model_name,
                "trigger_type": job.trigger_type.value,
            },
        )
        
        logger.info(f"Created retraining job: {job.job_id} for {trigger.model_name}")
        return job
    
    def create_manual_job(self, model_name: str, created_by: str) -> RetrainingJob:
        """Create a manual retraining job"""
        current_prod = self.model_registry.get_production_model(model_name)
        
        job = RetrainingJob(
            job_id=str(uuid.uuid4())[:12],
            model_name=model_name,
            trigger_id=None,
            trigger_type=RetrainingTriggerType.MANUAL,
            created_at=datetime.utcnow(),
            parent_version_id=current_prod.version_id if current_prod else None,
        )
        
        if current_prod and current_prod.production_metrics:
            job.baseline_metrics = current_prod.production_metrics
        
        self.jobs[job.job_id] = job
        
        self.audit_logger.log(
            action_type="manual_retraining_job_created",
            actor_id=created_by,
            parameters={
                "job_id": job.job_id,
                "model_name": model_name,
            },
        )
        
        logger.info(f"Created manual retraining job: {job.job_id} for {model_name}")
        return job
    
    def execute_retraining_job(self, job_id: str) -> Tuple[bool, str]:
        """Execute a retraining job"""
        job = self.jobs.get(job_id)
        if not job:
            return False, "Job not found"
        
        if job.status != "pending":
            return False, f"Job already in {job.status} status"
        
        job.status = "running"
        job.started_at = datetime.utcnow()
        
        try:
            callback = self._training_callbacks.get(job.model_name)
            if not callback:
                raise ValueError(f"No training callback for {job.model_name}")
            
            new_version, new_metrics = callback(job)
            
            job.new_version_id = new_version.version_id
            job.new_metrics = new_metrics
            
            if job.baseline_metrics and new_metrics:
                model_type = new_version.model_type
                job.improvement_detected = new_metrics.is_better_than(
                    job.baseline_metrics, model_type
                )
            
            job.status = "completed"
            job.completed_at = datetime.utcnow()
            
            # Reset data volume tracker
            self.reset_data_volume(job.model_name)
            
            # Clear feedback buffer
            if job.model_name in self.feedback_buffer:
                self.feedback_buffer[job.model_name] = []
            
            self.audit_logger.log(
                action_type="retraining_job_completed",
                actor_id="system",
                parameters={
                    "job_id": job_id,
                    "new_version_id": job.new_version_id,
                    "improvement": job.improvement_detected,
                },
            )
            
            logger.info(f"Completed retraining job: {job_id}. Improvement: {job.improvement_detected}")
            return True, "Training completed"
            
        except Exception as e:
            job.status = "failed"
            job.error_message = str(e)
            job.completed_at = datetime.utcnow()
            
            self.audit_logger.log(
                action_type="retraining_job_failed",
                actor_id="system",
                parameters={
                    "job_id": job_id,
                    "error": str(e),
                },
            )
            
            logger.error(f"Retraining job {job_id} failed: {e}")
            return False, str(e)
    
    def cancel_job(self, job_id: str, cancelled_by: str) -> Tuple[bool, str]:
        """Cancel a pending retraining job"""
        job = self.jobs.get(job_id)
        if not job:
            return False, "Job not found"
        
        if job.status != "pending":
            return False, f"Cannot cancel job in {job.status} status"
        
        job.status = "cancelled"
        job.completed_at = datetime.utcnow()
        
        self.audit_logger.log(
            action_type="retraining_job_cancelled",
            actor_id=cancelled_by,
            parameters={"job_id": job_id},
        )
        
        return True, "Job cancelled"
    
    def get_job(self, job_id: str) -> Optional[RetrainingJob]:
        """Get job by ID"""
        return self.jobs.get(job_id)
    
    def list_jobs(self, model_name: Optional[str] = None,
                  status: Optional[str] = None,
                  limit: int = 20) -> List[RetrainingJob]:
        """List retraining jobs with optional filters"""
        results = list(self.jobs.values())
        
        if model_name:
            results = [j for j in results if j.model_name == model_name]
        if status:
            results = [j for j in results if j.status == status]
        
        results.sort(key=lambda j: j.created_at, reverse=True)
        return results[:limit]
    
    def get_trigger_status(self) -> List[Dict[str, Any]]:
        """Get status of all triggers"""
        status = []
        for trigger in self.triggers.values():
            status.append({
                "trigger_id": trigger.trigger_id,
                "trigger_name": trigger.trigger_name,
                "model_name": trigger.model_name,
                "trigger_type": trigger.trigger_type.value,
                "is_active": trigger.is_active,
                "last_triggered": trigger.last_triggered_at.isoformat() if trigger.last_triggered_at else None,
                "cooldown_remaining_hours": self._get_cooldown_remaining(trigger),
            })
        return status
    
    def _get_cooldown_remaining(self, trigger: RetrainingTrigger) -> Optional[float]:
        """Get remaining cooldown hours for a trigger"""
        if not trigger.last_triggered_at:
            return 0
        
        cooldown_end = trigger.last_triggered_at + timedelta(hours=trigger.cooldown_hours)
        remaining = (cooldown_end - datetime.utcnow()).total_seconds() / 3600
        return max(0, remaining)
