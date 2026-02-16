"""
KPI Computation Services

Real data-backed KPI computations for the 14 ROI dimensions.
Each KPI service queries persistence layers and applies domain-specific
calculations to produce savings estimates with confidence intervals.
"""

from .base import KPIResult, KPIConfig, BaseKPIService
from .orchestrator import KPIOrchestrator
from .registry import KPI_REGISTRY, get_kpi_service

__all__ = [
    "KPIResult",
    "KPIConfig",
    "BaseKPIService",
    "KPIOrchestrator",
    "KPI_REGISTRY",
    "get_kpi_service",
]
