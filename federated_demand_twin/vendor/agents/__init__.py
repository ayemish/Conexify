"""
Federated Demand Twin - Agent Layer

CrewAI-compliant agent architecture for:
- Data quality and validation
- Bayesian analytics (attribution, elasticity, forecasting)
- Digital Twin simulation
- Optimization and allocation
- Governance and approval workflows
- Communication and rationale generation

Usage:
    from vendor.agents import (
        CrewAIOrchestrator,
        create_orchestrator,
        AgentRole,
        AgentCategory,
    )
    
    # Create orchestrator for a retailer
    orchestrator = create_orchestrator("walmart")
    
    # Run decision workflow
    decision_pack = orchestrator.run(
        data_inputs={"spend": spend_data, "demand": demand_data},
        current_allocation={"media": 1000000, "price": 500000},
        total_budget=2000000,
    )
"""

# Base infrastructure
from .crewai_base import (
    # Configuration
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    
    # State management
    BeliefState,
    
    # Messaging
    AgentMessageBus,
    AgentMessage,
    MessageType,
    
    # Base class
    DemandTwinAgent,
    
    # Registry
    AgentRegistry,
    
    # Utilities
    create_task,
    create_crew,
    get_agent_summary,
    CREWAI_AVAILABLE,
)

# Agent implementations
from .crewai_agents import (
    # Data Agents
    DataStewardAgent,
    DataValidatorAgent,
    
    # Analytics Agents
    AttributionAgent,
    ElasticityAgent,
    ForecastAgent,
    AnomalyDetectorAgent,
    
    # Simulation Agents
    ScenarioGeneratorAgent,
    DigitalTwinAgent,
    
    # Optimization Agents
    BudgetOptimizerAgent,
    InventoryOptimizerAgent,
    
    # Governance Agents
    GovernanceAgent,
    
    # Communication Agents
    RationaleAgent,
    ReportWriterAgent,
    
    # Factory
    create_agent,
)

# Orchestration
from .crewai_orchestrator import (
    CrewAIOrchestrator,
    OrchestratorConfig,
    DecisionPack,
    WorkflowStage,
    WorkflowStatus,
    StageResult,
    create_orchestrator,
    create_retail_media_orchestrator,
)

# Legacy compatibility - iQueue agents
from .iqueue import (
    IQueueWorkflow,
    WorkflowConfig,
)

__all__ = [
    # Base
    "CrewAIAgentConfig",
    "AgentCategory",
    "AgentRole",
    "BeliefState",
    "AgentMessageBus",
    "AgentMessage",
    "MessageType",
    "DemandTwinAgent",
    "AgentRegistry",
    "create_task",
    "create_crew",
    "get_agent_summary",
    "CREWAI_AVAILABLE",
    
    # Agents
    "DataStewardAgent",
    "DataValidatorAgent",
    "AttributionAgent",
    "ElasticityAgent",
    "ForecastAgent",
    "AnomalyDetectorAgent",
    "ScenarioGeneratorAgent",
    "DigitalTwinAgent",
    "BudgetOptimizerAgent",
    "InventoryOptimizerAgent",
    "GovernanceAgent",
    "RationaleAgent",
    "ReportWriterAgent",
    "create_agent",
    
    # Orchestration
    "CrewAIOrchestrator",
    "OrchestratorConfig",
    "DecisionPack",
    "WorkflowStage",
    "WorkflowStatus",
    "StageResult",
    "create_orchestrator",
    "create_retail_media_orchestrator",
    
    # Legacy
    "IQueueWorkflow",
    "WorkflowConfig",
]
