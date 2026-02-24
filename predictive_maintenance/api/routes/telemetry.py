"""Telemetry route module."""

from ._routes_legacy import telemetry_router, get_pdm_system, get_orchestrator
from .lifecycle_manager import get_runtime_lifecycle_manager

__all__ = [
    "telemetry_router",
    "get_pdm_system",
    "get_orchestrator",
    "get_runtime_lifecycle_manager",
]
