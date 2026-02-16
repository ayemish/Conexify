"""
Redis Event Bus for inter-crew coordination, progress, and artifact routing.

Uses Redis Streams (preferred) for durability and consumer groups;
Pub/Sub for transient progress updates.
"""

from loweconex_platform.event_bus.events import (
    EventType,
    EventEnvelope,
    create_envelope,
)
from loweconex_platform.event_bus.redis_streams import (
    LoweconexEventBus,
    InMemoryEventBus,
)

__all__ = [
    "EventType",
    "EventEnvelope",
    "create_envelope",
    "LoweconexEventBus",
    "InMemoryEventBus",
]
