"""
PDM Model Orchestrator - Multi-Agent Coordination for Predictive Maintenance

Orchestrates all PDM model agents to collaboratively determine maintenance outcomes.

Architecture:
                    ┌─────────────────────────────────────┐
                    │       PDMModelOrchestrator          │
                    │  (Coordinates all model agents)     │
                    └──────────────┬──────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
    ┌──────────┐            ┌──────────┐            ┌──────────┐
    │ Layer 0  │            │ Layer 1  │            │ Layer 2  │
    │ Context  │────────────│  Trust   │────────────│ Behavior │
    └──────────┘            └──────────┘            └──────────┘
          │                        │                        │
          │  RegimeDetectionAgent  │  SensorTrustAgent      │  BehaviorModelAgent
          │                        │                        │  ChangeDetectionAgent
          │                        │                        │
          └────────────────────────┼────────────────────────┘
                                   │
          ┌────────────────────────┼────────────────────────┐
          │                        │                        │
          ▼                        ▼                        ▼
    ┌──────────┐            ┌──────────┐            ┌──────────┐
    │ Layer 3  │            │ Layer 4  │            │ Existing │
    │ Diagnosis│────────────│ Decision │────────────│  Agents  │
    └──────────┘            └──────────┘            └──────────┘
          │                        │                        │
          │  FaultHypothesisAgent  │  DecisionPolicyAgent   │  CaseTriageAgent
          │                        │                        │  EvidenceToActionAgent
          │                        │                        │  WorkOrderComposerAgent
          │                        │                        │
          └────────────────────────┴────────────────────────┘

Agent Communication Protocol:
1. Layered Execution: Each layer completes before the next begins
2. Result Broadcasting: Each agent broadcasts results to downstream agents
3. Collaborative Voting: All agents vote on key decisions
4. Consensus Building: DecisionPolicyAgent aggregates votes and enforces constraints
"""

import logging
import asyncio
import uuid
from typing import Dict, List, Optional, Any, Tuple, Type
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import abstractmethod
from concurrent.futures import ThreadPoolExecutor

from .crewai_base import (
    DemandTwinAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
    BaseTool, AgentRegistry, BeliefState, CREWAI_AVAILABLE,
    Agent, Task, Crew, Process, AgentMessageBus, MessageType, AgentMessage
)
from .model_agents import (
    PDMModelAgent, PDMModelAgentRole, AgentAnalysisResult,
    AgentVote, AgentOpinion, CollaborativeDecision,
    RegimeDetectionAgent, SensorTrustAgent, BehaviorModelAgent,
    ChangeDetectionAgent, FaultHypothesisAgent, DecisionPolicyAgent,
)
from .workflow_agents import (
    PdMAgent, CaseTriageAgent, EvidenceToActionAgent, WorkOrderComposerAgent,
)
from ..integration.event_bus import (
    RedisEventBus, PdMEvent, PdMEventType, PdMEventFactory,
    EventHandler, InMemoryEventBus
)

logger = logging.getLogger(__name__)


# =============================================================================
# Orchestration Configuration
# =============================================================================

@dataclass
class OrchestratorConfig:
    """Configuration for the PDM Model Orchestrator"""
    # Consensus settings
    consensus_threshold: float = 0.6
    min_votes_for_decision: int = 3
    
    # Timing
    layer_timeout_seconds: float = 30.0
    total_timeout_seconds: float = 120.0
    
    # Agent weights (role -> weight multiplier)
    role_weights: Dict[PDMModelAgentRole, float] = field(default_factory=lambda: {
        PDMModelAgentRole.SENSOR_TRUST: 2.0,  # Critical for preventing false alarms
        PDMModelAgentRole.CHANGE_DETECTION: 1.5,  # Persistence is key
        PDMModelAgentRole.FAULT_HYPOTHESIS: 1.3,  # Diagnosis expertise
        PDMModelAgentRole.DECISION_POLICY: 1.5,  # Budget enforcement
        PDMModelAgentRole.REGIME_DETECTOR: 1.2,  # Context is foundational
        PDMModelAgentRole.BEHAVIOR_MODEL: 1.0,  # Standard weight
    })
    
    # Decision thresholds
    alert_confidence_threshold: float = 0.7
    dispatch_confidence_threshold: float = 0.85
    
    # Operational constraints
    max_alerts_per_day: int = 10
    max_dispatches_per_week: int = 3


@dataclass
class TelemetryInput:
    """Standardized telemetry input for orchestrator"""
    timestamp: datetime
    asset_id: str
    site_id: str
    
    # Operating state
    compressor_on: bool = False
    compressor_current: Optional[float] = None
    compressor_power: Optional[float] = None
    
    # Fans
    evap_fan_on: bool = False
    condenser_fan_on: bool = False
    supply_fan_speed: Optional[float] = None
    
    # Temperatures
    suction_line_temp: Optional[float] = None
    discharge_temp: Optional[float] = None
    supply_air_temp: Optional[float] = None
    return_air_temp: Optional[float] = None
    ambient_temp: Optional[float] = None
    
    # Pressures
    suction_pressure: Optional[float] = None
    discharge_pressure: Optional[float] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "asset_id": self.asset_id,
            "site_id": self.site_id,
            "compressor_on": self.compressor_on,
            "compressor_current": self.compressor_current,
            "compressor_power": self.compressor_power,
            "evap_fan_on": self.evap_fan_on,
            "condenser_fan_on": self.condenser_fan_on,
            "supply_fan_speed": self.supply_fan_speed,
            "suction_line_temp": self.suction_line_temp,
            "discharge_temp": self.discharge_temp,
            "supply_air_temp": self.supply_air_temp,
            "return_air_temp": self.return_air_temp,
            "ambient_temp": self.ambient_temp,
            "suction_pressure": self.suction_pressure,
            "discharge_pressure": self.discharge_pressure,
        }


@dataclass
class OrchestratorResult:
    """Result from a complete orchestration cycle"""
    result_id: str
    timestamp: datetime
    asset_id: str
    
    # Layer results
    layer_results: Dict[str, List[AgentAnalysisResult]]
    
    # Collaborative decision
    should_alert: bool
    alert_type: Optional[str]  # "watch", "action", "dispatch"
    decision: Optional[CollaborativeDecision]
    
    # Aggregated information
    regime: str
    sensor_trust: float
    change_detected: bool
    fault_hypothesis: Optional[str]
    fault_probability: float
    
    # Recommendations
    recommendations: List[str]
    concerns: List[str]
    evidence: List[Dict[str, Any]]
    
    # Metrics
    processing_time_ms: float
    agents_consulted: int
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "result_id": self.result_id,
            "timestamp": self.timestamp.isoformat(),
            "asset_id": self.asset_id,
            "should_alert": self.should_alert,
            "alert_type": self.alert_type,
            "regime": self.regime,
            "sensor_trust": self.sensor_trust,
            "change_detected": self.change_detected,
            "fault_hypothesis": self.fault_hypothesis,
            "fault_probability": self.fault_probability,
            "recommendations": self.recommendations,
            "concerns": self.concerns,
            "processing_time_ms": self.processing_time_ms,
            "agents_consulted": self.agents_consulted,
        }


# =============================================================================
# PDM Model Orchestrator
# =============================================================================

class PDMModelOrchestrator:
    """
    Orchestrates all PDM model agents to collaboratively determine maintenance outcomes.
    
    Key Responsibilities:
    1. Agent Lifecycle: Create, configure, and manage all model agents
    2. Layered Execution: Execute agents in proper dependency order
    3. Result Propagation: Pass results from upstream to downstream agents
    4. Collaborative Decision: Aggregate agent opinions for key decisions
    5. Constraint Enforcement: Apply operational and budget constraints
    """
    
    def __init__(
        self,
        site_id: str,
        config: Optional[OrchestratorConfig] = None,
        event_bus: Optional[RedisEventBus] = None,
        message_bus: Optional[AgentMessageBus] = None,
    ):
        self.site_id = site_id
        self.config = config or OrchestratorConfig()
        self.event_bus = event_bus or InMemoryEventBus(f"orchestrator_{site_id}")
        self.message_bus = message_bus or AgentMessageBus()
        
        # Initialize all model agents
        self._init_agents()
        
        # Result history
        self.result_history: List[OrchestratorResult] = []
        self.max_history = 1000
        
        # Metrics
        self.alerts_today = 0
        self.dispatches_this_week = 0
        self.last_reset_day = datetime.utcnow().date()
        self.last_reset_week = datetime.utcnow().isocalendar()[1]
        
        logger.info(f"PDMModelOrchestrator initialized for site {site_id}")
    
    def _init_agents(self):
        """Initialize all model agents in layers"""
        # Layer 0: Context
        self.regime_agent = RegimeDetectionAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        
        # Layer 1: Data Quality
        self.sensor_trust_agent = SensorTrustAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        
        # Layer 2: Behavioral Analysis
        self.behavior_agent = BehaviorModelAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        self.change_detection_agent = ChangeDetectionAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        
        # Layer 3: Diagnosis
        self.fault_hypothesis_agent = FaultHypothesisAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        
        # Layer 4: Decision
        self.decision_policy_agent = DecisionPolicyAgent(
            self.site_id, self.event_bus, message_bus=self.message_bus
        )
        
        # All model agents for voting
        self.model_agents: List[PDMModelAgent] = [
            self.regime_agent,
            self.sensor_trust_agent,
            self.behavior_agent,
            self.change_detection_agent,
            self.fault_hypothesis_agent,
            self.decision_policy_agent,
        ]
        
        # Wire up dependencies
        self._wire_agent_dependencies()
    
    def _wire_agent_dependencies(self):
        """Wire up agent dependencies for result propagation"""
        # Sensor trust depends on regime
        self.sensor_trust_agent.upstream_agents = [self.regime_agent.config.agent_id]
        
        # Behavior model depends on regime and trust
        self.behavior_agent.upstream_agents = [
            self.regime_agent.config.agent_id,
            self.sensor_trust_agent.config.agent_id,
        ]
        
        # Change detection depends on behavior
        self.change_detection_agent.upstream_agents = [
            self.behavior_agent.config.agent_id,
        ]
        
        # Fault hypothesis depends on change detection
        self.fault_hypothesis_agent.upstream_agents = [
            self.change_detection_agent.config.agent_id,
        ]
        
        # Decision policy depends on trust, change detection, fault hypothesis
        self.decision_policy_agent.upstream_agents = [
            self.sensor_trust_agent.config.agent_id,
            self.change_detection_agent.config.agent_id,
            self.fault_hypothesis_agent.config.agent_id,
        ]
        
        # Set downstream agents
        self.regime_agent.downstream_agents = [
            self.sensor_trust_agent.config.agent_id,
            self.behavior_agent.config.agent_id,
        ]
        self.sensor_trust_agent.downstream_agents = [
            self.behavior_agent.config.agent_id,
            self.decision_policy_agent.config.agent_id,
        ]
        self.behavior_agent.downstream_agents = [
            self.change_detection_agent.config.agent_id,
        ]
        self.change_detection_agent.downstream_agents = [
            self.fault_hypothesis_agent.config.agent_id,
            self.decision_policy_agent.config.agent_id,
        ]
        self.fault_hypothesis_agent.downstream_agents = [
            self.decision_policy_agent.config.agent_id,
        ]
    
    def process_telemetry(self, telemetry: TelemetryInput) -> OrchestratorResult:
        """
        Process telemetry through all agent layers.
        
        This is the main entry point for the multi-agent system.
        """
        start_time = datetime.utcnow()
        
        # Reset daily/weekly counters if needed
        self._reset_counters_if_needed()
        
        inputs = telemetry.to_dict()
        layer_results: Dict[str, List[AgentAnalysisResult]] = {}
        
        # =====================================================================
        # Layer 0: Regime Detection
        # =====================================================================
        regime_result = self.regime_agent.analyze(inputs)
        layer_results["layer_0_context"] = [regime_result]
        
        # Inject regime into inputs for subsequent layers
        inputs["regime"] = regime_result.result_data.get("regime", "unknown")
        inputs["is_steady_state"] = regime_result.result_data.get("is_steady_state", False)
        
        # =====================================================================
        # Layer 1: Sensor Trust
        # =====================================================================
        trust_result = self.sensor_trust_agent.analyze(inputs)
        layer_results["layer_1_trust"] = [trust_result]
        
        # Inject trust into inputs
        inputs["sensor_trust"] = trust_result.result_data.get("min_trust", 1.0)
        inputs["untrusted_sensors"] = trust_result.result_data.get("untrusted_sensors", [])
        
        # Early exit if sensors not trusted and not in steady state
        if (trust_result.result_data.get("min_trust", 1.0) < 0.5 or
            not regime_result.result_data.get("is_steady_state", False)):
            # Continue processing but note concerns
            pass
        
        # =====================================================================
        # Layer 2: Behavioral Analysis
        # =====================================================================
        behavior_result = self.behavior_agent.analyze(inputs)
        layer_results["layer_2_behavior"] = [behavior_result]
        
        # Pass residuals to change detection
        inputs["residuals"] = behavior_result.result_data.get("residuals", {})
        
        change_result = self.change_detection_agent.analyze(inputs)
        layer_results["layer_2_behavior"].append(change_result)
        
        # =====================================================================
        # Layer 3: Fault Diagnosis
        # =====================================================================
        # Combine results for fault hypothesis
        inputs["change_detections"] = change_result.result_data.get("change_results", {})
        inputs["telemetry"] = telemetry.to_dict()
        
        fault_result = self.fault_hypothesis_agent.analyze(inputs)
        layer_results["layer_3_diagnosis"] = [fault_result]
        
        # =====================================================================
        # Layer 4: Collaborative Decision
        # =====================================================================
        # Prepare decision context
        decision_context = {
            "regime": regime_result.result_data.get("regime"),
            "sensor_trust": trust_result.result_data.get("min_trust", 1.0),
            "changes_detected": change_result.result_data.get("changes_detected", []),
            "fault_hypothesis": fault_result.result_data.get("top_fault"),
            "fault_probability": fault_result.result_data.get("top_probability", 0),
            "is_confident": fault_result.result_data.get("is_confident", False),
            "false_alarm_probability": 1 - trust_result.result_data.get("min_trust", 1.0),
            "confidence": fault_result.result_data.get("top_probability", 0),
        }
        
        # Collaborative vote: Should we alert?
        alert_decision = self.decision_policy_agent.make_collaborative_decision(
            question="should_alert: generate an alert for this asset?",
            context=decision_context,
            voting_agents=self.model_agents,
            consensus_threshold=self.config.consensus_threshold,
        )
        
        layer_results["layer_4_decision"] = [
            self.decision_policy_agent.analyze(inputs)
        ]
        
        # =====================================================================
        # Determine Alert Type
        # =====================================================================
        should_alert, alert_type = self._determine_alert_type(
            alert_decision, decision_context
        )
        
        # Apply operational constraints
        should_alert, alert_type = self._apply_operational_constraints(
            should_alert, alert_type
        )
        
        # =====================================================================
        # Build Result
        # =====================================================================
        processing_time = (datetime.utcnow() - start_time).total_seconds() * 1000
        
        # Aggregate recommendations and concerns
        all_recommendations = []
        all_concerns = []
        all_evidence = []
        
        for layer, results in layer_results.items():
            for result in results:
                all_recommendations.extend(result.recommendations)
                all_concerns.extend(result.concerns)
        
        # Add evidence from votes
        if alert_decision:
            for vote in alert_decision.votes:
                all_evidence.extend(vote.evidence)
        
        result = OrchestratorResult(
            result_id=str(uuid.uuid4()),
            timestamp=datetime.utcnow(),
            asset_id=telemetry.asset_id,
            layer_results=layer_results,
            should_alert=should_alert,
            alert_type=alert_type,
            decision=alert_decision,
            regime=regime_result.result_data.get("regime", "unknown"),
            sensor_trust=trust_result.result_data.get("min_trust", 1.0),
            change_detected=len(change_result.result_data.get("changes_detected", [])) > 0,
            fault_hypothesis=fault_result.result_data.get("top_fault"),
            fault_probability=fault_result.result_data.get("top_probability", 0),
            recommendations=list(set(all_recommendations)),
            concerns=list(set(all_concerns)),
            evidence=all_evidence,
            processing_time_ms=processing_time,
            agents_consulted=len(self.model_agents),
        )
        
        # Track metrics
        if should_alert:
            self.alerts_today += 1
            if alert_type == "dispatch":
                self.dispatches_this_week += 1
        
        self.result_history.append(result)
        if len(self.result_history) > self.max_history:
            self.result_history = self.result_history[-self.max_history // 2:]
        
        return result
    
    def _determine_alert_type(
        self,
        decision: CollaborativeDecision,
        context: Dict[str, Any],
    ) -> Tuple[bool, Optional[str]]:
        """Determine if and what type of alert to generate"""
        if decision.final_decision != "proceed":
            return False, None
        
        confidence = decision.aggregate_confidence
        is_confident = context.get("is_confident", False)
        fault_prob = context.get("fault_probability", 0)
        
        if confidence >= self.config.dispatch_confidence_threshold and is_confident:
            return True, "dispatch"
        elif confidence >= self.config.alert_confidence_threshold:
            return True, "action"
        elif confidence >= 0.5:
            return True, "watch"
        else:
            return False, None
    
    def _apply_operational_constraints(
        self,
        should_alert: bool,
        alert_type: Optional[str],
    ) -> Tuple[bool, Optional[str]]:
        """Apply operational constraints (alert/dispatch limits)"""
        if not should_alert:
            return should_alert, alert_type
        
        # Check daily alert limit
        if self.alerts_today >= self.config.max_alerts_per_day:
            if alert_type in ["watch", "action"]:
                logger.warning(f"Daily alert limit reached ({self.config.max_alerts_per_day}). Suppressing {alert_type} alert.")
                return False, None
            # Allow dispatch even at limit for critical issues
        
        # Check weekly dispatch limit
        if alert_type == "dispatch":
            if self.dispatches_this_week >= self.config.max_dispatches_per_week:
                logger.warning(f"Weekly dispatch limit reached ({self.config.max_dispatches_per_week}). Downgrading to action.")
                return True, "action"
        
        return should_alert, alert_type
    
    def _reset_counters_if_needed(self):
        """Reset daily/weekly counters"""
        now = datetime.utcnow()
        
        if now.date() != self.last_reset_day:
            self.alerts_today = 0
            self.last_reset_day = now.date()
        
        if now.isocalendar()[1] != self.last_reset_week:
            self.dispatches_this_week = 0
            self.last_reset_week = now.isocalendar()[1]
    
    def get_agent_status(self) -> Dict[str, Any]:
        """Get status of all agents"""
        return {
            agent.config.agent_id: {
                "role": agent.model_role.value,
                "history_size": len(agent.analysis_history),
                "latest_result": agent.get_latest_result().to_dict() if agent.get_latest_result() else None,
            }
            for agent in self.model_agents
        }
    
    def get_orchestrator_metrics(self) -> Dict[str, Any]:
        """Get orchestrator metrics"""
        return {
            "site_id": self.site_id,
            "total_processed": len(self.result_history),
            "alerts_today": self.alerts_today,
            "dispatches_this_week": self.dispatches_this_week,
            "agents_count": len(self.model_agents),
            "avg_processing_time_ms": (
                sum(r.processing_time_ms for r in self.result_history[-100:]) / 
                min(len(self.result_history), 100)
            ) if self.result_history else 0,
        }


# =============================================================================
# CrewAI Integration: Collaborative Decision Crew
# =============================================================================

class PDMDecisionCrew:
    """
    CrewAI Crew for multi-agent maintenance decision making.
    
    Wraps the PDMModelOrchestrator in a CrewAI Crew for advanced
    multi-agent collaboration patterns.
    """
    
    def __init__(
        self,
        site_id: str,
        orchestrator: Optional[PDMModelOrchestrator] = None,
    ):
        self.site_id = site_id
        self.orchestrator = orchestrator or PDMModelOrchestrator(site_id)
        
        if CREWAI_AVAILABLE:
            self._init_crew()
        else:
            logger.warning("CrewAI not available. Using basic orchestrator only.")
            self.crew = None
    
    def _init_crew(self):
        """Initialize CrewAI Crew for advanced collaboration"""
        # Convert our model agents to CrewAI agents
        crew_agents = []
        
        for agent in self.orchestrator.model_agents:
            if CREWAI_AVAILABLE:
                crew_agent = Agent(
                    role=agent.config.role.value,
                    goal=agent.config.goal,
                    backstory=agent.config.backstory,
                    allow_delegation=True,
                    verbose=False,
                )
                crew_agents.append(crew_agent)
        
        if CREWAI_AVAILABLE and crew_agents:
            self.crew = Crew(
                agents=crew_agents,
                process=Process.hierarchical,
                verbose=False,
            )
        else:
            self.crew = None
    
    def process(self, telemetry: TelemetryInput) -> OrchestratorResult:
        """Process telemetry through the multi-agent system"""
        return self.orchestrator.process_telemetry(telemetry)


# =============================================================================
# Integration with Existing PDM Agents
# =============================================================================

class IntegratedPDMOrchestrator(PDMModelOrchestrator):
    """
    Extended orchestrator that integrates with existing PDM workflow agents.
    
    Combines:
    - New model agents (Layers 0-4): Analysis and decision
    - Existing workflow agents: Case triage, evidence, work orders
    """
    
    def __init__(
        self,
        site_id: str,
        config: Optional[OrchestratorConfig] = None,
        event_bus: Optional[RedisEventBus] = None,
    ):
        super().__init__(site_id, config, event_bus)
        
        # Initialize existing workflow agents
        self.case_triage_agent = CaseTriageAgent(self.event_bus)
        self.evidence_agent = EvidenceToActionAgent(self.event_bus)
        self.work_order_agent = WorkOrderComposerAgent(self.event_bus)
        
        self.workflow_agents = [
            self.case_triage_agent,
            self.evidence_agent,
            self.work_order_agent,
        ]
    
    def process_with_workflow(self, telemetry: TelemetryInput) -> Dict[str, Any]:
        """
        Process telemetry through model agents and workflow agents.
        
        Flow:
        1. Model agents analyze and decide on alert
        2. If alert, workflow agents handle case creation and work order
        """
        # Run model agent analysis
        result = self.process_telemetry(telemetry)
        
        workflow_result = {
            "analysis_result": result.to_dict(),
            "case_created": False,
            "work_order_created": False,
        }
        
        if not result.should_alert:
            return workflow_result
        
        # Create case event for workflow agents
        case_event = self._create_case_event(result)
        
        # Workflow agents handle case
        if result.alert_type in ["action", "dispatch"]:
            # Triage the case
            triage_result = self.case_triage_agent.handle(case_event)
            workflow_result["case_created"] = True
            workflow_result["triage_decision"] = triage_result.payload if triage_result else None
            
            # Generate maintenance packet
            if triage_result:
                packet_result = self.evidence_agent.handle(triage_result)
                workflow_result["maintenance_packet"] = packet_result.payload if packet_result else None
            
            # Create work order for dispatches
            if result.alert_type == "dispatch":
                workflow_result["work_order_created"] = True
        
        return workflow_result
    
    def _create_case_event(self, result: OrchestratorResult) -> PdMEvent:
        """Create a case event from analysis result"""
        factory = PdMEventFactory(f"orchestrator_{self.site_id}")
        
        return factory.case_created(
            case_id=result.result_id,
            alert_id=result.result_id,
            ev_score=result.fault_probability * 100,
            severity="high" if result.alert_type == "dispatch" else "medium",
            trigger_metrics={
                "fault_hypothesis": result.fault_hypothesis,
                "sensor_trust": result.sensor_trust,
                "change_detected": result.change_detected,
            },
        )


# =============================================================================
# Factory Functions
# =============================================================================

def create_pdm_orchestrator(
    site_id: str,
    config: Optional[OrchestratorConfig] = None,
    integrated: bool = True,
) -> PDMModelOrchestrator:
    """Create a PDM Model Orchestrator for a site"""
    if integrated:
        return IntegratedPDMOrchestrator(site_id, config)
    else:
        return PDMModelOrchestrator(site_id, config)


def create_pdm_decision_crew(site_id: str) -> PDMDecisionCrew:
    """Create a PDM Decision Crew for advanced multi-agent collaboration"""
    return PDMDecisionCrew(site_id)
