"""
PDM FastAPI Application

Main application factory and configuration.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("PDM API starting up...")
    
    # Initialize database
    try:
        from ..persistence.database import init_db, health_check
        init_db()
        if health_check():
            logger.info("Database connection verified")
        else:
            logger.warning("Database health check failed")
    except Exception as e:
        logger.warning(f"Database initialization skipped: {e}")
    
    # Initialize Redis event bus
    try:
        from ..integration.event_bus import RedisEventBus
        # Event bus will be initialized on first use
        logger.info("Event bus ready")
    except Exception as e:
        logger.warning(f"Event bus initialization skipped: {e}")
    
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
    app = FastAPI(
        title=title,
        description="Predictive Maintenance API for HVAC/R Equipment",
        version=version,
        debug=debug,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    
    # Configure CORS
    try:
        from ..config import settings
        cors_origins = settings.api.cors_origins
    except Exception:
        cors_origins = ["*"]
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Add exception handlers
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={"detail": "Internal server error", "type": type(exc).__name__}
        )
    
    # Include routers
    from .routes import (
        health_router,
        telemetry_router,
        alerts_router,
        assets_router,
        feedback_router,
        metrics_router,
    )
    
    app.include_router(health_router, tags=["Health"])
    app.include_router(telemetry_router, prefix="/api/v1/telemetry", tags=["Telemetry"])
    app.include_router(alerts_router, prefix="/api/v1/alerts", tags=["Alerts"])
    app.include_router(assets_router, prefix="/api/v1/assets", tags=["Assets"])
    app.include_router(feedback_router, prefix="/api/v1/feedback", tags=["Feedback"])
    app.include_router(metrics_router, prefix="/api/v1/metrics", tags=["Metrics"])
    
    return app


# Default application instance
app = create_app()
