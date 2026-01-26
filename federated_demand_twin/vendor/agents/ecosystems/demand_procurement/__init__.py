"""
Demand Forecast & Procurement Ecosystem

Self-contained agentic solution for demand forecasting and inventory optimization:
- Probabilistic demand forecasting
- Inventory optimization (ROP, EOQ, safety stock)
- Supplier management and procurement planning
- Lead time and stockout risk analysis
- Decision pack generation with rationale

This is the original core use case for the Federated Demand Twin.

Agents:
- DemandForecastAgent: Probabilistic demand forecasting
- InventoryOptimizationAgent: Computes optimal inventory policies
- SupplierManagementAgent: Manages supplier relationships and constraints
- RiskAnalysisAgent: Analyzes stockout and overstock risks
- ScenarioSimulationAgent: Runs what-if scenarios
- ProcurementPlanningAgent: Generates procurement plans
- GovernanceAgent: Validates recommendations
- ReportingAgent: Generates decision packs
"""

from .agents import (
    DemandForecastAgent,
    InventoryOptimizationAgent,
    SupplierManagementAgent,
    RiskAnalysisAgent,
    ScenarioSimulationAgent,
    ProcurementPlanningAgent,
    DPGovernanceAgent,
    DPReportingAgent,
)

from .orchestrator import DemandProcurementOrchestrator, create_demand_procurement_orchestrator
from .schemas import (
    DemandProcurementConfig,
    SKUConfig,
    SupplierConfig,
    DemandForecast,
    InventoryPolicy,
    ProcurementPlan,
    RiskAssessment,
    DPScenarioResult,
    DPDecisionPack,
)

__all__ = [
    # Agents
    "DemandForecastAgent",
    "InventoryOptimizationAgent",
    "SupplierManagementAgent",
    "RiskAnalysisAgent",
    "ScenarioSimulationAgent",
    "ProcurementPlanningAgent",
    "DPGovernanceAgent",
    "DPReportingAgent",
    
    # Orchestrator
    "DemandProcurementOrchestrator",
    "create_demand_procurement_orchestrator",
    
    # Schemas
    "DemandProcurementConfig",
    "SKUConfig",
    "SupplierConfig",
    "DemandForecast",
    "InventoryPolicy",
    "ProcurementPlan",
    "RiskAssessment",
    "DPScenarioResult",
    "DPDecisionPack",
]
