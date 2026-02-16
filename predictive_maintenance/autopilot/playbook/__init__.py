"""
Playbook DSL Module

Implements the Playbook Definition Language for Operations Autopilot:
- JSON/YAML schema validation
- Expression language parser
- Playbook registry with versioning
- Trigger and precondition evaluation
"""

from .schema import (
    PlaybookDefinition,
    PlaybookStep,
    PlaybookTrigger,
    PlaybookPrecondition,
    PlaybookVerification,
    PlaybookEscalation,
    PlaybookEvidence,
    PLAYBOOK_JSON_SCHEMA,
)
from .parser import PlaybookParser, PlaybookValidationError
from .expressions import ExpressionEvaluator, ExpressionError
from .registry import PlaybookRegistry

__all__ = [
    "PlaybookDefinition",
    "PlaybookStep",
    "PlaybookTrigger",
    "PlaybookPrecondition",
    "PlaybookVerification",
    "PlaybookEscalation",
    "PlaybookEvidence",
    "PLAYBOOK_JSON_SCHEMA",
    "PlaybookParser",
    "PlaybookValidationError",
    "ExpressionEvaluator",
    "ExpressionError",
    "PlaybookRegistry",
]
