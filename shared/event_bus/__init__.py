"""
Unified Event Bus — the single canonical event bus for the entire platform.

Provides:
- RedisEventBus: Redis Streams + Pub/Sub with consumer groups, DLQ, retry
- InMemoryEventBus: In-memory fallback for testing/dev
- PdMEvent / PdMEventType: Envelope and event types for PdM agents
- EventEnvelope / EventType: Envelope and event types for Loweconex KPI crews
- EventHandler: Abstract handler base class
- PdMEventFactory: Typed event factory for PdM domain

All event bus consumers across oil_gas, predictive_maintenance, and
loweconex_platform MUST import from this package.
"""

from shared.event_bus.events import (
    PdMEventType,
    PdMEvent,
    EventHandler,
    PdMEventFactory,
    EventType,
    EventEnvelope,
    create_envelope,
)
from shared.event_bus.redis_event_bus import (
    RedisEventBus,
    InMemoryEventBus,
    REDIS_AVAILABLE,
)

# Backward-compatible aliases
PDMEventType = PdMEventType
PDMEvent = PdMEvent
PDMEventBus = RedisEventBus
LoweconexEventBus = RedisEventBus

__all__ = [
    # Event bus transport
    "RedisEventBus",
    "InMemoryEventBus",
    "REDIS_AVAILABLE",
    # PdM envelope & types
    "PdMEventType",
    "PdMEvent",
    "EventHandler",
    "PdMEventFactory",
    # Loweconex envelope & types
    "EventType",
    "EventEnvelope",
    "create_envelope",
    # Backward-compatible aliases
    "PDMEventType",
    "PDMEvent",
    "PDMEventBus",
    "LoweconexEventBus",
]
