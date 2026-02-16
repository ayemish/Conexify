"""
Redis Event Bus — re-exports from shared canonical implementation.

ALL event bus classes, event types, and factories are defined in shared/event_bus/.
This file re-exports everything for backward compatibility.
"""

# Re-export everything from the single canonical implementation
from shared.event_bus import (
    RedisEventBus,
    InMemoryEventBus,
    PdMEventType,
    PdMEvent,
    EventHandler,
    PdMEventFactory,
    REDIS_AVAILABLE,
)

# Backward-compatible aliases
PDMEventType = PdMEventType
PDMEvent = PdMEvent
PDMEventBus = RedisEventBus
