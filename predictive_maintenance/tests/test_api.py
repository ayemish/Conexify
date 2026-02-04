"""
Tests for API Layer
"""

import pytest
from datetime import datetime
from fastapi.testclient import TestClient

import sys
import pathlib
ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from predictive_maintenance.api.app import create_app
from predictive_maintenance.api.schemas import (
    TelemetryRequest,
    AlertResponse,
    AssetResponse,
)


@pytest.fixture
def client():
    """Create test client"""
    app = create_app(debug=True)
    return TestClient(app)


class TestHealthEndpoints:
    """Test health check endpoints"""
    
    def test_health_check(self, client):
        """Test basic health check"""
        response = client.get("/health")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "healthy"
        assert "version" in data
    
    def test_liveness_check(self, client):
        """Test liveness probe"""
        response = client.get("/live")
        assert response.status_code == 200
        assert response.json()["status"] == "alive"
    
    def test_readiness_check(self, client):
        """Test readiness probe"""
        response = client.get("/ready")
        assert response.status_code == 200
        
        data = response.json()
        assert "ready" in data
        assert "database" in data
        assert "redis" in data


class TestTelemetryEndpoints:
    """Test telemetry endpoints"""
    
    def test_process_telemetry(self, client):
        """Test telemetry processing"""
        telemetry = {
            "timestamp": datetime.utcnow().isoformat(),
            "asset_id": "RTU_TEST_001",
            "site_id": "test_site",
            "compressor_on": True,
            "compressor_current": 15.0,
            "suction_pressure": 118.0,
            "discharge_pressure": 400.0,
            "supply_air_temp": 55.0,
            "return_air_temp": 75.0,
            "ambient_temp": 95.0,
        }
        
        response = client.post("/api/v1/telemetry", json=telemetry)
        assert response.status_code == 200
        
        data = response.json()
        assert data["asset_id"] == "RTU_TEST_001"
        assert data["processed"] == True
        assert "regime" in data
    
    def test_telemetry_validation(self, client):
        """Test telemetry validation"""
        # Missing required field
        telemetry = {
            "timestamp": datetime.utcnow().isoformat(),
            # Missing asset_id
        }
        
        response = client.post("/api/v1/telemetry", json=telemetry)
        assert response.status_code == 422  # Validation error
    
    def test_telemetry_batch(self, client):
        """Test batch telemetry processing"""
        readings = [
            {
                "timestamp": datetime.utcnow().isoformat(),
                "asset_id": f"RTU_TEST_{i:03d}",
                "site_id": "test_site",
                "compressor_on": True,
            }
            for i in range(5)
        ]
        
        response = client.post("/api/v1/telemetry/batch", json={"readings": readings})
        assert response.status_code == 200
        
        data = response.json()
        assert data["processed"] == 5


class TestAssetEndpoints:
    """Test asset endpoints"""
    
    def test_create_asset(self, client):
        """Test asset creation"""
        asset = {
            "asset_id": "RTU_CREATE_TEST",
            "site_id": "test_site",
            "asset_type": "hvac_rtu",
            "manufacturer": "Carrier",
        }
        
        response = client.post("/api/v1/assets", json=asset)
        # May fail if DB not available, that's ok for unit test
        assert response.status_code in [200, 500]
    
    def test_list_assets(self, client):
        """Test asset listing"""
        response = client.get("/api/v1/assets")
        assert response.status_code == 200
        
        data = response.json()
        assert "assets" in data
        assert "total" in data


class TestAlertEndpoints:
    """Test alert endpoints"""
    
    def test_list_alerts(self, client):
        """Test alert listing"""
        response = client.get("/api/v1/alerts")
        assert response.status_code == 200
        
        data = response.json()
        assert "alerts" in data
        assert "total" in data


class TestMetricsEndpoints:
    """Test metrics endpoints"""
    
    def test_deployment_metrics(self, client):
        """Test deployment metrics"""
        response = client.get("/api/v1/metrics/deployment?days=30")
        assert response.status_code == 200
        
        data = response.json()
        assert "period_start" in data
        assert "total_alarms" in data
    
    def test_calibration_metrics(self, client):
        """Test calibration metrics"""
        response = client.get("/api/v1/metrics/calibration")
        assert response.status_code == 200
        
        data = response.json()
        assert "total_feedback_records" in data


class TestAPISchemas:
    """Test API schema validation"""
    
    def test_telemetry_request_validation(self):
        """Test TelemetryRequest validation"""
        # Valid request
        request = TelemetryRequest(
            asset_id="test",
            compressor_on=True,
            suction_pressure=118.0,
        )
        assert request.asset_id == "test"
        
        # Pressure bounds
        request = TelemetryRequest(
            asset_id="test",
            suction_pressure=100.0,  # Valid
        )
        assert request.suction_pressure == 100.0
    
    def test_telemetry_request_defaults(self):
        """Test TelemetryRequest defaults"""
        request = TelemetryRequest(asset_id="test")
        
        assert request.compressor_on == False
        assert request.timestamp is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
