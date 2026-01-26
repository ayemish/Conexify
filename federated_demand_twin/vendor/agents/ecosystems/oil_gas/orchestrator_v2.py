"""
Oil & Gas Four-Plane Architecture - Orchestration Plane

Case lifecycle state machine and multi-pattern orchestration.
Supports: Sequential, Concurrent, Handoff, Manager-led patterns.
"""

import logging
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from enum import Enum
import uuid
import asyncio
from concurrent.futures import ThreadPoolExecutor

from ...crewai_base import AgentRegistry, AgentMessageBus

from .data_plane import (
    Case, CaseState, CasePriority, Alert, AlertClassification,
    EvidenceBundle, EvidenceStore, StreamProcessor, TelemetryPoint,
    ProcessedSignal, ActionRiskLevel, AutonomyLevel,
)

from .governance import PolicyEngine, AuditLogger, SitePolicy, ToolCategory

from .agent_plane import (
    SignalTriageAgent, CorrelationAgent, DiagnosticsAgent,
    RootCauseAnalystAgent, RemediationPlannerAgent,
)

from .agent_plane_extended import (
    ToolExecutorAgent, VerificationAgent, CustomerCommsAgent,
    GovernancePolicyAgent, LearningAgent,
)

logger = logging.getLogger(__name__)


class OrchestrationPattern(str, Enum):
    """Supported orchestration patterns"""
    SEQUENTIAL = "sequential"      # Pipeline: A → B → C
    CONCURRENT = "concurrent"      # Fan-out: A, B, C in parallel
    HANDOFF = "handoff"           # Specialist takeover
    MANAGER_LED = "manager_led"   # Dynamic planning/replanning


@dataclass
class ApprovalRequest:
    """Human-in-the-loop approval request"""
    request_id: str
    case_id: str
    step_description: str
    risk_level: ActionRiskLevel
    requested_at: datetime
    requested_by: str
    approved: Optional[bool] = None
    approved_by: Optional[str] = None
    approved_at: Optional[datetime] = None
    notes: str = ""


@dataclass 
class OrchestrationConfig:
    """Configuration for the orchestrator"""
    site_id: str
    site_name: str
    
    # Autonomy level
    autonomy_level: AutonomyLevel = AutonomyLevel.RECOMMEND_ONLY
    
    # Timeouts
    diagnosis_timeout_seconds: int = 300
    verification_wait_minutes: int = 30
    
    # Patterns enabled
    enable_concurrent_diagnostics: bool = True
    enable_auto_escalation: bool = True
    
    # Approval settings
    auto_approve_low_risk: bool = False
    escalation_threshold_minutes: int = 60


class CaseLifecycleManager:
    """
    Manages case state transitions through 9-state lifecycle:
    Intake → Triage → Diagnose → Plan → Authorize → Execute → Verify → Close → Learn
    """
    
    VALID_TRANSITIONS = {
        CaseState.INTAKE: [CaseState.TRIAGE],
        CaseState.TRIAGE: [CaseState.DIAGNOSE, CaseState.CLOSE],  # Can close if duplicate/noise
        CaseState.DIAGNOSE: [CaseState.PLAN, CaseState.TRIAGE],   # Can return for more triage
        CaseState.PLAN: [CaseState.AUTHORIZE, CaseState.DIAGNOSE],
        CaseState.AUTHORIZE: [CaseState.EXECUTE, CaseState.PLAN],  # Can replan if rejected
        CaseState.EXECUTE: [CaseState.VERIFY, CaseState.PLAN],     # Can replan if failed
        CaseState.VERIFY: [CaseState.CLOSE, CaseState.PLAN],       # Can replan if not verified
        CaseState.CLOSE: [CaseState.LEARN],
        CaseState.LEARN: [],  # Terminal state
    }
    
    def __init__(self, audit_logger: AuditLogger):
        self.audit_logger = audit_logger
    
    def can_transition(self, case: Case, target_state: CaseState) -> bool:
        """Check if transition is valid"""
        valid_targets = self.VALID_TRANSITIONS.get(case.state, [])
        return target_state in valid_targets
    
    def transition(self, case: Case, target_state: CaseState, actor: str, reason: str = "") -> bool:
        """Execute state transition"""
        if not self.can_transition(case, target_state):
            logger.warning(f"Invalid transition: {case.state} → {target_state}")
            return False
        
        case.transition_to(target_state, actor, reason)
        
        self.audit_logger.log(
            action_type="state_transition",
            actor_id=actor,
            case_id=case.case_id,
            parameters={"from": case.state_history[-1]["from"], "to": target_state.value},
        )
        
        return True


class FourPlaneOrchestrator:
    """
    Main orchestrator implementing the four-plane architecture.
    
    Data Plane: EvidenceStore, StreamProcessor
    Agent Plane: 10 specialized agents
    Orchestration Plane: This class - lifecycle management and patterns
    Execution Plane: ToolExecutor with governance controls
    """
    
    def __init__(self, config: OrchestrationConfig):
        self.config = config
        self.site_id = config.site_id
        
        # Initialize governance
        self.policy_engine = PolicyEngine()
        self.audit_logger = AuditLogger()
        
        # Set site policy
        self.policy_engine.set_site_policy(SitePolicy(
            site_id=config.site_id,
            customer_id=config.site_id,
            autonomy_level=config.autonomy_level,
        ))
        
        # Initialize data plane
        self.evidence_store = EvidenceStore()
        self.stream_processor = StreamProcessor()
        
        # Initialize case lifecycle
        self.lifecycle = CaseLifecycleManager(self.audit_logger)
        
        # Initialize agents
        self._init_agents()
        
        # State
        self.active_cases: Dict[str, Case] = {}
        self.pending_approvals: Dict[str, ApprovalRequest] = {}
        self.run_history: List[Dict] = []
        
        # Thread pool for concurrent operations
        self.executor = ThreadPoolExecutor(max_workers=4)
        
        logger.info(f"FourPlaneOrchestrator initialized for {config.site_name}")
    
    def _init_agents(self):
        """Initialize all 10 agents"""
        pe = self.policy_engine
        al = self.audit_logger
        bus = AgentMessageBus()
        
        # Core agents
        self.triage_agent = SignalTriageAgent(self.site_id, pe, al, bus)
        self.correlation_agent = CorrelationAgent(self.site_id, pe, al, bus)
        self.diagnostics_agent = DiagnosticsAgent(self.site_id, pe, al, bus)
        self.rca_agent = RootCauseAnalystAgent(self.site_id, pe, al, bus)
        self.planner_agent = RemediationPlannerAgent(self.site_id, pe, al, bus)
        
        # Execution agents
        self.executor_agent = ToolExecutorAgent(self.site_id, pe, al, bus)
        self.verification_agent = VerificationAgent(self.site_id, pe, al, bus)
        self.comms_agent = CustomerCommsAgent(self.site_id, pe, al, bus)
        self.governance_agent = GovernancePolicyAgent(self.site_id, pe, al, bus)
        self.learning_agent = LearningAgent(self.site_id, pe, al, bus)
        
        logger.info("Initialized 10 specialized agents")
    
    # =========================================================================
    # Main Entry Point
    # =========================================================================
    
    def process_telemetry(self, telemetry: List[TelemetryPoint]) -> List[Case]:
        """
        Main entry point: Process incoming telemetry through the full pipeline.
        Returns list of cases that were created or updated.
        """
        run_id = str(uuid.uuid4())[:12]
        logger.info(f"Run {run_id}: Processing {len(telemetry)} telemetry points")
        
        # Data Plane: Ingest and process
        self.evidence_store.ingest_telemetry(telemetry)
        signals = self.stream_processor.process_batch(telemetry)
        
        # Generate alerts from threshold breaches
        alerts = self._generate_alerts(signals)
        
        if not alerts:
            logger.info(f"Run {run_id}: No alerts generated")
            return []
        
        # Agent Plane: Triage
        cases = self.triage_agent.process_alerts(alerts)
        
        # Process each case through lifecycle
        for case in cases:
            self._process_case(case, signals)
            self.active_cases[case.case_id] = case
        
        self.run_history.append({
            "run_id": run_id,
            "timestamp": datetime.utcnow().isoformat(),
            "telemetry_count": len(telemetry),
            "alerts_generated": len(alerts),
            "cases_affected": len(cases),
        })
        
        return cases
    
    def _generate_alerts(self, signals: List[ProcessedSignal]) -> List[Alert]:
        """Generate alerts from processed signals"""
        alerts = []
        for signal in signals:
            if signal.threshold_breach or signal.anomaly_score > 3.0:
                alert = Alert(
                    alert_id=str(uuid.uuid4())[:12],
                    source_system="stream_processor",
                    device_id=signal.original.sensor_id.rsplit("_", 1)[0],  # Extract device from sensor
                    site_id=self.site_id,
                    alert_type="anomaly" if signal.anomaly_score > 3.0 else "threshold",
                    severity="high" if signal.anomaly_score > 4.0 else "medium",
                    message=f"Anomaly detected: score={signal.anomaly_score:.2f}",
                    current_value=signal.original.value,
                    triggered_at=datetime.utcnow(),
                )
                alerts.append(alert)
        return alerts
    
    # =========================================================================
    # Case Processing Pipeline
    # =========================================================================
    
    def _process_case(self, case: Case, signals: List[ProcessedSignal]):
        """Process a case through its lifecycle based on current state"""
        
        # State: INTAKE → TRIAGE
        if case.state == CaseState.INTAKE:
            self.lifecycle.transition(case, CaseState.TRIAGE, "orchestrator", "Initial triage")
        
        # State: TRIAGE → DIAGNOSE
        if case.state == CaseState.TRIAGE:
            # Build evidence bundle
            sensor_ids = list(set(s.original.sensor_id for s in signals))
            device_ids = list(set(a.device_id for a in case.source_alerts))
            case.evidence_bundle = self.evidence_store.create_evidence_bundle(
                case.case_id, sensor_ids, device_ids
            )
            self.lifecycle.transition(case, CaseState.DIAGNOSE, "orchestrator", "Evidence gathered")
        
        # State: DIAGNOSE (concurrent pattern)
        if case.state == CaseState.DIAGNOSE:
            self._run_diagnosis(case, signals)
            self.lifecycle.transition(case, CaseState.PLAN, "orchestrator", "Diagnosis complete")
        
        # State: PLAN
        if case.state == CaseState.PLAN:
            self.planner_agent.create_plan(case, case.hypotheses)
            self.lifecycle.transition(case, CaseState.AUTHORIZE, "orchestrator", "Plan created")
        
        # State: AUTHORIZE (human-in-the-loop)
        if case.state == CaseState.AUTHORIZE:
            authorized = self._handle_authorization(case)
            if authorized:
                self.lifecycle.transition(case, CaseState.EXECUTE, "orchestrator", "Plan authorized")
            # If not authorized, stays in AUTHORIZE waiting for approval
        
        # State: EXECUTE
        if case.state == CaseState.EXECUTE:
            self._execute_plan(case)
            self.lifecycle.transition(case, CaseState.VERIFY, "orchestrator", "Execution complete")
        
        # Note: VERIFY, CLOSE, LEARN handled separately or asynchronously
    
    def _run_diagnosis(self, case: Case, signals: List[ProcessedSignal]):
        """Run diagnosis phase - concurrent pattern if enabled"""
        
        if self.config.enable_concurrent_diagnostics:
            # Concurrent: Run diagnostics, correlation, and RCA in parallel
            futures = []
            
            # Submit concurrent tasks
            diag_future = self.executor.submit(
                self.diagnostics_agent.run_diagnostics, case, signals
            )
            futures.append(("diagnostics", diag_future))
            
            corr_future = self.executor.submit(
                self.correlation_agent.correlate_case, case, list(self.active_cases.values())
            )
            futures.append(("correlation", corr_future))
            
            # Collect results
            diagnostics = {}
            correlations = {}
            
            for name, future in futures:
                try:
                    result = future.result(timeout=self.config.diagnosis_timeout_seconds)
                    if name == "diagnostics":
                        diagnostics = result
                    else:
                        correlations = result
                except Exception as e:
                    logger.error(f"Concurrent {name} failed: {e}")
            
            # Run RCA with collected results
            self.rca_agent.analyze(case, diagnostics, correlations)
        else:
            # Sequential pattern
            diagnostics = self.diagnostics_agent.run_diagnostics(case, signals)
            correlations = self.correlation_agent.correlate_case(case, list(self.active_cases.values()))
            self.rca_agent.analyze(case, diagnostics, correlations)
    
    def _handle_authorization(self, case: Case) -> bool:
        """Handle plan authorization based on autonomy level and risk"""
        if not case.remediation_plan:
            return False
        
        plan = case.remediation_plan
        
        # Check autonomy level
        autonomy = self.config.autonomy_level
        
        if autonomy == AutonomyLevel.OBSERVE_ONLY:
            logger.info(f"Case {case.case_id}: Observe-only mode, no execution")
            return False
        
        if autonomy == AutonomyLevel.RECOMMEND_ONLY:
            # Generate recommendation but don't execute
            draft = self.comms_agent.draft_status_update(case)
            logger.info(f"Case {case.case_id}: Recommendation generated")
            plan.approved = False
            return False
        
        # Check if auto-approval is possible
        if autonomy in [AutonomyLevel.AUTO_LOW_RISK, AutonomyLevel.AUTO_MEDIUM_RISK, AutonomyLevel.FULL_AUTONOMY]:
            # Check plan risk level
            if plan.overall_risk == ActionRiskLevel.SAFE:
                plan.approved = True
                return True
            
            if plan.overall_risk == ActionRiskLevel.LOW and autonomy != AutonomyLevel.AUTO_LOW_RISK:
                plan.approved = True
                return True
            
            if plan.overall_risk == ActionRiskLevel.MEDIUM and autonomy in [AutonomyLevel.AUTO_MEDIUM_RISK, AutonomyLevel.FULL_AUTONOMY]:
                plan.approved = True
                return True
            
            if autonomy == AutonomyLevel.FULL_AUTONOMY:
                plan.approved = True
                return True
        
        # Need human approval
        self._create_approval_request(case)
        return False
    
    def _create_approval_request(self, case: Case):
        """Create human-in-the-loop approval request"""
        if not case.remediation_plan:
            return
        
        request = ApprovalRequest(
            request_id=str(uuid.uuid4())[:12],
            case_id=case.case_id,
            step_description=f"Approve {len(case.remediation_plan.steps)}-step remediation plan",
            risk_level=case.remediation_plan.overall_risk,
            requested_at=datetime.utcnow(),
            requested_by="orchestrator",
        )
        
        self.pending_approvals[request.request_id] = request
        
        case.add_timeline_entry(
            "approval_requested",
            f"Awaiting approval for {case.remediation_plan.overall_risk.value} risk plan",
            "orchestrator",
            {"approval_id": request.request_id},
        )
        
        logger.info(f"Case {case.case_id}: Approval request created: {request.request_id}")
    
    def _execute_plan(self, case: Case):
        """Execute remediation plan steps"""
        if not case.remediation_plan or not case.remediation_plan.approved:
            return
        
        plan = case.remediation_plan
        
        for step in plan.steps:
            if step.executed:
                continue
            
            # Check governance
            allowed, reason = self.governance_agent.check_permission(
                step, case, "executor_agent", "operator"
            )
            
            if not allowed:
                logger.warning(f"Step {step.sequence} blocked: {reason}")
                if "Approval required" in reason:
                    break  # Wait for approval
                continue
            
            # Execute step
            success, result, msg = self.executor_agent.execute_step(step, case)
            
            if not success:
                logger.error(f"Step {step.sequence} failed: {msg}")
                # Don't continue if step failed
                break
        
        plan.completed = all(s.executed for s in plan.steps)
    
    # =========================================================================
    # Human-in-the-Loop Interface
    # =========================================================================
    
    def approve_request(self, request_id: str, approved: bool, approver: str, notes: str = "") -> bool:
        """Process human approval decision"""
        if request_id not in self.pending_approvals:
            return False
        
        request = self.pending_approvals[request_id]
        request.approved = approved
        request.approved_by = approver
        request.approved_at = datetime.utcnow()
        request.notes = notes
        
        # Update case
        case = self.active_cases.get(request.case_id)
        if case and case.remediation_plan:
            if approved:
                case.remediation_plan.approved = True
                case.add_timeline_entry("approved", f"Plan approved by {approver}", approver)
                # Continue processing
                if case.state == CaseState.AUTHORIZE:
                    self.lifecycle.transition(case, CaseState.EXECUTE, approver, "Approved")
                    self._execute_plan(case)
            else:
                case.add_timeline_entry("rejected", f"Plan rejected by {approver}: {notes}", approver)
        
        self.audit_logger.log(
            action_type="approval_processed",
            actor_id=approver,
            actor_type="human",
            case_id=request.case_id,
            parameters={"approved": approved, "notes": notes},
        )
        
        return True
    
    def get_pending_approvals(self) -> List[ApprovalRequest]:
        """Get all pending approval requests"""
        return [r for r in self.pending_approvals.values() if r.approved is None]
    
    # =========================================================================
    # Verification and Closure
    # =========================================================================
    
    def verify_and_close(self, case_id: str, post_signals: List[ProcessedSignal]) -> Dict[str, Any]:
        """Verify remediation and close case"""
        case = self.active_cases.get(case_id)
        if not case:
            return {"error": "Case not found"}
        
        if case.state != CaseState.VERIFY:
            return {"error": f"Case not in VERIFY state (current: {case.state.value})"}
        
        # Get pre-action signals from evidence bundle
        pre_signals = []
        if case.evidence_bundle:
            pre_signals = [
                ProcessedSignal(
                    original=t, normalized_value=t.value, unit_harmonized=t.unit
                )
                for t in case.evidence_bundle.telemetry_window
            ]
        
        # Run verification
        verification = self.verification_agent.verify_remediation(case, pre_signals, post_signals)
        
        if verification.get("effective"):
            # Close case
            case.resolved = True
            case.resolution_time = datetime.utcnow()
            case.resolution_summary = verification.get("recommendation", "Remediation successful")
            
            self.lifecycle.transition(case, CaseState.CLOSE, "orchestrator", "Verified effective")
            
            # Send closure notice
            closure = self.comms_agent.draft_closure_notice(case)
            
            # Learn from case
            self.lifecycle.transition(case, CaseState.LEARN, "orchestrator", "Learning phase")
            learnings = self.learning_agent.process_closed_case(case, verification)
            
            return {
                "status": "closed",
                "verification": verification,
                "closure_notice": closure,
                "learnings": learnings,
            }
        else:
            # May need to replan
            case.add_timeline_entry(
                "verification_failed",
                f"Remediation not effective: {verification.get('recommendation')}",
                "orchestrator",
            )
            
            # Option: return to PLAN state
            self.lifecycle.transition(case, CaseState.PLAN, "orchestrator", "Replanning needed")
            
            return {
                "status": "replan_needed",
                "verification": verification,
            }
    
    # =========================================================================
    # Escalation
    # =========================================================================
    
    def check_escalations(self):
        """Check for cases that need escalation"""
        now = datetime.utcnow()
        
        for case in self.active_cases.values():
            if case.resolved:
                continue
            
            # Check SLA breach
            if case.sla_deadline and now > case.sla_deadline and not case.sla_breached:
                case.sla_breached = True
                self._escalate_case(case, "SLA deadline exceeded")
            
            # Check stuck cases
            if case.state_history:
                last_transition = datetime.fromisoformat(case.state_history[-1]["timestamp"])
                stuck_minutes = (now - last_transition).total_seconds() / 60
                
                if stuck_minutes > self.config.escalation_threshold_minutes:
                    if case.state in [CaseState.AUTHORIZE, CaseState.EXECUTE]:
                        self._escalate_case(case, f"Case stuck in {case.state.value} for {int(stuck_minutes)} minutes")
    
    def _escalate_case(self, case: Case, reason: str):
        """Escalate a case"""
        escalation = self.comms_agent.draft_escalation(case, reason, "supervisor")
        case.escalated_to = "supervisor"
        case.add_timeline_entry("escalated", reason, "orchestrator")
        
        self.audit_logger.log(
            action_type="escalation",
            actor_id="orchestrator",
            case_id=case.case_id,
            parameters={"reason": reason},
        )
        
        logger.warning(f"Case {case.case_id} escalated: {reason}")
    
    # =========================================================================
    # Reporting
    # =========================================================================
    
    def get_case_summary(self, case_id: str) -> Dict[str, Any]:
        """Get summary of a case"""
        case = self.active_cases.get(case_id)
        if not case:
            return {"error": "Case not found"}
        
        return {
            "case_id": case.case_id,
            "state": case.state.value,
            "priority": case.priority.value,
            "classification": case.classification.value if case.classification else None,
            "created_at": case.created_at.isoformat(),
            "resolved": case.resolved,
            "sla_breached": case.sla_breached,
            "alerts": len(case.source_alerts),
            "hypotheses": len(case.hypotheses),
            "root_cause": case.root_cause.description if case.root_cause else None,
            "plan_steps": len(case.remediation_plan.steps) if case.remediation_plan else 0,
            "timeline_entries": len(case.timeline),
        }
    
    def get_orchestrator_status(self) -> Dict[str, Any]:
        """Get overall orchestrator status"""
        active = [c for c in self.active_cases.values() if not c.resolved]
        resolved = [c for c in self.active_cases.values() if c.resolved]
        
        return {
            "site_id": self.site_id,
            "autonomy_level": self.config.autonomy_level.value,
            "active_cases": len(active),
            "resolved_cases": len(resolved),
            "pending_approvals": len(self.get_pending_approvals()),
            "cases_by_state": {
                state.value: len([c for c in active if c.state == state])
                for state in CaseState
            },
            "cases_by_priority": {
                p.value: len([c for c in active if c.priority == p])
                for p in CasePriority
            },
            "agents": [
                "SignalTriage", "Correlation", "Diagnostics", "RootCauseAnalyst",
                "RemediationPlanner", "ToolExecutor", "Verification",
                "CustomerComms", "GovernancePolicy", "Learning",
            ],
        }
