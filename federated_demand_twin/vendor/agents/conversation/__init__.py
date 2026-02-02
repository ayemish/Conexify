"""
Conversation Module - Conversational Agent Interface

Provides OpenAI-powered chat interface for querying CrewAI agents
about RMN and Demand/Procurement scenarios.
"""

from .scenario_advisor import UnifiedScenarioAdvisor, AdvisorSession, AdvisorResponse
from .openai_client import OpenAIClient, ChatMessage

__all__ = [
    "UnifiedScenarioAdvisor",
    "AdvisorSession", 
    "AdvisorResponse",
    "OpenAIClient",
    "ChatMessage",
]
