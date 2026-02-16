"""
Connector Base Classes

Defines the plugin interface for external system integrations.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Type

logger = logging.getLogger(__name__)


@dataclass
class ConnectorConfig:
    """Configuration for a connector"""
    name: str
    connector_type: str  # bms, cmms, notification
    enabled: bool = True
    
    # Connection settings
    base_url: Optional[str] = None
    api_key: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None
    
    # Retry settings
    max_retries: int = 3
    retry_delay_seconds: float = 1.0
    timeout_seconds: float = 30.0
    
    # Rate limiting
    max_requests_per_minute: int = 60
    
    # Custom settings
    settings: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConnectorResponse:
    """Standard response from connector operations"""
    success: bool
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    correlation_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "correlation_id": self.correlation_id,
            "timestamp": self.timestamp.isoformat(),
        }


class ConnectorBase(ABC):
    """
    Base class for all connectors.
    
    Connectors provide integration with external systems:
    - BMS (Building Management System)
    - CMMS (Computerized Maintenance Management System)
    - Notification services
    """
    
    def __init__(self, config: ConnectorConfig):
        self.config = config
        self.name = config.name
        self._connected = False
    
    @property
    def connector_type(self) -> str:
        """Return connector type identifier"""
        return self.config.connector_type
    
    @property
    def is_connected(self) -> bool:
        """Check if connector is connected"""
        return self._connected
    
    @abstractmethod
    def connect(self) -> bool:
        """
        Establish connection to external system.
        
        Returns:
            True if connection successful
        """
        pass
    
    @abstractmethod
    def disconnect(self) -> bool:
        """
        Close connection to external system.
        
        Returns:
            True if disconnection successful
        """
        pass
    
    @abstractmethod
    def health_check(self) -> bool:
        """
        Check if connection is healthy.
        
        Returns:
            True if healthy
        """
        pass
    
    def _log_operation(self, operation: str, details: Dict[str, Any]):
        """Log an operation for audit"""
        logger.info(
            f"[{self.name}] {operation}: {details}",
            extra={"connector": self.name, "operation": operation, **details}
        )


class ConnectorRegistry:
    """
    Registry for connector plugins.
    
    Manages connector lifecycle and provides factory methods.
    """
    
    _instance = None
    _connectors: Dict[str, Type[ConnectorBase]] = {}
    _instances: Dict[str, ConnectorBase] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    @classmethod
    def register(cls, connector_type: str, connector_class: Type[ConnectorBase]):
        """Register a connector class"""
        cls._connectors[connector_type] = connector_class
        logger.info(f"Registered connector: {connector_type} -> {connector_class.__name__}")
    
    @classmethod
    def create(cls, config: ConnectorConfig) -> ConnectorBase:
        """Create a connector instance from config"""
        connector_type = config.connector_type
        
        if connector_type not in cls._connectors:
            raise ValueError(f"Unknown connector type: {connector_type}")
        
        connector_class = cls._connectors[connector_type]
        instance = connector_class(config)
        
        # Cache instance
        cls._instances[config.name] = instance
        
        return instance
    
    @classmethod
    def get(cls, name: str) -> Optional[ConnectorBase]:
        """Get a connector instance by name"""
        return cls._instances.get(name)
    
    @classmethod
    def list_types(cls) -> List[str]:
        """List registered connector types"""
        return list(cls._connectors.keys())
    
    @classmethod
    def list_instances(cls) -> List[str]:
        """List active connector instances"""
        return list(cls._instances.keys())


def connector(connector_type: str):
    """
    Decorator to register a connector class.
    
    Usage:
        @connector("bms")
        class MyBMSConnector(BMSConnector):
            ...
    """
    def decorator(cls: Type[ConnectorBase]) -> Type[ConnectorBase]:
        ConnectorRegistry.register(connector_type, cls)
        return cls
    return decorator
