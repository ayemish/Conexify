"""
PDM Metrics Collection

Prometheus-compatible metrics for monitoring the PDM system.
"""

import time
import logging
from typing import Dict, List, Optional, Any, Callable
from functools import wraps
from dataclasses import dataclass, field
from collections import defaultdict
from threading import Lock

logger = logging.getLogger(__name__)

# Try to import prometheus_client
PROMETHEUS_AVAILABLE = False
try:
    from prometheus_client import (
        Counter, Gauge, Histogram, Summary,
        CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
        start_http_server as prom_start_server
    )
    PROMETHEUS_AVAILABLE = True
except ImportError:
    logger.warning("prometheus_client not installed. Using in-memory metrics fallback.")


# =============================================================================
# In-Memory Metrics Fallback
# =============================================================================

@dataclass
class InMemoryMetric:
    """Simple in-memory metric storage"""
    name: str
    help_text: str
    metric_type: str
    labels: List[str] = field(default_factory=list)
    values: Dict[tuple, float] = field(default_factory=dict)
    lock: Lock = field(default_factory=Lock)
    
    def labels_to_key(self, label_values: Dict[str, str]) -> tuple:
        return tuple(label_values.get(l, "") for l in self.labels)
    
    def inc(self, value: float = 1, **label_values):
        with self.lock:
            key = self.labels_to_key(label_values)
            self.values[key] = self.values.get(key, 0) + value
    
    def dec(self, value: float = 1, **label_values):
        with self.lock:
            key = self.labels_to_key(label_values)
            self.values[key] = self.values.get(key, 0) - value
    
    def set(self, value: float, **label_values):
        with self.lock:
            key = self.labels_to_key(label_values)
            self.values[key] = value
    
    def observe(self, value: float, **label_values):
        # For histograms/summaries, just track the latest and count
        with self.lock:
            key = self.labels_to_key(label_values)
            count_key = key + ("_count",)
            sum_key = key + ("_sum",)
            self.values[count_key] = self.values.get(count_key, 0) + 1
            self.values[sum_key] = self.values.get(sum_key, 0) + value
    
    def get_all(self) -> Dict[str, float]:
        with self.lock:
            return dict(self.values)


class InMemoryCounter:
    def __init__(self, name: str, help_text: str, labels: List[str]):
        self._metric = InMemoryMetric(name, help_text, "counter", labels)
    
    def labels(self, **kwargs):
        class LabeledCounter:
            def __init__(self, metric, label_values):
                self._metric = metric
                self._labels = label_values
            
            def inc(self, value=1):
                self._metric.inc(value, **self._labels)
        
        return LabeledCounter(self._metric, kwargs)
    
    def inc(self, value=1, **kwargs):
        self._metric.inc(value, **kwargs)


class InMemoryGauge:
    def __init__(self, name: str, help_text: str, labels: List[str]):
        self._metric = InMemoryMetric(name, help_text, "gauge", labels)
    
    def labels(self, **kwargs):
        class LabeledGauge:
            def __init__(self, metric, label_values):
                self._metric = metric
                self._labels = label_values
            
            def set(self, value):
                self._metric.set(value, **self._labels)
            
            def inc(self, value=1):
                self._metric.inc(value, **self._labels)
            
            def dec(self, value=1):
                self._metric.dec(value, **self._labels)
        
        return LabeledGauge(self._metric, kwargs)
    
    def set(self, value, **kwargs):
        self._metric.set(value, **kwargs)


class InMemoryHistogram:
    def __init__(self, name: str, help_text: str, labels: List[str], buckets=None):
        self._metric = InMemoryMetric(name, help_text, "histogram", labels)
        self._buckets = buckets or [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10]
    
    def labels(self, **kwargs):
        class LabeledHistogram:
            def __init__(self, metric, label_values):
                self._metric = metric
                self._labels = label_values
            
            def observe(self, value):
                self._metric.observe(value, **self._labels)
        
        return LabeledHistogram(self._metric, kwargs)
    
    def observe(self, value, **kwargs):
        self._metric.observe(value, **kwargs)
    
    def time(self):
        """Context manager to time operations"""
        class Timer:
            def __init__(self, histogram):
                self.histogram = histogram
                self.start = None
            
            def __enter__(self):
                self.start = time.time()
                return self
            
            def __exit__(self, *args):
                self.histogram.observe(time.time() - self.start)
        
        return Timer(self)


# =============================================================================
# Metrics Definitions
# =============================================================================

class MetricsCollector:
    """Central metrics collector for PDM system"""
    
    def __init__(self, prefix: str = "pdm"):
        self.prefix = prefix
        self._metrics: Dict[str, Any] = {}
        self._lock = Lock()
        
        # Initialize core metrics
        self._init_metrics()
    
    def _init_metrics(self):
        """Initialize all PDM metrics"""
        
        # Telemetry metrics
        self._metrics["telemetry_processed"] = self._create_counter(
            "telemetry_processed_total",
            "Total telemetry readings processed",
            ["asset_id", "regime"]
        )
        
        self._metrics["telemetry_latency"] = self._create_histogram(
            "telemetry_processing_seconds",
            "Telemetry processing latency",
            ["asset_id"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]
        )
        
        # Alert metrics
        self._metrics["alerts_generated"] = self._create_counter(
            "alerts_generated_total",
            "Total alerts generated",
            ["asset_id", "alert_type", "severity"]
        )
        
        self._metrics["alerts_active"] = self._create_gauge(
            "alerts_active",
            "Currently active alerts",
            ["asset_id", "alert_type"]
        )
        
        # Sensor trust metrics
        self._metrics["sensor_trust"] = self._create_gauge(
            "sensor_trust_score",
            "Current sensor trust score",
            ["asset_id", "sensor_id"]
        )
        
        self._metrics["sensors_untrusted"] = self._create_gauge(
            "sensors_untrusted_total",
            "Number of untrusted sensors",
            ["asset_id"]
        )
        
        # Regime metrics
        self._metrics["regime_current"] = self._create_gauge(
            "regime_current",
            "Current operating regime (encoded)",
            ["asset_id", "regime"]
        )
        
        self._metrics["regime_transitions"] = self._create_counter(
            "regime_transitions_total",
            "Total regime transitions",
            ["asset_id", "from_regime", "to_regime"]
        )
        
        # Change detection metrics
        self._metrics["change_detected"] = self._create_counter(
            "change_detected_total",
            "Total change detections",
            ["asset_id", "sensor_type"]
        )
        
        self._metrics["cusum_statistic"] = self._create_gauge(
            "cusum_statistic",
            "Current CUSUM statistic",
            ["asset_id", "sensor_type", "direction"]
        )
        
        # Fault hypothesis metrics
        self._metrics["fault_probability"] = self._create_gauge(
            "fault_probability",
            "Fault probability",
            ["asset_id", "fault_type"]
        )
        
        # False positive budget metrics
        self._metrics["fp_budget_remaining"] = self._create_gauge(
            "fp_budget_remaining",
            "Remaining false positive budget",
            ["site_id"]
        )
        
        self._metrics["fp_alarms_this_month"] = self._create_gauge(
            "fp_alarms_this_month",
            "Actionable alarms this month",
            ["site_id"]
        )
        
        # Model metrics
        self._metrics["model_inference_latency"] = self._create_histogram(
            "model_inference_seconds",
            "Model inference latency",
            ["model_type", "stage"],
            buckets=[0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5]
        )
        
        # Feedback metrics
        self._metrics["feedback_received"] = self._create_counter(
            "feedback_received_total",
            "Total feedback records",
            ["outcome"]
        )

        # Degraded-mode / partial computation metrics
        self._metrics["upload_rows_dropped"] = self._create_counter(
            "upload_rows_dropped_total",
            "Rows dropped during upload parsing/normalization",
            ["site_id", "reason"]
        )
        self._metrics["kpi_computations_skipped"] = self._create_counter(
            "kpi_computations_skipped_total",
            "KPI computations skipped due to partial failures",
            ["site_id", "kpi_name", "reason"]
        )
        self._metrics["kpi_enrichment_failures"] = self._create_counter(
            "kpi_enrichment_failures_total",
            "KPI enrichment failures that triggered degraded mode",
            ["site_id", "enrichment_type"]
        )
        
        # System health metrics
        self._metrics["system_uptime"] = self._create_gauge(
            "system_uptime_seconds",
            "System uptime in seconds",
            []
        )
        
        self._metrics["assets_monitored"] = self._create_gauge(
            "assets_monitored_total",
            "Total assets being monitored",
            ["site_id"]
        )
    
    def _create_counter(self, name: str, help_text: str, labels: List[str]):
        full_name = f"{self.prefix}_{name}"
        if PROMETHEUS_AVAILABLE:
            return Counter(full_name, help_text, labels)
        return InMemoryCounter(full_name, help_text, labels)
    
    def _create_gauge(self, name: str, help_text: str, labels: List[str]):
        full_name = f"{self.prefix}_{name}"
        if PROMETHEUS_AVAILABLE:
            return Gauge(full_name, help_text, labels)
        return InMemoryGauge(full_name, help_text, labels)
    
    def _create_histogram(self, name: str, help_text: str, labels: List[str], buckets=None):
        full_name = f"{self.prefix}_{name}"
        if PROMETHEUS_AVAILABLE:
            return Histogram(full_name, help_text, labels, buckets=buckets)
        return InMemoryHistogram(full_name, help_text, labels, buckets)
    
    def get(self, name: str):
        """Get a metric by name"""
        return self._metrics.get(name)
    
    def record_telemetry_processed(self, asset_id: str, regime: str, latency: float):
        """Record telemetry processing"""
        self._metrics["telemetry_processed"].labels(
            asset_id=asset_id, regime=regime
        ).inc()
        self._metrics["telemetry_latency"].labels(
            asset_id=asset_id
        ).observe(latency)
    
    def record_alert_generated(self, asset_id: str, alert_type: str, severity: str):
        """Record alert generation"""
        self._metrics["alerts_generated"].labels(
            asset_id=asset_id, alert_type=alert_type, severity=severity
        ).inc()
    
    def update_sensor_trust(self, asset_id: str, sensor_id: str, trust_score: float):
        """Update sensor trust score"""
        self._metrics["sensor_trust"].labels(
            asset_id=asset_id, sensor_id=sensor_id
        ).set(trust_score)
    
    def record_change_detected(self, asset_id: str, sensor_type: str):
        """Record change detection"""
        self._metrics["change_detected"].labels(
            asset_id=asset_id, sensor_type=sensor_type
        ).inc()
    
    def update_fault_probability(self, asset_id: str, fault_type: str, probability: float):
        """Update fault probability"""
        self._metrics["fault_probability"].labels(
            asset_id=asset_id, fault_type=fault_type
        ).set(probability)
    
    def record_feedback(self, outcome: str):
        """Record feedback"""
        self._metrics["feedback_received"].labels(outcome=outcome).inc()

    def record_upload_rows_dropped(self, site_id: str, reason: str, count: int = 1):
        """Record dropped rows for upload/ingestion quality tracking."""
        self._metrics["upload_rows_dropped"].labels(
            site_id=site_id,
            reason=reason,
        ).inc(count)

    def record_kpi_computation_skipped(self, site_id: str, kpi_name: str, reason: str, count: int = 1):
        """Record skipped KPI computations due to non-fatal errors."""
        self._metrics["kpi_computations_skipped"].labels(
            site_id=site_id,
            kpi_name=kpi_name,
            reason=reason,
        ).inc(count)

    def record_kpi_enrichment_failure(self, site_id: str, enrichment_type: str, count: int = 1):
        """Record enrichment failures that resulted in degraded output."""
        self._metrics["kpi_enrichment_failures"].labels(
            site_id=site_id,
            enrichment_type=enrichment_type,
        ).inc(count)
    
    def get_metrics_text(self) -> str:
        """Get metrics in Prometheus text format"""
        if PROMETHEUS_AVAILABLE:
            return generate_latest().decode("utf-8")
        
        # Fallback: generate simple text format
        lines = []
        for name, metric in self._metrics.items():
            if hasattr(metric, "_metric"):
                m = metric._metric
                lines.append(f"# HELP {m.name} {m.help_text}")
                lines.append(f"# TYPE {m.name} {m.metric_type}")
                for key, value in m.get_all().items():
                    label_str = ",".join(f'{l}="{v}"' for l, v in zip(m.labels, key) if v)
                    if label_str:
                        lines.append(f"{m.name}{{{label_str}}} {value}")
                    else:
                        lines.append(f"{m.name} {value}")
        return "\n".join(lines)
    
    def start_server(self, port: int = 9090):
        """Start Prometheus metrics server"""
        if PROMETHEUS_AVAILABLE:
            prom_start_server(port)
            logger.info(f"Prometheus metrics server started on port {port}")
        else:
            logger.warning("Prometheus not available, metrics server not started")


# Global metrics instance
metrics = MetricsCollector()

# Convenience metric accessors
TELEMETRY_PROCESSED = lambda: metrics.get("telemetry_processed")
ALERTS_GENERATED = lambda: metrics.get("alerts_generated")
INFERENCE_LATENCY = lambda: metrics.get("model_inference_latency")


def timed(metric_name: str = None, labels: Dict[str, str] = None):
    """Decorator to time function execution"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                return func(*args, **kwargs)
            finally:
                duration = time.time() - start
                if metric_name:
                    metric = metrics.get(metric_name)
                    if metric and labels:
                        metric.labels(**labels).observe(duration)
                    elif metric:
                        metric.observe(duration)
        return wrapper
    return decorator


def counted(metric_name: str, labels: Dict[str, str] = None):
    """Decorator to count function calls"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            metric = metrics.get(metric_name)
            if metric and labels:
                metric.labels(**labels).inc()
            elif metric:
                metric.inc()
            return func(*args, **kwargs)
        return wrapper
    return decorator
