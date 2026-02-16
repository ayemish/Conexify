"""
Estate Brain Knowledge Module

Enhanced knowledge layer for Operations Autopilot:
- RAG-enhanced document retrieval with citations
- Knowledge graph with Brick/Haystack ontology grounding
- Tenant-isolated vector stores
- Planner integration for context-aware playbook parameterization
"""

from .brain import (
    EstateBrain,
    KnowledgeQuery,
    KnowledgeResult,
)
from .graph import (
    KnowledgeGraph,
    Entity,
    Relationship,
)
from .planner import (
    PlannerContext,
    PlaybookPlanner,
)

__all__ = [
    "EstateBrain",
    "KnowledgeQuery",
    "KnowledgeResult",
    "KnowledgeGraph",
    "Entity",
    "Relationship",
    "PlannerContext",
    "PlaybookPlanner",
]
