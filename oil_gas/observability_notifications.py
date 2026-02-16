"""
Phase 5: Observability & API Layer - Notification Service

Notification delivery for alerts and system events.
"""

import logging
import json
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from .observability_models import (
    Alert,
    AlertSeverity,
    Notification,
    NotificationChannel,
    NotificationChannelType,
)

logger = logging.getLogger(__name__)


class NotificationProvider(ABC):
    """Base class for notification providers"""
    
    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Send a notification. Returns True on success."""
        pass


class WebhookProvider(NotificationProvider):
    """Webhook notification provider"""
    
    def __init__(self, url: str, headers: Dict[str, str] = None):
        self.url = url
        self.headers = headers or {"Content-Type": "application/json"}
    
    def send(self, notification: Notification) -> bool:
        """Send webhook notification"""
        try:
            payload = {
                "alert_id": notification.alert_id,
                "severity": notification.severity.value,
                "subject": notification.subject,
                "body": notification.body,
                "timestamp": notification.created_at.isoformat(),
                "metadata": notification.metadata,
            }
            
            # In production, would use requests library
            # import requests
            # response = requests.post(self.url, json=payload, headers=self.headers)
            # return response.status_code == 200
            
            logger.info(f"[WEBHOOK] Would send to {self.url}: {json.dumps(payload)[:200]}")
            return True
            
        except Exception as e:
            logger.error(f"Webhook send failed: {e}")
            return False


class EmailProvider(NotificationProvider):
    """Email notification provider"""
    
    def __init__(self, smtp_host: str, smtp_port: int = 587,
                 username: str = "", password: str = "",
                 from_address: str = ""):
        self.smtp_host = smtp_host
        self.smtp_port = smtp_port
        self.username = username
        self.password = password
        self.from_address = from_address
    
    def send(self, notification: Notification) -> bool:
        """Send email notification"""
        try:
            # In production, would use smtplib
            # import smtplib
            # from email.mime.text import MIMEText
            
            logger.info(f"[EMAIL] Would send to {notification.recipient}: {notification.subject}")
            return True
            
        except Exception as e:
            logger.error(f"Email send failed: {e}")
            return False


class SlackProvider(NotificationProvider):
    """Slack notification provider"""
    
    def __init__(self, webhook_url: str, channel: str = ""):
        self.webhook_url = webhook_url
        self.channel = channel
    
    def send(self, notification: Notification) -> bool:
        """Send Slack notification"""
        try:
            # Format as Slack message
            color = self._severity_to_color(notification.severity)
            
            payload = {
                "channel": self.channel,
                "attachments": [{
                    "color": color,
                    "title": notification.subject,
                    "text": notification.body,
                    "fields": [
                        {"title": "Alert ID", "value": notification.alert_id, "short": True},
                        {"title": "Severity", "value": notification.severity.value, "short": True},
                    ],
                    "ts": int(notification.created_at.timestamp()),
                }],
            }
            
            logger.info(f"[SLACK] Would send to {self.channel}: {notification.subject}")
            return True
            
        except Exception as e:
            logger.error(f"Slack send failed: {e}")
            return False
    
    def _severity_to_color(self, severity: AlertSeverity) -> str:
        """Map severity to Slack attachment color"""
        return {
            AlertSeverity.INFO: "#36a64f",      # Green
            AlertSeverity.WARNING: "#ffcc00",   # Yellow
            AlertSeverity.ERROR: "#ff6600",     # Orange
            AlertSeverity.CRITICAL: "#ff0000",  # Red
        }.get(severity, "#808080")


class InAppProvider(NotificationProvider):
    """In-app notification provider (stores for retrieval)"""
    
    def __init__(self, storage: List[Notification] = None):
        self.storage = storage if storage is not None else []
    
    def send(self, notification: Notification) -> bool:
        """Store notification for in-app display"""
        self.storage.append(notification)
        logger.info(f"[IN_APP] Stored notification: {notification.subject}")
        return True
    
    def get_unread(self, recipient: str) -> List[Notification]:
        """Get unread notifications for a recipient"""
        return [n for n in self.storage 
                if n.recipient == recipient and not n.delivered]
    
    def mark_read(self, notification_id: str) -> bool:
        """Mark notification as read"""
        for n in self.storage:
            if n.notification_id == notification_id:
                n.delivered = True
                return True
        return False


class NotificationService:
    """
    Central notification service for alert delivery.
    Manages channels, providers, and delivery.
    """
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
        self.providers: Dict[NotificationChannelType, NotificationProvider] = {}
        self.notification_history: List[Notification] = []
        self._callbacks: List[Callable[[Notification], None]] = []
        
        # Initialize default in-app provider
        self._in_app_storage: List[Notification] = []
        self.providers[NotificationChannelType.IN_APP] = InAppProvider(self._in_app_storage)
        
        logger.info("NotificationService initialized")
    
    def register_provider(self, channel_type: NotificationChannelType,
                          provider: NotificationProvider):
        """Register a notification provider"""
        self.providers[channel_type] = provider
        logger.info(f"Registered provider for {channel_type.value}")
    
    def add_channel(self, channel: NotificationChannel):
        """Add a notification channel"""
        self.channels[channel.channel_id] = channel
        logger.info(f"Added channel: {channel.name} ({channel.channel_type.value})")
    
    def remove_channel(self, channel_id: str):
        """Remove a notification channel"""
        if channel_id in self.channels:
            del self.channels[channel_id]
    
    def add_callback(self, callback: Callable[[Notification], None]):
        """Add callback for notification events"""
        self._callbacks.append(callback)
    
    def notify_alert(self, alert: Alert, channel_ids: List[str] = None) -> List[Notification]:
        """
        Send notifications for an alert.
        Returns list of notifications sent.
        """
        notifications = []
        
        # Determine channels to notify
        if channel_ids:
            channels = [self.channels[cid] for cid in channel_ids if cid in self.channels]
        else:
            # Use all enabled channels that match severity
            channels = [
                ch for ch in self.channels.values()
                if ch.is_enabled and alert.severity in ch.severity_filter
            ]
        
        for channel in channels:
            if not channel.can_send():
                logger.warning(f"Channel {channel.name} rate limited")
                continue
            
            notification = self._create_notification(alert, channel)
            
            success = self._send_notification(notification, channel)
            
            if success:
                notification.sent_at = datetime.utcnow()
                notification.delivered = True
                channel.record_send()
            else:
                notification.error_message = "Delivery failed"
            
            self.notification_history.append(notification)
            notifications.append(notification)
            
            # Call callbacks
            for callback in self._callbacks:
                try:
                    callback(notification)
                except Exception as e:
                    logger.error(f"Notification callback error: {e}")
        
        return notifications
    
    def _create_notification(self, alert: Alert, 
                             channel: NotificationChannel) -> Notification:
        """Create notification from alert"""
        subject = f"[{alert.severity.value.upper()}] {alert.rule_name}"
        
        body = f"""
Alert: {alert.rule_name}
Severity: {alert.severity.value}
Message: {alert.message}

Metric: {alert.metric_name}
Value: {alert.metric_value}
Threshold: {alert.threshold}

Started: {alert.started_at.isoformat()}
Labels: {alert.labels}
        """.strip()
        
        return Notification(
            alert_id=alert.alert_id,
            channel_id=channel.channel_id,
            channel_type=channel.channel_type,
            recipient=channel.config.get("recipient", ""),
            subject=subject,
            body=body,
            severity=alert.severity,
            metadata={
                "rule_id": alert.rule_id,
                "metric_name": alert.metric_name,
                "labels": alert.labels,
            },
        )
    
    def _send_notification(self, notification: Notification,
                           channel: NotificationChannel) -> bool:
        """Send notification via appropriate provider"""
        provider = self.providers.get(channel.channel_type)
        
        if not provider:
            logger.warning(f"No provider for {channel.channel_type.value}")
            return False
        
        try:
            return provider.send(notification)
        except Exception as e:
            logger.error(f"Send notification failed: {e}")
            return False
    
    def send_custom(self, channel_id: str, subject: str, body: str,
                    severity: AlertSeverity = AlertSeverity.INFO,
                    metadata: Dict[str, Any] = None) -> Optional[Notification]:
        """Send a custom notification (not alert-based)"""
        channel = self.channels.get(channel_id)
        if not channel:
            logger.warning(f"Channel not found: {channel_id}")
            return None
        
        if not channel.can_send():
            logger.warning(f"Channel {channel.name} rate limited")
            return None
        
        notification = Notification(
            channel_id=channel_id,
            channel_type=channel.channel_type,
            recipient=channel.config.get("recipient", ""),
            subject=subject,
            body=body,
            severity=severity,
            metadata=metadata or {},
        )
        
        success = self._send_notification(notification, channel)
        
        if success:
            notification.sent_at = datetime.utcnow()
            notification.delivered = True
            channel.record_send()
        
        self.notification_history.append(notification)
        return notification
    
    def get_in_app_notifications(self, recipient: str) -> List[Notification]:
        """Get in-app notifications for a recipient"""
        return [n for n in self._in_app_storage if n.recipient == recipient]
    
    def get_unread_count(self, recipient: str) -> int:
        """Get count of unread in-app notifications"""
        return len([n for n in self._in_app_storage 
                   if n.recipient == recipient and not n.delivered])
    
    def mark_notification_read(self, notification_id: str) -> bool:
        """Mark an in-app notification as read"""
        for n in self._in_app_storage:
            if n.notification_id == notification_id:
                n.delivered = True
                return True
        return False
    
    def get_history(self, limit: int = 100,
                    channel_type: Optional[NotificationChannelType] = None,
                    severity: Optional[AlertSeverity] = None) -> List[Notification]:
        """Get notification history with filters"""
        history = self.notification_history
        
        if channel_type:
            history = [n for n in history if n.channel_type == channel_type]
        if severity:
            history = [n for n in history if n.severity == severity]
        
        return sorted(history, key=lambda n: n.created_at, reverse=True)[:limit]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get notification statistics"""
        total = len(self.notification_history)
        delivered = len([n for n in self.notification_history if n.delivered])
        failed = len([n for n in self.notification_history if n.error_message])
        
        by_channel = {}
        for n in self.notification_history:
            ct = n.channel_type.value
            if ct not in by_channel:
                by_channel[ct] = {"total": 0, "delivered": 0}
            by_channel[ct]["total"] += 1
            if n.delivered:
                by_channel[ct]["delivered"] += 1
        
        by_severity = {}
        for n in self.notification_history:
            sev = n.severity.value
            by_severity[sev] = by_severity.get(sev, 0) + 1
        
        return {
            "total": total,
            "delivered": delivered,
            "failed": failed,
            "delivery_rate": delivered / total if total > 0 else 0,
            "by_channel": by_channel,
            "by_severity": by_severity,
            "active_channels": len([c for c in self.channels.values() if c.is_enabled]),
        }


def create_default_notification_service() -> NotificationService:
    """Create notification service with default channels"""
    service = NotificationService()
    
    # Add default in-app channel
    service.add_channel(NotificationChannel(
        channel_id="in-app-default",
        name="In-App Notifications",
        channel_type=NotificationChannelType.IN_APP,
        severity_filter=[AlertSeverity.INFO, AlertSeverity.WARNING, 
                        AlertSeverity.ERROR, AlertSeverity.CRITICAL],
    ))
    
    return service
