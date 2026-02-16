"""
Autopilot Orchestration Module

Implements durable workflow execution with:
- Checkpointing for pause/resume
- Human-in-the-loop approval interrupts
- Replay from any checkpoint for debugging/audit
- Agent permission enforcement
"""

from .runtime import (
    OrchestrationRuntime,
    RunContext,
    StepExecutor,
)
from .checkpoint import (
    CheckpointManager,
    CheckpointState,
)
from .approval import (
    ApprovalManager,
    ApprovalRequest,
)

__all__ = [
    "OrchestrationRuntime",
    "RunContext",
    "StepExecutor",
    "CheckpointManager",
    "CheckpointState",
    "ApprovalManager",
    "ApprovalRequest",
]
