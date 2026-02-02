"""
ML Learning Loop - Governance Controls

Approval workflows, risk assessment, and audit trails for ML operations.
"""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from .learning_loop_models import (
    ApprovalStatus,
    GovernanceAction,
    GovernanceApproval,
    ModelStage,
)
from .data_plane import ActionRiskLevel
from .governance import AuditLogger, PolicyEngine

logger = logging.getLogger(__name__)


class MLGovernanceController:
    """
    Governance controls for ML operations including approval workflows,
    risk assessment, and audit trails.
    """
    
    def __init__(self, policy_engine: Optional[PolicyEngine] = None,
                 audit_logger: Optional[AuditLogger] = None):
        self.policy_engine = policy_engine or PolicyEngine()
        self.audit_logger = audit_logger or AuditLogger()
        self.pending_approvals: Dict[str, GovernanceApproval] = {}
        self.processed_approvals: Dict[str, GovernanceApproval] = {}
        
        # Auto-approval rules by action type and risk level
        self.auto_approve_rules: Dict[GovernanceAction, Dict[ActionRiskLevel, bool]] = {
            GovernanceAction.MODEL_PROMOTE: {
                ActionRiskLevel.SAFE: True,
                ActionRiskLevel.LOW: False,
                ActionRiskLevel.MEDIUM: False,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
            GovernanceAction.MODEL_DEPLOY: {
                ActionRiskLevel.SAFE: False,
                ActionRiskLevel.LOW: False,
                ActionRiskLevel.MEDIUM: False,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
            GovernanceAction.MODEL_ROLLBACK: {
                ActionRiskLevel.SAFE: True,
                ActionRiskLevel.LOW: True,
                ActionRiskLevel.MEDIUM: False,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
            GovernanceAction.EXPERIMENT_START: {
                ActionRiskLevel.SAFE: True,
                ActionRiskLevel.LOW: True,
                ActionRiskLevel.MEDIUM: False,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
            GovernanceAction.EXPERIMENT_CONCLUDE: {
                ActionRiskLevel.SAFE: True,
                ActionRiskLevel.LOW: True,
                ActionRiskLevel.MEDIUM: True,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
            GovernanceAction.RETRAIN_TRIGGER: {
                ActionRiskLevel.SAFE: True,
                ActionRiskLevel.LOW: True,
                ActionRiskLevel.MEDIUM: True,
                ActionRiskLevel.HIGH: False,
                ActionRiskLevel.CRITICAL: False,
            },
        }
        
        # Required approver roles by action
        self.required_approvers: Dict[GovernanceAction, List[str]] = {
            GovernanceAction.MODEL_DEPLOY: ["ml_engineer", "ml_lead"],
            GovernanceAction.MODEL_PROMOTE: ["ml_engineer"],
            GovernanceAction.MODEL_ROLLBACK: ["ml_engineer", "on_call"],
            GovernanceAction.EXPERIMENT_START: ["ml_engineer", "product_owner"],
            GovernanceAction.EXPERIMENT_CONCLUDE: ["ml_engineer"],
            GovernanceAction.RETRAIN_TRIGGER: ["ml_engineer"],
        }
        
        # Approval expiration hours by action
        self.approval_expiration: Dict[GovernanceAction, int] = {
            GovernanceAction.MODEL_DEPLOY: 72,
            GovernanceAction.MODEL_PROMOTE: 72,
            GovernanceAction.MODEL_ROLLBACK: 4,  # Urgent
            GovernanceAction.EXPERIMENT_START: 168,
            GovernanceAction.EXPERIMENT_CONCLUDE: 72,
            GovernanceAction.RETRAIN_TRIGGER: 48,
        }
    
    def request_approval(self, action_type: GovernanceAction, target_id: str,
                         target_type: str, requested_by: str,
                         action_details: Dict[str, Any] = None,
                         risk_level: ActionRiskLevel = ActionRiskLevel.MEDIUM) -> GovernanceApproval:
        """Create an approval request"""
        expiration_hours = self.approval_expiration.get(action_type, 72)
        
        approval = GovernanceApproval(
            approval_id=str(uuid.uuid4())[:12],
            action_type=action_type,
            requested_at=datetime.utcnow(),
            requested_by=requested_by,
            target_id=target_id,
            target_type=target_type,
            action_details=action_details or {},
            risk_level=risk_level.value,
            expires_at=datetime.utcnow() + timedelta(hours=expiration_hours),
        )
        
        # Check auto-approval
        auto_approve = self.auto_approve_rules.get(action_type, {}).get(risk_level, False)
        if auto_approve:
            approval.status = ApprovalStatus.AUTO_APPROVED
            approval.reviewed_at = datetime.utcnow()
            approval.review_notes = "Auto-approved based on risk level"
            self.processed_approvals[approval.approval_id] = approval
        else:
            self.pending_approvals[approval.approval_id] = approval
        
        self.audit_logger.log(
            action_type="approval_requested",
            actor_id=requested_by,
            parameters={
                "approval_id": approval.approval_id,
                "action_type": action_type.value,
                "target_id": target_id,
                "risk_level": risk_level.value,
                "auto_approved": auto_approve,
            },
        )
        
        logger.info(f"Approval request created: {approval.approval_id} for {action_type.value}")
        return approval
    
    def process_approval(self, approval_id: str, approved: bool,
                         reviewer: str, notes: str = "") -> Tuple[bool, str]:
        """Process an approval decision"""
        approval = self.pending_approvals.get(approval_id)
        if not approval:
            if approval_id in self.processed_approvals:
                return False, "Approval already processed"
            return False, "Approval not found"
        
        if approval.expires_at and datetime.utcnow() > approval.expires_at:
            approval.status = ApprovalStatus.EXPIRED
            self.processed_approvals[approval_id] = approval
            del self.pending_approvals[approval_id]
            return False, "Approval request expired"
        
        # Validate reviewer permission
        required_roles = self.required_approvers.get(approval.action_type, [])
        # In production, verify reviewer has one of required_roles
        
        approval.status = ApprovalStatus.APPROVED if approved else ApprovalStatus.REJECTED
        approval.reviewed_by = reviewer
        approval.reviewed_at = datetime.utcnow()
        approval.review_notes = notes
        
        self.processed_approvals[approval_id] = approval
        del self.pending_approvals[approval_id]
        
        self.audit_logger.log(
            action_type="approval_processed",
            actor_id=reviewer,
            parameters={
                "approval_id": approval_id,
                "approved": approved,
                "notes": notes,
            },
        )
        
        status_text = "approved" if approved else "rejected"
        logger.info(f"Approval {approval_id} {status_text} by {reviewer}")
        return True, f"Approval {status_text}"
    
    def get_approval(self, approval_id: str) -> Optional[GovernanceApproval]:
        """Get approval by ID"""
        return self.pending_approvals.get(approval_id) or self.processed_approvals.get(approval_id)
    
    def get_pending_approvals(self, action_type: Optional[GovernanceAction] = None,
                              target_type: Optional[str] = None) -> List[GovernanceApproval]:
        """Get pending approvals with optional filters"""
        approvals = list(self.pending_approvals.values())
        
        if action_type:
            approvals = [a for a in approvals if a.action_type == action_type]
        if target_type:
            approvals = [a for a in approvals if a.target_type == target_type]
        
        # Sort by urgency (expiration date)
        approvals.sort(key=lambda a: a.expires_at or datetime.max)
        return approvals
    
    def get_approval_history(self, target_id: Optional[str] = None,
                            action_type: Optional[GovernanceAction] = None,
                            limit: int = 50) -> List[GovernanceApproval]:
        """Get approval history"""
        approvals = list(self.processed_approvals.values())
        
        if target_id:
            approvals = [a for a in approvals if a.target_id == target_id]
        if action_type:
            approvals = [a for a in approvals if a.action_type == action_type]
        
        approvals.sort(key=lambda a: a.requested_at, reverse=True)
        return approvals[:limit]
    
    def check_expired_approvals(self) -> List[GovernanceApproval]:
        """Check and expire overdue approvals"""
        expired = []
        now = datetime.utcnow()
        
        for approval_id, approval in list(self.pending_approvals.items()):
            if approval.expires_at and now > approval.expires_at:
                approval.status = ApprovalStatus.EXPIRED
                self.processed_approvals[approval_id] = approval
                del self.pending_approvals[approval_id]
                expired.append(approval)
                
                self.audit_logger.log(
                    action_type="approval_expired",
                    actor_id="system",
                    parameters={"approval_id": approval_id},
                )
        
        return expired
    
    def assess_risk(self, action_type: GovernanceAction, 
                    context: Dict[str, Any]) -> ActionRiskLevel:
        """Assess risk level for an action"""
        if action_type == GovernanceAction.MODEL_DEPLOY:
            if context.get("target_stage") == ModelStage.PRODUCTION.value:
                if context.get("has_canary_validation", False):
                    return ActionRiskLevel.MEDIUM
                return ActionRiskLevel.HIGH
            return ActionRiskLevel.MEDIUM
        
        elif action_type == GovernanceAction.MODEL_PROMOTE:
            target_stage = context.get("target_stage", "")
            if target_stage == ModelStage.PRODUCTION.value:
                return ActionRiskLevel.HIGH
            elif target_stage == ModelStage.CANARY.value:
                return ActionRiskLevel.MEDIUM
            return ActionRiskLevel.LOW
        
        elif action_type == GovernanceAction.MODEL_ROLLBACK:
            if context.get("target_was_production", False):
                return ActionRiskLevel.LOW  # Rollback to known-good is lower risk
            return ActionRiskLevel.MEDIUM
        
        elif action_type == GovernanceAction.EXPERIMENT_START:
            max_traffic = context.get("max_traffic_percentage", 50)
            if max_traffic <= 5:
                return ActionRiskLevel.SAFE
            elif max_traffic <= 10:
                return ActionRiskLevel.LOW
            elif max_traffic <= 30:
                return ActionRiskLevel.MEDIUM
            return ActionRiskLevel.HIGH
        
        elif action_type == GovernanceAction.RETRAIN_TRIGGER:
            if context.get("trigger_type") == "manual":
                return ActionRiskLevel.LOW
            if context.get("auto_deploy", False):
                return ActionRiskLevel.MEDIUM
            return ActionRiskLevel.LOW
        
        return ActionRiskLevel.MEDIUM
    
    def validate_action(self, action_type: GovernanceAction,
                        actor_id: str, context: Dict[str, Any]) -> Tuple[bool, str]:
        """Validate if an action can be performed"""
        if action_type == GovernanceAction.MODEL_DEPLOY:
            if not context.get("has_validation_metrics", False):
                return False, "Model must have validation metrics before deployment"
            
            if context.get("target_stage") == ModelStage.PRODUCTION.value:
                if not context.get("approval_id"):
                    return False, "Production deployment requires approval"
                
                approval = self.get_approval(context["approval_id"])
                if not approval or approval.status not in [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED]:
                    return False, "Valid approval required for production deployment"
        
        elif action_type == GovernanceAction.MODEL_PROMOTE:
            if context.get("target_stage") == ModelStage.PRODUCTION.value:
                if not context.get("has_staging_validation", False):
                    return False, "Model must pass staging validation before production"
        
        elif action_type == GovernanceAction.EXPERIMENT_START:
            if not context.get("has_control_variant", False):
                return False, "Experiment must have a control variant"
            
            if context.get("conflicts_with_active", False):
                return False, "Conflicting experiment already active for this model type"
        
        elif action_type == GovernanceAction.RETRAIN_TRIGGER:
            if context.get("job_already_running", False):
                return False, "Retraining job already in progress for this model"
        
        return True, "Validation passed"
    
    def create_rollback_approval(self, model_name: str, from_version: str,
                                  to_version: str, reason: str,
                                  requested_by: str) -> GovernanceApproval:
        """Create expedited approval for rollback"""
        context = {
            "model_name": model_name,
            "from_version": from_version,
            "to_version": to_version,
            "reason": reason,
            "target_was_production": True,
        }
        
        risk = self.assess_risk(GovernanceAction.MODEL_ROLLBACK, context)
        
        return self.request_approval(
            action_type=GovernanceAction.MODEL_ROLLBACK,
            target_id=to_version,
            target_type="model_version",
            requested_by=requested_by,
            action_details=context,
            risk_level=risk,
        )
    
    def get_governance_stats(self) -> Dict[str, Any]:
        """Get governance statistics"""
        pending = list(self.pending_approvals.values())
        processed = list(self.processed_approvals.values())
        
        approved = [a for a in processed if a.status == ApprovalStatus.APPROVED]
        rejected = [a for a in processed if a.status == ApprovalStatus.REJECTED]
        auto_approved = [a for a in processed if a.status == ApprovalStatus.AUTO_APPROVED]
        expired = [a for a in processed if a.status == ApprovalStatus.EXPIRED]
        
        return {
            "pending_count": len(pending),
            "total_processed": len(processed),
            "approved": len(approved),
            "rejected": len(rejected),
            "auto_approved": len(auto_approved),
            "expired": len(expired),
            "approval_rate": len(approved) / max(len(processed), 1) * 100,
            "pending_by_action": {
                action.value: len([a for a in pending if a.action_type == action])
                for action in GovernanceAction
            },
            "avg_approval_time_hours": self._calculate_avg_approval_time(approved),
        }
    
    def _calculate_avg_approval_time(self, approvals: List[GovernanceApproval]) -> Optional[float]:
        """Calculate average approval time in hours"""
        times = []
        for a in approvals:
            if a.requested_at and a.reviewed_at:
                diff = (a.reviewed_at - a.requested_at).total_seconds() / 3600
                times.append(diff)
        
        return sum(times) / len(times) if times else None


class RollbackManager:
    """
    Manages model rollback operations with safety checks.
    """
    
    def __init__(self, governance: MLGovernanceController, audit_logger: AuditLogger):
        self.governance = governance
        self.audit_logger = audit_logger
        self.rollback_history: List[Dict[str, Any]] = []
    
    def initiate_rollback(self, model_name: str, from_version_id: str,
                          to_version_id: str, reason: str,
                          initiated_by: str) -> Tuple[bool, str, Optional[str]]:
        """
        Initiate a rollback with governance checks.
        Returns (success, message, approval_id if needed)
        """
        context = {
            "model_name": model_name,
            "from_version": from_version_id,
            "to_version": to_version_id,
            "reason": reason,
            "target_was_production": True,
        }
        
        # Validate rollback
        valid, msg = self.governance.validate_action(
            GovernanceAction.MODEL_ROLLBACK, initiated_by, context
        )
        if not valid:
            return False, msg, None
        
        # Assess risk
        risk = self.governance.assess_risk(GovernanceAction.MODEL_ROLLBACK, context)
        
        # Create approval request
        approval = self.governance.request_approval(
            action_type=GovernanceAction.MODEL_ROLLBACK,
            target_id=to_version_id,
            target_type="model_version",
            requested_by=initiated_by,
            action_details=context,
            risk_level=risk,
        )
        
        if approval.status in [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED]:
            return True, "Rollback approved", approval.approval_id
        
        return False, "Rollback pending approval", approval.approval_id
    
    def execute_rollback(self, approval_id: str, executed_by: str,
                         rollback_func) -> Tuple[bool, str]:
        """Execute an approved rollback"""
        approval = self.governance.get_approval(approval_id)
        if not approval:
            return False, "Approval not found"
        
        if approval.status not in [ApprovalStatus.APPROVED, ApprovalStatus.AUTO_APPROVED]:
            return False, f"Rollback not approved (status: {approval.status.value})"
        
        try:
            details = approval.action_details
            success, msg = rollback_func(
                details["model_name"],
                details["to_version"],
                executed_by,
                details["reason"],
            )
            
            if success:
                self.rollback_history.append({
                    "approval_id": approval_id,
                    "model_name": details["model_name"],
                    "from_version": details["from_version"],
                    "to_version": details["to_version"],
                    "reason": details["reason"],
                    "executed_by": executed_by,
                    "executed_at": datetime.utcnow().isoformat(),
                })
            
            return success, msg
            
        except Exception as e:
            self.audit_logger.log(
                action_type="rollback_failed",
                actor_id=executed_by,
                parameters={
                    "approval_id": approval_id,
                    "error": str(e),
                },
            )
            return False, str(e)
    
    def get_rollback_history(self, model_name: Optional[str] = None) -> List[Dict[str, Any]]:
        """Get rollback history"""
        history = self.rollback_history
        if model_name:
            history = [h for h in history if h["model_name"] == model_name]
        return history
