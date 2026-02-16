"""
PDM Multi-Agent System - CrewAI-Based Predictive Maintenance

This package implements a multi-agent system for predictive maintenance decisions
using the CrewAI framework. Each PDM model is managed by a specialized agent,
and agents collaborate to determine maintenance outcomes.

Architecture Overview:
=======================

                    ┌─────────────────────────────────────┐
                    │    CollaborativeDecisionWorkflow    │
                    │    (Main Entry Point)               │
                    └──────────────┬──────────────────────┘
                                   │
                    ┌──────────────┴──────────────────────┐
                    │       PDMModelOrchestrator          │
                    │  (Coordinates all model agents)     │
                    └──────────────┬──────────────────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────┐
    │                              │                              │
    ▼                              ▼                              ▼
┌──────────┐                ┌──────────┐                  ┌──────────┐
│ Layer 0  │                │ Layer 1  │                  │ Layer 2  │
│ Context  │────────────────│  Trust   │──────────────────│ Behavior │
└──────────┘                └──────────┘                  └──────────┘
│ Regime   │                │ Sensor   │                  │ Behavior │
│ Detection│                │ Trust    │                  │ Change   │
└──────────┘                └──────────┘                  │ Detection│
                                                          └──────────┘
    │                              │                              │
    └──────────────────────────────┼──────────────────────────────┘
                                   │
    ┌──────────────────────────────┼──────────────────────────────┐
    │                              │                              │
    ▼                              ▼                              ▼
┌──────────┐                ┌──────────┐                  ┌──────────┐
│ Layer 3  │                │ Layer 4  │                  │ Existing │
│ Diagnosis│────────────────│ Decision │──────────────────│  Agents  │
└──────────┘                └──────────┘                  └──────────┘
│ Fault    │                │ Decision │                  │ Triage   │
│ Hypothesis│               │ Policy   │                  │ Evidence │
└──────────┘                │ Voting   │                  │ WorkOrder│
                            └──────────┘                  └──────────┘

Agent Types:
============

Layer 0 - Context Agents:
  - RegimeDetectionAgent: Classifies operating regime (OFF, STARTUP, STEADY_COOL, etc.)

Layer 1 - Data Quality Agents:
  - SensorTrustAgent: Evaluates sensor data trustworthiness

Layer 2 - Behavioral Analysis Agents:
  - BehaviorModelAgent: Predicts expected values, computes residuals
  - ChangeDetectionAgent: Detects persistent changes via CUSUM/GLR

Layer 3 - Diagnostic Agents:
  - FaultHypothesisAgent: Bayesian fault diagnosis with belief states

Layer 4 - Decision Agents:
  - DecisionPolicyAgent: Enforces FA budget, aggregates votes

Collaboration Patterns:
=======================

1. **Layered Execution**: Agents execute in dependency order
   - Each layer completes before the next begins
   - Results propagate from upstream to downstream agents

2. **Collaborative Voting**: All agents vote on key decisions
   - Weighted voting based on agent expertise
   - Sensor trust agent has veto power on data quality
   - Change detection agent validates persistence

3. **Consensus Building**: Multi-round consensus for critical decisions
   - Configurable consensus threshold (default 60%)
   - Dissent tracking for audit

4. **Escalation Protocol**: Agents escalate concerns to decision agents
   - Severity-based routing
   - Evidence attachment

Usage Example:
==============

```python
from oil_gas.agents.pdm_multiagent import (
    create_pdm_system,
    TelemetryInput,
)

# Create the multi-agent system for a site
pdm = create_pdm_system("site_001")

# Process telemetry
telemetry = TelemetryInput(
    timestamp=datetime.utcnow(),
    asset_id="RTU_001",
    site_id="site_001",
    compressor_on=True,
    compressor_current=15.2,
    suction_pressure=68.0,
    discharge_pressure=275.0,
    supply_air_temp=55.0,
    return_air_temp=75.0,
    ambient_temp=95.0,
)

# Run collaborative decision workflow
result = pdm.process(telemetry)

# Check the decision
print(f"Decision: {result.final_decision}")
print(f"Confidence: {result.confidence:.0%}")
print(f"Votes: {len(result.votes)}")

# Record feedback for model improvement
pdm.record_feedback(
    workflow_id=result.workflow_id,
    actual_outcome="compressor_failure",
    was_correct=True,
)
```

Integration with Existing Systems:
==================================

The multi-agent system integrates with:
- Advanced PDM Services (pdm_advanced_system.py)
- Existing PDM Agents (pdm_agents.py)
- Model Registry and Lifecycle (learning_loop_models.py)
- Event Bus for real-time communication (redis_event_bus.py)
"""

from datetime import datetime
from typing import Dict, List, Optional, Any

# Model Agents
from ..pdm_model_agents import (
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

# Orchestrator
from ..pdm_model_orchestrator import (
    PDMModelOrchestrator,
    OrchestratorConfig,
    TelemetryInput,
    OrchestratorResult,
    IntegratedPDMOrchestrator,
    PDMDecisionCrew,
    create_pdm_orchestrator,
    create_pdm_decision_crew,
)

# Communication Protocols
from ..pdm_agent_protocols import (
    ProtocolMessageBus,
    ProtocolMessage,
    ProtocolMessageType,
    MessagePriority,
    VotingProtocol,
    EscalationProtocol,
    ConsensusProtocol,
    ProtocolEnabledAgent,
    create_protocol_bus,
)

# Collaborative Workflow
from ..pdm_collaborative_workflow import (
    CollaborativeDecisionWorkflow,
    WorkflowContext,
    WorkflowState,
    DecisionType,
    DecisionRule,
    DecisionRuleEngine,
    create_collaborative_workflow,
)


# =============================================================================
# Convenience Factory Functions
# =============================================================================

def create_pdm_system(
    site_id: str,
    config: Optional[OrchestratorConfig] = None,
) -> CollaborativeDecisionWorkflow:
    """
    Create a complete PDM multi-agent system for a site.
    
    This is the main entry point for the multi-agent PDM system.
    
    Args:
        site_id: Unique identifier for the site
        config: Optional orchestrator configuration
        
    Returns:
        CollaborativeDecisionWorkflow instance ready to process telemetry
    """
    return create_collaborative_workflow(site_id, config)


def create_basic_orchestrator(
    site_id: str,
    config: Optional[OrchestratorConfig] = None,
) -> PDMModelOrchestrator:
    """
    Create a basic PDM orchestrator without full workflow.
    
    Use this for lower-level access to agent orchestration.
    """
    return create_pdm_orchestrator(site_id, config, integrated=False)


def create_integrated_orchestrator(
    site_id: str,
    config: Optional[OrchestratorConfig] = None,
) -> IntegratedPDMOrchestrator:
    """
    Create an orchestrator integrated with existing PDM workflow agents.
    """
    return IntegratedPDMOrchestrator(site_id, config)


# =============================================================================
# Exports
# =============================================================================

__all__ = [
    # Main Entry Point
    "create_pdm_system",
    
    # Factory Functions
    "create_basic_orchestrator",
    "create_integrated_orchestrator",
    "create_collaborative_workflow",
    "create_pdm_orchestrator",
    "create_pdm_decision_crew",
    "create_protocol_bus",
    
    # Core Types
    "TelemetryInput",
    "OrchestratorConfig",
    "OrchestratorResult",
    "WorkflowContext",
    "WorkflowState",
    "DecisionType",
    
    # Agent Types
    "PDMModelAgent",
    "PDMModelAgentRole",
    "AgentAnalysisResult",
    "AgentVote",
    "AgentOpinion",
    "CollaborativeDecision",
    
    # Specific Agents
    "RegimeDetectionAgent",
    "SensorTrustAgent",
    "BehaviorModelAgent",
    "ChangeDetectionAgent",
    "FaultHypothesisAgent",
    "DecisionPolicyAgent",
    
    # Orchestrators
    "PDMModelOrchestrator",
    "IntegratedPDMOrchestrator",
    "PDMDecisionCrew",
    
    # Workflows
    "CollaborativeDecisionWorkflow",
    "DecisionRule",
    "DecisionRuleEngine",
    
    # Protocols
    "ProtocolMessageBus",
    "ProtocolMessage",
    "ProtocolMessageType",
    "MessagePriority",
    "VotingProtocol",
    "EscalationProtocol",
    "ConsensusProtocol",
    "ProtocolEnabledAgent",
]
