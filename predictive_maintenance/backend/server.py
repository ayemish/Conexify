"""
PdM Backend Server — Standalone FastAPI application for the Operator Dashboard.

Serves all /api/v1/* endpoints with realistic HVAC/R demo data.
Includes WebSocket support for real-time operator updates.

Run:
    python -m predictive_maintenance.backend.server

Or:
    uvicorn predictive_maintenance.backend.server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s")
logger = logging.getLogger("pdm.backend")

# ═══════════════════════════════════════════════════════════════════════
# Data Generation
# ═══════════════════════════════════════════════════════════════════════

FAULT_TYPES = [
    "refrigerant_leak", "condenser_fouling", "compressor_degradation",
    "sensor_drift", "fan_bearing_wear", "valve_stuck", "filter_clogged",
]
REGIMES = ["cooling_steady", "cooling_transient", "heating_steady", "off_idle"]
ASSET_TYPES = ["hvac_rtu", "hvac_ahu", "chiller", "fcu", "cooling_tower"]
MANUFACTURERS = ["Carrier", "Trane", "Daikin", "Lennox", "York"]
SEVERITIES = ["low", "medium", "high", "critical"]
ALERT_TYPES = ["watch", "actionable", "dispatch", "sensor_integrity", "human_review"]
RISK_TIERS = ["Low", "Medium", "High", "Extreme"]

_rng = random.Random(42)


def _rb(lo: float, hi: float) -> float:
    return lo + _rng.random() * (hi - lo)


def _pick(seq):
    return seq[_rng.randint(0, len(seq) - 1)]


def _asset_id(i: int) -> str:
    prefixes = ["RTU", "AHU", "CHL", "FCU", "CT"]
    return f"{prefixes[i % len(prefixes)]}-{str(i + 1).zfill(3)}"


def _health_band(score: float) -> str:
    if score >= 80:
        return "healthy"
    if score >= 60:
        return "monitoring"
    if score >= 40:
        return "alert"
    if score >= 20:
        return "action"
    return "critical"


# ── Fleet ────────────────────────────────────────────────────────────

def generate_fleet(n: int = 12) -> List[Dict[str, Any]]:
    assets = []
    for i in range(n):
        hs = _rb(25, 98)
        band = _health_band(hs)
        has_fault = hs < 65
        rul = _rb(2000, 8000) if hs > 70 else _rb(50, 1500)
        st = _rb(0.7, 1.0)
        cs = _rb(0.5, 1.0)
        fp = _rb(0.1, 0.9 if has_fault else 0.3)
        deg = 1.0 - hs / 100

        assets.append({
            "asset_id": _asset_id(i),
            "location_id": f"LOC-{100 + i}",
            "asset_type": ASSET_TYPES[i % len(ASSET_TYPES)],
            "manufacturer": MANUFACTURERS[i % len(MANUFACTURERS)],
            "model": f"Model-{chr(65 + i)}",
            "status": "normal" if band == "healthy" else ("watching" if band == "monitoring" else "action_required"),
            "regime": _pick(REGIMES),
            "hours_monitored": round(_rb(500, 12000)),
            # Top-level for FleetOverview
            "health_score": round(hs, 1),
            "rul_hours": round(rul),
            "sensor_trust": round(st, 2),
            # Nested for PdmDashboard / AssetDetail
            "health": {
                "health_score": round(hs, 1),
                "health_band": band,
                "sensor_trust_score": round(st * 100),
                "change_detection_score": round(cs * 100),
                "fault_probability_score": round(fp * 100),
                "rul_score": round(rul / 8000 * 100),
                "degradation_score": round(deg * 100),
                "score_trend": round(_rb(-0.5, 0.3), 3),
                "pf_position": round(_rb(0.05, min(0.95, deg + 0.1)), 3),
                "confidence": round(_rb(0.7, 0.95), 3),
            },
            "rul": {
                "rul_hours": round(rul),
                "confidence": round(_rb(0.6, 0.92), 3),
                "degradation_index": round(deg, 3),
                "model_agreement": round(_rb(0.7, 0.98), 3),
                "fault_type": _pick(FAULT_TYPES) if has_fault else None,
            },
            "primary_fault": _pick(FAULT_TYPES) if has_fault else None,
            "confidence": round(_rb(0.5, 0.9), 3) if has_fault else None,
            "false_alarm_prob": round(_rb(0.02, 0.15), 3) if has_fault else None,
            "recommended_action": _pick([
                "Schedule inspection within 48h",
                "Dispatch technician",
                "Monitor closely for 24h",
                "Replace filter immediately",
            ]) if has_fault else None,
            "sensor_health": f"{_rng.randint(8, 12)}/12 sensors trusted",
            "active_alert": {
                "alert_type": _pick(["watch", "actionable"]),
                "primary_fault": _pick(FAULT_TYPES),
                "confidence": round(_rb(0.5, 0.9), 3),
                "false_alarm_prob": round(_rb(0.02, 0.15), 3),
                "recommended_action": "Schedule inspection",
                "timestamp": (datetime.utcnow() - timedelta(hours=_rb(0, 24))).isoformat() + "Z",
            } if has_fault else None,
        })
    return assets


# ── Incidents ────────────────────────────────────────────────────────

def generate_incidents(fleet: List[Dict]) -> List[Dict[str, Any]]:
    items = []
    for i in range(_rng.randint(3, 8)):
        items.append({
            "incident_id": f"INC-2025{str(i + 1).zfill(4)}",
            "severity": _pick(SEVERITIES),
            "fault_type": _pick(FAULT_TYPES),
            "status": _pick(["open", "investigating", "mitigating", "resolved"]),
            "asset_id": _pick(fleet)["asset_id"],
            "created_at": (datetime.utcnow() - timedelta(days=_rb(0, 7))).isoformat() + "Z",
            "description": _pick([
                "Abnormal discharge pressure trending upward",
                "Superheat exceeding threshold for 4 hours",
                "Compressor current draw 18% above baseline",
                "Return air sensor drift detected",
                "Condenser fan vibration alarm",
            ]),
        })
    return items


# ── Approvals ────────────────────────────────────────────────────────

def generate_approvals(fleet: List[Dict]) -> List[Dict[str, Any]]:
    items = []
    for i in range(_rng.randint(2, 6)):
        risk = _pick(RISK_TIERS)
        items.append({
            "approval_id": f"APR-2025{str(i + 1).zfill(4)}",
            "item_id": f"APR-2025{str(i + 1).zfill(4)}",
            "risk_tier": risk,
            "status": "pending" if i == 0 else _pick(["pending", "approved", "rejected"]),
            "action_summary": _pick([
                "Reduce compressor speed by 15% on RTU-003",
                "Schedule condenser coil cleaning for AHU-002",
                "Switch to backup sensor array on CHL-001",
                "Increase supply fan speed to compensate for filter restriction",
                "Initiate controlled shutdown sequence for CT-001",
            ]),
            "step_id": f"STEP-{i + 1}",
            "asset_id": _pick(fleet)["asset_id"],
            "created_at": (datetime.utcnow() - timedelta(days=_rb(0, 3))).isoformat() + "Z",
            "explanation": {
                "summary": "AI-generated recommendation based on trend analysis",
                "rationale": "Telemetry indicates progressive degradation pattern consistent with the identified fault mode.",
                "risk_assessment": f"Risk tier: {risk}. Estimated impact: moderate energy savings improvement.",
            },
            "validation": {
                "passed": True,
                "checks": [
                    {"name": "Safety bounds", "passed": True},
                    {"name": "Rate of change", "passed": True},
                    {"name": "Sensor agreement", "passed": risk != "Extreme"},
                ],
            },
            "proposed_actions": [
                {"action_type": "setpoint_change", "point_id": f"{_asset_id(i)}.SP", "value": _rng.randint(68, 76)},
                {"action_type": "mode_switch", "point_id": f"{_asset_id(i)}.MODE", "value": "economy"},
            ],
            "telemetry_snapshot": {
                "suction_pressure": round(_rb(90, 130), 1),
                "discharge_pressure": round(_rb(340, 420), 1),
                "superheat": round(_rb(6, 18), 1),
                "subcool": round(_rb(4, 12), 1),
            },
        })
    return items


# ── Alerts ───────────────────────────────────────────────────────────

def generate_alerts(fleet: List[Dict]) -> List[Dict[str, Any]]:
    items = []
    for i in range(_rng.randint(4, 10)):
        items.append({
            "alert_id": f"ALT-2025{str(i + 1).zfill(4)}",
            "alert_type": _pick(ALERT_TYPES),
            "status": _pick(["active", "active", "active", "acknowledged", "resolved"]),
            "asset_id": _pick(fleet)["asset_id"],
            "primary_fault": _pick(FAULT_TYPES),
            "confidence": round(_rb(0.4, 0.95), 3),
            "false_alarm_probability": round(_rb(0.01, 0.2), 3),
            "severity": _pick(SEVERITIES),
            "recommended_action": _pick([
                "Monitor for next 24 hours",
                "Schedule technician visit",
                "Dispatch emergency repair",
                "Verify sensor calibration",
                "Review with engineering team",
            ]),
            "evidence": [
                "Suction pressure 12% below baseline",
                "Superheat trending upward over 6 hours",
                "Compressor current exceeds 95th percentile",
            ],
            "fault_distribution": {
                "refrigerant_leak": round(_rb(0, 0.5), 3),
                "condenser_fouling": round(_rb(0, 0.3), 3),
                "compressor_degradation": round(_rb(0, 0.2), 3),
                "normal_operation": round(_rb(0.1, 0.4), 3),
            },
            "created_at": (datetime.utcnow() - timedelta(hours=_rb(0, 48))).isoformat() + "Z",
        })
    return items


# ═══════════════════════════════════════════════════════════════════════
# In-Memory Store
# ═══════════════════════════════════════════════════════════════════════

class DemoStore:
    """In-memory store for demo data. Regenerates every 30s for variation."""

    def __init__(self):
        self.fleet: List[Dict] = []
        self.incidents: List[Dict] = []
        self.approvals: List[Dict] = []
        self.alerts: List[Dict] = []
        self._last_refresh = 0.0
        self.refresh()

    def refresh(self, force: bool = False):
        now = time.time()
        if not force and now - self._last_refresh < 30:
            return
        self.fleet = generate_fleet()
        self.incidents = generate_incidents(self.fleet)
        self.approvals = generate_approvals(self.fleet)
        self.alerts = generate_alerts(self.fleet)
        self._last_refresh = now
        logger.info("Demo data refreshed — %d assets, %d alerts, %d approvals, %d incidents",
                     len(self.fleet), len(self.alerts), len(self.approvals), len(self.incidents))

    def fleet_metrics(self) -> Dict[str, Any]:
        self.refresh()
        avg_rul = sum(a.get("rul_hours", 0) for a in self.fleet) / max(len(self.fleet), 1)
        degrading = sum(1 for a in self.fleet if (a.get("health_score") or 100) < 60)
        open_inc = sum(1 for i in self.incidents if i["status"] != "resolved")
        return {
            "avg_rul_hours": round(avg_rul),
            "degrading_count": degrading,
            "open_incidents": open_inc,
            "total_assets": len(self.fleet),
        }

    def approval_stats(self) -> Dict[str, Any]:
        self.refresh()
        return {
            "total": len(self.approvals),
            "pending": sum(1 for i in self.approvals if i["status"] == "pending"),
            "approved": sum(1 for i in self.approvals if i["status"] == "approved"),
            "rejected": sum(1 for i in self.approvals if i["status"] == "rejected"),
            "avg_time_to_decision_minutes": _rng.randint(5, 45),
        }


store = DemoStore()


# ═══════════════════════════════════════════════════════════════════════
# WebSocket Manager
# ═══════════════════════════════════════════════════════════════════════

class ConnectionManager:
    def __init__(self):
        self.operator_connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.operator_connections.add(ws)
        logger.info("Operator WS connected (%d total)", len(self.operator_connections))

    def disconnect(self, ws: WebSocket):
        self.operator_connections.discard(ws)
        logger.info("Operator WS disconnected (%d total)", len(self.operator_connections))

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.operator_connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.operator_connections.discard(ws)


ws_manager = ConnectionManager()


# ═══════════════════════════════════════════════════════════════════════
# Background Task: Simulate Live Updates
# ═══════════════════════════════════════════════════════════════════════

async def live_update_loop():
    """Push simulated updates to WebSocket clients every 10 seconds."""
    while True:
        await asyncio.sleep(10)
        if not ws_manager.operator_connections:
            continue

        store.refresh()

        # Pick a random asset and nudge its health score slightly
        if store.fleet:
            asset = random.choice(store.fleet)
            delta = random.uniform(-1.5, 0.8)
            asset["health_score"] = max(5, min(99, asset["health_score"] + delta))
            asset["health"]["health_score"] = asset["health_score"]
            asset["health"]["health_band"] = _health_band(asset["health_score"])

            await ws_manager.broadcast({
                "type": "asset_update",
                "asset_id": asset["asset_id"],
                "update": {
                    "health_score": asset["health_score"],
                    "health": asset["health"],
                },
            })

        # Occasionally send a notification
        if random.random() < 0.2:
            await ws_manager.broadcast({
                "type": "notification",
                "title": "System Update",
                "body": random.choice([
                    "Sensor calibration completed for RTU-003",
                    "New approval item pending review",
                    "AHU-002 health trending downward",
                    "Condenser fouling alert resolved on CHL-001",
                ]),
                "severity": random.choice(["info", "warning"]),
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })


# ═══════════════════════════════════════════════════════════════════════
# FastAPI App
# ═══════════════════════════════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("PdM Backend starting...")
    store.refresh(force=True)
    task = asyncio.create_task(live_update_loop())
    yield
    task.cancel()
    logger.info("PdM Backend shutting down.")


app = FastAPI(
    title="PdM Operator Backend",
    description="Standalone backend for the PdM Operator Dashboard with demo data",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Health ───────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "healthy", "version": "1.0.0", "timestamp": datetime.utcnow().isoformat()}


# ── Fleet ────────────────────────────────────────────────────────────

@app.get("/api/v1/fleet/assets")
async def fleet_assets():
    store.refresh()
    return {"assets": store.fleet}


@app.get("/api/v1/fleet/metrics")
async def fleet_metrics():
    return store.fleet_metrics()


@app.get("/api/v1/fleet/asset/{asset_id}")
async def fleet_asset_detail(asset_id: str):
    store.refresh()
    asset = next((a for a in store.fleet if a["asset_id"] == asset_id), None)
    if not asset:
        return {"error": "Asset not found"}, 404
    return asset


# ── Dashboard (legacy PdmDashboard) ─────────────────────────────────

@app.get("/api/v1/dashboard")
async def dashboard():
    store.refresh()
    return store.fleet[0] if store.fleet else {}


# ── Incidents ────────────────────────────────────────────────────────

@app.get("/api/v1/autopilot/incidents")
async def incidents(limit: int = Query(50, ge=1, le=200)):
    store.refresh()
    return {"incidents": store.incidents[:limit]}


# ── Approval Queue ───────────────────────────────────────────────────

@app.get("/api/v1/approval-queue")
async def approval_queue(status: Optional[str] = None):
    store.refresh()
    items = store.approvals
    if status and status != "all":
        items = [i for i in items if i["status"] == status]
    return {"items": items}


@app.get("/api/v1/approval-queue/items")
async def approval_queue_items(limit: int = Query(50, ge=1, le=200)):
    store.refresh()
    return {"items": store.approvals[:limit]}


@app.get("/api/v1/approval-queue/stats")
async def approval_queue_stats():
    return store.approval_stats()


@app.post("/api/v1/approval-queue/{item_id}/approve")
async def approve_item(item_id: str):
    for item in store.approvals:
        if item["item_id"] == item_id or item["approval_id"] == item_id:
            item["status"] = "approved"
            await ws_manager.broadcast({
                "type": "approval_update",
                "item_id": item_id,
                "update": {"status": "approved"},
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
            return {"success": True, "status": "approved"}
    return {"success": False, "error": "Item not found"}


@app.post("/api/v1/approval-queue/{item_id}/reject")
async def reject_item(item_id: str):
    for item in store.approvals:
        if item["item_id"] == item_id or item["approval_id"] == item_id:
            item["status"] = "rejected"
            await ws_manager.broadcast({
                "type": "approval_update",
                "item_id": item_id,
                "update": {"status": "rejected"},
                "timestamp": datetime.utcnow().isoformat() + "Z",
            })
            return {"success": True, "status": "rejected"}
    return {"success": False, "error": "Item not found"}


# ── Alerts ───────────────────────────────────────────────────────────

@app.get("/api/v1/alerts")
async def alerts(
    asset_id: Optional[str] = None,
    active: Optional[bool] = None,
):
    store.refresh()
    items = store.alerts
    if asset_id:
        items = [a for a in items if a["asset_id"] == asset_id]
    if active:
        items = [a for a in items if a["status"] not in ("resolved", "dismissed", "suppressed")]
    return {"alerts": items}


@app.post("/api/v1/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: str):
    for a in store.alerts:
        if a["alert_id"] == alert_id:
            a["status"] = "acknowledged"
            return {"success": True, "status": "acknowledged"}
    return {"success": False, "error": "Alert not found"}


@app.post("/api/v1/alerts/{alert_id}/dismiss")
async def dismiss_alert(alert_id: str):
    for a in store.alerts:
        if a["alert_id"] == alert_id:
            a["status"] = "dismissed"
            return {"success": True, "status": "dismissed"}
    return {"success": False, "error": "Alert not found"}


@app.post("/api/v1/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str):
    for a in store.alerts:
        if a["alert_id"] == alert_id:
            a["status"] = "resolved"
            return {"success": True, "status": "resolved"}
    return {"success": False, "error": "Alert not found"}


# ── Feedback ─────────────────────────────────────────────────────────

@app.post("/api/v1/feedback")
async def submit_feedback():
    return {"success": True, "message": "Feedback recorded"}


# ── WebSocket ────────────────────────────────────────────────────────

@app.websocket("/api/v1/ws/operator")
async def operator_websocket(ws: WebSocket):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({
            "type": "connected",
            "message": "Connected to operator dashboard stream",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat() + "Z"})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "timestamp": datetime.utcnow().isoformat() + "Z"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.error("Operator WS error: %s", e)
        ws_manager.disconnect(ws)


@app.websocket("/api/v1/ws/dashboard/{asset_id}")
async def asset_dashboard_websocket(ws: WebSocket, asset_id: str):
    await ws_manager.connect(ws)
    try:
        await ws.send_json({
            "type": "connected",
            "asset_id": asset_id,
            "message": f"Connected to dashboard stream for {asset_id}",
            "timestamp": datetime.utcnow().isoformat() + "Z",
        })
        while True:
            try:
                data = await asyncio.wait_for(ws.receive_text(), timeout=30.0)
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await ws.send_json({"type": "pong", "timestamp": datetime.utcnow().isoformat() + "Z"})
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping", "timestamp": datetime.utcnow().isoformat() + "Z"})
    except WebSocketDisconnect:
        ws_manager.disconnect(ws)
    except Exception as e:
        logger.error("Asset WS error for %s: %s", asset_id, e)
        ws_manager.disconnect(ws)


# ═══════════════════════════════════════════════════════════════════════
# Entry Point
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "predictive_maintenance.backend.server:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
