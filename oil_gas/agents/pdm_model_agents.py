"""
PDM Model Agents - CrewAI Agents for Each Analytical Model

Each model in the PDM pipeline is managed by a specialized agent.
Agents collaborate through structured protocols to determine maintenance outcomes.

Agent Architecture (Layered):

Layer 0 - Context Agents:
  - RegimeDetectionAgent: Determines operating regime
  - ContextBuilderAgent: Builds environmental/operational context

Layer 1 - Data Quality Agents:
  - SensorTrustAgent: Evaluates sensor data trustworthiness
  - DataQualityAgent: Overall data quality assessment

Layer 2 - Behavioral Analysis Agents:
  - BehaviorModelAgent: Predicts expected values per regime
  - ResidualAnalysisAgent: Models residual error distributions
  - ChangeDetectionAgent: Detects persistent changes (CUSUM/GLR)

Layer 3 - Diagnostic Agents:
  - FaultHypothesisAgent: Bayesian fault diagnosis
  - EnergyImpactAgent: Energy penalty estimation
  - ComfortImpactAgent: Comfort impact estimation

Layer 4 - Decision Agents:
  - DecisionPolicyAgent: Enforces FA budget, makes alarm decisions
  - MaintenanceRecommendationAgent: Generates recommendations

Orchestration:
  - PDMModelOrchestrator: Coordinates all model agents
  - CollaborativeDecisionCrew: CrewAI Crew for multi-agent decision making
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import abstractmethod

from shared.agents.crewai_base import (
    DemandTwinAgent, CrewAIAgentConfig, AgentCategory, AgentRole,
    BaseTool, AgentRegistry, BeliefState, CREWAI_AVAILABLE,
    Agent, Task, Crew, Process, AgentMessageBus, MessageType, AgentMessage
)
from .redis_event_bus import (
    RedisEventBus, PdMEvent, PdMEventType, PdMEventFactory,
    EventHandler, InMemoryEventBus
)

logger = logging.getLogger(__name__)


# =============================================================================
# Extended Agent Roles for PDM Models
# =============================================================================

class PDMModelAgentRole(str, Enum):
    """Agent roles for PDM model management"""
    # Layer 0 - Context
    REGIME_DETECTOR = "regime_detector"
    CONTEXT_BUILDER = "context_builder"
    
    # Layer 1 - Data Quality
    SENSOR_TRUST = "sensor_trust"
    DATA_QUALITY = "data_quality"
    
    # Layer 2 - Behavioral Analysis
    BEHAVIOR_MODEL = "behavior_model"
    RESIDUAL_ANALYSIS = "residual_analysis"
    CHANGE_DETECTION = "change_detection"
    
    # Layer 3 - Diagnostics
    FAULT_HYPOTHESIS = "fault_hypothesis"
    ENERGY_IMPACT = "energy_impact"
    COMFORT_IMPACT = "comfort_impact"
    
    # Layer 4 - Decision
    DECISION_POLICY = "decision_policy"
    MAINTENANCE_RECOMMENDATION = "maintenance_recommendation"
    
    # Orchestration
    MODEL_ORCHESTRATOR = "model_orchestrator"


# =============================================================================
# Agent Communication Protocol
# =============================================================================

class AgentOpinion(str, Enum):
    """Agent opinions for collaborative decision-making"""
    STRONGLY_AGREE = "strongly_agree"
    AGREE = "agree"
    NEUTRAL = "neutral"
    DISAGREE = "disagree"
    STRONGLY_DISAGREE = "strongly_disagree"
    ABSTAIN = "abstain"


@dataclass
class AgentVote:
    """Vote from an agent on a decision"""
    agent_id: str
    agent_role: PDMModelAgentRole
    opinion: AgentOpinion
    confidence: float  # [0, 1]
    rationale: str
    evidence: List[Dict[str, Any]] = field(default_factory=list)
    weight: float = 1.0  # Agent's voting weight
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class CollaborativeDecision:
    """Result of collaborative agent decision-making"""
    decision_id: str
    question: str
    votes: List[AgentVote]
    consensus_reached: bool
    consensus_threshold: float
    final_decision: str
    aggregate_confidence: float
    dissenting_agents: List[str]
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AgentAnalysisResult:
    """Standardized result from any model agent's analysis"""
    agent_id: str
    agent_role: PDMModelAgentRole
    timestamp: datetime
    
    # Core result
    result_type: str  # e.g., "regime_state", "trust_score", "fault_hypothesis"
    result_data: Dict[str, Any]
    
    # Confidence and uncertainty
    confidence: float
    uncertainty: Dict[str, float] = field(default_factory=dict)
    
    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # agent_ids this result depends on
    
    # Recommendations
    recommendations: List[str] = field(default_factory=list)
    concerns: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "agent_role": self.agent_role.value,
            "timestamp": self.timestamp.isoformat(),
            "result_type": self.result_type,
            "result_data": self.result_data,
            "confidence": self.confidence,
            "recommendations": self.recommendations,
            "concerns": self.concerns,
        }


# =============================================================================
# Base PDM Model Agent
# =============================================================================

class PDMModelAgent(DemandTwinAgent, EventHandler):
    """
    Base class for PDM Model Agents.
    
    Each agent manages a specific model/service in the PDM pipeline.
    Agents communicate analysis results and collaborate on decisions.
    """
    
    def __init__(
        self,
        config: CrewAIAgentConfig,
        model_role: PDMModelAgentRole,
        event_bus: Optional[RedisEventBus] = None,
        message_bus: Optional[AgentMessageBus] = None,
        **kwargs
    ):
        super().__init__(config, message_bus, **kwargs)
        self.model_role = model_role
        self.event_bus = event_bus or InMemoryEventBus(config.agent_id)
        self.event_factory = PdMEventFactory(config.agent_id)
        
        # Register as event handler
        self.event_bus.register_handler(self)
        
        # Analysis results history
        self.analysis_history: List[AgentAnalysisResult] = []
        self.max_history = 1000
        
        # Collaboration state
        self.pending_votes: Dict[str, AgentVote] = {}
        self.received_results: Dict[str, AgentAnalysisResult] = {}
        
        # Layer dependencies
        self.upstream_agents: List[str] = []  # Agents this agent depends on
        self.downstream_agents: List[str] = []  # Agents that depend on this agent
    
    @property
    @abstractmethod
    def handled_event_types(self) -> List[PdMEventType]:
        """Event types this agent handles"""
        pass
    
    @abstractmethod
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Perform the agent's primary analysis"""
        pass
    
    @abstractmethod
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Cast a vote on a collaborative decision"""
        pass
    
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """Handle incoming events"""
        # Subclasses implement specific handling
        return None
    
    def receive_upstream_result(self, result: AgentAnalysisResult):
        """Receive analysis result from an upstream agent"""
        self.received_results[result.agent_id] = result
    
    def broadcast_result(self, result: AgentAnalysisResult):
        """Broadcast analysis result to downstream agents"""
        self.analysis_history.append(result)
        if len(self.analysis_history) > self.max_history:
            self.analysis_history = self.analysis_history[-self.max_history // 2:]
        
        # Send to downstream agents via message bus
        if self.message_bus:
            for agent_id in self.downstream_agents:
                message = AgentMessage(
                    sender_id=self.config.agent_id,
                    receiver_id=agent_id,
                    message_type=MessageType.RESULT,
                    content=result.to_dict(),
                )
                self.message_bus.send(message)
    
    def get_latest_result(self) -> Optional[AgentAnalysisResult]:
        """Get the most recent analysis result"""
        return self.analysis_history[-1] if self.analysis_history else None


# =============================================================================
# Layer 0: Context Agents
# =============================================================================

class RegimeDetectionAgent(PDMModelAgent):
    """
    Regime Detection Agent
    
    Determines operating regime (OFF, STARTUP, STEADY_COOL, DEFROST, etc.)
    This is the foundation - all other analysis is regime-aware.
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"regime_detection_{site_id}",
            role=AgentRole.DATA_STEWARD,
            category=AgentCategory.DATA,
            name="Regime Detection Specialist",
            goal="Accurately classify equipment operating regime to enable regime-aware analysis and prevent false positives from comparing different operating modes.",
            backstory="""You are an expert in HVAC/R system dynamics who understands that equipment 
            behaves fundamentally differently during startup, steady-state, defrost, and shutdown. 
            You recognize that comparing a startup transient to steady-state operation leads to 
            false alarms, and you classify regimes to prevent this confusion.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.REGIME_DETECTOR, event_bus, **kwargs)
        
        self.site_id = site_id
        self.current_regime = "unknown"
        self.regime_history: List[Dict[str, Any]] = []
        
        # Import the actual service
        from oil_gas.pdm_regime_service import RegimeSegmentationService
        self.regime_service = RegimeSegmentationService(site_id)
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.TELEMETRY_RECEIVED]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Classify current operating regime"""
        from oil_gas.pdm_regime_service import TelemetrySnapshot
        
        # Build snapshot from inputs
        snapshot = TelemetrySnapshot(
            timestamp=inputs.get("timestamp", datetime.utcnow()),
            asset_id=inputs.get("asset_id", self.site_id),
            compressor_on=inputs.get("compressor_on", False),
            compressor_current=inputs.get("compressor_current"),
            compressor_power=inputs.get("compressor_power"),
            evap_fan_on=inputs.get("evap_fan_on", False),
            condenser_fan_on=inputs.get("condenser_fan_on", False),
            supply_fan_speed=inputs.get("supply_fan_speed"),
            suction_temp=inputs.get("suction_line_temp"),
            discharge_temp=inputs.get("discharge_temp"),
            supply_air_temp=inputs.get("supply_air_temp"),
            return_air_temp=inputs.get("return_air_temp"),
            ambient_temp=inputs.get("ambient_temp"),
            suction_pressure=inputs.get("suction_pressure"),
            discharge_pressure=inputs.get("discharge_pressure"),
        )
        
        # Classify regime
        regime_state = self.regime_service.classify_regime(snapshot)
        self.current_regime = regime_state.regime.value
        
        result = AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="regime_state",
            result_data={
                "regime": regime_state.regime.value,
                "confidence": regime_state.confidence,
                "duration_seconds": regime_state.duration_seconds,
                "is_steady_state": self.regime_service.is_steady_state(),
                "previous_regime": regime_state.previous_regime.value if regime_state.previous_regime else None,
            },
            confidence=regime_state.confidence,
            recommendations=[
                "Proceed with regime-aware analysis" if regime_state.confidence > 0.7
                else "Low regime confidence - interpret results cautiously"
            ],
            concerns=[
                "System in transient regime - defer behavioral analysis"
            ] if not self.regime_service.is_steady_state() else [],
        )
        
        self.broadcast_result(result)
        return result
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Vote on whether to proceed with analysis given current regime"""
        is_steady = self.regime_service.is_steady_state()
        regime_state = self.regime_service.get_current_state()
        
        if "should_alert" in question.lower():
            if not is_steady:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.9,
                    rationale=f"System is in {self.current_regime} regime (transient). Defer alerting until steady-state.",
                    weight=1.5,  # High weight for regime considerations
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=regime_state.confidence if regime_state else 0.5,
                    rationale=f"System is in {self.current_regime} (steady-state). Regime analysis supports proceeding.",
                    weight=1.0,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Question not in regime agent's domain.",
            weight=0.0,
        )


# =============================================================================
# Layer 1: Sensor Trust Agent
# =============================================================================

class SensorTrustAgent(PDMModelAgent):
    """
    Sensor Trust Agent
    
    Layer 1 of three-layer inference: "Do I trust this sensor stream right now?"
    Prevents "bad telemetry = fault alarm" - the primary source of false positives.
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"sensor_trust_{site_id}",
            role=AgentRole.DATA_VALIDATOR,
            category=AgentCategory.DATA,
            name="Sensor Trust Evaluator",
            goal="Evaluate sensor data trustworthiness to prevent false alarms from sensor issues. Distinguish between equipment faults and sensor problems.",
            backstory="""You are a sensor calibration expert who has seen thousands of false alarms 
            caused by drifting sensors, stuck readings, and communication glitches. You know that 
            the first question to ask is not 'What's wrong with the equipment?' but 'Can I trust 
            this data?' You save countless unnecessary truck rolls by catching sensor issues first.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.SENSOR_TRUST, event_bus, **kwargs)
        
        self.site_id = site_id
        self.upstream_agents = [f"regime_detection_{site_id}"]
        
        # Import the actual service
        from oil_gas.pdm_sensor_trust_service import SensorTrustService
        self.trust_service = SensorTrustService(site_id)
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.TELEMETRY_RECEIVED]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Evaluate sensor trustworthiness"""
        from oil_gas.pdm_sensor_trust_service import SensorReading
        from oil_gas.pdm_schemas import SensorType
        
        timestamp = inputs.get("timestamp", datetime.utcnow())
        trust_scores = {}
        untrusted_sensors = []
        concerns = []
        
        # Process each sensor reading
        sensor_mapping = {
            "suction_pressure": SensorType.SUCTION_PRESSURE,
            "discharge_pressure": SensorType.DISCHARGE_PRESSURE,
            "suction_line_temp": SensorType.SUCTION_LINE_TEMP,
            "compressor_current": SensorType.COMPRESSOR_CURRENT,
            "supply_air_temp": SensorType.SUPPLY_AIR_TEMP,
            "return_air_temp": SensorType.RETURN_AIR_TEMP,
            "ambient_temp": SensorType.AMBIENT_TEMP,
        }
        
        for key, sensor_type in sensor_mapping.items():
            if key in inputs and inputs[key] is not None:
                reading = SensorReading(
                    timestamp=timestamp,
                    sensor_id=f"{self.site_id}_{key}",
                    sensor_type=sensor_type,
                    value=float(inputs[key]),
                )
                trust = self.trust_service.process_reading(reading)
                trust_scores[key] = trust.trust_score
                
                if not trust.is_trusted():
                    untrusted_sensors.append(key)
                    if trust.stuck_likelihood > 0.5:
                        concerns.append(f"{key} appears stuck (likelihood: {trust.stuck_likelihood:.0%})")
                    if trust.drift_likelihood > 0.3:
                        concerns.append(f"{key} may be drifting (likelihood: {trust.drift_likelihood:.0%})")
        
        min_trust = min(trust_scores.values()) if trust_scores else 1.0
        
        result = AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="sensor_trust",
            result_data={
                "trust_scores": trust_scores,
                "min_trust": min_trust,
                "untrusted_sensors": untrusted_sensors,
                "all_trusted": len(untrusted_sensors) == 0,
            },
            confidence=min_trust,
            depends_on=self.upstream_agents,
            recommendations=[
                "Proceed with analysis" if len(untrusted_sensors) == 0
                else f"Verify sensors before diagnosis: {', '.join(untrusted_sensors)}"
            ],
            concerns=concerns,
        )
        
        self.broadcast_result(result)
        return result
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Vote on decisions based on sensor trustworthiness"""
        all_trust = self.trust_service.get_all_trust_scores()
        min_trust = min([t.trust_score for t in all_trust.values()], default=1.0)
        untrusted = self.trust_service.get_untrusted_sensors()
        
        if "should_alert" in question.lower() or "should_dispatch" in question.lower():
            if min_trust < 0.5:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.STRONGLY_DISAGREE,
                    confidence=0.95,
                    rationale=f"Sensor trust too low ({min_trust:.0%}). Likely sensor issue, not equipment fault. Untrusted: {untrusted[:3]}",
                    weight=2.0,  # Very high weight - sensor trust is critical
                )
            elif min_trust < 0.8:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.7,
                    rationale=f"Sensor trust marginal ({min_trust:.0%}). Recommend sensor verification before maintenance dispatch.",
                    weight=1.5,
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=min_trust,
                    rationale=f"All sensors trusted ({min_trust:.0%}). Sensor data supports analysis.",
                    weight=1.0,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Question not in sensor trust domain.",
            weight=0.0,
        )


# =============================================================================
# Layer 2: Behavioral Analysis Agents
# =============================================================================

class BehaviorModelAgent(PDMModelAgent):
    """
    Behavior Model Agent
    
    Predicts expected values under current regime/context.
    Uses hierarchical model (global + per-unit fingerprint).
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"behavior_model_{site_id}",
            role=AgentRole.FORECASTER,
            category=AgentCategory.ANALYTICS,
            name="Behavioral Prediction Specialist",
            goal="Predict expected equipment behavior under current operating conditions to enable accurate residual analysis.",
            backstory="""You are an HVAC/R performance modeling expert who understands the physics 
            of refrigeration cycles and air handling. You know that expected behavior varies with 
            ambient temperature, load, and operating regime. You build accurate predictions that 
            serve as the baseline for detecting true deviations.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.BEHAVIOR_MODEL, event_bus, **kwargs)
        
        self.site_id = site_id
        self.upstream_agents = [f"regime_detection_{site_id}", f"sensor_trust_{site_id}"]
        
        # Import services
        from oil_gas.pdm_residual_service import BehaviorModelService
        from oil_gas.pdm_fingerprint_service import EquipmentFingerprintService
        
        self.behavior_service = BehaviorModelService(site_id)
        self.fingerprint_service = EquipmentFingerprintService(site_id)
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.TELEMETRY_RECEIVED]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Predict expected values and compute residuals"""
        from oil_gas.pdm_schemas import SensorType, OperatingRegime
        
        timestamp = inputs.get("timestamp", datetime.utcnow())
        regime_str = inputs.get("regime", "unknown")
        try:
            regime = OperatingRegime(regime_str)
        except ValueError:
            regime = OperatingRegime.UNKNOWN
        
        # Build context
        context = {
            "ambient_temp": inputs.get("ambient_temp", 70.0),
            "load_proxy": inputs.get("load_proxy", 0.5),
            "return_air_temp": inputs.get("return_air_temp"),
        }
        
        predictions = {}
        residuals = {}
        
        sensor_mapping = {
            "suction_pressure": SensorType.SUCTION_PRESSURE,
            "discharge_pressure": SensorType.DISCHARGE_PRESSURE,
            "compressor_current": SensorType.COMPRESSOR_CURRENT,
        }
        
        for key, sensor_type in sensor_mapping.items():
            if key in inputs and inputs[key] is not None:
                # Get prediction using hierarchical model
                pred, uncertainty = self.fingerprint_service.predict_hierarchical(
                    sensor_type, regime, context
                )
                predictions[key] = {"predicted": pred, "uncertainty": uncertainty}
                
                # Compute residual
                observed = inputs[key]
                residual = observed - pred
                residuals[key] = {
                    "observed": observed,
                    "predicted": pred,
                    "residual": residual,
                    "z_score": residual / (uncertainty + 0.01),
                }
                
                # Update models
                self.behavior_service.update_with_observation(
                    observed, sensor_type, regime, context
                )
                self.fingerprint_service.observe(sensor_type, regime, observed, context)
        
        # Check for significant deviations
        significant_deviations = [
            k for k, v in residuals.items() if abs(v.get("z_score", 0)) > 2.0
        ]
        
        result = AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="behavior_prediction",
            result_data={
                "regime": regime.value,
                "predictions": predictions,
                "residuals": residuals,
                "significant_deviations": significant_deviations,
                "fingerprint_confidence": self.fingerprint_service.local_adaptation.adaptation_confidence,
            },
            confidence=self.fingerprint_service.local_adaptation.adaptation_confidence,
            depends_on=self.upstream_agents,
            recommendations=[
                f"Significant deviations in: {', '.join(significant_deviations)}"
            ] if significant_deviations else ["Behavior within expected range"],
            concerns=[],
        )
        
        self.broadcast_result(result)
        return result
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Vote based on behavioral predictions"""
        latest = self.get_latest_result()
        if not latest:
            return AgentVote(
                agent_id=self.config.agent_id,
                agent_role=self.model_role,
                opinion=AgentOpinion.ABSTAIN,
                confidence=0.0,
                rationale="No behavior analysis available.",
                weight=0.0,
            )
        
        deviations = latest.result_data.get("significant_deviations", [])
        
        if "should_alert" in question.lower():
            if len(deviations) >= 2:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.AGREE,
                    confidence=0.7,
                    rationale=f"Multiple behavioral deviations detected: {deviations}. Equipment not behaving as expected.",
                    evidence=[{"deviations": deviations}],
                    weight=1.2,
                )
            elif len(deviations) == 1:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=0.5,
                    rationale=f"Single deviation in {deviations[0]}. May need more evidence.",
                    weight=0.8,
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.8,
                    rationale="Behavior within expected range. No significant deviations.",
                    weight=1.0,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Question not in behavior model domain.",
            weight=0.0,
        )


class ChangeDetectionAgent(PDMModelAgent):
    """
    Change Detection Agent
    
    Runs sequential change detection (CUSUM/GLR) on residual streams.
    Detects PERSISTENT changes, not point anomalies.
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"change_detection_{site_id}",
            role=AgentRole.ANOMALY_DETECTOR,
            category=AgentCategory.ANALYTICS,
            name="Sequential Change Detection Specialist",
            goal="Detect persistent behavioral changes using statistical methods (CUSUM/GLR). Distinguish true equipment degradation from transient noise.",
            backstory="""You are a signal processing expert trained in radar detection theory. 
            You know that a single spike is not an alarm - what matters is persistent deviation. 
            You use CUSUM and GLR to detect when a system is 'no longer behaving like itself' 
            rather than flagging every unusual reading.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.CHANGE_DETECTION, event_bus, **kwargs)
        
        self.site_id = site_id
        self.upstream_agents = [f"behavior_model_{site_id}"]
        
        # Import service
        from oil_gas.pdm_change_detection_service import SequentialChangeDetectionService
        self.change_service = SequentialChangeDetectionService(site_id)
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.ANALYSIS_COMPLETE]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Run change detection on residuals"""
        from oil_gas.pdm_schemas import OperatingRegime, SensorType, ResidualObservation
        
        timestamp = inputs.get("timestamp", datetime.utcnow())
        regime_str = inputs.get("regime", "unknown")
        try:
            regime = OperatingRegime(regime_str)
        except ValueError:
            regime = OperatingRegime.UNKNOWN
        
        residuals = inputs.get("residuals", {})
        sensor_trust = inputs.get("sensor_trust", 1.0)
        
        change_results = {}
        changes_detected = []
        
        for sensor_key, residual_data in residuals.items():
            # Create residual observation
            obs = ResidualObservation(
                timestamp=timestamp,
                sensor_id=f"{self.site_id}_{sensor_key}",
                sensor_type=SensorType.SUCTION_PRESSURE,  # Would map properly
                regime=regime,
                observed=residual_data.get("observed", 0),
                predicted=residual_data.get("predicted", 0),
                residual=residual_data.get("residual", 0),
                z_score=residual_data.get("z_score"),
            )
            
            # Process through change detector
            detection = self.change_service.process_observation(obs, regime, sensor_trust)
            
            change_results[sensor_key] = {
                "change_detected": detection.change_detected,
                "change_score": detection.change_score,
                "duration_hours": detection.anomaly_duration_hours,
                "n_regimes_observed": detection.n_regimes_observed,
                "stability_score": detection.stability_score,
            }
            
            if detection.change_detected:
                changes_detected.append(sensor_key)
        
        result = AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="change_detection",
            result_data={
                "change_results": change_results,
                "changes_detected": changes_detected,
                "any_change": len(changes_detected) > 0,
                "max_persistence_hours": max(
                    [r["duration_hours"] for r in change_results.values()], default=0
                ),
            },
            confidence=0.8 if len(changes_detected) > 0 else 0.9,
            depends_on=self.upstream_agents,
            recommendations=[
                f"Persistent changes in: {', '.join(changes_detected)}. Proceed to diagnosis."
            ] if changes_detected else ["No persistent changes. Continue monitoring."],
            concerns=[],
        )
        
        self.broadcast_result(result)
        return result
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Vote based on change detection results"""
        latest = self.get_latest_result()
        if not latest:
            return AgentVote(
                agent_id=self.config.agent_id,
                agent_role=self.model_role,
                opinion=AgentOpinion.ABSTAIN,
                confidence=0.0,
                rationale="No change detection analysis available.",
                weight=0.0,
            )
        
        changes = latest.result_data.get("changes_detected", [])
        max_persistence = latest.result_data.get("max_persistence_hours", 0)
        
        if "should_alert" in question.lower():
            if len(changes) > 0 and max_persistence >= 6.0:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.STRONGLY_AGREE,
                    confidence=0.9,
                    rationale=f"Persistent change detected for {max_persistence:.1f} hours in {changes}. This is not transient noise.",
                    evidence=[{"changes": changes, "persistence_hours": max_persistence}],
                    weight=1.5,
                )
            elif len(changes) > 0:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=0.6,
                    rationale=f"Change detected but persistence only {max_persistence:.1f} hours. Need more observation.",
                    weight=1.0,
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.85,
                    rationale="No persistent changes detected. Point anomalies do not warrant alerting.",
                    weight=1.3,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Question not in change detection domain.",
            weight=0.0,
        )


# =============================================================================
# Layer 3: Fault Hypothesis Agent
# =============================================================================

class FaultHypothesisAgent(PDMModelAgent):
    """
    Fault Hypothesis Agent
    
    Bayesian fault diagnosis - maintains belief state over fault types.
    Not multiclass classification - probabilistic hypothesis testing.
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"fault_hypothesis_{site_id}",
            role=AgentRole.DIGITAL_TWIN,
            category=AgentCategory.ANALYTICS,
            name="Bayesian Fault Diagnosis Specialist",
            goal="Maintain probabilistic belief state over fault types. Alarm only when probability mass is concentrated and evidence is consistent.",
            backstory="""You are a diagnostic reasoning expert who understands that forcing a 
            single fault label is often wrong. Instead, you maintain probability distributions 
            over fault hypotheses, gathering evidence until confidence is high enough for action. 
            You know that 'I don't know yet' is a valid answer that prevents false diagnoses.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.FAULT_HYPOTHESIS, event_bus, **kwargs)
        
        self.site_id = site_id
        self.upstream_agents = [f"change_detection_{site_id}"]
        
        # Import service
        from oil_gas.pdm_fault_hypothesis_service import FaultHypothesisService
        self.hypothesis_service = FaultHypothesisService(site_id)
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.ANALYSIS_COMPLETE]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """Update fault hypothesis based on evidence"""
        from oil_gas.pdm_schemas import SensorType
        
        # Extract symptoms from inputs
        residuals = inputs.get("residuals", {})
        changes = inputs.get("change_detections", {})
        telemetry = inputs.get("telemetry", {})
        
        # Build residual observations dict
        residual_obs = {}
        # Would convert properly in production
        
        # Extract symptoms
        symptoms = self.hypothesis_service.extract_symptoms(
            residual_obs, changes, telemetry
        )
        
        # Update hypothesis
        if symptoms:
            hypothesis = self.hypothesis_service.update_hypothesis(symptoms)
        else:
            hypothesis = self.hypothesis_service.current_hypothesis
        
        if hypothesis:
            top_faults = self.hypothesis_service.get_top_hypotheses(3)
            is_confident = self.hypothesis_service.is_diagnosis_confident()
            
            result_data = {
                "belief_distribution": hypothesis.get_belief_distribution(),
                "top_fault": hypothesis.most_likely_fault.value if hypothesis.most_likely_fault else None,
                "top_probability": top_faults[0][1] if top_faults else 0,
                "is_concentrated": hypothesis.is_concentrated,
                "is_confident": is_confident,
                "recommended_action": hypothesis.recommended_action,
                "n_evidence": len(hypothesis.evidence),
            }
            confidence = top_faults[0][1] if top_faults else 0.0
        else:
            result_data = {
                "belief_distribution": {},
                "top_fault": None,
                "is_concentrated": False,
                "is_confident": False,
            }
            confidence = 0.0
        
        result = AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="fault_hypothesis",
            result_data=result_data,
            confidence=confidence,
            depends_on=self.upstream_agents,
            recommendations=[
                result_data.get("recommended_action", "Continue gathering evidence")
            ],
            concerns=[
                "Diagnosis not confident - continue monitoring"
            ] if not result_data.get("is_confident") else [],
        )
        
        self.broadcast_result(result)
        return result
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """Vote based on fault hypothesis"""
        latest = self.get_latest_result()
        if not latest:
            return AgentVote(
                agent_id=self.config.agent_id,
                agent_role=self.model_role,
                opinion=AgentOpinion.ABSTAIN,
                confidence=0.0,
                rationale="No fault hypothesis available.",
                weight=0.0,
            )
        
        is_confident = latest.result_data.get("is_confident", False)
        is_concentrated = latest.result_data.get("is_concentrated", False)
        top_fault = latest.result_data.get("top_fault")
        top_prob = latest.result_data.get("top_probability", 0)
        
        if "should_alert" in question.lower():
            if is_confident and is_concentrated and top_prob > 0.6:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.AGREE,
                    confidence=top_prob,
                    rationale=f"Diagnosis confident: {top_fault} ({top_prob:.0%}). Evidence supports actionable alert.",
                    evidence=[{"fault": top_fault, "probability": top_prob}],
                    weight=1.3,
                )
            elif top_fault and top_prob > 0.4:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=top_prob,
                    rationale=f"Leading hypothesis: {top_fault} ({top_prob:.0%}). Need more evidence for confident diagnosis.",
                    weight=1.0,
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.7,
                    rationale="No confident diagnosis. Probability mass spread across multiple hypotheses.",
                    weight=1.2,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Question not in fault hypothesis domain.",
            weight=0.0,
        )


# =============================================================================
# Layer 4: Decision Policy Agent
# =============================================================================

class DecisionPolicyAgent(PDMModelAgent):
    """
    Decision Policy Agent
    
    Enforces false positive budget and makes final alarm decisions.
    Aggregates votes from all other agents.
    """
    
    def __init__(self, site_id: str, event_bus: Optional[RedisEventBus] = None, **kwargs):
        config = CrewAIAgentConfig(
            agent_id=f"decision_policy_{site_id}",
            role=AgentRole.POLICY_VALIDATOR,
            category=AgentCategory.GOVERNANCE,
            name="Decision Policy Enforcer",
            goal="Enforce false positive budget constraints. Make final alarm decisions by aggregating agent opinions. Ensure operational pacing.",
            backstory="""You are the final arbiter of maintenance decisions, responsible for 
            balancing detection sensitivity against alarm fatigue. You aggregate opinions from 
            specialist agents, apply operational constraints (e.g., max alarms per month), and 
            make decisions that optimize technician efficiency and customer satisfaction.""",
            site_id=site_id,
        )
        super().__init__(config, PDMModelAgentRole.DECISION_POLICY, event_bus, **kwargs)
        
        self.site_id = site_id
        self.upstream_agents = [
            f"sensor_trust_{site_id}",
            f"change_detection_{site_id}",
            f"fault_hypothesis_{site_id}",
        ]
        
        # Import service
        from oil_gas.pdm_decision_policy_service import DecisionPolicyService
        from oil_gas.pdm_schemas import FalsePositiveBudget
        
        budget = FalsePositiveBudget(
            max_actionable_alarms_per_unit_per_month=0.3,
            max_no_issue_found_rate=0.05,
        )
        self.decision_service = DecisionPolicyService(site_id, budget)
        
        # Track collaborative decisions
        self.decision_history: List[CollaborativeDecision] = []
    
    @property
    def handled_event_types(self) -> List[PdMEventType]:
        return [PdMEventType.ANALYSIS_COMPLETE]
    
    def analyze(self, inputs: Dict[str, Any]) -> AgentAnalysisResult:
        """This agent doesn't analyze - it orchestrates decisions"""
        return AgentAnalysisResult(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            timestamp=datetime.utcnow(),
            result_type="policy_status",
            result_data=self.decision_service.get_policy_summary(),
            confidence=1.0,
        )
    
    def make_collaborative_decision(
        self,
        question: str,
        context: Dict[str, Any],
        voting_agents: List[PDMModelAgent],
        consensus_threshold: float = 0.6,
    ) -> CollaborativeDecision:
        """
        Orchestrate a collaborative decision across all agents.
        
        This is the key multi-agent collaboration method.
        """
        votes = []
        
        # Collect votes from all agents
        for agent in voting_agents:
            vote = agent.vote_on_decision(question, context)
            if vote.opinion != AgentOpinion.ABSTAIN:
                votes.append(vote)
        
        # Calculate weighted consensus
        weighted_scores = {
            AgentOpinion.STRONGLY_AGREE: 2.0,
            AgentOpinion.AGREE: 1.0,
            AgentOpinion.NEUTRAL: 0.0,
            AgentOpinion.DISAGREE: -1.0,
            AgentOpinion.STRONGLY_DISAGREE: -2.0,
        }
        
        total_weight = sum(v.weight for v in votes)
        if total_weight == 0:
            weighted_score = 0
        else:
            weighted_score = sum(
                weighted_scores[v.opinion] * v.weight * v.confidence
                for v in votes
            ) / total_weight
        
        # Determine final decision
        if weighted_score >= consensus_threshold:
            final_decision = "proceed"
            consensus_reached = True
        elif weighted_score <= -consensus_threshold:
            final_decision = "defer"
            consensus_reached = True
        else:
            final_decision = "uncertain"
            consensus_reached = False
        
        # Calculate aggregate confidence
        if votes:
            aggregate_confidence = sum(v.confidence * v.weight for v in votes) / total_weight
        else:
            aggregate_confidence = 0.0
        
        # Identify dissenters
        dissenters = [
            v.agent_id for v in votes
            if (final_decision == "proceed" and v.opinion in [AgentOpinion.DISAGREE, AgentOpinion.STRONGLY_DISAGREE])
            or (final_decision == "defer" and v.opinion in [AgentOpinion.AGREE, AgentOpinion.STRONGLY_AGREE])
        ]
        
        decision = CollaborativeDecision(
            decision_id=str(uuid.uuid4()),
            question=question,
            votes=votes,
            consensus_reached=consensus_reached,
            consensus_threshold=consensus_threshold,
            final_decision=final_decision,
            aggregate_confidence=aggregate_confidence,
            dissenting_agents=dissenters,
        )
        
        self.decision_history.append(decision)
        
        self.log_action("collaborative_decision", {
            "question": question,
            "n_votes": len(votes),
        }, {
            "decision": final_decision,
            "consensus": consensus_reached,
            "weighted_score": weighted_score,
            "dissenters": dissenters,
        })
        
        return decision
    
    def vote_on_decision(self, question: str, context: Dict[str, Any]) -> AgentVote:
        """The decision policy agent applies budget constraints"""
        budget = self.decision_service.budget
        
        if "should_alert" in question.lower():
            # Check budget constraints
            fa_prob = context.get("false_alarm_probability", 0.5)
            confidence = context.get("confidence", 0.5)
            
            if fa_prob > budget.max_false_alarm_probability:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.9,
                    rationale=f"FA probability ({fa_prob:.1%}) exceeds budget ({budget.max_false_alarm_probability:.1%}).",
                    weight=1.5,
                )
            elif confidence < budget.min_confidence_for_actionable:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.DISAGREE,
                    confidence=0.8,
                    rationale=f"Confidence ({confidence:.0%}) below threshold ({budget.min_confidence_for_actionable:.0%}).",
                    weight=1.2,
                )
            else:
                return AgentVote(
                    agent_id=self.config.agent_id,
                    agent_role=self.model_role,
                    opinion=AgentOpinion.NEUTRAL,
                    confidence=0.7,
                    rationale="Budget constraints satisfied. Deferring to specialist agents.",
                    weight=0.8,
                )
        
        return AgentVote(
            agent_id=self.config.agent_id,
            agent_role=self.model_role,
            opinion=AgentOpinion.ABSTAIN,
            confidence=0.0,
            rationale="Not a policy question.",
            weight=0.0,
        )
