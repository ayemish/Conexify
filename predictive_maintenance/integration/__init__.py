"""
PDM Integration Module

Integration layer connecting all PDM components:
- Advanced PDM system orchestration
- Model lifecycle management (registry, A/B testing, retraining)
- Event-driven communication
"""

from .advanced_system import HVACRPdMAdvancedSystem
from .lifecycle import (
    ModelType,
    ModelStage,
    ModelVersion,
    PerformanceMetrics,
)
from .event_bus import RedisEventBus as PDMEventBus, PdMEvent as PDMEvent, PdMEventType as PDMEventType

__all__ = [
    # Advanced System
    "HVACRPdMAdvancedSystem",
    
    # Lifecycle
    "ModelType",
    "ModelStage",
    "ModelVersion",
    "PerformanceMetrics",
    
    # Event Bus
    "PDMEventBus",
    "PDMEvent",
    "PDMEventType",
]
