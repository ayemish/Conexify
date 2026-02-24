import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from predictive_maintenance.api.app import create_app
from predictive_maintenance.config import get_settings


@pytest.fixture(autouse=True)
def _reset_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_auth_middleware_missing_key_rejected(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "development")
    monkeypatch.setenv("PDM_API_KEYS", "test-key")
    app = create_app(debug=True)
    client = TestClient(app)

    response = client.get("/api/v1/assets")
    assert response.status_code == 401
    assert response.json().get("error_code") == "AUTH_MISSING_KEY"


def test_auth_middleware_invalid_key_rejected(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "development")
    monkeypatch.setenv("PDM_API_KEYS", "valid-key")
    app = create_app(debug=True)
    client = TestClient(app)

    response = client.get("/api/v1/assets", headers={"X-API-Key": "wrong-key"})
    assert response.status_code == 403
    assert response.json().get("error_code") == "AUTH_INVALID_KEY"


def test_auth_validate_no_implicit_admin_fallback(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "development")
    monkeypatch.delenv("PDM_API_KEYS", raising=False)
    app = create_app(debug=True)
    client = TestClient(app)

    response = client.post("/api/v1/auth/validate", json={"api_key": "anything"})
    assert response.status_code == 503


def test_websocket_auth_blocks_unauthorized(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "development")
    monkeypatch.setenv("PDM_API_KEYS", "valid-key")
    app = create_app(debug=True)
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as exc_info:
        with client.websocket_connect("/api/v1/ws/operator"):
            pass
    assert exc_info.value.code == 4401


def test_websocket_auth_accepts_valid_key(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "development")
    monkeypatch.setenv("PDM_API_KEYS", "valid-key")
    app = create_app(debug=True)
    client = TestClient(app)

    with client.websocket_connect("/api/v1/ws/operator", headers={"X-API-Key": "valid-key"}) as ws:
        payload = ws.receive_json()
        assert payload["type"] == "connected"


def test_production_requires_configured_api_keys(monkeypatch):
    monkeypatch.setenv("PDM_ENVIRONMENT", "production")
    monkeypatch.delenv("PDM_API_KEYS", raising=False)

    with pytest.raises(RuntimeError, match="PDM_API_KEYS is required in production"):
        create_app(debug=False)
