"""
BMS (Building Management System) Connector

Provides control write-back capabilities for autopilot actions.
"""

import logging
from abc import abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from .base import ConnectorBase, ConnectorConfig, ConnectorResponse, connector

logger = logging.getLogger(__name__)


@dataclass
class PointValue:
    """Point value with metadata"""
    point_id: str
    value: float
    timestamp: datetime
    quality: str = "good"  # good, uncertain, bad
    source: str = "bms"


class BMSConnector(ConnectorBase):
    """
    Abstract BMS connector interface.
    
    Provides:
    - read_points(): Read current point values
    - write_point(): Write a single point value
    - execute_sequence(): Execute a predefined control sequence
    """
    
    @abstractmethod
    def read_points(
        self,
        point_ids: List[str],
        window_seconds: int = 0,
    ) -> Dict[str, PointValue]:
        """
        Read current point values.
        
        Args:
            point_ids: List of point IDs to read
            window_seconds: If > 0, return average over window
            
        Returns:
            Dict mapping point_id to PointValue
        """
        pass
    
    @abstractmethod
    def write_point(
        self,
        point_id: str,
        value: float,
        ttl_seconds: int = 3600,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """
        Write a point value.
        
        Args:
            point_id: Point to write
            value: Value to write
            ttl_seconds: Time-to-live for override (auto-release after)
            correlation_id: Correlation ID for audit trail
            
        Returns:
            ConnectorResponse with write result
        """
        pass
    
    @abstractmethod
    def execute_sequence(
        self,
        sequence_id: str,
        params: Dict[str, Any] = None,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """
        Execute a predefined control sequence.
        
        Args:
            sequence_id: Sequence identifier
            params: Sequence parameters
            correlation_id: Correlation ID for audit trail
            
        Returns:
            ConnectorResponse with execution result
        """
        pass
    
    @abstractmethod
    def release_override(
        self,
        point_id: str,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """
        Release an active override on a point.
        
        Args:
            point_id: Point to release
            correlation_id: Correlation ID for audit trail
            
        Returns:
            ConnectorResponse with release result
        """
        pass
    
    @abstractmethod
    def get_override_status(
        self,
        point_id: str,
    ) -> Dict[str, Any]:
        """
        Get override status for a point.
        
        Returns:
            Dict with override status including:
            - is_overridden: bool
            - override_value: float (if overridden)
            - override_expiry: datetime (if overridden)
            - overridden_by: str (correlation_id)
        """
        pass


@connector("mock_bms")
class MockBMSConnector(BMSConnector):
    """
    Mock BMS connector for development and testing.
    
    Simulates BMS operations without actual hardware connection.
    """
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._points: Dict[str, PointValue] = {}
        self._overrides: Dict[str, Dict[str, Any]] = {}
        self._sequences: Dict[str, Dict[str, Any]] = {}
        
        # Initialize with some default points
        self._initialize_mock_points()
    
    def _initialize_mock_points(self):
        """Initialize mock point values"""
        default_points = {
            "zone_temp_setpoint": 72.0,
            "discharge_air_temp": 55.0,
            "supply_fan_speed": 80.0,
            "cooling_valve_position": 50.0,
            "heating_valve_position": 0.0,
            "damper_position": 100.0,
            "zone_temp": 73.5,
            "return_air_temp": 74.0,
            "outdoor_air_temp": 85.0,
            "supply_air_temp": 56.0,
        }
        
        for point_id, value in default_points.items():
            self._points[point_id] = PointValue(
                point_id=point_id,
                value=value,
                timestamp=datetime.utcnow(),
            )
    
    def connect(self) -> bool:
        """Establish mock connection"""
        logger.info(f"[{self.name}] Mock BMS connected")
        self._connected = True
        return True
    
    def disconnect(self) -> bool:
        """Close mock connection"""
        logger.info(f"[{self.name}] Mock BMS disconnected")
        self._connected = False
        return True
    
    def health_check(self) -> bool:
        """Check mock connection health"""
        return self._connected
    
    def read_points(
        self,
        point_ids: List[str],
        window_seconds: int = 0,
    ) -> Dict[str, PointValue]:
        """Read mock point values"""
        self._log_operation("read_points", {"point_ids": point_ids})
        
        result = {}
        for point_id in point_ids:
            if point_id in self._points:
                result[point_id] = self._points[point_id]
            else:
                # Generate a mock value
                result[point_id] = PointValue(
                    point_id=point_id,
                    value=0.0,
                    timestamp=datetime.utcnow(),
                    quality="uncertain",
                )
        
        return result
    
    def write_point(
        self,
        point_id: str,
        value: float,
        ttl_seconds: int = 3600,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """Write mock point value"""
        correlation_id = correlation_id or str(uuid.uuid4())
        
        self._log_operation("write_point", {
            "point_id": point_id,
            "value": value,
            "ttl_seconds": ttl_seconds,
            "correlation_id": correlation_id,
        })
        
        # Store previous value
        previous_value = self._points.get(point_id)
        previous = previous_value.value if previous_value else None
        
        # Update point
        self._points[point_id] = PointValue(
            point_id=point_id,
            value=value,
            timestamp=datetime.utcnow(),
            source="autopilot",
        )
        
        # Track override
        from datetime import timedelta
        self._overrides[point_id] = {
            "is_overridden": True,
            "override_value": value,
            "previous_value": previous,
            "override_expiry": datetime.utcnow() + timedelta(seconds=ttl_seconds),
            "overridden_by": correlation_id,
        }
        
        return ConnectorResponse(
            success=True,
            data={
                "point_id": point_id,
                "value": value,
                "previous_value": previous,
                "ttl_seconds": ttl_seconds,
            },
            correlation_id=correlation_id,
        )
    
    def execute_sequence(
        self,
        sequence_id: str,
        params: Dict[str, Any] = None,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """Execute mock control sequence"""
        correlation_id = correlation_id or str(uuid.uuid4())
        params = params or {}
        
        self._log_operation("execute_sequence", {
            "sequence_id": sequence_id,
            "params": params,
            "correlation_id": correlation_id,
        })
        
        # Simulate sequence execution
        self._sequences[sequence_id] = {
            "status": "completed",
            "started_at": datetime.utcnow(),
            "completed_at": datetime.utcnow(),
            "params": params,
            "correlation_id": correlation_id,
        }
        
        return ConnectorResponse(
            success=True,
            data={
                "sequence_id": sequence_id,
                "status": "completed",
            },
            correlation_id=correlation_id,
        )
    
    def release_override(
        self,
        point_id: str,
        correlation_id: str = None,
    ) -> ConnectorResponse:
        """Release mock override"""
        correlation_id = correlation_id or str(uuid.uuid4())
        
        self._log_operation("release_override", {
            "point_id": point_id,
            "correlation_id": correlation_id,
        })
        
        if point_id in self._overrides:
            override = self._overrides[point_id]
            # Restore previous value
            if override.get("previous_value") is not None:
                self._points[point_id] = PointValue(
                    point_id=point_id,
                    value=override["previous_value"],
                    timestamp=datetime.utcnow(),
                    source="bms",
                )
            del self._overrides[point_id]
        
        return ConnectorResponse(
            success=True,
            data={"point_id": point_id, "released": True},
            correlation_id=correlation_id,
        )
    
    def get_override_status(self, point_id: str) -> Dict[str, Any]:
        """Get mock override status"""
        if point_id in self._overrides:
            return self._overrides[point_id]
        
        return {
            "is_overridden": False,
            "override_value": None,
            "override_expiry": None,
            "overridden_by": None,
        }
    
    def set_mock_point(self, point_id: str, value: float):
        """Set a mock point value (for testing)"""
        self._points[point_id] = PointValue(
            point_id=point_id,
            value=value,
            timestamp=datetime.utcnow(),
        )
    
    def get_mock_points(self) -> Dict[str, float]:
        """Get all mock point values (for testing)"""
        return {pid: pv.value for pid, pv in self._points.items()}
