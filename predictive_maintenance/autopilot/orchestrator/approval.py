"""
Approval Manager

Manages human-in-the-loop approval workflow for autopilot runs.
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import uuid

from sqlalchemy.orm import Session

from ..models import ApprovalModel, AutopilotRunModel
from ..repositories import ApprovalRepository, AutopilotRunRepository
from ..schemas import RiskTier, ApprovalStatus, ApprovalDecision

logger = logging.getLogger(__name__)


@dataclass
class ApprovalRequest:
    """Request for human approval"""
    run_id: str
    step_id: Optional[str]
    tenant_id: str
    
    # What needs approval
    approval_type: str  # "run", "step", "action"
    risk_tier: RiskTier
    
    # Proposed actions
    proposed_actions: List[Dict[str, Any]]
    rationale: str
    
    # Evidence
    evidence_snapshot: Dict[str, Any] = field(default_factory=dict)
    
    # Timeout
    expires_in_minutes: int = 60


@dataclass
class ApprovalResult:
    """Result of an approval decision"""
    approval_id: str
    status: ApprovalStatus
    decision: Optional[ApprovalDecision]
    decided_by: Optional[str]
    decided_at: Optional[datetime]
    decision_notes: str
    edited_params: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_approved(self) -> bool:
        return self.decision in [ApprovalDecision.APPROVE, ApprovalDecision.EDIT]
    
    @property
    def is_rejected(self) -> bool:
        return self.decision == ApprovalDecision.REJECT
    
    @property
    def is_pending(self) -> bool:
        return self.status == ApprovalStatus.PENDING


class ApprovalManager:
    """
    Manages approval workflow for autopilot runs.
    
    Implements:
    - Risk tier-based approval requirements
    - Approval task creation and notification
    - Decision recording
    - Timeout handling
    - Escalation on rejection
    """
    
    def __init__(
        self,
        session_factory: Callable[[], Session],
        notification_connector: Optional[Any] = None,
        dev_mode: bool = True,
    ):
        self.session_factory = session_factory
        self.notification_connector = notification_connector
        self.dev_mode = dev_mode
    
    def requires_approval(
        self,
        risk_tier: RiskTier,
        action_type: str,
        policy: Dict[str, Any] = None,
    ) -> bool:
        """
        Determine if an action requires human approval.
        
        Args:
            risk_tier: Risk tier of the playbook
            action_type: Type of action being performed
            policy: Optional policy overrides
            
        Returns:
            True if approval is required
        """
        policy = policy or {}
        
        # Check policy overrides
        auto_approve_tiers = policy.get("auto_approve_risk_tiers", ["LOW"])
        if risk_tier.value in auto_approve_tiers:
            return False
        
        # Control writes always require approval for MEDIUM/HIGH
        control_actions = {"WRITE_POINT", "ESCALATE"}
        if action_type in control_actions:
            if risk_tier in [RiskTier.MEDIUM, RiskTier.HIGH]:
                return True
        
        # HIGH risk always requires approval
        if risk_tier == RiskTier.HIGH:
            return True
        
        return False
    
    def create_approval(self, request: ApprovalRequest) -> str:
        """
        Create an approval task.
        
        Args:
            request: Approval request details
            
        Returns:
            Approval ID
        """
        approval_id = f"APR-{uuid.uuid4().hex[:12].upper()}"
        expires_at = datetime.utcnow() + timedelta(minutes=request.expires_in_minutes)
        
        session = self.session_factory()
        try:
            approval_repo = ApprovalRepository(session)
            run_repo = AutopilotRunRepository(session)
            
            approval_repo.create(
                approval_id=approval_id,
                run_id=request.run_id,
                tenant_id=request.tenant_id,
                approval_type=request.approval_type,
                risk_tier=request.risk_tier.value,
                proposed_actions=request.proposed_actions,
                rationale=request.rationale,
                evidence_snapshot=request.evidence_snapshot,
                step_id=request.step_id,
                expires_at=expires_at,
            )
            
            # Update run status
            run_repo.set_pending_approval(request.run_id, approval_id)
            
            session.commit()
            
            logger.info(
                f"Created approval {approval_id} for run {request.run_id} "
                f"(risk_tier={request.risk_tier.value}, expires={expires_at})"
            )
            
            # TODO: Send notifications to approvers
            self._notify_approvers(request, approval_id)
            
            return approval_id
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to create approval: {e}")
            raise
        finally:
            session.close()
    
    def get_approval(self, approval_id: str) -> Optional[ApprovalResult]:
        """
        Get approval status.
        
        Returns:
            ApprovalResult or None if not found
        """
        session = self.session_factory()
        try:
            repo = ApprovalRepository(session)
            approval = repo.get_by_id(approval_id)
            
            if not approval:
                return None
            
            return ApprovalResult(
                approval_id=approval.approval_id,
                status=ApprovalStatus(approval.status),
                decision=ApprovalDecision(approval.decision) if approval.decision else None,
                decided_by=approval.decided_by,
                decided_at=approval.decided_at,
                decision_notes=approval.decision_notes or "",
                edited_params=approval.edited_params or {},
            )
        finally:
            session.close()
    
    def wait_for_approval(
        self,
        approval_id: str,
        timeout_seconds: int = 3600,
        poll_interval_seconds: int = 5,
    ) -> ApprovalResult:
        """
        Wait for an approval decision (blocking).
        
        In production, this would be replaced by event-driven handling.
        
        Args:
            approval_id: Approval ID to wait for
            timeout_seconds: Maximum time to wait
            poll_interval_seconds: Polling interval
            
        Returns:
            ApprovalResult with decision
        """
        import time
        
        start = datetime.utcnow()
        timeout = timedelta(seconds=timeout_seconds)
        
        while datetime.utcnow() - start < timeout:
            result = self.get_approval(approval_id)
            
            if result is None:
                raise ValueError(f"Approval {approval_id} not found")
            
            if not result.is_pending:
                return result
            
            # Check for expiration
            session = self.session_factory()
            try:
                repo = ApprovalRepository(session)
                approval = repo.get_by_id(approval_id)
                if approval and approval.expires_at and datetime.utcnow() > approval.expires_at:
                    # Mark as expired
                    approval.status = ApprovalStatus.EXPIRED.value
                    session.commit()
                    
                    return ApprovalResult(
                        approval_id=approval_id,
                        status=ApprovalStatus.EXPIRED,
                        decision=None,
                        decided_by=None,
                        decided_at=None,
                        decision_notes="Approval expired",
                    )
            finally:
                session.close()
            
            time.sleep(poll_interval_seconds)
        
        raise TimeoutError(f"Approval {approval_id} timed out after {timeout_seconds}s")
    
    def record_decision(
        self,
        approval_id: str,
        decision: ApprovalDecision,
        decided_by: str,
        decision_notes: str = "",
        edited_params: Dict[str, Any] = None,
    ) -> ApprovalResult:
        """
        Record an approval decision.
        
        Args:
            approval_id: Approval ID
            decision: The decision (approve/reject/edit)
            decided_by: User who made the decision
            decision_notes: Optional notes
            edited_params: Modified parameters if decision is EDIT
            
        Returns:
            Updated ApprovalResult
        """
        session = self.session_factory()
        try:
            approval_repo = ApprovalRepository(session)
            run_repo = AutopilotRunRepository(session)
            
            approval = approval_repo.get_by_id(approval_id)
            if not approval:
                raise ValueError(f"Approval {approval_id} not found")
            
            if approval.status != ApprovalStatus.PENDING.value:
                raise ValueError(f"Approval {approval_id} already decided: {approval.status}")
            
            # Record decision
            approval_repo.decide(
                approval_id=approval_id,
                decision=decision.value,
                decided_by=decided_by,
                decision_notes=decision_notes,
                edited_params=edited_params,
            )
            
            # Update run status
            run = run_repo.get_by_id(approval.run_id)
            if run:
                run_repo.clear_pending_approval(run.run_id)
                
                if decision in [ApprovalDecision.APPROVE, ApprovalDecision.EDIT]:
                    run_repo.update_status(run.run_id, "approved")
                elif decision == ApprovalDecision.REJECT:
                    run_repo.update_status(
                        run.run_id,
                        "rejected",
                        outcome="REJECTED",
                        outcome_reason=f"Rejected by {decided_by}: {decision_notes}"
                    )
            
            session.commit()
            
            logger.info(
                f"Recorded decision {decision.value} for approval {approval_id} "
                f"by {decided_by}"
            )
            
            return ApprovalResult(
                approval_id=approval_id,
                status=ApprovalStatus(approval.status),
                decision=decision,
                decided_by=decided_by,
                decided_at=datetime.utcnow(),
                decision_notes=decision_notes,
                edited_params=edited_params or {},
            )
            
        except Exception as e:
            session.rollback()
            logger.error(f"Failed to record decision: {e}")
            raise
        finally:
            session.close()
    
    def list_pending(
        self,
        tenant_id: str = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """
        List pending approvals.
        
        Returns:
            List of pending approval summaries
        """
        session = self.session_factory()
        try:
            repo = ApprovalRepository(session)
            approvals = repo.list_pending(tenant_id=tenant_id, limit=limit)
            
            return [
                {
                    "approval_id": a.approval_id,
                    "run_id": a.run_id,
                    "step_id": a.step_id,
                    "tenant_id": a.tenant_id,
                    "approval_type": a.approval_type,
                    "risk_tier": a.risk_tier,
                    "proposed_actions": a.proposed_actions,
                    "rationale": a.rationale,
                    "created_at": a.created_at.isoformat() if a.created_at else None,
                    "expires_at": a.expires_at.isoformat() if a.expires_at else None,
                }
                for a in approvals
            ]
        finally:
            session.close()
    
    def _notify_approvers(self, request: ApprovalRequest, approval_id: str):
        """
        Send notifications to approvers.
        """
        recipients_env = os.getenv("PDM_APPROVAL_RECIPIENTS", "")
        recipients = [r.strip() for r in recipients_env.split(",") if r.strip()]
        if not recipients:
            recipients = [f"ops@{request.tenant_id or 'default'}.local"]

        payload = {
            "approval_id": approval_id,
            "run_id": request.run_id,
            "risk_tier": request.risk_tier.value,
            "tenant_id": request.tenant_id,
            "step_id": request.step_id,
            "expires_in_minutes": request.expires_in_minutes,
        }

        connector = self.notification_connector
        if connector is None:
            if self.dev_mode:
                logger.info(
                    "Approval notification no-op in dev_mode: %s",
                    payload,
                )
                return
            raise RuntimeError(
                "Approval notification connector is required when dev_mode is disabled."
            )

        try:
            if hasattr(connector, "send_approval_request"):
                response = connector.send_approval_request(
                    recipients=recipients,
                    approval_id=approval_id,
                    run_id=request.run_id,
                    proposed_actions=request.proposed_actions,
                    rationale=request.rationale,
                    expires_at=datetime.utcnow() + timedelta(minutes=request.expires_in_minutes),
                )
            else:
                response = connector.send(
                    recipients=recipients,
                    channel="email",
                    subject=f"[APPROVAL REQUIRED] {approval_id}",
                    message=(
                        f"Approval required for run {request.run_id} "
                        f"(risk={request.risk_tier.value}, step={request.step_id})."
                    ),
                    context=payload,
                )
            logger.info(
                "Approval notification dispatched: approval_id=%s run_id=%s recipients=%s success=%s",
                approval_id,
                request.run_id,
                recipients,
                getattr(response, "success", True),
            )
        except Exception as exc:
            if self.dev_mode:
                logger.warning(
                    "Approval notification failed in dev_mode, continuing: approval_id=%s error=%s",
                    approval_id,
                    exc,
                )
                return
            raise RuntimeError(
                f"Approval notification failed for approval_id={approval_id}: {exc}"
            ) from exc
