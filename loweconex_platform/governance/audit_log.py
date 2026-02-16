"""
Audit Log — records all significant platform operations for governance.

Tracks: data imports, schema mappings, scenario runs, report generation,
and recommendation acceptance per FRD Section 2.2.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class AuditAction:
    """Canonical audit action types."""
    DATA_IMPORT = "data_import"
    SCHEMA_MAPPING = "schema_mapping"
    SCENARIO_RUN = "scenario_run"
    KPI_COMPUTED = "kpi_computed"
    REPORT_GENERATED = "report_generated"
    REPORT_EXPORTED = "report_exported"
    RECOMMENDATION_ACCEPTED = "recommendation_accepted"
    RECOMMENDATION_REJECTED = "recommendation_rejected"
    USER_LOGIN = "user_login"
    ROLE_CHANGED = "role_changed"
    TWIN_UPDATED = "twin_updated"
    THRESHOLD_CHANGED = "threshold_changed"
    HUMAN_REVIEW_COMPLETED = "human_review_completed"


@dataclass
class AuditEntry:
    """A single audit log entry."""
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    action: str = ""
    user_id: Optional[str] = None
    company_id: str = ""
    location_id: Optional[str] = None
    asset_id: Optional[str] = None
    details: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None
    ip_address: Optional[str] = None
    status: str = "success"  # "success" | "failure" | "pending"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "timestamp": self.timestamp,
            "action": self.action,
            "user_id": self.user_id,
            "company_id": self.company_id,
            "location_id": self.location_id,
            "asset_id": self.asset_id,
            "details": self.details,
            "correlation_id": self.correlation_id,
            "ip_address": self.ip_address,
            "status": self.status,
        }


class AuditLog:
    """
    In-memory audit log with query capabilities.
    
    Production implementation would write to PostgreSQL with
    append-only semantics and encryption at rest.
    """

    def __init__(self):
        self._entries: List[AuditEntry] = []
        self._max_entries = 100_000

    def log(
        self,
        action: str,
        company_id: str,
        user_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        location_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        status: str = "success",
    ) -> AuditEntry:
        """Record an audit entry."""
        entry = AuditEntry(
            action=action,
            user_id=user_id,
            company_id=company_id,
            location_id=location_id,
            asset_id=asset_id,
            details=details or {},
            correlation_id=correlation_id,
            status=status,
        )
        self._entries.append(entry)

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries // 2:]

        logger.debug(f"Audit: {action} by {user_id or 'system'} for {company_id}")
        return entry

    def query(
        self,
        company_id: Optional[str] = None,
        action: Optional[str] = None,
        user_id: Optional[str] = None,
        since: Optional[str] = None,
        until: Optional[str] = None,
        limit: int = 100,
    ) -> List[AuditEntry]:
        """Query audit entries with filters."""
        entries = self._entries
        if company_id:
            entries = [e for e in entries if e.company_id == company_id]
        if action:
            entries = [e for e in entries if e.action == action]
        if user_id:
            entries = [e for e in entries if e.user_id == user_id]
        if since:
            entries = [e for e in entries if e.timestamp >= since]
        if until:
            entries = [e for e in entries if e.timestamp <= until]
        return entries[-limit:]

    def get_by_correlation(self, correlation_id: str) -> List[AuditEntry]:
        """Get all entries for a correlation ID (e.g., a pipeline run)."""
        return [e for e in self._entries if e.correlation_id == correlation_id]

    def export_json(self, company_id: str, limit: int = 10000) -> str:
        """Export audit entries for a company as JSON."""
        entries = self.query(company_id=company_id, limit=limit)
        return json.dumps([e.to_dict() for e in entries], indent=2)

    def stats(self, company_id: Optional[str] = None) -> Dict[str, Any]:
        """Get audit log statistics."""
        entries = self._entries
        if company_id:
            entries = [e for e in entries if e.company_id == company_id]

        by_action: Dict[str, int] = {}
        for e in entries:
            by_action[e.action] = by_action.get(e.action, 0) + 1

        return {
            "total_entries": len(entries),
            "by_action": by_action,
            "unique_users": len(set(e.user_id for e in entries if e.user_id)),
        }
