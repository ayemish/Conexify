"""
Phase 5: Observability & API Layer

Main entry point that exports all observability components.

Components:
- Data Models: MetricPoint, Alert, NotificationChannel, HealthStatus
- Metrics Collector: Prometheus-compatible metrics collection
- REST API: HTTP endpoints for HVACRPdMSystem
- Notifications: Alert delivery to multiple channels
- Scheduler: Cron-like job scheduling
- Health Checks: System health monitoring

Example Usage:
    from .observability import (
        ObservabilityStack,
        HVACRPdMAPI,
        MetricsCollector,
        NotificationService,
        Scheduler,
        HealthChecker,
    )
    
    # Initialize with HVACRPdMSystem
    from .learning_loop import HVACRPdMSystem
    system = HVACRPdMSystem(site_id="site-001")
    
    # Create observability stack
    obs = ObservabilityStack(system)
    
    # Access components
    api = obs.api
    metrics = obs.metrics
    notifications = obs.notifications
    scheduler = obs.scheduler
    health = obs.health_checker
    
    # Start scheduler (background thread)
    scheduler.start()
    
    # API endpoints
    models = api.list_models()
    health_status = api.get_health()
"""

from .observability_models import (
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
    Alert,
    NotificationChannel,
    Notification,
    ScheduledJob,
    JobExecution,
    ComponentHealth,
    SystemHealth,
)

from .observability_metrics import MetricsCollector

from .observability_api import (
    HVACRPdMAPI,
    APIResponse,
    APIError,
)

from .observability_notifications import (
    NotificationService,
    NotificationProvider,
    WebhookProvider,
    EmailProvider,
    SlackProvider,
    InAppProvider,
    create_default_notification_service,
)

from .observability_scheduler import (
    Scheduler,
    JobRunner,
    CronParser,
)

from .observability_health import (
    HealthChecker,
    DiagnosticsRunner,
)

from .learning_loop_hvacr import HVACRPdMSystem


class ObservabilityStack:
    """
    Complete observability stack for HVACRPdMSystem.
    Provides unified access to all observability components.
    """
    
    def __init__(self, system: HVACRPdMSystem):
        self.system = system
        
        # Initialize components
        self.metrics = MetricsCollector()
        self.notifications = create_default_notification_service()
        self.api = HVACRPdMAPI(system, self.metrics)
        self.scheduler = Scheduler(system, self.metrics)
        self.health_checker = HealthChecker(system, self.metrics)
        self.diagnostics = DiagnosticsRunner(system, self.metrics)
        
        # Wire up alert notifications
        self._setup_alert_notifications()
    
    def _setup_alert_notifications(self):
        """Connect metrics alerts to notification service"""
        # When alerts fire, send notifications
        original_evaluate = self.metrics._evaluate_alerts
        
        def evaluate_with_notify(metric_name, namespace, labels, value):
            # Call original
            original_evaluate(metric_name, namespace, labels, value)
            
            # Check for newly fired alerts
            for alert in self.metrics.active_alerts.values():
                if alert.state == AlertState.FIRING and not alert.notification_sent:
                    self.notifications.notify_alert(alert)
                    alert.notification_sent = True
        
        self.metrics._evaluate_alerts = evaluate_with_notify
    
    def start(self):
        """Start background services"""
        self.scheduler.start()
    
    def stop(self):
        """Stop background services"""
        self.scheduler.stop()
    
    def get_status(self):
        """Get overall observability stack status"""
        return {
            "system": self.system.get_system_status(),
            "health": self.health_checker.check_all().to_dict(),
            "scheduler": self.scheduler.get_stats(),
            "notifications": self.notifications.get_stats(),
            "metrics": self.metrics.get_dashboard_summary(),
        }


__all__ = [
    # Enums
    "MetricType",
    "MetricNamespace",
    "AlertSeverity",
    "AlertState",
    "NotificationChannelType",
    "HealthStatus",
    "JobStatus",
    # Data Models
    "MetricPoint",
    "MetricSeries",
    "AlertRule",
    "Alert",
    "NotificationChannel",
    "Notification",
    "ScheduledJob",
    "JobExecution",
    "ComponentHealth",
    "SystemHealth",
    # Components
    "MetricsCollector",
    "HVACRPdMAPI",
    "APIResponse",
    "APIError",
    "NotificationService",
    "NotificationProvider",
    "WebhookProvider",
    "EmailProvider",
    "SlackProvider",
    "InAppProvider",
    "create_default_notification_service",
    "Scheduler",
    "JobRunner",
    "CronParser",
    "HealthChecker",
    "DiagnosticsRunner",
    # Stack
    "ObservabilityStack",
]
