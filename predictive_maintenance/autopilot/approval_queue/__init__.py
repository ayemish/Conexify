"""
Approval Queue Module

Human-in-the-loop approval system with LLM-powered explanations and validation.

Components:
- QueueItem: Enhanced approval item with LLM explanation
- LLMExplainer: Generates natural language explanations for workflow items
- LLMValidator: Validates workflow items before approval
- ApprovalQueueService: Manages the approval queue
- API routes and React UI for human reviewers
"""

from .models import (
    QueueItem,
    QueueItemStatus,
    LLMExplanation,
    LLMValidation,
    ApprovalDecision,
    RiskAssessment,
)
from .explainer import LLMExplainerService
from .validator import LLMValidatorService
from .service import ApprovalQueueService

__all__ = [
    "QueueItem",
    "QueueItemStatus",
    "LLMExplanation",
    "LLMValidation",
    "ApprovalDecision",
    "RiskAssessment",
    "LLMExplainerService",
    "LLMValidatorService",
    "ApprovalQueueService",
]
