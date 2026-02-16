"""
Phase 5: Observability & API Layer - Metrics Collector

Collects and manages metrics for model performance, experiments, and system health.
"""

import logging
import threading
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .observability_models import (
    Alert,
    AlertRule,
    AlertSeverity,
    AlertState,
    MetricNamespace,
    MetricPoint,
    MetricSeries,
    MetricType,
)
from .learning_loop_models import ModelType, PerformanceMetrics

logger = logging.getLogger(__name__)


class MetricsCollector:
    """
    Central metrics collection and storage system.
    Supports Prometheus-compatible export.
    """
    
    def __init__(self, retention_hours: int = 168):
        self.retention_hours = retention_hours
        self.series: Dict[str, MetricSeries] = {}
        self.alert_rules: Dict[str, AlertRule] = {}
        self.active_alerts: Dict[str, Alert] = {}
        self.resolved_alerts: List[Alert] = []
        self._lock = threading.Lock()
        self._start_time = datetime.utcnow()
        
        self._initialize_default_rules()
        logger.info("MetricsCollector initialized")
    
    def _get_series_key(self, name: str, namespace: MetricNamespace, 
                        labels: Dict[str, str]) -> str:
        """Generate unique key for a metric series"""
        sorted_labels = sorted(labels.items())
        label_str = ",".join(f"{k}={v}" for k, v in sorted_labels)
        return f"{namespace.value}:{name}:{label_str}"
    
    def record(self, name: str, value: float, 
               namespace: MetricNamespace = MetricNamespace.SYSTEM,
               labels: Dict[str, str] = None,
               metric_type: MetricType = MetricType.GAUGE,
               timestamp: Optional[datetime] = None):
        """Record a metric value"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            if key not in self.series:
                self.series[key] = MetricSeries(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    retention_hours=self.retention_hours,
                )
            
            self.series[key].add_point(value, timestamp)
        
        # Check alert rules
        self._evaluate_alerts(name, namespace, labels, value)
    
    def increment(self, name: str, value: float = 1.0,
                  namespace: MetricNamespace = MetricNamespace.SYSTEM,
                  labels: Dict[str, str] = None):
        """Increment a counter metric"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            if key not in self.series:
                self.series[key] = MetricSeries(
                    name=name,
                    namespace=namespace,
                    labels=labels,
                    retention_hours=self.retention_hours,
                )
            
            current = self.series[key].get_latest()
            new_value = (current.value if current else 0) + value
            self.series[key].add_point(new_value)
    
    def get_metric(self, name: str, namespace: MetricNamespace,
                   labels: Dict[str, str] = None) -> Optional[MetricPoint]:
        """Get latest value for a metric"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            if key in self.series:
                return self.series[key].get_latest()
        return None
    
    def get_series(self, name: str, namespace: MetricNamespace,
                   labels: Dict[str, str] = None) -> Optional[MetricSeries]:
        """Get a metric series"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            return self.series.get(key)
    
    def query_range(self, name: str, namespace: MetricNamespace,
                    start: datetime, end: datetime,
                    labels: Dict[str, str] = None) -> List[MetricPoint]:
        """Query metric values in time range"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            if key in self.series:
                return self.series[key].get_range(start, end)
        return []
    
    def get_stats(self, name: str, namespace: MetricNamespace,
                  labels: Dict[str, str] = None,
                  window_minutes: int = 60) -> Dict[str, float]:
        """Get statistics for a metric over recent window"""
        labels = labels or {}
        key = self._get_series_key(name, namespace, labels)
        
        with self._lock:
            if key in self.series:
                return self.series[key].compute_stats(window_minutes)
        return {}
    
    # =========================================================================
    # Model Performance Metrics
    # =========================================================================
    
    def record_model_metrics(self, model_name: str, model_version: str,
                             metrics: PerformanceMetrics):
        """Record model performance metrics"""
        labels = {"model_name": model_name, "model_version": model_version}
        
        if metrics.accuracy is not None:
            self.record("accuracy", metrics.accuracy, MetricNamespace.MODEL, labels)
        if metrics.precision is not None:
            self.record("precision", metrics.precision, MetricNamespace.MODEL, labels)
        if metrics.recall is not None:
            self.record("recall", metrics.recall, MetricNamespace.MODEL, labels)
        if metrics.f1_score is not None:
            self.record("f1_score", metrics.f1_score, MetricNamespace.MODEL, labels)
        if metrics.auc_roc is not None:
            self.record("auc_roc", metrics.auc_roc, MetricNamespace.MODEL, labels)
        if metrics.inference_latency_p95_ms is not None:
            self.record("inference_latency_p95_ms", metrics.inference_latency_p95_ms, 
                       MetricNamespace.MODEL, labels)
        if metrics.n_samples is not None:
            self.record("n_samples", metrics.n_samples, MetricNamespace.MODEL, labels)
    
    def record_prediction(self, model_name: str, model_version: str,
                          latency_ms: float, is_correct: Optional[bool] = None):
        """Record a single prediction event"""
        labels = {"model_name": model_name, "model_version": model_version}
        
        self.increment("predictions_total", 1, MetricNamespace.MODEL, labels)
        self.record("prediction_latency_ms", latency_ms, MetricNamespace.MODEL, labels)
        
        if is_correct is not None:
            if is_correct:
                self.increment("predictions_correct", 1, MetricNamespace.MODEL, labels)
            else:
                self.increment("predictions_incorrect", 1, MetricNamespace.MODEL, labels)
    
    # =========================================================================
    # Experiment Metrics
    # =========================================================================
    
    def record_experiment_metrics(self, experiment_id: str, variant_id: str,
                                  n_predictions: int, accuracy: float):
        """Record A/B experiment metrics"""
        labels = {"experiment_id": experiment_id, "variant_id": variant_id}
        
        self.record("variant_predictions", n_predictions, MetricNamespace.EXPERIMENT, labels)
        self.record("variant_accuracy", accuracy, MetricNamespace.EXPERIMENT, labels)
    
    def record_experiment_conclusion(self, experiment_id: str, 
                                     winner_variant: str, p_value: float):
        """Record experiment conclusion"""
        labels = {"experiment_id": experiment_id}
        
        self.record("p_value", p_value, MetricNamespace.EXPERIMENT, labels)
        self.increment("experiments_concluded", 1, MetricNamespace.EXPERIMENT)
    
    # =========================================================================
    # Retraining Metrics
    # =========================================================================
    
    def record_retraining_trigger(self, model_name: str, trigger_type: str):
        """Record retraining trigger event"""
        labels = {"model_name": model_name, "trigger_type": trigger_type}
        self.increment("retraining_triggers_total", 1, MetricNamespace.RETRAINING, labels)
    
    def record_retraining_job(self, model_name: str, status: str,
                              duration_seconds: Optional[float] = None):
        """Record retraining job completion"""
        labels = {"model_name": model_name, "status": status}
        self.increment("retraining_jobs_total", 1, MetricNamespace.RETRAINING, labels)
        
        if duration_seconds is not None:
            self.record("retraining_duration_seconds", duration_seconds, 
                       MetricNamespace.RETRAINING, {"model_name": model_name})
    
    # =========================================================================
    # Governance Metrics
    # =========================================================================
    
    def record_approval_request(self, action_type: str, risk_level: str):
        """Record approval request"""
        labels = {"action_type": action_type, "risk_level": risk_level}
        self.increment("approval_requests_total", 1, MetricNamespace.GOVERNANCE, labels)
    
    def record_approval_decision(self, action_type: str, approved: bool,
                                 duration_seconds: float):
        """Record approval decision"""
        status = "approved" if approved else "rejected"
        labels = {"action_type": action_type, "status": status}
        
        self.increment("approval_decisions_total", 1, MetricNamespace.GOVERNANCE, labels)
        self.record("approval_duration_seconds", duration_seconds, 
                   MetricNamespace.GOVERNANCE, {"action_type": action_type})
    
    # =========================================================================
    # Case Metrics
    # =========================================================================
    
    def record_case_created(self, model_type: str):
        """Record case creation"""
        labels = {"model_type": model_type}
        self.increment("cases_created_total", 1, MetricNamespace.CASE, labels)
    
    def record_case_outcome(self, model_type: str, outcome: str,
                            prediction_accurate: bool):
        """Record case outcome"""
        labels = {"model_type": model_type, "outcome": outcome}
        self.increment("cases_closed_total", 1, MetricNamespace.CASE, labels)
        
        if prediction_accurate:
            self.increment("predictions_accurate_total", 1, MetricNamespace.CASE, 
                          {"model_type": model_type})
    
    # =========================================================================
    # System Metrics
    # =========================================================================
    
    def record_system_metric(self, name: str, value: float, 
                             component: str = "hvacr_system"):
        """Record system-level metric"""
        labels = {"component": component}
        self.record(name, value, MetricNamespace.SYSTEM, labels)
    
    def get_uptime_seconds(self) -> float:
        """Get system uptime in seconds"""
        return (datetime.utcnow() - self._start_time).total_seconds()
    
    # =========================================================================
    # Alert Rules
    # =========================================================================
    
    def _initialize_default_rules(self):
        """Set up default alert rules"""
        # Model accuracy degradation
        self.add_alert_rule(AlertRule(
            rule_id="model_accuracy_low",
            name="Model Accuracy Low",
            description="Model accuracy dropped below threshold",
            metric_name="accuracy",
            namespace=MetricNamespace.MODEL,
            comparison="<",
            threshold=0.8,
            severity=AlertSeverity.WARNING,
            duration_seconds=300,
        ))
        
        # High latency
        self.add_alert_rule(AlertRule(
            rule_id="high_latency",
            name="High Inference Latency",
            description="Model inference latency is high",
            metric_name="inference_latency_p95_ms",
            namespace=MetricNamespace.MODEL,
            comparison=">",
            threshold=100,
            severity=AlertSeverity.WARNING,
            duration_seconds=60,
        ))
        
        # Retraining job failure
        self.add_alert_rule(AlertRule(
            rule_id="retraining_failure",
            name="Retraining Job Failed",
            description="Retraining job has failed",
            metric_name="retraining_jobs_total",
            namespace=MetricNamespace.RETRAINING,
            comparison=">",
            threshold=0,
            severity=AlertSeverity.ERROR,
            duration_seconds=0,
            labels={"status": "failed"},
        ))
    
    def add_alert_rule(self, rule: AlertRule):
        """Add an alert rule"""
        self.alert_rules[rule.rule_id] = rule
        logger.info(f"Added alert rule: {rule.name}")
    
    def remove_alert_rule(self, rule_id: str):
        """Remove an alert rule"""
        if rule_id in self.alert_rules:
            del self.alert_rules[rule_id]
    
    def _evaluate_alerts(self, metric_name: str, namespace: MetricNamespace,
                         labels: Dict[str, str], value: float):
        """Evaluate alert rules for a metric"""
        for rule in self.alert_rules.values():
            if not rule.is_enabled:
                continue
            
            if rule.metric_name != metric_name or rule.namespace != namespace:
                continue
            
            # Check label match
            if rule.labels:
                if not all(labels.get(k) == v for k, v in rule.labels.items()):
                    continue
            
            alert_key = f"{rule.rule_id}:{self._get_series_key(metric_name, namespace, labels)}"
            
            if rule.evaluate(value):
                if alert_key not in self.active_alerts:
                    # Create new pending alert
                    alert = Alert(
                        rule_id=rule.rule_id,
                        rule_name=rule.name,
                        severity=rule.severity,
                        state=AlertState.PENDING,
                        message=f"{rule.name}: {metric_name} = {value} (threshold: {rule.comparison} {rule.threshold})",
                        metric_name=metric_name,
                        metric_value=value,
                        threshold=rule.threshold,
                        labels=labels.copy(),
                        annotations=rule.annotations.copy(),
                    )
                    self.active_alerts[alert_key] = alert
                else:
                    # Update existing alert
                    alert = self.active_alerts[alert_key]
                    alert.metric_value = value
                    
                    # Check if should fire (duration exceeded)
                    if alert.state == AlertState.PENDING:
                        elapsed = (datetime.utcnow() - alert.started_at).total_seconds()
                        if elapsed >= rule.duration_seconds:
                            alert.fire()
                            logger.warning(f"Alert fired: {alert.message}")
            else:
                # Condition no longer met - resolve alert
                if alert_key in self.active_alerts:
                    alert = self.active_alerts[alert_key]
                    if alert.state in [AlertState.FIRING, AlertState.PENDING]:
                        alert.resolve()
                        self.resolved_alerts.append(alert)
                        del self.active_alerts[alert_key]
                        logger.info(f"Alert resolved: {alert.rule_name}")
    
    def get_active_alerts(self) -> List[Alert]:
        """Get all active alerts"""
        return list(self.active_alerts.values())
    
    def get_firing_alerts(self) -> List[Alert]:
        """Get only firing alerts"""
        return [a for a in self.active_alerts.values() if a.state == AlertState.FIRING]
    
    def acknowledge_alert(self, alert_id: str, user_id: str) -> bool:
        """Acknowledge an alert"""
        for alert in self.active_alerts.values():
            if alert.alert_id == alert_id:
                alert.acknowledge(user_id)
                return True
        return False
    
    def silence_alert(self, alert_id: str, duration_minutes: int) -> bool:
        """Silence an alert"""
        for alert in self.active_alerts.values():
            if alert.alert_id == alert_id:
                alert.silence(duration_minutes)
                return True
        return False
    
    # =========================================================================
    # Export
    # =========================================================================
    
    def export_prometheus(self) -> str:
        """Export all metrics in Prometheus format"""
        lines = []
        
        with self._lock:
            for series in self.series.values():
                latest = series.get_latest()
                if latest:
                    lines.append(latest.to_prometheus())
        
        return "\n".join(lines)
    
    def export_json(self) -> Dict[str, Any]:
        """Export all metrics as JSON"""
        result = {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": self.get_uptime_seconds(),
            "metrics": {},
            "active_alerts": [a.to_dict() for a in self.active_alerts.values()],
        }
        
        with self._lock:
            for key, series in self.series.items():
                latest = series.get_latest()
                if latest:
                    result["metrics"][key] = {
                        "value": latest.value,
                        "timestamp": latest.timestamp.isoformat(),
                        "labels": latest.labels,
                    }
        
        return result
    
    def get_dashboard_summary(self) -> Dict[str, Any]:
        """Get summary for dashboard display"""
        model_metrics = {}
        experiment_metrics = {}
        system_metrics = {}
        
        with self._lock:
            for key, series in self.series.items():
                latest = series.get_latest()
                if not latest:
                    continue
                
                if series.namespace == MetricNamespace.MODEL:
                    model_name = series.labels.get("model_name", "unknown")
                    if model_name not in model_metrics:
                        model_metrics[model_name] = {}
                    model_metrics[model_name][series.name] = latest.value
                
                elif series.namespace == MetricNamespace.EXPERIMENT:
                    exp_id = series.labels.get("experiment_id", "unknown")
                    if exp_id not in experiment_metrics:
                        experiment_metrics[exp_id] = {}
                    experiment_metrics[exp_id][series.name] = latest.value
                
                elif series.namespace == MetricNamespace.SYSTEM:
                    system_metrics[series.name] = latest.value
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "uptime_seconds": self.get_uptime_seconds(),
            "models": model_metrics,
            "experiments": experiment_metrics,
            "system": system_metrics,
            "alerts": {
                "active": len(self.active_alerts),
                "firing": len(self.get_firing_alerts()),
            },
        }
