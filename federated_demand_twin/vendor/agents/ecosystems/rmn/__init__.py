"""
RMN (Retail Media Network) Optimization Ecosystem

Self-contained agentic solution for retail media spend optimization:
- Multi-touch attribution with Bayesian uncertainty
- Channel elasticity estimation
- Budget allocation optimization
- Scenario simulation via Digital Twin
- Governance and compliance validation
- Human-readable rationale generation

Agents:
- DataIngestionAgent: Validates media spend and performance data
- AttributionAgent: Bayesian multi-touch attribution
- ElasticityAgent: Channel-level elasticity estimation
- ScenarioAgent: Generates allocation scenarios
- TwinAgent: Monte Carlo simulation of outcomes
- OptimizerAgent: Constrained budget optimization
- GovernanceAgent: Policy validation
- RationaleAgent: LLM-powered explanations
"""

from .agents import (
    RMNDataIngestionAgent,
    RMNAttributionAgent,
    RMNElasticityAgent,
    RMNScenarioAgent,
    RMNTwinAgent,
    RMNOptimizerAgent,
    RMNGovernanceAgent,
    RMNRationaleAgent,
)

from .orchestrator import RMNOrchestrator, create_rmn_orchestrator
from .schemas import (
    RMNConfig,
    ChannelConfig,
    ChannelType,
    MediaSpendData,
    AttributionResult,
    ElasticityPosterior,
    AllocationScenario,
    SimulationResult,
    OptimizationResult,
    GovernanceDecision,
    RMNDecisionPack,
)

__all__ = [
    # Agents
    "RMNDataIngestionAgent",
    "RMNAttributionAgent",
    "RMNElasticityAgent",
    "RMNScenarioAgent",
    "RMNTwinAgent",
    "RMNOptimizerAgent",
    "RMNGovernanceAgent",
    "RMNRationaleAgent",
    
    # Orchestrator
    "RMNOrchestrator",
    "create_rmn_orchestrator",
    
    # Schemas
    "RMNConfig",
    "ChannelConfig",
    "ChannelType",
    "MediaSpendData",
    "AttributionResult",
    "ElasticityPosterior",
    "AllocationScenario",
    "SimulationResult",
    "OptimizationResult",
    "GovernanceDecision",
    "RMNDecisionPack",
]
