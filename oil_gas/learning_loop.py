"""
ML Learning Loop System for HVAC R&PdM (Refrigeration & Predictive Maintenance)

Main entry point that exports all learning loop components.

Components:
- Data Models: ModelVersion, Experiment, PerformanceMetrics
- Model Registry: Versioning and lineage tracking
- A/B Testing: Statistical model comparison framework
- Retraining Pipeline: Automated triggers and execution
- Governance Controls: Approval workflows and rollback
- HVACRPdMSystem: Integrated case management

Example Usage:
    from .learning_loop import HVACRPdMSystem, ModelVersion, ModelType
    
    # Initialize system
    system = HVACRPdMSystem(site_id="site-001")
    system.initialize_default_triggers()
    
    # Register a model
    model = ModelVersion(
        version_id="anomaly-v1",
        model_name="anomaly_detection",
        model_type=ModelType.ANOMALY_DETECTION,
        version_number="1.0.0",
        created_at=datetime.utcnow(),
        created_by="ml_engineer",
    )
    system.register_model(model)
    
    # Deploy to production
    system.deploy_model("anomaly-v1", "ml_engineer")
    
    # Get model for prediction (considers A/B tests)
    version_id, variant_id = system.get_model_for_prediction(
        ModelType.ANOMALY_DETECTION, case_id="case-123"
    )
    
    # Record outcome for feedback
    system.record_case_outcome("case-123", "resolved", was_prediction_accurate=True)
    
    # Check retraining triggers
    jobs = system.check_retraining_triggers()
"""

# Data Models
from .learning_loop_models import (
    # Enumerations
    ModelType,
    ModelStage,
    ExperimentStatus,
    TrafficSplitStrategy,
    RetrainingTriggerType,
    ApprovalStatus,
    GovernanceAction,
    # Core Models
    PerformanceMetrics,
    ModelArtifact,
    ModelVersion,
    ExperimentVariant,
    Experiment,
    RetrainingTrigger,
    RetrainingJob,
    GovernanceApproval,
)

# Model Registry
from .learning_loop_registry import ModelRegistry

# A/B Testing Framework
from .learning_loop_abtesting import ABTestingFramework

# Retraining Pipeline
from .learning_loop_retraining import RetrainingPipeline

# Governance Controls
from .learning_loop_governance import (
    MLGovernanceController,
    RollbackManager,
)

# Integrated System
from .learning_loop_hvacr import HVACRPdMSystem

__all__ = [
    # Enumerations
    "ModelType",
    "ModelStage",
    "ExperimentStatus",
    "TrafficSplitStrategy",
    "RetrainingTriggerType",
    "ApprovalStatus",
    "GovernanceAction",
    # Data Models
    "PerformanceMetrics",
    "ModelArtifact",
    "ModelVersion",
    "ExperimentVariant",
    "Experiment",
    "RetrainingTrigger",
    "RetrainingJob",
    "GovernanceApproval",
    # Components
    "ModelRegistry",
    "ABTestingFramework",
    "RetrainingPipeline",
    "MLGovernanceController",
    "RollbackManager",
    # Integrated System
    "HVACRPdMSystem",
]
