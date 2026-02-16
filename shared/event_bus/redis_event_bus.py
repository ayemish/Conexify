"""
Unified Redis Event Bus — single canonical implementation.

Supports BOTH:
- PdM-style: register_handler(EventHandler), publish(PdMEvent)
- Loweconex-style: subscribe(event_type, callback), publish(EventEnvelope)

Both envelope types implement to_json()/from_json() — the bus is
envelope-agnostic internally (stores JSON strings in Redis Streams).

Features:
- Redis Streams for durable, ordered event delivery
- Consumer groups for load-balanced processing
- Dead-letter queue for failed messages
- Pub/Sub for real-time transient updates
- Automatic retry with backoff
- In-memory fallback for dev/testing
"""

import json
import logging
import threading
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Union

from shared.event_bus.events import (
    EventEnvelope,
    EventHandler,
    EventType,
    PdMEvent,
    PdMEventType,
)

logger = logging.getLogger(__name__)

# Redis imports with fallback
REDIS_AVAILABLE = False
try:
    import redis
    REDIS_AVAILABLE = True
except ImportError:
    logger.warning("Redis not installed. Using in-memory fallback.")
    redis = None


# Type alias: handler can be either an EventHandler object or a callable
EventCallback = Callable[[Any], None]


class RedisEventBus:
    """
    Unified Redis-backed event bus for multi-agent collaboration.

    Supports two usage patterns:

    PdM pattern (handler objects):
        bus.register_handler(my_handler)   # EventHandler with handled_event_types
        bus.publish(pdm_event)             # PdMEvent

    Loweconex pattern (callable subscriptions):
        bus.subscribe("KPI_COMPUTED", my_callback)
        bus.publish(envelope)              # EventEnvelope

    Both patterns work simultaneously on the same bus instance.
    """

    CHANNEL_PREFIX = "platform:events:"
    STREAM_PREFIX = "platform:stream:"
    DLQ_STREAM = "platform:dlq"
    AGENT_REGISTRY_KEY = "platform:agents"

    def __init__(
        self,
        redis_url: str = "redis://localhost:6379",
        agent_id: str = "default",
        consumer_group: str = "platform_agents",
        consumer_name: Optional[str] = None,
        use_streams: bool = True,
        stream_maxlen: int = 100_000,
        retry_max: int = 3,
        retry_backoff_ms: int = 1000,
    ):
        self.agent_id = agent_id
        self.use_streams = use_streams
        self.consumer_group = consumer_group
        self.consumer_name = consumer_name or f"consumer_{agent_id}_{id(self)}"
        self.stream_maxlen = stream_maxlen
        self.retry_max = retry_max
        self.retry_backoff_ms = retry_backoff_ms

        # PdM-style handlers: event_type -> [EventHandler]
        self._pdm_handlers: Dict[PdMEventType, List[EventHandler]] = {}
        # Loweconex-style handlers: event_type_str -> [Callable]
        self._handlers: Dict[str, List[EventCallback]] = defaultdict(list)

        self._running = False
        self._listener_threads: List[threading.Thread] = []

        # In-memory fallback state
        self._in_memory_events: List[Any] = []  # mixed PdMEvent / EventEnvelope
        self._in_memory_streams: Dict[str, List[Any]] = defaultdict(list)

        if REDIS_AVAILABLE and redis is not None:
            try:
                self._redis = redis.from_url(redis_url, decode_responses=True)
                self._redis.ping()
                self._pubsub = self._redis.pubsub()
                if use_streams:
                    self._ensure_consumer_group(self._main_stream_key())
                logger.info(f"Connected to Redis at {redis_url}")
            except Exception as e:
                logger.warning(f"Redis not reachable ({e}), falling back to in-memory")
                self._redis = None
                self._pubsub = None
        else:
            self._redis = None
            self._pubsub = None
            logger.warning("Redis not available, using in-memory event bus")

    # -------------------------------------------------------------------------
    # Key helpers
    # -------------------------------------------------------------------------

    def _main_stream_key(self) -> str:
        return f"{self.STREAM_PREFIX}main"

    def _typed_stream_key(self, event_type: str) -> str:
        return f"{self.STREAM_PREFIX}{event_type}"

    def _ensure_consumer_group(self, stream_key: str):
        if not self._redis:
            return
        try:
            self._redis.xgroup_create(
                stream_key, self.consumer_group, id="0", mkstream=True
            )
        except Exception as e:
            if "BUSYGROUP" not in str(e):
                raise

    # -------------------------------------------------------------------------
    # Publish (supports both PdMEvent and EventEnvelope)
    # -------------------------------------------------------------------------

    @staticmethod
    def validate_envelope(event: Union[PdMEvent, EventEnvelope]) -> List[str]:
        """
        Validate an event envelope before publishing.
        Returns a list of validation errors (empty = valid).
        """
        errors: List[str] = []
        if isinstance(event, EventEnvelope):
            if not event.event_type:
                errors.append("EventEnvelope missing event_type")
            if not event.company_id:
                errors.append("EventEnvelope missing company_id")
            if not event.msg_id:
                errors.append("EventEnvelope missing msg_id")
            if not event.payload_schema_version:
                errors.append("EventEnvelope missing payload_schema_version")
        elif isinstance(event, PdMEvent):
            if not event.event_id:
                errors.append("PdMEvent missing event_id")
            if not event.source_agent:
                errors.append("PdMEvent missing source_agent")
        return errors

    def publish(self, event: Union[PdMEvent, EventEnvelope]) -> str:
        """
        Publish an event (PdMEvent or EventEnvelope) to the bus.
        Validates envelope schema before publishing; malformed messages go to DLQ.
        Returns the message/event ID.
        """
        # Schema validation gate
        validation_errors = self.validate_envelope(event)
        if validation_errors:
            event_id = getattr(event, "msg_id", getattr(event, "event_id", str(uuid.uuid4())))
            event_json = event.to_json() if hasattr(event, "to_json") else str(event)
            error_msg = f"Schema validation failed: {'; '.join(validation_errors)}"
            logger.warning(f"Publish rejected for {event_id}: {error_msg}")
            self._send_to_dlq("SCHEMA_VALIDATION", event_id, event_json, error_msg)
            return str(event_id)

        event_json = event.to_json()

        # Determine event type string for routing
        if isinstance(event, PdMEvent):
            event_type_str = event.event_type.value
            event_id = event.event_id
        elif isinstance(event, EventEnvelope):
            event_type_str = event.event_type
            event_id = event.msg_id
        else:
            # Duck typing fallback: anything with to_json
            event_type_str = getattr(event, "event_type", "unknown")
            if hasattr(event_type_str, "value"):
                event_type_str = event_type_str.value
            event_id = getattr(event, "event_id", getattr(event, "msg_id", str(uuid.uuid4())))

        if self._redis:
            try:
                # Write to per-type stream
                typed_key = self._typed_stream_key(event_type_str)
                self._redis.xadd(
                    typed_key, {"event": event_json}, maxlen=self.stream_maxlen
                )

                # Pub/Sub for real-time delivery
                channel = f"{self.CHANNEL_PREFIX}{event_type_str}"
                self._redis.publish(channel, event_json)

                logger.debug(f"Published {event_type_str} -> {typed_key}")
                return str(event_id)
            except Exception as e:
                logger.error(f"Redis publish failed: {e}, using in-memory fallback")

        # In-memory fallback
        self._in_memory_events.append(event)
        self._in_memory_streams[event_type_str].append(event)
        self._dispatch_all(event, event_type_str)
        return str(event_id)

    def publish_batch(self, events: List[Union[PdMEvent, EventEnvelope]]) -> List[str]:
        """Publish multiple events. Returns list of IDs."""
        return [self.publish(e) for e in events]

    # -------------------------------------------------------------------------
    # Subscribe / Register (both patterns)
    # -------------------------------------------------------------------------

    def register_handler(self, handler: EventHandler):
        """PdM-style: register an EventHandler object."""
        for event_type in handler.handled_event_types:
            if event_type not in self._pdm_handlers:
                self._pdm_handlers[event_type] = []
            self._pdm_handlers[event_type].append(handler)

            if self._pubsub:
                channel = f"{self.CHANNEL_PREFIX}{event_type.value}"
                self._pubsub.subscribe(channel)

            if self._redis:
                self._ensure_consumer_group(self._typed_stream_key(event_type.value))

        logger.info(f"Registered PdM handler for: {handler.handled_event_types}")

    def subscribe(self, event_type: str, handler: EventCallback):
        """Loweconex-style: register a callable for an event type string."""
        self._handlers[event_type].append(handler)
        if self._redis:
            self._ensure_consumer_group(self._typed_stream_key(event_type))
        logger.debug(f"Subscribed callable to {event_type}")

    def subscribe_many(self, event_types: List[str], handler: EventCallback):
        """Register a callable for multiple event types."""
        for et in event_types:
            self.subscribe(et, handler)

    # -------------------------------------------------------------------------
    # Dispatch
    # -------------------------------------------------------------------------

    def _dispatch_all(self, event: Any, event_type_str: str):
        """Dispatch to both PdM handlers and Loweconex callbacks."""
        # PdM-style handlers
        if isinstance(event, PdMEvent):
            pdm_handlers = self._pdm_handlers.get(event.event_type, [])
            for handler in pdm_handlers:
                try:
                    response = handler.handle(event)
                    if response:
                        self.publish(response)
                except Exception as e:
                    logger.error(f"PdM handler error for {event.event_id}: {e}")
                    self._send_to_dlq(event_type_str, event.event_id, event.to_json(), str(e))

        # Loweconex-style callbacks
        callbacks = self._handlers.get(event_type_str, [])
        for callback in callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Callback error for {event_type_str}: {e}")
                retry_count = getattr(event, "retry_count", 0)
                max_retries = getattr(event, "max_retries", self.retry_max)
                if retry_count < max_retries:
                    event.retry_count = retry_count + 1
                    self.publish(event)
                else:
                    eid = getattr(event, "event_id", getattr(event, "msg_id", "unknown"))
                    ejson = event.to_json() if hasattr(event, "to_json") else str(event)
                    self._send_to_dlq(event_type_str, eid, ejson, str(e))

    def _send_to_dlq(self, event_type: str, msg_id: str, event_json: str, error: str):
        """Send a failed message to the dead-letter queue."""
        if self._redis:
            dlq_entry = {
                "original_stream": self._typed_stream_key(event_type),
                "original_msg_id": str(msg_id),
                "event": event_json,
                "error": error,
                "failed_ts": datetime.utcnow().isoformat(),
            }
            try:
                self._redis.xadd(self.DLQ_STREAM, dlq_entry, maxlen=10_000)
            except Exception as e:
                logger.error(f"Failed to write to DLQ: {e}")
        logger.warning(f"Message {msg_id} sent to DLQ: {error}")

    # -------------------------------------------------------------------------
    # Listen (background threads)
    # -------------------------------------------------------------------------

    def start_listening(self):
        """Start background threads to consume from Redis Streams."""
        if self._running:
            return
        self._running = True

        if self._redis:
            # Start listener for Pub/Sub (PdM-style real-time)
            if self._pubsub and self._pdm_handlers:
                t = threading.Thread(
                    target=self._pubsub_listen_loop, daemon=True, name="pubsub-listener"
                )
                t.start()
                self._listener_threads.append(t)

            # Start per-type stream listeners (Loweconex-style)
            for event_type in self._handlers:
                t = threading.Thread(
                    target=self._stream_listener,
                    args=(event_type,),
                    daemon=True,
                    name=f"listener-{event_type}",
                )
                t.start()
                self._listener_threads.append(t)

            logger.info(f"Started {len(self._listener_threads)} event listeners")
        else:
            logger.info("In-memory mode: handlers invoked synchronously on publish")

    def stop_listening(self):
        """Stop all listener threads."""
        self._running = False
        for t in self._listener_threads:
            t.join(timeout=5)
        self._listener_threads.clear()
        logger.info("Stopped all event listeners")

    def _pubsub_listen_loop(self):
        """Background: listen for PdM-style Pub/Sub messages."""
        while self._running:
            try:
                message = self._pubsub.get_message(timeout=1.0)
                if message and message["type"] == "message":
                    event = PdMEvent.from_json(message["data"])
                    event_type_str = event.event_type.value
                    self._dispatch_all(event, event_type_str)
            except Exception as e:
                logger.error(f"Pub/Sub listener error: {e}")
                time.sleep(1)

    def _stream_listener(self, event_type: str):
        """Background: read from a Redis Stream consumer group."""
        stream_key = self._typed_stream_key(event_type)
        self._ensure_consumer_group(stream_key)

        while self._running:
            try:
                messages = self._redis.xreadgroup(
                    groupname=self.consumer_group,
                    consumername=self.consumer_name,
                    streams={stream_key: ">"},
                    count=10,
                    block=2000,
                )
                if not messages:
                    continue

                for _, msg_list in messages:
                    for msg_id, msg_data in msg_list:
                        try:
                            event_json = msg_data.get("event", "{}")
                            # Try EventEnvelope first, then PdMEvent
                            try:
                                envelope = EventEnvelope.from_json(event_json)
                                self._dispatch_all(envelope, event_type)
                            except Exception:
                                pdm_event = PdMEvent.from_json(event_json)
                                self._dispatch_all(pdm_event, event_type)
                            self._redis.xack(stream_key, self.consumer_group, msg_id)
                        except Exception as e:
                            logger.error(f"Error processing {msg_id}: {e}")
                            self._send_to_dlq(event_type, str(msg_id), msg_data.get("event", ""), str(e))
            except Exception as e:
                logger.error(f"Stream listener error for {event_type}: {e}")
                time.sleep(1)

    # -------------------------------------------------------------------------
    # Query / Replay
    # -------------------------------------------------------------------------

    def get_events(
        self,
        event_types: Optional[List[PdMEventType]] = None,
        since: Optional[datetime] = None,
        limit: int = 100,
    ) -> List[PdMEvent]:
        """PdM-style: get events from in-memory store (or stream)."""
        events = [e for e in self._in_memory_events if isinstance(e, PdMEvent)]
        events = events[-limit:]
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        if since:
            events = [e for e in events if e.timestamp >= since]
        return events

    def get_stream_messages(
        self,
        event_type: str,
        count: int = 100,
        start: str = "-",
        end: str = "+",
    ) -> List[EventEnvelope]:
        """Loweconex-style: read messages from a typed stream."""
        stream_key = self._typed_stream_key(event_type)
        if self._redis:
            messages = self._redis.xrange(stream_key, min=start, max=end, count=count)
            results = []
            for m in messages:
                try:
                    results.append(EventEnvelope.from_json(m[1]["event"]))
                except Exception:
                    pass
            return results
        else:
            return [e for e in self._in_memory_streams.get(event_type, [])
                    if isinstance(e, EventEnvelope)][:count]

    def get_pending_count(self, event_type: str) -> int:
        if not self._redis:
            return 0
        try:
            info = self._redis.xpending(self._typed_stream_key(event_type), self.consumer_group)
            return info.get("pending", 0) if isinstance(info, dict) else 0
        except Exception:
            return 0

    def get_dlq_messages(self, count: int = 100) -> List[Dict[str, Any]]:
        if not self._redis:
            return []
        messages = self._redis.xrange(self.DLQ_STREAM, count=count)
        return [m[1] for m in messages]

    # -------------------------------------------------------------------------
    # Agent Registry
    # -------------------------------------------------------------------------

    def register_agent(self, agent_id: str, agent_info: Dict[str, Any]):
        if not self._redis:
            return
        agent_info["registered_at"] = datetime.utcnow().isoformat()
        agent_info["last_heartbeat"] = datetime.utcnow().isoformat()
        self._redis.hset(self.AGENT_REGISTRY_KEY, agent_id, json.dumps(agent_info))

    def get_registered_agents(self) -> Dict[str, Dict[str, Any]]:
        if not self._redis:
            return {}
        agents = self._redis.hgetall(self.AGENT_REGISTRY_KEY)
        return {k: json.loads(v) for k, v in agents.items()}

    def send_heartbeat(self):
        self.publish(PdMEvent(
            event_id=str(uuid.uuid4()),
            event_type=PdMEventType.AGENT_HEARTBEAT,
            source_agent=self.agent_id,
            timestamp=datetime.utcnow(),
            payload={"status": "alive"},
        ))

    def health_check(self) -> bool:
        """Check if Redis connection is healthy."""
        if not self._redis:
            return False
        try:
            return self._redis.ping()
        except Exception:
            return False

    # -------------------------------------------------------------------------
    # Loweconex convenience methods
    # -------------------------------------------------------------------------

    def emit_crew_started(self, crew_name: str, company_id: str, correlation_id: str):
        self.publish(EventEnvelope(
            event_type=EventType.CREW_STARTED.value,
            company_id=company_id,
            producer=crew_name,
            correlation_id=correlation_id,
            payload={"crew_name": crew_name, "started_ts": datetime.utcnow().isoformat()},
        ))

    def emit_crew_completed(self, crew_name: str, company_id: str, correlation_id: str, artifact_ids: Optional[List[str]] = None):
        self.publish(EventEnvelope(
            event_type=EventType.CREW_COMPLETED.value,
            company_id=company_id,
            producer=crew_name,
            correlation_id=correlation_id,
            artifact_ids=artifact_ids or [],
            payload={"crew_name": crew_name, "completed_ts": datetime.utcnow().isoformat()},
        ))

    def emit_kpi_computed(
        self, kpi_name: str, company_id: str, correlation_id: str,
        payload: Dict[str, Any], location_id: Optional[str] = None,
    ):
        self.publish(EventEnvelope(
            event_type=EventType.KPI_COMPUTED.value,
            company_id=company_id,
            location_id=location_id,
            producer=f"kpi_crew_{kpi_name}",
            kpi_name=kpi_name,
            correlation_id=correlation_id,
            payload=payload,
        ))


# =============================================================================
# In-Memory Event Bus (for testing/dev)
# =============================================================================

class InMemoryEventBus(RedisEventBus):
    """Simplified in-memory event bus for testing without Redis."""

    def __init__(self, agent_id: str = "test"):
        self.agent_id = agent_id
        self.use_streams = False
        self.consumer_group = "test"
        self.consumer_name = f"test_consumer_{agent_id}"
        self.stream_maxlen = 10_000
        self.retry_max = 3
        self.retry_backoff_ms = 100

        self._pdm_handlers: Dict[PdMEventType, List[EventHandler]] = {}
        self._handlers: Dict[str, List[EventCallback]] = defaultdict(list)
        self._running = False
        self._listener_threads: List[threading.Thread] = []
        self._redis = None
        self._pubsub = None
        self._in_memory_events: List[Any] = []
        self._in_memory_streams: Dict[str, List[Any]] = defaultdict(list)

    def publish(self, event: Union[PdMEvent, EventEnvelope]) -> str:
        if isinstance(event, PdMEvent):
            event_type_str = event.event_type.value
            event_id = event.event_id
        elif isinstance(event, EventEnvelope):
            event_type_str = event.event_type
            event_id = event.msg_id
        else:
            event_type_str = str(getattr(event, "event_type", "unknown"))
            event_id = str(getattr(event, "event_id", getattr(event, "msg_id", uuid.uuid4())))

        self._in_memory_events.append(event)
        self._in_memory_streams[event_type_str].append(event)
        self._dispatch_all(event, event_type_str)
        return str(event_id)

    def get_all_events(self) -> List[Any]:
        return list(self._in_memory_events)

    def clear(self):
        self._in_memory_events.clear()
        self._in_memory_streams.clear()

    def start_listening(self):
        self._running = True

    def stop_listening(self):
        self._running = False
