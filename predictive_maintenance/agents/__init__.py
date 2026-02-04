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
]
