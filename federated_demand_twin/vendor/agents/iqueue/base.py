"""
Base Classes for iQueue Agent Architecture

Provides foundational components for all agents in the autonomous MMM system.
"""

import numpy as np
from typing import Dict, List, Tuple, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from abc import ABC, abstractmethod
import json
import logging
from pathlib import Path
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AgentType(str, Enum):
    """Types of agents in the iQueue architecture"""
    DATA_STEWARD = "data_steward"
    ENDOGENOUS_STATE = "endogenous_state"
    DRIVER_CONTROLLABLE = "driver_controllable"
    DRIVER_NON_CONTROLLABLE = "driver_non_controllable"
    ATTRIBUTION = "attribution"
    SCENARIO_GENERATION = "scenario_generation"
    OPTIMIZATION = "optimization"
    GOVERNANCE = "governance"


class MessageType(str, Enum):
    """Types of messages exchanged between agents"""
    BELIEF_UPDATE = "belief_update"
    DATA_QUALITY = "data_quality"
    ALERT = "alert"
    SCENARIO_REQUEST = "scenario_request"
    SCENARIO_RESULT = "scenario_result"
    OPTIMIZATION_REQUEST = "optimization_request"
    OPTIMIZATION_RESULT = "optimization_result"
    GOVERNANCE_CHECK = "governance_check"
    GOVERNANCE_DECISION = "governance_decision"
    ATTRIBUTION_UPDATE = "attribution_update"


class ConfidenceLevel(str, Enum):
    """Confidence levels for agent outputs"""
    HIGH = "high"       # >90% confidence
    MEDIUM = "medium"   # 70-90% confidence
    LOW = "low"         # 50-70% confidence
    CRITICAL = "critical"  # <50% confidence - requires human review


@dataclass
class AgentConfig:
    """Configuration for iQueue agents"""
    agent_id: str
    agent_type: AgentType
    retailer_id: Optional[str] = None
    segment_id: Optional[str] = None
    
    # Belief update settings
    belief_update_frequency: str = "daily"  # daily, weekly, on_demand
    prior_weight: float = 0.3  # Weight given to prior vs new evidence
    
    # Thresholds
    confidence_threshold: float = 0.7
    alert_threshold: float = 0.5
    
    # Persistence
    state_path: Optional[str] = None
    persist_beliefs: bool = True
    
    # CrewAI settings
    verbose: bool = True
    allow_delegation: bool = True
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'agent_id': self.agent_id,
            'agent_type': self.agent_type.value,
            'retailer_id': self.retailer_id,
            'segment_id': self.segment_id,
            'belief_update_frequency': self.belief_update_frequency,
            'prior_weight': self.prior_weight,
            'confidence_threshold': self.confidence_threshold,
            'alert_threshold': self.alert_threshold
        }


@dataclass
class BeliefState:
    """
    Represents an agent's belief about a quantity.
    
    Uses Bayesian representation with mean, variance, and confidence.
    """
    name: str
    mean: float
    variance: float
    confidence: float  # 0-1 confidence in this belief
    
    # Temporal tracking
    last_updated: datetime = field(default_factory=datetime.utcnow)
    update_count: int = 0
    
    # Historical values for trend detection
    history: List[Tuple[datetime, float]] = field(default_factory=list)
    max_history: int = 100
    
    # Metadata
    source: str = "prior"
    evidence_count: int = 0
    
    @property
    def std(self) -> float:
        return np.sqrt(self.variance)
    
    @property
    def ci_lower(self) -> float:
        """95% CI lower bound"""
        return self.mean - 1.96 * self.std
    
    @property
    def ci_upper(self) -> float:
        """95% CI upper bound"""
        return self.mean + 1.96 * self.std
    
    def update(
        self,
        observation: float,
        observation_variance: float,
        prior_weight: float = 0.3
    ) -> 'BeliefState':
        """
        Bayesian update of belief given new observation.
        
        Uses conjugate normal-normal update.
        """
        # Precision-weighted update
        prior_precision = 1 / (self.variance + 1e-8)
        obs_precision = 1 / (observation_variance + 1e-8)
        
        # Posterior precision and mean
        posterior_precision = prior_weight * prior_precision + (1 - prior_weight) * obs_precision
        posterior_mean = (
            prior_weight * prior_precision * self.mean + 
            (1 - prior_weight) * obs_precision * observation
        ) / posterior_precision
        
        posterior_variance = 1 / posterior_precision
        
        # Update confidence based on evidence accumulation
        new_confidence = min(0.99, self.confidence + 0.01 * (1 - self.confidence))
        
        # Track history
        new_history = self.history.copy()
        new_history.append((datetime.utcnow(), posterior_mean))
        if len(new_history) > self.max_history:
            new_history = new_history[-self.max_history:]
        
        return BeliefState(
            name=self.name,
            mean=posterior_mean,
            variance=posterior_variance,
            confidence=new_confidence,
            last_updated=datetime.utcnow(),
            update_count=self.update_count + 1,
            history=new_history,
            source="observation",
            evidence_count=self.evidence_count + 1
        )
    
    def detect_drift(self, window: int = 10, threshold: float = 2.0) -> Optional[str]:
        """Detect significant drift in belief over time"""
        if len(self.history) < window * 2:
            return None
        
        recent = [v for _, v in self.history[-window:]]
        older = [v for _, v in self.history[-window*2:-window]]
        
        recent_mean = np.mean(recent)
        older_mean = np.mean(older)
        pooled_std = np.std(recent + older)
        
        if pooled_std < 1e-8:
            return None
        
        z_score = abs(recent_mean - older_mean) / pooled_std
        
        if z_score > threshold:
            direction = "increase" if recent_mean > older_mean else "decrease"
            return f"Significant {direction} detected (z={z_score:.2f})"
        
        return None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'name': self.name,
            'mean': self.mean,
            'variance': self.variance,
            'std': self.std,
            'confidence': self.confidence,
            'ci_lower': self.ci_lower,
            'ci_upper': self.ci_upper,
            'last_updated': self.last_updated.isoformat(),
            'update_count': self.update_count,
            'source': self.source,
            'evidence_count': self.evidence_count
        }


@dataclass
class AgentMessage:
    """Message exchanged between agents"""
    message_id: str
    message_type: MessageType
    sender_id: str
    recipient_id: Optional[str]  # None for broadcast
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    priority: int = 0  # Higher = more urgent
    requires_response: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'message_id': self.message_id,
            'message_type': self.message_type.value,
            'sender_id': self.sender_id,
            'recipient_id': self.recipient_id,
            'payload': self.payload,
            'timestamp': self.timestamp.isoformat(),
            'priority': self.priority,
            'requires_response': self.requires_response
        }


class AgentMessageBus:
    """
    Message bus for inter-agent communication.
    
    Enables agents to publish and subscribe to messages.
    """
    
    def __init__(self):
        self.subscribers: Dict[MessageType, List[Callable]] = {}
        self.message_history: List[AgentMessage] = []
        self.max_history = 1000
    
    def subscribe(self, message_type: MessageType, callback: Callable):
        """Subscribe to a message type"""
        if message_type not in self.subscribers:
            self.subscribers[message_type] = []
        self.subscribers[message_type].append(callback)
    
    def publish(self, message: AgentMessage):
        """Publish a message to subscribers"""
        self.message_history.append(message)
        if len(self.message_history) > self.max_history:
            self.message_history = self.message_history[-self.max_history:]
        
        if message.message_type in self.subscribers:
            for callback in self.subscribers[message.message_type]:
                try:
                    callback(message)
                except Exception as e:
                    logger.error(f"Error in message handler: {e}")
    
    def get_messages_for(
        self,
        recipient_id: str,
        since: Optional[datetime] = None
    ) -> List[AgentMessage]:
        """Get messages for a specific recipient"""
        messages = []
        for msg in self.message_history:
            if msg.recipient_id == recipient_id or msg.recipient_id is None:
                if since is None or msg.timestamp > since:
                    messages.append(msg)
        return messages


class BaseIQueueAgent(ABC):
    """
    Base class for all iQueue agents.
    
    Provides common functionality for:
    - Belief state management
    - Message handling
    - CrewAI integration
    """
    
    def __init__(
        self,
        config: AgentConfig,
        message_bus: Optional[AgentMessageBus] = None
    ):
        self.config = config
        self.message_bus = message_bus or AgentMessageBus()
        
        # Belief states
        self.beliefs: Dict[str, BeliefState] = {}
        
        # Alerts and diagnostics
        self.alerts: List[Dict[str, Any]] = []
        self.max_alerts = 100
        
        # State tracking
        self.last_update: Optional[datetime] = None
        self.update_count = 0
        
        # Initialize
        self._initialize_beliefs()
        self._subscribe_to_messages()
        
        logger.info(f"Agent {config.agent_id} ({config.agent_type.value}) initialized")
    
    @abstractmethod
    def _initialize_beliefs(self):
        """Initialize belief states for this agent"""
        pass
    
    @abstractmethod
    def _subscribe_to_messages(self):
        """Subscribe to relevant message types"""
        pass
    
    @abstractmethod
    def process(self, inputs: Dict[str, Any]) -> Dict[str, Any]:
        """Main processing logic for the agent"""
        pass
    
    def update_belief(
        self,
        belief_name: str,
        observation: float,
        observation_variance: float
    ):
        """Update a belief given new observation"""
        if belief_name not in self.beliefs:
            logger.warning(f"Belief {belief_name} not found in agent {self.config.agent_id}")
            return
        
        old_belief = self.beliefs[belief_name]
        new_belief = old_belief.update(
            observation, observation_variance, self.config.prior_weight
        )
        self.beliefs[belief_name] = new_belief
        
        # Check for drift
        drift = new_belief.detect_drift()
        if drift:
            self._raise_alert(f"Drift detected in {belief_name}: {drift}")
        
        # Publish update
        self._publish_belief_update(belief_name, new_belief)
    
    def _raise_alert(self, message: str, severity: str = "warning"):
        """Raise an alert"""
        alert = {
            'agent_id': self.config.agent_id,
            'timestamp': datetime.utcnow().isoformat(),
            'message': message,
            'severity': severity
        }
        self.alerts.append(alert)
        if len(self.alerts) > self.max_alerts:
            self.alerts = self.alerts[-self.max_alerts:]
        
        logger.warning(f"Agent {self.config.agent_id}: {message}")
        
        # Publish alert
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.ALERT,
            sender_id=self.config.agent_id,
            recipient_id=None,  # Broadcast
            payload=alert,
            priority=1 if severity == "critical" else 0
        ))
    
    def _publish_belief_update(self, belief_name: str, belief: BeliefState):
        """Publish belief update to message bus"""
        self.message_bus.publish(AgentMessage(
            message_id=self._generate_id(),
            message_type=MessageType.BELIEF_UPDATE,
            sender_id=self.config.agent_id,
            recipient_id=None,  # Broadcast
            payload={
                'belief_name': belief_name,
                'belief': belief.to_dict()
            }
        ))
    
    def _generate_id(self) -> str:
        """Generate unique message ID"""
        content = f"{self.config.agent_id}_{datetime.utcnow().isoformat()}"
        return hashlib.md5(content.encode()).hexdigest()[:12]
    
    def get_confidence_level(self) -> ConfidenceLevel:
        """Get overall confidence level of this agent"""
        if not self.beliefs:
            return ConfidenceLevel.LOW
        
        avg_confidence = np.mean([b.confidence for b in self.beliefs.values()])
        
        if avg_confidence >= 0.9:
            return ConfidenceLevel.HIGH
        elif avg_confidence >= 0.7:
            return ConfidenceLevel.MEDIUM
        elif avg_confidence >= 0.5:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.CRITICAL
    
    def get_state(self) -> Dict[str, Any]:
        """Get current state of the agent"""
        return {
            'agent_id': self.config.agent_id,
            'agent_type': self.config.agent_type.value,
            'beliefs': {name: b.to_dict() for name, b in self.beliefs.items()},
            'confidence_level': self.get_confidence_level().value,
            'alerts': self.alerts[-10:],
            'last_update': self.last_update.isoformat() if self.last_update else None,
            'update_count': self.update_count
        }
    
    def save_state(self, path: Optional[str] = None):
        """Persist agent state to disk"""
        save_path = path or self.config.state_path
        if not save_path:
            return
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, 'w') as f:
            json.dump(self.get_state(), f, indent=2, default=str)
    
    def load_state(self, path: Optional[str] = None):
        """Load agent state from disk"""
        load_path = path or self.config.state_path
        if not load_path or not Path(load_path).exists():
            return
        
        with open(load_path, 'r') as f:
            state = json.load(f)
        
        # Restore beliefs
        for name, belief_dict in state.get('beliefs', {}).items():
            self.beliefs[name] = BeliefState(
                name=belief_dict['name'],
                mean=belief_dict['mean'],
                variance=belief_dict['variance'],
                confidence=belief_dict['confidence'],
                source=belief_dict.get('source', 'loaded'),
                evidence_count=belief_dict.get('evidence_count', 0)
            )
    
    def to_crewai_agent(self):
        """
        Convert to CrewAI Agent format.
        
        Returns a dictionary that can be used to create a CrewAI Agent.
        """
        return {
            'role': self.config.agent_type.value.replace('_', ' ').title(),
            'goal': self._get_goal(),
            'backstory': self._get_backstory(),
            'verbose': self.config.verbose,
            'allow_delegation': self.config.allow_delegation
        }
    
    @abstractmethod
    def _get_goal(self) -> str:
        """Get the goal description for this agent"""
        pass
    
    @abstractmethod
    def _get_backstory(self) -> str:
        """Get the backstory for this agent"""
        pass
