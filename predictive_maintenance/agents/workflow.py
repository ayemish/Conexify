"""
PDM Collaborative Decision-Making Workflow

Implements the complete workflow for multi-agent collaborative maintenance decisions.

Workflow Stages:
1. Telemetry Ingestion & Context Building
2. Layered Analysis Pipeline
3. Collaborative Voting & Consensus
4. Decision Finalization & Action

Key Features:
- Layered agent execution with dependency management
- Weighted voting with agent expertise
- Consensus building with dissent tracking
- Decision audit trail for governance
- Feedback loop for model improvement
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from collections import defaultdict
import json

from .model_agents import (
    PDMModelAgent, PDMModelAgentRole, AgentAnalysisResult,
    AgentVote, AgentOpinion, CollaborativeDecision,
)
from .orchestrator import (
    PDMModelOrchestrator, OrchestratorConfig, TelemetryInput, OrchestratorResult,
)
from .protocols import (
    ProtocolMessageBus, VotingProtocol, EscalationProtocol, ConsensusProtocol,
    ProtocolMessage, ProtocolMessageType, MessagePriority,
)
from ..services.rag_service import get_rag_service

logger = logging.getLogger(__name__)


# =============================================================================
# Workflow States
# =============================================================================

class WorkflowState(str, Enum):
    """States in the collaborative decision workflow"""
    INITIALIZED = "initialized"
    CONTEXT_BUILDING = "context_building"
    LAYER_0_REGIME = "layer_0_regime"
    LAYER_1_TRUST = "layer_1_trust"
    LAYER_2_BEHAVIOR = "layer_2_behavior"
    LAYER_3_DIAGNOSIS = "layer_3_diagnosis"
    LAYER_4_VOTING = "layer_4_voting"
    CONSENSUS_BUILDING = "consensus_building"
    DECISION_FINALIZED = "decision_finalized"
    ACTION_TAKEN = "action_taken"
    COMPLETED = "completed"
    FAILED = "failed"


class DecisionType(str, Enum):
    """Types of maintenance decisions"""
    NO_ACTION = "no_action"
    CONTINUE_MONITORING = "continue_monitoring"
    WATCH_ALERT = "watch_alert"
    ACTION_ALERT = "action_alert"
    DISPATCH_REQUIRED = "dispatch_required"
    EMERGENCY_DISPATCH = "emergency_dispatch"


# =============================================================================
# Workflow Context
# =============================================================================

@dataclass
class WorkflowContext:
    """Context maintained throughout the workflow"""
    workflow_id: str
    site_id: str
    asset_id: str
    started_at: datetime
    
    # Input
    telemetry: Dict[str, Any]
    
    # State tracking
    current_state: WorkflowState = WorkflowState.INITIALIZED
    state_history: List[Tuple[WorkflowState, datetime]] = field(default_factory=list)
    
    # Layer results
    regime_result: Optional[AgentAnalysisResult] = None
    trust_result: Optional[AgentAnalysisResult] = None
    behavior_results: List[AgentAnalysisResult] = field(default_factory=list)
    diagnosis_result: Optional[AgentAnalysisResult] = None
    
    # Voting
    votes: List[AgentVote] = field(default_factory=list)
    collaborative_decision: Optional[CollaborativeDecision] = None
    
    # Final decision
    final_decision: Optional[DecisionType] = None
    decision_rationale: str = ""
    confidence: float = 0.0
    
    # Audit trail
    events: List[Dict[str, Any]] = field(default_factory=list)
    
    def transition_to(self, state: WorkflowState):
        """Transition to a new state"""
        self.state_history.append((self.current_state, datetime.utcnow()))
        self.current_state = state
        self.log_event("state_transition", {"from": self.state_history[-1][0].value, "to": state.value})
    
    def log_event(self, event_type: str, data: Dict[str, Any]):
        """Log an event to the audit trail"""
        self.events.append({
            "event_id": str(uuid.uuid4()),
            "event_type": event_type,
            "timestamp": datetime.utcnow().isoformat(),
            "workflow_id": self.workflow_id,
            "state": self.current_state.value,
            "data": data,
        })
    
    def get_duration_seconds(self) -> float:
        """Get workflow duration in seconds"""
        return (datetime.utcnow() - self.started_at).total_seconds()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            "workflow_id": self.workflow_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "started_at": self.started_at.isoformat(),
            "current_state": self.current_state.value,
            "final_decision": self.final_decision.value if self.final_decision else None,
            "confidence": self.confidence,
            "duration_seconds": self.get_duration_seconds(),
            "n_votes": len(self.votes),
            "n_events": len(self.events),
        }


# =============================================================================
# Decision Rules
# =============================================================================

@dataclass
class DecisionRule:
    """A rule for making maintenance decisions"""
    rule_id: str
    name: str
    description: str
    priority: int  # Lower = higher priority
    
    # Conditions
    min_sensor_trust: float = 0.0
    require_steady_state: bool = False
    require_change_detected: bool = False
    min_fault_probability: float = 0.0
    min_consensus_confidence: float = 0.0
    required_agent_agreement: List[PDMModelAgentRole] = field(default_factory=list)
    
    # Decision
    decision_type: DecisionType = DecisionType.NO_ACTION
    
    def evaluate(self, context: WorkflowContext) -> Tuple[bool, str]:
        """Evaluate if this rule applies to the context"""
        reasons = []
        
        # Sensor trust check
        if context.trust_result:
            trust = context.trust_result.result_data.get("min_trust", 1.0)
            if trust < self.min_sensor_trust:
                return False, f"Sensor trust {trust:.0%} below threshold {self.min_sensor_trust:.0%}"
        
        # Steady state check
        if self.require_steady_state and context.regime_result:
            is_steady = context.regime_result.result_data.get("is_steady_state", False)
            if not is_steady:
                return False, "System not in steady state"
        
        # Change detected check
        if self.require_change_detected:
            change_detected = False
            for result in context.behavior_results:
                if result.result_type == "change_detection":
                    if result.result_data.get("any_change", False):
                        change_detected = True
                        break
            if not change_detected:
                return False, "No persistent change detected"
        
        # Fault probability check
        if context.diagnosis_result and self.min_fault_probability > 0:
            prob = context.diagnosis_result.result_data.get("top_probability", 0)
            if prob < self.min_fault_probability:
                return False, f"Fault probability {prob:.0%} below threshold {self.min_fault_probability:.0%}"
        
        # Consensus confidence check
        if context.collaborative_decision and self.min_consensus_confidence > 0:
            conf = context.collaborative_decision.aggregate_confidence
            if conf < self.min_consensus_confidence:
                return False, f"Consensus confidence {conf:.0%} below threshold {self.min_consensus_confidence:.0%}"
        
        # Agent agreement check
        if self.required_agent_agreement and context.votes:
            agreeing_roles = set()
            for vote in context.votes:
                if vote.opinion in [AgentOpinion.AGREE, AgentOpinion.STRONGLY_AGREE]:
                    agreeing_roles.add(vote.agent_role)
            
            missing = set(self.required_agent_agreement) - agreeing_roles
            if missing:
                return False, f"Missing agreement from: {[r.value for r in missing]}"
        
        return True, "All conditions met"


class DecisionRuleEngine:
    """Engine for evaluating decision rules"""
    
    def __init__(self):
        self.rules: List[DecisionRule] = []
        self._init_default_rules()
    
    def _init_default_rules(self):
        """Initialize default decision rules"""
        # Emergency dispatch - critical situations
        self.rules.append(DecisionRule(
            rule_id="emergency_dispatch",
            name="Emergency Dispatch",
            description="Dispatch immediately for critical confirmed faults",
            priority=1,
            min_sensor_trust=0.8,
            require_steady_state=True,
            require_change_detected=True,
            min_fault_probability=0.9,
            min_consensus_confidence=0.85,
            required_agent_agreement=[
                PDMModelAgentRole.CHANGE_DETECTION,
                PDMModelAgentRole.FAULT_HYPOTHESIS,
            ],
            decision_type=DecisionType.EMERGENCY_DISPATCH,
        ))
        
        # Standard dispatch
        self.rules.append(DecisionRule(
            rule_id="dispatch_required",
            name="Dispatch Required",
            description="Dispatch for confirmed faults with high confidence",
            priority=2,
            min_sensor_trust=0.7,
            require_steady_state=True,
            require_change_detected=True,
            min_fault_probability=0.7,
            min_consensus_confidence=0.7,
            decision_type=DecisionType.DISPATCH_REQUIRED,
        ))
        
        # Action alert
        self.rules.append(DecisionRule(
            rule_id="action_alert",
            name="Action Alert",
            description="Generate actionable alert for likely faults",
            priority=3,
            min_sensor_trust=0.6,
            require_steady_state=True,
            require_change_detected=True,
            min_fault_probability=0.5,
            min_consensus_confidence=0.6,
            decision_type=DecisionType.ACTION_ALERT,
        ))
        
        # Watch alert
        self.rules.append(DecisionRule(
            rule_id="watch_alert",
            name="Watch Alert",
            description="Generate watch alert for emerging issues",
            priority=4,
            min_sensor_trust=0.5,
            require_change_detected=True,
            min_consensus_confidence=0.5,
            decision_type=DecisionType.WATCH_ALERT,
        ))
        
        # Continue monitoring
        self.rules.append(DecisionRule(
            rule_id="continue_monitoring",
            name="Continue Monitoring",
            description="Continue monitoring when change detected but not confident",
            priority=5,
            min_sensor_trust=0.4,
            require_change_detected=True,
            decision_type=DecisionType.CONTINUE_MONITORING,
        ))
        
        # No action (default)
        self.rules.append(DecisionRule(
            rule_id="no_action",
            name="No Action",
            description="No action needed - system operating normally",
            priority=100,
            decision_type=DecisionType.NO_ACTION,
        ))
        
        # Sort by priority
        self.rules.sort(key=lambda r: r.priority)
    
    def evaluate(self, context: WorkflowContext) -> Tuple[DecisionType, str, str]:
        """Evaluate rules and return the first matching decision"""
        for rule in self.rules:
            matches, reason = rule.evaluate(context)
            if matches:
                context.log_event("rule_matched", {
                    "rule_id": rule.rule_id,
                    "rule_name": rule.name,
                    "decision": rule.decision_type.value,
                })
                return rule.decision_type, rule.name, reason
        
        return DecisionType.NO_ACTION, "default", "No rules matched"


# =============================================================================
# Collaborative Workflow
# =============================================================================

class CollaborativeDecisionWorkflow:
    """
    Main workflow orchestrating multi-agent collaborative decisions.
    
    This is the primary entry point for the PDM multi-agent system.
    """
    
    def __init__(
        self,
        site_id: str,
        orchestrator: Optional[PDMModelOrchestrator] = None,
        config: Optional[OrchestratorConfig] = None,
    ):
        self.site_id = site_id
        self.orchestrator = orchestrator or PDMModelOrchestrator(site_id, config)
        self.rule_engine = DecisionRuleEngine()
        
        # Protocol bus for agent communication
        self.message_bus = ProtocolMessageBus()
        
        # Workflow tracking
        self.active_workflows: Dict[str, WorkflowContext] = {}
        self.completed_workflows: List[WorkflowContext] = []
        self.max_completed = 1000
        
        # Callbacks
        self.on_decision_callbacks: List[Callable[[WorkflowContext], None]] = []
        self.on_alert_callbacks: List[Callable[[WorkflowContext, DecisionType], None]] = []
        
        logger.info(f"CollaborativeDecisionWorkflow initialized for site {site_id}")
    
    def process(self, telemetry: TelemetryInput) -> WorkflowContext:
        """
        Process telemetry through the complete collaborative workflow.
        
        Returns the workflow context with the final decision.
        """
        # Create workflow context
        context = WorkflowContext(
            workflow_id=str(uuid.uuid4()),
            site_id=self.site_id,
            asset_id=telemetry.asset_id,
            started_at=datetime.utcnow(),
            telemetry=telemetry.to_dict(),
        )
        
        self.active_workflows[context.workflow_id] = context
        context.log_event("workflow_started", {"asset_id": telemetry.asset_id})
        
        try:
            # Stage 1: Context Building
            context.transition_to(WorkflowState.CONTEXT_BUILDING)
            self._build_context(context, telemetry)
            
            # Stage 2: Layered Analysis
            self._run_layered_analysis(context, telemetry)
            
            # Stage 3: Collaborative Voting
            context.transition_to(WorkflowState.LAYER_4_VOTING)
            self._run_collaborative_voting(context)
            
            # Stage 4: Decision Finalization
            context.transition_to(WorkflowState.DECISION_FINALIZED)
            self._finalize_decision(context)
            
            # Stage 5: Action (if needed)
            if context.final_decision not in [DecisionType.NO_ACTION, DecisionType.CONTINUE_MONITORING]:
                context.transition_to(WorkflowState.ACTION_TAKEN)
                self._take_action(context)
            
            context.transition_to(WorkflowState.COMPLETED)
            context.log_event("workflow_completed", {
                "decision": context.final_decision.value if context.final_decision else None,
                "confidence": context.confidence,
                "duration_seconds": context.get_duration_seconds(),
            })
            self._index_agent_summary(context)
            
        except Exception as e:
            context.transition_to(WorkflowState.FAILED)
            context.log_event("workflow_failed", {"error": str(e)})
            logger.error(f"Workflow {context.workflow_id} failed: {e}")
        
        finally:
            # Move to completed
            del self.active_workflows[context.workflow_id]
            self.completed_workflows.append(context)
            if len(self.completed_workflows) > self.max_completed:
                self.completed_workflows = self.completed_workflows[-self.max_completed // 2:]
        
        return context

    def _index_agent_summary(self, context: WorkflowContext):
        """Index a summary of agent results into the RAG store."""
        summary = {
            "workflow_id": context.workflow_id,
            "site_id": context.site_id,
            "asset_id": context.asset_id,
            "final_decision": context.final_decision.value if context.final_decision else None,
            "confidence": context.confidence,
            "regime": context.regime_result.result_data.get("regime") if context.regime_result else None,
            "min_trust": context.trust_result.result_data.get("min_trust") if context.trust_result else None,
            "changes": [
                r.result_data for r in context.behavior_results if r.result_type == "change_detection"
            ],
            "diagnosis": context.diagnosis_result.result_data if context.diagnosis_result else None,
            "votes": [
                {
                    "agent_id": v.agent_id,
                    "agent_role": v.agent_role.value,
                    "opinion": v.opinion.value,
                    "confidence": v.confidence,
                    "rationale": v.rationale,
                }
                for v in context.votes
            ],
        }
        rag = get_rag_service()
        content = rag.format_document("agent_summary", summary)
        rag.index_document(
            doc_type="agent_summary",
            content=content,
            asset_id=context.asset_id,
            site_id=context.site_id,
            metadata={"source": "workflow"},
        )
    
    def _build_context(self, context: WorkflowContext, telemetry: TelemetryInput):
        """Build initial context from telemetry"""
        context.log_event("context_building", {
            "timestamp": telemetry.timestamp.isoformat(),
            "compressor_on": telemetry.compressor_on,
        })
    
    def _run_layered_analysis(self, context: WorkflowContext, telemetry: TelemetryInput):
        """Run analysis through all agent layers"""
        inputs = telemetry.to_dict()
        
        # Layer 0: Regime Detection
        context.transition_to(WorkflowState.LAYER_0_REGIME)
        context.regime_result = self.orchestrator.regime_agent.analyze(inputs)
        context.log_event("layer_0_complete", {
            "regime": context.regime_result.result_data.get("regime"),
            "confidence": context.regime_result.confidence,
        })
        
        inputs["regime"] = context.regime_result.result_data.get("regime", "unknown")
        inputs["is_steady_state"] = context.regime_result.result_data.get("is_steady_state", False)
        
        # Layer 1: Sensor Trust
        context.transition_to(WorkflowState.LAYER_1_TRUST)
        context.trust_result = self.orchestrator.sensor_trust_agent.analyze(inputs)
        context.log_event("layer_1_complete", {
            "min_trust": context.trust_result.result_data.get("min_trust"),
            "untrusted": context.trust_result.result_data.get("untrusted_sensors"),
        })
        
        inputs["sensor_trust"] = context.trust_result.result_data.get("min_trust", 1.0)
        
        # Layer 2: Behavioral Analysis
        context.transition_to(WorkflowState.LAYER_2_BEHAVIOR)
        
        behavior_result = self.orchestrator.behavior_agent.analyze(inputs)
        context.behavior_results.append(behavior_result)
        
        inputs["residuals"] = behavior_result.result_data.get("residuals", {})
        
        change_result = self.orchestrator.change_detection_agent.analyze(inputs)
        context.behavior_results.append(change_result)
        
        context.log_event("layer_2_complete", {
            "deviations": behavior_result.result_data.get("significant_deviations"),
            "changes": change_result.result_data.get("changes_detected"),
        })
        
        # Layer 3: Diagnosis
        context.transition_to(WorkflowState.LAYER_3_DIAGNOSIS)
        inputs["change_detections"] = change_result.result_data.get("change_results", {})
        inputs["telemetry"] = telemetry.to_dict()
        
        context.diagnosis_result = self.orchestrator.fault_hypothesis_agent.analyze(inputs)
        context.log_event("layer_3_complete", {
            "top_fault": context.diagnosis_result.result_data.get("top_fault"),
            "probability": context.diagnosis_result.result_data.get("top_probability"),
            "confident": context.diagnosis_result.result_data.get("is_confident"),
        })
    
    def _run_collaborative_voting(self, context: WorkflowContext):
        """Run collaborative voting among all agents"""
        # Build voting context
        voting_context = {
            "asset_id": context.asset_id,
            "regime": context.regime_result.result_data.get("regime") if context.regime_result else None,
            "sensor_trust": context.trust_result.result_data.get("min_trust", 1.0) if context.trust_result else 1.0,
            "is_steady_state": context.regime_result.result_data.get("is_steady_state", False) if context.regime_result else False,
            "changes_detected": [],
            "fault_hypothesis": None,
            "fault_probability": 0,
        }
        
        for result in context.behavior_results:
            if result.result_type == "change_detection":
                voting_context["changes_detected"] = result.result_data.get("changes_detected", [])
        
        if context.diagnosis_result:
            voting_context["fault_hypothesis"] = context.diagnosis_result.result_data.get("top_fault")
            voting_context["fault_probability"] = context.diagnosis_result.result_data.get("top_probability", 0)
            voting_context["is_confident"] = context.diagnosis_result.result_data.get("is_confident", False)
        
        # Collect votes from all agents
        question = "Should we generate a maintenance alert for this asset?"
        
        for agent in self.orchestrator.model_agents:
            vote = agent.vote_on_decision(question, voting_context)
            context.votes.append(vote)
            context.log_event("vote_cast", {
                "agent_id": agent.config.agent_id,
                "role": vote.agent_role.value,
                "opinion": vote.opinion.value,
                "confidence": vote.confidence,
                "weight": vote.weight,
            })
        
        # Aggregate votes
        context.collaborative_decision = self.orchestrator.decision_policy_agent.make_collaborative_decision(
            question=question,
            context=voting_context,
            voting_agents=self.orchestrator.model_agents,
            consensus_threshold=self.orchestrator.config.consensus_threshold,
        )
        
        context.log_event("voting_complete", {
            "final_decision": context.collaborative_decision.final_decision,
            "consensus": context.collaborative_decision.consensus_reached,
            "confidence": context.collaborative_decision.aggregate_confidence,
            "dissenters": context.collaborative_decision.dissenting_agents,
        })
    
    def _finalize_decision(self, context: WorkflowContext):
        """Finalize the maintenance decision using rule engine"""
        decision_type, rule_name, reason = self.rule_engine.evaluate(context)
        
        context.final_decision = decision_type
        context.decision_rationale = f"{rule_name}: {reason}"
        context.confidence = context.collaborative_decision.aggregate_confidence if context.collaborative_decision else 0
        
        context.log_event("decision_finalized", {
            "decision": decision_type.value,
            "rule": rule_name,
            "rationale": reason,
            "confidence": context.confidence,
        })
        
        # Notify callbacks
        for callback in self.on_decision_callbacks:
            try:
                callback(context)
            except Exception as e:
                logger.error(f"Decision callback error: {e}")
    
    def _take_action(self, context: WorkflowContext):
        """Take action based on the final decision"""
        decision = context.final_decision
        
        if decision in [DecisionType.DISPATCH_REQUIRED, DecisionType.EMERGENCY_DISPATCH]:
            action = "create_dispatch"
        elif decision == DecisionType.ACTION_ALERT:
            action = "create_action_alert"
        elif decision == DecisionType.WATCH_ALERT:
            action = "create_watch_alert"
        else:
            action = "none"
        
        context.log_event("action_taken", {
            "action": action,
            "decision": decision.value,
        })
        
        # Notify alert callbacks
        if decision not in [DecisionType.NO_ACTION, DecisionType.CONTINUE_MONITORING]:
            for callback in self.on_alert_callbacks:
                try:
                    callback(context, decision)
                except Exception as e:
                    logger.error(f"Alert callback error: {e}")
    
    def record_feedback(
        self,
        workflow_id: str,
        actual_outcome: str,
        was_correct: bool,
        notes: str = "",
    ):
        """Record feedback on a decision for model improvement"""
        # Find workflow
        context = None
        for wf in self.completed_workflows:
            if wf.workflow_id == workflow_id:
                context = wf
                break
        
        if not context:
            logger.warning(f"Workflow {workflow_id} not found for feedback")
            return
        
        context.log_event("feedback_received", {
            "actual_outcome": actual_outcome,
            "was_correct": was_correct,
            "predicted_decision": context.final_decision.value if context.final_decision else None,
            "notes": notes,
        })
        
        # Feed back to model retraining pipeline
        try:
            from ..services.retraining_trigger_service import (
                RetrainingTriggerService,
                FeedbackRecord,
            )
            trigger_svc = RetrainingTriggerService()
            fb = FeedbackRecord(
                timestamp=datetime.utcnow(),
                asset_id=context.asset_id if hasattr(context, "asset_id") else "",
                fault_type=actual_outcome,
                predicted_outcome=context.final_decision.value if context.final_decision else "unknown",
                actual_outcome=actual_outcome,
                was_correct=was_correct,
                notes=notes,
            )
            retrain_req = trigger_svc.record_feedback(fb)
            if retrain_req:
                logger.info(
                    "Retraining triggered from feedback: %s",
                    retrain_req.request_id,
                )
        except Exception as e:
            logger.debug(f"Retraining trigger skipped: {e}")
        
        logger.info(f"Feedback recorded for workflow {workflow_id}: correct={was_correct}")
    
    def get_workflow_summary(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """Get summary of a workflow"""
        for wf in self.completed_workflows:
            if wf.workflow_id == workflow_id:
                return wf.to_dict()
        return None
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get workflow metrics"""
        if not self.completed_workflows:
            return {"total": 0}
        
        decisions = defaultdict(int)
        for wf in self.completed_workflows:
            if wf.final_decision:
                decisions[wf.final_decision.value] += 1
        
        durations = [wf.get_duration_seconds() for wf in self.completed_workflows]
        
        return {
            "total_workflows": len(self.completed_workflows),
            "active_workflows": len(self.active_workflows),
            "decision_distribution": dict(decisions),
            "avg_duration_seconds": sum(durations) / len(durations),
            "max_duration_seconds": max(durations),
            "min_duration_seconds": min(durations),
        }


# =============================================================================
# Workflow Factory
# =============================================================================

def create_collaborative_workflow(
    site_id: str,
    config: Optional[OrchestratorConfig] = None,
) -> CollaborativeDecisionWorkflow:
    """Create a collaborative decision workflow for a site"""
    return CollaborativeDecisionWorkflow(site_id, config=config)


# =============================================================================
# Example Usage
# =============================================================================

def example_usage():
    """Example usage of the collaborative workflow"""
    from .orchestrator import TelemetryInput
    
    # Create workflow
    workflow = create_collaborative_workflow("site_001")
    
    # Register callbacks
    def on_decision(context: WorkflowContext):
        print(f"Decision made: {context.final_decision}")
    
    def on_alert(context: WorkflowContext, decision_type: DecisionType):
        print(f"Alert generated: {decision_type} for {context.asset_id}")
    
    workflow.on_decision_callbacks.append(on_decision)
    workflow.on_alert_callbacks.append(on_alert)
    
    # Process telemetry
    telemetry = TelemetryInput(
        timestamp=datetime.utcnow(),
        asset_id="RTU_001",
        site_id="site_001",
        compressor_on=True,
        compressor_current=15.2,
        suction_pressure=68.0,
        discharge_pressure=275.0,
        suction_line_temp=42.0,
        supply_air_temp=55.0,
        return_air_temp=75.0,
        ambient_temp=95.0,
    )
    
    # Run workflow
    context = workflow.process(telemetry)
    
    # Check result
    print(f"Workflow {context.workflow_id}:")
    print(f"  Decision: {context.final_decision}")
    print(f"  Confidence: {context.confidence:.0%}")
    print(f"  Duration: {context.get_duration_seconds():.2f}s")
    print(f"  Votes: {len(context.votes)}")
    
    return context
