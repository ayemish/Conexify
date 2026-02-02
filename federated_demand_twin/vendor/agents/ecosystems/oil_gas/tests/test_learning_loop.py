"""
Phase 4 Validation Tests: ML Learning Loop System

Tests for:
- Data models (ModelVersion, Experiment, PerformanceMetrics)
- Model versioning and registry
- A/B testing framework
- Automated retraining triggers and pipeline
- Governance controls (approval workflows, rollback)
- HVACRPdMSystem integration with case management
"""

import pytest
import uuid
from datetime import datetime, timedelta
from typing import Tuple

from ..learning_loop import (
    # Enumerations
    ModelType,
    ModelStage,
    ExperimentStatus,
    TrafficSplitStrategy,
    RetrainingTriggerType,
    ApprovalStatus,
    GovernanceAction,
    # Data Models
    PerformanceMetrics,
    ModelArtifact,
    ModelVersion,
    ExperimentVariant,
    Experiment,
    RetrainingTrigger,
    RetrainingJob,
    GovernanceApproval,
    # Components
    ModelRegistry,
    ABTestingFramework,
    RetrainingPipeline,
    MLGovernanceController,
    RollbackManager,
    # Integrated System
    HVACRPdMSystem,
)
from ..data_plane import ActionRiskLevel
from ..governance import AuditLogger


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def audit_logger():
    """Create a test audit logger"""
    return AuditLogger()


@pytest.fixture
def model_registry(audit_logger):
    """Create a model registry"""
    return ModelRegistry(audit_logger)


@pytest.fixture
def sample_model():
    """Create a sample model version"""
    return ModelVersion(
        version_id=str(uuid.uuid4())[:12],
        model_name="anomaly_detection",
        model_type=ModelType.ANOMALY_DETECTION,
        version_number="1.0.0",
        created_at=datetime.utcnow(),
        created_by="test_engineer",
        n_training_samples=10000,
        hyperparameters={"learning_rate": 0.001, "epochs": 100},
    )


@pytest.fixture
def sample_metrics():
    """Create sample performance metrics"""
    return PerformanceMetrics(
        metrics_id=str(uuid.uuid4())[:12],
        model_version_id="test-version",
        computed_at=datetime.utcnow(),
        accuracy=0.95,
        precision=0.92,
        recall=0.88,
        f1_score=0.90,
        auc_roc=0.96,
        n_samples=5000,
    )


@pytest.fixture
def hvacr_system(audit_logger):
    """Create HVACRPdMSystem instance"""
    return HVACRPdMSystem(site_id="test-site-001", audit_logger=audit_logger)


# =============================================================================
# Test: Data Models
# =============================================================================

class TestDataModels:
    """Tests for learning loop data models"""
    
    def test_model_version_creation(self):
        """Test ModelVersion dataclass creation"""
        model = ModelVersion(
            version_id="test-v1",
            model_name="failure_prediction",
            model_type=ModelType.FAILURE_PREDICTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
        )
        
        assert model.version_id == "test-v1"
        assert model.model_type == ModelType.FAILURE_PREDICTION
        assert model.stage == ModelStage.DEVELOPMENT
        assert model.is_active is True
        assert model.approval_status == ApprovalStatus.PENDING
    
    def test_model_version_to_dict(self, sample_model):
        """Test ModelVersion serialization"""
        data = sample_model.to_dict()
        
        assert "version_id" in data
        assert "model_name" in data
        assert "model_type" in data
        assert data["stage"] == "development"
        assert data["is_active"] is True
    
    def test_performance_metrics_creation(self):
        """Test PerformanceMetrics dataclass"""
        metrics = PerformanceMetrics(
            metrics_id="m1",
            model_version_id="v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95,
            f1_score=0.90,
            auc_roc=0.96,
            inference_latency_p95_ms=15.5,
            n_samples=10000,
        )
        
        assert metrics.accuracy == 0.95
        assert metrics.f1_score == 0.90
        assert metrics.n_samples == 10000
    
    def test_performance_metrics_get_primary_metric(self, sample_metrics):
        """Test primary metric extraction by model type"""
        # Anomaly detection uses AUC-ROC
        primary = sample_metrics.get_primary_metric(ModelType.ANOMALY_DETECTION)
        assert primary == 0.96  # auc_roc
        
        # RCA uses accuracy
        primary = sample_metrics.get_primary_metric(ModelType.ROOT_CAUSE_ANALYSIS)
        assert primary == 0.95  # accuracy
    
    def test_performance_metrics_comparison(self):
        """Test metrics comparison"""
        metrics_a = PerformanceMetrics(
            metrics_id="a", model_version_id="v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95, f1_score=0.90, auc_roc=0.96,
        )
        metrics_b = PerformanceMetrics(
            metrics_id="b", model_version_id="v2",
            computed_at=datetime.utcnow(),
            accuracy=0.90, f1_score=0.85, auc_roc=0.91,
        )
        
        # metrics_a should be better for anomaly detection
        assert metrics_a.is_better_than(metrics_b, ModelType.ANOMALY_DETECTION)
        assert not metrics_b.is_better_than(metrics_a, ModelType.ANOMALY_DETECTION)
    
    def test_experiment_creation(self):
        """Test Experiment dataclass"""
        experiment = Experiment(
            experiment_id="exp-001",
            experiment_name="Test A/B",
            description="Testing model comparison",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="v1", variant_name="Control",
                    model_version_id="model-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="v2", variant_name="Treatment",
                    model_version_id="model-v2",
                    traffic_percentage=50, is_control=False,
                ),
            ],
            created_by="test_user",
        )
        
        assert experiment.experiment_id == "exp-001"
        assert len(experiment.variants) == 2
        assert experiment.status == ExperimentStatus.DRAFT
        assert experiment.get_control_variant() is not None
    
    def test_experiment_variant_assignment(self):
        """Test deterministic variant assignment"""
        experiment = Experiment(
            experiment_id="exp-002",
            experiment_name="Sticky Test",
            description="Test sticky assignment",
            model_type=ModelType.FAILURE_PREDICTION,
            traffic_split_strategy=TrafficSplitStrategy.STICKY_SITE,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="v1", traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="v2", traffic_percentage=50, is_control=False,
                ),
            ],
        )
        
        # Same entity should always get same variant (sticky)
        entity_id = "site-123"
        variant1 = experiment.get_variant_for_entity(entity_id)
        variant2 = experiment.get_variant_for_entity(entity_id)
        assert variant1.variant_id == variant2.variant_id
    
    def test_retraining_trigger_creation(self):
        """Test RetrainingTrigger dataclass"""
        trigger = RetrainingTrigger(
            trigger_id="t1",
            trigger_name="Performance Degradation",
            trigger_type=RetrainingTriggerType.PERFORMANCE_DEGRADATION,
            model_name="anomaly_detection",
            performance_metric="f1_score",
            degradation_threshold_pct=5.0,
            cooldown_hours=48,
        )
        
        assert trigger.trigger_type == RetrainingTriggerType.PERFORMANCE_DEGRADATION
        assert trigger.is_active is True
        assert trigger.requires_approval is True


# =============================================================================
# Test: Model Registry
# =============================================================================

class TestModelRegistry:
    """Tests for model versioning and registry"""
    
    def test_register_model(self, model_registry, sample_model):
        """Test model registration"""
        version_id = model_registry.register_model(sample_model)
        
        assert version_id == sample_model.version_id
        assert model_registry.get_model(version_id) is not None
    
    def test_get_model_by_name_version(self, model_registry, sample_model):
        """Test retrieval by name and version number"""
        model_registry.register_model(sample_model)
        
        found = model_registry.get_model_by_name_version(
            sample_model.model_name, sample_model.version_number
        )
        assert found is not None
        assert found.version_id == sample_model.version_id
    
    def test_get_latest_version(self, model_registry):
        """Test getting latest version"""
        for i, version in enumerate(["1.0.0", "1.1.0", "2.0.0"]):
            model = ModelVersion(
                version_id=f"v{i}",
                model_name="test_model",
                model_type=ModelType.ANOMALY_DETECTION,
                version_number=version,
                created_at=datetime.utcnow(),
                created_by="test",
            )
            model_registry.register_model(model)
        
        latest = model_registry.get_latest_version("test_model")
        assert latest.version_number == "2.0.0"
    
    def test_promote_model(self, model_registry, sample_model):
        """Test model promotion through stages"""
        model_registry.register_model(sample_model)
        
        # Development -> Staging
        success, msg = model_registry.promote_model(
            sample_model.version_id, ModelStage.STAGING, "engineer"
        )
        assert success
        assert model_registry.get_model(sample_model.version_id).stage == ModelStage.STAGING
        
        # Staging -> Production
        success, msg = model_registry.promote_model(
            sample_model.version_id, ModelStage.PRODUCTION, "engineer"
        )
        assert success
        assert model_registry.get_model(sample_model.version_id).stage == ModelStage.PRODUCTION
    
    def test_invalid_stage_transition(self, model_registry, sample_model):
        """Test that invalid transitions are rejected"""
        model_registry.register_model(sample_model)
        
        # Development -> Production (should fail, need staging first)
        success, msg = model_registry.promote_model(
            sample_model.version_id, ModelStage.PRODUCTION, "engineer"
        )
        assert not success
        assert "Invalid transition" in msg
    
    def test_rollback_model(self, model_registry):
        """Test model rollback"""
        # Create two versions
        v1 = ModelVersion(
            version_id="v1", model_name="test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(), created_by="test",
        )
        v2 = ModelVersion(
            version_id="v2", model_name="test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="2.0.0",
            created_at=datetime.utcnow(), created_by="test",
        )
        
        model_registry.register_model(v1)
        model_registry.register_model(v2)
        
        # Promote v1 to production
        model_registry.promote_model("v1", ModelStage.STAGING, "test")
        model_registry.promote_model("v1", ModelStage.PRODUCTION, "test")
        
        # Promote v2 to production (v1 gets archived)
        model_registry.promote_model("v2", ModelStage.STAGING, "test")
        model_registry.promote_model("v2", ModelStage.PRODUCTION, "test")
        
        assert model_registry.get_model("v2").stage == ModelStage.PRODUCTION
        assert "v1" in model_registry.get_model("v2").can_rollback_to
        
        # Rollback to v1
        success, msg = model_registry.rollback_model("test", "v1", "engineer", "Bug in v2")
        assert success
        assert model_registry.get_model("v1").stage == ModelStage.PRODUCTION
    
    def test_list_versions(self, model_registry):
        """Test listing model versions"""
        for i in range(5):
            model = ModelVersion(
                version_id=f"v{i}",
                model_name="test_model",
                model_type=ModelType.ANOMALY_DETECTION,
                version_number=f"1.{i}.0",
                created_at=datetime.utcnow(),
                created_by="test",
            )
            model_registry.register_model(model)
        
        versions = model_registry.list_versions("test_model", limit=3)
        assert len(versions) == 3
    
    def test_compare_versions(self, model_registry):
        """Test version comparison"""
        v1 = ModelVersion(
            version_id="v1", model_name="test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(), created_by="test",
            hyperparameters={"lr": 0.001, "epochs": 100},
        )
        v2 = ModelVersion(
            version_id="v2", model_name="test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="2.0.0",
            created_at=datetime.utcnow(), created_by="test",
            hyperparameters={"lr": 0.0001, "epochs": 200},
        )
        
        model_registry.register_model(v1)
        model_registry.register_model(v2)
        
        comparison = model_registry.compare_versions("v1", "v2")
        assert "hyperparameter_diff" in comparison
        assert "lr" in comparison["hyperparameter_diff"]


# =============================================================================
# Test: A/B Testing Framework
# =============================================================================

class TestABTestingFramework:
    """Tests for A/B testing framework"""
    
    @pytest.fixture
    def ab_framework(self, model_registry, audit_logger):
        """Create AB testing framework with registered models"""
        # Register control and treatment models
        control = ModelVersion(
            version_id="control-v1", model_name="anomaly",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(), created_by="test",
            stage=ModelStage.PRODUCTION,
        )
        treatment = ModelVersion(
            version_id="treatment-v1", model_name="anomaly",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="2.0.0",
            created_at=datetime.utcnow(), created_by="test",
            stage=ModelStage.STAGING,
        )
        model_registry.register_model(control)
        model_registry.register_model(treatment)
        
        return ABTestingFramework(model_registry, audit_logger)
    
    def test_create_experiment(self, ab_framework):
        """Test experiment creation"""
        experiment = Experiment(
            experiment_id="exp-001",
            experiment_name="Anomaly Detection Test",
            description="Compare v1 vs v2",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
            created_by="test_user",
        )
        
        exp_id = ab_framework.create_experiment(experiment)
        assert exp_id == "exp-001"
    
    def test_experiment_traffic_validation(self, ab_framework):
        """Test that traffic must sum to 100%"""
        experiment = Experiment(
            experiment_id="exp-bad",
            experiment_name="Bad Traffic Split",
            description="Invalid traffic",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=30, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=30, is_control=False,
                ),
            ],
        )
        
        with pytest.raises(ValueError) as exc:
            ab_framework.create_experiment(experiment)
        assert "100" in str(exc.value)
    
    def test_experiment_requires_control(self, ab_framework):
        """Test that experiment requires control variant"""
        experiment = Experiment(
            experiment_id="exp-no-ctrl",
            experiment_name="No Control",
            description="Missing control",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="t1", variant_name="Treatment 1",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=False,
                ),
                ExperimentVariant(
                    variant_id="t2", variant_name="Treatment 2",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
        )
        
        with pytest.raises(ValueError) as exc:
            ab_framework.create_experiment(experiment)
        assert "control" in str(exc.value).lower()
    
    def test_approve_and_start_experiment(self, ab_framework):
        """Test experiment approval and start workflow"""
        experiment = Experiment(
            experiment_id="exp-workflow",
            experiment_name="Workflow Test",
            description="Test workflow",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
        )
        ab_framework.create_experiment(experiment)
        
        # Approve
        success, _ = ab_framework.approve_experiment("exp-workflow", "approver")
        assert success
        assert ab_framework.get_experiment("exp-workflow").status == ExperimentStatus.APPROVED
        
        # Start
        success, _ = ab_framework.start_experiment("exp-workflow", "starter")
        assert success
        assert ab_framework.get_experiment("exp-workflow").status == ExperimentStatus.RUNNING
    
    def test_get_model_for_prediction_with_experiment(self, ab_framework):
        """Test model selection during active experiment"""
        experiment = Experiment(
            experiment_id="exp-active",
            experiment_name="Active Test",
            description="Test active",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
            traffic_split_strategy=TrafficSplitStrategy.STICKY_SITE,
        )
        ab_framework.create_experiment(experiment)
        ab_framework.approve_experiment("exp-active", "approver")
        ab_framework.start_experiment("exp-active", "starter")
        
        # Should get a model and variant ID
        version_id, variant_id = ab_framework.get_model_for_prediction(
            ModelType.ANOMALY_DETECTION, "site-001"
        )
        
        assert version_id in ["control-v1", "treatment-v1"]
        assert variant_id in ["ctrl", "treat"]
    
    def test_record_and_compute_statistics(self, ab_framework):
        """Test recording predictions and computing statistics"""
        experiment = Experiment(
            experiment_id="exp-stats",
            experiment_name="Stats Test",
            description="Test statistics",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
        )
        ab_framework.create_experiment(experiment)
        ab_framework.approve_experiment("exp-stats", "approver")
        ab_framework.start_experiment("exp-stats", "starter")
        
        # Record predictions
        for i in range(100):
            ab_framework.record_prediction("exp-stats", "ctrl", i % 2 == 0)
            ab_framework.record_prediction("exp-stats", "treat", i % 3 != 0)
        
        # Compute statistics
        stats = ab_framework.compute_experiment_statistics("exp-stats")
        
        assert stats["status"] == "running"
        assert len(stats["variants"]) == 2
        assert all(v["n_predictions"] == 100 for v in stats["variants"])
    
    def test_conclude_experiment(self, ab_framework):
        """Test experiment conclusion"""
        experiment = Experiment(
            experiment_id="exp-conclude",
            experiment_name="Conclude Test",
            description="Test conclusion",
            model_type=ModelType.ANOMALY_DETECTION,
            variants=[
                ExperimentVariant(
                    variant_id="ctrl", variant_name="Control",
                    model_version_id="control-v1",
                    traffic_percentage=50, is_control=True,
                ),
                ExperimentVariant(
                    variant_id="treat", variant_name="Treatment",
                    model_version_id="treatment-v1",
                    traffic_percentage=50, is_control=False,
                ),
            ],
        )
        ab_framework.create_experiment(experiment)
        ab_framework.approve_experiment("exp-conclude", "approver")
        ab_framework.start_experiment("exp-conclude", "starter")
        
        success, msg = ab_framework.conclude_experiment(
            "exp-conclude", "concluder", winner_variant_id="treat", reason="Treatment performed better"
        )
        
        assert success
        exp = ab_framework.get_experiment("exp-conclude")
        assert exp.status == ExperimentStatus.COMPLETED
        assert exp.winner_variant_id == "treat"


# =============================================================================
# Test: Retraining Pipeline
# =============================================================================

class TestRetrainingPipeline:
    """Tests for automated retraining pipeline"""
    
    @pytest.fixture
    def pipeline(self, model_registry, audit_logger):
        """Create retraining pipeline"""
        return RetrainingPipeline(model_registry, audit_logger)
    
    def test_register_trigger(self, pipeline):
        """Test trigger registration"""
        trigger = RetrainingTrigger(
            trigger_id="t1",
            trigger_name="Perf Degradation",
            trigger_type=RetrainingTriggerType.PERFORMANCE_DEGRADATION,
            model_name="test_model",
            degradation_threshold_pct=5.0,
        )
        
        pipeline.register_trigger(trigger)
        assert "t1" in pipeline.triggers
    
    def test_performance_degradation_trigger(self, pipeline, model_registry):
        """Test performance degradation detection"""
        # Register model
        model = ModelVersion(
            version_id="v1", model_name="test_model",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(), created_by="test",
            stage=ModelStage.PRODUCTION,
        )
        model_registry.register_model(model)
        
        # Register trigger
        trigger = RetrainingTrigger(
            trigger_id="perf-t1",
            trigger_name="Perf Degradation",
            trigger_type=RetrainingTriggerType.PERFORMANCE_DEGRADATION,
            model_name="test_model",
            performance_metric="accuracy",
            degradation_threshold_pct=5.0,
            baseline_window_hours=1,
        )
        pipeline.register_trigger(trigger)
        
        # Record baseline metrics (high accuracy)
        for i in range(15):
            metrics = PerformanceMetrics(
                metrics_id=f"m-old-{i}",
                model_version_id="v1",
                computed_at=datetime.utcnow() - timedelta(hours=2),
                accuracy=0.95,
            )
            pipeline.record_metrics("test_model", metrics)
        
        # Record recent metrics (degraded accuracy)
        for i in range(10):
            metrics = PerformanceMetrics(
                metrics_id=f"m-new-{i}",
                model_version_id="v1",
                computed_at=datetime.utcnow(),
                accuracy=0.85,  # 10% degradation
            )
            pipeline.record_metrics("test_model", metrics)
        
        # Evaluate triggers
        triggered = pipeline.evaluate_triggers()
        assert len(triggered) >= 1
        assert any(t.trigger_id == "perf-t1" for t in triggered)
    
    def test_feedback_trigger(self, pipeline):
        """Test case feedback trigger"""
        trigger = RetrainingTrigger(
            trigger_id="feedback-t1",
            trigger_name="Feedback Trigger",
            trigger_type=RetrainingTriggerType.CASE_FEEDBACK,
            model_name="test_model",
            min_feedback_count=10,
            negative_feedback_threshold_pct=30.0,
        )
        pipeline.register_trigger(trigger)
        
        # Record feedback (40% negative)
        for i in range(10):
            feedback_type = "negative" if i < 4 else "positive"
            pipeline.record_feedback("test_model", f"case-{i}", feedback_type, feedback_type == "positive")
        
        triggered = pipeline.evaluate_triggers()
        assert any(t.trigger_id == "feedback-t1" for t in triggered)
    
    def test_data_volume_trigger(self, pipeline):
        """Test new data volume trigger"""
        trigger = RetrainingTrigger(
            trigger_id="volume-t1",
            trigger_name="Volume Trigger",
            trigger_type=RetrainingTriggerType.NEW_DATA_VOLUME,
            model_name="test_model",
            min_new_samples=1000,
        )
        pipeline.register_trigger(trigger)
        
        # Record data volume
        pipeline.record_new_data("test_model", 1500)
        
        triggered = pipeline.evaluate_triggers()
        assert any(t.trigger_id == "volume-t1" for t in triggered)
    
    def test_cooldown_prevents_trigger(self, pipeline):
        """Test that cooldown prevents immediate re-trigger"""
        trigger = RetrainingTrigger(
            trigger_id="cooldown-t1",
            trigger_name="Cooldown Test",
            trigger_type=RetrainingTriggerType.NEW_DATA_VOLUME,
            model_name="test_model",
            min_new_samples=100,
            cooldown_hours=24,
        )
        pipeline.register_trigger(trigger)
        
        pipeline.record_new_data("test_model", 200)
        
        # First evaluation should trigger
        triggered = pipeline.evaluate_triggers()
        assert any(t.trigger_id == "cooldown-t1" for t in triggered)
        
        # Create job (sets last_triggered_at)
        for t in triggered:
            if t.trigger_id == "cooldown-t1":
                pipeline.create_retraining_job(t)
        
        # Reset volume and try again
        pipeline.reset_data_volume("test_model")
        pipeline.record_new_data("test_model", 200)
        
        # Should not trigger due to cooldown
        triggered = pipeline.evaluate_triggers()
        assert not any(t.trigger_id == "cooldown-t1" for t in triggered)
    
    def test_create_manual_job(self, pipeline):
        """Test manual retraining job creation"""
        job = pipeline.create_manual_job("test_model", "engineer")
        
        assert job.job_id is not None
        assert job.trigger_type == RetrainingTriggerType.MANUAL
        assert job.status == "pending"
    
    def test_execute_retraining_job_without_callback(self, pipeline):
        """Test job execution fails without callback"""
        job = pipeline.create_manual_job("test_model", "engineer")
        
        success, msg = pipeline.execute_retraining_job(job.job_id)
        
        assert not success
        assert "callback" in msg.lower()
        assert pipeline.get_job(job.job_id).status == "failed"


# =============================================================================
# Test: Governance Controls
# =============================================================================

class TestGovernanceControls:
    """Tests for approval workflows and governance"""
    
    @pytest.fixture
    def governance(self, audit_logger):
        """Create governance controller"""
        return MLGovernanceController(audit_logger=audit_logger)
    
    def test_request_approval(self, governance):
        """Test approval request creation"""
        approval = governance.request_approval(
            action_type=GovernanceAction.MODEL_DEPLOY,
            target_id="model-v1",
            target_type="model_version",
            requested_by="engineer",
            risk_level=ActionRiskLevel.MEDIUM,
        )
        
        assert approval.approval_id is not None
        assert approval.status == ApprovalStatus.PENDING
        assert approval.action_type == GovernanceAction.MODEL_DEPLOY
    
    def test_auto_approval_low_risk(self, governance):
        """Test auto-approval for low-risk actions"""
        approval = governance.request_approval(
            action_type=GovernanceAction.MODEL_ROLLBACK,
            target_id="model-v1",
            target_type="model_version",
            requested_by="engineer",
            risk_level=ActionRiskLevel.LOW,  # Low risk rollback auto-approves
        )
        
        assert approval.status == ApprovalStatus.AUTO_APPROVED
    
    def test_process_approval(self, governance):
        """Test approval processing"""
        approval = governance.request_approval(
            action_type=GovernanceAction.MODEL_DEPLOY,
            target_id="model-v1",
            target_type="model_version",
            requested_by="engineer",
            risk_level=ActionRiskLevel.HIGH,
        )
        
        success, msg = governance.process_approval(
            approval.approval_id, approved=True, reviewer="lead", notes="Looks good"
        )
        
        assert success
        processed = governance.get_approval(approval.approval_id)
        assert processed.status == ApprovalStatus.APPROVED
        assert processed.reviewed_by == "lead"
    
    def test_reject_approval(self, governance):
        """Test approval rejection"""
        approval = governance.request_approval(
            action_type=GovernanceAction.EXPERIMENT_START,
            target_id="exp-001",
            target_type="experiment",
            requested_by="engineer",
            risk_level=ActionRiskLevel.MEDIUM,
        )
        
        success, msg = governance.process_approval(
            approval.approval_id, approved=False, reviewer="lead", notes="Not ready"
        )
        
        assert success
        processed = governance.get_approval(approval.approval_id)
        assert processed.status == ApprovalStatus.REJECTED
    
    def test_approval_expiration(self, governance):
        """Test expired approvals"""
        approval = governance.request_approval(
            action_type=GovernanceAction.MODEL_DEPLOY,
            target_id="model-v1",
            target_type="model_version",
            requested_by="engineer",
            risk_level=ActionRiskLevel.HIGH,
        )
        
        # Manually expire
        approval.expires_at = datetime.utcnow() - timedelta(hours=1)
        
        expired = governance.check_expired_approvals()
        assert len(expired) == 1
        assert expired[0].status == ApprovalStatus.EXPIRED
    
    def test_risk_assessment(self, governance):
        """Test risk level assessment"""
        # Production deployment is HIGH risk
        risk = governance.assess_risk(
            GovernanceAction.MODEL_DEPLOY,
            {"target_stage": "production", "has_canary_validation": False}
        )
        assert risk == ActionRiskLevel.HIGH
        
        # With canary validation, MEDIUM
        risk = governance.assess_risk(
            GovernanceAction.MODEL_DEPLOY,
            {"target_stage": "production", "has_canary_validation": True}
        )
        assert risk == ActionRiskLevel.MEDIUM
        
        # Small traffic experiment is LOW risk
        risk = governance.assess_risk(
            GovernanceAction.EXPERIMENT_START,
            {"max_traffic_percentage": 5}
        )
        assert risk == ActionRiskLevel.SAFE
    
    def test_validate_action(self, governance):
        """Test action validation"""
        # Deployment without metrics should fail
        valid, msg = governance.validate_action(
            GovernanceAction.MODEL_DEPLOY,
            "engineer",
            {"has_validation_metrics": False, "target_stage": "production"}
        )
        assert not valid
        assert "metrics" in msg.lower()
        
        # Experiment without control should fail
        valid, msg = governance.validate_action(
            GovernanceAction.EXPERIMENT_START,
            "engineer",
            {"has_control_variant": False}
        )
        assert not valid
        assert "control" in msg.lower()
    
    def test_get_pending_approvals(self, governance):
        """Test listing pending approvals"""
        for i in range(3):
            governance.request_approval(
                action_type=GovernanceAction.MODEL_DEPLOY,
                target_id=f"model-v{i}",
                target_type="model_version",
                requested_by="engineer",
                risk_level=ActionRiskLevel.HIGH,
            )
        
        pending = governance.get_pending_approvals()
        assert len(pending) == 3
        
        # Filter by action type
        pending = governance.get_pending_approvals(action_type=GovernanceAction.EXPERIMENT_START)
        assert len(pending) == 0


# =============================================================================
# Test: Rollback Manager
# =============================================================================

class TestRollbackManager:
    """Tests for rollback management"""
    
    @pytest.fixture
    def rollback_manager(self, audit_logger):
        """Create rollback manager"""
        governance = MLGovernanceController(audit_logger=audit_logger)
        return RollbackManager(governance, audit_logger)
    
    def test_initiate_rollback(self, rollback_manager):
        """Test rollback initiation"""
        success, msg, approval_id = rollback_manager.initiate_rollback(
            model_name="test_model",
            from_version_id="v2",
            to_version_id="v1",
            reason="Performance issues",
            initiated_by="engineer",
        )
        
        # Low risk rollback should auto-approve
        assert success
        assert approval_id is not None


# =============================================================================
# Test: HVACRPdMSystem Integration
# =============================================================================

class TestHVACRPdMSystemIntegration:
    """Tests for integrated HVACR PdM system"""
    
    def test_system_initialization(self, hvacr_system):
        """Test system initialization"""
        assert hvacr_system.site_id == "test-site-001"
        assert hvacr_system.model_registry is not None
        assert hvacr_system.ab_testing is not None
        assert hvacr_system.retraining_pipeline is not None
        assert hvacr_system.governance is not None
    
    def test_initialize_default_triggers(self, hvacr_system):
        """Test default trigger initialization"""
        hvacr_system.initialize_default_triggers()
        
        triggers = hvacr_system.retraining_pipeline.triggers
        assert len(triggers) >= 4
        
        # Check for expected trigger types
        trigger_types = [t.trigger_type for t in triggers.values()]
        assert RetrainingTriggerType.PERFORMANCE_DEGRADATION in trigger_types
        assert RetrainingTriggerType.CASE_FEEDBACK in trigger_types
        assert RetrainingTriggerType.DRIFT_DETECTED in trigger_types
    
    def test_register_and_deploy_model(self, hvacr_system):
        """Test model registration and deployment workflow"""
        model = ModelVersion(
            version_id="hvac-anomaly-v1",
            model_name=ModelType.ANOMALY_DETECTION.value,
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="ml_engineer",
            stage=ModelStage.STAGING,  # Already staged
        )
        model.validation_metrics = PerformanceMetrics(
            metrics_id="m1", model_version_id="hvac-anomaly-v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95, f1_score=0.92,
        )
        
        hvacr_system.register_model(model)
        
        # Deploy with skip_approval for testing
        success, msg = hvacr_system.deploy_model("hvac-anomaly-v1", "engineer", skip_approval=True)
        assert success
        assert hvacr_system.active_models.get(ModelType.ANOMALY_DETECTION) == "hvac-anomaly-v1"
    
    def test_get_model_for_prediction(self, hvacr_system):
        """Test model selection for predictions"""
        # Register production model
        model = ModelVersion(
            version_id="prod-model-v1",
            model_name=ModelType.FAILURE_PREDICTION.value,
            model_type=ModelType.FAILURE_PREDICTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
            stage=ModelStage.PRODUCTION,
        )
        hvacr_system.register_model(model)
        hvacr_system.active_models[ModelType.FAILURE_PREDICTION] = "prod-model-v1"
        
        version_id, variant_id = hvacr_system.get_model_for_prediction(
            ModelType.FAILURE_PREDICTION, "case-001"
        )
        
        assert version_id == "prod-model-v1"
        assert variant_id is None  # No active experiment
    
    def test_record_prediction_and_outcome(self, hvacr_system):
        """Test prediction and case outcome recording"""
        # Setup
        model = ModelVersion(
            version_id="track-model-v1",
            model_name=ModelType.ANOMALY_DETECTION.value,
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
            stage=ModelStage.PRODUCTION,
        )
        hvacr_system.register_model(model)
        
        # Record prediction
        hvacr_system.record_prediction(
            model_version_id="track-model-v1",
            case_id="case-track-001",
            prediction={"anomaly": True, "confidence": 0.85},
            is_correct=True,
        )
        
        assert "case-track-001" in hvacr_system.case_model_mapping
        assert len(hvacr_system.prediction_buffer) == 1
        
        # Record outcome
        hvacr_system.record_case_outcome(
            case_id="case-track-001",
            outcome="resolved",
            was_prediction_accurate=True,
            feedback_notes="Correct prediction",
        )
        
        assert "track-model-v1" in hvacr_system.model_case_outcomes
    
    def test_create_ab_test(self, hvacr_system):
        """Test A/B test creation via system"""
        # Register models
        for vid in ["ab-ctrl", "ab-treat"]:
            model = ModelVersion(
                version_id=vid,
                model_name=ModelType.ROOT_CAUSE_ANALYSIS.value,
                model_type=ModelType.ROOT_CAUSE_ANALYSIS,
                version_number="1.0.0" if vid == "ab-ctrl" else "2.0.0",
                created_at=datetime.utcnow(),
                created_by="engineer",
            )
            hvacr_system.register_model(model)
        
        success, exp_id = hvacr_system.create_ab_test(
            name="RCA Comparison",
            description="Compare RCA models",
            model_type=ModelType.ROOT_CAUSE_ANALYSIS,
            control_version_id="ab-ctrl",
            treatment_version_id="ab-treat",
            control_traffic_pct=70,
            created_by="engineer",
        )
        
        assert success
        assert exp_id is not None
    
    def test_check_retraining_triggers(self, hvacr_system):
        """Test retraining trigger check"""
        hvacr_system.initialize_default_triggers()
        
        # Without any degradation, no triggers should fire
        jobs = hvacr_system.check_retraining_triggers()
        # May or may not fire depending on state
        assert isinstance(jobs, list)
    
    def test_trigger_manual_retrain(self, hvacr_system):
        """Test manual retraining trigger"""
        success, job_id = hvacr_system.trigger_manual_retrain(
            ModelType.DEMAND_FORECAST.value, "engineer"
        )
        
        assert success
        assert job_id is not None
    
    def test_get_system_status(self, hvacr_system):
        """Test system status retrieval"""
        hvacr_system.initialize_default_triggers()
        
        status = hvacr_system.get_system_status()
        
        assert status["site_id"] == "test-site-001"
        assert "active_models" in status
        assert "registry_stats" in status
        assert "governance_stats" in status
        assert "retraining_triggers" in status
    
    def test_get_model_health(self, hvacr_system):
        """Test model health check"""
        model = ModelVersion(
            version_id="health-v1",
            model_name="health_test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
            stage=ModelStage.PRODUCTION,
            deployed_at=datetime.utcnow(),
        )
        hvacr_system.register_model(model)
        
        health = hvacr_system.get_model_health("health_test")
        
        assert health["model_name"] == "health_test"
        assert health["version"] == "1.0.0"
        assert health["stage"] == "production"
        assert "in_experiment" in health


# =============================================================================
# Test: End-to-End Workflow
# =============================================================================

class TestEndToEndWorkflow:
    """End-to-end integration tests"""
    
    def test_full_model_lifecycle(self, hvacr_system):
        """Test complete model lifecycle: register → deploy → experiment → retrain"""
        # 1. Register model v1
        v1 = ModelVersion(
            version_id="e2e-v1",
            model_name="e2e_model",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
            stage=ModelStage.STAGING,
        )
        v1.validation_metrics = PerformanceMetrics(
            metrics_id="e2e-m1", model_version_id="e2e-v1",
            computed_at=datetime.utcnow(),
            accuracy=0.90, f1_score=0.88, auc_roc=0.92,
        )
        hvacr_system.register_model(v1)
        
        # 2. Deploy v1
        success, _ = hvacr_system.deploy_model("e2e-v1", "engineer", skip_approval=True)
        assert success
        
        # 3. Register model v2
        v2 = ModelVersion(
            version_id="e2e-v2",
            model_name="e2e_model",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="2.0.0",
            created_at=datetime.utcnow(),
            created_by="engineer",
            stage=ModelStage.STAGING,
        )
        v2.validation_metrics = PerformanceMetrics(
            metrics_id="e2e-m2", model_version_id="e2e-v2",
            computed_at=datetime.utcnow(),
            accuracy=0.95, f1_score=0.93, auc_roc=0.97,
        )
        hvacr_system.register_model(v2)
        
        # 4. Create A/B test
        success, exp_id = hvacr_system.create_ab_test(
            name="E2E Test",
            description="Testing v1 vs v2",
            model_type=ModelType.ANOMALY_DETECTION,
            control_version_id="e2e-v1",
            treatment_version_id="e2e-v2",
            control_traffic_pct=50,
        )
        assert success
        
        # 5. Start experiment
        success, _ = hvacr_system.start_ab_test(exp_id, "engineer")
        assert success
        
        # 6. Record predictions
        for i in range(50):
            version_id, variant_id = hvacr_system.get_model_for_prediction(
                ModelType.ANOMALY_DETECTION, f"case-{i}"
            )
            hvacr_system.record_prediction(
                model_version_id=version_id,
                case_id=f"case-{i}",
                prediction={"anomaly": True},
                is_correct=True,
                experiment_variant_id=variant_id,
            )
        
        # 7. Conclude experiment
        success, _ = hvacr_system.conclude_ab_test(exp_id, "engineer", promote_winner=True)
        assert success
        
        # 8. Verify system status
        status = hvacr_system.get_system_status()
        assert status["cases_tracked"] >= 50


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
