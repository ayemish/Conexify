"""
CrewAI Agent Infrastructure — re-exports from shared canonical implementation.

ALL CrewAI classes, agents, and utilities are defined in shared/agents/crewai_base.py.
This file re-exports everything for backward compatibility.
"""

# Re-export everything from the single canonical implementation
from shared.agents.crewai_base import *  # noqa: F401,F403
from shared.agents.crewai_base import (
    CREWAI_AVAILABLE,
    Agent,
    Task,
    Crew,
    Process,
    BaseTool,
    AgentCategory,
    AgentRole,
    CrewAIAgentConfig,
    BeliefState,
    MessageType,
    AgentMessage,
    AgentMessageBus,
    BaseCrewAgent,
    AgentRegistry,
    create_task,
    create_crew,
    get_agent_summary,
)

# Backward-compatible alias used by predictive_maintenance code
DemandTwinAgent = BaseCrewAgent
