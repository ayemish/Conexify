"""
ML Learning Loop - HVACRPdMSystem Integration

Integrated HVAC Refrigeration & Predictive Maintenance System.
Connects ML learning loop with case management and operations.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .learning_loop_models import (
    ApprovalStatus,
    Experiment,
    ExperimentStatus,
    ExperimentVariant,
    GovernanceAction,
    ModelStage,
    ModelType,
    ModelVersion,
    PerformanceMetrics,
    RetrainingTrigger,
    RetrainingTriggerType,
    TrafficSplitStrategy,
)
from .learning_loop_registry import ModelRegistry
from .learning_loop_abtesting import ABTestingFramework
from .learning_loop_retraining import RetrainingPipeline
from .learning_loop_governance import MLGovernanceController, RollbackManager
from .data_plane import Case, CaseState, ActionRiskLevel
from .governance import AuditLogger

logger = logging.getLogger(__name__)


class HVACRPdMSystem:
    """
    Integrated HVAC Refrigeration & Predictive Maintenance System.
    
    Connects:
    - Model Registry for versioning
    - A/B Testing for model comparison
    - Retraining Pipeline for automated updates
    - Governance Controls for approval workflows
    - Case Management for operational integration
    """
    
    def __init__(self, site_id: str, audit_logger: Optional[AuditLogger] = None):
        self.site_id = site_id
        self.audit_logger = audit_logger or AuditLogger()
        
        # Initialize core components
        self.model_registry = ModelRegistry(self.audit_logger)
        self.ab_testing = ABTestingFramework(self.model_registry, self.audit_logger)
        self.retraining_pipeline = RetrainingPipeline(self.model_registry, self.audit_logger)
        self.governance = MLGovernanceController(audit_logger=self.audit_logger)
        self.rollback_manager = RollbackManager(self.governance, self.audit_logger)
        
        # Case integration tracking
        self.case_model_mapping: Dict[str, Dict] = {}  # case_id -> model info
        self.model_case_outcomes: Dict[str, List[Dict]] = {}  # model_version_id -> outcomes
        
        # Active models by type
        self.active_models: Dict[ModelType, str] = {}  # model_type -> version_id
        
        # Prediction tracking for metrics
        self.prediction_buffer: List[Dict] = []
        self.metrics_aggregation_interval = timedelta(hours=1)
        self.last_metrics_aggregation: Dict[str, datetime] = {}
        
        logger.info(f"HVACRPdMSystem initialized for site: {site_id}")
    
    def initialize_default_triggers(self):
        """Set up default retraining triggers for HVACR models"""
        # Anomaly detection - performance degradation
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="perf-anomaly-detection",
            trigger_name="Anomaly Detection Performance",
            trigger_type=RetrainingTriggerType.PERFORMANCE_DEGRADATION,
            model_name=ModelType.ANOMALY_DETECTION.value,
            performance_metric="f1_score",
            degradation_threshold_pct=5.0,
            baseline_window_hours=168,
            cooldown_hours=48,
        ))
        
        # Failure prediction - case feedback
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="feedback-failure-prediction",
            trigger_name="Failure Prediction Feedback",
            trigger_type=RetrainingTriggerType.CASE_FEEDBACK,
            model_name=ModelType.FAILURE_PREDICTION.value,
            min_feedback_count=50,
            negative_feedback_threshold_pct=15.0,
            cooldown_hours=72,
        ))
        
        # Root cause analysis - drift detection
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="drift-rca",
            trigger_name="RCA Drift Detection",
            trigger_type=RetrainingTriggerType.DRIFT_DETECTED,
            model_name=ModelType.ROOT_CAUSE_ANALYSIS.value,
            drift_threshold=0.15,
            drift_window_hours=24,
            cooldown_hours=96,
        ))
        
        # Demand forecast - scheduled weekly
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="scheduled-demand-forecast",
            trigger_name="Weekly Demand Forecast Retrain",
            trigger_type=RetrainingTriggerType.SCHEDULED,
            model_name=ModelType.DEMAND_FORECAST.value,
            cron_expression="0 2 * * 0",  # Sunday 2 AM
            cooldown_hours=168,
            requires_approval=False,
            auto_approve_if_improvement=True,
        ))
        
        # Energy optimization - new data volume
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="volume-energy-optimization",
            trigger_name="Energy Optimization Data Volume",
            trigger_type=RetrainingTriggerType.NEW_DATA_VOLUME,
            model_name=ModelType.ENERGY_OPTIMIZATION.value,
            min_new_samples=50000,
            cooldown_hours=168,
        ))
        
        logger.info("Initialized default retraining triggers")
    
    # =========================================================================
    # Model Registration and Deployment
    # =========================================================================
    
    def register_model(self, model: ModelVersion) -> str:
        """Register a new model version"""
        version_id = self.model_registry.register_model(model)
        return version_id
    
    def deploy_model(self, version_id: str, deployed_by: str,
                     skip_approval: bool = False) -> Tuple[bool, str]:
        """Deploy a model to production with governance checks"""
        model = self.model_registry.get_model(version_id)
        if not model:
            return False, "Model not found"
        
        context = {
            "target_stage": ModelStage.PRODUCTION.value,
            "has_validation_metrics": model.validation_metrics is not None,
            "has_staging_validation": model.stage in [ModelStage.STAGING, ModelStage.CANARY],
            "has_canary_validation": model.stage == ModelStage.CANARY,
        }
        
        if skip_approval:
            # Skip governance validation when approval is bypassed (for testing/emergency)
            if not context["has_validation_metrics"]:
                return False, "Model must have validation metrics before deployment"
        else:
            # Validate with full governance
            valid, msg = self.governance.validate_action(
                GovernanceAction.MODEL_DEPLOY, deployed_by, context
            )
            if not valid:
                return False, msg
        
        if not skip_approval:
            # Request approval
            risk = self.governance.assess_risk(GovernanceAction.MODEL_DEPLOY, context)
            approval = self.governance.request_approval(
                action_type=GovernanceAction.MODEL_DEPLOY,
                target_id=version_id,
                target_type="model_version",
                requested_by=deployed_by,
                action_details=context,
                risk_level=risk,
            )
            
            if approval.status not in [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED]:
                return False, f"Deployment pending approval: {approval.approval_id}"
        
        # Promote to production
        success, msg = self.model_registry.promote_model(
            version_id, ModelStage.PRODUCTION, deployed_by
        )
        
        if success:
            self.active_models[model.model_type] = version_id
        
        return success, msg
    
    def rollback_model(self, model_name: str, reason: str,
                       rolled_back_by: str) -> Tuple[bool, str]:
        """Rollback to previous production model"""
        current = self.model_registry.get_production_model(model_name)
        if not current:
            return False, "No production model found"
        
        if not current.can_rollback_to:
            return False, "No rollback target available"
        
        target_id = current.can_rollback_to[-1]  # Most recent previous version
        
        # Initiate rollback with governance
        success, msg, approval_id = self.rollback_manager.initiate_rollback(
            model_name=model_name,
            from_version_id=current.version_id,
            to_version_id=target_id,
            reason=reason,
            initiated_by=rolled_back_by,
        )
        
        if not success and approval_id:
            return False, f"Rollback pending approval: {approval_id}"
        
        if success:
            # Execute rollback
            return self.rollback_manager.execute_rollback(
                approval_id=approval_id,
                executed_by=rolled_back_by,
                rollback_func=self.model_registry.rollback_model,
            )
        
        return success, msg
    
    # =========================================================================
    # Prediction and Case Integration
    # =========================================================================
    
    def get_model_for_prediction(self, model_type: ModelType,
                                 case_id: Optional[str] = None) -> Tuple[str, Optional[str]]:
        """
        Get model version for prediction, considering active experiments.
        Returns (model_version_id, experiment_variant_id or None)
        """
        entity_id = case_id or self.site_id
        
        try:
            return self.ab_testing.get_model_for_prediction(model_type, entity_id)
        except ValueError:
            # No experiment, check active models
            if model_type in self.active_models:
                return self.active_models[model_type], None
            
            # Fall back to registry
            prod = self.model_registry.get_production_model(model_type.value)
            if prod:
                return prod.version_id, None
            
            raise ValueError(f"No model available for {model_type.value}")
    
    def record_prediction(self, model_version_id: str, case_id: str,
                          prediction: Any, actual: Optional[Any] = None,
                          is_correct: Optional[bool] = None,
                          metrics: Optional[Dict[str, float]] = None,
                          experiment_variant_id: Optional[str] = None):
        """Record a prediction for metrics tracking"""
        record = {
            "model_version_id": model_version_id,
            "case_id": case_id,
            "prediction": prediction,
            "actual": actual,
            "is_correct": is_correct,
            "metrics": metrics or {},
            "timestamp": datetime.utcnow().isoformat(),
            "experiment_variant_id": experiment_variant_id,
        }
        
        self.prediction_buffer.append(record)
        
        # Track case-model mapping
        self.case_model_mapping[case_id] = {
            "model_version_id": model_version_id,
            "model_type": self.model_registry.get_model(model_version_id).model_type.value
                         if self.model_registry.get_model(model_version_id) else None,
            "experiment_variant_id": experiment_variant_id,
            "prediction_time": datetime.utcnow().isoformat(),
        }
        
        # Update experiment if applicable
        if experiment_variant_id:
            model = self.model_registry.get_model(model_version_id)
            if model:
                active_exp = self.ab_testing.get_active_experiment(model.model_type)
                if active_exp and is_correct is not None:
                    self.ab_testing.record_prediction(
                        active_exp.experiment_id, 
                        experiment_variant_id,
                        is_correct,
                        metrics,
                    )
    
    def record_case_outcome(self, case_id: str, outcome: str,
                            was_prediction_accurate: bool,
                            feedback_notes: str = ""):
        """Record case outcome for model feedback"""
        mapping = self.case_model_mapping.get(case_id)
        if not mapping:
            return
        
        model_version_id = mapping["model_version_id"]
        model_type = mapping.get("model_type")
        
        # Store outcome
        if model_version_id not in self.model_case_outcomes:
            self.model_case_outcomes[model_version_id] = []
        
        self.model_case_outcomes[model_version_id].append({
            "case_id": case_id,
            "outcome": outcome,
            "accurate": was_prediction_accurate,
            "notes": feedback_notes,
            "recorded_at": datetime.utcnow().isoformat(),
        })
        
        # Record feedback for retraining triggers
        if model_type:
            feedback_type = "positive" if was_prediction_accurate else "negative"
            self.retraining_pipeline.record_feedback(
                model_type, case_id, feedback_type, was_prediction_accurate
            )
        
        # Update experiment if applicable
        if mapping.get("experiment_variant_id"):
            model = self.model_registry.get_model(model_version_id)
            if model:
                active_exp = self.ab_testing.get_active_experiment(model.model_type)
                if active_exp:
                    self.ab_testing.record_case_outcome(
                        active_exp.experiment_id,
                        mapping["experiment_variant_id"],
                        case_id,
                        outcome,
                    )
    
    def integrate_with_case(self, case: Case, model_type: ModelType) -> Dict[str, Any]:
        """
        Integrate ML predictions with case management.
        Returns model info and prediction routing.
        """
        version_id, variant_id = self.get_model_for_prediction(model_type, case.case_id)
        
        integration = {
            "case_id": case.case_id,
            "model_type": model_type.value,
            "model_version_id": version_id,
            "experiment_variant_id": variant_id,
            "in_experiment": variant_id is not None,
        }
        
        model = self.model_registry.get_model(version_id)
        if model:
            integration["model_version_number"] = model.version_number
            integration["model_stage"] = model.stage.value
        
        return integration
    
    # =========================================================================
    # A/B Testing
    # =========================================================================
    
    def create_ab_test(self, name: str, description: str,
                       model_type: ModelType,
                       control_version_id: str,
                       treatment_version_id: str,
                       control_traffic_pct: float = 50.0,
                       created_by: str = "system") -> Tuple[bool, str]:
        """Create a simple A/B test between two model versions"""
        experiment = Experiment(
            experiment_id=str(uuid.uuid4())[:12],
            experiment_name=name,
            description=description,
            model_type=model_type,
            created_by=created_by,
            variants=[
                ExperimentVariant(
                    variant_id=str(uuid.uuid4())[:8],
                    variant_name="Control",
                    model_version_id=control_version_id,
                    traffic_percentage=control_traffic_pct,
                    is_control=True,
                ),
                ExperimentVariant(
                    variant_id=str(uuid.uuid4())[:8],
                    variant_name="Treatment",
                    model_version_id=treatment_version_id,
                    traffic_percentage=100 - control_traffic_pct,
                    is_control=False,
                ),
            ],
            traffic_split_strategy=TrafficSplitStrategy.STICKY_SITE,
            target_sites=[self.site_id],
        )
        
        try:
            exp_id = self.ab_testing.create_experiment(experiment)
            return True, exp_id
        except ValueError as e:
            return False, str(e)
    
    def start_ab_test(self, experiment_id: str, started_by: str) -> Tuple[bool, str]:
        """Approve and start an A/B test"""
        # Approve first
        success, msg = self.ab_testing.approve_experiment(experiment_id, started_by)
        if not success:
            return False, msg
        
        # Then start
        return self.ab_testing.start_experiment(experiment_id, started_by)
    
    def conclude_ab_test(self, experiment_id: str, concluded_by: str,
                         promote_winner: bool = False) -> Tuple[bool, str]:
        """Conclude an A/B test and optionally promote winner"""
        success, msg = self.ab_testing.conclude_experiment(
            experiment_id, concluded_by
        )
        
        if success and promote_winner:
            exp = self.ab_testing.get_experiment(experiment_id)
            if exp and exp.winner_variant_id:
                # Find winner's model version
                for variant in exp.variants:
                    if variant.variant_id == exp.winner_variant_id:
                        self.deploy_model(variant.model_version_id, concluded_by)
                        break
        
        return success, msg
    
    def get_ab_test_status(self, experiment_id: str) -> Dict[str, Any]:
        """Get current A/B test statistics"""
        return self.ab_testing.compute_experiment_statistics(experiment_id)
    
    # =========================================================================
    # Retraining
    # =========================================================================
    
    def check_retraining_triggers(self) -> List[Dict[str, Any]]:
        """Check all triggers and create jobs for those that fire"""
        triggered = self.retraining_pipeline.evaluate_triggers()
        jobs = []
        
        for trigger in triggered:
            job = self.retraining_pipeline.create_retraining_job(trigger)
            jobs.append({
                "job_id": job.job_id,
                "model_name": trigger.model_name,
                "trigger_type": trigger.trigger_type.value,
                "trigger_name": trigger.trigger_name,
            })
        
        return jobs
    
    def trigger_manual_retrain(self, model_name: str, 
                               triggered_by: str) -> Tuple[bool, str]:
        """Manually trigger a retraining job"""
        job = self.retraining_pipeline.create_manual_job(model_name, triggered_by)
        return True, job.job_id
    
    def register_training_callback(self, model_name: str, callback: Callable):
        """Register training function for automated retraining"""
        self.retraining_pipeline.register_training_callback(model_name, callback)
    
    def execute_retraining(self, job_id: str) -> Tuple[bool, str]:
        """Execute a retraining job"""
        return self.retraining_pipeline.execute_retraining_job(job_id)
    
    # =========================================================================
    # Metrics Aggregation
    # =========================================================================
    
    def aggregate_metrics(self, model_name: str) -> Optional[PerformanceMetrics]:
        """Aggregate buffered predictions into metrics"""
        now = datetime.utcnow()
        last_agg = self.last_metrics_aggregation.get(model_name, datetime.min)
        
        if now - last_agg < self.metrics_aggregation_interval:
            return None
        
        # Filter predictions for this model
        model_preds = [
            p for p in self.prediction_buffer
            if self.model_registry.get_model(p["model_version_id"]) and
               self.model_registry.get_model(p["model_version_id"]).model_name == model_name
        ]
        
        if not model_preds:
            return None
        
        # Calculate metrics
        correct = sum(1 for p in model_preds if p.get("is_correct"))
        total = len(model_preds)
        
        metrics = PerformanceMetrics(
            metrics_id=str(uuid.uuid4())[:12],
            model_version_id=model_preds[0]["model_version_id"],
            computed_at=now,
            accuracy=correct / total if total > 0 else None,
            n_samples=total,
            evaluation_period_start=last_agg,
            evaluation_period_end=now,
        )
        
        # Record for triggers
        self.retraining_pipeline.record_metrics(model_name, metrics)
        
        # Update last aggregation time
        self.last_metrics_aggregation[model_name] = now
        
        # Clear processed predictions
        processed_ids = {p["model_version_id"] for p in model_preds}
        self.prediction_buffer = [
            p for p in self.prediction_buffer
            if p["model_version_id"] not in processed_ids
        ]
        
        return metrics
    
    # =========================================================================
    # System Status
    # =========================================================================
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        return {
            "site_id": self.site_id,
            "active_models": {
                mt.value: vid for mt, vid in self.active_models.items()
            },
            "registry_stats": self.model_registry.get_registry_stats(),
            "governance_stats": self.governance.get_governance_stats(),
            "active_experiments": [
                {
                    "experiment_id": exp.experiment_id,
                    "name": exp.experiment_name,
                    "model_type": exp.model_type.value,
                    "status": exp.status.value,
                }
                for exp in self.ab_testing.active_experiments.values()
            ],
            "retraining_triggers": self.retraining_pipeline.get_trigger_status(),
            "pending_jobs": len([
                j for j in self.retraining_pipeline.jobs.values()
                if j.status == "pending"
            ]),
            "cases_tracked": len(self.case_model_mapping),
            "predictions_buffered": len(self.prediction_buffer),
        }
    
    def get_model_health(self, model_name: str) -> Dict[str, Any]:
        """Get health status for a specific model"""
        prod = self.model_registry.get_production_model(model_name)
        if not prod:
            return {"status": "no_production_model"}
        
        health = {
            "model_name": model_name,
            "version": prod.version_number,
            "stage": prod.stage.value,
            "deployed_at": prod.deployed_at.isoformat() if prod.deployed_at else None,
        }
        
        # Check metrics trend
        metrics = self.retraining_pipeline.metrics_history.get(model_name, [])
        if metrics:
            recent = metrics[-10:] if len(metrics) >= 10 else metrics
            health["recent_accuracy"] = [m.accuracy for m in recent if m.accuracy]
            
            if len(recent) >= 2:
                trend = recent[-1].accuracy - recent[0].accuracy if recent[-1].accuracy and recent[0].accuracy else 0
                health["accuracy_trend"] = "improving" if trend > 0.01 else "degrading" if trend < -0.01 else "stable"
        
        # Check for active experiments
        model_type = prod.model_type
        active_exp = self.ab_testing.get_active_experiment(model_type)
        if active_exp:
            health["in_experiment"] = True
            health["experiment_id"] = active_exp.experiment_id
        else:
            health["in_experiment"] = False
        
        # Check feedback
        feedback = self.retraining_pipeline.feedback_buffer.get(model_name, [])
        if feedback:
            negative = sum(1 for f in feedback if f.get("feedback_type") == "negative")
            health["feedback_count"] = len(feedback)
            health["negative_feedback_pct"] = (negative / len(feedback)) * 100
        
        return health
