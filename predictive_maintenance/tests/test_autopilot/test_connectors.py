"""
Tests for Autopilot Connectors
"""

import pytest
from predictive_maintenance.autopilot.connectors.base import (
    ConnectorConfig,
    ConnectorRegistry,
)
from predictive_maintenance.autopilot.connectors.bms import (
    MockBMSConnector,
    PointValue,
)
from predictive_maintenance.autopilot.connectors.cmms import (
    MockCMSSConnector,
    WorkOrder,
)
from predictive_maintenance.autopilot.connectors.notification import (
    MockNotificationConnector,
)


@pytest.fixture
def bms_config():
    return ConnectorConfig(
        name="test_bms",
        connector_type="mock_bms",
        enabled=True,
    )


@pytest.fixture
def cmms_config():
    return ConnectorConfig(
        name="test_cmms",
        connector_type="mock_cmms",
        enabled=True,
    )


@pytest.fixture
def notification_config():
    return ConnectorConfig(
        name="test_notification",
        connector_type="mock_notification",
        enabled=True,
    )


class TestMockBMSConnector:
    """Test Mock BMS Connector"""
    
    def test_connect(self, bms_config):
        connector = MockBMSConnector(bms_config)
        assert connector.connect() == True
        assert connector.is_connected == True
    
    def test_disconnect(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        assert connector.disconnect() == True
        assert connector.is_connected == False
    
    def test_health_check(self, bms_config):
        connector = MockBMSConnector(bms_config)
        assert connector.health_check() == False
        connector.connect()
        assert connector.health_check() == True
    
    def test_read_points(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        
        # Read default points
        points = connector.read_points(["zone_temp", "supply_fan_speed"])
        
        assert "zone_temp" in points
        assert "supply_fan_speed" in points
        assert isinstance(points["zone_temp"], PointValue)
    
    def test_write_point(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        
        # Write a point
        response = connector.write_point(
            point_id="zone_temp_setpoint",
            value=74.0,
            ttl_seconds=3600,
            correlation_id="test-123"
        )
        
        assert response.success == True
        assert response.data["point_id"] == "zone_temp_setpoint"
        assert response.data["value"] == 74.0
        assert response.correlation_id == "test-123"
    
    def test_write_updates_value(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        
        # Write a value
        connector.write_point("test_point", 100.0)
        
        # Read it back
        points = connector.read_points(["test_point"])
        assert points["test_point"].value == 100.0
    
    def test_override_status(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        
        # No override initially
        status = connector.get_override_status("test_point")
        assert status["is_overridden"] == False
        
        # Write creates override
        connector.write_point("test_point", 50.0, correlation_id="ovr-001")
        
        status = connector.get_override_status("test_point")
        assert status["is_overridden"] == True
        assert status["override_value"] == 50.0
        assert status["overridden_by"] == "ovr-001"
    
    def test_release_override(self, bms_config):
        connector = MockBMSConnector(bms_config)
        connector.connect()
        
        # Set initial value
        connector.set_mock_point("test_point", 70.0)
        
        # Create override
        connector.write_point("test_point", 80.0)
        
        # Release override
        response = connector.release_override("test_point")
        assert response.success == True
        
        # Value should be restored
        points = connector.read_points(["test_point"])
        assert points["test_point"].value == 70.0


class TestMockCMSSConnector:
    """Test Mock CMMS Connector"""
    
    def test_create_ticket(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        result = connector.create_ticket(
            title="Test Ticket",
            description="Test description",
            priority="P2",
            asset_id="RTU-001",
            site_id="SITE-001",
        )
        
        assert "ticket_id" in result
        assert result["title"] == "Test Ticket"
        assert result["priority"] == "P2"
        assert result["status"] == "open"
    
    def test_get_ticket(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        # Create ticket
        result = connector.create_ticket(
            title="Retrieve Test",
            description="Test",
            priority="P1",
        )
        ticket_id = result["ticket_id"]
        
        # Retrieve it
        ticket = connector.get_ticket(ticket_id)
        
        assert ticket is not None
        assert isinstance(ticket, WorkOrder)
        assert ticket.title == "Retrieve Test"
        assert ticket.priority == "P1"
    
    def test_update_ticket(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        # Create ticket
        result = connector.create_ticket(title="Update Test", description="", priority="P3")
        ticket_id = result["ticket_id"]
        
        # Update it
        update_result = connector.update_ticket(ticket_id, {"status": "in_progress"})
        
        assert update_result["status"] == "in_progress"
        
        # Verify update
        ticket = connector.get_ticket(ticket_id)
        assert ticket.status == "in_progress"
    
    def test_attach_evidence(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        # Create ticket
        result = connector.create_ticket(title="Evidence Test", description="", priority="P2")
        ticket_id = result["ticket_id"]
        
        # Attach evidence
        response = connector.attach_evidence(
            ticket_id=ticket_id,
            evidence_pack_url="https://storage.example.com/evidence/EVD-001",
            evidence_pack_id="EVD-001",
        )
        
        assert response.success == True
        
        # Verify attachment
        ticket = connector.get_ticket(ticket_id)
        assert "EVD-001" in ticket.attachments
    
    def test_add_note(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        # Create ticket
        result = connector.create_ticket(title="Note Test", description="", priority="P2")
        ticket_id = result["ticket_id"]
        
        # Add note
        response = connector.add_note(
            ticket_id=ticket_id,
            note="Test note content",
            note_type="comment",
        )
        
        assert response.success == True
    
    def test_list_tickets(self, cmms_config):
        connector = MockCMSSConnector(cmms_config)
        connector.connect()
        
        # Create tickets
        connector.create_ticket(title="List Test 1", description="", priority="P2", site_id="SITE-A")
        connector.create_ticket(title="List Test 2", description="", priority="P1", site_id="SITE-A")
        connector.create_ticket(title="List Test 3", description="", priority="P2", site_id="SITE-B")
        
        # List all
        all_tickets = connector.list_tickets()
        assert len(all_tickets) == 3
        
        # Filter by site
        site_a_tickets = connector.list_tickets(site_id="SITE-A")
        assert len(site_a_tickets) == 2


class TestMockNotificationConnector:
    """Test Mock Notification Connector"""
    
    def test_send_notification(self, notification_config):
        connector = MockNotificationConnector(notification_config)
        connector.connect()
        
        response = connector.send(
            recipients=["user@example.com"],
            message="Test notification",
            channel="email",
            subject="Test Subject",
        )
        
        assert response.success == True
        assert "notification_id" in response.data
    
    def test_send_approval_request(self, notification_config):
        connector = MockNotificationConnector(notification_config)
        connector.connect()
        
        response = connector.send_approval_request(
            recipients=["approver@example.com"],
            approval_id="APR-001",
            run_id="RUN-001",
            proposed_actions=[{"type": "WRITE_POINT", "description": "Adjust setpoint"}],
            rationale="Temperature exceeds threshold",
        )
        
        assert response.success == True
        assert response.data["approval_id"] == "APR-001"
    
    def test_send_alert(self, notification_config):
        connector = MockNotificationConnector(notification_config)
        connector.connect()
        
        response = connector.send_alert(
            recipients=["facilities@example.com"],
            alert_type="high_temperature",
            asset_id="RTU-001",
            site_id="SITE-001",
            message="Zone temperature exceeds 85°F",
            severity="high",
        )
        
        assert response.success == True
        assert response.data["severity"] == "high"
    
    def test_get_sent_log(self, notification_config):
        connector = MockNotificationConnector(notification_config)
        connector.connect()
        
        # Send some notifications
        connector.send(recipients=["a@test.com"], message="Test 1", channel="email")
        connector.send(recipients=["b@test.com"], message="Test 2", channel="sms")
        
        # Get log
        log = connector.get_sent_log()
        
        assert len(log) == 2
        assert log[0]["recipients"] == ["a@test.com"]
        assert log[1]["recipients"] == ["b@test.com"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
