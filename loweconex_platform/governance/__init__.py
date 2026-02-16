"""
Governance — RBAC, audit logging, compliance checks, prompt governance,
and event-aware enterprise module integration.

Provides tenant isolation, role-based permissions, audit trail,
and event bus wiring for enterprise governance modules.
"""

from loweconex_platform.governance.rbac import RBACManager, Permission, Role, User
from loweconex_platform.governance.audit_log import AuditLog, AuditEntry
from loweconex_platform.governance.compliance import ComplianceChecker
from loweconex_platform.governance.event_integration import (
    EventAwareDataQualityEngine,
    EventAwareDriftMonitor,
    EventAwareExecutionEngine,
    EventAwareExceptionManager,
    SLAEventHook,
    BenchmarkPostKPIHook,
    create_event_aware_modules,
)

__all__ = [
    "RBACManager",
    "Permission",
    "Role",
    "User",
    "AuditLog",
    "AuditEntry",
    "ComplianceChecker",
    "EventAwareDataQualityEngine",
    "EventAwareDriftMonitor",
    "EventAwareExecutionEngine",
    "EventAwareExceptionManager",
    "SLAEventHook",
    "BenchmarkPostKPIHook",
    "create_event_aware_modules",
]
