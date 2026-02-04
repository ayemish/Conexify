"""
Unified CrewAI Agent Infrastructure

Provides CrewAI-compliant base classes and utilities for all agents
in the Federated Demand Twin system.

Architecture:
- All agents extend CrewAI's Agent class for LLM-powered reasoning
- Agents maintain domain-specific tools and state
- Crews orchestrate multi-agent workflows
- Tasks define specific agent actions

Agent Categories:
1. Data Agents - Data quality, validation, transformation
2. Analytics Agents - Attribution, elasticity, forecasting  
3. Simulation Agents - Digital Twin, scenario generation
4. Optimization Agents - Budget allocation, inventory planning
5. Governance Agents - Policy validation, approval workflows
6. Communication Agents - Rationale generation, reporting
"""

import logging
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from abc import ABC, abstractmethod
import json
from pathlib import Path

# Define mock classes first (will be overwritten if CrewAI available)
class _MockAgent:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class _MockTask:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

class _MockCrew:
    def __init__(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)
    def kickoff(self, inputs=None):
        return {"status": "mock", "message": "CrewAI not available"}

class _MockProcess:
    sequential = "sequential"
    hierarchical = "hierarchical"

class BaseTool:
    """Base class for agent tools"""
    name: str = ""
    description: str = ""
    def _run(self, *args, **kwargs):
        pass

# CrewAI imports with fallback
CREWAI_AVAILABLE = False
Agent = _MockAgent
Task = _MockTask
Crew = _MockCrew
Process = _MockProcess

try:
    from crewai import Agent, Task, Crew, Process
    CREWAI_AVAILABLE = True
    # Try to import BaseTool from crewai (optional)
    try:
        from crewai.tools import BaseTool
    except ImportError:
        pass  # Keep our BaseTool definition
except Exception as e:
    logging.warning(f"CrewAI not available: {e}. Using mock classes.")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# =============================================================================
# Agent Categories and Types
# =============================================================================

class AgentCategory(str, Enum):
    """High-level agent categories"""
    DATA = "data"
    ANALYTICS = "analytics"
    SIMULATION = "simulation"
    OPTIMIZATION = "optimization"
    GOVERNANCE = "governance"
    COMMUNICATION = "communication"


class AgentRole(str, Enum):
    """Specific agent roles within the system"""
    # Data Agents
    DATA_STEWARD = "data_steward"
    DATA_VALIDATOR = "data_validator"
    DATA_TRANSFORMER = "data_transformer"
    
    # Analytics Agents
    ATTRIBUTION = "attribution"
    ELASTICITY = "elasticity"
    FORECASTER = "forecaster"
    ANOMALY_DETECTOR = "anomaly_detector"
    
    # Simulation Agents
    DIGITAL_TWIN = "digital_twin"
    SCENARIO_GENERATOR = "scenario_generator"
    MONTE_CARLO = "monte_carlo"
    
    # Driver Agents (MMM)
    MEDIA_DRIVER = "media_driver"
    PRICE_DRIVER = "price_driver"
    TRADE_DRIVER = "trade_driver"
    TIMESERIES_DRIVER = "timeseries_driver"
    EVENTS_DRIVER = "events_driver"
    COMPETITION_DRIVER = "competition_driver"
    
    # Endogenous State Agents
    BASKET = "basket"
    PENETRATION = "penetration"
    ITEMS_PER_BASKET = "items_per_basket"
    SIZE_PER_ITEM = "size_per_item"
    
    # Optimization Agents
    BUDGET_OPTIMIZER = "budget_optimizer"
    INVENTORY_OPTIMIZER = "inventory_optimizer"
    RESOURCE_ALLOCATOR = "resource_allocator"
    
    # Governance Agents
    POLICY_VALIDATOR = "policy_validator"
    APPROVAL_WORKFLOW = "approval_workflow"
    COMPLIANCE_CHECKER = "compliance_checker"
    
    # Communication Agents
    RATIONALE_GENERATOR = "rationale_generator"
    REPORT_WRITER = "report_writer"
    EXECUTIVE_SUMMARIZER = "executive_summarizer"


# =============================================================================
# Agent Configuration
# =============================================================================

@dataclass
class CrewAIAgentConfig:
    """Unified configuration for CrewAI agents"""
    # Identity
    agent_id: str
    role: AgentRole
    category: AgentCategory
    
    # CrewAI settings
    name: str = ""
    goal: str = ""
    backstory: str = ""
    verbose: bool = True
    allow_delegation: bool = True
    max_iter: int = 25
    max_rpm: int = 10
    
    # LLM settings
    llm_model: str = "gpt-4"
    temperature: float = 0.7
    
    # Domain context
    retailer_id: Optional[str] = None
    segment_id: Optional[str] = None
    
    # State management
    persist_state: bool = True
    state_path: Optional[str] = None
    
    # Thresholds
    confidence_threshold: float = 0.7
    quality_threshold: float = 0.8
    
    def to_crewai_kwargs(self) -> Dict[str, Any]:
        """Convert to CrewAI Agent constructor kwargs"""
        return {
            "role": self.name or self.role.value.replace("_", " ").title(),
            "goal": self.goal,
            "backstory": self.backstory,
            "verbose": self.verbose,
            "allow_delegation": self.allow_delegation,
            "max_iter": self.max_iter,
            "max_rpm": self.max_rpm,
        }


# =============================================================================
# Belief State (Bayesian State Management)
# =============================================================================

@dataclass
class BeliefState:
    """
    Bayesian belief state for agents.
    
    Agents maintain beliefs as probability distributions,
    updating them as new evidence arrives.
    """
    belief_id: str
    agent_id: str
    
    # Distribution parameters
    mean: float
    std: float
    ci_lower: float
    ci_upper: float
    
    # Metadata
    n_observations: int = 0
    evidence_strength: float = 0.5
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    # Prior information
    prior_mean: float = 0.0
    prior_std: float = 1.0
    
    def update(self, observation: float, observation_std: float = 0.1):
        """Bayesian update with new observation"""
        # Precision-weighted update
        prior_precision = 1.0 / max(self.std ** 2, 1e-6)
        obs_precision = 1.0 / max(observation_std ** 2, 1e-6)
        
        posterior_precision = prior_precision + obs_precision
        posterior_mean = (
            prior_precision * self.mean + obs_precision * observation
        ) / posterior_precision
        posterior_std = 1.0 / (posterior_precision ** 0.5)
        
        self.mean = posterior_mean
        self.std = posterior_std
        self.ci_lower = max(0, posterior_mean - 1.645 * posterior_std)
        self.ci_upper = posterior_mean + 1.645 * posterior_std
        self.n_observations += 1
        self.evidence_strength = min(1.0, self.n_observations / 100)
        self.last_updated = datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "belief_id": self.belief_id,
            "agent_id": self.agent_id,
            "mean": self.mean,
            "std": self.std,
            "ci_lower": self.ci_lower,
            "ci_upper": self.ci_upper,
            "n_observations": self.n_observations,
            "evidence_strength": self.evidence_strength,
            "last_updated": self.last_updated.isoformat(),
        }


# =============================================================================
# Agent Message Bus
# =============================================================================

class MessageType(str, Enum):
    """Types of inter-agent messages"""
    BELIEF_UPDATE = "belief_update"
    DATA_QUALITY = "data_quality"
    ALERT = "alert"
    RESULT = "result"
    TASK_REQUEST = "task_request"
    TASK_RESULT = "task_result"
    SCENARIO_REQUEST = "scenario_request"
    SCENARIO_RESULT = "scenario_result"
    OPTIMIZATION_REQUEST = "optimization_request"
    OPTIMIZATION_RESULT = "optimization_result"
    GOVERNANCE_CHECK = "governance_check"
    GOVERNANCE_DECISION = "governance_decision"


@dataclass
class AgentMessage:
    """Message exchanged between agents"""
    message_id: str
    message_type: MessageType
    sender_id: str
    recipient_id: Optional[str]  # None for broadcast
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "recipient_id": self.recipient_id,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
        }


class AgentMessageBus:
    """
    Central message bus for inter-agent communication.
    
    Supports:
    - Point-to-point messaging
    - Broadcast messaging
    - Topic-based subscriptions
    """
    
    def __init__(self):
        self.messages: List[AgentMessage] = []
        self.subscriptions: Dict[str, List[str]] = {}  # topic -> [agent_ids]
        self.message_handlers: Dict[str, Callable] = {}  # agent_id -> handler
    
    def publish(self, message: AgentMessage):
        """Publish a message to the bus"""
        self.messages.append(message)
        
        # Invoke handlers
        if message.recipient_id and message.recipient_id in self.message_handlers:
            self.message_handlers[message.recipient_id](message)
        elif message.recipient_id is None:
            # Broadcast
            for handler in self.message_handlers.values():
                handler(message)
    
    def subscribe(self, agent_id: str, handler: Callable):
        """Subscribe an agent to receive messages"""
        self.message_handlers[agent_id] = handler
    
    def get_messages(
        self,
        recipient_id: Optional[str] = None,
        message_type: Optional[MessageType] = None,
        since: Optional[datetime] = None
    ) -> List[AgentMessage]:
        """Get messages matching criteria"""
        result = []
        for msg in self.messages:
            if recipient_id and msg.recipient_id != recipient_id and msg.recipient_id is not None:
                continue
            if message_type and msg.message_type != message_type:
                continue
            if since and msg.timestamp < since:
                continue
            result.append(msg)
        return result


# =============================================================================
# Base CrewAI Agent
# =============================================================================

class DemandTwinAgent:
    """
    Base class for all CrewAI-compliant agents in the Demand Twin system.
    
    Uses composition pattern - wraps CrewAI Agent for LLM tasks while
    maintaining domain-specific state and behavior:
    - Bayesian belief state management
    - Inter-agent messaging
    - Domain-specific tools
    - State persistence
    """
    
    def __init__(
        self,
        config: CrewAIAgentConfig,
        message_bus: Optional[AgentMessageBus] = None,
        tools: Optional[List[BaseTool]] = None,
        **kwargs
    ):
        self.config = config
        self.message_bus = message_bus or AgentMessageBus()
        self.beliefs: Dict[str, BeliefState] = {}
        self.action_history: List[Dict[str, Any]] = []
        
        # Create CrewAI Agent as composition (when available for LLM tasks)
        if CREWAI_AVAILABLE:
            crewai_kwargs = config.to_crewai_kwargs()
            crewai_kwargs.update(kwargs)
            if tools:
                crewai_kwargs["tools"] = tools
            try:
                self._crewai_agent = Agent(**crewai_kwargs)
            except Exception as e:
                logger.warning(f"Could not create CrewAI agent: {e}")
                self._crewai_agent = None
        else:
            self._crewai_agent = None
        
        # Subscribe to message bus
        if message_bus:
            message_bus.subscribe(config.agent_id, self._handle_message)
        
        logger.info(f"Initialized {config.role.value} agent: {config.agent_id}")
    
    @property
    def crewai_agent(self) -> Optional[Agent]:
        """Get the underlying CrewAI agent for LLM tasks"""
        return self._crewai_agent
    
    def _handle_message(self, message: AgentMessage):
        """Handle incoming messages"""
        if message.message_type == MessageType.BELIEF_UPDATE:
            self._handle_belief_update(message)
        elif message.message_type == MessageType.TASK_REQUEST:
            self._handle_task_request(message)
    
    def _handle_belief_update(self, message: AgentMessage):
        """Process belief update message"""
        payload = message.payload
        belief_id = payload.get("belief_id")
        if belief_id and belief_id in self.beliefs:
            self.beliefs[belief_id].update(
                payload.get("observation", 0),
                payload.get("observation_std", 0.1)
            )
    
    def _handle_task_request(self, message: AgentMessage):
        """Process task request - override in subclasses"""
        pass
    
    def update_belief(
        self,
        belief_id: str,
        observation: float,
        observation_std: float = 0.1
    ):
        """Update a belief with new observation"""
        if belief_id not in self.beliefs:
            self.beliefs[belief_id] = BeliefState(
                belief_id=belief_id,
                agent_id=self.config.agent_id,
                mean=observation,
                std=observation_std,
                ci_lower=observation - 1.645 * observation_std,
                ci_upper=observation + 1.645 * observation_std,
            )
        else:
            self.beliefs[belief_id].update(observation, observation_std)
        
        # Broadcast update
        if self.message_bus:
            self.message_bus.publish(AgentMessage(
                message_id=f"belief-{datetime.utcnow().timestamp()}",
                message_type=MessageType.BELIEF_UPDATE,
                sender_id=self.config.agent_id,
                recipient_id=None,
                payload={
                    "belief_id": belief_id,
                    "observation": observation,
                    "observation_std": observation_std,
                    "new_mean": self.beliefs[belief_id].mean,
                    "new_std": self.beliefs[belief_id].std,
                }
            ))
    
    def get_belief(self, belief_id: str) -> Optional[BeliefState]:
        """Get a belief by ID"""
        return self.beliefs.get(belief_id)
    
    def log_action(self, action: str, inputs: Dict[str, Any], outputs: Dict[str, Any]):
        """Log an action taken by this agent"""
        self.action_history.append({
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "inputs": inputs,
            "outputs": outputs,
        })
    
    def save_state(self, path: Optional[str] = None):
        """Persist agent state"""
        save_path = path or self.config.state_path
        if not save_path:
            return
        
        state = {
            "agent_id": self.config.agent_id,
            "role": self.config.role.value,
            "beliefs": {k: v.to_dict() for k, v in self.beliefs.items()},
            "action_history": self.action_history[-100:],  # Last 100 actions
            "saved_at": datetime.utcnow().isoformat(),
        }
        
        Path(save_path).parent.mkdir(parents=True, exist_ok=True)
        with open(save_path, "w") as f:
            json.dump(state, f, indent=2)
    
    def load_state(self, path: Optional[str] = None):
        """Load agent state"""
        load_path = path or self.config.state_path
        if not load_path or not Path(load_path).exists():
            return
        
        with open(load_path, "r") as f:
            state = json.load(f)
        
        # Restore beliefs
        for belief_id, belief_dict in state.get("beliefs", {}).items():
            self.beliefs[belief_id] = BeliefState(
                belief_id=belief_dict["belief_id"],
                agent_id=belief_dict["agent_id"],
                mean=belief_dict["mean"],
                std=belief_dict["std"],
                ci_lower=belief_dict["ci_lower"],
                ci_upper=belief_dict["ci_upper"],
                n_observations=belief_dict["n_observations"],
                evidence_strength=belief_dict["evidence_strength"],
            )
        
        self.action_history = state.get("action_history", [])


# =============================================================================
# Agent Registry
# =============================================================================

class AgentRegistry:
    """
    Central registry for all agents in the system.
    
    Provides:
    - Agent discovery
    - Lifecycle management
    - Cross-agent coordination
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents: Dict[str, DemandTwinAgent] = {}
            cls._instance._message_bus = AgentMessageBus()
        return cls._instance
    
    @classmethod
    def get_instance(cls) -> "AgentRegistry":
        return cls()
    
    def register(self, agent: DemandTwinAgent):
        """Register an agent"""
        self._agents[agent.config.agent_id] = agent
        logger.info(f"Registered agent: {agent.config.agent_id}")
    
    def unregister(self, agent_id: str):
        """Unregister an agent"""
        if agent_id in self._agents:
            del self._agents[agent_id]
            logger.info(f"Unregistered agent: {agent_id}")
    
    def get(self, agent_id: str) -> Optional[DemandTwinAgent]:
        """Get an agent by ID"""
        return self._agents.get(agent_id)
    
    def get_by_role(self, role: AgentRole) -> List[DemandTwinAgent]:
        """Get all agents with a specific role"""
        return [a for a in self._agents.values() if a.config.role == role]
    
    def get_by_category(self, category: AgentCategory) -> List[DemandTwinAgent]:
        """Get all agents in a category"""
        return [a for a in self._agents.values() if a.config.category == category]
    
    def get_all(self) -> List[DemandTwinAgent]:
        """Get all registered agents"""
        return list(self._agents.values())
    
    @property
    def message_bus(self) -> AgentMessageBus:
        """Get the shared message bus"""
        return self._message_bus
    
    def save_all_states(self, base_path: str):
        """Save all agent states"""
        for agent in self._agents.values():
            if agent.config.persist_state:
                path = f"{base_path}/{agent.config.agent_id}.json"
                agent.save_state(path)
    
    def load_all_states(self, base_path: str):
        """Load all agent states"""
        for agent in self._agents.values():
            path = f"{base_path}/{agent.config.agent_id}.json"
            if Path(path).exists():
                agent.load_state(path)


# =============================================================================
# Task Templates
# =============================================================================

def create_task(
    description: str,
    agent: DemandTwinAgent,
    expected_output: str,
    context: Optional[List[Task]] = None,
    **kwargs
) -> Task:
    """Create a CrewAI Task with standard configuration"""
    return Task(
        description=description,
        agent=agent,
        expected_output=expected_output,
        context=context or [],
        **kwargs
    )


# =============================================================================
# Crew Factory
# =============================================================================

def create_crew(
    name: str,
    agents: List[DemandTwinAgent],
    tasks: List[Task],
    process: str = "sequential",
    verbose: bool = True,
    **kwargs
) -> Crew:
    """
    Create a CrewAI Crew for multi-agent workflows.
    
    Args:
        name: Crew name
        agents: List of agents in the crew
        tasks: List of tasks to execute
        process: "sequential" or "hierarchical"
        verbose: Enable verbose logging
    
    Returns:
        Configured Crew instance
    """
    process_type = Process.hierarchical if process == "hierarchical" else Process.sequential
    
    return Crew(
        agents=agents,
        tasks=tasks,
        process=process_type,
        verbose=verbose,
        **kwargs
    )


# =============================================================================
# Utility Functions
# =============================================================================

def get_agent_summary() -> Dict[str, Any]:
    """Get summary of all registered agents"""
    registry = AgentRegistry.get_instance()
    agents = registry.get_all()
    
    by_category = {}
    for agent in agents:
        cat = agent.config.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append({
            "id": agent.config.agent_id,
            "role": agent.config.role.value,
            "beliefs": len(agent.beliefs),
            "actions": len(agent.action_history),
        })
    
    return {
        "total_agents": len(agents),
        "by_category": by_category,
        "crewai_available": CREWAI_AVAILABLE,
    }
