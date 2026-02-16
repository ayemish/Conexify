"""
Approval Queue Data Models

Enhanced models for workflow queue items with LLM explanations and validation.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class QueueItemStatus(str, Enum):
    """Status of a queue item"""
    PENDING = "pending"
    EXPLAINING = "explaining"  # LLM generating explanation
    VALIDATING = "validating"  # LLM validating
    READY = "ready"  # Ready for human review
    IN_REVIEW = "in_review"  # Human reviewing
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    ESCALATED = "escalated"


class RiskLevel(str, Enum):
    """Risk level assessment"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ValidationStatus(str, Enum):
    """LLM validation status"""
    PASSED = "passed"
    WARNING = "warning"
    FAILED = "failed"
    NEEDS_REVIEW = "needs_review"


@dataclass
class RiskAssessment:
    """Risk assessment for a workflow item"""
    overall_risk: RiskLevel = RiskLevel.MEDIUM
    
    # Risk factors
    equipment_criticality: float = 0.5  # 0-1
    business_impact: float = 0.5  # 0-1
    safety_risk: float = 0.0  # 0-1
    reversibility: float = 0.8  # 0-1 (1 = easily reversible)
    
    # Explanations
    risk_factors: List[str] = field(default_factory=list)
    mitigations: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "overall_risk": self.overall_risk.value,
            "equipment_criticality": self.equipment_criticality,
            "business_impact": self.business_impact,
            "safety_risk": self.safety_risk,
            "reversibility": self.reversibility,
            "risk_factors": self.risk_factors,
            "mitigations": self.mitigations,
        }


@dataclass
class LLMExplanation:
    """LLM-generated explanation for a workflow item"""
    explanation_id: str = field(default_factory=lambda: f"EXP-{uuid.uuid4().hex[:12]}")
    
    # Summary
    title: str = ""
    summary: str = ""
    
    # Detailed explanation sections
    what_happened: str = ""  # What triggered this workflow
    what_will_happen: str = ""  # What actions will be taken
    why_recommended: str = ""  # Why this is recommended
    expected_outcome: str = ""  # Expected result
    
    # Risk and impact
    risk_assessment: RiskAssessment = field(default_factory=RiskAssessment)
    
    # Evidence summary
    key_evidence: List[Dict[str, Any]] = field(default_factory=list)
    
    # Similar past cases
    similar_cases: List[Dict[str, Any]] = field(default_factory=list)
    
    # Alternative options
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    
    # Confidence
    confidence: float = 0.0
    uncertainty_factors: List[str] = field(default_factory=list)
    
    # Generation metadata
    model_used: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)
    generation_time_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "explanation_id": self.explanation_id,
            "title": self.title,
            "summary": self.summary,
            "what_happened": self.what_happened,
            "what_will_happen": self.what_will_happen,
            "why_recommended": self.why_recommended,
            "expected_outcome": self.expected_outcome,
            "risk_assessment": self.risk_assessment.to_dict(),
            "key_evidence": self.key_evidence,
            "similar_cases": self.similar_cases,
            "alternatives": self.alternatives,
            "confidence": self.confidence,
            "uncertainty_factors": self.uncertainty_factors,
            "model_used": self.model_used,
            "generated_at": self.generated_at.isoformat(),
            "generation_time_ms": self.generation_time_ms,
        }


@dataclass
class LLMValidation:
    """LLM validation result for a workflow item"""
    validation_id: str = field(default_factory=lambda: f"VAL-{uuid.uuid4().hex[:12]}")
    
    # Overall status
    status: ValidationStatus = ValidationStatus.NEEDS_REVIEW
    
    # Validation checks
    checks: List[Dict[str, Any]] = field(default_factory=list)
    # Each check: {"name": str, "passed": bool, "message": str, "severity": str}
    
    # Issues found
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    info: List[str] = field(default_factory=list)
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    
    # Pre-conditions check
    preconditions_met: bool = True
    failed_preconditions: List[str] = field(default_factory=list)
    
    # Safety checks
    safety_checks_passed: bool = True
    safety_concerns: List[str] = field(default_factory=list)
    
    # Confidence
    validation_confidence: float = 0.0
    
    # Metadata
    model_used: str = ""
    validated_at: datetime = field(default_factory=datetime.utcnow)
    validation_time_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "validation_id": self.validation_id,
            "status": self.status.value,
            "checks": self.checks,
            "errors": self.errors,
            "warnings": self.warnings,
            "info": self.info,
            "recommendations": self.recommendations,
            "preconditions_met": self.preconditions_met,
            "failed_preconditions": self.failed_preconditions,
            "safety_checks_passed": self.safety_checks_passed,
            "safety_concerns": self.safety_concerns,
            "validation_confidence": self.validation_confidence,
            "model_used": self.model_used,
            "validated_at": self.validated_at.isoformat(),
            "validation_time_ms": self.validation_time_ms,
        }
    
    @property
    def is_valid(self) -> bool:
        return self.status in (ValidationStatus.PASSED, ValidationStatus.WARNING)


@dataclass
class ApprovalDecision:
    """Human approval decision"""
    decision_id: str = field(default_factory=lambda: f"DEC-{uuid.uuid4().hex[:12]}")
    
    # Decision
    approved: bool = False
    decision: str = ""  # "approved", "rejected", "modified"
    
    # Reviewer
    reviewer_id: str = ""
    reviewer_name: str = ""
    reviewer_role: str = ""
    
    # Timing
    reviewed_at: datetime = field(default_factory=datetime.utcnow)
    review_duration_seconds: int = 0
    
    # Notes
    notes: str = ""
    rejection_reason: str = ""
    
    # Modifications
    modified_params: Dict[str, Any] = field(default_factory=dict)
    
    # Confidence in LLM
    llm_explanation_helpful: Optional[bool] = None
    llm_validation_accurate: Optional[bool] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "approved": self.approved,
            "decision": self.decision,
            "reviewer_id": self.reviewer_id,
            "reviewer_name": self.reviewer_name,
            "reviewer_role": self.reviewer_role,
            "reviewed_at": self.reviewed_at.isoformat(),
            "review_duration_seconds": self.review_duration_seconds,
            "notes": self.notes,
            "rejection_reason": self.rejection_reason,
            "modified_params": self.modified_params,
            "llm_explanation_helpful": self.llm_explanation_helpful,
            "llm_validation_accurate": self.llm_validation_accurate,
        }


@dataclass
class QueueItem:
    """
    Workflow queue item for human-in-the-loop approval.
    
    Enhanced with LLM-generated explanations and validation.
    """
    item_id: str = field(default_factory=lambda: f"QI-{uuid.uuid4().hex[:12]}")
    
    # Source
    approval_id: str = ""  # Link to ApprovalModel
    run_id: str = ""
    incident_id: str = ""
    playbook_id: str = ""
    step_id: str = ""
    
    # Context
    tenant_id: str = ""
    site_id: str = ""
    asset_id: str = ""
    
    # Classification
    item_type: str = "action_approval"  # action_approval, playbook_selection, escalation
    risk_tier: str = "MEDIUM"
    priority: int = 50  # 0-100, higher = more urgent
    
    # Proposed action
    proposed_actions: List[Dict[str, Any]] = field(default_factory=list)
    action_summary: str = ""
    
    # Context data
    telemetry_snapshot: Dict[str, Any] = field(default_factory=dict)
    fault_context: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)
    
    # Status
    status: QueueItemStatus = QueueItemStatus.PENDING
    
    # LLM Explanation
    explanation: Optional[LLMExplanation] = None
    explanation_error: Optional[str] = None
    
    # LLM Validation
    validation: Optional[LLMValidation] = None
    validation_error: Optional[str] = None
    
    # Human Decision
    decision: Optional[ApprovalDecision] = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    
    # Assignment
    assigned_to: Optional[str] = None
    assigned_at: Optional[datetime] = None
    
    # Escalation
    escalation_level: int = 0
    escalated_from: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "item_id": self.item_id,
            "approval_id": self.approval_id,
            "run_id": self.run_id,
            "incident_id": self.incident_id,
            "playbook_id": self.playbook_id,
            "step_id": self.step_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "item_type": self.item_type,
            "risk_tier": self.risk_tier,
            "priority": self.priority,
            "proposed_actions": self.proposed_actions,
            "action_summary": self.action_summary,
            "telemetry_snapshot": self.telemetry_snapshot,
            "fault_context": self.fault_context,
            "evidence": self.evidence,
            "status": self.status.value,
            "explanation": self.explanation.to_dict() if self.explanation else None,
            "explanation_error": self.explanation_error,
            "validation": self.validation.to_dict() if self.validation else None,
            "validation_error": self.validation_error,
            "decision": self.decision.to_dict() if self.decision else None,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "assigned_to": self.assigned_to,
            "assigned_at": self.assigned_at.isoformat() if self.assigned_at else None,
            "escalation_level": self.escalation_level,
        }
    
    @property
    def is_ready_for_review(self) -> bool:
        """Check if item has explanation and validation ready"""
        return (
            self.explanation is not None 
            and self.validation is not None
            and self.status == QueueItemStatus.READY
        )
    
    @property
    def requires_immediate_attention(self) -> bool:
        """Check if item is high priority or near expiration"""
        if self.risk_tier in ("HIGH", "EXTREME"):
            return True
        if self.expires_at:
            time_left = (self.expires_at - datetime.utcnow()).total_seconds()
            return time_left < 300  # Less than 5 minutes
        return False
