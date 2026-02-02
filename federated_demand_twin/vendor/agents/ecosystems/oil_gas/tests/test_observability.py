"""
Phase 5 Validation Tests: Observability & API Layer

Tests for:
- Metrics collector and Prometheus export
- REST API endpoints
- Notification service
- Scheduler and job runner
- Health checks and diagnostics
"""

import pytest
import time
from datetime import datetime, timedelta
from typing import Dict, Any

from ..observability import (
    # Enums
    MetricType,
    MetricNamespace,
    AlertSeverity,
    AlertState,
    NotificationChannelType,
    HealthStatus,
    JobStatus,
    # Data Models
    MetricPoint,
    MetricSeries,
    AlertRule,
    ComponentHealth,
    SystemHealth,
    ScheduledJob,
    JobExecution,
    # Components
    MetricsCollector,
    HVACRPdMAPI,
    NotificationService,
    Scheduler,
    HealthChecker,
    DiagnosticsRunner,
    ObservabilityStack,
)
from ..observability_notifications import (
    NotificationChannel,
    Notification,
    InAppProvider,
    create_default_notification_service,
)
from ..learning_loop import (
    HVACRPdMSystem,
    ModelVersion,
    ModelType,
    ModelStage,
    PerformanceMetrics,
)
from ..governance import AuditLogger


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def audit_logger():
    """Create test audit logger"""
    return AuditLogger()


@pytest.fixture
def hvacr_system(audit_logger):
    """Create HVACRPdMSystem for testing"""
    system = HVACRPdMSystem(site_id="test-site", audit_logger=audit_logger)
    system.initialize_default_triggers()
    return system


@pytest.fixture
def metrics_collector():
    """Create metrics collector"""
    return MetricsCollector(retention_hours=24)


@pytest.fixture
def api(hvacr_system, metrics_collector):
    """Create API instance"""
    return HVACRPdMAPI(hvacr_system, metrics_collector)


@pytest.fixture
def notification_service():
    """Create notification service"""
    return create_default_notification_service()


@pytest.fixture
def scheduler(hvacr_system, metrics_collector):
    """Create scheduler"""
    return Scheduler(hvacr_system, metrics_collector)


@pytest.fixture
def health_checker(hvacr_system, metrics_collector):
    """Create health checker"""
    return HealthChecker(hvacr_system, metrics_collector)


@pytest.fixture
def observability_stack(hvacr_system):
    """Create full observability stack"""
    return ObservabilityStack(hvacr_system)


# =============================================================================
# Test: Data Models
# =============================================================================

class TestObservabilityModels:
    """Tests for observability data models"""
    
    def test_metric_point_creation(self):
        """Test MetricPoint dataclass"""
        point = MetricPoint(
            name="accuracy",
            namespace=MetricNamespace.MODEL,
            metric_type=MetricType.GAUGE,
            value=0.95,
            labels={"model_name": "test"},
        )
        
        assert point.name == "accuracy"
        assert point.value == 0.95
        assert point.namespace == MetricNamespace.MODEL
    
    def test_metric_point_prometheus_format(self):
        """Test Prometheus export format"""
        point = MetricPoint(
            name="accuracy",
            namespace=MetricNamespace.MODEL,
            value=0.95,
            labels={"model_name": "test_model"},
        )
        
        prom = point.to_prometheus()
        assert "model_accuracy" in prom
        assert 'model_name="test_model"' in prom
        assert "0.95" in prom
    
    def test_metric_series(self):
        """Test MetricSeries with multiple points"""
        series = MetricSeries(
            name="latency",
            namespace=MetricNamespace.SYSTEM,
        )
        
        for i in range(10):
            series.add_point(10.0 + i)
        
        assert len(series.points) == 10
        assert series.get_latest().value == 19.0
    
    def test_metric_series_stats(self):
        """Test MetricSeries statistics"""
        series = MetricSeries(name="test")
        
        for v in [10, 20, 30, 40, 50]:
            series.add_point(float(v))
        
        stats = series.compute_stats(window_minutes=60)
        
        assert stats["min"] == 10.0
        assert stats["max"] == 50.0
        assert stats["avg"] == 30.0
        assert stats["count"] == 5
    
    def test_alert_rule_evaluation(self):
        """Test AlertRule condition evaluation"""
        rule = AlertRule(
            name="High Latency",
            metric_name="latency",
            comparison=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
        )
        
        assert rule.evaluate(150) is True
        assert rule.evaluate(50) is False
        assert rule.evaluate(100) is False  # Not > 100
    
    def test_alert_lifecycle(self):
        """Test Alert state transitions"""
        from ..observability_models import Alert
        
        alert = Alert(
            rule_name="Test Alert",
            severity=AlertSeverity.WARNING,
            message="Test message",
        )
        
        assert alert.state == AlertState.PENDING
        
        alert.fire()
        assert alert.state == AlertState.FIRING
        assert alert.fired_at is not None
        
        alert.acknowledge("user-1")
        assert alert.state == AlertState.ACKNOWLEDGED
        assert alert.acknowledged_by == "user-1"
    
    def test_component_health(self):
        """Test ComponentHealth dataclass"""
        health = ComponentHealth(
            name="model_registry",
            status=HealthStatus.HEALTHY,
            message="All systems operational",
            response_time_ms=5.2,
        )
        
        data = health.to_dict()
        assert data["status"] == "healthy"
        assert data["response_time_ms"] == 5.2
    
    def test_system_health_overall_status(self):
        """Test SystemHealth status computation"""
        health = SystemHealth()
        health.components = [
            ComponentHealth(name="a", status=HealthStatus.HEALTHY),
            ComponentHealth(name="b", status=HealthStatus.HEALTHY),
        ]
        health.compute_overall_status()
        assert health.overall_status == HealthStatus.HEALTHY
        
        health.components.append(
            ComponentHealth(name="c", status=HealthStatus.DEGRADED)
        )
        health.compute_overall_status()
        assert health.overall_status == HealthStatus.DEGRADED
        
        health.components.append(
            ComponentHealth(name="d", status=HealthStatus.UNHEALTHY)
        )
        health.compute_overall_status()
        assert health.overall_status == HealthStatus.UNHEALTHY
    
    def test_job_execution_lifecycle(self):
        """Test JobExecution state transitions"""
        execution = JobExecution(job_id="job-1", job_name="Test Job")
        
        assert execution.status == JobStatus.SCHEDULED
        
        execution.start()
        assert execution.status == JobStatus.RUNNING
        assert execution.started_at is not None
        
        execution.complete({"result": "success"})
        assert execution.status == JobStatus.COMPLETED
        assert execution.completed_at is not None
        assert execution.duration_seconds is not None


# =============================================================================
# Test: Metrics Collector
# =============================================================================

class TestMetricsCollector:
    """Tests for metrics collector"""
    
    def test_record_metric(self, metrics_collector):
        """Test basic metric recording"""
        metrics_collector.record("test_metric", 42.0)
        
        point = metrics_collector.get_metric("test_metric", MetricNamespace.SYSTEM)
        assert point is not None
        assert point.value == 42.0
    
    def test_record_with_labels(self, metrics_collector):
        """Test metric recording with labels"""
        metrics_collector.record(
            "accuracy", 0.95,
            namespace=MetricNamespace.MODEL,
            labels={"model_name": "anomaly_detection"},
        )
        
        point = metrics_collector.get_metric(
            "accuracy", MetricNamespace.MODEL,
            labels={"model_name": "anomaly_detection"},
        )
        assert point.value == 0.95
    
    def test_increment_counter(self, metrics_collector):
        """Test counter increment"""
        metrics_collector.increment("requests_total", 1)
        metrics_collector.increment("requests_total", 1)
        metrics_collector.increment("requests_total", 1)
        
        point = metrics_collector.get_metric("requests_total", MetricNamespace.SYSTEM)
        assert point.value == 3.0
    
    def test_query_range(self, metrics_collector):
        """Test range query"""
        now = datetime.utcnow()
        
        for i in range(5):
            metrics_collector.record(
                "test", float(i),
                timestamp=now - timedelta(minutes=5-i),
            )
        
        points = metrics_collector.query_range(
            "test", MetricNamespace.SYSTEM,
            start=now - timedelta(minutes=10),
            end=now,
        )
        
        assert len(points) == 5
    
    def test_record_model_metrics(self, metrics_collector):
        """Test model metrics recording"""
        perf = PerformanceMetrics(
            metrics_id="m1",
            model_version_id="v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95,
            f1_score=0.92,
            auc_roc=0.97,
        )
        
        metrics_collector.record_model_metrics("test_model", "1.0.0", perf)
        
        acc = metrics_collector.get_metric(
            "accuracy", MetricNamespace.MODEL,
            labels={"model_name": "test_model", "model_version": "1.0.0"},
        )
        assert acc.value == 0.95
    
    def test_record_prediction(self, metrics_collector):
        """Test prediction event recording"""
        metrics_collector.record_prediction("model_a", "1.0", 15.5, is_correct=True)
        metrics_collector.record_prediction("model_a", "1.0", 12.3, is_correct=False)
        
        total = metrics_collector.get_metric(
            "predictions_total", MetricNamespace.MODEL,
            labels={"model_name": "model_a", "model_version": "1.0"},
        )
        assert total.value == 2.0
    
    def test_alert_rule_triggering(self, metrics_collector):
        """Test alert rule evaluation"""
        rule = AlertRule(
            rule_id="test_alert",
            name="Test Alert",
            metric_name="error_rate",
            namespace=MetricNamespace.SYSTEM,
            comparison=">",
            threshold=0.1,
            severity=AlertSeverity.WARNING,
            duration_seconds=0,  # Fire immediately
        )
        metrics_collector.add_alert_rule(rule)
        
        # Record metric that triggers alert
        metrics_collector.record("error_rate", 0.2)
        
        alerts = metrics_collector.get_active_alerts()
        assert len(alerts) >= 1
    
    def test_prometheus_export(self, metrics_collector):
        """Test Prometheus format export"""
        metrics_collector.record("test_a", 1.0)
        metrics_collector.record("test_b", 2.0, labels={"env": "test"})
        
        output = metrics_collector.export_prometheus()
        
        assert "system_test_a" in output
        assert "system_test_b" in output
    
    def test_dashboard_summary(self, metrics_collector):
        """Test dashboard summary generation"""
        metrics_collector.record("accuracy", 0.95, MetricNamespace.MODEL,
                                 labels={"model_name": "test"})
        metrics_collector.record_system_metric("uptime", 3600)
        
        summary = metrics_collector.get_dashboard_summary()
        
        assert "timestamp" in summary
        assert "models" in summary
        assert "system" in summary


# =============================================================================
# Test: REST API
# =============================================================================

class TestRESTAPI:
    """Tests for REST API endpoints"""
    
    def test_health_endpoint(self, api):
        """Test health check endpoint"""
        response = api.get_health()
        
        assert response["success"] is True
        assert response["data"]["status"] == "healthy"
    
    def test_list_models_empty(self, api):
        """Test listing models when empty"""
        response = api.list_models()
        
        assert response["success"] is True
        assert response["data"] == []
    
    def test_list_models_with_data(self, api, hvacr_system):
        """Test listing models with registered models"""
        model = ModelVersion(
            version_id="api-test-v1",
            model_name="api_test_model",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="test",
        )
        hvacr_system.register_model(model)
        
        response = api.list_models()
        
        assert response["success"] is True
        assert len(response["data"]) == 1
        assert response["data"][0]["version_id"] == "api-test-v1"
    
    def test_get_model(self, api, hvacr_system):
        """Test getting model by ID"""
        model = ModelVersion(
            version_id="get-test-v1",
            model_name="get_test",
            model_type=ModelType.FAILURE_PREDICTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="test",
        )
        hvacr_system.register_model(model)
        
        response = api.get_model("get-test-v1")
        
        assert response["success"] is True
        assert response["data"]["version_id"] == "get-test-v1"
    
    def test_get_model_not_found(self, api):
        """Test getting non-existent model"""
        response = api.get_model("nonexistent")
        
        assert response["success"] is False
        assert response["status_code"] == 404
    
    def test_deploy_model(self, api, hvacr_system):
        """Test model deployment via API"""
        model = ModelVersion(
            version_id="deploy-api-v1",
            model_name="deploy_test",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="test",
            stage=ModelStage.STAGING,
        )
        model.validation_metrics = PerformanceMetrics(
            metrics_id="m1", model_version_id="deploy-api-v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95,
        )
        hvacr_system.register_model(model)
        
        response = api.deploy_model({
            "version_id": "deploy-api-v1",
            "deployed_by": "api_user",
            "skip_approval": True,
        })
        
        assert response["success"] is True
    
    def test_deploy_missing_fields(self, api):
        """Test deployment with missing fields"""
        response = api.deploy_model({"version_id": "test"})
        
        assert response["success"] is False
        assert "deployed_by" in response["message"]
    
    def test_list_experiments(self, api):
        """Test listing experiments"""
        response = api.list_experiments()
        
        assert response["success"] is True
        assert isinstance(response["data"], list)
    
    def test_create_experiment(self, api, hvacr_system):
        """Test creating experiment via API"""
        # Register models first
        for vid in ["exp-ctrl", "exp-treat"]:
            model = ModelVersion(
                version_id=vid,
                model_name="exp_model",
                model_type=ModelType.ANOMALY_DETECTION,
                version_number="1.0.0" if vid == "exp-ctrl" else "2.0.0",
                created_at=datetime.utcnow(),
                created_by="test",
            )
            hvacr_system.register_model(model)
        
        response = api.create_experiment({
            "name": "API Test Experiment",
            "description": "Test via API",
            "model_type": "anomaly_detection",
            "control_version_id": "exp-ctrl",
            "treatment_version_id": "exp-treat",
            "created_by": "api_user",
        })
        
        assert response["success"] is True
        assert "experiment_id" in response["data"]
    
    def test_trigger_retraining(self, api):
        """Test manual retraining trigger"""
        response = api.trigger_retraining({
            "model_name": "test_model",
            "triggered_by": "api_user",
        })
        
        assert response["success"] is True
        assert "job_id" in response["data"]
    
    def test_list_pending_approvals(self, api):
        """Test listing pending approvals"""
        response = api.list_pending_approvals()
        
        assert response["success"] is True
        assert isinstance(response["data"], list)
    
    def test_get_active_alerts(self, api):
        """Test getting active alerts"""
        response = api.get_active_alerts()
        
        assert response["success"] is True
        assert isinstance(response["data"], list)
    
    def test_get_metrics_json(self, api):
        """Test JSON metrics export"""
        response = api.get_metrics_json()
        
        assert response["success"] is True
        assert "metrics" in response["data"]
    
    def test_get_dashboard(self, api):
        """Test dashboard endpoint"""
        response = api.get_dashboard()
        
        assert response["success"] is True
        assert "system" in response["data"]


# =============================================================================
# Test: Notification Service
# =============================================================================

class TestNotificationService:
    """Tests for notification service"""
    
    def test_add_channel(self, notification_service):
        """Test adding notification channel"""
        channel = NotificationChannel(
            channel_id="test-webhook",
            name="Test Webhook",
            channel_type=NotificationChannelType.WEBHOOK,
            config={"url": "https://example.com/webhook"},
        )
        
        notification_service.add_channel(channel)
        
        assert "test-webhook" in notification_service.channels
    
    def test_notify_alert(self, notification_service):
        """Test alert notification"""
        from ..observability_models import Alert
        
        alert = Alert(
            alert_id="test-alert-1",
            rule_name="Test Alert",
            severity=AlertSeverity.WARNING,
            message="Test alert message",
            metric_name="test_metric",
            metric_value=0.5,
        )
        alert.fire()
        
        notifications = notification_service.notify_alert(alert)
        
        # Should send to in-app channel (default)
        assert len(notifications) >= 1
    
    def test_send_custom_notification(self, notification_service):
        """Test custom notification sending"""
        notification = notification_service.send_custom(
            channel_id="in-app-default",
            subject="Test Subject",
            body="Test body content",
            severity=AlertSeverity.INFO,
        )
        
        assert notification is not None
        assert notification.delivered is True
    
    def test_rate_limiting(self, notification_service):
        """Test channel rate limiting"""
        channel = NotificationChannel(
            channel_id="rate-limited",
            name="Rate Limited Channel",
            channel_type=NotificationChannelType.IN_APP,
            rate_limit_per_hour=2,
        )
        notification_service.add_channel(channel)
        
        # Should succeed twice
        for _ in range(2):
            n = notification_service.send_custom("rate-limited", "Test", "Body")
            assert n is not None
        
        # Third should fail due to rate limit
        n = notification_service.send_custom("rate-limited", "Test", "Body")
        assert n is None
    
    def test_in_app_notifications(self, notification_service):
        """Test in-app notification storage"""
        notification_service.send_custom(
            "in-app-default", "Subject 1", "Body 1",
            metadata={"recipient": "user-1"},
        )
        
        # Get in-app notifications
        notifications = notification_service.get_in_app_notifications("")
        assert len(notifications) >= 1
    
    def test_notification_stats(self, notification_service):
        """Test notification statistics"""
        notification_service.send_custom("in-app-default", "Test 1", "Body")
        notification_service.send_custom("in-app-default", "Test 2", "Body")
        
        stats = notification_service.get_stats()
        
        assert stats["total"] >= 2
        assert stats["delivered"] >= 2


# =============================================================================
# Test: Scheduler
# =============================================================================

class TestScheduler:
    """Tests for job scheduler"""
    
    def test_scheduler_initialization(self, scheduler):
        """Test scheduler initializes with default jobs"""
        jobs = scheduler.get_job_status()
        
        assert len(jobs) >= 4  # Default jobs
        job_types = [j["job_type"] for j in jobs]
        assert "retraining_check" in job_types
        assert "metrics_aggregation" in job_types
    
    def test_add_custom_job(self, scheduler):
        """Test adding custom job"""
        job = ScheduledJob(
            job_id="custom-job",
            name="Custom Job",
            job_type="health_check",
            cron_expression="*/5 * * * *",
        )
        
        scheduler.add_job(job)
        
        jobs = scheduler.get_job_status()
        assert any(j["job_id"] == "custom-job" for j in jobs)
    
    def test_run_job_now(self, scheduler):
        """Test immediate job execution"""
        execution = scheduler.run_now("health-check")
        
        assert execution is not None
        assert execution.status == JobStatus.COMPLETED
    
    def test_enable_disable_job(self, scheduler):
        """Test job enable/disable"""
        scheduler.disable_job("health-check")
        
        jobs = scheduler.get_job_status()
        health_job = next(j for j in jobs if j["job_id"] == "health-check")
        assert health_job["is_enabled"] is False
        
        scheduler.enable_job("health-check")
        jobs = scheduler.get_job_status()
        health_job = next(j for j in jobs if j["job_id"] == "health-check")
        assert health_job["is_enabled"] is True
    
    def test_execution_history(self, scheduler):
        """Test execution history tracking"""
        scheduler.run_now("health-check")
        scheduler.run_now("health-check")
        
        history = scheduler.get_execution_history(job_id="health-check")
        
        assert len(history) >= 2
        assert all(e["job_id"] == "health-check" for e in history)
    
    def test_scheduler_stats(self, scheduler):
        """Test scheduler statistics"""
        scheduler.run_now("health-check")
        
        stats = scheduler.get_stats()
        
        assert "total_jobs" in stats
        assert "total_executions" in stats
        assert stats["total_executions"] >= 1


# =============================================================================
# Test: Health Checks
# =============================================================================

class TestHealthChecker:
    """Tests for health checker"""
    
    def test_check_all(self, health_checker):
        """Test comprehensive health check"""
        health = health_checker.check_all()
        
        assert health.overall_status in list(HealthStatus)
        assert len(health.components) >= 4
    
    def test_individual_component_check(self, health_checker):
        """Test checking individual component"""
        component = health_checker.check_component("model_registry")
        
        assert component is not None
        assert component.name == "model_registry"
        assert component.status in list(HealthStatus)
    
    def test_is_healthy(self, health_checker):
        """Test quick health check"""
        result = health_checker.is_healthy()
        assert isinstance(result, bool)
    
    def test_is_ready(self, health_checker):
        """Test readiness check"""
        result = health_checker.is_ready()
        assert isinstance(result, bool)
    
    def test_is_live(self, health_checker):
        """Test liveness check"""
        result = health_checker.is_live()
        assert result is True
    
    def test_uptime_tracking(self, health_checker):
        """Test uptime calculation"""
        uptime = health_checker.get_uptime_seconds()
        assert uptime >= 0


# =============================================================================
# Test: Diagnostics
# =============================================================================

class TestDiagnosticsRunner:
    """Tests for diagnostics runner"""
    
    def test_full_diagnostics(self, hvacr_system, metrics_collector):
        """Test comprehensive diagnostics"""
        runner = DiagnosticsRunner(hvacr_system, metrics_collector)
        
        diagnostics = runner.run_full_diagnostics()
        
        assert "timestamp" in diagnostics
        assert "system_status" in diagnostics
        assert "model_summary" in diagnostics
        assert "recommendations" in diagnostics
    
    def test_recommendations_generation(self, hvacr_system, metrics_collector):
        """Test recommendation generation"""
        runner = DiagnosticsRunner(hvacr_system, metrics_collector)
        
        diagnostics = runner.run_full_diagnostics()
        
        assert "recommendations" in diagnostics
        assert isinstance(diagnostics["recommendations"], list)


# =============================================================================
# Test: Observability Stack
# =============================================================================

class TestObservabilityStack:
    """Tests for full observability stack"""
    
    def test_stack_initialization(self, observability_stack):
        """Test stack initialization"""
        assert observability_stack.system is not None
        assert observability_stack.metrics is not None
        assert observability_stack.api is not None
        assert observability_stack.scheduler is not None
        assert observability_stack.health_checker is not None
    
    def test_get_status(self, observability_stack):
        """Test stack status"""
        status = observability_stack.get_status()
        
        assert "system" in status
        assert "health" in status
        assert "scheduler" in status
        assert "notifications" in status
        assert "metrics" in status


# =============================================================================
# Test: End-to-End Integration
# =============================================================================

class TestEndToEndObservability:
    """End-to-end integration tests"""
    
    def test_full_workflow(self, observability_stack):
        """Test complete observability workflow"""
        stack = observability_stack
        system = stack.system
        
        # 1. Register and deploy model
        model = ModelVersion(
            version_id="e2e-obs-v1",
            model_name="e2e_obs_model",
            model_type=ModelType.ANOMALY_DETECTION,
            version_number="1.0.0",
            created_at=datetime.utcnow(),
            created_by="test",
            stage=ModelStage.STAGING,
        )
        model.validation_metrics = PerformanceMetrics(
            metrics_id="e2e-m1", model_version_id="e2e-obs-v1",
            computed_at=datetime.utcnow(),
            accuracy=0.95, f1_score=0.92,
        )
        system.register_model(model)
        system.deploy_model("e2e-obs-v1", "test", skip_approval=True)
        
        # 2. Record metrics
        stack.metrics.record_model_metrics("e2e_obs_model", "1.0.0", model.validation_metrics)
        stack.metrics.record_prediction("e2e_obs_model", "1.0.0", 15.0, is_correct=True)
        
        # 3. Check via API
        models_response = stack.api.list_models()
        assert models_response["success"] is True
        
        # 4. Run health check
        health = stack.health_checker.check_all()
        assert health.overall_status != HealthStatus.UNHEALTHY
        
        # 5. Get dashboard
        dashboard = stack.api.get_dashboard()
        assert dashboard["success"] is True
        
        # 6. Check status
        status = stack.get_status()
        assert "system" in status


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
