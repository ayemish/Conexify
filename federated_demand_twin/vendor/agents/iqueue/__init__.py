"""
iQueue Agent Architecture

Autonomous MMM (Marketing Mix Modeling) Decision System

Agent Roles:
1. Data Steward/Quality Agents - Validate streams, detect drift, produce confidence scores
2. Endogenous-State Agents - Own beliefs for baskets, penetration, items, size
3. Driver Agents - Controllable (Media/Price/Trade) and Non-controllable (Time/Events/Competition)
4. Attribution & Pathway Agent - Decomposition into direct/indirect/carryover
5. Scenario Generation Agent - Auto-generate and prune reallocations
6. Optimization Agent - Next Best Investment under constraints
7. Governance/Policy Agent - Enforce rules, block low-confidence, explain

Operational Workflow: Sense → Update → Simulate → Optimize → Explain → Learn
"""

from .base import AgentConfig, BaseIQueueAgent, AgentMessage, BeliefState
from .data_steward import DataStewardAgent, DataQualityReport
from .endogenous_state import (
    EndogenousStateAgent, BasketAgent, PenetrationAgent, 
    ItemsPerBasketAgent, SizePerItemAgent
)
from .driver_agents import (
    DriverAgent, ControllableDriverAgent, NonControllableDriverAgent,
    MediaDriverAgent, PriceDriverAgent, TradeDriverAgent,
    TimeSeriesDriverAgent, EventsDriverAgent, CompetitionDriverAgent
)
from .attribution import AttributionAgent, PathwayDecomposition
from .scenario_generation import ScenarioGenerationAgent, ScenarioCandidate
from .optimization import OptimizationAgent, InvestmentPlan
from .governance import GovernanceAgent, DecisionPackage
from .workflow import IQueueWorkflow, WorkflowConfig

__all__ = [
    # Base
    'AgentConfig', 'BaseIQueueAgent', 'AgentMessage', 'BeliefState',
    # Data Steward
    'DataStewardAgent', 'DataQualityReport',
    # Endogenous State
    'EndogenousStateAgent', 'BasketAgent', 'PenetrationAgent',
    'ItemsPerBasketAgent', 'SizePerItemAgent',
    # Driver Agents
    'DriverAgent', 'ControllableDriverAgent', 'NonControllableDriverAgent',
    'MediaDriverAgent', 'PriceDriverAgent', 'TradeDriverAgent',
    'TimeSeriesDriverAgent', 'EventsDriverAgent', 'CompetitionDriverAgent',
    # Attribution
    'AttributionAgent', 'PathwayDecomposition',
    # Scenario
    'ScenarioGenerationAgent', 'ScenarioCandidate',
    # Optimization
    'OptimizationAgent', 'InvestmentPlan',
    # Governance
    'GovernanceAgent', 'DecisionPackage',
    # Workflow
    'IQueueWorkflow', 'WorkflowConfig'
]
