"""
Approval Queue Service

Manages the workflow approval queue with LLM-powered explanations and validation.
"""

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional

from .models import (
    QueueItem,
    QueueItemStatus,
    LLMExplanation,
    LLMValidation,
    ApprovalDecision,
    RiskAssessment,
    RiskLevel,
    ValidationStatus,
)
from .explainer import LLMExplainerService
from .validator import LLMValidatorService

logger = logging.getLogger(__name__)


class ApprovalQueueService:
    """
    Manages the approval queue for human-in-the-loop workflows.
    
    Features:
    - Queue management with priority ordering
    - LLM explanation generation
    - LLM validation
    - Assignment and escalation
    - Decision tracking
    """
    
    def __init__(
        self,
        explainer: LLMExplainerService = None,
        validator: LLMValidatorService = None,
        default_expiry_hours: int = 4,
        auto_escalate_minutes: int = 30,
        session_factory: Optional[Callable] = None,
        preload_limit: int = 500,
    ):
        self.explainer = explainer or LLMExplainerService()
        self.validator = validator or LLMValidatorService()
        self.default_expiry_hours = default_expiry_hours
        self.auto_escalate_minutes = auto_escalate_minutes
        self.session_factory = session_factory
        
        # In-memory queue (would be database in production)
        self._queue: Dict[str, QueueItem] = {}
        self._by_tenant: Dict[str, List[str]] = defaultdict(list)
        self._by_status: Dict[QueueItemStatus, List[str]] = defaultdict(list)
        
        # Callbacks
        self._on_approval: Optional[Callable] = None
        self._on_rejection: Optional[Callable] = None
        self._on_escalation: Optional[Callable] = None

        # Best-effort cache warmup from persisted queue state.
        self._bootstrap_cache(limit=preload_limit)

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _bootstrap_cache(self, limit: int = 500):
        """Hydrate in-memory cache from persisted queue items, if configured."""
        if self.session_factory is None:
            return
        try:
            from ...persistence.approval_queue_repository import ApprovalQueueRepository
            session = self.session_factory()
            try:
                repo = ApprovalQueueRepository(session)
                rows = repo.list_items(limit=limit, offset=0)
                for row in rows:
                    item = self._row_to_item(row)
                    if item is None:
                        continue
                    self._queue[item.item_id] = item
                    self._by_tenant[item.tenant_id].append(item.item_id)
                    self._by_status[item.status].append(item.item_id)
            finally:
                session.close()
        except Exception as exc:  # pragma: no cover
            logger.warning("Approval queue cache bootstrap skipped: %s", exc)

    def _persist_item(self, item: QueueItem):
        """Best-effort persistence for queue item state transitions."""
        if self.session_factory is None:
            return
        try:
            from ...persistence.approval_queue_repository import ApprovalQueueRepository
            session = self.session_factory()
            try:
                repo = ApprovalQueueRepository(session)
                repo.upsert(item.item_id, self._item_to_row_data(item))
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()
        except Exception as exc:  # pragma: no cover
            logger.warning("Approval queue persistence skipped for %s: %s", item.item_id, exc)

    def _load_item_from_persistence(self, item_id: str) -> Optional[QueueItem]:
        """Load one queue item from persistence into cache."""
        if self.session_factory is None:
            return None
        try:
            from ...persistence.approval_queue_repository import ApprovalQueueRepository
            session = self.session_factory()
            try:
                repo = ApprovalQueueRepository(session)
                row = repo.get_by_id(item_id)
                item = self._row_to_item(row) if row else None
                if item:
                    self._queue[item.item_id] = item
                    if item.item_id not in self._by_tenant[item.tenant_id]:
                        self._by_tenant[item.tenant_id].append(item.item_id)
                    self._update_status_index(item.item_id, item.status)
                return item
            finally:
                session.close()
        except Exception as exc:  # pragma: no cover
            logger.warning("Approval queue load skipped for %s: %s", item_id, exc)
            return None

    @staticmethod
    def _parse_dt(value: Any) -> Optional[datetime]:
        if value is None:
            return None
        if isinstance(value, datetime):
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

    def _item_to_row_data(self, item: QueueItem) -> Dict[str, Any]:
        return {
            "approval_id": item.approval_id,
            "run_id": item.run_id,
            "incident_id": item.incident_id,
            "playbook_id": item.playbook_id,
            "step_id": item.step_id,
            "tenant_id": item.tenant_id,
            "site_id": item.site_id,
            "asset_id": item.asset_id,
            "item_type": item.item_type,
            "risk_tier": item.risk_tier,
            "priority": item.priority,
            "proposed_actions": item.proposed_actions,
            "action_summary": item.action_summary,
            "telemetry_snapshot": item.telemetry_snapshot,
            "fault_context": item.fault_context,
            "evidence": item.evidence,
            "status": item.status.value if hasattr(item.status, "value") else str(item.status),
            "explanation": item.explanation.to_dict() if item.explanation else None,
            "explanation_error": item.explanation_error,
            "validation": item.validation.to_dict() if item.validation else None,
            "validation_error": item.validation_error,
            "decision": item.decision.to_dict() if item.decision else None,
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "expires_at": item.expires_at,
            "assigned_to": item.assigned_to,
            "assigned_at": item.assigned_at,
            "escalation_level": item.escalation_level,
        }

    def _row_to_item(self, row: Any) -> Optional[QueueItem]:
        if row is None:
            return None
        try:
            status_val = row.status if isinstance(row.status, str) else "pending"
            try:
                status = QueueItemStatus(status_val)
            except Exception:
                status = QueueItemStatus.PENDING

            item = QueueItem(
                item_id=row.item_id,
                approval_id=row.approval_id or "",
                run_id=row.run_id or "",
                incident_id=row.incident_id or "",
                playbook_id=row.playbook_id or "",
                step_id=row.step_id or "",
                tenant_id=row.tenant_id or "",
                site_id=row.site_id or "",
                asset_id=row.asset_id or "",
                item_type=row.item_type or "action_approval",
                risk_tier=row.risk_tier or "MEDIUM",
                priority=int(row.priority or 50),
                proposed_actions=list(row.proposed_actions or []),
                action_summary=row.action_summary or "",
                telemetry_snapshot=dict(row.telemetry_snapshot or {}),
                fault_context=dict(row.fault_context or {}),
                evidence=dict(row.evidence or {}),
                status=status,
                explanation_error=row.explanation_error,
                validation_error=row.validation_error,
                created_at=row.created_at or datetime.utcnow(),
                updated_at=row.updated_at or datetime.utcnow(),
                expires_at=row.expires_at,
                assigned_to=row.assigned_to,
                assigned_at=row.assigned_at,
                escalation_level=int(row.escalation_level or 0),
            )

            if row.explanation_data:
                item.explanation = self._parse_explanation(row.explanation_data)
            if row.validation_data:
                item.validation = self._parse_validation(row.validation_data)
            if row.decision_data:
                item.decision = self._parse_decision(row.decision_data)
            return item
        except Exception as exc:  # pragma: no cover
            logger.warning("Failed to deserialize queue item row %s: %s", getattr(row, "item_id", "?"), exc)
            return None

    def _parse_explanation(self, data: Dict[str, Any]) -> Optional[LLMExplanation]:
        if not isinstance(data, dict):
            return None
        risk_raw = data.get("risk_assessment") or {}
        risk_level_raw = str(risk_raw.get("overall_risk", "medium")).lower()
        try:
            risk_level = RiskLevel(risk_level_raw)
        except Exception:
            risk_level = RiskLevel.MEDIUM
        risk = RiskAssessment(
            overall_risk=risk_level,
            equipment_criticality=float(risk_raw.get("equipment_criticality", 0.5) or 0.5),
            business_impact=float(risk_raw.get("business_impact", 0.5) or 0.5),
            safety_risk=float(risk_raw.get("safety_risk", 0.0) or 0.0),
            reversibility=float(risk_raw.get("reversibility", 0.8) or 0.8),
            risk_factors=list(risk_raw.get("risk_factors") or []),
            mitigations=list(risk_raw.get("mitigations") or []),
        )
        return LLMExplanation(
            explanation_id=str(data.get("explanation_id", "")),
            title=str(data.get("title", "")),
            summary=str(data.get("summary", "")),
            what_happened=str(data.get("what_happened", "")),
            what_will_happen=str(data.get("what_will_happen", "")),
            why_recommended=str(data.get("why_recommended", "")),
            expected_outcome=str(data.get("expected_outcome", "")),
            risk_assessment=risk,
            key_evidence=list(data.get("key_evidence") or []),
            similar_cases=list(data.get("similar_cases") or []),
            alternatives=list(data.get("alternatives") or []),
            confidence=float(data.get("confidence", 0.0) or 0.0),
            uncertainty_factors=list(data.get("uncertainty_factors") or []),
            model_used=str(data.get("model_used", "")),
            generated_at=self._parse_dt(data.get("generated_at")) or datetime.utcnow(),
            generation_time_ms=int(data.get("generation_time_ms", 0) or 0),
        )

    def _parse_validation(self, data: Dict[str, Any]) -> Optional[LLMValidation]:
        if not isinstance(data, dict):
            return None
        status_raw = str(data.get("status", "needs_review"))
        try:
            status = ValidationStatus(status_raw)
        except Exception:
            status = ValidationStatus.NEEDS_REVIEW
        return LLMValidation(
            validation_id=str(data.get("validation_id", "")),
            status=status,
            checks=list(data.get("checks") or []),
            errors=list(data.get("errors") or []),
            warnings=list(data.get("warnings") or []),
            info=list(data.get("info") or []),
            recommendations=list(data.get("recommendations") or []),
            preconditions_met=bool(data.get("preconditions_met", True)),
            failed_preconditions=list(data.get("failed_preconditions") or []),
            safety_checks_passed=bool(data.get("safety_checks_passed", True)),
            safety_concerns=list(data.get("safety_concerns") or []),
            validation_confidence=float(data.get("validation_confidence", 0.0) or 0.0),
            model_used=str(data.get("model_used", "")),
            validated_at=self._parse_dt(data.get("validated_at")) or datetime.utcnow(),
            validation_time_ms=int(data.get("validation_time_ms", 0) or 0),
        )

    def _parse_decision(self, data: Dict[str, Any]) -> Optional[ApprovalDecision]:
        if not isinstance(data, dict):
            return None
        return ApprovalDecision(
            decision_id=str(data.get("decision_id", "")),
            approved=bool(data.get("approved", False)),
            decision=str(data.get("decision", "")),
            reviewer_id=str(data.get("reviewer_id", "")),
            reviewer_name=str(data.get("reviewer_name", "")),
            reviewer_role=str(data.get("reviewer_role", "")),
            reviewed_at=self._parse_dt(data.get("reviewed_at")) or datetime.utcnow(),
            review_duration_seconds=int(data.get("review_duration_seconds", 0) or 0),
            notes=str(data.get("notes", "")),
            rejection_reason=str(data.get("rejection_reason", "")),
            modified_params=dict(data.get("modified_params") or {}),
            llm_explanation_helpful=data.get("llm_explanation_helpful"),
            llm_validation_accurate=data.get("llm_validation_accurate"),
        )
    
    async def add_item(
        self,
        approval_id: str,
        run_id: str,
        incident_id: str,
        playbook_id: str,
        step_id: str,
        tenant_id: str,
        site_id: str,
        asset_id: str,
        item_type: str,
        risk_tier: str,
        proposed_actions: List[Dict[str, Any]],
        action_summary: str,
        telemetry_snapshot: Dict[str, Any] = None,
        fault_context: Dict[str, Any] = None,
        evidence: Dict[str, Any] = None,
        priority: int = 50,
        expires_in_hours: int = None,
    ) -> QueueItem:
        """
        Add a new item to the approval queue.
        
        Automatically generates LLM explanation and validation.
        """
        # Calculate priority based on risk tier
        if risk_tier == "EXTREME":
            priority = max(priority, 90)
        elif risk_tier == "HIGH":
            priority = max(priority, 70)
        
        # Create queue item
        item = QueueItem(
            approval_id=approval_id,
            run_id=run_id,
            incident_id=incident_id,
            playbook_id=playbook_id,
            step_id=step_id,
            tenant_id=tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            item_type=item_type,
            risk_tier=risk_tier,
            priority=priority,
            proposed_actions=proposed_actions,
            action_summary=action_summary,
            telemetry_snapshot=telemetry_snapshot or {},
            fault_context=fault_context or {},
            evidence=evidence or {},
            status=QueueItemStatus.PENDING,
            expires_at=datetime.utcnow() + timedelta(
                hours=expires_in_hours or self.default_expiry_hours
            ),
        )
        
        # Store in queue
        self._queue[item.item_id] = item
        self._by_tenant[tenant_id].append(item.item_id)
        self._by_status[QueueItemStatus.PENDING].append(item.item_id)
        self._persist_item(item)
        
        logger.info(f"Added queue item {item.item_id} for approval {approval_id}")
        
        # Start async explanation and validation
        asyncio.create_task(self._process_item(item))
        
        return item
    
    async def _process_item(self, item: QueueItem):
        """Process item: generate explanation and validation"""
        try:
            # Update status
            item.status = QueueItemStatus.EXPLAINING
            item.updated_at = datetime.utcnow()
            self._persist_item(item)
            
            # Generate explanation
            try:
                item.explanation = await self.explainer.generate_explanation(item)
            except Exception as e:
                logger.error(f"Explanation generation failed: {e}")
                item.explanation_error = str(e)
            
            # Update status
            item.status = QueueItemStatus.VALIDATING
            item.updated_at = datetime.utcnow()
            self._persist_item(item)
            
            # Run validation
            try:
                item.validation = await self.validator.validate(item)
            except Exception as e:
                logger.error(f"Validation failed: {e}")
                item.validation_error = str(e)
            
            # Mark as ready
            item.status = QueueItemStatus.READY
            item.updated_at = datetime.utcnow()
            
            # Update status index
            self._update_status_index(item.item_id, QueueItemStatus.READY)
            self._persist_item(item)
            
            logger.info(f"Queue item {item.item_id} ready for review")
            
        except Exception as e:
            logger.error(f"Item processing failed: {e}")
            item.status = QueueItemStatus.READY  # Still allow review
            item.updated_at = datetime.utcnow()
            self._persist_item(item)
    
    def _update_status_index(self, item_id: str, new_status: QueueItemStatus):
        """Update status index"""
        # Remove from old status lists
        for status in QueueItemStatus:
            if item_id in self._by_status[status]:
                self._by_status[status].remove(item_id)
        
        # Add to new status list
        if item_id not in self._by_status[new_status]:
            self._by_status[new_status].append(item_id)
    
    def get_item(self, item_id: str) -> Optional[QueueItem]:
        """Get a queue item by ID"""
        item = self._queue.get(item_id)
        if item is not None:
            return item
        return self._load_item_from_persistence(item_id)
    
    def get_queue(
        self,
        tenant_id: str = None,
        status: QueueItemStatus = None,
        risk_tier: str = None,
        assigned_to: str = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[QueueItem]:
        """Get queue items with filtering"""
        if self.session_factory is not None:
            try:
                from ...persistence.approval_queue_repository import ApprovalQueueRepository
                session = self.session_factory()
                try:
                    repo = ApprovalQueueRepository(session)
                    rows = repo.list_items(
                        tenant_id=tenant_id,
                        status=status.value if hasattr(status, "value") else status,
                        risk_tier=risk_tier,
                        assigned_to=assigned_to,
                        limit=limit,
                        offset=offset,
                    )
                finally:
                    session.close()
                items: List[QueueItem] = []
                for row in rows:
                    item = self._row_to_item(row)
                    if item is None:
                        continue
                    self._queue[item.item_id] = item
                    if item.item_id not in self._by_tenant[item.tenant_id]:
                        self._by_tenant[item.tenant_id].append(item.item_id)
                    self._update_status_index(item.item_id, item.status)
                    items.append(item)
                return items
            except Exception as exc:  # pragma: no cover
                logger.warning("Queue persistence list failed, falling back to memory: %s", exc)

        items = list(self._queue.values())
        
        # Apply filters
        if tenant_id:
            items = [i for i in items if i.tenant_id == tenant_id]
        if status:
            items = [i for i in items if i.status == status]
        if risk_tier:
            items = [i for i in items if i.risk_tier == risk_tier]
        if assigned_to:
            items = [i for i in items if i.assigned_to == assigned_to]
        
        # Sort by priority (descending) then created_at (ascending)
        items.sort(key=lambda x: (-x.priority, x.created_at))
        
        return items[offset:offset + limit]
    
    def get_pending_count(self, tenant_id: str = None) -> Dict[str, int]:
        """Get count of pending items by status"""
        if self.session_factory is not None:
            try:
                from ...persistence.approval_queue_repository import ApprovalQueueRepository
                session = self.session_factory()
                try:
                    repo = ApprovalQueueRepository(session)
                    counts = repo.count_by_status(tenant_id=tenant_id)
                finally:
                    session.close()
                return {
                    QueueItemStatus.PENDING.value: int(counts.get(QueueItemStatus.PENDING.value, 0)),
                    QueueItemStatus.READY.value: int(counts.get(QueueItemStatus.READY.value, 0)),
                    QueueItemStatus.IN_REVIEW.value: int(counts.get(QueueItemStatus.IN_REVIEW.value, 0)),
                }
            except Exception as exc:  # pragma: no cover
                logger.warning("Queue persistence count failed, falling back to memory: %s", exc)

        counts = {}
        for status in [QueueItemStatus.PENDING, QueueItemStatus.READY, QueueItemStatus.IN_REVIEW]:
            items = self._by_status.get(status, [])
            if tenant_id:
                items = [i for i in items if (self._queue.get(i) and self._queue[i].tenant_id == tenant_id)]
            counts[status.value] = len(items)
        return counts
    
    async def assign_item(
        self,
        item_id: str,
        reviewer_id: str,
    ) -> QueueItem:
        """Assign an item to a reviewer"""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        if item.status not in (QueueItemStatus.READY, QueueItemStatus.IN_REVIEW):
            raise ValueError(f"Item not ready for assignment: {item.status}")
        
        item.assigned_to = reviewer_id
        item.assigned_at = datetime.utcnow()
        item.status = QueueItemStatus.IN_REVIEW
        item.updated_at = datetime.utcnow()
        
        self._update_status_index(item_id, QueueItemStatus.IN_REVIEW)
        self._persist_item(item)
        
        logger.info(f"Assigned item {item_id} to {reviewer_id}")
        return item
    
    async def unassign_item(self, item_id: str) -> QueueItem:
        """Unassign an item (return to queue)"""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        item.assigned_to = None
        item.assigned_at = None
        item.status = QueueItemStatus.READY
        item.updated_at = datetime.utcnow()
        
        self._update_status_index(item_id, QueueItemStatus.READY)
        self._persist_item(item)
        
        return item
    
    async def approve(
        self,
        item_id: str,
        reviewer_id: str,
        reviewer_name: str = "",
        reviewer_role: str = "",
        notes: str = "",
        modified_params: Dict[str, Any] = None,
        llm_explanation_helpful: bool = None,
        llm_validation_accurate: bool = None,
    ) -> QueueItem:
        """Approve a queue item"""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        # Calculate review duration
        review_duration = 0
        if item.assigned_at:
            review_duration = int((datetime.utcnow() - item.assigned_at).total_seconds())
        
        # Create decision
        item.decision = ApprovalDecision(
            approved=True,
            decision="approved" if not modified_params else "modified",
            reviewer_id=reviewer_id,
            reviewer_name=reviewer_name,
            reviewer_role=reviewer_role,
            review_duration_seconds=review_duration,
            notes=notes,
            modified_params=modified_params or {},
            llm_explanation_helpful=llm_explanation_helpful,
            llm_validation_accurate=llm_validation_accurate,
        )
        
        item.status = QueueItemStatus.APPROVED
        item.updated_at = datetime.utcnow()
        
        self._update_status_index(item_id, QueueItemStatus.APPROVED)
        self._persist_item(item)
        
        # Trigger callback
        if self._on_approval:
            await self._on_approval(item)
        
        logger.info(f"Item {item_id} approved by {reviewer_id}")
        return item
    
    async def reject(
        self,
        item_id: str,
        reviewer_id: str,
        reviewer_name: str = "",
        reviewer_role: str = "",
        reason: str = "",
        notes: str = "",
        llm_explanation_helpful: bool = None,
        llm_validation_accurate: bool = None,
    ) -> QueueItem:
        """Reject a queue item"""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        # Calculate review duration
        review_duration = 0
        if item.assigned_at:
            review_duration = int((datetime.utcnow() - item.assigned_at).total_seconds())
        
        # Create decision
        item.decision = ApprovalDecision(
            approved=False,
            decision="rejected",
            reviewer_id=reviewer_id,
            reviewer_name=reviewer_name,
            reviewer_role=reviewer_role,
            review_duration_seconds=review_duration,
            notes=notes,
            rejection_reason=reason,
            llm_explanation_helpful=llm_explanation_helpful,
            llm_validation_accurate=llm_validation_accurate,
        )
        
        item.status = QueueItemStatus.REJECTED
        item.updated_at = datetime.utcnow()
        
        self._update_status_index(item_id, QueueItemStatus.REJECTED)
        self._persist_item(item)
        
        # Trigger callback
        if self._on_rejection:
            await self._on_rejection(item)
        
        logger.info(f"Item {item_id} rejected by {reviewer_id}")
        return item
    
    async def escalate(
        self,
        item_id: str,
        reason: str = "",
    ) -> QueueItem:
        """Escalate an item to higher authority"""
        item = self.get_item(item_id)
        if not item:
            raise ValueError(f"Item not found: {item_id}")
        
        item.escalation_level += 1
        item.status = QueueItemStatus.ESCALATED
        item.priority = min(100, item.priority + 20)  # Increase priority
        item.updated_at = datetime.utcnow()
        
        # Reset assignment
        item.assigned_to = None
        item.assigned_at = None
        
        self._update_status_index(item_id, QueueItemStatus.ESCALATED)
        self._persist_item(item)
        
        # Trigger callback
        if self._on_escalation:
            await self._on_escalation(item, reason)
        
        logger.info(f"Item {item_id} escalated (level {item.escalation_level})")
        return item
    
    async def check_expirations(self):
        """Check for expired items and auto-escalate stale items"""
        now = datetime.utcnow()
        escalate_threshold = now - timedelta(minutes=self.auto_escalate_minutes)
        
        for item in self._queue.values():
            # Check expiration
            if item.expires_at and item.expires_at < now:
                if item.status in (QueueItemStatus.PENDING, QueueItemStatus.READY, QueueItemStatus.IN_REVIEW):
                    item.status = QueueItemStatus.EXPIRED
                    item.updated_at = now
                    self._update_status_index(item.item_id, QueueItemStatus.EXPIRED)
                    self._persist_item(item)
                    logger.warning(f"Item {item.item_id} expired")
            
            # Check for stale items needing escalation
            elif item.status == QueueItemStatus.READY and item.created_at < escalate_threshold:
                if item.escalation_level < 3:  # Max 3 escalations
                    await self.escalate(item.item_id, "Auto-escalated due to timeout")
    
    def get_stats(self, tenant_id: str = None) -> Dict[str, Any]:
        """Get queue statistics"""
        if self.session_factory is not None:
            items = self.get_queue(tenant_id=tenant_id, limit=5000, offset=0)
        else:
            items = list(self._queue.values())
            if tenant_id:
                items = [i for i in items if i.tenant_id == tenant_id]
        
        # Status distribution
        status_counts = defaultdict(int)
        for item in items:
            status_counts[item.status.value] += 1
        
        # Risk tier distribution
        risk_counts = defaultdict(int)
        for item in items:
            risk_counts[item.risk_tier] += 1
        
        # Average review time for completed items
        completed = [i for i in items if i.decision and i.decision.review_duration_seconds > 0]
        avg_review_time = (
            sum(i.decision.review_duration_seconds for i in completed) / len(completed)
            if completed else 0
        )
        
        # LLM feedback stats
        helpful_count = sum(
            1 for i in completed 
            if i.decision.llm_explanation_helpful is True
        )
        accurate_count = sum(
            1 for i in completed 
            if i.decision.llm_validation_accurate is True
        )
        
        return {
            "total_items": len(items),
            "status_distribution": dict(status_counts),
            "risk_distribution": dict(risk_counts),
            "pending_count": status_counts.get("pending", 0) + status_counts.get("ready", 0),
            "avg_review_time_seconds": avg_review_time,
            "completed_reviews": len(completed),
            "llm_explanation_helpful_rate": helpful_count / len(completed) if completed else 0,
            "llm_validation_accurate_rate": accurate_count / len(completed) if completed else 0,
        }
    
    def set_callbacks(
        self,
        on_approval: Callable = None,
        on_rejection: Callable = None,
        on_escalation: Callable = None,
    ):
        """Set callback functions for queue events"""
        self._on_approval = on_approval
        self._on_rejection = on_rejection
        self._on_escalation = on_escalation
