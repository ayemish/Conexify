"""
Inter-Crew Messaging System for Cross-Team Coordination

Enables message passing between different optimization crews
(Brand, RMN, Channel, Campaign, Scenario Orchestrator) to achieve
coordinated decision support across the multi-agent system.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set
from queue import PriorityQueue
import threading
import logging

logger = logging.getLogger(__name__)


class MessagePriority(Enum):
    """Priority levels for inter-crew messages."""
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    LOW = 4


class MessageType(Enum):
    """Types of messages that can be passed between crews."""
    REQUEST = "request"
    RESPONSE = "response"
    NOTIFICATION = "notification"
    CONSTRAINT_UPDATE = "constraint_update"
    RECOMMENDATION = "recommendation"
    ESCALATION = "escalation"
    ACKNOWLEDGMENT = "acknowledgment"
    QUERY = "query"
    RESULT = "result"


class CrewType(Enum):
    """Types of optimization crews."""
    SCENARIO_ORCHESTRATOR = "scenario_orchestrator"
    BRAND = "brand_optimization"
    RMN = "rmn_optimization"
    CHANNEL = "channel_optimization"
    CAMPAIGN = "campaign_optimization"


@dataclass
class CrewMessage:
    """A message passed between crews."""
    message_id: str
    message_type: MessageType
    source_crew: CrewType
    target_crew: CrewType
    subject: str
    payload: Dict[str, Any]
    priority: MessagePriority = MessagePriority.NORMAL
    correlation_id: Optional[str] = None  # Links related messages
    scenario_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    expires_at: Optional[datetime] = None
    requires_response: bool = False
    response_timeout_seconds: int = 300
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __lt__(self, other: "CrewMessage") -> bool:
        """Compare by priority for queue ordering."""
        return self.priority.value < other.priority.value
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "source_crew": self.source_crew.value,
            "target_crew": self.target_crew.value,
            "subject": self.subject,
            "payload": self.payload,
            "priority": self.priority.value,
            "correlation_id": self.correlation_id,
            "scenario_id": self.scenario_id,
            "timestamp": self.timestamp.isoformat(),
            "requires_response": self.requires_response,
            "metadata": self.metadata,
        }
    
    @classmethod
    def create_request(
        cls,
        source: CrewType,
        target: CrewType,
        subject: str,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
        priority: MessagePriority = MessagePriority.NORMAL,
    ) -> "CrewMessage":
        """Create a request message."""
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.REQUEST,
            source_crew=source,
            target_crew=target,
            subject=subject,
            payload=payload,
            priority=priority,
            scenario_id=scenario_id,
            requires_response=True,
        )
    
    @classmethod
    def create_response(
        cls,
        original: "CrewMessage",
        payload: Dict[str, Any],
    ) -> "CrewMessage":
        """Create a response to a request message."""
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.RESPONSE,
            source_crew=original.target_crew,
            target_crew=original.source_crew,
            subject=f"RE: {original.subject}",
            payload=payload,
            priority=original.priority,
            correlation_id=original.message_id,
            scenario_id=original.scenario_id,
        )
    
    @classmethod
    def create_notification(
        cls,
        source: CrewType,
        target: CrewType,
        subject: str,
        payload: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> "CrewMessage":
        """Create a notification message (no response required)."""
        return cls(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.NOTIFICATION,
            source_crew=source,
            target_crew=target,
            subject=subject,
            payload=payload,
            scenario_id=scenario_id,
            requires_response=False,
        )


MessageHandler = Callable[[CrewMessage], Optional[CrewMessage]]


class MessageBus:
    """Central message bus for inter-crew communication."""
    
    def __init__(self):
        self._queues: Dict[CrewType, PriorityQueue] = {
            crew: PriorityQueue() for crew in CrewType
        }
        self._handlers: Dict[CrewType, Dict[MessageType, List[MessageHandler]]] = {
            crew: {msg_type: [] for msg_type in MessageType}
            for crew in CrewType
        }
        self._message_log: List[CrewMessage] = []
        self._pending_responses: Dict[str, CrewMessage] = {}
        self._lock = threading.Lock()
    
    def send(self, message: CrewMessage) -> str:
        """Send a message to a target crew."""
        with self._lock:
            self._message_log.append(message)
            self._queues[message.target_crew].put(message)
            
            if message.requires_response:
                self._pending_responses[message.message_id] = message
            
            logger.debug(
                f"Message sent: {message.message_id} from {message.source_crew.value} "
                f"to {message.target_crew.value}: {message.subject}"
            )
            
        return message.message_id
    
    def broadcast(
        self,
        message: CrewMessage,
        targets: Optional[List[CrewType]] = None,
    ) -> List[str]:
        """Broadcast a message to multiple crews."""
        if targets is None:
            targets = [c for c in CrewType if c != message.source_crew]
        
        message_ids = []
        for target in targets:
            msg_copy = CrewMessage(
                message_id=str(uuid.uuid4()),
                message_type=message.message_type,
                source_crew=message.source_crew,
                target_crew=target,
                subject=message.subject,
                payload=message.payload,
                priority=message.priority,
                correlation_id=message.message_id,
                scenario_id=message.scenario_id,
            )
            message_ids.append(self.send(msg_copy))
        
        return message_ids
    
    def receive(self, crew: CrewType, block: bool = False, timeout: float = None) -> Optional[CrewMessage]:
        """Receive the next message for a crew."""
        try:
            if block:
                return self._queues[crew].get(block=True, timeout=timeout)
            else:
                if self._queues[crew].empty():
                    return None
                return self._queues[crew].get_nowait()
        except Exception:
            return None
    
    def receive_all(self, crew: CrewType) -> List[CrewMessage]:
        """Receive all pending messages for a crew."""
        messages = []
        while not self._queues[crew].empty():
            try:
                messages.append(self._queues[crew].get_nowait())
            except Exception:
                break
        return messages
    
    def register_handler(
        self,
        crew: CrewType,
        message_type: MessageType,
        handler: MessageHandler,
    ) -> None:
        """Register a handler for a specific message type."""
        self._handlers[crew][message_type].append(handler)
    
    def process_messages(self, crew: CrewType, max_messages: int = 10) -> List[Dict[str, Any]]:
        """Process pending messages for a crew using registered handlers."""
        results = []
        messages = self.receive_all(crew)[:max_messages]
        
        for message in messages:
            handlers = self._handlers[crew].get(message.message_type, [])
            for handler in handlers:
                try:
                    response = handler(message)
                    if response:
                        self.send(response)
                        results.append({
                            "message_id": message.message_id,
                            "response_id": response.message_id,
                            "status": "handled_with_response",
                        })
                    else:
                        results.append({
                            "message_id": message.message_id,
                            "status": "handled",
                        })
                except Exception as e:
                    logger.error(f"Handler error for message {message.message_id}: {e}")
                    results.append({
                        "message_id": message.message_id,
                        "status": "error",
                        "error": str(e),
                    })
        
        return results
    
    def get_pending_response(self, message_id: str) -> Optional[CrewMessage]:
        """Get the response for a pending request."""
        return self._pending_responses.get(message_id)
    
    def get_message_log(
        self,
        scenario_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[CrewMessage]:
        """Get message log, optionally filtered by scenario."""
        with self._lock:
            if scenario_id:
                messages = [m for m in self._message_log if m.scenario_id == scenario_id]
            else:
                messages = self._message_log.copy()
            return messages[-limit:]
    
    def get_conversation_thread(self, correlation_id: str) -> List[CrewMessage]:
        """Get all messages in a conversation thread."""
        with self._lock:
            thread = []
            for message in self._message_log:
                if message.message_id == correlation_id or message.correlation_id == correlation_id:
                    thread.append(message)
            return sorted(thread, key=lambda m: m.timestamp)


class CrossCrewCoordinator:
    """
    Coordinates message passing between crews for scenario execution.
    Manages the flow of information and decisions across the multi-agent system.
    """
    
    def __init__(self, message_bus: Optional[MessageBus] = None):
        self.bus = message_bus or MessageBus()
        self._active_scenarios: Dict[str, Dict[str, Any]] = {}
        self._crew_status: Dict[CrewType, str] = {
            crew: "idle" for crew in CrewType
        }
    
    def start_scenario_coordination(
        self,
        scenario_id: str,
        scenario_name: str,
        crew_sequence: List[str],
        initial_context: Dict[str, Any],
    ) -> str:
        """Start coordinated execution of a scenario across crews."""
        coordination_id = str(uuid.uuid4())
        
        self._active_scenarios[coordination_id] = {
            "scenario_id": scenario_id,
            "scenario_name": scenario_name,
            "crew_sequence": crew_sequence,
            "current_crew_index": 0,
            "context": initial_context,
            "status": "started",
            "started_at": datetime.now(),
            "messages_sent": [],
            "results": {},
        }
        
        # Send initial message to first crew
        if crew_sequence:
            first_crew = CrewType(crew_sequence[0])
            msg = CrewMessage.create_request(
                source=CrewType.SCENARIO_ORCHESTRATOR,
                target=first_crew,
                subject=f"Execute scenario: {scenario_name}",
                payload={
                    "coordination_id": coordination_id,
                    "scenario_id": scenario_id,
                    "context": initial_context,
                    "is_first_in_sequence": True,
                },
                scenario_id=scenario_id,
                priority=MessagePriority.HIGH,
            )
            self.bus.send(msg)
            self._active_scenarios[coordination_id]["messages_sent"].append(msg.message_id)
        
        return coordination_id
    
    def advance_scenario(
        self,
        coordination_id: str,
        crew_result: Dict[str, Any],
    ) -> Optional[CrewMessage]:
        """Advance a scenario to the next crew in the sequence."""
        if coordination_id not in self._active_scenarios:
            return None
        
        state = self._active_scenarios[coordination_id]
        current_index = state["current_crew_index"]
        sequence = state["crew_sequence"]
        
        # Store result from current crew
        current_crew = sequence[current_index]
        state["results"][current_crew] = crew_result
        
        # Update context with crew result
        state["context"].update(crew_result.get("updates", {}))
        
        # Move to next crew
        next_index = current_index + 1
        if next_index >= len(sequence):
            state["status"] = "completed"
            state["completed_at"] = datetime.now()
            return None
        
        state["current_crew_index"] = next_index
        next_crew = CrewType(sequence[next_index])
        
        # Send message to next crew
        msg = CrewMessage.create_request(
            source=CrewType.SCENARIO_ORCHESTRATOR,
            target=next_crew,
            subject=f"Continue scenario: {state['scenario_name']}",
            payload={
                "coordination_id": coordination_id,
                "scenario_id": state["scenario_id"],
                "context": state["context"],
                "previous_crew_result": crew_result,
                "sequence_position": next_index,
            },
            scenario_id=state["scenario_id"],
            priority=MessagePriority.HIGH,
        )
        self.bus.send(msg)
        state["messages_sent"].append(msg.message_id)
        
        return msg
    
    def request_crew_input(
        self,
        requesting_crew: CrewType,
        target_crew: CrewType,
        query: str,
        context: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> str:
        """Request input/analysis from another crew."""
        msg = CrewMessage.create_request(
            source=requesting_crew,
            target=target_crew,
            subject=f"Input request: {query}",
            payload={
                "query": query,
                "context": context,
            },
            scenario_id=scenario_id,
            priority=MessagePriority.NORMAL,
        )
        return self.bus.send(msg)
    
    def notify_constraint_change(
        self,
        source_crew: CrewType,
        constraint_type: str,
        old_value: Any,
        new_value: Any,
        reason: str,
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        """Notify all crews of a constraint change."""
        msg = CrewMessage(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.CONSTRAINT_UPDATE,
            source_crew=source_crew,
            target_crew=CrewType.SCENARIO_ORCHESTRATOR,  # Will be broadcast
            subject=f"Constraint update: {constraint_type}",
            payload={
                "constraint_type": constraint_type,
                "old_value": old_value,
                "new_value": new_value,
                "reason": reason,
            },
            scenario_id=scenario_id,
            priority=MessagePriority.HIGH,
        )
        return self.bus.broadcast(msg)
    
    def escalate_issue(
        self,
        source_crew: CrewType,
        issue_type: str,
        description: str,
        severity: str,
        context: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> str:
        """Escalate an issue to the orchestrator."""
        msg = CrewMessage(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.ESCALATION,
            source_crew=source_crew,
            target_crew=CrewType.SCENARIO_ORCHESTRATOR,
            subject=f"Escalation: {issue_type}",
            payload={
                "issue_type": issue_type,
                "description": description,
                "severity": severity,
                "context": context,
            },
            scenario_id=scenario_id,
            priority=MessagePriority.CRITICAL if severity == "critical" else MessagePriority.HIGH,
        )
        return self.bus.send(msg)
    
    def share_recommendation(
        self,
        source_crew: CrewType,
        target_crews: List[CrewType],
        recommendation: Dict[str, Any],
        scenario_id: Optional[str] = None,
    ) -> List[str]:
        """Share a recommendation with other crews for feedback."""
        msg = CrewMessage(
            message_id=str(uuid.uuid4()),
            message_type=MessageType.RECOMMENDATION,
            source_crew=source_crew,
            target_crew=CrewType.SCENARIO_ORCHESTRATOR,
            subject="Recommendation for review",
            payload=recommendation,
            scenario_id=scenario_id,
            priority=MessagePriority.NORMAL,
        )
        return self.bus.broadcast(msg, targets=target_crews)
    
    def get_scenario_status(self, coordination_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a coordinated scenario."""
        state = self._active_scenarios.get(coordination_id)
        if not state:
            return None
        
        return {
            "coordination_id": coordination_id,
            "scenario_id": state["scenario_id"],
            "scenario_name": state["scenario_name"],
            "status": state["status"],
            "current_crew": state["crew_sequence"][state["current_crew_index"]]
                if state["current_crew_index"] < len(state["crew_sequence"]) else None,
            "progress": f"{state['current_crew_index'] + 1}/{len(state['crew_sequence'])}",
            "messages_sent": len(state["messages_sent"]),
            "results_collected": list(state["results"].keys()),
        }
    
    def get_cross_crew_messages(
        self,
        scenario_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Get all cross-crew messages, optionally for a scenario."""
        messages = self.bus.get_message_log(scenario_id=scenario_id)
        return [m.to_dict() for m in messages]
