"""
WebSocket Endpoints for Real-Time Dashboard Updates

Provides real-time streaming of:
- Telemetry updates
- Alert notifications
- Approval queue changes
- Fleet status updates
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set
from dataclasses import dataclass, field

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

logger = logging.getLogger(__name__)

router = APIRouter()

# ── Heartbeat configuration ─────────────────────────────────────────
HEARTBEAT_INTERVAL_S = 30      # Server sends ping every N seconds
HEARTBEAT_TIMEOUT_S = 10       # Max wait for pong after ping
MAX_MISSED_HEARTBEATS = 3      # Disconnect after N missed pongs


@dataclass
class ConnectionMeta:
    """Per-connection metadata for heartbeat tracking."""
    channel: str
    connected_at: float = field(default_factory=time.time)
    last_pong_at: float = field(default_factory=time.time)
    missed_heartbeats: int = 0


@dataclass
class ConnectionManager:
    """Manages WebSocket connections for real-time updates"""
    
    active_connections: Dict[str, Set[WebSocket]] = field(default_factory=dict)
    operator_connections: Set[WebSocket] = field(default_factory=set)
    _meta: Dict[int, ConnectionMeta] = field(default_factory=dict)
    
    async def connect(self, websocket: WebSocket, channel: str = "operator"):
        """Accept and register a new WebSocket connection"""
        await websocket.accept()
        
        if channel == "operator":
            self.operator_connections.add(websocket)
        else:
            if channel not in self.active_connections:
                self.active_connections[channel] = set()
            self.active_connections[channel].add(websocket)
        
        self._meta[id(websocket)] = ConnectionMeta(channel=channel)
        logger.info(f"WebSocket connected to channel: {channel}")
    
    def disconnect(self, websocket: WebSocket, channel: str = "operator"):
        """Remove a WebSocket connection"""
        if channel == "operator":
            self.operator_connections.discard(websocket)
        elif channel in self.active_connections:
            self.active_connections[channel].discard(websocket)
        
        self._meta.pop(id(websocket), None)
        logger.info(f"WebSocket disconnected from channel: {channel}")
    
    def record_pong(self, websocket: WebSocket):
        """Record that a pong was received."""
        meta = self._meta.get(id(websocket))
        if meta:
            meta.last_pong_at = time.time()
            meta.missed_heartbeats = 0

    def record_missed(self, websocket: WebSocket) -> int:
        """Record a missed heartbeat. Returns new missed count."""
        meta = self._meta.get(id(websocket))
        if meta:
            meta.missed_heartbeats += 1
            return meta.missed_heartbeats
        return 0

    def get_connection_count(self) -> Dict[str, int]:
        """Return connection counts by channel."""
        counts: Dict[str, int] = {"operator": len(self.operator_connections)}
        for ch, conns in self.active_connections.items():
            counts[ch] = len(conns)
        return counts

    async def broadcast_to_channel(self, channel: str, message: dict):
        """Broadcast message to all connections on a channel"""
        connections = self.active_connections.get(channel, set())
        disconnected = set()
        
        for connection in connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.add(connection)
        
        for conn in disconnected:
            self.active_connections[channel].discard(conn)
    
    async def broadcast_to_operators(self, message: dict):
        """Broadcast message to all operator dashboard connections"""
        disconnected = set()
        
        for connection in self.operator_connections:
            try:
                await connection.send_json(message)
            except Exception as e:
                logger.warning(f"Failed to send to operator WebSocket: {e}")
                disconnected.add(connection)
        
        for conn in disconnected:
            self.operator_connections.discard(conn)
    
    async def send_to_asset(self, asset_id: str, message: dict):
        """Send message to connections watching a specific asset"""
        channel = f"asset:{asset_id}"
        await self.broadcast_to_channel(channel, message)
        await self.broadcast_to_operators(message)


manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager"""
    return manager


async def _heartbeat_loop(websocket: WebSocket, channel: str):
    """Server-side heartbeat: send ping, expect pong within timeout.

    Protocol:
    - Server sends ``{"type": "ping"}`` every ``HEARTBEAT_INTERVAL_S`` seconds.
    - Client must reply ``{"type": "pong"}`` within ``HEARTBEAT_TIMEOUT_S``.
    - After ``MAX_MISSED_HEARTBEATS`` consecutive misses, connection is closed.

    Reconnection guidance (sent in the ``connected`` message):
    - Clients should implement exponential backoff starting at 1 s.
    - Include ``last_event_ts`` query param on reconnect to receive missed events.
    """
    try:
        while True:
            await asyncio.sleep(HEARTBEAT_INTERVAL_S)
            try:
                await websocket.send_json({
                    "type": "ping",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            except Exception:
                break
    except asyncio.CancelledError:
        pass


async def _ws_message_loop(websocket: WebSocket, channel: str):
    """Shared message handling loop with heartbeat tracking."""
    while True:
        try:
            data = await asyncio.wait_for(
                websocket.receive_text(),
                timeout=float(HEARTBEAT_INTERVAL_S + HEARTBEAT_TIMEOUT_S),
            )
            message = json.loads(data)

            msg_type = message.get("type")
            if msg_type == "pong":
                manager.record_pong(websocket)
            elif msg_type == "ping":
                await websocket.send_json({
                    "type": "pong",
                    "timestamp": datetime.utcnow().isoformat(),
                })
            elif msg_type == "subscribe":
                sub_channel = message.get("channel")
                if sub_channel:
                    if sub_channel not in manager.active_connections:
                        manager.active_connections[sub_channel] = set()
                    manager.active_connections[sub_channel].add(websocket)
                    await websocket.send_json({"type": "subscribed", "channel": sub_channel})

        except asyncio.TimeoutError:
            missed = manager.record_missed(websocket)
            if missed >= MAX_MISSED_HEARTBEATS:
                logger.warning("WebSocket %s missed %d heartbeats — disconnecting", channel, missed)
                await websocket.close(code=4000, reason="heartbeat_timeout")
                return
            # Send another ping to probe the connection
            try:
                await websocket.send_json({"type": "ping", "timestamp": datetime.utcnow().isoformat()})
            except Exception:
                return


@router.websocket("/ws/operator")
async def operator_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for operator dashboard.
    
    Receives all system-wide updates:
    - New alerts
    - Approval queue changes
    - Fleet status updates
    """
    await manager.connect(websocket, "operator")
    
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to operator dashboard stream",
            "timestamp": datetime.utcnow().isoformat(),
            "heartbeat": {
                "interval_s": HEARTBEAT_INTERVAL_S,
                "timeout_s": HEARTBEAT_TIMEOUT_S,
                "max_missed": MAX_MISSED_HEARTBEATS,
                "protocol": "Send {type:'pong'} in response to {type:'ping'}. "
                            "Reconnect with exponential backoff (1s, 2s, 4s, ..., max 30s).",
            },
        })

        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, "operator"))
        try:
            await _ws_message_loop(websocket, "operator")
        finally:
            heartbeat_task.cancel()
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, "operator")
    except Exception as e:
        logger.error(f"Operator WebSocket error: {e}")
        manager.disconnect(websocket, "operator")


@router.websocket("/ws/dashboard/{asset_id}")
async def asset_dashboard_websocket(
    websocket: WebSocket,
    asset_id: str,
):
    """
    WebSocket endpoint for asset-specific dashboard updates.
    
    Streams:
    - Telemetry updates for the asset
    - Alert updates
    - RUL estimates
    """
    channel = f"asset:{asset_id}"
    await manager.connect(websocket, channel)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "asset_id": asset_id,
            "message": f"Connected to dashboard stream for {asset_id}",
            "timestamp": datetime.utcnow().isoformat(),
            "heartbeat": {
                "interval_s": HEARTBEAT_INTERVAL_S,
                "timeout_s": HEARTBEAT_TIMEOUT_S,
                "max_missed": MAX_MISSED_HEARTBEATS,
            },
        })

        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, channel))
        try:
            await _ws_message_loop(websocket, channel)
        finally:
            heartbeat_task.cancel()
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error(f"Asset dashboard WebSocket error: {e}")
        manager.disconnect(websocket, channel)


@router.websocket("/ws/approvals")
async def approvals_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for approval queue updates.
    
    Streams:
    - New approval items
    - Status changes
    - Decision notifications
    """
    channel = "approvals"
    await manager.connect(websocket, channel)
    
    try:
        await websocket.send_json({
            "type": "connected",
            "message": "Connected to approval queue stream",
            "timestamp": datetime.utcnow().isoformat(),
            "heartbeat": {
                "interval_s": HEARTBEAT_INTERVAL_S,
                "timeout_s": HEARTBEAT_TIMEOUT_S,
                "max_missed": MAX_MISSED_HEARTBEATS,
            },
        })

        heartbeat_task = asyncio.create_task(_heartbeat_loop(websocket, channel))
        try:
            await _ws_message_loop(websocket, channel)
        finally:
            heartbeat_task.cancel()
                
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)
    except Exception as e:
        logger.error(f"Approvals WebSocket error: {e}")
        manager.disconnect(websocket, channel)


async def broadcast_telemetry_update(asset_id: str, telemetry: dict):
    """Broadcast telemetry update to relevant WebSocket clients"""
    message = {
        "type": "telemetry_update",
        "asset_id": asset_id,
        "telemetry": telemetry,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.send_to_asset(asset_id, message)


async def broadcast_alert(alert: dict):
    """Broadcast new or updated alert to WebSocket clients"""
    message = {
        "type": "alert_new" if alert.get("is_new") else "alert_update",
        "alert": alert,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.send_to_asset(alert.get("asset_id", ""), message)


async def broadcast_rul_update(asset_id: str, rul: dict):
    """Broadcast RUL estimate update"""
    message = {
        "type": "rul_update",
        "asset_id": asset_id,
        "rul": rul,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.send_to_asset(asset_id, message)


async def broadcast_approval_update(item: dict, event_type: str = "update"):
    """Broadcast approval queue update"""
    message = {
        "type": f"approval_{event_type}",
        "item_id": item.get("item_id") or item.get("approval_id"),
        "item": item if event_type == "added" else None,
        "update": item if event_type == "update" else None,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast_to_channel("approvals", message)
    await manager.broadcast_to_operators(message)


async def broadcast_fleet_update(metrics: dict):
    """Broadcast fleet-wide metrics update"""
    message = {
        "type": "fleet_metrics",
        "metrics": metrics,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast_to_operators(message)


async def broadcast_notification(title: str, body: str, severity: str = "info"):
    """Broadcast notification to all operator dashboards"""
    message = {
        "type": "notification",
        "title": title,
        "body": body,
        "severity": severity,
        "timestamp": datetime.utcnow().isoformat(),
    }
    await manager.broadcast_to_operators(message)
