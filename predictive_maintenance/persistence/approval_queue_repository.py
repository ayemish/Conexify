"""
DB-Backed Approval Queue Repository

Replaces the in-memory dict storage in ApprovalQueueService with
PostgreSQL persistence via SQLAlchemy.

The repository handles serialization/deserialization between the
dataclass-based QueueItem and the SQLAlchemy ApprovalQueueItemModel.
"""

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc

from .models import ApprovalQueueItemModel, RetrainingRequestModel

logger = logging.getLogger(__name__)


class ApprovalQueueRepository:
    """CRUD operations for persisted approval queue items."""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _coerce_dt(value):
        if value is None or isinstance(value, datetime):
            return value
        if isinstance(value, str):
            txt = value.strip()
            if txt.endswith("Z"):
                txt = txt[:-1] + "+00:00"
            try:
                parsed = datetime.fromisoformat(txt)
                return parsed.replace(tzinfo=None) if parsed.tzinfo else parsed
            except Exception:
                return None
        return None

    def upsert(self, item_id: str, data: Dict[str, Any]) -> ApprovalQueueItemModel:
        """Insert or update a queue item from a dict (dataclass.to_dict() output)."""
        existing = self.session.query(ApprovalQueueItemModel).filter(
            ApprovalQueueItemModel.item_id == item_id
        ).first()

        if existing:
            for key, value in data.items():
                if key in ("created_at", "updated_at", "expires_at", "assigned_at"):
                    value = self._coerce_dt(value)
                if hasattr(existing, key) and key not in ("id", "item_id"):
                    setattr(existing, key, value)
            existing.updated_at = datetime.utcnow()
            self.session.flush()
            return existing

        model = ApprovalQueueItemModel(
            item_id=item_id,
            approval_id=data.get("approval_id", ""),
            run_id=data.get("run_id", ""),
            incident_id=data.get("incident_id", ""),
            playbook_id=data.get("playbook_id", ""),
            step_id=data.get("step_id", ""),
            tenant_id=data.get("tenant_id", ""),
            site_id=data.get("site_id", ""),
            asset_id=data.get("asset_id", ""),
            item_type=data.get("item_type", "action_approval"),
            risk_tier=data.get("risk_tier", "MEDIUM"),
            priority=data.get("priority", 50),
            proposed_actions=data.get("proposed_actions", []),
            action_summary=data.get("action_summary", ""),
            telemetry_snapshot=data.get("telemetry_snapshot", {}),
            fault_context=data.get("fault_context", {}),
            evidence=data.get("evidence", {}),
            status=data.get("status", "pending"),
            explanation_data=data.get("explanation"),
            explanation_error=data.get("explanation_error"),
            validation_data=data.get("validation"),
            validation_error=data.get("validation_error"),
            decision_data=data.get("decision"),
            created_at=self._coerce_dt(data.get("created_at")) or datetime.utcnow(),
            updated_at=self._coerce_dt(data.get("updated_at")) or datetime.utcnow(),
            expires_at=self._coerce_dt(data.get("expires_at")),
            assigned_to=data.get("assigned_to"),
            assigned_at=self._coerce_dt(data.get("assigned_at")),
            escalation_level=data.get("escalation_level", 0),
        )
        self.session.add(model)
        self.session.flush()
        return model

    def get_by_id(self, item_id: str) -> Optional[ApprovalQueueItemModel]:
        return self.session.query(ApprovalQueueItemModel).filter(
            ApprovalQueueItemModel.item_id == item_id
        ).first()

    def update_status(self, item_id: str, status: str) -> bool:
        item = self.get_by_id(item_id)
        if item:
            item.status = status
            item.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def update_assignment(
        self, item_id: str, assigned_to: Optional[str], status: str,
    ) -> bool:
        item = self.get_by_id(item_id)
        if item:
            item.assigned_to = assigned_to
            item.assigned_at = datetime.utcnow() if assigned_to else None
            item.status = status
            item.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def update_decision(self, item_id: str, decision_data: Dict, status: str) -> bool:
        item = self.get_by_id(item_id)
        if item:
            item.decision_data = decision_data
            item.status = status
            item.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def update_explanation(self, item_id: str, explanation_data: Dict) -> bool:
        item = self.get_by_id(item_id)
        if item:
            item.explanation_data = explanation_data
            item.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def update_validation(self, item_id: str, validation_data: Dict) -> bool:
        item = self.get_by_id(item_id)
        if item:
            item.validation_data = validation_data
            item.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False

    def list_items(
        self,
        tenant_id: Optional[str] = None,
        status: Optional[str] = None,
        risk_tier: Optional[str] = None,
        assigned_to: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[ApprovalQueueItemModel]:
        query = self.session.query(ApprovalQueueItemModel)

        if tenant_id:
            query = query.filter(ApprovalQueueItemModel.tenant_id == tenant_id)
        if status:
            query = query.filter(ApprovalQueueItemModel.status == status)
        if risk_tier:
            query = query.filter(ApprovalQueueItemModel.risk_tier == risk_tier)
        if assigned_to:
            query = query.filter(ApprovalQueueItemModel.assigned_to == assigned_to)

        return (
            query.order_by(
                desc(ApprovalQueueItemModel.priority),
                ApprovalQueueItemModel.created_at,
            )
            .offset(offset)
            .limit(limit)
            .all()
        )

    def count_by_status(self, tenant_id: Optional[str] = None) -> Dict[str, int]:
        query = self.session.query(
            ApprovalQueueItemModel.status,
        )
        if tenant_id:
            query = query.filter(ApprovalQueueItemModel.tenant_id == tenant_id)

        rows = query.all()
        counts: Dict[str, int] = {}
        for (status,) in rows:
            counts[status] = counts.get(status, 0) + 1
        return counts

    def get_expired(self, now: Optional[datetime] = None) -> List[ApprovalQueueItemModel]:
        now = now or datetime.utcnow()
        return self.session.query(ApprovalQueueItemModel).filter(
            ApprovalQueueItemModel.expires_at < now,
            ApprovalQueueItemModel.status.in_(["pending", "ready", "in_review"]),
        ).all()


class RetrainingRequestRepository:
    """CRUD operations for persisted retraining requests."""

    def __init__(self, session: Session):
        self.session = session

    def create(self, data: Dict[str, Any]) -> RetrainingRequestModel:
        model = RetrainingRequestModel(
            request_id=data.get("request_id", ""),
            trigger_type=data.get("trigger_type", ""),
            model_id=data.get("model_id", ""),
            asset_id=data.get("asset_id", ""),
            fault_type=data.get("fault_type"),
            false_positive_rate=data.get("false_positive_rate", 0.0),
            false_negative_rate=data.get("false_negative_rate", 0.0),
            mean_absolute_error=data.get("mean_absolute_error", 0.0),
            n_incorrect_recent=data.get("n_incorrect_recent", 0),
            n_observations_since_train=data.get("n_observations_since_train", 0),
            evidence=data.get("evidence", {}),
        )
        self.session.add(model)
        self.session.flush()
        return model

    def get_pending(self, limit: int = 50) -> List[RetrainingRequestModel]:
        return self.session.query(RetrainingRequestModel).filter(
            RetrainingRequestModel.status == "pending"
        ).order_by(RetrainingRequestModel.created_at).limit(limit).all()

    def mark_completed(self, request_id: str) -> bool:
        item = self.session.query(RetrainingRequestModel).filter(
            RetrainingRequestModel.request_id == request_id
        ).first()
        if item:
            item.status = "completed"
            item.completed_at = datetime.utcnow()
            self.session.flush()
            return True
        return False
