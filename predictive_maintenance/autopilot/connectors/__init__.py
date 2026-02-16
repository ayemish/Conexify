"""
Autopilot Connectors Module

Plugin interface for external system integrations:
- BMS (Building Management System) for control write-back
- CMMS (Computerized Maintenance Management System) for work orders
- Notification systems for alerts and approvals

Mock connectors are only registered when PDM_ENVIRONMENT != "production".
"""

import os

from .base import (
    ConnectorBase,
    ConnectorConfig,
    ConnectorRegistry,
)
from .bms import BMSConnector
from .cmms import CMSSConnector
from .notification import NotificationConnector

__all__ = [
    "ConnectorBase",
    "ConnectorConfig",
    "ConnectorRegistry",
    "BMSConnector",
    "CMSSConnector",
    "NotificationConnector",
]

# Gate mock connectors behind PDM_ENVIRONMENT — never load in production
_env = os.environ.get("PDM_ENVIRONMENT", "development").lower()
if _env != "production":
    from .bms import MockBMSConnector
    from .cmms import MockCMSSConnector
    from .notification import MockNotificationConnector
    __all__ += ["MockBMSConnector", "MockCMSSConnector", "MockNotificationConnector"]
else:
    # Unregister mock connectors if they were auto-registered by @connector decorator
    for _mock_type in ("mock_bms", "mock_cmms", "mock_notification"):
        ConnectorRegistry._connectors.pop(_mock_type, None)
