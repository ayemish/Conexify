"""
PDM Agents Module

Multi-agent system for collaborative predictive maintenance decisions.
Uses CrewAI framework for agent orchestration.

Agent Layers:
- Layer 0: Context (Regime Detection)
- Layer 1: Data Quality (Sensor Trust)
- Layer 2: Behavioral Analysis (Behavior Model, Change Detection)
- Layer 3: Diagnostics (Fault Hypothesis)
- Layer 4: Decision (Decision Policy)

This module is part of the SEPARATE Predictive Maintenance project.
"""

from .model_agents import (
    PDMModelAgent,
    PDMModelAgentRole,
    AgentAnalysisResult,
    AgentVote,
    AgentOpinion,
    CollaborativeDecision,
    RegimeDetectionAgent,
    SensorTrustAgent,
    BehaviorModelAgent,
    ChangeDetectionAgent,
    FaultHypothesisAgent,
    DecisionPolicyAgent,
)
from .orchestrator import (
    PDMModelOrchestrator,
    OrchestratorConfig,
    TelemetryInput,
    OrchestratorResult,
)
from .workflow import (
    CollaborativeDecisionWorkflow,
    WorkflowContext,
    WorkflowState,
    DecisionType,
    create_collaborative_workflow,
)
from .protocols import (
    ProtocolMessageBus,
    VotingProtocol,
    EscalationProtocol,
    ConsensusProtocol,
)
from .sensor_coverage_agent import SensorCoverageAgent
from .dag_orchestration_agent import DAGOrchestrationAgent
from .federated_learning_agent import FederatedLearningAgent
from .knowledge_graph_agent import KnowledgeGraphAgent
from .ontology_agent import OntologyAgent
from .parts_inventory_agent import PartsInventoryAgent
from .technician_scheduling_agent import TechnicianSchedulingAgent
from .scenario_agents import (
    BudgetScenarioAgent,
    RiskScenarioAgent,
    PaybackScenarioAgent,
    ScenarioContext,
    ScenarioAgentResult,
)
from .crews import CREW_REGISTRY

__all__ = [
    # Model Agents
    "PDMModelAgent",
    "PDMModelAgentRole",
    "AgentAnalysisResult",
    "AgentVote",
    "AgentOpinion",
    "CollaborativeDecision",
    "RegimeDetectionAgent",
    "SensorTrustAgent",
    "BehaviorModelAgent",
    "ChangeDetectionAgent",
    "FaultHypothesisAgent",
    "DecisionPolicyAgent",
    
    # Orchestrator
    "PDMModelOrchestrator",
    "OrchestratorConfig",
    "TelemetryInput",
    "OrchestratorResult",
    
    # Workflow
    "CollaborativeDecisionWorkflow",
    "WorkflowContext",
    "WorkflowState",
    "DecisionType",
    "create_collaborative_workflow",
    
    # Protocols
    "ProtocolMessageBus",
    "VotingProtocol",
    "EscalationProtocol",
    "ConsensusProtocol",
    
    # New CrewAI Agents (Phase 2-6)
    "SensorCoverageAgent",
    "DAGOrchestrationAgent",
    "FederatedLearningAgent",
    "KnowledgeGraphAgent",
    "OntologyAgent",
    "PartsInventoryAgent",
    "TechnicianSchedulingAgent",
    
    # Scenario Agents
    "BudgetScenarioAgent",
    "RiskScenarioAgent",
    "PaybackScenarioAgent",
    "ScenarioContext",
    "ScenarioAgentResult",
    
    # Crew compositions
    "CREW_REGISTRY",
]
