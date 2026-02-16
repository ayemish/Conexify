"""
KPI Service Registry

Maps KPI names to their computation service classes and provides
factory functions for instantiation.
"""

import logging
from typing import Dict, Type

from .base import BaseKPIService, KPIConfig
from .energy_kpi import EnergyReductionKPI
from .refrigerant_kpi import RefrigerantLeakReductionKPI
from .workorder_kpi import WorkOrderReductionKPI
from .remaining_kpis import (
    FoodWasteReductionKPI,
    AssetFailurePredictionKPI,
    PPMMaximizationKPI,
    FoodSafetyComplianceKPI,
    ESGComplianceKPI,
    AssetUptimeIncreaseKPI,
    CallCenterReductionKPI,
    ServiceBureauReductionKPI,
    PreventiveMaintenanceOptKPI,
    FoodTempDiagnosticsKPI,
    CapExLifecycleKPI,
)

logger = logging.getLogger(__name__)


KPI_REGISTRY: Dict[str, Type[BaseKPIService]] = {
    "energy_reduction": EnergyReductionKPI,
    "refrigerant_leak_reduction": RefrigerantLeakReductionKPI,
    "work_order_reduction": WorkOrderReductionKPI,
    "food_waste_reduction": FoodWasteReductionKPI,
    "asset_failure_prediction": AssetFailurePredictionKPI,
    "ppm_maximization": PPMMaximizationKPI,
    "food_safety_compliance": FoodSafetyComplianceKPI,
    "esg_compliance": ESGComplianceKPI,
    "asset_uptime_increase": AssetUptimeIncreaseKPI,
    "call_center_volume_reduction": CallCenterReductionKPI,
    "service_bureau_reduction": ServiceBureauReductionKPI,
    "preventive_maintenance_optimization": PreventiveMaintenanceOptKPI,
    "food_temp_diagnostics_improvement": FoodTempDiagnosticsKPI,
    "capex_lifecycle_optimization": CapExLifecycleKPI,
}


def get_kpi_service(kpi_name: str, config: KPIConfig) -> BaseKPIService:
    """Instantiate a KPI service by name."""
    cls = KPI_REGISTRY.get(kpi_name)
    if cls is None:
        raise KeyError(f"Unknown KPI: {kpi_name}. Available: {list(KPI_REGISTRY.keys())}")
    return cls(config)
