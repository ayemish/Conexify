"""API route exports by bounded module."""

from .health import health_router  # noqa: F401
from .telemetry import telemetry_router, get_pdm_system, get_orchestrator  # noqa: F401
from .alerts import alerts_router  # noqa: F401
from .assets import assets_router  # noqa: F401
from .feedback import feedback_router  # noqa: F401
from .metrics import metrics_router  # noqa: F401
from .query import query_router  # noqa: F401
from ._routes_legacy import scenario_router as legacy_scenario_router  # noqa: F401
from .scenario_routes import scenario_router  # noqa: F401
from .lifecycle_manager import get_runtime_lifecycle_manager  # noqa: F401

_lifecycle_manager = get_runtime_lifecycle_manager()
_pdm_systems = _lifecycle_manager.pdm_systems
_orchestrators = _lifecycle_manager.orchestrators

__all__ = [
    "health_router",
    "telemetry_router",
    "alerts_router",
    "assets_router",
    "feedback_router",
    "metrics_router",
    "query_router",
    "scenario_router",
    "legacy_scenario_router",
    "_pdm_systems",
    "_orchestrators",
    "get_pdm_system",
    "get_orchestrator",
    "get_runtime_lifecycle_manager",
]
