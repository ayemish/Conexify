"""
API Key Authentication Middleware

Validates requests against configured API keys from PDM_API_KEYS env var.
Unauthenticated routes (health, docs, openapi) are exempt.
When no API keys are configured, all requests are allowed (dev mode).
"""

import logging
from typing import List, Optional, Set

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)

# Routes that never require authentication
EXEMPT_PATHS: Set[str] = {
    "/",
    "/health",
    "/healthz",
    "/ready",
    "/docs",
    "/redoc",
    "/openapi.json",
}

# Path prefixes that never require authentication
EXEMPT_PREFIXES = (
    "/docs",
    "/redoc",
)


class APIKeyMiddleware(BaseHTTPMiddleware):
    """Middleware that enforces API key authentication.

    Configuration is read from ``settings.api.api_keys`` (comma-separated
    env var ``PDM_API_KEYS``).  When the list is empty, authentication is
    disabled so the system works out-of-the-box in development.

    Valid API keys can be supplied via:
    - Header: ``X-API-Key: <key>`` (header name configurable)
    - Query parameter: ``?api_key=<key>``
    """

    def __init__(self, app: ASGIApp, api_keys: Optional[List[str]] = None, header_name: str = "X-API-Key"):
        super().__init__(app)
        self.api_keys: Set[str] = set(api_keys or [])
        self.header_name = header_name
        self.enabled = bool(self.api_keys)
        if self.enabled:
            logger.info("API key authentication enabled (%d keys configured)", len(self.api_keys))
        else:
            logger.info("API key authentication disabled (no keys configured)")

    async def dispatch(self, request: Request, call_next):
        # Skip auth when disabled
        if not self.enabled:
            return await call_next(request)

        # Skip exempt paths
        path = request.url.path
        if path in EXEMPT_PATHS or path.startswith(EXEMPT_PREFIXES):
            return await call_next(request)

        # Skip OPTIONS (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)

        # Extract API key from header or query param
        api_key = request.headers.get(self.header_name)
        if not api_key:
            api_key = request.query_params.get("api_key")

        if not api_key:
            return JSONResponse(
                status_code=401,
                content={
                    "error_code": "AUTH_MISSING_KEY",
                    "message": f"API key required. Provide via '{self.header_name}' header or 'api_key' query parameter.",
                },
            )

        if api_key not in self.api_keys:
            logger.warning("Invalid API key attempt from %s", request.client.host if request.client else "unknown")
            return JSONResponse(
                status_code=403,
                content={
                    "error_code": "AUTH_INVALID_KEY",
                    "message": "Invalid API key.",
                },
            )

        return await call_next(request)
