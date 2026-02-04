"""
Redis Event Bus for Multi-Agent Collaboration

Provides a Redis-backed event bus for inter-agent communication
with support for pub/sub messaging, event persistence, and
distributed agent coordination.

Features:
- Pub/sub messaging between agents
- Event persistence for replay and audit
- Topic-based subscriptions
- Event deduplication
- Dead letter queue for failed deliveries
"""

import logging
import json
import uuid
import asyncio
from typing import Dict, List, Optional, Any, Callable, Union
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from enum import Enum
from abc import ABC, abstractmethod
import threading
import time

logger = logging.getLogger(__name__)

# Redis imports with fallback
REDIS_AVAILABLE = False
try:
    import redis
    from redis import Redis
    from redis.client import PubSub
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis not installed. Using in-memory fallback.")
    Redis = None
    PubSub = None


# =============================================================================
# Event Types for PdM Agents
# =============================================================================

class PdMEventType(str, Enum):
    """Event types for Predictive Maintenance agent collaboration"""
    # Telemetry
    TELEMETRY_RECEIVED = "telemetry.received"
    ANALYSIS_COMPLETE = "analysis.complete"
    # Alert & Case Events
    ALERT_CREATED = "alert.created"
    ALERT_UPDATED = "alert.updated"
    ALERT_CLUSTERED = "alert.clustered"
    CASE_CREATED = "case.created"
    CASE_UPDATED = "case.updated"
    CASE_TRIAGED = "case.triaged"
    CASE_CLOSED = "case.closed"
    
    # Work Order Events
    WORK_ORDER_DRAFTED = "work_order.drafted"
    WORK_ORDER_SUBMITTED = "work_order.submitted"
    WORK_ORDER_COMPLETED = "work_order.completed"
    WORK_ORDER_VERIFIED = "work_order.verified"
    
    # Dispatch Events
    DISPATCH_BATCH_CREATED = "dispatch.batch_created"
    DISPATCH_SCHEDULED = "dispatch.scheduled"
    DISPATCH_COMPLETED = "dispatch.completed"
    
    # Model & Experimentation Events
    MODEL_DRIFT_DETECTED = "model.drift_detected"
    MODEL_RETRAIN_TRIGGERED = "model.retrain_triggered"
    MODEL_PROMOTION_REQUESTED = "model.promotion_requested"
    EXPERIMENT_COMPLETED = "experiment.completed"
    
    # Data Quality Events
    DATA_QUALITY_ISSUE = "data.quality_issue"
    DATA_GAP_DETECTED = "data.gap_detected"
    SENSOR_OFFLINE = "sensor.offline"
    
    # Agent Coordination Events
    AGENT_TASK_REQUEST = "agent.task_request"
    AGENT_TASK_RESULT = "agent.task_result"
    AGENT_HEARTBEAT = "agent.heartbeat"
    AGENT_HANDOFF = "agent.handoff"
    
    # Verification Events
    VERIFICATION_STARTED = "verification.started"
    VERIFICATION_PASSED = "verification.passed"
    VERIFICATION_FAILED = "verification.failed"
    
    # Evidence & Explainability Events
    EVIDENCE_PACKAGE_CREATED = "evidence.package_created"
    MAINTENANCE_PACKET_CREATED = "maintenance.packet_created"


# =============================================================================
# Event Payload Structures
# =============================================================================

@dataclass
class PdMEvent:
    """Base event structure for all PdM events"""
    event_id: str
    event_type: PdMEventType
    source_agent: str
    timestamp: datetime
    
    # Core identifiers
    tenant_id: Optional[str] = None
    site_id: Optional[str] = None
    asset_id: Optional[str] = None
    case_id: Optional[str] = None
    
    # Payload
    payload: Dict[str, Any] = field(default_factory=dict)
    
    # Routing
    target_agents: Optional[List[str]] = None  # None = broadcast
    priority: int = 5  # 1-10, 1 highest
    
    # Correlation
    correlation_id: Optional[str] = None
    causation_id: Optional[str] = None
    
    # TTL and processing
    ttl_seconds: int = 3600
    retry_count: int = 0
    max_retries: int = 3
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "source_agent": self.source_agent,
            "timestamp": self.timestamp.isoformat(),
            "tenant_id": self.tenant_id,
            "site_id": self.site_id,
            "asset_id": self.asset_id,
            "case_id": self.case_id,
            "payload": self.payload,
            "target_agents": self.target_agents,
            "priority": self.priority,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "ttl_seconds": self.ttl_seconds,
            "retry_count": self.retry_count,
            "max_retries": self.max_retries,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PdMEvent":
        return cls(
            event_id=data["event_id"],
            event_type=PdMEventType(data["event_type"]),
            source_agent=data["source_agent"],
            timestamp=datetime.fromisoformat(data["timestamp"]),
            tenant_id=data.get("tenant_id"),
            site_id=data.get("site_id"),
            asset_id=data.get("asset_id"),
            case_id=data.get("case_id"),
            payload=data.get("payload", {}),
            target_agents=data.get("target_agents"),
            priority=data.get("priority", 5),
            correlation_id=data.get("correlation_id"),
            causation_id=data.get("causation_id"),
            ttl_seconds=data.get("ttl_seconds", 3600),
            retry_count=data.get("retry_count", 0),
            max_retries=data.get("max_retries", 3),
        )
    
    def to_json(self) -> str:
        return json.dumps(self.to_dict())
    
    @classmethod
    def from_json(cls, json_str: str) -> "PdMEvent":
        return cls.from_dict(json.loads(json_str))


# =============================================================================
# Event Handler Protocol
# =============================================================================

class EventHandler(ABC):
    """Abstract base class for event handlers"""
    
    @abstractmethod
    def handle(self, event: PdMEvent) -> Optional[PdMEvent]:
        """
        Handle an event.
        
        Returns:
            Optional response event to publish, or None
        """
        pass
    
    @property
    @abstractmethod
    def handled_event_types(self) -> List[PdMEventType]:
        """Event types this handler subscribes to"""
        pass


# =============================================================================
# Redis Event Bus
# =============================================================================

class RedisEventBus:
    """
    Redis-backed event bus for multi-agent collaboration.
    
    Supports:
    - Pub/sub for real-time event delivery
    - Streams for persistent event log
    - Consumer groups for load balancing
    - Dead letter queue for failed events
    """
    
    CHANNEL_PREFIX = "pdm:events:"
    STREAM_KEY = "pdm:event_stream"
    DLQ_KEY = "pdm:dead_letter_queue"
    AGENT_REGISTRY_KEY = "pdm:agents"
    
    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        agent_id: str = "default",
        use_streams: bool = True,
        consumer_group: Optional[str] = None,
    ):
        self.agent_id = agent_id
        self.use_streams = use_streams
        self.consumer_group = consumer_group or f"pdm_agents_{agent_id}"
        self._handlers: Dict[PdMEventType, List[EventHandler]] = {}
        self._running = False
        self._listener_thread: Optional[threading.Thread] = None
        
        if REDIS_AVAILABLE:
            self._redis = redis.from_url(redis_url, decode_responses=True)
            self._pubsub = self._redis.pubsub()
            self._init_consumer_group()
        else:
            self._redis = None
            self._pubsub = None
            self._in_memory_events: List[PdMEvent] = []
            logger.warning("Redis not available, using in-memory event storage")
    
    def _init_consumer_group(self):
        """Initialize Redis Streams consumer group"""
        if not self._redis or not self.use_streams:
            return
        
        try:
            self._redis.xgroup_create(
                self.STREAM_KEY,
                self.consumer_group,
                id="0",
                mkstream=True
            )
        except redis.exceptions.ResponseError as e:
            if "BUSYGROUP" not in str(e):
                raise
    
    def register_handler(self, handler: EventHandler):
        """Register an event handler"""
        for event_type in handler.handled_event_types:
            if event_type not in self._handlers:
                self._handlers[event_type] = []
            self._handlers[event_type].append(handler)
            
            # Subscribe to Redis channel for this event type
            if self._pubsub:
                channel = f"{self.CHANNEL_PREFIX}{event_type.value}"
                self._pubsub.subscribe(channel)
        
        logger.info(f"Registered handler for events: {handler.handled_event_types}")
    
    def publish(self, event: PdMEvent) -> str:
        """
        Publish an event to the bus.
        
        Returns:
            Event ID
        """
        event_json = event.to_json()
        
        if self._redis:
            # Publish to pub/sub channel
            channel = f"{self.CHANNEL_PREFIX}{event.event_type.value}"
            self._redis.publish(channel, event_json)
            
            # Also add to stream for persistence
            if self.use_streams:
                self._redis.xadd(
                    self.STREAM_KEY,
                    {"event": event_json},
                    maxlen=10000  # Keep last 10k events
                )
            
            logger.debug(f"Published event {event.event_id} to {channel}")
        else:
            # In-memory fallback
            self._in_memory_events.append(event)
            self._dispatch_to_handlers(event)
        
        return event.event_id
    
    def _dispatch_to_handlers(self, event: PdMEvent):
        """Dispatch event to registered handlers"""
        handlers = self._handlers.get(event.event_type, [])
        
        for handler in handlers:
            try:
                response = handler.handle(event)
                if response:
                    self.publish(response)
            except Exception as e:
                logger.error(f"Handler error for {event.event_id}: {e}")
                self._send_to_dlq(event, str(e))
    
    def _send_to_dlq(self, event: PdMEvent, error: str):
        """Send failed event to dead letter queue"""
        if not self._redis:
            return
        
        dlq_entry = {
            "event": event.to_json(),
            "error": error,
            "failed_at": datetime.utcnow().isoformat(),
            "agent_id": self.agent_id,
        }
        self._redis.lpush(self.DLQ_KEY, json.dumps(dlq_entry))
    
    def start_listening(self):
        """Start listening for events in background thread"""
        if not self._redis:
            logger.warning("Redis not available, cannot start listener")
            return
        
        self._running = True
        self._listener_thread = threading.Thread(
            target=self._listen_loop,
            daemon=True
        )
        self._listener_thread.start()
        logger.info(f"Event bus listener started for agent {self.agent_id}")
    
    def stop_listening(self):
        """Stop the event listener"""
        self._running = False
        if self._listener_thread:
            self._listener_thread.join(timeout=5)
    
    def _listen_loop(self):
        """Main listening loop for pub/sub messages"""
        while self._running:
            try:
                message = self._pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    event = PdMEvent.from_json(message["data"])
                    self._dispatch_to_handlers(event)
            except Exception as e:
                logger.error(f"Error in listener loop: {e}")
                time.sleep(1)
    
    def get_events(
        self,
        event_types: Optional[List[PdMEventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PdMEvent]:
        """Get events from the stream"""
        if not self._redis or not self.use_streams:
            # In-memory fallback
            events = self._in_memory_events[-limit:]
            if event_types:
                events = [e for e in events if e.event_type in event_types]
            if since:
                events = [e for e in events if e.timestamp >= since]
            return events
        
        # Read from Redis stream
        start_id = "-" if not since else f"{int(since.timestamp() * 1000)}-0"
        
        messages = self._redis.xrange(
            self.STREAM_KEY,
            min=start_id,
            count=limit
        )
        
        events = []
        for msg_id, msg_data in messages:
            event = PdMEvent.from_json(msg_data["event"])
            if not event_types or event.event_type in event_types:
                events.append(event)
        
        return events
    
    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]):
        """Register an agent in the shared registry"""
        if not self._redis:
            return
        
        agent_info["registered_at"] = datetime.utcnow().isoformat()
        agent_info["last_heartbeat"] = datetime.utcnow().isoformat()
        self._redis.hset(self.AGENT_REGISTRY_KEY, agent_id, json.dumps(agent_info))
    
    def get_registered_agents(self) -> Dict[str, Dict[str, Any]]:
        """Get all registered agents"""
        if not self._redis:
            return {}
        
        agents = self._redis.hgetall(self.AGENT_REGISTRY_KEY)
        return {k: json.loads(v) for k, v in agents.items()}
    
    def send_heartbeat(self):
        """Send agent heartbeat"""
        self.publish(PdMEvent(
            event_id=str(uuid.uuid4()),
            event_type=PdMEventType.AGENT_HEARTBEAT,
            source_agent=self.agent_id,
            timestamp=datetime.utcnow(),
            payload={"status": "alive"},
        ))


# =============================================================================
# Event Factory
# =============================================================================

class PdMEventFactory:
    """Factory for creating typed PdM events"""
    
    def __init__(self, source_agent: str, tenant_id: Optional[str] = None):
        self.source_agent = source_agent
        self.tenant_id = tenant_id
    
    def _create_base(
        self,
        event_type: PdMEventType,
        payload: Dict[str, Any],
        **kwargs
    ) -> PdMEvent:
        return PdMEvent(
            event_id=str(uuid.uuid4()),
            event_type=event_type,
            source_agent=self.source_agent,
            timestamp=datetime.utcnow(),
            tenant_id=self.tenant_id,
            payload=payload,
            **kwargs
        )
    
    def alert_created(
        self,
        alert_id: str,
        asset_id: str,
        site_id: str,
        alert_type: str,
        severity: str,
        confidence: float,
        ev_score: float,
        contributing_metrics: List[Dict[str, Any]],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.ALERT_CREATED,
            {
                "alert_id": alert_id,
                "alert_type": alert_type,
                "severity": severity,
                "confidence": confidence,
                "ev_score": ev_score,
                "contributing_metrics": contributing_metrics,
            },
            asset_id=asset_id,
            site_id=site_id,
        )
    
    def case_created(
        self,
        case_id: str,
        asset_id: str,
        site_id: str,
        title: str,
        severity: str,
        ev_score: float,
        alert_ids: List[str],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.CASE_CREATED,
            {
                "title": title,
                "severity": severity,
                "ev_score": ev_score,
                "alert_ids": alert_ids,
            },
            case_id=case_id,
            asset_id=asset_id,
            site_id=site_id,
        )
    
    def case_triaged(
        self,
        case_id: str,
        triage_decision: str,  # 'monitor' | 'triage' | 'dispatch'
        cluster_id: Optional[str],
        rationale: str,
        priority_score: float,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.CASE_TRIAGED,
            {
                "triage_decision": triage_decision,
                "cluster_id": cluster_id,
                "rationale": rationale,
                "priority_score": priority_score,
            },
            case_id=case_id,
        )
    
    def work_order_drafted(
        self,
        case_id: str,
        work_order_id: str,
        title: str,
        description: str,
        priority: str,
        estimated_parts: List[str],
        estimated_duration_hours: float,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.WORK_ORDER_DRAFTED,
            {
                "work_order_id": work_order_id,
                "title": title,
                "description": description,
                "priority": priority,
                "estimated_parts": estimated_parts,
                "estimated_duration_hours": estimated_duration_hours,
            },
            case_id=case_id,
        )
    
    def maintenance_packet_created(
        self,
        case_id: str,
        packet_id: str,
        problem_statement: str,
        evidence_items: List[Dict[str, Any]],
        likely_root_causes: List[str],
        recommended_actions: List[Dict[str, Any]],
        safety_notes: List[str],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.MAINTENANCE_PACKET_CREATED,
            {
                "packet_id": packet_id,
                "problem_statement": problem_statement,
                "evidence_items": evidence_items,
                "likely_root_causes": likely_root_causes,
                "recommended_actions": recommended_actions,
                "safety_notes": safety_notes,
            },
            case_id=case_id,
        )
    
    def dispatch_batch_created(
        self,
        batch_id: str,
        site_id: str,
        case_ids: List[str],
        total_ev: float,
        estimated_savings: float,
        rationale: str,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.DISPATCH_BATCH_CREATED,
            {
                "batch_id": batch_id,
                "case_ids": case_ids,
                "total_ev": total_ev,
                "estimated_savings": estimated_savings,
                "rationale": rationale,
            },
            site_id=site_id,
        )
    
    def verification_result(
        self,
        case_id: str,
        passed: bool,
        verification_method: str,
        confidence: float,
        evidence: Dict[str, Any],
        recommendation: str,
    ) -> PdMEvent:
        event_type = PdMEventType.VERIFICATION_PASSED if passed else PdMEventType.VERIFICATION_FAILED
        return self._create_base(
            event_type,
            {
                "passed": passed,
                "verification_method": verification_method,
                "confidence": confidence,
                "evidence": evidence,
                "recommendation": recommendation,
            },
            case_id=case_id,
        )
    
    def model_promotion_requested(
        self,
        model_id: str,
        current_version: str,
        proposed_version: str,
        justification: str,
        metrics_comparison: Dict[str, Any],
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.MODEL_PROMOTION_REQUESTED,
            {
                "model_id": model_id,
                "current_version": current_version,
                "proposed_version": proposed_version,
                "justification": justification,
                "metrics_comparison": metrics_comparison,
            },
        )
    
    def data_quality_issue(
        self,
        asset_id: str,
        site_id: str,
        issue_type: str,
        affected_sensors: List[str],
        severity: str,
        diagnosis: str,
        recommended_action: str,
    ) -> PdMEvent:
        return self._create_base(
            PdMEventType.DATA_QUALITY_ISSUE,
            {
                "issue_type": issue_type,
                "affected_sensors": affected_sensors,
                "severity": severity,
                "diagnosis": diagnosis,
                "recommended_action": recommended_action,
            },
            asset_id=asset_id,
            site_id=site_id,
        )


# =============================================================================
# In-Memory Event Bus (for testing without Redis)
# =============================================================================

class InMemoryEventBus(RedisEventBus):
    """In-memory event bus for testing without Redis"""
    
    def __init__(self, agent_id: str = "test"):
        self.agent_id = agent_id
        self.use_streams = False
        self.consumer_group = f"pdm_agents_{agent_id}"
        self._redis = None
        self._pubsub = None
        self._handlers: Dict[PdMEventType, List[EventHandler]] = {}
        self._events: List[PdMEvent] = []
        self._running = False
    
    def publish(self, event: PdMEvent) -> str:
        self._events.append(event)
        self._dispatch_to_handlers(event)
        return event.event_id
    
    def _dispatch_to_handlers(self, event: PdMEvent):
        handlers = self._handlers.get(event.event_type, [])
        for handler in handlers:
            try:
                response = handler.handle(event)
                if response:
                    self.publish(response)
            except Exception as e:
                logger.error(f"Handler error: {e}")
    
    def get_events(
        self,
        event_types: Optional[List[PdMEventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PdMEvent]:
        events = self._events[-limit:]
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        if since:
            events = [e for e in events if e.timestamp >= since]
        return events
    
    def start_listening(self):
        self._running = True
    
    def stop_listening(self):
        self._running = False


# Backward-compatible aliases
PDMEventType = PdMEventType
PDMEvent = PdMEvent
PDMEventBus = RedisEventBus
