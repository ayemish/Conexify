"""
Approval Queue API Routes

REST API endpoints for the human-in-the-loop approval queue.
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
import logging
from fastapi import APIRouter, HTTPException, Query, Body
from pydantic import BaseModel, Field

from .models import QueueItem, QueueItemStatus
from .service import ApprovalQueueService

# Initialize service
logger = logging.getLogger(__name__)


def _build_queue_service() -> ApprovalQueueService:
    session_factory = None
    try:
        from ...config import settings
        if settings.persistence.enabled:
            from ...persistence.database import get_session_factory
            session_factory = get_session_factory()
    except Exception as exc:  # pragma: no cover
        logger.warning("Approval queue persistence unavailable, using in-memory mode: %s", exc)
        session_factory = None
    return ApprovalQueueService(session_factory=session_factory)


queue_service = _build_queue_service()

# Create routers
queue_router = APIRouter(prefix="/queue", tags=["Approval Queue"])
review_router = APIRouter(prefix="/review", tags=["Review Actions"])


# Request/Response Models
class QueueItemResponse(BaseModel):
    item_id: str
    approval_id: str
    run_id: str
    asset_id: str
    site_id: str
    item_type: str
    risk_tier: str
    priority: int
    action_summary: str
    status: str
    created_at: str
    expires_at: Optional[str]
    assigned_to: Optional[str]
    has_explanation: bool
    has_validation: bool
    validation_status: Optional[str]


class QueueItemDetailResponse(BaseModel):
    item_id: str
    approval_id: str
    run_id: str
    incident_id: str
    playbook_id: str
    step_id: str
    tenant_id: str
    site_id: str
    asset_id: str
    item_type: str
    risk_tier: str
    priority: int
    proposed_actions: List[Dict[str, Any]]
    action_summary: str
    telemetry_snapshot: Dict[str, Any]
    fault_context: Dict[str, Any]
    evidence: Dict[str, Any]
    status: str
    explanation: Optional[Dict[str, Any]]
    explanation_error: Optional[str]
    validation: Optional[Dict[str, Any]]
    validation_error: Optional[str]
    decision: Optional[Dict[str, Any]]
    created_at: str
    updated_at: str
    expires_at: Optional[str]
    assigned_to: Optional[str]
    escalation_level: int


class ApproveRequest(BaseModel):
    reviewer_id: str = Field(..., description="ID of the reviewer")
    reviewer_name: str = ""
    reviewer_role: str = ""
    notes: str = ""
    modified_params: Optional[Dict[str, Any]] = None
    llm_explanation_helpful: Optional[bool] = None
    llm_validation_accurate: Optional[bool] = None


class RejectRequest(BaseModel):
    reviewer_id: str = Field(..., description="ID of the reviewer")
    reviewer_name: str = ""
    reviewer_role: str = ""
    reason: str = Field(..., description="Reason for rejection")
    notes: str = ""
    llm_explanation_helpful: Optional[bool] = None
    llm_validation_accurate: Optional[bool] = None


class QueueStatsResponse(BaseModel):
    total_items: int
    pending_count: int
    status_distribution: Dict[str, int]
    risk_distribution: Dict[str, int]
    avg_review_time_seconds: float
    completed_reviews: int
    llm_explanation_helpful_rate: float
    llm_validation_accurate_rate: float


class CreateQueueItemRequest(BaseModel):
    approval_id: str = Field(..., min_length=1)
    run_id: str = Field(..., min_length=1)
    incident_id: str = Field(..., min_length=1)
    playbook_id: str = Field(..., min_length=1)
    step_id: str = Field(..., min_length=1)
    tenant_id: str = Field(..., min_length=1)
    site_id: str = Field(..., min_length=1)
    asset_id: str = Field(..., min_length=1)
    item_type: str = "action_approval"
    risk_tier: str = "MEDIUM"
    priority: int = 50
    proposed_actions: List[Dict[str, Any]] = Field(default_factory=list)
    action_summary: str = ""
    telemetry_snapshot: Dict[str, Any] = Field(default_factory=dict)
    fault_context: Dict[str, Any] = Field(default_factory=dict)
    evidence: Dict[str, Any] = Field(default_factory=dict)
    expires_in_hours: Optional[int] = None


def _to_detail_response(item: QueueItem) -> QueueItemDetailResponse:
    return QueueItemDetailResponse(
        item_id=item.item_id,
        approval_id=item.approval_id,
        run_id=item.run_id,
        incident_id=item.incident_id,
        playbook_id=item.playbook_id,
        step_id=item.step_id,
        tenant_id=item.tenant_id,
        site_id=item.site_id,
        asset_id=item.asset_id,
        item_type=item.item_type,
        risk_tier=item.risk_tier,
        priority=item.priority,
        proposed_actions=item.proposed_actions,
        action_summary=item.action_summary,
        telemetry_snapshot=item.telemetry_snapshot,
        fault_context=item.fault_context,
        evidence=item.evidence,
        status=item.status.value,
        explanation=item.explanation.to_dict() if item.explanation else None,
        explanation_error=item.explanation_error,
        validation=item.validation.to_dict() if item.validation else None,
        validation_error=item.validation_error,
        decision=item.decision.to_dict() if item.decision else None,
        created_at=item.created_at.isoformat(),
        updated_at=item.updated_at.isoformat(),
        expires_at=item.expires_at.isoformat() if item.expires_at else None,
        assigned_to=item.assigned_to,
        escalation_level=item.escalation_level,
    )


# Queue Endpoints
@queue_router.post("", response_model=QueueItemDetailResponse)
async def create_queue_item(request: CreateQueueItemRequest):
    """Create a queue item for human review/approval."""
    item = await queue_service.add_item(
        approval_id=request.approval_id,
        run_id=request.run_id,
        incident_id=request.incident_id,
        playbook_id=request.playbook_id,
        step_id=request.step_id,
        tenant_id=request.tenant_id,
        site_id=request.site_id,
        asset_id=request.asset_id,
        item_type=request.item_type,
        risk_tier=request.risk_tier,
        proposed_actions=request.proposed_actions,
        action_summary=request.action_summary,
        telemetry_snapshot=request.telemetry_snapshot,
        fault_context=request.fault_context,
        evidence=request.evidence,
        priority=request.priority,
        expires_in_hours=request.expires_in_hours,
    )
    return _to_detail_response(item)


@queue_router.get("", response_model=List[QueueItemResponse])
async def list_queue(
    tenant_id: Optional[str] = None,
    status: Optional[str] = None,
    risk_tier: Optional[str] = None,
    assigned_to: Optional[str] = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """List items in the approval queue"""
    status_enum = QueueItemStatus(status) if status else None
    
    items = queue_service.get_queue(
        tenant_id=tenant_id,
        status=status_enum,
        risk_tier=risk_tier,
        assigned_to=assigned_to,
        limit=limit,
        offset=offset,
    )
    
    return [
        QueueItemResponse(
            item_id=item.item_id,
            approval_id=item.approval_id,
            run_id=item.run_id,
            asset_id=item.asset_id,
            site_id=item.site_id,
            item_type=item.item_type,
            risk_tier=item.risk_tier,
            priority=item.priority,
            action_summary=item.action_summary,
            status=item.status.value,
            created_at=item.created_at.isoformat(),
            expires_at=item.expires_at.isoformat() if item.expires_at else None,
            assigned_to=item.assigned_to,
            has_explanation=item.explanation is not None,
            has_validation=item.validation is not None,
            validation_status=item.validation.status.value if item.validation else None,
        )
        for item in items
    ]


@queue_router.get("/stats", response_model=QueueStatsResponse)
async def get_queue_stats(tenant_id: Optional[str] = None):
    """Get queue statistics"""
    stats = queue_service.get_stats(tenant_id=tenant_id)
    return QueueStatsResponse(**stats)


@queue_router.get("/pending-counts")
async def get_pending_counts(tenant_id: Optional[str] = None):
    """Get counts of pending items by status"""
    return queue_service.get_pending_count(tenant_id=tenant_id)


@queue_router.get("/{item_id}", response_model=QueueItemDetailResponse)
async def get_queue_item(item_id: str):
    """Get detailed information about a queue item"""
    item = queue_service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    return _to_detail_response(item)


# Review Action Endpoints
@review_router.post("/{item_id}/assign")
async def assign_item(
    item_id: str,
    reviewer_id: str = Body(..., embed=True),
):
    """Assign an item to a reviewer"""
    try:
        item = await queue_service.assign_item(item_id, reviewer_id)
        return {"status": "assigned", "item_id": item_id, "assigned_to": reviewer_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@review_router.post("/{item_id}/unassign")
async def unassign_item(item_id: str):
    """Unassign an item (return to queue)"""
    try:
        item = await queue_service.unassign_item(item_id)
        return {"status": "unassigned", "item_id": item_id}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@review_router.post("/{item_id}/approve")
async def approve_item(item_id: str, request: ApproveRequest):
    """Approve a queue item"""
    try:
        item = await queue_service.approve(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            reviewer_name=request.reviewer_name,
            reviewer_role=request.reviewer_role,
            notes=request.notes,
            modified_params=request.modified_params,
            llm_explanation_helpful=request.llm_explanation_helpful,
            llm_validation_accurate=request.llm_validation_accurate,
        )
        return {
            "status": "approved",
            "item_id": item_id,
            "decision_id": item.decision.decision_id if item.decision else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@review_router.post("/{item_id}/reject")
async def reject_item(item_id: str, request: RejectRequest):
    """Reject a queue item"""
    try:
        item = await queue_service.reject(
            item_id=item_id,
            reviewer_id=request.reviewer_id,
            reviewer_name=request.reviewer_name,
            reviewer_role=request.reviewer_role,
            reason=request.reason,
            notes=request.notes,
            llm_explanation_helpful=request.llm_explanation_helpful,
            llm_validation_accurate=request.llm_validation_accurate,
        )
        return {
            "status": "rejected",
            "item_id": item_id,
            "decision_id": item.decision.decision_id if item.decision else None,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@review_router.post("/{item_id}/escalate")
async def escalate_item(
    item_id: str,
    reason: str = Body(default="", embed=True),
):
    """Escalate an item to higher authority"""
    try:
        item = await queue_service.escalate(item_id, reason)
        return {
            "status": "escalated",
            "item_id": item_id,
            "escalation_level": item.escalation_level,
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@review_router.post("/{item_id}/regenerate-explanation")
async def regenerate_explanation(item_id: str):
    """Regenerate the LLM explanation for an item"""
    item = queue_service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        # Invalidate cache and regenerate
        queue_service.explainer.invalidate_cache(item_id)
        item.explanation = await queue_service.explainer.generate_explanation(item)
        item.explanation_error = None
        item.updated_at = datetime.utcnow()
        
        return {
            "status": "regenerated",
            "item_id": item_id,
            "explanation_id": item.explanation.explanation_id,
        }
    except Exception as e:
        item.explanation_error = str(e)
        raise HTTPException(status_code=500, detail=str(e))


@review_router.post("/{item_id}/revalidate")
async def revalidate_item(item_id: str):
    """Re-run validation for an item"""
    item = queue_service.get_item(item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    
    try:
        item.validation = await queue_service.validator.validate(item)
        item.validation_error = None
        item.updated_at = datetime.utcnow()
        
        return {
            "status": "revalidated",
            "item_id": item_id,
            "validation_status": item.validation.status.value,
        }
    except Exception as e:
        item.validation_error = str(e)
        raise HTTPException(status_code=500, detail=str(e))
