"""
ML Learning Loop - Data Models

Data models for ModelVersion, Experiment, and PerformanceMetrics.
"""

import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


# =============================================================================
# Enumerations
# =============================================================================

class ModelType(str, Enum):
    """Types of ML models in the system"""
    ANOMALY_DETECTION = "anomaly_detection"
    FAILURE_PREDICTION = "failure_prediction"
    ROOT_CAUSE_ANALYSIS = "root_cause_analysis"
    DEMAND_FORECAST = "demand_forecast"
    ENERGY_OPTIMIZATION = "energy_optimization"
    COMFORT_PREDICTION = "comfort_prediction"


class ModelStage(str, Enum):
    """Model lifecycle stages"""
    DEVELOPMENT = "development"
    STAGING = "staging"
    CANARY = "canary"
    PRODUCTION = "production"
    ARCHIVED = "archived"
    ROLLBACK = "rollback"


class ExperimentStatus(str, Enum):
    """Experiment lifecycle status"""
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TrafficSplitStrategy(str, Enum):
    """A/B test traffic allocation strategies"""
    RANDOM = "random"
    STICKY_USER = "sticky_user"
    STICKY_SITE = "sticky_site"
    ROUND_ROBIN = "round_robin"
    WEIGHTED = "weighted"


class RetrainingTriggerType(str, Enum):
    """Types of retraining triggers"""
    SCHEDULED = "scheduled"
    DRIFT_DETECTED = "drift_detected"
    PERFORMANCE_DEGRADATION = "performance_degradation"
    NEW_DATA_VOLUME = "new_data_volume"
    MANUAL = "manual"
    CASE_FEEDBACK = "case_feedback"


class ApprovalStatus(str, Enum):
    """Approval workflow status"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    AUTO_APPROVED = "auto_approved"
    EXPIRED = "expired"


class GovernanceAction(str, Enum):
    """Governance-controlled actions"""
    MODEL_PROMOTE = "model_promote"
    MODEL_DEPLOY = "model_deploy"
    MODEL_ROLLBACK = "model_rollback"
    EXPERIMENT_START = "experiment_start"
    EXPERIMENT_CONCLUDE = "experiment_conclude"
    RETRAIN_TRIGGER = "retrain_trigger"


# =============================================================================
# Performance Metrics
# =============================================================================

@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics for model evaluation.
    Supports both offline (validation) and online (production) metrics.
    """
    metrics_id: str
    model_version_id: str
    computed_at: datetime
    
    # Classification metrics
    accuracy: Optional[float] = None
    precision: Optional[float] = None
    recall: Optional[float] = None
    f1_score: Optional[float] = None
    auc_roc: Optional[float] = None
    auc_pr: Optional[float] = None
    
    # Regression metrics
    mae: Optional[float] = None
    mse: Optional[float] = None
    rmse: Optional[float] = None
    mape: Optional[float] = None
    r2_score: Optional[float] = None
    
    # Anomaly detection specific
    anomaly_precision: Optional[float] = None
    anomaly_recall: Optional[float] = None
    false_positive_rate: Optional[float] = None
    detection_latency_seconds: Optional[float] = None
    
    # Predictive maintenance specific
    prediction_lead_time_hours: Optional[float] = None
    failure_capture_rate: Optional[float] = None
    mean_time_to_failure_error: Optional[float] = None
    
    # Business metrics
    cases_prevented: int = 0
    estimated_cost_savings: float = 0.0
    sla_improvement_pct: float = 0.0
    
    # Operational metrics
    inference_latency_p50_ms: Optional[float] = None
    inference_latency_p95_ms: Optional[float] = None
    inference_latency_p99_ms: Optional[float] = None
    throughput_qps: Optional[float] = None
    memory_usage_mb: Optional[float] = None
    
    # Data quality
    data_coverage_pct: float = 100.0
    feature_completeness_pct: float = 100.0
    
    # Evaluation metadata
    evaluation_dataset: str = ""
    n_samples: int = 0
    evaluation_period_start: Optional[datetime] = None
    evaluation_period_end: Optional[datetime] = None
    confidence_level: float = 0.95
    metrics_ci: Dict[str, Tuple[float, float]] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metrics_id": self.metrics_id,
            "model_version_id": self.model_version_id,
            "computed_at": self.computed_at.isoformat(),
            "accuracy": self.accuracy,
            "precision": self.precision,
            "recall": self.recall,
            "f1_score": self.f1_score,
            "auc_roc": self.auc_roc,
            "mae": self.mae,
            "rmse": self.rmse,
            "inference_latency_p95_ms": self.inference_latency_p95_ms,
            "n_samples": self.n_samples,
        }
    
    def get_primary_metric(self, model_type: ModelType) -> Optional[float]:
        """Get the primary metric for a given model type"""
        metric_map = {
            ModelType.ANOMALY_DETECTION: self.auc_roc or self.f1_score,
            ModelType.FAILURE_PREDICTION: self.failure_capture_rate or self.recall,
            ModelType.ROOT_CAUSE_ANALYSIS: self.accuracy,
            ModelType.DEMAND_FORECAST: self.mape,
            ModelType.ENERGY_OPTIMIZATION: self.mae,
            ModelType.COMFORT_PREDICTION: self.rmse,
        }
        return metric_map.get(model_type)
    
    def is_better_than(self, other: "PerformanceMetrics", model_type: ModelType, 
                       min_improvement_pct: float = 0.0) -> bool:
        """Compare if this metric set is better than another"""
        self_metric = self.get_primary_metric(model_type)
        other_metric = other.get_primary_metric(model_type)
        
        if self_metric is None or other_metric is None:
            return False
        
        lower_is_better = model_type in [
            ModelType.DEMAND_FORECAST, 
            ModelType.ENERGY_OPTIMIZATION,
            ModelType.COMFORT_PREDICTION,
        ]
        
        if lower_is_better:
            improvement = (other_metric - self_metric) / other_metric * 100
        else:
            improvement = (self_metric - other_metric) / other_metric * 100
        
        return improvement >= min_improvement_pct


# =============================================================================
# Model Version
# =============================================================================

@dataclass
class ModelArtifact:
    """Reference to model binary artifacts"""
    artifact_id: str
    artifact_type: str  # weights, checkpoint, onnx, tensorrt
    storage_uri: str
    size_bytes: int
    checksum_sha256: str
    created_at: datetime
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ModelVersion:
    """
    Versioned ML model with full lineage tracking.
    """
    version_id: str
    model_name: str
    model_type: ModelType
    version_number: str  # Semantic versioning: major.minor.patch
    
    # Lineage
    created_at: datetime
    created_by: str
    parent_version_id: Optional[str] = None
    
    # Stage and status
    stage: ModelStage = ModelStage.DEVELOPMENT
    is_active: bool = True
    
    # Training details
    training_job_id: Optional[str] = None
    training_started_at: Optional[datetime] = None
    training_completed_at: Optional[datetime] = None
    training_duration_minutes: Optional[float] = None
    
    # Data lineage
    training_data_version: Optional[str] = None
    training_data_hash: Optional[str] = None
    feature_set_version: Optional[str] = None
    n_training_samples: int = 0
    n_validation_samples: int = 0
    
    # Configuration
    hyperparameters: Dict[str, Any] = field(default_factory=dict)
    feature_config: Dict[str, Any] = field(default_factory=dict)
    preprocessing_config: Dict[str, Any] = field(default_factory=dict)
    
    # Artifacts
    artifacts: List[ModelArtifact] = field(default_factory=list)
    
    # Performance
    validation_metrics: Optional[PerformanceMetrics] = None
    production_metrics: Optional[PerformanceMetrics] = None
    
    # Deployment
    deployed_at: Optional[datetime] = None
    deployed_by: Optional[str] = None
    deployment_config: Dict[str, Any] = field(default_factory=dict)
    serving_endpoints: List[str] = field(default_factory=list)
    
    # Governance
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    approval_notes: str = ""
    
    # Metadata
    tags: List[str] = field(default_factory=list)
    description: str = ""
    changelog: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Rollback support
    can_rollback_to: List[str] = field(default_factory=list)
    rolled_back_from: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "version_id": self.version_id,
            "model_name": self.model_name,
            "model_type": self.model_type.value,
            "version_number": self.version_number,
            "stage": self.stage.value,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "created_by": self.created_by,
            "approval_status": self.approval_status.value,
            "n_training_samples": self.n_training_samples,
        }
    
    def get_artifact(self, artifact_type: str) -> Optional[ModelArtifact]:
        """Get artifact by type"""
        for artifact in self.artifacts:
            if artifact.artifact_type == artifact_type:
                return artifact
        return None


# =============================================================================
# Experiment
# =============================================================================

@dataclass
class ExperimentVariant:
    """A/B test variant configuration"""
    variant_id: str
    variant_name: str
    model_version_id: str
    traffic_percentage: float  # 0-100
    is_control: bool = False
    
    n_predictions: int = 0
    n_correct_predictions: int = 0
    accumulated_metrics: Dict[str, float] = field(default_factory=dict)
    cases_handled: List[str] = field(default_factory=list)
    case_outcomes: Dict[str, str] = field(default_factory=dict)


@dataclass
class Experiment:
    """A/B testing experiment for model comparison."""
    experiment_id: str
    experiment_name: str
    description: str
    
    model_type: ModelType
    variants: List[ExperimentVariant] = field(default_factory=list)
    traffic_split_strategy: TrafficSplitStrategy = TrafficSplitStrategy.RANDOM
    
    target_sites: List[str] = field(default_factory=list)
    target_equipment_types: List[str] = field(default_factory=list)
    
    created_at: datetime = field(default_factory=datetime.utcnow)
    created_by: str = ""
    scheduled_start: Optional[datetime] = None
    scheduled_end: Optional[datetime] = None
    actual_start: Optional[datetime] = None
    actual_end: Optional[datetime] = None
    
    status: ExperimentStatus = ExperimentStatus.DRAFT
    
    # Statistical configuration
    primary_metric: str = "accuracy"
    minimum_detectable_effect: float = 0.02
    confidence_level: float = 0.95
    statistical_power: float = 0.80
    min_sample_size_per_variant: int = 1000
    
    # Auto-conclusion
    auto_conclude_on_significance: bool = True
    max_duration_days: int = 30
    early_stopping_enabled: bool = True
    early_stopping_threshold: float = 0.01
    
    # Governance
    approval_status: ApprovalStatus = ApprovalStatus.PENDING
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    
    # Results
    winner_variant_id: Optional[str] = None
    conclusion_reason: str = ""
    final_p_value: Optional[float] = None
    effect_size: Optional[float] = None
    
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "experiment_id": self.experiment_id,
            "experiment_name": self.experiment_name,
            "status": self.status.value,
            "model_type": self.model_type.value,
            "n_variants": len(self.variants),
            "primary_metric": self.primary_metric,
            "approval_status": self.approval_status.value,
            "winner_variant_id": self.winner_variant_id,
        }
    
    def get_control_variant(self) -> Optional[ExperimentVariant]:
        """Get the control variant"""
        for v in self.variants:
            if v.is_control:
                return v
        return None
    
    def get_variant_for_entity(self, entity_id: str) -> ExperimentVariant:
        """Assign an entity to a variant based on traffic split strategy"""
        if self.traffic_split_strategy in [TrafficSplitStrategy.STICKY_USER, TrafficSplitStrategy.STICKY_SITE]:
            hash_val = int(hashlib.md5(entity_id.encode()).hexdigest(), 16)
            bucket = hash_val % 100
        else:
            bucket = np.random.randint(0, 100)
        
        cumulative = 0
        for variant in self.variants:
            cumulative += variant.traffic_percentage
            if bucket < cumulative:
                return variant
        
        return self.variants[-1]


# =============================================================================
# Retraining
# =============================================================================

@dataclass
class RetrainingTrigger:
    """Configuration for automated retraining triggers"""
    trigger_id: str
    trigger_name: str
    trigger_type: RetrainingTriggerType
    model_name: str
    is_active: bool = True
    
    cron_expression: Optional[str] = None
    drift_threshold: float = 0.1
    drift_window_hours: int = 24
    drift_metric: str = "psi"
    performance_metric: str = "accuracy"
    degradation_threshold_pct: float = 5.0
    baseline_window_hours: int = 168
    min_new_samples: int = 10000
    min_feedback_count: int = 100
    negative_feedback_threshold_pct: float = 20.0
    cooldown_hours: int = 24
    last_triggered_at: Optional[datetime] = None
    requires_approval: bool = True
    auto_approve_if_improvement: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trigger_id": self.trigger_id,
            "trigger_name": self.trigger_name,
            "trigger_type": self.trigger_type.value,
            "model_name": self.model_name,
            "is_active": self.is_active,
        }


@dataclass
class RetrainingJob:
    """Tracking for a retraining job execution"""
    job_id: str
    model_name: str
    trigger_id: Optional[str]
    trigger_type: RetrainingTriggerType
    
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    status: str = "pending"
    error_message: Optional[str] = None
    
    parent_version_id: Optional[str] = None
    training_data_version: str = ""
    new_version_id: Optional[str] = None
    
    baseline_metrics: Optional[PerformanceMetrics] = None
    new_metrics: Optional[PerformanceMetrics] = None
    improvement_detected: bool = False
    approval_status: ApprovalStatus = ApprovalStatus.PENDING


# =============================================================================
# Governance
# =============================================================================

@dataclass
class GovernanceApproval:
    """Approval request for governance-controlled actions"""
    approval_id: str
    action_type: GovernanceAction
    requested_at: datetime
    requested_by: str
    
    target_id: str
    target_type: str
    
    action_details: Dict[str, Any] = field(default_factory=dict)
    risk_level: str = "medium"
    
    status: ApprovalStatus = ApprovalStatus.PENDING
    reviewed_by: Optional[str] = None
    reviewed_at: Optional[datetime] = None
    review_notes: str = ""
    expires_at: Optional[datetime] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "approval_id": self.approval_id,
            "action_type": self.action_type.value,
            "status": self.status.value,
            "target_id": self.target_id,
            "risk_level": self.risk_level,
            "requested_at": self.requested_at.isoformat(),
        }


# =============================================================================
# Minimal Infrastructure Classes (Registry, A/B, Retraining, Governance)
# =============================================================================

class AuditLogger:
    """Lightweight audit logger used by lifecycle components."""

    def __init__(self):
        self.events: List[Dict[str, Any]] = []

    def log_event(self, action: str, details: Dict[str, Any], actor: str = "system"):
        self.events.append({
            "event_id": str(uuid.uuid4())[:12],
            "action": action,
            "actor": actor,
            "timestamp": datetime.utcnow().isoformat(),
            "details": details,
        })


class ModelRegistry:
    """In-memory model registry with basic promotion and lookup."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.audit_logger = audit_logger or AuditLogger()
        self.models: Dict[str, ModelVersion] = {}

    def register_model(self, model: ModelVersion) -> str:
        self.models[model.version_id] = model
        self.audit_logger.log_event("model.registered", {"version_id": model.version_id})
        return model.version_id

    def get_model(self, version_id: str) -> Optional[ModelVersion]:
        return self.models.get(version_id)

    def promote_model(self, version_id: str, stage: ModelStage, promoted_by: str) -> Tuple[bool, str]:
        model = self.get_model(version_id)
        if not model:
            return False, "Model not found"
        model.stage = stage
        if stage == ModelStage.PRODUCTION:
            model.deployed_at = datetime.utcnow()
            model.deployed_by = promoted_by
        self.audit_logger.log_event("model.promoted", {"version_id": version_id, "stage": stage.value}, promoted_by)
        return True, "Model promoted"

    def get_registry_stats(self) -> Dict[str, Any]:
        by_stage: Dict[str, int] = {}
        for m in self.models.values():
            by_stage[m.stage.value] = by_stage.get(m.stage.value, 0) + 1
        return {
            "total_models": len(self.models),
            "by_stage": by_stage,
        }


class ABTestingFramework:
    """Minimal A/B testing registry."""

    def __init__(self, model_registry: ModelRegistry, audit_logger: Optional[AuditLogger] = None):
        self.model_registry = model_registry
        self.audit_logger = audit_logger or AuditLogger()
        self.experiments: Dict[str, Any] = {}

    def create_experiment(self, experiment: Any) -> str:
        exp_id = getattr(experiment, "experiment_id", None)
        if not exp_id:
            raise ValueError("Experiment missing experiment_id")
        if exp_id in self.experiments:
            raise ValueError("Experiment already exists")
        self.experiments[exp_id] = experiment
        self.audit_logger.log_event("experiment.created", {"experiment_id": exp_id})
        return exp_id


class RetrainingPipeline:
    """Minimal retraining pipeline with trigger tracking."""

    def __init__(self, model_registry: ModelRegistry, audit_logger: Optional[AuditLogger] = None):
        self.model_registry = model_registry
        self.audit_logger = audit_logger or AuditLogger()
        self.triggers: Dict[str, RetrainingTrigger] = {}
        self.jobs: Dict[str, RetrainingJob] = {}
        self.metrics_history: Dict[str, List[PerformanceMetrics]] = {}
        self.feedback_events: List[Dict[str, Any]] = []

    def register_trigger(self, trigger: RetrainingTrigger):
        self.triggers[trigger.trigger_id] = trigger
        self.audit_logger.log_event("retraining.trigger_registered", {"trigger_id": trigger.trigger_id})

    def record_metrics(self, model_name: str, metrics: PerformanceMetrics):
        self.metrics_history.setdefault(model_name, []).append(metrics)

    def record_feedback(self, model_name: str, alert_id: str, feedback_type: str, is_accurate: bool):
        self.feedback_events.append({
            "model_name": model_name,
            "alert_id": alert_id,
            "feedback_type": feedback_type,
            "is_accurate": is_accurate,
            "timestamp": datetime.utcnow().isoformat(),
        })

    def evaluate_triggers(self) -> List[RetrainingTrigger]:
        # Placeholder: real implementation would evaluate drift/perf thresholds
        return []

    def create_retraining_job(self, trigger: RetrainingTrigger) -> RetrainingJob:
        job = RetrainingJob(
            job_id=str(uuid.uuid4())[:12],
            model_name=trigger.model_name,
            trigger_id=trigger.trigger_id,
            trigger_type=trigger.trigger_type,
            created_at=datetime.utcnow(),
        )
        self.jobs[job.job_id] = job
        self.audit_logger.log_event("retraining.job_created", {"job_id": job.job_id})
        return job

    def get_trigger_status(self) -> List[Dict[str, Any]]:
        return [
            {
                "trigger_id": t.trigger_id,
                "trigger_name": t.trigger_name,
                "trigger_type": t.trigger_type.value,
                "model_name": t.model_name,
            }
            for t in self.triggers.values()
        ]


class MLGovernanceController:
    """Minimal governance controller."""

    def __init__(self, audit_logger: Optional[AuditLogger] = None):
        self.audit_logger = audit_logger or AuditLogger()
        self.approvals: Dict[str, GovernanceApproval] = {}

    def request_approval(self, approval: GovernanceApproval) -> str:
        self.approvals[approval.approval_id] = approval
        self.audit_logger.log_event("governance.approval_requested", approval.to_dict())
        return approval.approval_id


class RollbackManager:
    """Minimal rollback manager placeholder."""

    def __init__(self, governance: MLGovernanceController, audit_logger: Optional[AuditLogger] = None):
        self.governance = governance
        self.audit_logger = audit_logger or AuditLogger()

    def request_rollback(self, target_id: str, requested_by: str = "system") -> str:
        approval = GovernanceApproval(
            approval_id=str(uuid.uuid4())[:12],
            action_type=GovernanceAction.MODEL_ROLLBACK,
            requested_at=datetime.utcnow(),
            requested_by=requested_by,
            target_id=target_id,
            target_type="model",
        )
        return self.governance.request_approval(approval)


# Backward-compatible alias
ModelGovernance = MLGovernanceController
