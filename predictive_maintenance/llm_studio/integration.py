"""
LLM Studio Integration

Hooks into the autopilot orchestrator and agent system to automatically
capture workflow decisions for LLM training data generation.
"""

import logging
from datetime import datetime
from functools import wraps
from typing import Any, Callable, Dict, List, Optional

from .models import (
    WorkflowTrace,
    AgentDecision,
    ContextSnapshot,
    DecisionType,
    OutcomeStatus,
)
from .capture import WorkflowCaptureService

logger = logging.getLogger(__name__)

# Global capture service instance
_capture_service: Optional[WorkflowCaptureService] = None


def get_capture_service() -> WorkflowCaptureService:
    """Get or create the global capture service"""
    global _capture_service
    if _capture_service is None:
        _capture_service = WorkflowCaptureService()
    return _capture_service


def set_capture_service(service: WorkflowCaptureService):
    """Set the global capture service (for testing)"""
    global _capture_service
    _capture_service = service


class AutopilotCaptureHook:
    """
    Hook into autopilot orchestrator to capture workflow decisions.
    
    Usage:
        hook = AutopilotCaptureHook()
        
        # At start of autopilot run
        trace = hook.on_run_start(run_id, incident_id, asset_id, ...)
        
        # For each step/decision
        decision = hook.on_decision(
            trace_id=trace.trace_id,
            decision_type=DecisionType.ACTION_EXECUTION,
            ...
        )
        
        # On completion
        hook.on_run_complete(trace.trace_id, status, outcome)
    """
    
    def __init__(self, capture_service: WorkflowCaptureService = None):
        self.capture = capture_service or get_capture_service()
    
    def on_run_start(
        self,
        run_id: str,
        incident_id: str,
        asset_id: str,
        site_id: str,
        tenant_id: str,
        playbook_id: str = "",
    ) -> WorkflowTrace:
        """Called when an autopilot run starts"""
        trace = self.capture.start_trace(
            workflow_type="autopilot_run",
            tenant_id=tenant_id,
            site_id=site_id,
            asset_id=asset_id,
            incident_id=incident_id,
            run_id=run_id,
        )
        
        logger.info(f"Capture hook: started trace {trace.trace_id} for run {run_id}")
        return trace
    
    def on_decision(
        self,
        trace_id: str,
        decision_type: DecisionType,
        agent_name: str,
        context: Dict[str, Any],
        reasoning: List[str],
        decision: str,
        action: Dict[str, Any],
        confidence: float = 0.0,
        alternatives: List[Dict[str, Any]] = None,
    ) -> AgentDecision:
        """Called when an agent makes a decision"""
        # Build context snapshot
        context_snapshot = ContextSnapshot(
            timestamp=datetime.utcnow(),
            asset_id=context.get("asset_id", ""),
            site_id=context.get("site_id", ""),
            tenant_id=context.get("tenant_id", ""),
            telemetry=context.get("telemetry", {}),
            regime=context.get("regime", ""),
            ambient_conditions=context.get("ambient", {}),
            active_alerts=context.get("alerts", []),
            fault_hypotheses=context.get("hypotheses", []),
            retrieved_documents=context.get("documents", []),
            similar_cases=context.get("similar_cases", []),
            applicable_policies=context.get("policies", []),
        )
        
        decision_obj = self.capture.record_decision(
            trace_id=trace_id,
            decision_type=decision_type,
            agent_name=agent_name,
            context=context_snapshot,
            reasoning_steps=reasoning,
            decision=decision,
            action_taken=action,
            confidence=confidence,
            alternatives=alternatives,
        )
        
        logger.debug(f"Capture hook: recorded decision {decision_obj.decision_id}")
        return decision_obj
    
    def on_decision_outcome(
        self,
        decision_id: str,
        success: bool,
        result: str,
        metrics: Dict[str, float] = None,
        verification_passed: bool = None,
    ):
        """Called when a decision's outcome is known"""
        status = OutcomeStatus.SUCCESS if success else OutcomeStatus.FAILURE
        
        self.capture.record_outcome(
            decision_id=decision_id,
            status=status,
            result_summary=result,
            metrics=metrics,
            verification_passed=verification_passed,
        )
        
        logger.debug(f"Capture hook: recorded outcome for {decision_id}")
    
    def on_run_complete(
        self,
        trace_id: str,
        success: bool,
        outcome: str,
    ):
        """Called when an autopilot run completes"""
        status = OutcomeStatus.SUCCESS if success else OutcomeStatus.FAILURE
        
        self.capture.complete_trace(
            trace_id=trace_id,
            status=status,
            outcome=outcome,
        )
        
        logger.info(f"Capture hook: completed trace {trace_id}")


def capture_decision(
    decision_type: DecisionType,
    agent_name: str = None,
):
    """
    Decorator to automatically capture agent decisions.
    
    Usage:
        @capture_decision(DecisionType.FAULT_DETECTION, "FaultHypothesisAgent")
        def detect_fault(self, telemetry, context):
            reasoning = ["Step 1...", "Step 2..."]
            decision = "Fault detected"
            return {"reasoning": reasoning, "decision": decision, "action": {...}}
    
    The decorated function should return a dict with:
    - reasoning: List[str] - reasoning steps
    - decision: str - the decision made
    - action: Dict - action taken
    - confidence: float (optional) - confidence score
    """
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Get capture service
            capture = get_capture_service()
            
            # Try to get trace context from kwargs or first arg
            trace_id = kwargs.get("trace_id")
            context = kwargs.get("context", {})
            
            # Execute the function
            start_time = datetime.utcnow()
            result = func(*args, **kwargs)
            duration_ms = int((datetime.utcnow() - start_time).total_seconds() * 1000)
            
            # If result has expected structure and we have a trace, record decision
            if trace_id and isinstance(result, dict):
                try:
                    decision = capture.record_decision(
                        trace_id=trace_id,
                        decision_type=decision_type,
                        agent_name=agent_name or func.__name__,
                        context=ContextSnapshot(
                            timestamp=start_time,
                            **{k: v for k, v in context.items() 
                               if k in ContextSnapshot.__dataclass_fields__}
                        ),
                        reasoning_steps=result.get("reasoning", []),
                        decision=result.get("decision", ""),
                        action_taken=result.get("action", {}),
                        confidence=result.get("confidence", 0.0),
                        alternatives=result.get("alternatives", []),
                    )
                    decision.duration_ms = duration_ms
                    
                    # Attach decision_id to result
                    result["_decision_id"] = decision.decision_id
                except Exception as e:
                    logger.warning(f"Failed to capture decision: {e}")
            
            return result
        return wrapper
    return decorator


class AgentTracingMixin:
    """
    Mixin class for agents to enable automatic decision capture.
    
    Usage:
        class MyAgent(AgentTracingMixin):
            def __init__(self):
                super().__init__()
                self.agent_name = "MyAgent"
            
            def process(self, context, trace_id=None):
                with self.trace_decision(trace_id, DecisionType.FAULT_DETECTION) as tracer:
                    tracer.add_reasoning("Step 1...")
                    tracer.add_reasoning("Step 2...")
                    tracer.set_decision("Fault detected")
                    tracer.set_action({"type": "alert"})
    """
    
    agent_name: str = "UnknownAgent"
    
    def trace_decision(
        self,
        trace_id: str,
        decision_type: DecisionType,
    ):
        """Context manager for tracing a decision"""
        return DecisionTracer(
            trace_id=trace_id,
            decision_type=decision_type,
            agent_name=self.agent_name,
            capture_service=get_capture_service(),
        )


class DecisionTracer:
    """Context manager for building and capturing a decision"""
    
    def __init__(
        self,
        trace_id: str,
        decision_type: DecisionType,
        agent_name: str,
        capture_service: WorkflowCaptureService,
    ):
        self.trace_id = trace_id
        self.decision_type = decision_type
        self.agent_name = agent_name
        self.capture = capture_service
        
        self.reasoning_steps: List[str] = []
        self.decision: str = ""
        self.action: Dict[str, Any] = {}
        self.confidence: float = 0.0
        self.alternatives: List[Dict[str, Any]] = []
        self.context: Dict[str, Any] = {}
        
        self._start_time: datetime = None
        self._decision_obj: AgentDecision = None
    
    def __enter__(self):
        self._start_time = datetime.utcnow()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            # Record failed decision
            self.decision = f"Error: {exc_val}"
        
        if self.trace_id:
            try:
                context_snapshot = ContextSnapshot(
                    timestamp=self._start_time,
                    **{k: v for k, v in self.context.items()
                       if k in ContextSnapshot.__dataclass_fields__}
                )
                
                self._decision_obj = self.capture.record_decision(
                    trace_id=self.trace_id,
                    decision_type=self.decision_type,
                    agent_name=self.agent_name,
                    context=context_snapshot,
                    reasoning_steps=self.reasoning_steps,
                    decision=self.decision,
                    action_taken=self.action,
                    confidence=self.confidence,
                    alternatives=self.alternatives,
                )
                
                duration = int((datetime.utcnow() - self._start_time).total_seconds() * 1000)
                self._decision_obj.duration_ms = duration
                
            except Exception as e:
                logger.warning(f"Failed to record decision: {e}")
        
        return False  # Don't suppress exceptions
    
    def add_reasoning(self, step: str):
        """Add a reasoning step"""
        self.reasoning_steps.append(step)
    
    def set_decision(self, decision: str):
        """Set the decision"""
        self.decision = decision
    
    def set_action(self, action: Dict[str, Any]):
        """Set the action taken"""
        self.action = action
    
    def set_confidence(self, confidence: float):
        """Set confidence score"""
        self.confidence = confidence
    
    def set_context(self, **context):
        """Set context values"""
        self.context.update(context)
    
    def add_alternative(self, alternative: Dict[str, Any]):
        """Add an alternative that was considered"""
        self.alternatives.append(alternative)
    
    @property
    def decision_id(self) -> Optional[str]:
        """Get the decision ID after context exit"""
        return self._decision_obj.decision_id if self._decision_obj else None
