"""
LLM Studio Data Models

Captures agent workflow behavior for LLM training:
- WorkflowTrace: Complete execution trace of an agent workflow
- AgentDecision: Individual decision point with context and reasoning
- DecisionOutcome: Result of a decision (success/failure/partial)
- TrainingExample: Formatted example for LLM fine-tuning
- Annotation: Human feedback and labels
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional


class DecisionType(str, Enum):
    """Types of agent decisions"""
    FAULT_DETECTION = "fault_detection"
    PLAYBOOK_SELECTION = "playbook_selection"
    ACTION_EXECUTION = "action_execution"
    APPROVAL_REQUEST = "approval_request"
    ESCALATION = "escalation"
    VERIFICATION = "verification"
    PARAMETER_RESOLUTION = "parameter_resolution"
    RISK_ASSESSMENT = "risk_assessment"


class OutcomeStatus(str, Enum):
    """Outcome status of a decision"""
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"
    PENDING = "pending"
    TIMEOUT = "timeout"
    REJECTED = "rejected"


class AnnotationType(str, Enum):
    """Types of human annotations"""
    CORRECT = "correct"
    INCORRECT = "incorrect"
    PARTIALLY_CORRECT = "partially_correct"
    NEEDS_REVIEW = "needs_review"
    EXEMPLARY = "exemplary"  # Use as training example
    DO_NOT_TRAIN = "do_not_train"  # Exclude from training


class ExportFormat(str, Enum):
    """Training data export formats"""
    JSONL = "jsonl"
    CONVERSATION = "conversation"  # OpenAI chat format
    ALPACA = "alpaca"  # Instruction/input/output format
    SHAREGPT = "sharegpt"  # ShareGPT conversation format


@dataclass
class ContextSnapshot:
    """Snapshot of context at decision time"""
    timestamp: datetime
    
    # Asset/equipment context
    asset_id: str = ""
    site_id: str = ""
    tenant_id: str = ""
    
    # Telemetry context
    telemetry: Dict[str, float] = field(default_factory=dict)
    point_history: Dict[str, List[float]] = field(default_factory=dict)
    
    # Operating context
    regime: str = ""
    ambient_conditions: Dict[str, float] = field(default_factory=dict)
    
    # Alert/fault context
    active_alerts: List[Dict[str, Any]] = field(default_factory=list)
    fault_hypotheses: List[Dict[str, Any]] = field(default_factory=list)
    
    # Knowledge context
    retrieved_documents: List[Dict[str, Any]] = field(default_factory=list)
    similar_cases: List[Dict[str, Any]] = field(default_factory=list)
    
    # Policy context
    applicable_policies: List[Dict[str, Any]] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "site_id": self.site_id,
            "tenant_id": self.tenant_id,
            "telemetry": self.telemetry,
            "regime": self.regime,
            "ambient_conditions": self.ambient_conditions,
            "active_alerts": self.active_alerts,
            "fault_hypotheses": self.fault_hypotheses,
            "retrieved_documents": self.retrieved_documents,
            "similar_cases": self.similar_cases,
            "applicable_policies": self.applicable_policies,
        }


@dataclass
class AgentDecision:
    """
    Individual agent decision point.
    
    Captures the complete context, reasoning, and action for a single decision,
    suitable for LLM training as an instruction-following example.
    """
    decision_id: str = field(default_factory=lambda: f"DEC-{uuid.uuid4().hex[:12]}")
    trace_id: str = ""
    
    # Decision metadata
    decision_type: DecisionType = DecisionType.ACTION_EXECUTION
    agent_name: str = ""
    model_version: str = ""
    
    # Timing
    timestamp: datetime = field(default_factory=datetime.utcnow)
    duration_ms: int = 0
    
    # Input context
    context: ContextSnapshot = field(default_factory=lambda: ContextSnapshot(datetime.utcnow()))
    
    # Reasoning (chain of thought)
    reasoning_steps: List[str] = field(default_factory=list)
    confidence: float = 0.0
    
    # Decision output
    decision: str = ""  # Natural language description
    action_taken: Dict[str, Any] = field(default_factory=dict)
    
    # Alternatives considered
    alternatives: List[Dict[str, Any]] = field(default_factory=list)
    
    # Outcome (filled in later)
    outcome: Optional["DecisionOutcome"] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "trace_id": self.trace_id,
            "decision_type": self.decision_type.value,
            "agent_name": self.agent_name,
            "model_version": self.model_version,
            "timestamp": self.timestamp.isoformat(),
            "duration_ms": self.duration_ms,
            "context": self.context.to_dict(),
            "reasoning_steps": self.reasoning_steps,
            "confidence": self.confidence,
            "decision": self.decision,
            "action_taken": self.action_taken,
            "alternatives": self.alternatives,
            "outcome": self.outcome.to_dict() if self.outcome else None,
        }
    
    def to_training_prompt(self) -> str:
        """Format as instruction prompt for LLM training"""
        lines = [
            "### Context",
            f"Asset: {self.context.asset_id}",
            f"Regime: {self.context.regime}",
            f"Telemetry: {self.context.telemetry}",
        ]
        
        if self.context.active_alerts:
            lines.append(f"Active Alerts: {len(self.context.active_alerts)}")
        
        if self.context.fault_hypotheses:
            lines.append(f"Fault Hypotheses: {self.context.fault_hypotheses}")
        
        lines.extend([
            "",
            "### Task",
            f"Decision Type: {self.decision_type.value}",
            "",
            "### Reasoning",
        ])
        lines.extend(self.reasoning_steps)
        
        lines.extend([
            "",
            "### Decision",
            self.decision,
        ])
        
        return "\n".join(lines)


@dataclass
class DecisionOutcome:
    """Outcome of an agent decision"""
    outcome_id: str = field(default_factory=lambda: f"OUT-{uuid.uuid4().hex[:12]}")
    decision_id: str = ""
    
    # Status
    status: OutcomeStatus = OutcomeStatus.PENDING
    
    # Timing
    completed_at: Optional[datetime] = None
    duration_to_outcome_ms: int = 0
    
    # Results
    result_summary: str = ""
    metrics: Dict[str, float] = field(default_factory=dict)
    
    # Verification
    verification_passed: Optional[bool] = None
    verification_details: Dict[str, Any] = field(default_factory=dict)
    
    # Human feedback
    human_verified: bool = False
    human_feedback: str = ""
    
    # Error info (if failed)
    error_message: str = ""
    error_details: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "outcome_id": self.outcome_id,
            "decision_id": self.decision_id,
            "status": self.status.value,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_to_outcome_ms": self.duration_to_outcome_ms,
            "result_summary": self.result_summary,
            "metrics": self.metrics,
            "verification_passed": self.verification_passed,
            "verification_details": self.verification_details,
            "human_verified": self.human_verified,
            "human_feedback": self.human_feedback,
            "error_message": self.error_message,
        }


@dataclass
class Annotation:
    """Human annotation for a decision or trace"""
    annotation_id: str = field(default_factory=lambda: f"ANN-{uuid.uuid4().hex[:12]}")
    
    # Target
    decision_id: Optional[str] = None
    trace_id: Optional[str] = None
    
    # Annotation
    annotation_type: AnnotationType = AnnotationType.NEEDS_REVIEW
    annotator_id: str = ""
    annotator_role: str = ""  # engineer, domain_expert, etc.
    
    # Feedback
    is_correct: Optional[bool] = None
    quality_score: Optional[float] = None  # 0-1
    
    # Corrections
    corrected_decision: Optional[str] = None
    corrected_reasoning: List[str] = field(default_factory=list)
    
    # Notes
    notes: str = ""
    tags: List[str] = field(default_factory=list)
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "annotation_id": self.annotation_id,
            "decision_id": self.decision_id,
            "trace_id": self.trace_id,
            "annotation_type": self.annotation_type.value,
            "annotator_id": self.annotator_id,
            "annotator_role": self.annotator_role,
            "is_correct": self.is_correct,
            "quality_score": self.quality_score,
            "corrected_decision": self.corrected_decision,
            "corrected_reasoning": self.corrected_reasoning,
            "notes": self.notes,
            "tags": self.tags,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class WorkflowTrace:
    """
    Complete execution trace of an agent workflow.
    
    Captures the full sequence of decisions from incident detection
    through resolution, suitable for analyzing agent behavior patterns.
    """
    trace_id: str = field(default_factory=lambda: f"TRC-{uuid.uuid4().hex[:12]}")
    
    # Workflow identity
    workflow_type: str = ""  # autopilot_run, fault_detection, etc.
    incident_id: Optional[str] = None
    run_id: Optional[str] = None
    
    # Context
    tenant_id: str = ""
    site_id: str = ""
    asset_id: str = ""
    
    # Timing
    started_at: datetime = field(default_factory=datetime.utcnow)
    completed_at: Optional[datetime] = None
    
    # Decisions
    decisions: List[AgentDecision] = field(default_factory=list)
    
    # Overall outcome
    final_status: OutcomeStatus = OutcomeStatus.PENDING
    final_outcome: str = ""
    
    # Annotations
    annotations: List[Annotation] = field(default_factory=list)
    
    # Training metadata
    include_in_training: bool = True
    quality_score: Optional[float] = None
    
    def add_decision(self, decision: AgentDecision):
        """Add a decision to the trace"""
        decision.trace_id = self.trace_id
        self.decisions.append(decision)
    
    def complete(self, status: OutcomeStatus, outcome: str):
        """Mark trace as complete"""
        self.completed_at = datetime.utcnow()
        self.final_status = status
        self.final_outcome = outcome
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "trace_id": self.trace_id,
            "workflow_type": self.workflow_type,
            "incident_id": self.incident_id,
            "run_id": self.run_id,
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "decisions": [d.to_dict() for d in self.decisions],
            "final_status": self.final_status.value,
            "final_outcome": self.final_outcome,
            "annotations": [a.to_dict() for a in self.annotations],
            "include_in_training": self.include_in_training,
            "quality_score": self.quality_score,
        }
    
    def duration_ms(self) -> int:
        """Total duration in milliseconds"""
        if self.completed_at:
            return int((self.completed_at - self.started_at).total_seconds() * 1000)
        return int((datetime.utcnow() - self.started_at).total_seconds() * 1000)


@dataclass
class TrainingExample:
    """
    Formatted training example for LLM fine-tuning.
    
    Supports multiple output formats:
    - JSONL: Single JSON object per line
    - Conversation: OpenAI chat completion format
    - Alpaca: Instruction/Input/Output format
    """
    example_id: str = field(default_factory=lambda: f"EX-{uuid.uuid4().hex[:12]}")
    
    # Source
    source_decision_id: str = ""
    source_trace_id: str = ""
    
    # Content
    system_prompt: str = ""
    instruction: str = ""
    input_context: str = ""
    expected_output: str = ""
    
    # Metadata
    decision_type: str = ""
    quality_score: float = 0.0
    is_human_verified: bool = False
    
    # Tags for filtering
    tags: List[str] = field(default_factory=list)
    
    def to_jsonl(self) -> Dict[str, Any]:
        """Export as JSONL format"""
        return {
            "id": self.example_id,
            "instruction": self.instruction,
            "input": self.input_context,
            "output": self.expected_output,
            "metadata": {
                "decision_type": self.decision_type,
                "quality_score": self.quality_score,
                "human_verified": self.is_human_verified,
                "tags": self.tags,
            }
        }
    
    def to_conversation(self) -> Dict[str, Any]:
        """Export as OpenAI conversation format"""
        messages = []
        
        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})
        
        user_content = self.instruction
        if self.input_context:
            user_content += f"\n\n{self.input_context}"
        
        messages.append({"role": "user", "content": user_content})
        messages.append({"role": "assistant", "content": self.expected_output})
        
        return {"messages": messages}
    
    def to_alpaca(self) -> Dict[str, Any]:
        """Export as Alpaca format"""
        return {
            "instruction": self.instruction,
            "input": self.input_context,
            "output": self.expected_output,
        }
    
    def to_sharegpt(self) -> Dict[str, Any]:
        """Export as ShareGPT format"""
        conversations = []
        
        if self.system_prompt:
            conversations.append({"from": "system", "value": self.system_prompt})
        
        user_content = self.instruction
        if self.input_context:
            user_content += f"\n\n{self.input_context}"
        
        conversations.append({"from": "human", "value": user_content})
        conversations.append({"from": "gpt", "value": self.expected_output})
        
        return {"conversations": conversations}
