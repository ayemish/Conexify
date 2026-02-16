"""
Autopilot Repositories

Data access layer for Autopilot entities.
"""

from datetime import datetime
from typing import List, Optional, Dict, Any

from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from .models import (
    PlaybookModel,
    PlaybookVersionModel,
    IncidentModel,
    AutopilotRunModel,
    RunStepModel,
    RunActionModel,
    ApprovalModel,
    CheckpointModel,
    VerificationResultModel,
    EvidencePackModel,
    PolicyModel,
)


class PlaybookRepository:
    """Repository for Playbook operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        playbook_id: str,
        name: str,
        asset_class: str,
        fault_type: str,
        risk_tier: str = "MEDIUM",
        description: str = "",
    ) -> PlaybookModel:
        playbook = PlaybookModel(
            playbook_id=playbook_id,
            name=name,
            asset_class=asset_class,
            fault_type=fault_type,
            risk_tier=risk_tier,
            description=description,
        )
        self.session.add(playbook)
        self.session.flush()
        return playbook
    
    def get_by_id(self, playbook_id: str) -> Optional[PlaybookModel]:
        return self.session.query(PlaybookModel).filter(
            PlaybookModel.playbook_id == playbook_id
        ).first()
    
    def list_active(
        self,
        asset_class: Optional[str] = None,
        fault_type: Optional[str] = None,
        risk_tier: Optional[str] = None,
    ) -> List[PlaybookModel]:
        query = self.session.query(PlaybookModel).filter(
            PlaybookModel.is_active == True
        )
        if asset_class:
            query = query.filter(PlaybookModel.asset_class == asset_class)
        if fault_type:
            query = query.filter(PlaybookModel.fault_type == fault_type)
        if risk_tier:
            query = query.filter(PlaybookModel.risk_tier == risk_tier)
        return query.all()
    
    def retire(self, playbook_id: str) -> bool:
        playbook = self.get_by_id(playbook_id)
        if playbook:
            playbook.is_active = False
            playbook.retired_at = datetime.utcnow()
            self.session.flush()
            return True
        return False


class PlaybookVersionRepository:
    """Repository for PlaybookVersion operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        playbook_id: str,
        version: str,
        definition: Dict[str, Any],
        content_hash: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> PlaybookVersionModel:
        pv = PlaybookVersionModel(
            playbook_id=playbook_id,
            version=version,
            definition=definition,
            triggers=definition.get("triggers", []),
            preconditions=definition.get("preconditions", []),
            steps=definition.get("steps", []),
            verification=definition.get("verification", []),
            escalation=definition.get("escalation", {}),
            evidence_requirements=definition.get("evidence", {}),
            content_hash=content_hash,
            created_by=created_by,
        )
        self.session.add(pv)
        self.session.flush()
        return pv
    
    def get_latest(self, playbook_id: str) -> Optional[PlaybookVersionModel]:
        return self.session.query(PlaybookVersionModel).filter(
            PlaybookVersionModel.playbook_id == playbook_id,
            PlaybookVersionModel.retired_at.is_(None),
        ).order_by(PlaybookVersionModel.effective_from.desc()).first()
    
    def get_version(self, playbook_id: str, version: str) -> Optional[PlaybookVersionModel]:
        return self.session.query(PlaybookVersionModel).filter(
            PlaybookVersionModel.playbook_id == playbook_id,
            PlaybookVersionModel.version == version,
        ).first()
    
    def list_versions(self, playbook_id: str) -> List[PlaybookVersionModel]:
        return self.session.query(PlaybookVersionModel).filter(
            PlaybookVersionModel.playbook_id == playbook_id
        ).order_by(PlaybookVersionModel.effective_from.desc()).all()


class IncidentRepository:
    """Repository for Incident operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        incident_id: str,
        tenant_id: str,
        site_id: str,
        asset_id: str,
        fault_type: str,
        severity: str,
        source: str,
        start_ts: datetime,
        trigger_evidence: Dict[str, Any] = None,
        point_values: Dict[str, float] = None,
    ) -> IncidentModel:
        dedup_key = f"{asset_id}:{fault_type}:{start_ts.date().isoformat()}"
        
        incident = IncidentModel(
            incident_id=incident_id,
            tenant_id=tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            fault_type=fault_type,
            severity=severity,
            source=source,
            start_ts=start_ts,
            trigger_evidence=trigger_evidence or {},
            point_values=point_values or {},
            dedup_key=dedup_key,
        )
        self.session.add(incident)
        self.session.flush()
        return incident
    
    def get_by_id(self, incident_id: str) -> Optional[IncidentModel]:
        return self.session.query(IncidentModel).filter(
            IncidentModel.incident_id == incident_id
        ).first()
    
    def find_duplicate(
        self,
        asset_id: str,
        fault_type: str,
        start_ts: datetime,
    ) -> Optional[IncidentModel]:
        dedup_key = f"{asset_id}:{fault_type}:{start_ts.date().isoformat()}"
        return self.session.query(IncidentModel).filter(
            IncidentModel.dedup_key == dedup_key,
            IncidentModel.status.in_(["open", "matched", "run_started"]),
        ).first()
    
    def list_open(
        self,
        tenant_id: Optional[str] = None,
        site_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[IncidentModel]:
        query = self.session.query(IncidentModel).filter(
            IncidentModel.status.in_(["open", "matched", "run_started"])
        )
        if tenant_id:
            query = query.filter(IncidentModel.tenant_id == tenant_id)
        if site_id:
            query = query.filter(IncidentModel.site_id == site_id)
        if asset_id:
            query = query.filter(IncidentModel.asset_id == asset_id)
        return query.order_by(IncidentModel.detected_at.desc()).limit(limit).all()
    
    def update_status(self, incident_id: str, status: str) -> bool:
        incident = self.get_by_id(incident_id)
        if incident:
            incident.status = status
            incident.updated_at = datetime.utcnow()
            if status in ["resolved", "closed"]:
                incident.closed_at = datetime.utcnow()
            self.session.flush()
            return True
        return False
    
    def set_matched_playbook(
        self,
        incident_id: str,
        playbook_id: str,
        match_reason: str,
    ) -> bool:
        incident = self.get_by_id(incident_id)
        if incident:
            incident.matched_playbook_id = playbook_id
            incident.match_reason = match_reason
            incident.status = "matched"
            incident.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False


class AutopilotRunRepository:
    """Repository for AutopilotRun operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        run_id: str,
        incident_id: str,
        playbook_id: str,
        playbook_version: str,
        tenant_id: str,
        site_id: str,
        asset_id: str,
        thread_id: str,
        risk_tier: str = "MEDIUM",
        plan_rationale: str = "",
    ) -> AutopilotRunModel:
        run = AutopilotRunModel(
            run_id=run_id,
            incident_id=incident_id,
            playbook_id=playbook_id,
            playbook_version=playbook_version,
            tenant_id=tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            thread_id=thread_id,
            risk_tier=risk_tier,
            plan_rationale=plan_rationale,
        )
        self.session.add(run)
        self.session.flush()
        return run
    
    def get_by_id(self, run_id: str) -> Optional[AutopilotRunModel]:
        return self.session.query(AutopilotRunModel).filter(
            AutopilotRunModel.run_id == run_id
        ).first()
    
    def get_by_thread(self, thread_id: str) -> Optional[AutopilotRunModel]:
        return self.session.query(AutopilotRunModel).filter(
            AutopilotRunModel.thread_id == thread_id
        ).first()
    
    def list_active(
        self,
        tenant_id: Optional[str] = None,
        site_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[AutopilotRunModel]:
        active_statuses = ["planning", "awaiting_approval", "approved", "executing", "paused", "verifying"]
        query = self.session.query(AutopilotRunModel).filter(
            AutopilotRunModel.status.in_(active_statuses)
        )
        if tenant_id:
            query = query.filter(AutopilotRunModel.tenant_id == tenant_id)
        if site_id:
            query = query.filter(AutopilotRunModel.site_id == site_id)
        if asset_id:
            query = query.filter(AutopilotRunModel.asset_id == asset_id)
        return query.order_by(AutopilotRunModel.created_at.desc()).limit(limit).all()
    
    def update_status(
        self,
        run_id: str,
        status: str,
        outcome: Optional[str] = None,
        outcome_reason: Optional[str] = None,
    ) -> bool:
        run = self.get_by_id(run_id)
        if run:
            run.status = status
            run.updated_at = datetime.utcnow()
            if outcome:
                run.outcome = outcome
                run.outcome_reason = outcome_reason
            if status == "executing" and not run.started_at:
                run.started_at = datetime.utcnow()
            if status in ["completed", "failed", "cancelled", "rejected"]:
                run.completed_at = datetime.utcnow()
            self.session.flush()
            return True
        return False
    
    def set_pending_approval(self, run_id: str, approval_id: str) -> bool:
        run = self.get_by_id(run_id)
        if run:
            run.pending_approval_id = approval_id
            run.status = "awaiting_approval"
            run.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False
    
    def clear_pending_approval(self, run_id: str) -> bool:
        run = self.get_by_id(run_id)
        if run:
            run.pending_approval_id = None
            run.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False
    
    def set_checkpoint(self, run_id: str, checkpoint_id: str) -> bool:
        run = self.get_by_id(run_id)
        if run:
            run.current_checkpoint_id = checkpoint_id
            run.updated_at = datetime.utcnow()
            self.session.flush()
            return True
        return False


class ApprovalRepository:
    """Repository for Approval operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        approval_id: str,
        run_id: str,
        tenant_id: str,
        approval_type: str,
        risk_tier: str,
        proposed_actions: List[Dict[str, Any]],
        rationale: str,
        evidence_snapshot: Dict[str, Any],
        step_id: Optional[str] = None,
        expires_at: Optional[datetime] = None,
    ) -> ApprovalModel:
        approval = ApprovalModel(
            approval_id=approval_id,
            run_id=run_id,
            tenant_id=tenant_id,
            approval_type=approval_type,
            risk_tier=risk_tier,
            proposed_actions=proposed_actions,
            rationale=rationale,
            evidence_snapshot=evidence_snapshot,
            step_id=step_id,
            expires_at=expires_at,
        )
        self.session.add(approval)
        self.session.flush()
        return approval
    
    def get_by_id(self, approval_id: str) -> Optional[ApprovalModel]:
        return self.session.query(ApprovalModel).filter(
            ApprovalModel.approval_id == approval_id
        ).first()
    
    def list_pending(
        self,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[ApprovalModel]:
        query = self.session.query(ApprovalModel).filter(
            ApprovalModel.status == "pending"
        )
        if tenant_id:
            query = query.filter(ApprovalModel.tenant_id == tenant_id)
        return query.order_by(ApprovalModel.created_at.desc()).limit(limit).all()
    
    def decide(
        self,
        approval_id: str,
        decision: str,
        decided_by: str,
        decision_notes: str = "",
        edited_params: Dict[str, Any] = None,
    ) -> bool:
        approval = self.get_by_id(approval_id)
        if approval and approval.status == "pending":
            approval.decision = decision
            approval.decided_by = decided_by
            approval.decided_at = datetime.utcnow()
            approval.decision_notes = decision_notes
            
            if decision == "approve":
                approval.status = "approved"
            elif decision == "reject":
                approval.status = "rejected"
                approval.escalation_triggered = True
            elif decision == "edit":
                approval.status = "edited"
                approval.edited_params = edited_params or {}
            
            self.session.flush()
            return True
        return False


class CheckpointRepository:
    """Repository for Checkpoint operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        checkpoint_id: str,
        run_id: str,
        thread_id: str,
        step_index: int,
        run_status: str,
        state_json: str,
        reason: str = "",
        parent_checkpoint_id: Optional[str] = None,
    ) -> CheckpointModel:
        checkpoint = CheckpointModel(
            checkpoint_id=checkpoint_id,
            run_id=run_id,
            thread_id=thread_id,
            step_index=step_index,
            run_status=run_status,
            state_json=state_json,
            reason=reason,
            parent_checkpoint_id=parent_checkpoint_id,
        )
        self.session.add(checkpoint)
        self.session.flush()
        return checkpoint
    
    def get_by_id(self, checkpoint_id: str) -> Optional[CheckpointModel]:
        return self.session.query(CheckpointModel).filter(
            CheckpointModel.checkpoint_id == checkpoint_id
        ).first()
    
    def get_latest(self, run_id: str) -> Optional[CheckpointModel]:
        return self.session.query(CheckpointModel).filter(
            CheckpointModel.run_id == run_id
        ).order_by(CheckpointModel.created_at.desc()).first()
    
    def list_for_run(self, run_id: str) -> List[CheckpointModel]:
        return self.session.query(CheckpointModel).filter(
            CheckpointModel.run_id == run_id
        ).order_by(CheckpointModel.created_at.asc()).all()


class PolicyRepository:
    """Repository for Policy operations"""
    
    def __init__(self, session: Session):
        self.session = session
    
    def create(
        self,
        policy_id: str,
        tenant_id: str,
        name: str,
        site_id: Optional[str] = None,
        asset_id: Optional[str] = None,
        description: str = "",
        constraints: List[Dict[str, Any]] = None,
        max_setpoint_delta: float = 5.0,
        max_override_duration_seconds: int = 3600,
        max_commands_per_asset_per_hour: int = 10,
    ) -> PolicyModel:
        policy = PolicyModel(
            policy_id=policy_id,
            tenant_id=tenant_id,
            name=name,
            site_id=site_id,
            asset_id=asset_id,
            description=description,
            constraints=constraints or [],
            max_setpoint_delta=max_setpoint_delta,
            max_override_duration_seconds=max_override_duration_seconds,
            max_commands_per_asset_per_hour=max_commands_per_asset_per_hour,
        )
        self.session.add(policy)
        self.session.flush()
        return policy
    
    def get_by_id(self, policy_id: str) -> Optional[PolicyModel]:
        return self.session.query(PolicyModel).filter(
            PolicyModel.policy_id == policy_id
        ).first()
    
    def get_effective_policy(
        self,
        tenant_id: str,
        site_id: Optional[str] = None,
        asset_id: Optional[str] = None,
    ) -> Optional[PolicyModel]:
        """Get most specific active policy for the scope"""
        # Try asset-specific first
        if asset_id:
            policy = self.session.query(PolicyModel).filter(
                PolicyModel.tenant_id == tenant_id,
                PolicyModel.asset_id == asset_id,
                PolicyModel.is_active == True,
            ).first()
            if policy:
                return policy
        
        # Try site-specific
        if site_id:
            policy = self.session.query(PolicyModel).filter(
                PolicyModel.tenant_id == tenant_id,
                PolicyModel.site_id == site_id,
                PolicyModel.asset_id.is_(None),
                PolicyModel.is_active == True,
            ).first()
            if policy:
                return policy
        
        # Fall back to tenant-wide
        return self.session.query(PolicyModel).filter(
            PolicyModel.tenant_id == tenant_id,
            PolicyModel.site_id.is_(None),
            PolicyModel.asset_id.is_(None),
            PolicyModel.is_active == True,
        ).first()
    
    def list_for_tenant(self, tenant_id: str) -> List[PolicyModel]:
        return self.session.query(PolicyModel).filter(
            PolicyModel.tenant_id == tenant_id,
            PolicyModel.is_active == True,
        ).all()
