"""
PDM Observability Module

Structured logging, metrics, and tracing for the PDM system.
"""

from .logging import (
    setup_logging,
    get_logger,
    StructuredLogger,
)
from .metrics import (
    MetricsCollector,
    metrics,
    TELEMETRY_PROCESSED,
    ALERTS_GENERATED,
    INFERENCE_LATENCY,
)
from .tracing import (
    setup_tracing,
    trace_span,
    get_tracer,
)

__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    "StructuredLogger",
    # Metrics
    "MetricsCollector",
    "metrics",
    "TELEMETRY_PROCESSED",
    "ALERTS_GENERATED",
    "INFERENCE_LATENCY",
    # Tracing
    "setup_tracing",
    "trace_span",
    "get_tracer",
]
