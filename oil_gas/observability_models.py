"""
Phase 5: Observability & API Layer - Data Models

Data models for metrics, alerts, notifications, and system health.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional


class MetricType(Enum):
    """Types of metrics collected"""
    GAUGE = "gauge"          # Point-in-time value (e.g., accuracy)
    COUNTER = "counter"      # Monotonically increasing (e.g., predictions_total)
    HISTOGRAM = "histogram"  # Distribution (e.g., latency)
    SUMMARY = "summary"      # Quantiles


class MetricNamespace(Enum):
    """Namespaces for metric organization"""
    MODEL = "model"                    # Model performance metrics
    EXPERIMENT = "experiment"          # A/B test metrics
    RETRAINING = "retraining"          # Retraining pipeline metrics
    GOVERNANCE = "governance"          # Approval workflow metrics
    SYSTEM = "system"                  # System health metrics
    CASE = "case"                      # Case management metrics


class AlertSeverity(Enum):
    """Alert severity levels"""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class AlertState(Enum):
    """Alert lifecycle states"""
    FIRING = "firing"
    PENDING = "pending"
    RESOLVED = "resolved"
    SILENCED = "silenced"
    ACKNOWLEDGED = "acknowledged"


class NotificationChannelType(Enum):
    """Notification delivery channels"""
    EMAIL = "email"
    SLACK = "slack"
    WEBHOOK = "webhook"
    SMS = "sms"
    PAGERDUTY = "pagerduty"
    IN_APP = "in_app"


class HealthStatus(Enum):
    """System component health status"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


class JobStatus(Enum):
    """Scheduled job status"""
    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    SKIPPED = "skipped"


@dataclass
class MetricPoint:
    """Single metric data point"""
    metric_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    namespace: MetricNamespace = MetricNamespace.SYSTEM
    metric_type: MetricType = MetricType.GAUGE
    value: float = 0.0
    timestamp: datetime = field(default_factory=datetime.utcnow)
    labels: Dict[str, str] = field(default_factory=dict)
    unit: str = ""
    description: str = ""
    
    def to_prometheus(self) -> str:
        """Export in Prometheus format"""
        labels_str = ",".join(f'{k}="{v}"' for k, v in self.labels.items())
        metric_name = f"{self.namespace.value}_{self.name}".replace(".", "_")
        if labels_str:
            return f"{metric_name}{{{labels_str}}} {self.value} {int(self.timestamp.timestamp() * 1000)}"
        return f"{metric_name} {self.value} {int(self.timestamp.timestamp() * 1000)}"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "metric_id": self.metric_id,
            "name": self.name,
            "namespace": self.namespace.value,
            "metric_type": self.metric_type.value,
            "value": self.value,
            "timestamp": self.timestamp.isoformat(),
            "labels": self.labels,
            "unit": self.unit,
        }


@dataclass
class MetricSeries:
    """Time series of metric points"""
    series_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    namespace: MetricNamespace = MetricNamespace.SYSTEM
    labels: Dict[str, str] = field(default_factory=dict)
    points: List[MetricPoint] = field(default_factory=list)
    retention_hours: int = 168  # 7 days default
    
    def add_point(self, value: float, timestamp: Optional[datetime] = None):
        """Add a new point to the series"""
        point = MetricPoint(
            name=self.name,
            namespace=self.namespace,
            value=value,
            timestamp=timestamp or datetime.utcnow(),
            labels=self.labels.copy(),
        )
        self.points.append(point)
        self._prune_old_points()
    
    def _prune_old_points(self):
        """Remove points older than retention period"""
        cutoff = datetime.utcnow() - timedelta(hours=self.retention_hours)
        self.points = [p for p in self.points if p.timestamp > cutoff]
    
    def get_latest(self) -> Optional[MetricPoint]:
        """Get most recent point"""
        return self.points[-1] if self.points else None
    
    def get_range(self, start: datetime, end: datetime) -> List[MetricPoint]:
        """Get points in time range"""
        return [p for p in self.points if start <= p.timestamp <= end]
    
    def compute_stats(self, window_minutes: int = 60) -> Dict[str, float]:
        """Compute statistics over recent window"""
        cutoff = datetime.utcnow() - timedelta(minutes=window_minutes)
        recent = [p.value for p in self.points if p.timestamp > cutoff]
        
        if not recent:
            return {}
        
        import statistics
        return {
            "min": min(recent),
            "max": max(recent),
            "avg": statistics.mean(recent),
            "count": len(recent),
            "stddev": statistics.stdev(recent) if len(recent) > 1 else 0,
        }


@dataclass
class AlertRule:
    """Alert rule definition"""
    rule_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    description: str = ""
    metric_name: str = ""
    namespace: MetricNamespace = MetricNamespace.SYSTEM
    condition: str = ""  # e.g., "> 0.1", "< 0.8", "== 0"
    threshold: float = 0.0
    comparison: str = ">"  # >, <, >=, <=, ==, !=
    severity: AlertSeverity = AlertSeverity.WARNING
    duration_seconds: int = 60  # Must be true for this duration
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    notification_channels: List[str] = field(default_factory=list)
    is_enabled: bool = True
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def evaluate(self, value: float) -> bool:
        """Evaluate if condition is met"""
        if self.comparison == ">":
            return value > self.threshold
        elif self.comparison == "<":
            return value < self.threshold
        elif self.comparison == ">=":
            return value >= self.threshold
        elif self.comparison == "<=":
            return value <= self.threshold
        elif self.comparison == "==":
            return value == self.threshold
        elif self.comparison == "!=":
            return value != self.threshold
        return False


@dataclass
class Alert:
    """Active alert instance"""
    alert_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    rule_id: str = ""
    rule_name: str = ""
    severity: AlertSeverity = AlertSeverity.WARNING
    state: AlertState = AlertState.PENDING
    message: str = ""
    metric_name: str = ""
    metric_value: float = 0.0
    threshold: float = 0.0
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.utcnow)
    fired_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    silenced_until: Optional[datetime] = None
    notification_sent: bool = False
    
    def fire(self):
        """Transition to firing state"""
        self.state = AlertState.FIRING
        self.fired_at = datetime.utcnow()
    
    def resolve(self):
        """Resolve the alert"""
        self.state = AlertState.RESOLVED
        self.resolved_at = datetime.utcnow()
    
    def acknowledge(self, user_id: str):
        """Acknowledge the alert"""
        self.state = AlertState.ACKNOWLEDGED
        self.acknowledged_by = user_id
        self.acknowledged_at = datetime.utcnow()
    
    def silence(self, duration_minutes: int):
        """Silence the alert temporarily"""
        self.state = AlertState.SILENCED
        self.silenced_until = datetime.utcnow() + timedelta(minutes=duration_minutes)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "severity": self.severity.value,
            "state": self.state.value,
            "message": self.message,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "threshold": self.threshold,
            "labels": self.labels,
            "started_at": self.started_at.isoformat(),
            "fired_at": self.fired_at.isoformat() if self.fired_at else None,
            "resolved_at": self.resolved_at.isoformat() if self.resolved_at else None,
        }


@dataclass
class NotificationChannel:
    """Notification delivery channel configuration"""
    channel_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    channel_type: NotificationChannelType = NotificationChannelType.WEBHOOK
    config: Dict[str, Any] = field(default_factory=dict)
    is_enabled: bool = True
    severity_filter: List[AlertSeverity] = field(default_factory=lambda: list(AlertSeverity))
    rate_limit_per_hour: int = 100
    last_sent_at: Optional[datetime] = None
    sent_count_hour: int = 0
    
    def can_send(self) -> bool:
        """Check if rate limit allows sending"""
        if not self.is_enabled:
            return False
        if self.last_sent_at:
            if (datetime.utcnow() - self.last_sent_at).total_seconds() > 3600:
                self.sent_count_hour = 0
        return self.sent_count_hour < self.rate_limit_per_hour
    
    def record_send(self):
        """Record a notification sent"""
        self.sent_count_hour += 1
        self.last_sent_at = datetime.utcnow()


@dataclass
class Notification:
    """Notification message"""
    notification_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    alert_id: str = ""
    channel_id: str = ""
    channel_type: NotificationChannelType = NotificationChannelType.WEBHOOK
    recipient: str = ""
    subject: str = ""
    body: str = ""
    severity: AlertSeverity = AlertSeverity.INFO
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivered: bool = False
    error_message: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ScheduledJob:
    """Scheduled job definition"""
    job_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    description: str = ""
    job_type: str = ""  # retraining_check, metrics_aggregation, etc.
    cron_expression: str = ""  # Cron schedule
    is_enabled: bool = True
    last_run_at: Optional[datetime] = None
    next_run_at: Optional[datetime] = None
    timeout_seconds: int = 3600
    retry_count: int = 3
    retry_delay_seconds: int = 60
    config: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class JobExecution:
    """Job execution record"""
    execution_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    job_id: str = ""
    job_name: str = ""
    status: JobStatus = JobStatus.SCHEDULED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error_message: Optional[str] = None
    retry_attempt: int = 0
    
    def start(self):
        """Mark job as started"""
        self.status = JobStatus.RUNNING
        self.started_at = datetime.utcnow()
    
    def complete(self, result: Dict[str, Any] = None):
        """Mark job as completed"""
        self.status = JobStatus.COMPLETED
        self.completed_at = datetime.utcnow()
        self.result = result or {}
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()
    
    def fail(self, error: str):
        """Mark job as failed"""
        self.status = JobStatus.FAILED
        self.completed_at = datetime.utcnow()
        self.error_message = error
        if self.started_at:
            self.duration_seconds = (self.completed_at - self.started_at).total_seconds()


@dataclass
class ComponentHealth:
    """Health status of a system component"""
    component_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    name: str = ""
    status: HealthStatus = HealthStatus.UNKNOWN
    message: str = ""
    last_check_at: datetime = field(default_factory=datetime.utcnow)
    response_time_ms: Optional[float] = None
    details: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "component_id": self.component_id,
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "last_check_at": self.last_check_at.isoformat(),
            "response_time_ms": self.response_time_ms,
            "details": self.details,
        }


@dataclass
class SystemHealth:
    """Overall system health status"""
    check_id: str = field(default_factory=lambda: str(uuid.uuid4())[:12])
    timestamp: datetime = field(default_factory=datetime.utcnow)
    overall_status: HealthStatus = HealthStatus.UNKNOWN
    components: List[ComponentHealth] = field(default_factory=list)
    version: str = "1.0.0"
    uptime_seconds: float = 0.0
    
    def compute_overall_status(self):
        """Compute overall status from component statuses"""
        if not self.components:
            self.overall_status = HealthStatus.UNKNOWN
            return
        
        statuses = [c.status for c in self.components]
        
        if any(s == HealthStatus.UNHEALTHY for s in statuses):
            self.overall_status = HealthStatus.UNHEALTHY
        elif any(s == HealthStatus.DEGRADED for s in statuses):
            self.overall_status = HealthStatus.DEGRADED
        elif all(s == HealthStatus.HEALTHY for s in statuses):
            self.overall_status = HealthStatus.HEALTHY
        else:
            self.overall_status = HealthStatus.DEGRADED
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "check_id": self.check_id,
            "timestamp": self.timestamp.isoformat(),
            "overall_status": self.overall_status.value,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "components": [c.to_dict() for c in self.components],
        }
