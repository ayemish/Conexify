"""
TC-I: API Layer, Auth Middleware & SSE Progress (TC-I01–I04)

Tests tenant-isolated auth, report access RBAC, SSE progress streaming,
and backpressure monitoring.
"""

import pytest

from loweconex_platform.api.server import (
    AuthMiddleware, TenantContext, ProgressManager, BackpressureMonitor, create_app,
)


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def auth():
    middleware = AuthMiddleware()
    middleware.register_token("token_comp1_admin", TenantContext(
        user_id="user-1", company_id="COMP-1",
        roles=["admin"], permissions=["view_reports", "manage_kpis"],
        authenticated=True,
    ))
    middleware.register_token("token_comp1_viewer", TenantContext(
        user_id="user-2", company_id="COMP-1",
        roles=["viewer"], permissions=["view_reports"],
        authenticated=True,
    ))
    middleware.register_token("token_comp2_admin", TenantContext(
        user_id="user-3", company_id="COMP-2",
        roles=["admin"], permissions=["view_reports", "manage_kpis"],
        authenticated=True,
    ))
    return middleware


@pytest.fixture
def progress():
    return ProgressManager()


@pytest.fixture
def backpressure():
    return BackpressureMonitor(max_lag_threshold=1000, max_concurrency=5)


@pytest.fixture
def app(auth, progress, backpressure):
    return create_app(auth=auth, progress=progress, backpressure=backpressure)


# =============================================================================
# TC-I01: Authentication
# =============================================================================

class TestTCI01Authentication:
    def test_valid_token_authenticates(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_admin")
        assert ctx.authenticated is True
        assert ctx.company_id == "COMP-1"
        assert ctx.user_id == "user-1"

    def test_missing_header_returns_unauthenticated(self, auth):
        ctx = auth.authenticate(None)
        assert ctx.authenticated is False

    def test_invalid_token_returns_unauthenticated(self, auth):
        ctx = auth.authenticate("Bearer invalid_token_xyz")
        assert ctx.authenticated is False

    def test_malformed_header_returns_unauthenticated(self, auth):
        ctx = auth.authenticate("Basic some_basic_auth")
        assert ctx.authenticated is False

    def test_empty_bearer_returns_unauthenticated(self, auth):
        ctx = auth.authenticate("Bearer ")
        assert ctx.authenticated is False


# =============================================================================
# TC-I02: Tenant Isolation
# =============================================================================

class TestTCI02TenantIsolation:
    def test_user_can_access_own_company(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_admin")
        assert auth.authorize_company_access(ctx, "COMP-1") is True

    def test_user_cannot_access_other_company(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_admin")
        assert auth.authorize_company_access(ctx, "COMP-2") is False

    def test_comp2_user_cannot_access_comp1(self, auth):
        ctx = auth.authenticate("Bearer token_comp2_admin")
        assert auth.authorize_company_access(ctx, "COMP-1") is False

    def test_unauthenticated_user_denied(self, auth):
        ctx = TenantContext(authenticated=False)
        assert auth.authorize_company_access(ctx, "COMP-1") is False

    def test_audit_log_records_violation(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_admin")
        auth.authorize_company_access(ctx, "COMP-2")
        log = auth.get_audit_log()
        violations = [e for e in log if e["action"] == "tenant_violation"]
        assert len(violations) >= 1


# =============================================================================
# TC-I03: Permission-Based RBAC
# =============================================================================

class TestTCI03RBAC:
    def test_admin_has_all_permissions(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_admin")
        assert ctx.has_permission("view_reports") is True
        assert ctx.has_permission("manage_kpis") is True
        assert ctx.has_permission("anything_else") is True  # admin role

    def test_viewer_limited_permissions(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_viewer")
        assert ctx.has_permission("view_reports") is True
        assert ctx.has_permission("manage_kpis") is False

    def test_authorize_permission_check(self, auth):
        ctx = auth.authenticate("Bearer token_comp1_viewer")
        assert auth.authorize_permission(ctx, "view_reports") is True
        assert auth.authorize_permission(ctx, "manage_kpis") is False


# =============================================================================
# TC-I04: API Route Handlers
# =============================================================================

class TestTCI04APIRoutes:
    def test_get_report_authorized(self, app):
        handler = app["routes"]["GET /api/v1/reports/{company_id}/{report_id}"]
        result = handler("COMP-1", "report-001", "Bearer token_comp1_admin")
        assert result["status"] == 200
        assert result["company_id"] == "COMP-1"

    def test_get_report_tenant_violation(self, app):
        handler = app["routes"]["GET /api/v1/reports/{company_id}/{report_id}"]
        result = handler("COMP-2", "report-001", "Bearer token_comp1_admin")
        assert result["status"] == 403

    def test_get_report_unauthenticated(self, app):
        handler = app["routes"]["GET /api/v1/reports/{company_id}/{report_id}"]
        result = handler("COMP-1", "report-001", "")
        assert result["status"] == 401

    def test_health_endpoint(self, app):
        handler = app["routes"]["GET /api/v1/health"]
        result = handler()
        assert result["status"] == 200
        assert "healthy" in result
        assert "total_lag" in result

    def test_progress_endpoint_authorized(self, app):
        app["progress"].push_progress("COMP-1", "energy_crew", "running", 50.0, "Calculating...")
        handler = app["routes"]["GET /api/v1/progress/{company_id}"]
        result = handler("COMP-1", "Bearer token_comp1_admin")
        assert result["status"] == 200
        assert len(result["progress"]) >= 1


# =============================================================================
# TC-I: SSE Progress Manager
# =============================================================================

class TestTCIProgressManager:
    def test_push_and_retrieve_progress(self, progress):
        progress.push_progress("COMP-1", "energy_crew", "running", 25.0, "Step 1")
        progress.push_progress("COMP-1", "energy_crew", "running", 75.0, "Step 3")
        recent = progress.get_recent_progress("COMP-1")
        assert len(recent) == 2
        assert recent[0]["progress_pct"] == 25.0
        assert recent[1]["progress_pct"] == 75.0

    def test_progress_filtered_by_company(self, progress):
        progress.push_progress("COMP-1", "crew_a", "done", 100.0)
        progress.push_progress("COMP-2", "crew_b", "done", 100.0)
        comp1 = progress.get_recent_progress("COMP-1")
        comp2 = progress.get_recent_progress("COMP-2")
        assert len(comp1) == 1
        assert len(comp2) == 1
        assert comp1[0]["company_id"] == "COMP-1"


# =============================================================================
# TC-I: Backpressure Monitor
# =============================================================================

class TestTCIBackpressure:
    def test_healthy_when_no_lag(self, backpressure):
        report = backpressure.health_check()
        assert report["healthy"] is True
        assert report["throttling"] is False

    def test_unhealthy_when_lag_exceeds_threshold(self, backpressure):
        backpressure.record_lag("stream:events", 2000)
        report = backpressure.health_check()
        assert report["healthy"] is False
        assert report["throttling"] is True

    def test_concurrency_slots(self, backpressure):
        for _ in range(5):
            assert backpressure.acquire_slot() is True
        assert backpressure.acquire_slot() is False  # At max
        backpressure.release_slot()
        assert backpressure.acquire_slot() is True

    def test_metrics_format(self, backpressure):
        backpressure.record_lag("stream:kpi", 500)
        metrics = backpressure.get_metrics()
        assert "event_bus_consumer_lag_total" in metrics
        assert "event_bus_active_workers" in metrics
        assert "event_bus_throttling" in metrics

    def test_throughput_recording(self, backpressure):
        backpressure.record_throughput("stream:events", 150.5)
        assert len(backpressure._throughput_log) == 1
