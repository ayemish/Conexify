"""
Scenario Catalog for Retail Media Spend Optimization

Business decision-support scenarios organized into 5 categories:
A. Core Outcome Scenarios (1-5)
B. Incrementality-Specific Scenarios (6-12)
C. Risk & Governance Scenarios (13-15)
D. Portfolio Management Scenarios (16-18)
E. Operational Scenarios (19-21)
"""

from .schemas import (
    ScenarioCategory,
    ObjectiveType,
    RiskAppetite,
    Cadence,
    BusinessScenario,
    ScenarioConstraints,
    ScenarioTrigger,
    RecommendedAction,
    DecisionRecommendation,
    EvidenceItem,
    ReasoningChain,
    DecisionSupportOutput,
)

from .catalog import SCENARIO_CATALOG, get_scenario, list_scenarios_by_category
from .messaging import CrewMessage, MessageBus, CrossCrewCoordinator
from .executor import ScenarioExecutor
from .integration import (
    CrewAdapter,
    CrewExecutionRequest,
    CrewExecutionResult,
    ScenarioCrewOrchestrator,
    create_integrated_executor,
)

__all__ = [
    # Schemas
    "ScenarioCategory",
    "ObjectiveType", 
    "RiskAppetite",
    "Cadence",
    "BusinessScenario",
    "ScenarioConstraints",
    "ScenarioTrigger",
    "RecommendedAction",
    "DecisionRecommendation",
    "EvidenceItem",
    "ReasoningChain",
    "DecisionSupportOutput",
    # Catalog
    "SCENARIO_CATALOG",
    "get_scenario",
    "list_scenarios_by_category",
    # Messaging
    "CrewMessage",
    "MessageBus",
    "CrossCrewCoordinator",
    # Executor
    "ScenarioExecutor",
    # Integration
    "CrewAdapter",
    "CrewExecutionRequest",
    "CrewExecutionResult",
    "ScenarioCrewOrchestrator",
    "create_integrated_executor",
]

