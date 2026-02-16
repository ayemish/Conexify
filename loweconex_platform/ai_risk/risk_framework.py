"""
AI Risk Management Framework — NIST AI RMF-aligned.

Implements:
- AI Risk Registry (risk identification, categorization, scoring)
- Risk Controls (preventive, detective, corrective)
- Prompt Security (injection resistance, tool-use allowlists, exfiltration guards)
- Human Review Policy (risk-tiered triggers for high-impact recommendations)
- AI Incident Log and response playbooks

References:
- NIST AI Risk Management Framework (AI 100-1)
- OWASP Top 10 for LLM Applications
- EU AI Act risk classification concepts
"""

from __future__ import annotations

import hashlib
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# =============================================================================
# Risk classification
# =============================================================================

class RiskCategory(str, Enum):
    """NIST AI RMF-aligned risk categories."""
    RELIABILITY = "reliability"
    SAFETY = "safety"
    SECURITY = "security"
    PRIVACY = "privacy"
    FAIRNESS = "fairness"
    TRANSPARENCY = "transparency"
    ACCOUNTABILITY = "accountability"
    VALIDITY = "validity"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ControlType(str, Enum):
    PREVENTIVE = "preventive"
    DETECTIVE = "detective"
    CORRECTIVE = "corrective"


class IncidentSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class IncidentStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    MITIGATED = "mitigated"
    RESOLVED = "resolved"
    CLOSED = "closed"


# =============================================================================
# Risk and control data models
# =============================================================================

@dataclass
class AIRisk:
    """An identified AI risk in the platform."""
    risk_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    category: str = RiskCategory.RELIABILITY.value
    level: str = RiskLevel.MEDIUM.value

    # Impact and likelihood (1–5 scale)
    impact_score: int = 3
    likelihood_score: int = 3

    # Affected components
    affected_models: List[str] = field(default_factory=list)
    affected_kpis: List[str] = field(default_factory=list)
    affected_agents: List[str] = field(default_factory=list)

    # Mitigation
    mitigations: List[str] = field(default_factory=list)
    control_ids: List[str] = field(default_factory=list)
    residual_risk: str = RiskLevel.LOW.value

    # Metadata
    owner: str = ""
    identified_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    last_reviewed: Optional[str] = None
    review_frequency: str = "quarterly"
    status: str = "open"  # open, mitigated, accepted, closed

    @property
    def risk_score(self) -> int:
        return self.impact_score * self.likelihood_score

    def to_dict(self) -> Dict[str, Any]:
        return {
            "risk_id": self.risk_id,
            "title": self.title,
            "description": self.description,
            "category": self.category,
            "level": self.level,
            "impact_score": self.impact_score,
            "likelihood_score": self.likelihood_score,
            "risk_score": self.risk_score,
            "affected_models": self.affected_models,
            "affected_kpis": self.affected_kpis,
            "affected_agents": self.affected_agents,
            "mitigations": self.mitigations,
            "control_ids": self.control_ids,
            "residual_risk": self.residual_risk,
            "owner": self.owner,
            "identified_ts": self.identified_ts,
            "last_reviewed": self.last_reviewed,
            "status": self.status,
        }


@dataclass
class RiskControl:
    """A control mitigating one or more AI risks."""
    control_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    control_type: str = ControlType.PREVENTIVE.value
    implemented: bool = False
    automated: bool = False

    # Testing
    test_procedure: str = ""
    last_tested: Optional[str] = None
    test_result: Optional[str] = None

    # Linked risks
    mitigates_risk_ids: List[str] = field(default_factory=list)

    owner: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "control_id": self.control_id,
            "title": self.title,
            "description": self.description,
            "control_type": self.control_type,
            "implemented": self.implemented,
            "automated": self.automated,
            "test_procedure": self.test_procedure,
            "last_tested": self.last_tested,
            "test_result": self.test_result,
            "mitigates_risk_ids": self.mitigates_risk_ids,
            "owner": self.owner,
        }


# =============================================================================
# AI Risk Registry
# =============================================================================

class AIRiskRegistry:
    """
    Central registry for all identified AI risks and controls.

    Supports:
    - Risk identification and scoring
    - Control mapping and effectiveness tracking
    - Periodic review cadence enforcement
    - Risk heat map generation
    """

    def __init__(self):
        self._risks: Dict[str, AIRisk] = {}
        self._controls: Dict[str, RiskControl] = {}

    def register_risk(self, risk: AIRisk):
        self._risks[risk.risk_id] = risk
        logger.info(f"Registered AI risk: {risk.title} (score={risk.risk_score})")

    def register_control(self, control: RiskControl):
        self._controls[control.control_id] = control

    def get_risk(self, risk_id: str) -> Optional[AIRisk]:
        return self._risks.get(risk_id)

    def get_risks_by_category(self, category: str) -> List[AIRisk]:
        return [r for r in self._risks.values() if r.category == category]

    def get_risks_by_level(self, level: str) -> List[AIRisk]:
        return [r for r in self._risks.values() if r.level == level]

    def get_overdue_reviews(self) -> List[AIRisk]:
        """Get risks that haven't been reviewed within their cadence."""
        overdue = []
        now = datetime.utcnow()
        for risk in self._risks.values():
            if not risk.last_reviewed:
                overdue.append(risk)
                continue
            last = datetime.fromisoformat(risk.last_reviewed)
            cadence_days = {"weekly": 7, "monthly": 30, "quarterly": 90, "annual": 365}
            days = cadence_days.get(risk.review_frequency, 90)
            if (now - last).days > days:
                overdue.append(risk)
        return overdue

    def heat_map(self) -> Dict[str, Any]:
        """Generate a risk heat map (impact x likelihood matrix)."""
        matrix: Dict[str, List[str]] = {}
        for risk in self._risks.values():
            key = f"{risk.impact_score}x{risk.likelihood_score}"
            if key not in matrix:
                matrix[key] = []
            matrix[key].append(risk.risk_id)

        return {
            "matrix": matrix,
            "total_risks": len(self._risks),
            "critical": len([r for r in self._risks.values() if r.risk_score >= 20]),
            "high": len([r for r in self._risks.values() if 12 <= r.risk_score < 20]),
            "medium": len([r for r in self._risks.values() if 6 <= r.risk_score < 12]),
            "low": len([r for r in self._risks.values() if r.risk_score < 6]),
        }

    def controls_coverage(self) -> Dict[str, Any]:
        """Audit control coverage across risks."""
        covered = sum(1 for r in self._risks.values() if r.control_ids)
        tested = sum(1 for c in self._controls.values() if c.last_tested)
        return {
            "total_risks": len(self._risks),
            "risks_with_controls": covered,
            "coverage_pct": covered / len(self._risks) if self._risks else 0,
            "total_controls": len(self._controls),
            "controls_tested": tested,
        }


# =============================================================================
# Prompt security guard
# =============================================================================

class PromptGuard:
    """
    Prompt injection resistance and tool-use safety.

    Implements:
    - Prompt injection detection (pattern-based + heuristic)
    - Tool-use allowlists (only permitted tools per agent)
    - Data exfiltration controls (PII/secret detection in outputs)
    - Output sanitization
    """

    # Common prompt injection patterns
    INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?previous\s+instructions",
        r"forget\s+(all\s+)?your\s+(instructions|rules|guidelines)",
        r"you\s+are\s+now\s+(?:a|an)\s+",
        r"pretend\s+you\s+are",
        r"act\s+as\s+if\s+you",
        r"disregard\s+(all\s+)?(?:previous|prior|above)",
        r"override\s+(?:your|the|all)\s+",
        r"system\s*prompt\s*[:=]",
        r"<\s*/?system\s*>",
        r"\[\s*INST\s*\]",
        r"jailbreak",
        r"DAN\s*mode",
    ]

    # PII patterns for exfiltration detection
    PII_PATTERNS = [
        (r"\b\d{3}-\d{2}-\d{4}\b", "SSN"),
        (r"\b\d{16}\b", "credit_card"),
        (r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b", "email"),
        (r"\b(?:sk-|pk_|api[_-]?key)[A-Za-z0-9]{20,}\b", "api_key"),
    ]

    def __init__(
        self,
        tool_allowlists: Optional[Dict[str, Set[str]]] = None,
        max_output_length: int = 50_000,
        block_on_injection: bool = True,
    ):
        self.tool_allowlists = tool_allowlists or {}
        self.max_output_length = max_output_length
        self.block_on_injection = block_on_injection
        self._compiled_injection = [re.compile(p, re.IGNORECASE) for p in self.INJECTION_PATTERNS]
        self._compiled_pii = [(re.compile(p), label) for p, label in self.PII_PATTERNS]
        self._violation_log: List[Dict[str, Any]] = []

    def check_prompt(self, prompt: str, agent_id: str = "") -> Dict[str, Any]:
        """
        Check a prompt for injection attempts.

        Returns:
            {"safe": bool, "violations": [...], "sanitized_prompt": str}
        """
        violations = []

        for pattern in self._compiled_injection:
            match = pattern.search(prompt)
            if match:
                violations.append({
                    "type": "prompt_injection",
                    "pattern": pattern.pattern,
                    "matched": match.group(),
                    "position": match.start(),
                })

        # Heuristic: unusual control characters
        control_chars = sum(1 for c in prompt if ord(c) < 32 and c not in '\n\r\t')
        if control_chars > 5:
            violations.append({
                "type": "suspicious_control_chars",
                "count": control_chars,
            })

        # Heuristic: excessive prompt length
        if len(prompt) > 100_000:
            violations.append({
                "type": "excessive_length",
                "length": len(prompt),
            })

        safe = len(violations) == 0

        if violations:
            self._log_violation("prompt_check", agent_id, violations)

        return {
            "safe": safe,
            "violations": violations,
            "blocked": self.block_on_injection and not safe,
        }

    def check_tool_use(self, agent_id: str, tool_name: str) -> Dict[str, Any]:
        """Check if an agent is allowed to use a specific tool."""
        if agent_id not in self.tool_allowlists:
            return {"allowed": True, "reason": "No allowlist configured"}

        allowed_tools = self.tool_allowlists[agent_id]
        if tool_name in allowed_tools:
            return {"allowed": True}

        violation = {
            "type": "unauthorized_tool_use",
            "agent_id": agent_id,
            "tool_name": tool_name,
            "allowed_tools": list(allowed_tools),
        }
        self._log_violation("tool_use", agent_id, [violation])
        return {"allowed": False, "reason": f"Tool '{tool_name}' not in allowlist", "violation": violation}

    def check_output(self, output: str, agent_id: str = "") -> Dict[str, Any]:
        """
        Check agent output for data exfiltration (PII/secrets).

        Returns:
            {"safe": bool, "findings": [...], "sanitized": str}
        """
        findings = []

        for pattern, label in self._compiled_pii:
            matches = pattern.findall(output)
            if matches:
                findings.append({
                    "type": "pii_detected",
                    "label": label,
                    "count": len(matches),
                })

        # Length check
        if len(output) > self.max_output_length:
            findings.append({
                "type": "excessive_output_length",
                "length": len(output),
                "max": self.max_output_length,
            })

        safe = len(findings) == 0

        # Sanitize: mask PII
        sanitized = output
        for pattern, label in self._compiled_pii:
            sanitized = pattern.sub(f"[REDACTED_{label.upper()}]", sanitized)

        if findings:
            self._log_violation("output_check", agent_id, findings)

        return {
            "safe": safe,
            "findings": findings,
            "sanitized": sanitized,
        }

    def _log_violation(self, check_type: str, agent_id: str, violations: List[Dict]):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "check_type": check_type,
            "agent_id": agent_id,
            "violations": violations,
        }
        self._violation_log.append(entry)
        logger.warning(f"PromptGuard violation: {check_type} by {agent_id}: {violations}")

    def get_violation_log(self) -> List[Dict[str, Any]]:
        return list(self._violation_log)


# =============================================================================
# Human review policy
# =============================================================================

@dataclass
class ReviewTrigger:
    """A condition that triggers mandatory human review."""
    trigger_id: str
    name: str
    description: str
    condition_fn: Optional[Callable[[Dict[str, Any]], bool]] = None
    # Static thresholds (alternative to condition_fn)
    metric: Optional[str] = None
    operator: str = ">"  # >, <, >=, <=, ==
    threshold: Optional[float] = None


class HumanReviewPolicy:
    """
    Risk-tiered human review triggers.

    Defines when human review is required before a recommendation
    or action can proceed. Supports:
    - Dollar-threshold triggers (CapEx > $X)
    - Risk-score triggers
    - Model-confidence triggers
    - Custom condition functions
    """

    def __init__(self):
        self._triggers: List[ReviewTrigger] = []
        self._review_log: List[Dict[str, Any]] = []

    def add_trigger(self, trigger: ReviewTrigger):
        self._triggers.append(trigger)

    def add_default_triggers(self):
        """Add standard enterprise review triggers."""
        self._triggers.extend([
            ReviewTrigger(
                trigger_id="capex_high",
                name="High CapEx Recommendation",
                description="CapEx recommendations > $50,000 require human review",
                metric="capex_usd",
                operator=">",
                threshold=50_000,
            ),
            ReviewTrigger(
                trigger_id="low_confidence",
                name="Low Model Confidence",
                description="Recommendations with confidence < 0.5 require review",
                metric="confidence",
                operator="<",
                threshold=0.5,
            ),
            ReviewTrigger(
                trigger_id="safety_impact",
                name="Safety-Related Recommendation",
                description="Any recommendation touching safety systems requires review",
                metric="safety_impact",
                operator="==",
                threshold=1.0,
            ),
            ReviewTrigger(
                trigger_id="first_time_kpi",
                name="First-Time KPI for Customer",
                description="First KPI run for a new customer requires review",
                metric="is_first_run",
                operator="==",
                threshold=1.0,
            ),
            ReviewTrigger(
                trigger_id="significant_variance",
                name="Significant Variance from Benchmark",
                description="Results > 2 std from benchmark require review",
                metric="benchmark_z_score",
                operator=">",
                threshold=2.0,
            ),
        ])

    def evaluate(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate all triggers against a recommendation context.

        Returns:
            {
                "review_required": bool,
                "triggered": [...],
                "can_auto_approve": bool,
            }
        """
        triggered = []

        for trigger in self._triggers:
            fired = False

            if trigger.condition_fn:
                try:
                    fired = trigger.condition_fn(context)
                except Exception as e:
                    logger.error(f"Trigger {trigger.trigger_id} error: {e}")

            elif trigger.metric and trigger.threshold is not None:
                value = context.get(trigger.metric)
                if value is not None:
                    fired = self._compare(value, trigger.operator, trigger.threshold)

            if fired:
                triggered.append({
                    "trigger_id": trigger.trigger_id,
                    "name": trigger.name,
                    "description": trigger.description,
                })

        review_required = len(triggered) > 0

        if review_required:
            self._review_log.append({
                "timestamp": datetime.utcnow().isoformat(),
                "triggers": triggered,
                "context_keys": list(context.keys()),
            })

        return {
            "review_required": review_required,
            "triggered": triggered,
            "can_auto_approve": not review_required,
        }

    @staticmethod
    def _compare(value: float, operator: str, threshold: float) -> bool:
        ops = {">": lambda a, b: a > b, "<": lambda a, b: a < b,
               ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
               "==": lambda a, b: a == b}
        return ops.get(operator, lambda a, b: False)(value, threshold)

    def get_review_log(self) -> List[Dict[str, Any]]:
        return list(self._review_log)


# =============================================================================
# AI incident log
# =============================================================================

@dataclass
class AIIncident:
    """An AI-related incident requiring investigation."""
    incident_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    title: str = ""
    description: str = ""
    severity: str = IncidentSeverity.MEDIUM.value
    status: str = IncidentStatus.OPEN.value

    # Classification
    category: str = RiskCategory.RELIABILITY.value
    affected_models: List[str] = field(default_factory=list)
    affected_customers: List[str] = field(default_factory=list)

    # Impact
    impact_description: str = ""
    financial_impact_usd: Optional[float] = None
    data_affected: bool = False

    # Timeline
    detected_ts: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    acknowledged_ts: Optional[str] = None
    mitigated_ts: Optional[str] = None
    resolved_ts: Optional[str] = None

    # Response
    root_cause: str = ""
    corrective_actions: List[str] = field(default_factory=list)
    preventive_actions: List[str] = field(default_factory=list)
    assigned_to: str = ""

    # Linked artifacts
    linked_risk_ids: List[str] = field(default_factory=list)
    linked_alert_ids: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "incident_id": self.incident_id,
            "title": self.title,
            "description": self.description,
            "severity": self.severity,
            "status": self.status,
            "category": self.category,
            "affected_models": self.affected_models,
            "affected_customers": self.affected_customers,
            "impact_description": self.impact_description,
            "financial_impact_usd": self.financial_impact_usd,
            "data_affected": self.data_affected,
            "detected_ts": self.detected_ts,
            "acknowledged_ts": self.acknowledged_ts,
            "mitigated_ts": self.mitigated_ts,
            "resolved_ts": self.resolved_ts,
            "root_cause": self.root_cause,
            "corrective_actions": self.corrective_actions,
            "preventive_actions": self.preventive_actions,
            "assigned_to": self.assigned_to,
            "linked_risk_ids": self.linked_risk_ids,
            "linked_alert_ids": self.linked_alert_ids,
        }


class AIIncidentLog:
    """
    Log of all AI-related incidents with lifecycle management.
    """

    def __init__(self):
        self._incidents: Dict[str, AIIncident] = {}

    def report(self, incident: AIIncident) -> str:
        self._incidents[incident.incident_id] = incident
        logger.warning(f"AI incident reported: {incident.title} ({incident.severity})")
        return incident.incident_id

    def acknowledge(self, incident_id: str, assigned_to: str):
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.INVESTIGATING.value
            inc.acknowledged_ts = datetime.utcnow().isoformat()
            inc.assigned_to = assigned_to

    def mitigate(self, incident_id: str, actions: List[str]):
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.MITIGATED.value
            inc.mitigated_ts = datetime.utcnow().isoformat()
            inc.corrective_actions = actions

    def resolve(self, incident_id: str, root_cause: str, preventive_actions: List[str]):
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.RESOLVED.value
            inc.resolved_ts = datetime.utcnow().isoformat()
            inc.root_cause = root_cause
            inc.preventive_actions = preventive_actions

    def close(self, incident_id: str):
        inc = self._incidents.get(incident_id)
        if inc:
            inc.status = IncidentStatus.CLOSED.value

    def get_open(self) -> List[AIIncident]:
        return [
            i for i in self._incidents.values()
            if i.status in (IncidentStatus.OPEN.value, IncidentStatus.INVESTIGATING.value)
        ]

    def get_all(self) -> List[AIIncident]:
        return list(self._incidents.values())

    def stats(self) -> Dict[str, Any]:
        statuses = {}
        for inc in self._incidents.values():
            statuses[inc.status] = statuses.get(inc.status, 0) + 1
        return {
            "total": len(self._incidents),
            "by_status": statuses,
            "open": len(self.get_open()),
        }
