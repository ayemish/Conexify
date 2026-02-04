"""
PDM API Layer

FastAPI-based REST API for the Predictive Maintenance system.
"""

from .app import create_app, app
from .schemas import (
    TelemetryRequest,
    TelemetryResponse,
    AlertResponse,
    AssetResponse,
    FeedbackRequest,
    HealthResponse,
)

__all__ = [
    "create_app",
    "app",
    "TelemetryRequest",
    "TelemetryResponse",
    "AlertResponse",
    "AssetResponse",
    "FeedbackRequest",
    "HealthResponse",
]
