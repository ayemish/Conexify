"""
Oil & Gas Four-Plane Architecture - Agent Plane (Part 1)

Core agents: SignalTriage, Correlation, Diagnostics, RootCauseAnalyst, RemediationPlanner
"""

import numpy as np
from typing import Dict, List, Optional, Any, Tuple, Set
from datetime import datetime, timedelta
from dataclasses import dataclass, field
import logging
import uuid

from shared.agents.crewai_base import (
    DemandTwinAgent,
    CrewAIAgentConfig,
    AgentCategory,
    AgentRole,
    AgentMessageBus,
)

from .data_plane import (
    Case, CaseState, CasePriority, AlertClassification, Alert,
    Hypothesis, RemediationPlan, ActionStep, ActionRiskLevel,
    EvidenceBundle, TelemetryPoint, ProcessedSignal,
)

from .governance import (
    ToolSchema, PolicyEngine, AuditLogger, OutputValidator, get_standard_tools,
)

logger = logging.getLogger(__name__)


class FourPlaneAgent(DemandTwinAgent):
    """Base class for agents in the four-plane architecture."""
    
    def __init__(
        self,
        config: CrewAIAgentConfig,
        policy_engine: PolicyEngine,
        audit_logger: AuditLogger,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        super().__init__(config, message_bus)
        self.policy_engine = policy_engine
        self.audit_logger = audit_logger
        self.output_validator = OutputValidator()
        self.tools = get_standard_tools()
    
    def execute_tool(
        self, tool_id: str, params: Dict[str, Any], case: Case, role_id: str = "operator",
    ) -> Tuple[bool, Dict[str, Any], str]:
        """Execute a tool with policy checks and audit logging."""
        start_time = datetime.utcnow()
        
        allowed, reason = self.policy_engine.can_execute_tool(
            tool_id, role_id, case.site_id, case.priority
        )
        if not allowed:
            self.audit_logger.log(
                action_type="tool_denied", actor_id=self.config.agent_id,
                tool_id=tool_id, site_id=case.site_id, case_id=case.case_id,
                error=reason, success=False,
            )
            return False, {}, reason
        
        tool = self.tools.get(tool_id)
        if tool:
            valid, errors = tool.validate_params(params)
            if not valid:
                return False, {}, f"Validation failed: {errors}"
        
        try:
            result = {"tool_id": tool_id, "status": "executed", "timestamp": datetime.utcnow().isoformat()}
            _, sanitized, _ = self.output_validator.validate_tool_output(tool_id, result)
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            self.audit_logger.log(
                action_type="tool_executed", actor_id=self.config.agent_id,
                tool_id=tool_id, site_id=case.site_id, case_id=case.case_id,
                result=str(sanitized)[:500], success=True, duration_ms=duration_ms,
            )
            return True, sanitized, "Success"
        except Exception as e:
            self.audit_logger.log(
                action_type="tool_failed", actor_id=self.config.agent_id,
                tool_id=tool_id, case_id=case.case_id, error=str(e), success=False,
            )
            return False, {}, str(e)


class SignalTriageAgent(FourPlaneAgent):
    """Deduplicates alerts, suppresses noise, assigns severity, creates/updates cases."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None, dedup_window_minutes: int = 15):
        config = CrewAIAgentConfig(
            agent_id=f"triage-{site_id}", role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA, name="Signal Triage Agent",
            goal="Deduplicate, filter noise, classify alerts, and create cases",
            backstory="First responder for incoming alerts. Separates signal from noise.",
            site_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.site_id = site_id
        self.dedup_window = timedelta(minutes=dedup_window_minutes)
        self.recent_alerts: List[Alert] = []
        self.suppression_rules: Dict[str, Dict] = {}
        self.active_cases: Dict[str, Case] = {}
    
    def process_alerts(self, alerts: List[Alert]) -> List[Case]:
        """Process incoming alerts and create/update cases."""
        cases_affected = []
        for alert in alerts:
            if self._is_suppressed(alert):
                alert.suppressed = True
                continue
            if self._find_duplicate(alert):
                alert.deduplicated = True
                continue
            self._classify_alert(alert)
            case = self._find_or_create_case(alert)
            case.source_alerts.append(alert)
            alert.merged_into_case = case.case_id
            if case not in cases_affected:
                cases_affected.append(case)
            self.recent_alerts.append(alert)
        cutoff = datetime.utcnow() - self.dedup_window
        self.recent_alerts = [a for a in self.recent_alerts if a.triggered_at > cutoff]
        return cases_affected
    
    def _is_suppressed(self, alert: Alert) -> bool:
        key = f"{alert.device_id}_{alert.alert_type}"
        rule = self.suppression_rules.get(key)
        return rule and datetime.utcnow() < rule.get("until", datetime.min)
    
    def _find_duplicate(self, alert: Alert) -> Optional[Alert]:
        for recent in self.recent_alerts:
            if (recent.device_id == alert.device_id and recent.alert_type == alert.alert_type and
                abs((alert.triggered_at - recent.triggered_at).total_seconds()) < self.dedup_window.total_seconds()):
                return recent
        return None
    
    def _classify_alert(self, alert: Alert):
        t = alert.alert_type.lower()
        if any(x in t for x in ["h2s", "gas", "leak", "fire"]):
            alert.classification = AlertClassification.SAFETY
        elif any(x in t for x in ["fail", "critical"]):
            alert.classification = AlertClassification.IMPENDING_FAILURE
        elif any(x in t for x in ["sla", "timeout"]):
            alert.classification = AlertClassification.SLA_RISK
        elif any(x in t for x in ["comfort", "temperature"]):
            alert.classification = AlertClassification.COMFORT
        else:
            alert.classification = AlertClassification.ENERGY_WASTE
    
    def _find_or_create_case(self, alert: Alert) -> Case:
        for case in self.active_cases.values():
            if case.site_id == alert.site_id and not case.resolved:
                if any(a.device_id == alert.device_id for a in case.source_alerts):
                    return case
        case = Case(
            case_id=str(uuid.uuid4())[:12], site_id=alert.site_id,
            created_at=datetime.utcnow(), classification=alert.classification,
            priority=self._priority_from_classification(alert.classification),
        )
        sla = {CasePriority.P1_CRITICAL: 1, CasePriority.P2_HIGH: 4, CasePriority.P3_MEDIUM: 24,
               CasePriority.P4_LOW: 72, CasePriority.P5_INFO: 168}
        case.sla_deadline = datetime.utcnow() + timedelta(hours=sla[case.priority])
        case.add_timeline_entry("case_created", f"From alert: {alert.message}", self.config.agent_id)
        self.active_cases[case.case_id] = case
        return case
    
    def _priority_from_classification(self, c: AlertClassification) -> CasePriority:
        mapping = {
            AlertClassification.SAFETY: CasePriority.P1_CRITICAL,
            AlertClassification.IMPENDING_FAILURE: CasePriority.P2_HIGH,
            AlertClassification.SLA_RISK: CasePriority.P2_HIGH,
            AlertClassification.COMPLIANCE: CasePriority.P2_HIGH,
            AlertClassification.COMFORT: CasePriority.P3_MEDIUM,
        }
        return mapping.get(c, CasePriority.P4_LOW)


class CorrelationAgent(FourPlaneAgent):
    """Clusters related alerts, builds incident graphs, detects cascade failures."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None, correlation_window_minutes: int = 30):
        config = CrewAIAgentConfig(
            agent_id=f"correlation-{site_id}", role=AgentRole.ANOMALY_DETECTOR,
            category=AgentCategory.ANALYTICS, name="Correlation Agent",
            goal="Identify related alerts and detect cascade failures",
            backstory="Expert at finding hidden connections between events.",
            site_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.site_id = site_id
        self.correlation_window = timedelta(minutes=correlation_window_minutes)
        self.system_topology: Dict[str, Set[str]] = {}
    
    def correlate_case(self, case: Case, all_cases: List[Case]) -> Dict[str, Any]:
        correlations = {"case_id": case.case_id, "related_cases": [], "cascade_detected": False,
                       "cascade_path": [], "correlation_confidence": 0.0}
        case_devices = set(a.device_id for a in case.source_alerts)
        
        for other in all_cases:
            if other.case_id == case.case_id:
                continue
            diff = abs((other.created_at - case.created_at).total_seconds())
            if diff < self.correlation_window.total_seconds():
                other_devices = set(a.device_id for a in other.source_alerts)
                if case_devices & other_devices or self._connected(case_devices, other_devices):
                    correlations["related_cases"].append({
                        "case_id": other.case_id, "time_diff": diff,
                        "shared": list(case_devices & other_devices),
                    })
        
        if len(correlations["related_cases"]) >= 2:
            correlations["cascade_detected"] = True
            correlations["cascade_path"] = [case.case_id] + [r["case_id"] for r in correlations["related_cases"][:2]]
            correlations["correlation_confidence"] = 0.85
        
        if correlations["related_cases"]:
            case.add_timeline_entry("correlation_found", f"Found {len(correlations['related_cases'])} related", self.config.agent_id)
        return correlations
    
    def _connected(self, d1: Set[str], d2: Set[str]) -> bool:
        for dev in d1:
            if self.system_topology.get(dev, set()) & d2:
                return True
        return False


class DiagnosticsAgent(FourPlaneAgent):
    """Runs fault trees, compares against known failure signatures."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"diagnostics-{site_id}", role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS, name="Diagnostics Agent",
            goal="Run diagnostic procedures and identify failure patterns",
            backstory="Diagnostic expert running fault tree analysis.",
            site_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
        self.failure_signatures = [
            {"id": "compressor_short_cycle", "name": "Compressor Short Cycling",
             "symptoms": ["high_cycle_rate", "discharge_temp_rising"], "causes": ["refrigerant_low", "dirty_condenser"]},
            {"id": "pump_cavitation", "name": "Pump Cavitation",
             "symptoms": ["vibration_high", "flow_fluctuation"], "causes": ["inlet_blockage", "air_entrainment"]},
        ]
    
    def run_diagnostics(self, case: Case, signals: List[ProcessedSignal]) -> Dict[str, Any]:
        results = {"case_id": case.case_id, "signature_matches": [], "diagnostic_confidence": 0.0}
        symptoms = self._extract_symptoms(signals)
        
        for sig in self.failure_signatures:
            matches = sum(1 for s in sig["symptoms"] if any(s in sym for sym in symptoms))
            score = matches / max(len(sig["symptoms"]), 1)
            if score > 0.5:
                results["signature_matches"].append({
                    "signature": sig["name"], "score": score, "causes": sig["causes"],
                })
        
        if results["signature_matches"]:
            results["diagnostic_confidence"] = max(m["score"] for m in results["signature_matches"])
        case.add_timeline_entry("diagnostics_complete", f"Found {len(results['signature_matches'])} matches", self.config.agent_id)
        return results
    
    def _extract_symptoms(self, signals: List[ProcessedSignal]) -> List[str]:
        symptoms = []
        for s in signals:
            if s.anomaly_score > 2.0:
                symptoms.append(f"{s.original.sensor_id}_anomaly")
            if s.threshold_breach:
                symptoms.append(f"{s.original.sensor_id}_breach")
        return symptoms


class RootCauseAnalystAgent(FourPlaneAgent):
    """Proposes root cause hypotheses with confidence and validations."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"rca-{site_id}", role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS, name="Root Cause Analyst",
            goal="Identify root causes with evidence-based confidence",
            backstory="Root cause analysis expert who formulates hypotheses.",
            site_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
    
    def analyze(self, case: Case, diagnostics: Dict, correlations: Dict) -> List[Hypothesis]:
        hypotheses = []
        for match in diagnostics.get("signature_matches", []):
            for cause in match.get("causes", []):
                hypotheses.append(Hypothesis(
                    hypothesis_id=str(uuid.uuid4())[:8],
                    description=f"Root cause: {cause} (from {match['signature']})",
                    confidence=match["score"] * 0.9,
                    evidence_for=[f"Pattern match: {match['score']:.2f}"],
                    validations_required=[f"Verify {cause}"],
                ))
        if correlations.get("cascade_detected"):
            hypotheses.append(Hypothesis(
                hypothesis_id=str(uuid.uuid4())[:8],
                description="Cascade failure from upstream",
                confidence=correlations.get("correlation_confidence", 0.5),
                evidence_for=["Cascade path detected"],
                validations_required=["Verify upstream system"],
            ))
        hypotheses.sort(key=lambda h: h.confidence, reverse=True)
        case.hypotheses = hypotheses
        if hypotheses:
            case.root_cause = hypotheses[0]
        case.add_timeline_entry("rca_complete", f"Generated {len(hypotheses)} hypotheses", self.config.agent_id)
        return hypotheses


class RemediationPlannerAgent(FourPlaneAgent):
    """Produces ordered action plans (safe checks → reversible → invasive)."""
    
    def __init__(self, site_id: str, policy_engine: PolicyEngine, audit_logger: AuditLogger,
                 message_bus: Optional[AgentMessageBus] = None):
        config = CrewAIAgentConfig(
            agent_id=f"planner-{site_id}", role=AgentRole.BUDGET_OPTIMIZER,
            category=AgentCategory.OPTIMIZATION, name="Remediation Planner",
            goal="Create safe, ordered action plans with rollback",
            backstory="Creates plans prioritizing safety and reversibility.",
            site_id=site_id,
        )
        super().__init__(config, policy_engine, audit_logger, message_bus)
    
    def create_plan(self, case: Case, hypotheses: List[Hypothesis]) -> RemediationPlan:
        steps = []
        seq = 0
        
        # Phase 1: Safe verification
        if hypotheses:
            for v in hypotheses[0].validations_required[:2]:
                steps.append(ActionStep(
                    step_id=str(uuid.uuid4())[:8], sequence=seq, action_type="verification",
                    description=f"Verify: {v}", risk_level=ActionRiskLevel.SAFE,
                    tool_name="query_telemetry",
                ))
                seq += 1
        
        # Phase 2: Reversible actions
        steps.append(ActionStep(
            step_id=str(uuid.uuid4())[:8], sequence=seq, action_type="remediation",
            description="Adjust setpoint if applicable", risk_level=ActionRiskLevel.LOW,
            tool_name="adjust_setpoint", requires_approval=True,
        ))
        seq += 1
        
        # Phase 3: Schedule inspection
        steps.append(ActionStep(
            step_id=str(uuid.uuid4())[:8], sequence=seq, action_type="dispatch",
            description="Schedule onsite inspection", risk_level=ActionRiskLevel.LOW,
            tool_name="dispatch_technician", requires_approval=True,
        ))
        seq += 1
        
        # Final: Verification
        steps.append(ActionStep(
            step_id=str(uuid.uuid4())[:8], sequence=seq, action_type="post_verification",
            description="Verify remediation success", risk_level=ActionRiskLevel.SAFE,
            tool_name="query_telemetry",
        ))
        
        max_risk = max((s.risk_level for s in steps), default=ActionRiskLevel.SAFE)
        plan = RemediationPlan(
            plan_id=str(uuid.uuid4())[:12], case_id=case.case_id,
            created_at=datetime.utcnow(), created_by=self.config.agent_id,
            steps=steps, overall_risk=max_risk, estimated_duration_minutes=len(steps) * 15,
            approval_required=any(s.requires_approval for s in steps),
        )
        case.remediation_plan = plan
        case.add_timeline_entry("plan_created", f"{len(steps)}-step plan", self.config.agent_id)
        return plan
