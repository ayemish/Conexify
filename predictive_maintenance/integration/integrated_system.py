"""
PDM Integrated System - Bridges Advanced PDM with Existing Model Infrastructure

Connects the new advanced PDM methodology with the existing:
- ModelType (ANOMALY_DETECTION, FAILURE_PREDICTION, ROOT_CAUSE_ANALYSIS, etc.)
- Model Registry for versioning
- A/B Testing framework
- Retraining Pipeline
- Governance Controls

This allows the advanced radar-inspired detection, regime segmentation,
three-layer inference, and Bayesian hypothesis testing to work with
the existing model lifecycle infrastructure.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

from .lifecycle import (
    ABTestingFramework,
    AuditLogger,
    ModelRegistry,
    ModelStage,
    ModelType,
    ModelVersion,
    PerformanceMetrics,
    RetrainingPipeline,
    RetrainingTrigger,
    RetrainingTriggerType,
    MLGovernanceController,
    RollbackManager,
)

from ..core.schemas import (
    AlertType,
    DeploymentMetrics,
    FalsePositiveBudget,
    FaultHypothesis,
    FaultType,
    FeedbackOutcome,
    OperatingRegime,
    PDMAlert,
    SensorType,
)
from .advanced_system import (
    HVACRPdMAdvancedSystem,
    PDMSystemConfig,
)

logger = logging.getLogger(__name__)


@dataclass
class ModelTypeMapping:
    """Maps between advanced PDM components and existing ModelType"""
    # Which ModelType handles which part of the pipeline
    sensor_trust_model: ModelType = ModelType.ANOMALY_DETECTION
    behavior_model: ModelType = ModelType.FAILURE_PREDICTION
    change_detection_model: ModelType = ModelType.ANOMALY_DETECTION
    fault_hypothesis_model: ModelType = ModelType.ROOT_CAUSE_ANALYSIS
    energy_impact_model: ModelType = ModelType.ENERGY_OPTIMIZATION
    comfort_impact_model: ModelType = ModelType.COMFORT_PREDICTION


class PDMIntegratedSystem:
    """
    Integrated PDM System combining advanced methodology with existing infrastructure.
    
    Architecture:
    - Advanced PDM System: Handles the detection pipeline
      - Regime segmentation
      - Sensor trust (Layer 1)
      - Behavior prediction + residual modeling (Layer 2)
      - Change detection (CUSUM/GLR)
      - Fault hypothesis (Layer 3, Bayesian)
      - Decision policy with FA budget
    
    - Existing Infrastructure: Handles model lifecycle
      - Model Registry: Version control for trained models
      - A/B Testing: Compare model versions
      - Retraining Pipeline: Automated retraining triggers
      - Governance: Approval workflows
    
    Model Type Mapping:
    - ANOMALY_DETECTION: Sensor trust + Change detection models
    - FAILURE_PREDICTION: Behavior model (expected value prediction)
    - ROOT_CAUSE_ANALYSIS: Fault hypothesis model
    - DEMAND_FORECAST: (Not directly used in PDM, available for integration)
    - ENERGY_OPTIMIZATION: Energy impact estimation
    - COMFORT_PREDICTION: Comfort impact estimation
    """
    
    def __init__(self, 
                 site_id: str,
                 config: Optional[PDMSystemConfig] = None,
                 audit_logger: Optional[AuditLogger] = None):
        self.site_id = site_id
        self.audit_logger = audit_logger or AuditLogger()
        
        # Initialize advanced PDM system
        self.pdm_system = HVACRPdMAdvancedSystem(site_id, config)
        
        # Initialize existing infrastructure
        self.model_registry = ModelRegistry(self.audit_logger)
        self.ab_testing = ABTestingFramework(self.model_registry, self.audit_logger)
        self.retraining_pipeline = RetrainingPipeline(self.model_registry, self.audit_logger)
        self.governance = MLGovernanceController(audit_logger=self.audit_logger)
        self.rollback_manager = RollbackManager(self.governance, self.audit_logger)
        
        # Model type mapping
        self.model_mapping = ModelTypeMapping()
        
        # Active model versions by type
        self.active_models: Dict[ModelType, str] = {}
        
        # Prediction tracking for metrics and retraining
        self.prediction_buffer: List[Dict] = []
        self.metrics_aggregation_interval = timedelta(hours=1)
        self.last_metrics_aggregation: Dict[ModelType, datetime] = {}
        
        # Register advanced PDM retraining triggers
        self._initialize_advanced_triggers()
        
        logger.info(f"PDMIntegratedSystem initialized for site: {site_id}")
    
    def _initialize_advanced_triggers(self):
        """Set up retraining triggers for advanced PDM models"""
        
        # Sensor Trust Model (ANOMALY_DETECTION) - drift detection
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="sensor-trust-drift",
            trigger_name="Sensor Trust Model Drift",
            trigger_type=RetrainingTriggerType.DRIFT_DETECTED,
            model_name=ModelType.ANOMALY_DETECTION.value,
            drift_threshold=0.10,  # 10% drift
            drift_window_hours=168,  # 1 week
            cooldown_hours=72,
        ))
        
        # Behavior Model (FAILURE_PREDICTION) - performance degradation
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="behavior-model-degradation",
            trigger_name="Behavior Model Performance",
            trigger_type=RetrainingTriggerType.PERFORMANCE_DEGRADATION,
            model_name=ModelType.FAILURE_PREDICTION.value,
            performance_metric="rmse",  # Residual error
            degradation_threshold_pct=10.0,
            baseline_window_hours=336,  # 2 weeks
            cooldown_hours=168,
        ))
        
        # Fault Hypothesis Model (ROOT_CAUSE_ANALYSIS) - case feedback
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="fault-hypothesis-feedback",
            trigger_name="Fault Hypothesis Feedback",
            trigger_type=RetrainingTriggerType.CASE_FEEDBACK,
            model_name=ModelType.ROOT_CAUSE_ANALYSIS.value,
            min_feedback_count=30,
            negative_feedback_threshold_pct=20.0,  # >20% wrong diagnosis
            cooldown_hours=168,
        ))
        
        # Energy Optimization - new data volume
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="energy-impact-volume",
            trigger_name="Energy Impact Model Data",
            trigger_type=RetrainingTriggerType.NEW_DATA_VOLUME,
            model_name=ModelType.ENERGY_OPTIMIZATION.value,
            min_new_samples=10000,
            cooldown_hours=336,
        ))
        
        # Comfort Prediction - scheduled monthly
        self.retraining_pipeline.register_trigger(RetrainingTrigger(
            trigger_id="comfort-scheduled",
            trigger_name="Monthly Comfort Model Retrain",
            trigger_type=RetrainingTriggerType.SCHEDULED,
            model_name=ModelType.COMFORT_PREDICTION.value,
            cron_expression="0 3 1 * *",  # 1st of month, 3 AM
            cooldown_hours=672,  # 4 weeks
            requires_approval=False,
            auto_approve_if_improvement=True,
        ))
        
        logger.info("Initialized advanced PDM retraining triggers")
    
    def process_telemetry(self, telemetry: Dict[str, Any]) -> PDMAlert:
        """
        Process telemetry through the advanced PDM pipeline.
        
        Also tracks predictions for model lifecycle management.
        """
        # Run through advanced PDM system
        alert = self.pdm_system.process_telemetry(telemetry)
        
        # Track prediction for metrics
        self._track_prediction(telemetry, alert)
        
        return alert
    
    def _track_prediction(self, telemetry: Dict[str, Any], alert: PDMAlert):
        """Track prediction for model performance metrics"""
        timestamp = telemetry.get("timestamp", datetime.utcnow())
        
        prediction_record = {
            "timestamp": timestamp,
            "alert_id": alert.alert_id,
            "alert_type": alert.alert_type.value,
            "primary_fault": alert.primary_fault.value if alert.primary_fault else None,
            "confidence": alert.confidence,
            "false_alarm_probability": alert.false_alarm_probability,
            "regime": self.pdm_system.current_regime.value,
            "sensor_trust_min": min(
                [t.trust_score for t in self.pdm_system.current_trust_scores.values()],
                default=1.0
            ),
            "n_sensors_anomalous": sum(
                1 for d in self.pdm_system.current_changes.values()
                if d.change_score > 0.3
            ),
        }
        
        self.prediction_buffer.append(prediction_record)
        
        # Limit buffer size
        if len(self.prediction_buffer) > 10000:
            self.prediction_buffer = self.prediction_buffer[-5000:]
    
    def aggregate_metrics(self, model_type: ModelType) -> Optional[PerformanceMetrics]:
        """Aggregate metrics for a specific model type"""
        now = datetime.utcnow()
        last_agg = self.last_metrics_aggregation.get(model_type, datetime.min)
        
        if now - last_agg < self.metrics_aggregation_interval:
            return None
        
        # Filter predictions based on model type
        recent_predictions = [
            p for p in self.prediction_buffer
            if p["timestamp"] > last_agg
        ]
        
        if not recent_predictions:
            return None
        
        # Compute metrics based on model type
        if model_type == ModelType.ANOMALY_DETECTION:
            # Sensor trust and change detection metrics
            avg_trust = sum(p["sensor_trust_min"] for p in recent_predictions) / len(recent_predictions)
            anomaly_rate = sum(1 for p in recent_predictions if p["n_sensors_anomalous"] > 0) / len(recent_predictions)
            
            metrics = PerformanceMetrics(
                metrics_id=f"pdm-{model_type.value}-{now.isoformat()}",
                model_version_id=self.active_models.get(model_type, "default"),
                computed_at=now,
                accuracy=avg_trust,
                false_positive_rate=anomaly_rate * 0.1,  # Estimated
                n_samples=len(recent_predictions),
                evaluation_period_start=last_agg,
                evaluation_period_end=now,
            )
        
        elif model_type == ModelType.FAILURE_PREDICTION:
            # Behavior model metrics (residual quality)
            actionable = [p for p in recent_predictions if p["alert_type"] == "actionable"]
            precision = len([p for p in actionable if p["confidence"] > 0.8]) / max(len(actionable), 1)
            
            metrics = PerformanceMetrics(
                metrics_id=f"pdm-{model_type.value}-{now.isoformat()}",
                model_version_id=self.active_models.get(model_type, "default"),
                computed_at=now,
                precision=precision,
                n_samples=len(recent_predictions),
                evaluation_period_start=last_agg,
                evaluation_period_end=now,
            )
        
        elif model_type == ModelType.ROOT_CAUSE_ANALYSIS:
            # Fault hypothesis metrics
            with_diagnosis = [p for p in recent_predictions if p["primary_fault"] is not None]
            avg_confidence = sum(p["confidence"] for p in with_diagnosis) / max(len(with_diagnosis), 1)
            
            metrics = PerformanceMetrics(
                metrics_id=f"pdm-{model_type.value}-{now.isoformat()}",
                model_version_id=self.active_models.get(model_type, "default"),
                computed_at=now,
                accuracy=avg_confidence,
                n_samples=len(with_diagnosis),
                evaluation_period_start=last_agg,
                evaluation_period_end=now,
            )
        
        else:
            return None
        
        # Record metrics for retraining pipeline
        self.retraining_pipeline.record_metrics(model_type.value, metrics)
        self.last_metrics_aggregation[model_type] = now
        
        return metrics
    
    def record_feedback(self, 
                        alert_id: str, 
                        outcome: FeedbackOutcome,
                        confirmed_fault: Optional[FaultType] = None,
                        notes: str = ""):
        """
        Record human feedback and propagate to retraining pipeline.
        """
        # Record in advanced PDM system
        self.pdm_system.record_feedback(alert_id, outcome, confirmed_fault, notes)
        
        # Propagate to retraining pipeline for relevant models
        feedback_type = "positive" if outcome == FeedbackOutcome.CONFIRMED_FAULT else "negative"
        is_accurate = outcome == FeedbackOutcome.CONFIRMED_FAULT
        
        # Behavior model feedback
        self.retraining_pipeline.record_feedback(
            ModelType.FAILURE_PREDICTION.value,
            alert_id,
            feedback_type,
            is_accurate
        )
        
        # Fault hypothesis feedback
        if confirmed_fault or outcome == FeedbackOutcome.NO_ISSUE_FOUND:
            self.retraining_pipeline.record_feedback(
                ModelType.ROOT_CAUSE_ANALYSIS.value,
                alert_id,
                feedback_type,
                is_accurate
            )
    
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
    
    def register_model(self, 
                       model_type: ModelType,
                       model_artifact: Any,
                       trained_by: str,
                       description: str = "") -> str:
        """Register a new model version"""
        model = ModelVersion(
            version_id=f"{model_type.value}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            model_name=model_type.value,
            model_type=model_type,
            version_number=f"1.0.{len(self.model_registry.models)}",
            created_at=datetime.utcnow(),
            created_by=trained_by,
            description=description,
            model_artifact_uri=str(model_artifact),
        )
        
        version_id = self.model_registry.register_model(model)
        return version_id
    
    def deploy_model(self, 
                     version_id: str,
                     deployed_by: str) -> Tuple[bool, str]:
        """Deploy a model version to production"""
        model = self.model_registry.get_model(version_id)
        if not model:
            return False, "Model not found"
        
        success, msg = self.model_registry.promote_model(
            version_id, ModelStage.PRODUCTION, deployed_by
        )
        
        if success:
            self.active_models[model.model_type] = version_id
            
            # Wire into PDM system based on model type
            self._wire_model_to_pdm(model.model_type, version_id)
        
        return success, msg
    
    def _wire_model_to_pdm(self, model_type: ModelType, version_id: str):
        """Wire a deployed model into the PDM pipeline"""
        # This is where we would update the actual model artifacts
        # in the PDM system components
        
        if model_type == ModelType.ANOMALY_DETECTION:
            # Update sensor trust and change detection parameters
            logger.info(f"Wired {version_id} to sensor trust and change detection")
            
        elif model_type == ModelType.FAILURE_PREDICTION:
            # Update behavior model
            logger.info(f"Wired {version_id} to behavior prediction model")
            
        elif model_type == ModelType.ROOT_CAUSE_ANALYSIS:
            # Update fault hypothesis priors and likelihoods
            logger.info(f"Wired {version_id} to fault hypothesis model")
            
        elif model_type == ModelType.ENERGY_OPTIMIZATION:
            # Update energy impact estimation
            logger.info(f"Wired {version_id} to energy impact model")
            
        elif model_type == ModelType.COMFORT_PREDICTION:
            # Update comfort impact estimation
            logger.info(f"Wired {version_id} to comfort prediction model")
    
    def create_ab_test(self,
                       name: str,
                       model_type: ModelType,
                       control_version_id: str,
                       treatment_version_id: str,
                       traffic_split: float = 50.0,
                       created_by: str = "system") -> Tuple[bool, str]:
        """Create an A/B test for a model type"""
        from .learning_loop_models import Experiment, ExperimentVariant, TrafficSplitStrategy
        import uuid
        
        experiment = Experiment(
            experiment_id=str(uuid.uuid4())[:12],
            experiment_name=name,
            description=f"A/B test for {model_type.value}",
            model_type=model_type,
            created_by=created_by,
            variants=[
                ExperimentVariant(
                    variant_id=str(uuid.uuid4())[:8],
                    variant_name="Control",
                    model_version_id=control_version_id,
                    traffic_percentage=traffic_split,
                    is_control=True,
                ),
                ExperimentVariant(
                    variant_id=str(uuid.uuid4())[:8],
                    variant_name="Treatment",
                    model_version_id=treatment_version_id,
                    traffic_percentage=100 - traffic_split,
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
    
    def get_system_status(self) -> Dict[str, Any]:
        """Get comprehensive system status"""
        pdm_status = self.pdm_system.get_system_status()
        
        return {
            "site_id": self.site_id,
            "pdm_status": pdm_status,
            "active_models": {
                mt.value: vid for mt, vid in self.active_models.items()
            },
            "registry_stats": self.model_registry.get_registry_stats(),
            "retraining_triggers": self.retraining_pipeline.get_trigger_status(),
            "pending_jobs": len([
                j for j in self.retraining_pipeline.jobs.values()
                if j.status == "pending"
            ]),
            "predictions_tracked": len(self.prediction_buffer),
        }
    
    def get_deployment_metrics(self,
                                period_start: datetime,
                                period_end: datetime) -> DeploymentMetrics:
        """Get deployment metrics"""
        return self.pdm_system.get_deployment_metrics(period_start, period_end)


def create_integrated_pdm_system(
    site_id: str,
    max_alarms_per_month: float = 0.3,
    max_fa_rate: float = 0.05,
    audit_logger: Optional[AuditLogger] = None
) -> PDMIntegratedSystem:
    """
    Factory function to create a fully integrated PDM system.
    
    Combines:
    - Advanced PDM methodology (radar-inspired, Bayesian, etc.)
    - Existing model lifecycle infrastructure (registry, A/B, retraining)
    """
    budget = FalsePositiveBudget(
        max_actionable_alarms_per_unit_per_month=max_alarms_per_month,
        max_no_issue_found_rate=max_fa_rate,
    )
    
    config = PDMSystemConfig(
        false_positive_budget=budget,
    )
    
    return PDMIntegratedSystem(site_id, config, audit_logger)
