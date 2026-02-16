"""Oil & Gas agent package (legacy + PDM modules)."""

from .legacy import (  # noqa: F401
    TelemetryIngestionAgent,
    AnomalyDetectionAgent,
    PredictiveMaintenanceAgent,
    ProductionOptimizationAgent,
    SafetyMonitoringAgent,
    ComplianceAgent,
    AlertAgent,
    ReportingAgent,
)

__all__ = [
    "TelemetryIngestionAgent",
    "AnomalyDetectionAgent",
    "PredictiveMaintenanceAgent",
    "ProductionOptimizationAgent",
    "SafetyMonitoringAgent",
    "ComplianceAgent",
    "AlertAgent",
    "ReportingAgent",
]
