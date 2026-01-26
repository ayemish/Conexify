"""
Retail Media Spend Optimization Module

This module implements a complete Bayesian → Digital Twin → Agent architecture
for optimizing retail media network spend allocation.

Components:
- schemas.py: Data contracts for retail media domain
- bayesian_engine.py: Bayesian analysis layer (elasticity posteriors, attribution)
- media_twin.py: Digital Twin for retail media simulation
- agents.py: Agent layer (Attribution, Scenario, Optimization, Governance, Rationale)
- api.py: FastAPI endpoints for the retail media optimization pipeline
- orchestrator.py: Integration orchestrator wiring all components
"""

from .schemas import (
    RetailerConfig,
    ChannelConfig,
    SKUConfig,
    MediaAllocation,
    ElasticityPosterior,
    AttributionResult,
    RetailerSKUState,
    MediaScenario,
    MediaSimulationResult,
    MediaDecisionPack,
)

from .bayesian_engine import (
    RetailMediaBayesianEngine,
    ChannelElasticityModel,
    BayesianAttributionModel,
    FederatedElasticityAggregator,
)

from .media_twin import (
    RetailMediaTwin,
    MediaSimulationEngine,
)

from .agents import (
    AttributionAgent,
    ScenarioGenerationAgent,
    OptimizationAgent,
    GovernanceAgent,
    RationaleAgent,
)

from .orchestrator import RetailMediaOrchestrator

__all__ = [
    # Schemas
    "RetailerConfig",
    "ChannelConfig", 
    "SKUConfig",
    "MediaAllocation",
    "ElasticityPosterior",
    "AttributionResult",
    "RetailerSKUState",
    "MediaScenario",
    "MediaSimulationResult",
    "MediaDecisionPack",
    # Bayesian
    "RetailMediaBayesianEngine",
    "ChannelElasticityModel",
    "BayesianAttributionModel",
    "FederatedElasticityAggregator",
    # Twin
    "RetailMediaTwin",
    "MediaSimulationEngine",
    # Agents
    "AttributionAgent",
    "ScenarioGenerationAgent",
    "OptimizationAgent",
    "GovernanceAgent",
    "RationaleAgent",
    # Orchestrator
    "RetailMediaOrchestrator",
]
