"""
Notification Connector

Provides notification capabilities for autopilot runs.
"""

import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import uuid

from .base import ConnectorBase, ConnectorConfig, ConnectorResponse, connector

logger = logging.getLogger(__name__)


@dataclass
class Notification:
    """Notification record"""
    notification_id: str
    recipients: List[str]
    channel: str  # email, sms, push, webhook
    subject: str
    message: str
    
    # Status
    status: str = "pending"  # pending, sent, delivered, failed
    
    # Context
    run_id: Optional[str] = None
    approval_id: Optional[str] = None
    
    # Timing
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: Optional[datetime] = None
    delivered_at: Optional[datetime] = None
    
    # Error tracking
    error: Optional[str] = None
    retry_count: int = 0


class NotificationConnector(ConnectorBase):
    """
    Abstract notification connector interface.
    
    Provides:
    - send(): Send a notification
    - send_approval_request(): Send approval request notification
    - send_alert(): Send alert notification
    """
    
    @abstractmethod
    def send(
        self,
        recipients: List[str],
        message: str,
        channel: str = "email",
        subject: str = None,
        context: Dict[str, Any] = None,
    ) -> ConnectorResponse:
        """
        Send a notification.
        
        Args:
            recipients: List of recipient identifiers
            message: Message content
            channel: Delivery channel (email, sms, push, webhook)
            subject: Message subject (for email)
            context: Additional context data
            
        Returns:
            ConnectorResponse with send result
        """
        pass
    
    @abstractmethod
    def send_approval_request(
        self,
        recipients: List[str],
        approval_id: str,
        run_id: str,
        proposed_actions: List[Dict[str, Any]],
        rationale: str,
        expires_at: datetime = None,
    ) -> ConnectorResponse:
        """
        Send an approval request notification.
        
        Args:
            recipients: Approvers to notify
            approval_id: Approval ID
            run_id: Run ID
            proposed_actions: Actions requiring approval
            rationale: Why approval is needed
            expires_at: Approval expiration time
            
        Returns:
            ConnectorResponse with send result
        """
        pass
    
    @abstractmethod
    def send_alert(
        self,
        recipients: List[str],
        alert_type: str,
        asset_id: str,
        site_id: str,
        message: str,
        severity: str = "medium",
    ) -> ConnectorResponse:
        """
        Send an alert notification.
        
        Args:
            recipients: Recipients to notify
            alert_type: Type of alert
            asset_id: Related asset
            site_id: Related site
            message: Alert message
            severity: Alert severity
            
        Returns:
            ConnectorResponse with send result
        """
        pass
    
    @abstractmethod
    def get_notification_status(
        self,
        notification_id: str,
    ) -> Optional[Notification]:
        """
        Get notification delivery status.
        
        Args:
            notification_id: Notification ID
            
        Returns:
            Notification or None if not found
        """
        pass


@connector("mock_notification")
class MockNotificationConnector(NotificationConnector):
    """
    Mock notification connector for development and testing.
    """
    
    def __init__(self, config: ConnectorConfig):
        super().__init__(config)
        self._notifications: Dict[str, Notification] = {}
        self._sent_log: List[Dict[str, Any]] = []
    
    def connect(self) -> bool:
        logger.info(f"[{self.name}] Mock notification service connected")
        self._connected = True
        return True
    
    def disconnect(self) -> bool:
        logger.info(f"[{self.name}] Mock notification service disconnected")
        self._connected = False
        return True
    
    def health_check(self) -> bool:
        return self._connected
    
    def send(
        self,
        recipients: List[str],
        message: str,
        channel: str = "email",
        subject: str = None,
        context: Dict[str, Any] = None,
    ) -> ConnectorResponse:
        notification_id = f"NOT-{uuid.uuid4().hex[:8].upper()}"
        
        self._log_operation("send", {
            "notification_id": notification_id,
            "recipients": recipients,
            "channel": channel,
        })
        
        notification = Notification(
            notification_id=notification_id,
            recipients=recipients,
            channel=channel,
            subject=subject or "Autopilot Notification",
            message=message,
            status="sent",
            sent_at=datetime.utcnow(),
            run_id=context.get("run_id") if context else None,
        )
        
        self._notifications[notification_id] = notification
        self._sent_log.append({
            "notification_id": notification_id,
            "recipients": recipients,
            "channel": channel,
            "subject": subject,
            "message": message[:100],
            "sent_at": datetime.utcnow().isoformat(),
        })
        
        logger.info(
            f"[MOCK] Sent notification {notification_id} to {recipients} via {channel}"
        )
        
        return ConnectorResponse(
            success=True,
            data={
                "notification_id": notification_id,
                "status": "sent",
                "recipients": recipients,
                "channel": channel,
            },
        )
    
    def send_approval_request(
        self,
        recipients: List[str],
        approval_id: str,
        run_id: str,
        proposed_actions: List[Dict[str, Any]],
        rationale: str,
        expires_at: datetime = None,
    ) -> ConnectorResponse:
        notification_id = f"NOT-{uuid.uuid4().hex[:8].upper()}"
        
        self._log_operation("send_approval_request", {
            "notification_id": notification_id,
            "approval_id": approval_id,
            "recipients": recipients,
        })
        
        message = f"""
APPROVAL REQUIRED

Run ID: {run_id}
Approval ID: {approval_id}

Proposed Actions:
{self._format_actions(proposed_actions)}

Rationale: {rationale}

Expires: {expires_at.isoformat() if expires_at else 'No expiration'}

Please approve or reject this request.
"""
        
        notification = Notification(
            notification_id=notification_id,
            recipients=recipients,
            channel="email",
            subject=f"[APPROVAL REQUIRED] Autopilot Run {run_id}",
            message=message,
            status="sent",
            sent_at=datetime.utcnow(),
            run_id=run_id,
            approval_id=approval_id,
        )
        
        self._notifications[notification_id] = notification
        
        logger.info(
            f"[MOCK] Sent approval request {approval_id} to {recipients}"
        )
        
        return ConnectorResponse(
            success=True,
            data={
                "notification_id": notification_id,
                "approval_id": approval_id,
                "status": "sent",
            },
        )
    
    def send_alert(
        self,
        recipients: List[str],
        alert_type: str,
        asset_id: str,
        site_id: str,
        message: str,
        severity: str = "medium",
    ) -> ConnectorResponse:
        notification_id = f"NOT-{uuid.uuid4().hex[:8].upper()}"
        
        self._log_operation("send_alert", {
            "notification_id": notification_id,
            "alert_type": alert_type,
            "severity": severity,
        })
        
        full_message = f"""
[{severity.upper()}] {alert_type}

Site: {site_id}
Asset: {asset_id}

{message}
"""
        
        notification = Notification(
            notification_id=notification_id,
            recipients=recipients,
            channel="email",
            subject=f"[{severity.upper()}] {alert_type} - {asset_id}",
            message=full_message,
            status="sent",
            sent_at=datetime.utcnow(),
        )
        
        self._notifications[notification_id] = notification
        
        logger.info(
            f"[MOCK] Sent alert {alert_type} ({severity}) to {recipients}"
        )
        
        return ConnectorResponse(
            success=True,
            data={
                "notification_id": notification_id,
                "alert_type": alert_type,
                "severity": severity,
                "status": "sent",
            },
        )
    
    def get_notification_status(
        self,
        notification_id: str,
    ) -> Optional[Notification]:
        return self._notifications.get(notification_id)
    
    def _format_actions(self, actions: List[Dict[str, Any]]) -> str:
        """Format actions for display"""
        lines = []
        for i, action in enumerate(actions, 1):
            lines.append(f"  {i}. {action.get('type', 'Unknown')}: {action.get('description', '')}")
        return "\n".join(lines) or "  (No actions specified)"
    
    def get_sent_log(self) -> List[Dict[str, Any]]:
        """Get sent notifications log (for testing)"""
        return self._sent_log.copy()
    
    def clear_log(self):
        """Clear sent log (for testing)"""
        self._sent_log.clear()
