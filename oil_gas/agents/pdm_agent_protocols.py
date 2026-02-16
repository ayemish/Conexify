"""
PDM Agent Communication Protocols

Defines structured communication protocols for agent-to-agent interaction
in the multi-agent predictive maintenance system.

Protocol Types:
1. Result Broadcasting: Agents broadcast analysis results to downstream agents
2. Query-Response: Agents query upstream agents for specific information
3. Voting Protocol: Structured voting for collaborative decisions
4. Escalation Protocol: Agents escalate concerns to higher-level agents
5. Consensus Protocol: Multi-round consensus building for critical decisions

Message Types:
- ANALYSIS_RESULT: Result of an agent's analysis
- QUERY: Request for information from another agent
- RESPONSE: Response to a query
- VOTE_REQUEST: Request for a vote on a decision
- VOTE: Vote on a decision
- ESCALATION: Concern escalated to decision agent
- FEEDBACK: Feedback on decision outcomes
"""

import logging
import uuid
from typing import Dict, List, Optional, Any, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import asyncio
from collections import defaultdict

logger = logging.getLogger(__name__)


# =============================================================================
# Protocol Message Types
# =============================================================================

class ProtocolMessageType(str, Enum):
    """Types of protocol messages"""
    # Result broadcasting
    ANALYSIS_RESULT = "analysis_result"
    RESULT_ACK = "result_ack"
    
    # Query-Response
    QUERY = "query"
    RESPONSE = "response"
    QUERY_TIMEOUT = "query_timeout"
    
    # Voting
    VOTE_REQUEST = "vote_request"
    VOTE = "vote"
    VOTE_RESULT = "vote_result"
    
    # Escalation
    ESCALATION = "escalation"
    ESCALATION_ACK = "escalation_ack"
    
    # Feedback
    FEEDBACK = "feedback"
    FEEDBACK_ACK = "feedback_ack"
    
    # Control
    HEARTBEAT = "heartbeat"
    SYNC_REQUEST = "sync_request"
    SYNC_RESPONSE = "sync_response"


class MessagePriority(str, Enum):
    """Message priority levels"""
    CRITICAL = "critical"
    HIGH = "high"
    NORMAL = "normal"
    LOW = "low"


@dataclass
class ProtocolMessage:
    """Base protocol message structure"""
    message_id: str
    message_type: ProtocolMessageType
    sender_id: str
    receiver_id: Optional[str]  # None for broadcast
    priority: MessagePriority
    payload: Dict[str, Any]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    correlation_id: Optional[str] = None  # For request-response correlation
    ttl_seconds: float = 60.0  # Time-to-live
    
    def is_expired(self) -> bool:
        return (datetime.utcnow() - self.timestamp).total_seconds() > self.ttl_seconds
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "message_id": self.message_id,
            "message_type": self.message_type.value,
            "sender_id": self.sender_id,
            "receiver_id": self.receiver_id,
            "priority": self.priority.value,
            "payload": self.payload,
            "timestamp": self.timestamp.isoformat(),
            "correlation_id": self.correlation_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProtocolMessage":
        return cls(
            message_id=data["message_id"],
            message_type=ProtocolMessageType(data["message_type"]),
            sender_id=data["sender_id"],
            receiver_id=data.get("receiver_id"),
            priority=MessagePriority(data.get("priority", "normal")),
            payload=data["payload"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            correlation_id=data.get("correlation_id"),
        )


# =============================================================================
# Protocol Handlers
# =============================================================================

class ProtocolHandler(ABC):
    """Base class for protocol message handlers"""
    
    @abstractmethod
    def can_handle(self, message: ProtocolMessage) -> bool:
        """Check if this handler can process the message"""
        pass
    
    @abstractmethod
    def handle(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Process the message and optionally return a response"""
        pass


class ResultBroadcastHandler(ProtocolHandler):
    """Handler for analysis result broadcasts"""
    
    def __init__(self, agent_id: str, on_result: Callable[[ProtocolMessage], None]):
        self.agent_id = agent_id
        self.on_result = on_result
        self.received_results: Dict[str, ProtocolMessage] = {}
    
    def can_handle(self, message: ProtocolMessage) -> bool:
        return message.message_type == ProtocolMessageType.ANALYSIS_RESULT
    
    def handle(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        if message.is_expired():
            return None
        
        # Store and process result
        self.received_results[message.sender_id] = message
        self.on_result(message)
        
        # Send acknowledgment
        return ProtocolMessage(
            message_id=str(uuid.uuid4()),
            message_type=ProtocolMessageType.RESULT_ACK,
            sender_id=self.agent_id,
            receiver_id=message.sender_id,
            priority=MessagePriority.LOW,
            payload={"received_message_id": message.message_id},
            correlation_id=message.message_id,
        )


class QueryResponseHandler(ProtocolHandler):
    """Handler for query-response interactions"""
    
    def __init__(
        self,
        agent_id: str,
        query_handlers: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]],
    ):
        self.agent_id = agent_id
        self.query_handlers = query_handlers
        self.pending_queries: Dict[str, ProtocolMessage] = {}
        self.responses: Dict[str, ProtocolMessage] = {}
    
    def can_handle(self, message: ProtocolMessage) -> bool:
        return message.message_type in [
            ProtocolMessageType.QUERY,
            ProtocolMessageType.RESPONSE,
        ]
    
    def handle(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        if message.message_type == ProtocolMessageType.QUERY:
            return self._handle_query(message)
        elif message.message_type == ProtocolMessageType.RESPONSE:
            return self._handle_response(message)
        return None
    
    def _handle_query(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        query_type = message.payload.get("query_type")
        
        if query_type not in self.query_handlers:
            return ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.RESPONSE,
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                priority=message.priority,
                payload={"error": f"Unknown query type: {query_type}"},
                correlation_id=message.message_id,
            )
        
        # Execute query handler
        try:
            result = self.query_handlers[query_type](message.payload)
            return ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.RESPONSE,
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                priority=message.priority,
                payload=result,
                correlation_id=message.message_id,
            )
        except Exception as e:
            return ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.RESPONSE,
                sender_id=self.agent_id,
                receiver_id=message.sender_id,
                priority=message.priority,
                payload={"error": str(e)},
                correlation_id=message.message_id,
            )
    
    def _handle_response(self, message: ProtocolMessage) -> None:
        if message.correlation_id:
            self.responses[message.correlation_id] = message
        return None


# =============================================================================
# Voting Protocol
# =============================================================================

@dataclass
class VoteRequest:
    """Request for agents to vote on a decision"""
    request_id: str
    question: str
    context: Dict[str, Any]
    options: List[str]
    deadline: datetime
    min_votes: int
    initiator_id: str
    voting_agents: List[str]
    
    def is_expired(self) -> bool:
        return datetime.utcnow() > self.deadline


@dataclass
class Vote:
    """An agent's vote on a decision"""
    vote_id: str
    request_id: str
    voter_id: str
    choice: str
    confidence: float
    weight: float
    rationale: str
    evidence: List[Dict[str, Any]]
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class VoteResult:
    """Aggregated result of a voting round"""
    request_id: str
    question: str
    votes: List[Vote]
    winner: str
    consensus_reached: bool
    total_weight: float
    winning_weight: float
    participation_rate: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


class VotingProtocol:
    """
    Implements structured voting protocol for multi-agent decisions.
    
    Protocol Flow:
    1. Initiator broadcasts VOTE_REQUEST to voting agents
    2. Each agent responds with VOTE message
    3. Initiator aggregates votes and broadcasts VOTE_RESULT
    """
    
    def __init__(self, agent_id: str, message_bus: "ProtocolMessageBus"):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.pending_requests: Dict[str, VoteRequest] = {}
        self.received_votes: Dict[str, List[Vote]] = defaultdict(list)
        self.results: Dict[str, VoteResult] = {}
    
    def initiate_vote(
        self,
        question: str,
        context: Dict[str, Any],
        options: List[str],
        voting_agents: List[str],
        timeout_seconds: float = 30.0,
        min_votes: int = 1,
    ) -> str:
        """Initiate a voting round"""
        request = VoteRequest(
            request_id=str(uuid.uuid4()),
            question=question,
            context=context,
            options=options,
            deadline=datetime.utcnow() + timedelta(seconds=timeout_seconds),
            min_votes=min_votes,
            initiator_id=self.agent_id,
            voting_agents=voting_agents,
        )
        
        self.pending_requests[request.request_id] = request
        
        # Broadcast vote request
        for agent_id in voting_agents:
            message = ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.VOTE_REQUEST,
                sender_id=self.agent_id,
                receiver_id=agent_id,
                priority=MessagePriority.HIGH,
                payload={
                    "request_id": request.request_id,
                    "question": question,
                    "context": context,
                    "options": options,
                    "deadline": request.deadline.isoformat(),
                },
            )
            self.message_bus.send(message)
        
        return request.request_id
    
    def cast_vote(
        self,
        request_id: str,
        choice: str,
        confidence: float,
        weight: float,
        rationale: str,
        evidence: Optional[List[Dict[str, Any]]] = None,
    ) -> Vote:
        """Cast a vote on a pending request"""
        vote = Vote(
            vote_id=str(uuid.uuid4()),
            request_id=request_id,
            voter_id=self.agent_id,
            choice=choice,
            confidence=confidence,
            weight=weight,
            rationale=rationale,
            evidence=evidence or [],
        )
        
        # Send vote to initiator
        if request_id in self.pending_requests:
            initiator = self.pending_requests[request_id].initiator_id
        else:
            # Find from received request
            initiator = None  # Would be stored from received request
        
        if initiator:
            message = ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.VOTE,
                sender_id=self.agent_id,
                receiver_id=initiator,
                priority=MessagePriority.HIGH,
                payload={
                    "vote_id": vote.vote_id,
                    "request_id": request_id,
                    "choice": choice,
                    "confidence": confidence,
                    "weight": weight,
                    "rationale": rationale,
                    "evidence": evidence or [],
                },
                correlation_id=request_id,
            )
            self.message_bus.send(message)
        
        return vote
    
    def receive_vote(self, message: ProtocolMessage) -> None:
        """Receive a vote from another agent"""
        payload = message.payload
        vote = Vote(
            vote_id=payload["vote_id"],
            request_id=payload["request_id"],
            voter_id=message.sender_id,
            choice=payload["choice"],
            confidence=payload["confidence"],
            weight=payload["weight"],
            rationale=payload["rationale"],
            evidence=payload.get("evidence", []),
        )
        self.received_votes[vote.request_id].append(vote)
    
    def tally_votes(self, request_id: str) -> Optional[VoteResult]:
        """Tally votes for a request"""
        if request_id not in self.pending_requests:
            return None
        
        request = self.pending_requests[request_id]
        votes = self.received_votes.get(request_id, [])
        
        if len(votes) < request.min_votes:
            return None
        
        # Aggregate weighted votes
        vote_totals: Dict[str, float] = defaultdict(float)
        for vote in votes:
            vote_totals[vote.choice] += vote.weight * vote.confidence
        
        total_weight = sum(vote_totals.values())
        
        if total_weight == 0:
            winner = request.options[0] if request.options else "unknown"
            winning_weight = 0
        else:
            winner = max(vote_totals.keys(), key=lambda k: vote_totals[k])
            winning_weight = vote_totals[winner]
        
        participation_rate = len(votes) / len(request.voting_agents) if request.voting_agents else 0
        consensus_reached = (winning_weight / total_weight > 0.6) if total_weight > 0 else False
        
        result = VoteResult(
            request_id=request_id,
            question=request.question,
            votes=votes,
            winner=winner,
            consensus_reached=consensus_reached,
            total_weight=total_weight,
            winning_weight=winning_weight,
            participation_rate=participation_rate,
        )
        
        self.results[request_id] = result
        
        # Broadcast result
        for agent_id in request.voting_agents:
            message = ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.VOTE_RESULT,
                sender_id=self.agent_id,
                receiver_id=agent_id,
                priority=MessagePriority.NORMAL,
                payload={
                    "request_id": request_id,
                    "winner": winner,
                    "consensus_reached": consensus_reached,
                    "participation_rate": participation_rate,
                },
                correlation_id=request_id,
            )
            self.message_bus.send(message)
        
        return result


# =============================================================================
# Escalation Protocol
# =============================================================================

@dataclass
class Escalation:
    """An escalation from one agent to another"""
    escalation_id: str
    source_agent: str
    target_agent: str
    concern_type: str
    severity: str
    description: str
    evidence: List[Dict[str, Any]]
    recommended_action: str
    timestamp: datetime = field(default_factory=datetime.utcnow)


class EscalationProtocol:
    """
    Implements escalation protocol for agents to raise concerns.
    
    Use Cases:
    - Sensor trust agent flags unreliable data
    - Change detection agent flags persistent anomaly
    - Fault hypothesis agent flags confident diagnosis
    """
    
    def __init__(self, agent_id: str, message_bus: "ProtocolMessageBus"):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.escalations_sent: List[Escalation] = []
        self.escalations_received: List[Escalation] = []
    
    def escalate(
        self,
        target_agent: str,
        concern_type: str,
        severity: str,
        description: str,
        evidence: List[Dict[str, Any]],
        recommended_action: str,
    ) -> Escalation:
        """Escalate a concern to another agent"""
        escalation = Escalation(
            escalation_id=str(uuid.uuid4()),
            source_agent=self.agent_id,
            target_agent=target_agent,
            concern_type=concern_type,
            severity=severity,
            description=description,
            evidence=evidence,
            recommended_action=recommended_action,
        )
        
        self.escalations_sent.append(escalation)
        
        message = ProtocolMessage(
            message_id=str(uuid.uuid4()),
            message_type=ProtocolMessageType.ESCALATION,
            sender_id=self.agent_id,
            receiver_id=target_agent,
            priority=MessagePriority.HIGH if severity == "critical" else MessagePriority.NORMAL,
            payload={
                "escalation_id": escalation.escalation_id,
                "concern_type": concern_type,
                "severity": severity,
                "description": description,
                "evidence": evidence,
                "recommended_action": recommended_action,
            },
        )
        self.message_bus.send(message)
        
        return escalation
    
    def receive_escalation(self, message: ProtocolMessage) -> Escalation:
        """Receive an escalation from another agent"""
        payload = message.payload
        escalation = Escalation(
            escalation_id=payload["escalation_id"],
            source_agent=message.sender_id,
            target_agent=self.agent_id,
            concern_type=payload["concern_type"],
            severity=payload["severity"],
            description=payload["description"],
            evidence=payload.get("evidence", []),
            recommended_action=payload["recommended_action"],
        )
        
        self.escalations_received.append(escalation)
        
        # Send acknowledgment
        ack = ProtocolMessage(
            message_id=str(uuid.uuid4()),
            message_type=ProtocolMessageType.ESCALATION_ACK,
            sender_id=self.agent_id,
            receiver_id=message.sender_id,
            priority=MessagePriority.NORMAL,
            payload={"escalation_id": escalation.escalation_id, "received": True},
            correlation_id=message.message_id,
        )
        self.message_bus.send(ack)
        
        return escalation


# =============================================================================
# Consensus Protocol (Multi-Round)
# =============================================================================

@dataclass
class ConsensusRound:
    """A round in multi-round consensus building"""
    round_id: str
    round_number: int
    proposal: str
    votes: Dict[str, bool]  # agent_id -> agree/disagree
    rationales: Dict[str, str]
    
    def get_agreement_rate(self) -> float:
        if not self.votes:
            return 0.0
        return sum(self.votes.values()) / len(self.votes)


class ConsensusProtocol:
    """
    Implements multi-round consensus building for critical decisions.
    
    Protocol:
    1. Proposer submits initial proposal
    2. Agents vote with rationale
    3. If consensus not reached, refine proposal based on rationales
    4. Repeat until consensus or max rounds
    """
    
    def __init__(
        self,
        agent_id: str,
        message_bus: "ProtocolMessageBus",
        consensus_threshold: float = 0.8,
        max_rounds: int = 3,
    ):
        self.agent_id = agent_id
        self.message_bus = message_bus
        self.consensus_threshold = consensus_threshold
        self.max_rounds = max_rounds
        self.rounds: Dict[str, List[ConsensusRound]] = defaultdict(list)
    
    def initiate_consensus(
        self,
        proposal: str,
        context: Dict[str, Any],
        participating_agents: List[str],
    ) -> str:
        """Initiate a consensus-building process"""
        consensus_id = str(uuid.uuid4())
        
        round_0 = ConsensusRound(
            round_id=f"{consensus_id}_0",
            round_number=0,
            proposal=proposal,
            votes={},
            rationales={},
        )
        self.rounds[consensus_id].append(round_0)
        
        # Request votes from all agents
        for agent_id in participating_agents:
            message = ProtocolMessage(
                message_id=str(uuid.uuid4()),
                message_type=ProtocolMessageType.VOTE_REQUEST,
                sender_id=self.agent_id,
                receiver_id=agent_id,
                priority=MessagePriority.HIGH,
                payload={
                    "consensus_id": consensus_id,
                    "round_number": 0,
                    "proposal": proposal,
                    "context": context,
                    "type": "consensus",
                },
            )
            self.message_bus.send(message)
        
        return consensus_id
    
    def vote_on_proposal(
        self,
        consensus_id: str,
        round_number: int,
        agree: bool,
        rationale: str,
    ) -> None:
        """Vote on a consensus proposal"""
        message = ProtocolMessage(
            message_id=str(uuid.uuid4()),
            message_type=ProtocolMessageType.VOTE,
            sender_id=self.agent_id,
            receiver_id=None,  # Would go to initiator
            priority=MessagePriority.NORMAL,
            payload={
                "consensus_id": consensus_id,
                "round_number": round_number,
                "agree": agree,
                "rationale": rationale,
                "type": "consensus",
            },
        )
        self.message_bus.send(message)
    
    def receive_vote(
        self,
        consensus_id: str,
        round_number: int,
        voter_id: str,
        agree: bool,
        rationale: str,
    ) -> None:
        """Receive a vote on a consensus proposal"""
        if consensus_id not in self.rounds or round_number >= len(self.rounds[consensus_id]):
            return
        
        round_obj = self.rounds[consensus_id][round_number]
        round_obj.votes[voter_id] = agree
        round_obj.rationales[voter_id] = rationale
    
    def check_consensus(self, consensus_id: str) -> Tuple[bool, float]:
        """Check if consensus has been reached"""
        if consensus_id not in self.rounds:
            return False, 0.0
        
        latest_round = self.rounds[consensus_id][-1]
        agreement_rate = latest_round.get_agreement_rate()
        
        return agreement_rate >= self.consensus_threshold, agreement_rate


# =============================================================================
# Message Bus
# =============================================================================

class ProtocolMessageBus:
    """
    Central message bus for protocol communication.
    
    Features:
    - Priority-based message queuing
    - Message routing to appropriate handlers
    - Dead letter handling for undeliverable messages
    """
    
    def __init__(self):
        self.handlers: Dict[str, List[ProtocolHandler]] = defaultdict(list)
        self.message_queue: List[ProtocolMessage] = []
        self.dead_letters: List[ProtocolMessage] = []
        self.subscribers: Dict[str, List[Callable[[ProtocolMessage], None]]] = defaultdict(list)
    
    def register_handler(self, agent_id: str, handler: ProtocolHandler) -> None:
        """Register a handler for an agent"""
        self.handlers[agent_id].append(handler)
    
    def subscribe(self, agent_id: str, callback: Callable[[ProtocolMessage], None]) -> None:
        """Subscribe to messages for an agent"""
        self.subscribers[agent_id].append(callback)
    
    def send(self, message: ProtocolMessage) -> None:
        """Send a message"""
        # Add to queue sorted by priority
        priority_order = {
            MessagePriority.CRITICAL: 0,
            MessagePriority.HIGH: 1,
            MessagePriority.NORMAL: 2,
            MessagePriority.LOW: 3,
        }
        
        self.message_queue.append(message)
        self.message_queue.sort(key=lambda m: priority_order[m.priority])
    
    def deliver(self, message: ProtocolMessage) -> Optional[ProtocolMessage]:
        """Deliver a message to its recipient"""
        if message.is_expired():
            self.dead_letters.append(message)
            return None
        
        target_id = message.receiver_id
        
        # Broadcast message
        if target_id is None:
            for agent_id, handlers in self.handlers.items():
                if agent_id != message.sender_id:
                    for handler in handlers:
                        if handler.can_handle(message):
                            handler.handle(message)
            return None
        
        # Directed message
        if target_id not in self.handlers:
            self.dead_letters.append(message)
            return None
        
        for handler in self.handlers[target_id]:
            if handler.can_handle(message):
                response = handler.handle(message)
                if response:
                    return response
        
        # Notify subscribers
        for callback in self.subscribers.get(target_id, []):
            callback(message)
        
        return None
    
    def process_queue(self) -> int:
        """Process all messages in the queue"""
        processed = 0
        responses = []
        
        while self.message_queue:
            message = self.message_queue.pop(0)
            response = self.deliver(message)
            if response:
                responses.append(response)
            processed += 1
        
        # Queue any responses
        for response in responses:
            self.send(response)
        
        return processed


# =============================================================================
# Agent Protocol Mixin
# =============================================================================

class ProtocolEnabledAgent:
    """
    Mixin that adds protocol capabilities to PDM agents.
    
    Provides:
    - Result broadcasting
    - Query-response handling
    - Voting participation
    - Escalation sending/receiving
    """
    
    def __init__(self, agent_id: str, message_bus: ProtocolMessageBus):
        self.protocol_agent_id = agent_id
        self.protocol_bus = message_bus
        
        # Initialize protocols
        self.voting_protocol = VotingProtocol(agent_id, message_bus)
        self.escalation_protocol = EscalationProtocol(agent_id, message_bus)
        
        # Result broadcasting
        self._result_handler = ResultBroadcastHandler(
            agent_id, self._on_upstream_result
        )
        message_bus.register_handler(agent_id, self._result_handler)
    
    def broadcast_analysis_result(
        self,
        result_type: str,
        result_data: Dict[str, Any],
        confidence: float,
    ) -> None:
        """Broadcast an analysis result to downstream agents"""
        message = ProtocolMessage(
            message_id=str(uuid.uuid4()),
            message_type=ProtocolMessageType.ANALYSIS_RESULT,
            sender_id=self.protocol_agent_id,
            receiver_id=None,  # Broadcast
            priority=MessagePriority.NORMAL,
            payload={
                "result_type": result_type,
                "result_data": result_data,
                "confidence": confidence,
            },
        )
        self.protocol_bus.send(message)
    
    def _on_upstream_result(self, message: ProtocolMessage) -> None:
        """Called when an upstream result is received"""
        pass  # Override in subclass
    
    def escalate_concern(
        self,
        target_agent: str,
        concern_type: str,
        severity: str,
        description: str,
        evidence: List[Dict[str, Any]],
        recommended_action: str,
    ) -> None:
        """Escalate a concern to another agent"""
        self.escalation_protocol.escalate(
            target_agent, concern_type, severity, description, evidence, recommended_action
        )
    
    def participate_in_vote(
        self,
        request_id: str,
        choice: str,
        confidence: float,
        weight: float,
        rationale: str,
    ) -> None:
        """Participate in a voting round"""
        self.voting_protocol.cast_vote(
            request_id, choice, confidence, weight, rationale
        )


# =============================================================================
# Factory
# =============================================================================

def create_protocol_bus() -> ProtocolMessageBus:
    """Create a new protocol message bus"""
    return ProtocolMessageBus()


def enable_agent_protocols(
    agent_id: str,
    message_bus: ProtocolMessageBus,
) -> ProtocolEnabledAgent:
    """Enable protocol capabilities for an agent"""
    return ProtocolEnabledAgent(agent_id, message_bus)
