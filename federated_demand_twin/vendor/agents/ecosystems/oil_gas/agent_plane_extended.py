"""
Oil & Gas Four-Plane Architecture - Agent Plane (Part 2)

Execution agents: ToolExecutor, Verification, CustomerComms, GovernancePolicy, Learning
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timedelta
import logging
import uuid

from .agent_plane import FourPlaneAgent
from .data_plane import (
    Case, CaseState, CasePriority, ActionStep, ActionRiskLevel, ProcessedSignal,
)
from .governance import PolicyEngine, AuditLogger

from ...crewai_base import (
    CrewAIAgentConfig, AgentCategory, AgentRole, AgentMessageBus,
)

logger = logging.getLogger(__name__)


class ToolExecutorAgent(FourPlaneAgent):
    """Performs approved tool calls using strict schemas. Only agent that executes external actions."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"executor-{site_id}", role=AgentRole.COMPLIANCE_CHECKER,
            category=AgentCategory.GOVERNANCE, name="Tool Executor",
            goal="Execute approved actions safely with full audit trails",
            backstory="Executor of approved actions with strict validation.",
            retailer_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.rate_limits: Dict[str, List[datetime]] = {}
    
    def execute_step(self, step: ActionStep, case: Case, role_id: str = "operator") -> Tuple[bool, Dict, str]:
        """Execute a plan step if approved and within policy."""
        if step.requires_approval and not step.approved_by:
            return False, {}, "Step requires approval before execution"
        
        if not self._check_rate_limit(step.tool_name):
            return False, {}, f"Rate limit exceeded for {step.tool_name}"
        
        success, result, msg = self.execute_tool(step.tool_name, step.tool_params, case, role_id)
        
        if success:
            step.executed = True
            step.executed_at = datetime.utcnow()
            step.execution_result = result
        
        case.add_timeline_entry(
            "step_executed" if success else "step_failed",
            f"Step {step.sequence}: {step.description} - {'OK' if success else msg}",
            self.config.agent_id,
        )
        return success, result, msg
    
    def _check_rate_limit(self, tool_id: str) -> bool:
        if not tool_id:
            return True
        tool = self.tools.get(tool_id)
        if not tool:
            return True
        
        now = datetime.utcnow()
        hour_ago = now - timedelta(hours=1)
        
        if tool_id not in self.rate_limits:
            self.rate_limits[tool_id] = []
        self.rate_limits[tool_id] = [t for t in self.rate_limits[tool_id] if t > hour_ago]
        
        if len(self.rate_limits[tool_id]) >= tool.max_calls_per_hour:
            return False
        self.rate_limits[tool_id].append(now)
        return True


class VerificationAgent(FourPlaneAgent):
    """Confirms remediation worked via post-action telemetry checks."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"verification-{site_id}", role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE, name="Verification Agent",
            goal="Verify remediation effectiveness through data analysis",
            backstory="Verifies actions achieved intended effect via telemetry.",
            retailer_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
    
    def verify_remediation(self, case: Case, pre_signals: List[ProcessedSignal],
                          post_signals: List[ProcessedSignal]) -> Dict[str, Any]:
        """Verify remediation by comparing pre/post signals."""
        result = {
            "case_id": case.case_id, "verified_at": datetime.utcnow().isoformat(),
            "effective": False, "improved": [], "worsened": [], "confidence": 0.0,
        }
        
        pre_by_sensor = self._group(pre_signals)
        post_by_sensor = self._group(post_signals)
        
        for sensor_id in set(pre_by_sensor) | set(post_by_sensor):
            pre = pre_by_sensor.get(sensor_id, [])
            post = post_by_sensor.get(sensor_id, [])
            if not pre or not post:
                continue
            
            pre_score = np.mean([s.anomaly_score for s in pre])
            post_score = np.mean([s.anomaly_score for s in post])
            change = post_score - pre_score
            
            if change < -0.5:
                result["improved"].append({"sensor": sensor_id, "delta": -change})
            elif change > 0.5:
                result["worsened"].append({"sensor": sensor_id, "delta": change})
        
        n_improved = len(result["improved"])
        n_worsened = len(result["worsened"])
        
        if n_improved > 0 and n_worsened == 0:
            result["effective"] = True
            result["confidence"] = min(0.9, 0.5 + n_improved * 0.1)
            result["recommendation"] = "Remediation successful"
        elif n_worsened > n_improved:
            result["recommendation"] = "Consider rollback"
            result["confidence"] = 0.7
        else:
            result["effective"] = n_improved > n_worsened
            result["recommendation"] = "Continue monitoring"
            result["confidence"] = 0.5
        
        case.add_timeline_entry("verification", f"Effective: {result['effective']}", self.config.agent_id)
        return result
    
    def _group(self, signals: List[ProcessedSignal]) -> Dict[str, List]:
        grouped = {}
        for s in signals:
            sid = s.original.sensor_id
            grouped.setdefault(sid, []).append(s)
        return grouped


class CustomerCommsAgent(FourPlaneAgent):
    """Drafts updates, ETAs, and closure notes; routes for approval."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"comms-{site_id}", role=AgentRole.REPORT_WRITER,
            category=AgentCategory.COMMUNICATION, name="Customer Communications",
            goal="Draft clear, accurate communications for stakeholders",
            backstory="Crafts professional communications for stakeholders.",
            retailer_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
    
    def draft_status_update(self, case: Case) -> Dict[str, Any]:
        priority_text = {
            CasePriority.P1_CRITICAL: "Critical - immediate attention",
            CasePriority.P2_HIGH: "High priority - active investigation",
            CasePriority.P3_MEDIUM: "Being addressed",
            CasePriority.P4_LOW: "Scheduled for resolution",
        }
        
        msg = [f"**Status**: {case.state.value.title()}",
               f"**Priority**: {priority_text.get(case.priority, 'Under review')}"]
        
        if case.sla_deadline:
            remaining = case.sla_deadline - datetime.utcnow()
            if remaining.total_seconds() > 0:
                msg.append(f"**ETA**: {int(remaining.total_seconds()/3600)} hours")
        
        if case.remediation_plan:
            done = sum(1 for s in case.remediation_plan.steps if s.executed)
            msg.append(f"**Progress**: {done}/{len(case.remediation_plan.steps)} steps")
        
        return {
            "type": "status", "case_id": case.case_id,
            "subject": f"Status: Case {case.case_id}",
            "message": "\n".join(msg),
            "requires_approval": case.priority in [CasePriority.P1_CRITICAL, CasePriority.P2_HIGH],
        }
    
    def draft_closure_notice(self, case: Case) -> Dict[str, Any]:
        msg = ["Issue resolved.", f"**Summary**: {case.resolution_summary or 'Addressed successfully'}"]
        if case.root_cause:
            msg.append(f"**Root Cause**: {case.root_cause.description}")
        return {
            "type": "closure", "case_id": case.case_id,
            "subject": f"Resolved: Case {case.case_id}",
            "message": "\n".join(msg), "requires_approval": True,
        }
    
    def draft_escalation(self, case: Case, reason: str, to: str) -> Dict[str, Any]:
        return {
            "type": "escalation", "case_id": case.case_id,
            "subject": f"Escalation: {case.case_id}",
            "message": f"**Reason**: {reason}\n**To**: {to}\n**Priority**: {case.priority.value}",
            "requires_approval": False,
        }


class GovernancePolicyAgent(FourPlaneAgent):
    """Enforces RBAC, least-privilege, approval thresholds, audit logging."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"governance-{site_id}", role=AgentRole.COMPLIANCE_CHECKER,
            category=AgentCategory.GOVERNANCE, name="Governance & Policy",
            goal="Enforce security policies, RBAC, and audit requirements",
            backstory="Guardian of security and compliance.",
            retailer_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.pending_approvals: Dict[str, Dict] = {}
    
    def check_permission(self, step: ActionStep, case: Case, agent: str, role: str) -> Tuple[bool, str]:
        """Check if action is permitted given policies."""
        if step.tool_name:
            allowed, reason = self.policy_engine.can_execute_tool(
                step.tool_name, role, case.site_id, case.priority)
            if not allowed:
                self.audit_logger.log(
                    action_type="denied", actor_id=agent, tool_id=step.tool_name,
                    case_id=case.case_id, error=reason, success=False)
                return False, reason
        
        needs, reason = self.policy_engine.requires_approval(step.tool_name, case.site_id, case.priority)
        if needs and not step.approved_by:
            aid = self._create_approval(step, case, agent)
            return False, f"Approval required. ID: {aid}"
        return True, "Permitted"
    
    def _create_approval(self, step: ActionStep, case: Case, agent: str) -> str:
        aid = str(uuid.uuid4())[:12]
        self.pending_approvals[aid] = {
            "id": aid, "step": step.step_id, "case": case.case_id,
            "agent": agent, "action": step.description, "status": "pending",
            "created": datetime.utcnow().isoformat(),
        }
        self.audit_logger.log(action_type="approval_requested", actor_id=agent,
                             case_id=case.case_id, parameters={"approval_id": aid})
        return aid
    
    def process_approval(self, aid: str, approved: bool, approver: str) -> Tuple[bool, str]:
        if aid not in self.pending_approvals:
            return False, "Approval not found"
        req = self.pending_approvals[aid]
        req["status"] = "approved" if approved else "rejected"
        req["approver"] = approver
        req["processed_at"] = datetime.utcnow().isoformat()
        self.audit_logger.log(
            action_type="approval_processed", actor_id=approver,
            parameters={"approval_id": aid, "approved": approved})
        return True, f"Approval {'granted' if approved else 'denied'}"


class LearningAgent(FourPlaneAgent):
    """Harvests outcomes, labels incidents, updates runbooks and models."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"learning-{site_id}", role=AgentRole.RATIONALE_GENERATOR,
            category=AgentCategory.ANALYTICS, name="Learning Agent",
            goal="Extract lessons and improve system knowledge",
            backstory="Learns from outcomes to improve future responses.",
            retailer_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.incident_labels: List[Dict] = []
        self.runbook_updates: List[Dict] = []
    
    def process_closed_case(self, case: Case, verification: Dict) -> Dict[str, Any]:
        """Extract learnings from a closed case."""
        learnings = {
            "case_id": case.case_id, "processed_at": datetime.utcnow().isoformat(),
            "lessons": [], "runbook_updates": [], "model_feedback": {},
        }
        
        # Label the incident
        label = {
            "case_id": case.case_id,
            "classification": case.classification.value if case.classification else "unknown",
            "root_cause": case.root_cause.description if case.root_cause else "unknown",
            "resolution_effective": verification.get("effective", False),
            "time_to_resolve": None,
        }
        if case.resolution_time and case.created_at:
            label["time_to_resolve"] = (case.resolution_time - case.created_at).total_seconds()
        self.incident_labels.append(label)
        
        # Extract lessons
        if case.root_cause and verification.get("effective"):
            learnings["lessons"].append(
                f"For {case.classification.value if case.classification else 'issues'}: "
                f"{case.root_cause.description} - remediation effective"
            )
        
        if not verification.get("effective"):
            learnings["lessons"].append(
                f"Remediation for case {case.case_id} was not fully effective - review approach"
            )
        
        # Suggest runbook update
        if case.remediation_plan and verification.get("effective"):
            successful_steps = [s.description for s in case.remediation_plan.steps if s.executed]
            if successful_steps:
                update = {
                    "trigger": case.classification.value if case.classification else "general",
                    "steps": successful_steps,
                    "confidence": verification.get("confidence", 0.5),
                }
                self.runbook_updates.append(update)
                learnings["runbook_updates"].append(update)
        
        # Model feedback for federated learning
        if case.hypotheses:
            learnings["model_feedback"] = {
                "hypothesis_accuracy": [
                    {"hypothesis": h.description, "confidence": h.confidence, "validated": not h.invalidated}
                    for h in case.hypotheses[:3]
                ],
                "diagnostic_signatures_matched": len([h for h in case.hypotheses if h.confidence > 0.7]),
            }
        
        case.lessons_learned = learnings["lessons"]
        case.add_timeline_entry("learning_complete", f"Extracted {len(learnings['lessons'])} lessons", self.config.agent_id)
        
        return learnings
    
    def get_similar_cases(self, case: Case, limit: int = 5) -> List[Dict]:
        """Find similar historical cases for reference."""
        similar = []
        for label in self.incident_labels:
            if label["classification"] == (case.classification.value if case.classification else ""):
                similar.append(label)
        return sorted(similar, key=lambda x: x.get("time_to_resolve") or float('inf'))[:limit]
