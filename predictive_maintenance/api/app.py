"""
PDM FastAPI Application

Main application factory and configuration.
"""

import logging
import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler with comprehensive startup validation."""
    settings = getattr(app.state, "settings", None)
    if settings is None:
        try:
            from ..config import get_settings
            get_settings.cache_clear()
            settings = get_settings()
        except Exception:
            settings = None

    # Startup
    logger.info("PDM API starting up...")
    startup_checks = {}
    
    # 1. Validate configuration
    try:
        assert settings.database.url, "Database URL not configured"
        startup_checks["config"] = True
        logger.info("Configuration validated (env=%s)", settings.environment)
    except Exception as e:
        startup_checks["config"] = False
        logger.error(f"Configuration validation failed: {e}")
    
    # 2. Initialize database
    try:
        from ..persistence.database import init_db, health_check
        init_db()
        if health_check():
            startup_checks["database"] = True
            logger.info("Database connection verified")
        else:
            startup_checks["database"] = False
            logger.warning("Database health check failed")
    except Exception as e:
        startup_checks["database"] = False
        logger.warning(f"Database initialization skipped: {e}")
    
    # 3. Initialize Redis event bus
    try:
        from ..integration.event_bus import RedisEventBus
        bus = RedisEventBus(redis_url=settings.redis.url)
        startup_checks["redis"] = True
        logger.info("Event bus ready")
    except Exception as e:
        startup_checks["redis"] = False
        logger.warning(f"Event bus initialization skipped: {e}")
    
    # 4. Verify service registry loads
    try:
        from ..core.service_registry import get_registry
        registry = get_registry()
        startup_checks["service_registry"] = True
        logger.info("Service registry initialized")
    except Exception as e:
        startup_checks["service_registry"] = False
        logger.warning(f"Service registry init failed: {e}")
    
    # 5. Initialize circuit breakers
    try:
        from ..core.circuit_breaker import get_breaker, CircuitBreakerConfig
        get_breaker("database", CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=15))
        get_breaker("redis", CircuitBreakerConfig(failure_threshold=5, recovery_timeout_seconds=10))
        get_breaker("llm", CircuitBreakerConfig(failure_threshold=3, recovery_timeout_seconds=60))
        startup_checks["circuit_breakers"] = True
        logger.info("Circuit breakers initialized")
    except Exception as e:
        startup_checks["circuit_breakers"] = False
        logger.warning(f"Circuit breaker init failed: {e}")
    
    # 6. Setup tracing
    try:
        from ..observability.tracing import setup_tracing
        setup_tracing(
            service_name="pdm",
            jaeger_host=settings.metrics.jaeger_host,
            jaeger_port=settings.metrics.jaeger_port,
            enabled=settings.metrics.tracing_enabled,
        )
        startup_checks["tracing"] = True
    except Exception as e:
        startup_checks["tracing"] = False
        logger.warning(f"Tracing setup skipped: {e}")
    
    # 7. Start Prometheus metrics server
    try:
        if settings.metrics.enabled:
            from ..observability.metrics import metrics
            metrics.start_server(port=settings.metrics.port)
            startup_checks["metrics"] = True
    except Exception as e:
        startup_checks["metrics"] = False
        logger.warning(f"Metrics server skipped: {e}")
    
    # Report startup summary
    passed = sum(1 for v in startup_checks.values() if v)
    total = len(startup_checks)
    logger.info(
        "Startup validation: %d/%d checks passed %s",
        passed, total, startup_checks,
    )
    
    # Store checks for health endpoint
    app.state.startup_checks = startup_checks
    
    yield
    
    # Shutdown
    logger.info("PDM API shutting down...")


def create_app(
    title: str = "PDM API",
    version: str = "1.0.0",
    debug: bool = False,
) -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Args:
        title: API title
        version: API version
        debug: Enable debug mode
    
    Returns:
        Configured FastAPI application
    """
    openapi_tags = [
        {"name": "Health", "description": "Liveness and readiness probes"},
        {"name": "Telemetry", "description": "Real-time and historical sensor telemetry ingestion"},
        {"name": "Alerts", "description": "Alert management — create, acknowledge, resolve"},
        {"name": "Assets", "description": "Asset registry CRUD and fleet inventory"},
        {"name": "Feedback", "description": "Operator feedback on alerts and recommendations"},
        {"name": "Metrics", "description": "Prometheus-compatible system and model metrics"},
        {"name": "Query", "description": "Ad-hoc data queries across telemetry and alerts"},
        {"name": "Scenario", "description": "Scenario creation, comparison, and what-if analysis"},
        {"name": "Autopilot", "description": "Operations autopilot — incidents, runs, playbooks"},
        {"name": "LLM Studio", "description": "LLM workflow capture, annotations, and training data"},
        {"name": "Approval Queue", "description": "Human-in-the-loop approval workflow"},
        {"name": "Approval Queue - Review", "description": "Review and approve/reject queued actions"},
        {"name": "WebSocket", "description": "Real-time WebSocket streams for dashboards"},
        {"name": "Advanced Services", "description": "Phase 3-4 capabilities — RAG, digital twins, model lifecycle"},
        {"name": "KPI Dashboard", "description": "14-KPI computation dashboard with savings estimates"},
        {"name": "Fleet Overview", "description": "Fleet-wide asset health, metrics, and status"},
        {"name": "Data Upload", "description": "CSV/Excel telemetry upload and normalization"},
        {"name": "Maintenance Scenarios", "description": "Maintenance scenario simulation and comparison"},
        {"name": "Data Mapping", "description": "Schema mapping configuration for data normalization"},
        {"name": "Orchestration Visibility", "description": "Pipeline status, agent health, and decision trails"},
        {"name": "Loweconex Platform", "description": "CrewAI-powered 14-crew KPI pipeline and orchestration"},
        {"name": "Ingestion", "description": "Data connectors (CSV, API, SFTP, S3, DB) and streaming ingest"},
        {"name": "Scenario Advisor", "description": "Conversational AI advisor for scenario optimization"},
        {"name": "ROI Export", "description": "ROI workbook and report export"},
        {"name": "Ownership Decision Support", "description": "Ownership-aware cost stack, metric catalog, consolidated ROI, and decision support"},
    ]

    app = FastAPI(
        title=title,
        description="Predictive Maintenance API for HVAC/R Equipment",
        version=version,
        debug=debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        openapi_tags=openapi_tags,
    )

    app_settings = None
    try:
        from ..config import get_settings
        get_settings.cache_clear()
        app_settings = get_settings()
    except Exception as exc:
        logger.warning("Settings load failed during app creation: %s", exc)
    app.state.settings = app_settings
    
    # Configure CORS
    try:
        cors_origins = app_settings.api.cors_origins if app_settings else ["*"]
    except Exception:
        cors_origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add observability middleware
    from ..observability.logging import LoggingMiddleware
    from ..observability.tracing import TracingMiddleware
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TracingMiddleware)
    
    # Add API key authentication middleware
    _auth_strict = os.getenv("PDM_ENVIRONMENT", "development").lower() == "production"
    try:
        from .auth import APIKeyMiddleware
        _auth_cfg = app_settings
        _auth_strict = bool(getattr(_auth_cfg, "is_production", _auth_strict))
        env_api_keys = [
            key.strip()
            for key in os.getenv("PDM_API_KEYS", "").split(",")
            if key.strip()
        ]
        api_keys = env_api_keys or list(getattr(getattr(_auth_cfg, "api", None), "api_keys", []) or [])
        header_name = (
            os.getenv("PDM_API_KEY_HEADER")
            or getattr(getattr(_auth_cfg, "api", None), "api_key_header", "X-API-Key")
            or "X-API-Key"
        )
        if _auth_strict and not api_keys:
            raise RuntimeError(
                "PDM_API_KEYS is required in production; refusing to start with auth disabled."
            )
        app.add_middleware(
            APIKeyMiddleware,
            api_keys=api_keys,
            header_name=header_name,
        )
    except Exception as e:
        if _auth_strict:
            logger.error("FATAL: API key auth middleware initialization failed in production: %s", e)
            raise RuntimeError(
                f"Auth middleware initialization failed in production: {e}"
            ) from e
        logger.warning(f"API key auth middleware not available: {e}")

    # Add rate limiting middleware
    try:
        from .rate_limiter import RateLimiterMiddleware
        _cfg = app_settings
        app.add_middleware(
            RateLimiterMiddleware,
            max_requests=_cfg.api.rate_limit_requests,
            window_seconds=_cfg.api.rate_limit_window_seconds,
        )
    except Exception as e:
        logger.warning(f"Rate limiter not available: {e}")
    
    # Add exception handlers
    from ..core.exceptions import PDMError

    @app.exception_handler(PDMError)
    async def pdm_error_handler(request: Request, exc: PDMError):
        logger.warning(
            f"Domain error: {exc.error_code} – {exc}",
            extra={"error_code": exc.error_code, "context": exc.context},
        )
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"error_code": "PDM_INTERNAL", "message": "Internal server error", "context": {"type": type(exc).__name__}}
        )
    
    # ── Route registration ───────────────────────────────────────────
    # In production, route import failures are FATAL (no silent degradation).
    # In development/test, they are logged as warnings for convenience.
    _strict = bool(getattr(app_settings, "is_production", False))

    _failed_routers: list = []

    def _try_register(label: str, register_fn):
        """Register a group of routers; re-raise in production."""
        try:
            register_fn()
            logger.info("%s routes registered", label)
        except Exception as e:
            if _strict:
                logger.error("FATAL: %s route registration failed in production: %s", label, e)
                raise RuntimeError(
                    f"{label} route registration failed in production — "
                    f"fix the import or set PDM_ENVIRONMENT=development to degrade gracefully: {e}"
                ) from e
            _failed_routers.append(label)
            logger.warning(f"{label} routes not available: {e}")

    # Core routers (always required — fail even in dev)
    from .routes import (
        health_router,
        telemetry_router,
        alerts_router,
        assets_router,
        feedback_router,
        metrics_router,
        query_router,
        scenario_router,
    )
    
    app.include_router(health_router, tags=["Health"])
    app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["Telemetry"])
    app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["Alerts"])
    app.include_router(assets_router, prefix="/api/v1/assets", tags=["Assets"])
    app.include_router(feedback_router, prefix="/api/v1/feedback", tags=["Feedback"])
    app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["Metrics"])
    app.include_router(query_router, prefix="/api/v1/query", tags=["Query"])
    app.include_router(scenario_router, prefix="/api/v1/scenario", tags=["Scenario"])
    
    # Autopilot routers
    def _reg_autopilot():
        from ..autopilot.routes import (
            incidents_router,
            runs_router,
            approvals_router,
            playbooks_router,
        )
        app.include_router(incidents_router, prefix="/api/v1/incidents", tags=["Autopilot - Incidents"])
        app.include_router(runs_router, prefix="/api/v1/runs", tags=["Autopilot - Runs"])
        app.include_router(approvals_router, prefix="/api/v1/approvals", tags=["Autopilot - Approvals"])
        app.include_router(playbooks_router, prefix="/api/v1/playbooks", tags=["Autopilot - Playbooks"])
    _try_register("Autopilot", _reg_autopilot)
    
    # LLM Studio routers (workflow capture & training data)
    def _reg_llm_studio():
        from ..llm_studio.routes import (
            traces_router,
            decisions_router,
            annotations_router,
            export_router,
            stats_router,
        )
        app.include_router(traces_router, prefix="/api/v1/llm-studio/traces", tags=["LLM Studio - Traces"])
        app.include_router(decisions_router, prefix="/api/v1/llm-studio/decisions", tags=["LLM Studio - Decisions"])
        app.include_router(annotations_router, prefix="/api/v1/llm-studio/annotations", tags=["LLM Studio - Annotations"])
        app.include_router(export_router, prefix="/api/v1/llm-studio/export", tags=["LLM Studio - Export"])
        app.include_router(stats_router, prefix="/api/v1/llm-studio/stats", tags=["LLM Studio - Stats"])
    _try_register("LLM Studio", _reg_llm_studio)
    
    # Approval Queue routers (human-in-the-loop with LLM explanations)
    def _reg_approval_queue():
        from ..autopilot.approval_queue.routes import (
            queue_router,
            review_router,
        )
        app.include_router(queue_router, prefix="/api/v1/approval-queue", tags=["Approval Queue"])
        app.include_router(review_router, prefix="/api/v1/approval-queue/review", tags=["Approval Queue - Review"])
    _try_register("Approval Queue", _reg_approval_queue)
    
    # WebSocket routers (real-time streaming)
    def _reg_websocket():
        from .websocket import router as websocket_router
        app.include_router(websocket_router, prefix="/api/v1", tags=["WebSocket"])
    _try_register("WebSocket", _reg_websocket)
    
    # Advanced Services routers (Phase 3-4 capabilities)
    def _reg_advanced():
        from .routes.advanced_services import router as advanced_router
        app.include_router(advanced_router, prefix="/api/v1/advanced", tags=["Advanced Services"])
    _try_register("Advanced Services", _reg_advanced)
    
    # KPI Dashboard, Fleet Overview, Data Upload, Maintenance Scenarios
    def _reg_kpi_fleet():
        from .routes.kpi_fleet_routes import (
            kpi_router,
            fleet_router,
            upload_router,
            scenario_maint_router,
        )
        app.include_router(kpi_router, prefix="/api/v1/kpi", tags=["KPI Dashboard"])
        app.include_router(fleet_router, prefix="/api/v1/fleet", tags=["Fleet Overview"])
        app.include_router(upload_router, prefix="/api/v1/upload", tags=["Data Upload"])
        app.include_router(scenario_maint_router, prefix="/api/v1/scenarios/maintenance", tags=["Maintenance Scenarios"])
    _try_register("KPI/Fleet/Upload", _reg_kpi_fleet)

    # Budget Management
    def _reg_budget():
        from .routes.budget_routes import budget_router
        app.include_router(budget_router, prefix="/api/v1/budget", tags=["Budget Management"])
    _try_register("Budget Management", _reg_budget)

    # Business Case Generation
    def _reg_business_case():
        from .routes.business_case_routes import business_case_router
        app.include_router(business_case_router, prefix="/api/v1/business-case", tags=["Business Case"])
    _try_register("Business Case", _reg_business_case)

    # Decision Matrix
    def _reg_decision_matrix():
        from .routes.decision_matrix_routes import decision_matrix_router
        app.include_router(decision_matrix_router, prefix="/api/v1/decision-matrix", tags=["Decision Matrix"])
    _try_register("Decision Matrix", _reg_decision_matrix)

    # CapEx Platform Data
    def _reg_capex_data():
        from .routes.capex_routes import capex_data_router
        app.include_router(capex_data_router, prefix="/api/v1/capex", tags=["CapEx Platform Data"])
    _try_register("CapEx Platform Data", _reg_capex_data)
    
    # Data Mapping Configuration
    def _reg_data_mapping():
        from .routes.data_mapping_routes import mapping_router
        app.include_router(mapping_router, prefix="/api/v1/mappings", tags=["Data Mapping"])
    _try_register("Data Mapping", _reg_data_mapping)
    
    # Orchestration Visibility
    def _reg_orchestration():
        from .routes.orchestration_routes import orchestration_router
        app.include_router(orchestration_router, prefix="/api/v1/orchestration", tags=["Orchestration Visibility"])
    _try_register("Orchestration Visibility", _reg_orchestration)
    
    # Loweconex Platform (CrewAI pipeline)
    def _reg_loweconex():
        from .routes.loweconex_routes import loweconex_router
        app.include_router(loweconex_router, prefix="/api/v1/loweconex", tags=["Loweconex Platform"])
    _try_register("Loweconex Platform", _reg_loweconex)

    # Ingestion connectors & streaming
    def _reg_ingestion():
        from .routes.ingestion_routes import ingestion_router
        app.include_router(ingestion_router, prefix="/api/v1/ingestion", tags=["Ingestion"])
    _try_register("Ingestion", _reg_ingestion)

    # Scenario Advisor (conversational interface)
    def _reg_advisor():
        from .routes.advisor_routes import advisor_router
        app.include_router(advisor_router, prefix="/api/advisor", tags=["Scenario Advisor"])
    _try_register("Scenario Advisor", _reg_advisor)

    # ROI Workbook Export
    def _reg_roi_export():
        from .routes.export_routes import export_router as roi_export_router
        app.include_router(roi_export_router, prefix="/api/v1/export", tags=["ROI Export"])
    _try_register("ROI Export", _reg_roi_export)

    # AI Work Order Management (LLM-powered)
    def _reg_workorders():
        from .routes.workorder_routes import workorder_router
        app.include_router(workorder_router, prefix="/api/v1/workorders", tags=["Work Orders"])
    _try_register("Work Orders", _reg_workorders)

    # Governance & Compliance API (gap #26 — expose all 12 governance modules)
    def _reg_governance():
        from .routes.governance_api_routes import governance_api_router
        app.include_router(governance_api_router, prefix="/api/v1/governance", tags=["Governance"])
    _try_register("Governance", _reg_governance)

    # Auth validation endpoint for frontend login (gap #12 frontend auth)
    def _reg_auth():
        from .routes.auth_routes import auth_router
        app.include_router(auth_router, prefix="/api/v1/auth", tags=["Auth"])
    _try_register("Auth", _reg_auth)

    # Ownership Decision Support (cost stack, ownership mapping, consolidated ROI)
    def _reg_ownership():
        from .routes.ownership_routes import ownership_router
        app.include_router(ownership_router, prefix="/api/v1/ownership", tags=["Ownership Decision Support"])
    _try_register("Ownership Decision Support", _reg_ownership)

    if _failed_routers:
        logger.warning(
            "Route registration: %d groups failed (dev mode): %s",
            len(_failed_routers), ", ".join(_failed_routers),
        )
    
    return app


# Default application instance
app = create_app()
