"""
Operating Model — Ownership, SLAs, Review Cadence, Exception Management.

Defines the human system that sustains the platform:
- RACI matrices per KPI (data owner, ops owner, finance owner, compliance)
- SLA definitions with threshold enforcement
- Review cadence (weekly triage, monthly savings, quarterly model)
- Exception management (data gaps, mis-mappings, false positives)
"""

from loweconex_platform.operating_model.operating_model import (
    RACIMatrix,
    RACIEntry,
    RACIRole,
    SLADefinition,
    SLATracker,
    ReviewCadence,
    ReviewScheduler,
    ExceptionManager,
    ExceptionRecord,
)

__all__ = [
    "RACIMatrix",
    "RACIEntry",
    "RACIRole",
    "SLADefinition",
    "SLATracker",
    "ReviewCadence",
    "ReviewScheduler",
    "ExceptionManager",
    "ExceptionRecord",
]
