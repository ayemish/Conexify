"""
Workflow Capture Service

Captures agent workflow behavior for LLM training data generation.
Integrates with the autopilot orchestrator and agent system.
"""

import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional
from collections import defaultdict

from .models import (
    WorkflowTrace,
    AgentDecision,
    DecisionOutcome,
    ContextSnapshot,
    DecisionType,
    OutcomeStatus,
    Annotation,
    AnnotationType,
)

logger = logging.getLogger(__name__)


class WorkflowCaptureService:
    """
    Captures agent workflow execution for LLM training.
    
    Features:
    - Automatic trace capture from autopilot runs
    - Decision point instrumentation
    - Outcome tracking
    - Integration with human feedback
    """
    
    def __init__(self, session_factory: Callable = None):
        self.session_factory = session_factory
        
        # In-memory storage (would be database in production)
        self._traces: Dict[str, WorkflowTrace] = {}
        self._decisions: Dict[str, AgentDecision] = {}
        self._annotations: Dict[str, List[Annotation]] = defaultdict(list)
        
        # Active traces by run/incident
        self._active_by_run: Dict[str, str] = {}
        self._active_by_incident: Dict[str, str] = {}
    
    def start_trace(
        self,
        workflow_type: str,
        tenant_id: str,
        site_id: str,
        asset_id: str,
        incident_id: str = None,
        run_id: str = None,
    ) -> WorkflowTrace:
        """Start a new workflow trace"""
        trace = WorkflowTrace(
            workflow_type=workflow_type,
            tenant_id=tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            incident_id=incident_id,
            run_id=run_id,
        )
        
        self._traces[trace.trace_id] = trace
        
        if run_id:
            self._active_by_run[run_id] = trace.trace_id
        if incident_id:
            self._active_by_incident[incident_id] = trace.trace_id
        
        logger.info(f"Started workflow trace {trace.trace_id} for {workflow_type}")
        return trace
    
    def get_trace(self, trace_id: str) -> Optional[WorkflowTrace]:
        """Get a trace by ID"""
        return self._traces.get(trace_id)
    
    def get_trace_by_run(self, run_id: str) -> Optional[WorkflowTrace]:
        """Get trace for a specific run"""
        trace_id = self._active_by_run.get(run_id)
        return self._traces.get(trace_id) if trace_id else None
    
    def record_decision(
        self,
        trace_id: str,
        decision_type: DecisionType,
        agent_name: str,
        context: ContextSnapshot,
        reasoning_steps: List[str],
        decision: str,
        action_taken: Dict[str, Any],
        confidence: float = 0.0,
        alternatives: List[Dict[str, Any]] = None,
        model_version: str = "",
    ) -> AgentDecision:
        """Record an agent decision point"""
        trace = self._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")
        
        decision_obj = AgentDecision(
            trace_id=trace_id,
            decision_type=decision_type,
            agent_name=agent_name,
            model_version=model_version,
            context=context,
            reasoning_steps=reasoning_steps,
            confidence=confidence,
            decision=decision,
            action_taken=action_taken,
            alternatives=alternatives or [],
        )
        
        trace.add_decision(decision_obj)
        self._decisions[decision_obj.decision_id] = decision_obj
        
        logger.debug(
            f"Recorded decision {decision_obj.decision_id} "
            f"({decision_type.value}) in trace {trace_id}"
        )
        
        return decision_obj
    
    def record_outcome(
        self,
        decision_id: str,
        status: OutcomeStatus,
        result_summary: str,
        metrics: Dict[str, float] = None,
        verification_passed: bool = None,
        verification_details: Dict[str, Any] = None,
        error_message: str = "",
    ) -> DecisionOutcome:
        """Record the outcome of a decision"""
        decision = self._decisions.get(decision_id)
        if not decision:
            raise ValueError(f"Decision not found: {decision_id}")
        
        outcome = DecisionOutcome(
            decision_id=decision_id,
            status=status,
            completed_at=datetime.utcnow(),
            duration_to_outcome_ms=int(
                (datetime.utcnow() - decision.timestamp).total_seconds() * 1000
            ),
            result_summary=result_summary,
            metrics=metrics or {},
            verification_passed=verification_passed,
            verification_details=verification_details or {},
            error_message=error_message,
        )
        
        decision.outcome = outcome
        
        logger.debug(
            f"Recorded outcome for decision {decision_id}: {status.value}"
        )
        
        return outcome
    
    def complete_trace(
        self,
        trace_id: str,
        status: OutcomeStatus,
        outcome: str,
    ) -> WorkflowTrace:
        """Complete a workflow trace"""
        trace = self._traces.get(trace_id)
        if not trace:
            raise ValueError(f"Trace not found: {trace_id}")
        
        trace.complete(status, outcome)
        
        # Clean up active mappings
        if trace.run_id and trace.run_id in self._active_by_run:
            del self._active_by_run[trace.run_id]
        if trace.incident_id and trace.incident_id in self._active_by_incident:
            del self._active_by_incident[trace.incident_id]
        
        logger.info(
            f"Completed trace {trace_id} with status {status.value}: {outcome}"
        )
        
        return trace
    
    def add_annotation(
        self,
        annotation_type: AnnotationType,
        annotator_id: str,
        decision_id: str = None,
        trace_id: str = None,
        is_correct: bool = None,
        quality_score: float = None,
        corrected_decision: str = None,
        corrected_reasoning: List[str] = None,
        notes: str = "",
        tags: List[str] = None,
        annotator_role: str = "",
    ) -> Annotation:
        """Add a human annotation to a decision or trace"""
        annotation = Annotation(
            decision_id=decision_id,
            trace_id=trace_id,
            annotation_type=annotation_type,
            annotator_id=annotator_id,
            annotator_role=annotator_role,
            is_correct=is_correct,
            quality_score=quality_score,
            corrected_decision=corrected_decision,
            corrected_reasoning=corrected_reasoning or [],
            notes=notes,
            tags=tags or [],
        )
        
        # Add to decision or trace
        if decision_id:
            self._annotations[decision_id].append(annotation)
            decision = self._decisions.get(decision_id)
            if decision and decision.outcome:
                decision.outcome.human_verified = True
                decision.outcome.human_feedback = notes
        
        if trace_id:
            trace = self._traces.get(trace_id)
            if trace:
                trace.annotations.append(annotation)
                
                # Update training inclusion based on annotation
                if annotation_type == AnnotationType.DO_NOT_TRAIN:
                    trace.include_in_training = False
                elif annotation_type == AnnotationType.EXEMPLARY:
                    trace.quality_score = max(trace.quality_score or 0, 0.9)
        
        logger.info(
            f"Added annotation {annotation.annotation_id} "
            f"({annotation_type.value}) by {annotator_id}"
        )
        
        return annotation
    
    def list_traces(
        self,
        tenant_id: str = None,
        workflow_type: str = None,
        status: OutcomeStatus = None,
        include_in_training: bool = None,
        min_quality_score: float = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[WorkflowTrace]:
        """List traces with filtering"""
        traces = list(self._traces.values())
        
        # Apply filters
        if tenant_id:
            traces = [t for t in traces if t.tenant_id == tenant_id]
        if workflow_type:
            traces = [t for t in traces if t.workflow_type == workflow_type]
        if status:
            traces = [t for t in traces if t.final_status == status]
        if include_in_training is not None:
            traces = [t for t in traces if t.include_in_training == include_in_training]
        if min_quality_score is not None:
            traces = [
                t for t in traces 
                if t.quality_score and t.quality_score >= min_quality_score
            ]
        
        # Sort by start time descending
        traces.sort(key=lambda t: t.started_at, reverse=True)
        
        return traces[offset:offset + limit]
    
    def get_decisions_for_training(
        self,
        decision_types: List[DecisionType] = None,
        min_confidence: float = None,
        only_successful: bool = True,
        only_human_verified: bool = False,
        limit: int = 1000,
    ) -> List[AgentDecision]:
        """Get decisions suitable for training data"""
        decisions = list(self._decisions.values())
        
        # Filter by decision type
        if decision_types:
            decisions = [d for d in decisions if d.decision_type in decision_types]
        
        # Filter by confidence
        if min_confidence is not None:
            decisions = [d for d in decisions if d.confidence >= min_confidence]
        
        # Filter by outcome
        if only_successful:
            decisions = [
                d for d in decisions
                if d.outcome and d.outcome.status == OutcomeStatus.SUCCESS
            ]
        
        # Filter by human verification
        if only_human_verified:
            decisions = [
                d for d in decisions
                if d.outcome and d.outcome.human_verified
            ]
        
        # Check trace inclusion
        decisions = [
            d for d in decisions
            if d.trace_id in self._traces 
            and self._traces[d.trace_id].include_in_training
        ]
        
        return decisions[:limit]
    
    def get_trace_stats(self) -> Dict[str, Any]:
        """Get statistics about captured traces"""
        traces = list(self._traces.values())
        decisions = list(self._decisions.values())
        
        status_counts = defaultdict(int)
        type_counts = defaultdict(int)
        
        for trace in traces:
            status_counts[trace.final_status.value] += 1
        
        for decision in decisions:
            type_counts[decision.decision_type.value] += 1
        
        successful_decisions = [
            d for d in decisions
            if d.outcome and d.outcome.status == OutcomeStatus.SUCCESS
        ]
        
        verified_decisions = [
            d for d in decisions
            if d.outcome and d.outcome.human_verified
        ]
        
        return {
            "total_traces": len(traces),
            "total_decisions": len(decisions),
            "status_counts": dict(status_counts),
            "decision_type_counts": dict(type_counts),
            "successful_decisions": len(successful_decisions),
            "verified_decisions": len(verified_decisions),
            "trainable_decisions": len(self.get_decisions_for_training()),
            "avg_decisions_per_trace": (
                len(decisions) / len(traces) if traces else 0
            ),
        }
