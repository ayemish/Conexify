"""Scenario Advisor conversational interface.

Provides:
- RagStore: dual-mode embedding RAG store
- OpenAIClient: LLM client with availability detection
- UnifiedScenarioAdvisor: conversational advisor with tool calling + offline fallback
- create_advisor: factory function
"""

from .rag_store import RagStore, RagDocument, RagSearchResult
from .openai_client import OpenAIClient
from .scenario_advisor import (
    UnifiedScenarioAdvisor,
    AdvisorSession,
    AdvisorResponse,
    ChatMessage,
    MessageRole,
    Ecosystem,
    create_advisor,
    get_shared_advisor,
)

__all__ = [
    "RagStore",
    "RagDocument",
    "RagSearchResult",
    "OpenAIClient",
    "UnifiedScenarioAdvisor",
    "AdvisorSession",
    "AdvisorResponse",
    "ChatMessage",
    "MessageRole",
    "Ecosystem",
    "create_advisor",
    "get_shared_advisor",
]
