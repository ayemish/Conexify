"""
Autopilot API Routes

REST API endpoints for the Operations Autopilot system.
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# =============================================================================
# Background Orchestration Task
# =============================================================================

def orchestrate_run(run_id: str):
    """Execute an autopilot run in a background thread.

    Loads the orchestration runtime, starts or resumes the run, and
    drives it to completion (or until an approval gate is reached).
    """
    from .orchestrator.runtime import OrchestrationRuntime
    from .repositories import AutopilotRunRepository

    try:
        session_factory = _get_session_factory()
        runtime = OrchestrationRuntime(session_factory)

        context = runtime.start_run(run_id)
        outcome, reason = runtime.execute_run(context)

        logger.info(
            "Run %s finished: outcome=%s reason=%s",
            run_id, outcome, reason,
        )
    except Exception as e:
        logger.error("orchestrate_run failed for %s: %s", run_id, e, exc_info=True)
        try:
            with _get_session_factory()() as session:
                repo = AutopilotRunRepository(session)
                repo.update_status(run_id, "failed", "FAILED", str(e))
                session.commit()
        except Exception:
            pass


def _get_session_factory():
    """Lazy import of the DB session factory."""
    from ..persistence.database import get_session_factory
    return get_session_factory()


# =============================================================================
# Request/Response Schemas
# =============================================================================

class IncidentCreateRequest(BaseModel):
    """Request to create a new incident"""
    tenant_id: str
    site_id: str
    asset_id: str
    fault_type: str
    severity: str = "medium"
    source: str = "external"
    start_ts: Optional[datetime] = None
    trigger_evidence: Dict[str, Any] = Field(default_factory=dict)
    point_values: Dict[str, float] = Field(default_factory=dict)


class IncidentResponse(BaseModel):
    """Incident response"""
    incident_id: str
    tenant_id: str
    site_id: str
    asset_id: str
    fault_type: str
    severity: str
    source: str
    status: str
    start_ts: datetime
    detected_at: datetime
    matched_playbook_id: Optional[str] = None
    match_reason: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    """List of incidents"""
    incidents: List[IncidentResponse]
    total: int


class RunCreateRequest(BaseModel):
    """Request to create a run from incident + playbook"""
    incident_id: str
    playbook_id: Optional[str] = None  # Auto-match if not provided


class RunResponse(BaseModel):
    """AutopilotRun response"""
    run_id: str
    incident_id: str
    playbook_id: str
    playbook_version: str
    tenant_id: str
    site_id: str
    asset_id: str
    status: str
    risk_tier: str
    current_step_index: int
    pending_approval_id: Optional[str] = None
    outcome: Optional[str] = None
    outcome_reason: Optional[str] = None
    plan_rationale: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class RunListResponse(BaseModel):
    """List of runs"""
    runs: List[RunResponse]
    total: int


class ApprovalTaskResponse(BaseModel):
    """Approval task for operator view"""
    approval_id: str
    run_id: str
    step_id: Optional[str] = None
    tenant_id: str
    approval_type: str
    risk_tier: str
    status: str
    proposed_actions: List[Dict[str, Any]]
    rationale: Optional[str] = None
    evidence_snapshot: Dict[str, Any]
    created_at: datetime
    expires_at: Optional[datetime] = None


class ApprovalListResponse(BaseModel):
    """List of pending approvals"""
    approvals: List[ApprovalTaskResponse]
    total: int


class ApprovalDecisionRequest(BaseModel):
    """Request to decide on an approval"""
    decision: str  # approve, reject, edit
    decided_by: str
    decision_notes: str = ""
    edited_params: Dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionResponse(BaseModel):
    """Response after approval decision"""
    approval_id: str
    status: str
    decision: str
    run_status: str


class EvidencePackResponse(BaseModel):
    """Evidence pack summary"""
    pack_id: str
    run_id: str
    incident_id: str
    tenant_id: str
    site_id: str
    asset_id: str
    playbook_id: str
    outcome: str
    outcome_reason: Optional[str] = None
    created_at: datetime
    content_hash: Optional[str] = None


class PlaybookResponse(BaseModel):
    """Playbook summary"""
    playbook_id: str
    name: str
    asset_class: str
    fault_type: str
    risk_tier: str
    current_version: str
    is_active: bool
    created_at: datetime


class PlaybookListResponse(BaseModel):
    """List of playbooks"""
    playbooks: List[PlaybookResponse]
    total: int


# =============================================================================
# Dependency Injection
# =============================================================================

def get_session():
    """Get database session"""
    from ..persistence.database import get_session as db_get_session
    return db_get_session()


# =============================================================================
# Incidents Router
# =============================================================================

incidents_router = APIRouter()


@incidents_router.post("", response_model=IncidentResponse)
async def create_incident(request: IncidentCreateRequest):
    """
    Create a new incident.
    
    Incidents are deduplicated by (asset_id, fault_type, date).
    If a duplicate is found, returns the existing incident.
    """
    from .repositories import IncidentRepository
    import uuid
    
    try:
        with get_session() as session:
            repo = IncidentRepository(session)
            
            start_ts = request.start_ts or datetime.utcnow()
            
            # Check for duplicate
            existing = repo.find_duplicate(
                asset_id=request.asset_id,
                fault_type=request.fault_type,
                start_ts=start_ts,
            )
            if existing:
                return IncidentResponse(
                    incident_id=existing.incident_id,
                    tenant_id=existing.tenant_id,
                    site_id=existing.site_id,
                    asset_id=existing.asset_id,
                    fault_type=existing.fault_type,
                    severity=existing.severity,
                    source=existing.source,
                    status=existing.status,
                    start_ts=existing.start_ts,
                    detected_at=existing.detected_at,
                    matched_playbook_id=existing.matched_playbook_id,
                    match_reason=existing.match_reason,
                    created_at=existing.created_at,
                    updated_at=existing.updated_at,
                )
            
            # Create new incident
            incident_id = f"INC-{uuid.uuid4().hex[:12].upper()}"
            incident = repo.create(
                incident_id=incident_id,
                tenant_id=request.tenant_id,
                site_id=request.site_id,
                asset_id=request.asset_id,
                fault_type=request.fault_type,
                severity=request.severity,
                source=request.source,
                start_ts=start_ts,
                trigger_evidence=request.trigger_evidence,
                point_values=request.point_values,
            )
            session.commit()
            
            return IncidentResponse(
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                site_id=incident.site_id,
                asset_id=incident.asset_id,
                fault_type=incident.fault_type,
                severity=incident.severity,
                source=incident.source,
                status=incident.status,
                start_ts=incident.start_ts,
                detected_at=incident.detected_at,
                matched_playbook_id=incident.matched_playbook_id,
                match_reason=incident.match_reason,
                created_at=incident.created_at,
                updated_at=incident.updated_at,
            )
    except Exception as e:
        logger.error(f"Error creating incident: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@incidents_router.get("/{incident_id}", response_model=IncidentResponse)
async def get_incident(incident_id: str):
    """Get incident by ID"""
    from .repositories import IncidentRepository
    
    try:
        with get_session() as session:
            repo = IncidentRepository(session)
            incident = repo.get_by_id(incident_id)
            
            if not incident:
                raise HTTPException(status_code=404, detail="Incident not found")
            
            return IncidentResponse(
                incident_id=incident.incident_id,
                tenant_id=incident.tenant_id,
                site_id=incident.site_id,
                asset_id=incident.asset_id,
                fault_type=incident.fault_type,
                severity=incident.severity,
                source=incident.source,
                status=incident.status,
                start_ts=incident.start_ts,
                detected_at=incident.detected_at,
                matched_playbook_id=incident.matched_playbook_id,
                match_reason=incident.match_reason,
                created_at=incident.created_at,
                updated_at=incident.updated_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting incident: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@incidents_router.get("", response_model=IncidentListResponse)
async def list_incidents(
    tenant_id: Optional[str] = None,
    site_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """List incidents with optional filtering"""
    from .repositories import IncidentRepository
    
    try:
        with get_session() as session:
            repo = IncidentRepository(session)
            incidents = repo.list_open(
                tenant_id=tenant_id,
                site_id=site_id,
                asset_id=asset_id,
                limit=limit,
            )
            
            return IncidentListResponse(
                incidents=[
                    IncidentResponse(
                        incident_id=i.incident_id,
                        tenant_id=i.tenant_id,
                        site_id=i.site_id,
                        asset_id=i.asset_id,
                        fault_type=i.fault_type,
                        severity=i.severity,
                        source=i.source,
                        status=i.status,
                        start_ts=i.start_ts,
                        detected_at=i.detected_at,
                        matched_playbook_id=i.matched_playbook_id,
                        match_reason=i.match_reason,
                        created_at=i.created_at,
                        updated_at=i.updated_at,
                    )
                    for i in incidents
                ],
                total=len(incidents),
            )
    except Exception as e:
        logger.error(f"Error listing incidents: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Runs Router
# =============================================================================

runs_router = APIRouter()


@runs_router.post("", response_model=RunResponse)
async def create_run(request: RunCreateRequest, background_tasks: BackgroundTasks):
    """
    Create a new AutopilotRun from an incident.
    
    If playbook_id is not provided, the system will attempt to match
    a playbook based on asset class and fault type.
    """
    from .repositories import IncidentRepository, AutopilotRunRepository, PlaybookRepository
    import uuid
    
    try:
        with get_session() as session:
            incident_repo = IncidentRepository(session)
            run_repo = AutopilotRunRepository(session)
            playbook_repo = PlaybookRepository(session)
            
            # Get incident
            incident = incident_repo.get_by_id(request.incident_id)
            if not incident:
                raise HTTPException(status_code=404, detail="Incident not found")
            
            # Match playbook if not provided
            playbook_id = request.playbook_id
            match_reason = ""
            
            if not playbook_id:
                # Auto-match based on fault type
                playbooks = playbook_repo.list_active(fault_type=incident.fault_type)
                if playbooks:
                    playbook = playbooks[0]
                    playbook_id = playbook.playbook_id
                    match_reason = f"Auto-matched by fault_type={incident.fault_type}"
                else:
                    raise HTTPException(
                        status_code=400,
                        detail=f"No playbook found for fault_type={incident.fault_type}"
                    )
            
            # Get playbook details
            playbook = playbook_repo.get_by_id(playbook_id)
            if not playbook:
                raise HTTPException(status_code=404, detail="Playbook not found")
            
            # Update incident with matched playbook
            incident_repo.set_matched_playbook(
                incident_id=incident.incident_id,
                playbook_id=playbook_id,
                match_reason=match_reason or "Explicitly specified",
            )
            
            # Create run
            run_id = f"RUN-{uuid.uuid4().hex[:12].upper()}"
            thread_id = str(uuid.uuid4())
            
            run = run_repo.create(
                run_id=run_id,
                incident_id=incident.incident_id,
                playbook_id=playbook_id,
                playbook_version=playbook.current_version,
                tenant_id=incident.tenant_id,
                site_id=incident.site_id,
                asset_id=incident.asset_id,
                thread_id=thread_id,
                risk_tier=playbook.risk_tier,
                plan_rationale=f"Created run for incident {incident.incident_id} using playbook {playbook_id}",
            )
            
            # Update incident status
            incident_repo.update_status(incident.incident_id, "run_started")
            
            session.commit()
            
            return RunResponse(
                run_id=run.run_id,
                incident_id=run.incident_id,
                playbook_id=run.playbook_id,
                playbook_version=run.playbook_version,
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                asset_id=run.asset_id,
                status=run.status,
                risk_tier=run.risk_tier,
                current_step_index=run.current_step_index,
                pending_approval_id=run.pending_approval_id,
                outcome=run.outcome,
                outcome_reason=run.outcome_reason,
                plan_rationale=run.plan_rationale,
                created_at=run.created_at,
                updated_at=run.updated_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str):
    """Get run by ID"""
    from .repositories import AutopilotRunRepository
    
    try:
        with get_session() as session:
            repo = AutopilotRunRepository(session)
            run = repo.get_by_id(run_id)
            
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            
            return RunResponse(
                run_id=run.run_id,
                incident_id=run.incident_id,
                playbook_id=run.playbook_id,
                playbook_version=run.playbook_version,
                tenant_id=run.tenant_id,
                site_id=run.site_id,
                asset_id=run.asset_id,
                status=run.status,
                risk_tier=run.risk_tier,
                current_step_index=run.current_step_index,
                pending_approval_id=run.pending_approval_id,
                outcome=run.outcome,
                outcome_reason=run.outcome_reason,
                plan_rationale=run.plan_rationale,
                created_at=run.created_at,
                updated_at=run.updated_at,
                started_at=run.started_at,
                completed_at=run.completed_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.get("", response_model=RunListResponse)
async def list_runs(
    tenant_id: Optional[str] = None,
    site_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(100, ge=1, le=500),
):
    """List runs with optional filtering"""
    from .repositories import AutopilotRunRepository
    
    try:
        with get_session() as session:
            repo = AutopilotRunRepository(session)
            runs = repo.list_active(
                tenant_id=tenant_id,
                site_id=site_id,
                asset_id=asset_id,
                limit=limit,
            )
            
            return RunListResponse(
                runs=[
                    RunResponse(
                        run_id=r.run_id,
                        incident_id=r.incident_id,
                        playbook_id=r.playbook_id,
                        playbook_version=r.playbook_version,
                        tenant_id=r.tenant_id,
                        site_id=r.site_id,
                        asset_id=r.asset_id,
                        status=r.status,
                        risk_tier=r.risk_tier,
                        current_step_index=r.current_step_index,
                        pending_approval_id=r.pending_approval_id,
                        outcome=r.outcome,
                        outcome_reason=r.outcome_reason,
                        plan_rationale=r.plan_rationale,
                        created_at=r.created_at,
                        updated_at=r.updated_at,
                        started_at=r.started_at,
                        completed_at=r.completed_at,
                    )
                    for r in runs
                ],
                total=len(runs),
            )
    except Exception as e:
        logger.error(f"Error listing runs: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.post("/{run_id}/execute")
async def execute_run(run_id: str, background_tasks: BackgroundTasks):
    """
    Start executing a run.
    
    This triggers the orchestration thread which will:
    1. Load the playbook
    2. Execute steps in order
    3. Pause for approvals as needed
    4. Run verifications
    5. Generate evidence pack
    """
    from .repositories import AutopilotRunRepository
    
    try:
        with get_session() as session:
            repo = AutopilotRunRepository(session)
            run = repo.get_by_id(run_id)
            
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            
            if run.status not in ["planning", "approved"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot execute run in status {run.status}"
                )
            
            repo.update_status(run_id, "executing")
            session.commit()
            
            background_tasks.add_task(orchestrate_run, run_id)
            
            return {"status": "executing", "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.post("/{run_id}/cancel")
async def cancel_run(run_id: str):
    """Cancel a run"""
    from .repositories import AutopilotRunRepository
    
    try:
        with get_session() as session:
            repo = AutopilotRunRepository(session)
            run = repo.get_by_id(run_id)
            
            if not run:
                raise HTTPException(status_code=404, detail="Run not found")
            
            if run.status in ["completed", "failed", "cancelled"]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot cancel run in status {run.status}"
                )
            
            repo.update_status(run_id, "cancelled", outcome="CANCELLED", outcome_reason="User cancelled")
            session.commit()
            
            return {"status": "cancelled", "run_id": run_id}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling run: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@runs_router.get("/{run_id}/evidence", response_model=EvidencePackResponse)
async def get_run_evidence(run_id: str):
    """Get evidence pack for a run"""
    from .models import EvidencePackModel
    
    try:
        with get_session() as session:
            pack = session.query(EvidencePackModel).filter(
                EvidencePackModel.run_id == run_id
            ).first()
            
            if not pack:
                raise HTTPException(status_code=404, detail="Evidence pack not found")
            
            return EvidencePackResponse(
                pack_id=pack.pack_id,
                run_id=pack.run_id,
                incident_id=pack.incident_id,
                tenant_id=pack.tenant_id,
                site_id=pack.site_id,
                asset_id=pack.asset_id,
                playbook_id=pack.playbook_id,
                outcome=pack.outcome,
                outcome_reason=pack.outcome_reason,
                created_at=pack.created_at,
                content_hash=pack.content_hash,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting evidence: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Approvals Router
# =============================================================================

approvals_router = APIRouter()


@approvals_router.get("", response_model=ApprovalListResponse)
async def list_approvals(
    tenant_id: Optional[str] = None,
    status: str = Query("pending"),
    limit: int = Query(100, ge=1, le=500),
):
    """List pending approvals"""
    from .repositories import ApprovalRepository
    
    try:
        with get_session() as session:
            repo = ApprovalRepository(session)
            approvals = repo.list_pending(tenant_id=tenant_id, limit=limit)
            
            return ApprovalListResponse(
                approvals=[
                    ApprovalTaskResponse(
                        approval_id=a.approval_id,
                        run_id=a.run_id,
                        step_id=a.step_id,
                        tenant_id=a.tenant_id,
                        approval_type=a.approval_type,
                        risk_tier=a.risk_tier,
                        status=a.status,
                        proposed_actions=a.proposed_actions,
                        rationale=a.rationale,
                        evidence_snapshot=a.evidence_snapshot,
                        created_at=a.created_at,
                        expires_at=a.expires_at,
                    )
                    for a in approvals
                ],
                total=len(approvals),
            )
    except Exception as e:
        logger.error(f"Error listing approvals: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@approvals_router.post("/{approval_id}/decision", response_model=ApprovalDecisionResponse)
async def decide_approval(approval_id: str, request: ApprovalDecisionRequest):
    """
    Submit a decision on an approval.
    
    Decisions:
    - approve: Proceed with proposed actions
    - reject: Cancel the run and escalate
    - edit: Modify parameters and proceed
    """
    from .repositories import ApprovalRepository, AutopilotRunRepository
    
    try:
        with get_session() as session:
            approval_repo = ApprovalRepository(session)
            run_repo = AutopilotRunRepository(session)
            
            approval = approval_repo.get_by_id(approval_id)
            if not approval:
                raise HTTPException(status_code=404, detail="Approval not found")
            
            if approval.status != "pending":
                raise HTTPException(
                    status_code=400,
                    detail=f"Approval already decided: {approval.status}"
                )
            
            # Record decision
            approval_repo.decide(
                approval_id=approval_id,
                decision=request.decision,
                decided_by=request.decided_by,
                decision_notes=request.decision_notes,
                edited_params=request.edited_params if request.decision == "edit" else None,
            )
            
            # Update run status based on decision
            run = run_repo.get_by_id(approval.run_id)
            if run:
                run_repo.clear_pending_approval(run.run_id)
                
                if request.decision == "approve" or request.decision == "edit":
                    run_repo.update_status(run.run_id, "approved")
                    run_status = "approved"
                elif request.decision == "reject":
                    run_repo.update_status(
                        run.run_id, 
                        "rejected", 
                        outcome="REJECTED",
                        outcome_reason=f"Rejected by {request.decided_by}: {request.decision_notes}"
                    )
                    run_status = "rejected"
                else:
                    run_status = run.status
            else:
                run_status = "unknown"
            
            session.commit()
            
            return ApprovalDecisionResponse(
                approval_id=approval_id,
                status=approval.status,
                decision=request.decision,
                run_status=run_status,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deciding approval: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# Playbooks Router
# =============================================================================

playbooks_router = APIRouter()


@playbooks_router.get("", response_model=PlaybookListResponse)
async def list_playbooks(
    asset_class: Optional[str] = None,
    fault_type: Optional[str] = None,
    risk_tier: Optional[str] = None,
):
    """List playbooks with optional filtering"""
    from .repositories import PlaybookRepository
    
    try:
        with get_session() as session:
            repo = PlaybookRepository(session)
            playbooks = repo.list_active(
                asset_class=asset_class,
                fault_type=fault_type,
                risk_tier=risk_tier,
            )
            
            return PlaybookListResponse(
                playbooks=[
                    PlaybookResponse(
                        playbook_id=p.playbook_id,
                        name=p.name,
                        asset_class=p.asset_class,
                        fault_type=p.fault_type,
                        risk_tier=p.risk_tier,
                        current_version=p.current_version,
                        is_active=p.is_active,
                        created_at=p.created_at,
                    )
                    for p in playbooks
                ],
                total=len(playbooks),
            )
    except Exception as e:
        logger.error(f"Error listing playbooks: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@playbooks_router.get("/{playbook_id}", response_model=PlaybookResponse)
async def get_playbook(playbook_id: str):
    """Get playbook by ID"""
    from .repositories import PlaybookRepository
    
    try:
        with get_session() as session:
            repo = PlaybookRepository(session)
            playbook = repo.get_by_id(playbook_id)
            
            if not playbook:
                raise HTTPException(status_code=404, detail="Playbook not found")
            
            return PlaybookResponse(
                playbook_id=playbook.playbook_id,
                name=playbook.name,
                asset_class=playbook.asset_class,
                fault_type=playbook.fault_type,
                risk_tier=playbook.risk_tier,
                current_version=playbook.current_version,
                is_active=playbook.is_active,
                created_at=playbook.created_at,
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting playbook: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
