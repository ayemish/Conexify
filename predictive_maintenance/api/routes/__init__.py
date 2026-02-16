"""API route sub-modules.

Re-exports all routers from the legacy routes.py so that
``from .routes import health_router, ...`` continues to work
after this package was created.
"""

# The legacy routes module was renamed to _routes_legacy to avoid
# shadowing.  We import everything it exposes.
from ._routes_legacy import (  # noqa: F401
    health_router,
    telemetry_router,
    alerts_router,
    assets_router,
    feedback_router,
    metrics_router,
    query_router,
    scenario_router as legacy_scenario_router,
    # Shared state used by kpi_fleet_routes
    _pdm_systems,
    _orchestrators,
    get_pdm_system,
    get_orchestrator,
)

# Domain-aligned scenario routes (HVAC/R decision support).
from .scenario_routes import scenario_router  # noqa: F401
