"""
Agent Ecosystems

Three distinct, self-contained agent ecosystems built on shared CrewAI infrastructure:

1. **RMN (Retail Media Network) Optimization**
   - Multi-touch attribution with Bayesian uncertainty
   - Media mix modeling and elasticity estimation
   - Budget allocation optimization across channels
   - Scenario simulation via Digital Twin
   - Governance and rationale generation

2. **Oil & Gas Telemetry Monitoring**
   - Device telemetry ingestion and validation
   - Anomaly detection and predictive maintenance
   - Production optimization
   - Safety and compliance monitoring
   - Operational reporting

3. **Demand Forecast & Procurement**
   - Probabilistic demand forecasting
   - Inventory optimization (ROP, EOQ, safety stock)
   - Supplier management and procurement planning
   - Lead time and stockout risk analysis
   - Decision pack generation with rationale

Each ecosystem has:
- Domain-specific agents extending CrewAI base
- Orchestrator coordinating the workflow
- Data schemas defining contracts
- Decision pack output
"""

from .rmn import RMNOrchestrator, create_rmn_orchestrator
from .oil_gas import OilGasOrchestrator, create_oil_gas_orchestrator
from .demand_procurement import DemandProcurementOrchestrator, create_demand_procurement_orchestrator

__all__ = [
    # RMN
    "RMNOrchestrator",
    "create_rmn_orchestrator",
    
    # Oil & Gas
    "OilGasOrchestrator",
    "create_oil_gas_orchestrator",
    
    # Demand & Procurement
    "DemandProcurementOrchestrator",
    "create_demand_procurement_orchestrator",
]
