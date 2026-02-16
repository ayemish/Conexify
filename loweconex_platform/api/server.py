"""
API Server — FastAPI application with tenant-isolated auth middleware,
SSE progress streaming, backpressure monitoring, and report access.

Provides:
- /api/v1/reports/* — tenant-scoped report access with RBAC
- /api/v1/progress/stream — SSE endpoint for pipeline progress
- /api/v1/health — backpressure and consumer lag metrics
- Auth middleware enforcing company_id tenant boundary
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# =============================================================================
# Tenant Context
# =============================================================================

@dataclass
class TenantContext:
    """Request-scoped tenant context extracted from auth token."""
    user_id: str = ""
    company_id: str = ""
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    authenticated: bool = False

    def has_permission(self, permission: str) -> bool:
        return permission in self.permissions or "admin" in self.roles

    def can_access_company(self, target_company_id: str) -> bool:
        """Hard tenant isolation: user can only access their own company."""
        return self.company_id == target_company_id


# =============================================================================
# Auth Middleware
# =============================================================================

class AuthMiddleware:
    """
    Authentication and authorization middleware.
    
    Extracts tenant context from Authorization header (Bearer token),
    enforces hard tenant isolation on all endpoints.
    
    For production: integrate with OAuth2/OIDC provider.
    For dev/testing: supports a simple token→context mapping.
    """

    def __init__(self):
        self._token_map: Dict[str, TenantContext] = {}
        self._audit_log: List[Dict[str, Any]] = []

    def register_token(self, token: str, context: TenantContext):
        """Register a token→context mapping (dev/testing)."""
        self._token_map[token] = context

    def authenticate(self, authorization_header: Optional[str]) -> TenantContext:
        """
        Authenticate a request from its Authorization header.
        Returns TenantContext (authenticated=False if invalid).
        """
        if not authorization_header:
            self._log_audit("", "auth_failed", "No authorization header")
            return TenantContext()

        parts = authorization_header.split(" ", 1)
        if len(parts) != 2 or parts[0].lower() != "bearer":
            self._log_audit("", "auth_failed", "Invalid authorization format")
            return TenantContext()

        token = parts[1]
        ctx = self._token_map.get(token)
        if not ctx:
            self._log_audit("", "auth_failed", "Unknown token")
            return TenantContext()

        self._log_audit(ctx.user_id, "authenticated", ctx.company_id)
        return ctx

    def authorize_company_access(
        self, ctx: TenantContext, target_company_id: str
    ) -> bool:
        """Check if the authenticated user can access the target company."""
        if not ctx.authenticated:
            self._log_audit(ctx.user_id, "access_denied", "Not authenticated")
            return False
        if not ctx.can_access_company(target_company_id):
            self._log_audit(
                ctx.user_id, "tenant_violation",
                f"User company={ctx.company_id} tried to access company={target_company_id}"
            )
            return False
        return True

    def authorize_permission(
        self, ctx: TenantContext, permission: str
    ) -> bool:
        """Check if the authenticated user has a specific permission."""
        if not ctx.has_permission(permission):
            self._log_audit(ctx.user_id, "permission_denied", permission)
            return False
        return True

    def _log_audit(self, user_id: str, action: str, details: str):
        self._audit_log.append({
            "user_id": user_id,
            "action": action,
            "details": details,
            "ts": datetime.utcnow().isoformat(),
        })

    def get_audit_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._audit_log[-limit:]


# =============================================================================
# SSE Progress Manager
# =============================================================================

class ProgressManager:
    """
    Manages Server-Sent Events (SSE) for pipeline progress streaming.
    
    Crews and orchestrator push progress events; SSE clients receive them
    in real-time filtered by company_id.
    """

    def __init__(self):
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}
        self._history: List[Dict[str, Any]] = []

    def push_progress(
        self,
        company_id: str,
        crew_name: str,
        status: str,
        progress_pct: float = 0.0,
        message: str = "",
        run_id: str = "",
    ):
        """Push a progress event to all subscribers for a company."""
        event = {
            "event_id": str(uuid.uuid4()),
            "company_id": company_id,
            "crew_name": crew_name,
            "status": status,
            "progress_pct": progress_pct,
            "message": message,
            "run_id": run_id,
            "ts": datetime.utcnow().isoformat(),
        }
        self._history.append(event)

        queues = self._subscribers.get(company_id, [])
        for queue in queues:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(f"SSE queue full for company {company_id}")

    def subscribe(self, company_id: str) -> asyncio.Queue:
        """Create a subscription queue for SSE streaming."""
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        if company_id not in self._subscribers:
            self._subscribers[company_id] = []
        self._subscribers[company_id].append(queue)
        return queue

    def unsubscribe(self, company_id: str, queue: asyncio.Queue):
        """Remove a subscription queue."""
        queues = self._subscribers.get(company_id, [])
        if queue in queues:
            queues.remove(queue)

    async def stream_events(self, company_id: str) -> AsyncGenerator[str, None]:
        """Async generator yielding SSE-formatted progress events."""
        queue = self.subscribe(company_id)
        try:
            while True:
                event = await asyncio.wait_for(queue.get(), timeout=30.0)
                yield f"data: {json.dumps(event)}\n\n"
        except asyncio.TimeoutError:
            yield f"data: {json.dumps({'type': 'keepalive', 'ts': datetime.utcnow().isoformat()})}\n\n"
        except GeneratorExit:
            pass
        finally:
            self.unsubscribe(company_id, queue)

    def get_recent_progress(self, company_id: str, limit: int = 20) -> List[Dict[str, Any]]:
        return [e for e in self._history[-200:] if e["company_id"] == company_id][-limit:]


# =============================================================================
# Backpressure Monitor
# =============================================================================

class BackpressureMonitor:
    """
    Monitors consumer lag, queue depth, and system health metrics.
    
    Provides:
    - Consumer lag tracking per stream/consumer group
    - Dynamic concurrency throttling signals
    - Health check endpoint data
    """

    def __init__(self, max_lag_threshold: int = 10000, max_concurrency: int = 10):
        self.max_lag_threshold = max_lag_threshold
        self.max_concurrency = max_concurrency
        self._current_concurrency = 0
        self._lag_metrics: Dict[str, int] = {}
        self._throughput_log: List[Dict[str, Any]] = []
        self._health_checks: List[Dict[str, Any]] = []

    def record_lag(self, stream_name: str, pending_count: int):
        """Record consumer lag for a stream."""
        self._lag_metrics[stream_name] = pending_count
        if pending_count > self.max_lag_threshold:
            logger.warning(
                f"Backpressure alert: stream={stream_name} lag={pending_count} > threshold={self.max_lag_threshold}"
            )

    def record_throughput(self, stream_name: str, messages_per_second: float):
        """Record throughput metric."""
        self._throughput_log.append({
            "stream": stream_name,
            "mps": messages_per_second,
            "ts": datetime.utcnow().isoformat(),
        })

    def should_throttle(self) -> bool:
        """Check if we should throttle new work based on backpressure."""
        total_lag = sum(self._lag_metrics.values())
        return total_lag > self.max_lag_threshold or self._current_concurrency >= self.max_concurrency

    def acquire_slot(self) -> bool:
        """Try to acquire a concurrency slot. Returns False if at capacity."""
        if self._current_concurrency >= self.max_concurrency:
            return False
        self._current_concurrency += 1
        return True

    def release_slot(self):
        """Release a concurrency slot."""
        self._current_concurrency = max(0, self._current_concurrency - 1)

    def health_check(self) -> Dict[str, Any]:
        """Produce a health check report."""
        total_lag = sum(self._lag_metrics.values())
        healthy = total_lag <= self.max_lag_threshold
        report = {
            "healthy": healthy,
            "total_lag": total_lag,
            "max_lag_threshold": self.max_lag_threshold,
            "lag_per_stream": dict(self._lag_metrics),
            "current_concurrency": self._current_concurrency,
            "max_concurrency": self.max_concurrency,
            "throttling": self.should_throttle(),
            "ts": datetime.utcnow().isoformat(),
        }
        self._health_checks.append(report)
        return report

    def get_metrics(self) -> Dict[str, Any]:
        """Get Prometheus-compatible metrics dict."""
        return {
            "event_bus_consumer_lag_total": sum(self._lag_metrics.values()),
            "event_bus_consumer_lag_per_stream": dict(self._lag_metrics),
            "event_bus_active_workers": self._current_concurrency,
            "event_bus_max_workers": self.max_concurrency,
            "event_bus_throttling": 1 if self.should_throttle() else 0,
        }


# =============================================================================
# FastAPI App Factory
# =============================================================================

def create_app(
    auth: Optional[AuthMiddleware] = None,
    progress: Optional[ProgressManager] = None,
    backpressure: Optional[BackpressureMonitor] = None,
    governance_modules: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Create the API application configuration.
    
    Returns a dict of route handlers suitable for FastAPI/Starlette mounting.
    For production, this would return a FastAPI() app instance.
    For testing/dev, returns the handler registry for direct invocation.
    
    Args:
        governance_modules: Optional dict of enterprise module instances for
            governance routes. Keys: security_registry, risk_registry,
            sla_tracker, exception_manager, lineage_tracker, model_registry,
            dq_engine, benchmark_engine, health_monitor.
    """
    _auth = auth or AuthMiddleware()
    _progress = progress or ProgressManager()
    _backpressure = backpressure or BackpressureMonitor()

    def get_report(company_id: str, report_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/reports/{company_id}/{report_id}"""
        ctx = _auth.authenticate(authorization)
        if not ctx.authenticated:
            return {"error": "Unauthorized", "status": 401}
        if not _auth.authorize_company_access(ctx, company_id):
            return {"error": "Forbidden: tenant boundary violation", "status": 403}
        if not _auth.authorize_permission(ctx, "view_reports"):
            return {"error": "Forbidden: insufficient permissions", "status": 403}
        return {"status": 200, "company_id": company_id, "report_id": report_id}

    def get_progress(company_id: str, authorization: str) -> Dict[str, Any]:
        """GET /api/v1/progress/{company_id}"""
        ctx = _auth.authenticate(authorization)
        if not ctx.authenticated:
            return {"error": "Unauthorized", "status": 401}
        if not _auth.authorize_company_access(ctx, company_id):
            return {"error": "Forbidden: tenant boundary violation", "status": 403}
        return {
            "status": 200,
            "progress": _progress.get_recent_progress(company_id),
        }

    def health() -> Dict[str, Any]:
        """GET /api/v1/health"""
        return {
            "status": 200,
            **_backpressure.health_check(),
        }

    routes = {
        "GET /api/v1/reports/{company_id}/{report_id}": get_report,
        "GET /api/v1/progress/{company_id}": get_progress,
        "GET /api/v1/health": health,
    }

    # Mount governance routes if modules are provided
    if governance_modules:
        try:
            from loweconex_platform.api.governance_routes import create_governance_routes
            gov = create_governance_routes(auth=_auth, **governance_modules)
            routes.update(gov.get("routes", {}))
        except Exception as e:
            logger.warning(f"Governance routes not mounted: {e}")

    # Mount KPI dashboard routes
    kpi_cache = None
    try:
        from loweconex_platform.api.kpi_routes import create_kpi_routes, KPIDashboardCache
        kpi_cache = KPIDashboardCache()
        kpi = create_kpi_routes(auth=_auth, cache=kpi_cache)
        routes.update(kpi.get("routes", {}))
        kpi_cache = kpi["cache"]
    except Exception as e:
        logger.warning(f"KPI dashboard routes not mounted: {e}")

    return {
        "auth": _auth,
        "progress": _progress,
        "backpressure": _backpressure,
        "kpi_cache": kpi_cache,
        "routes": routes,
    }
