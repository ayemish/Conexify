"""
PDM API Schemas

Pydantic models for API request/response validation.
"""

from datetime import datetime
from typing import Dict, List, Optional, Any
from pydantic import BaseModel, Field, validator


# =============================================================================
# Health Check
# =============================================================================

class HealthResponse(BaseModel):
    """Health check response"""
    status: str = Field(..., description="Overall health status")
    version: str = Field(..., description="API version")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    checks: Dict[str, bool] = Field(default_factory=dict, description="Individual health checks")


class ReadyResponse(BaseModel):
    """Readiness check response"""
    ready: bool
    database: bool
    redis: bool
    message: str = ""


# =============================================================================
# Telemetry
# =============================================================================

class TelemetryRequest(BaseModel):
    """Single telemetry reading request"""
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    asset_id: str = Field(..., min_length=1, max_length=100)
    site_id: Optional[str] = Field(None, max_length=100)
    
    # Operating state
    compressor_on: bool = False
    compressor_current: Optional[float] = Field(None, ge=0)
    compressor_power: Optional[float] = Field(None, ge=0)
    evap_fan_on: bool = False
    condenser_fan_on: bool = False
    supply_fan_speed: Optional[float] = Field(None, ge=0, le=100)
    
    # Temperatures (Fahrenheit)
    suction_line_temp: Optional[float] = Field(None, ge=-50, le=200)
    discharge_temp: Optional[float] = Field(None, ge=-50, le=300)
    supply_air_temp: Optional[float] = Field(None, ge=-50, le=150)
    return_air_temp: Optional[float] = Field(None, ge=-50, le=150)
    ambient_temp: Optional[float] = Field(None, ge=-50, le=150)
    ambient_humidity: Optional[float] = Field(None, ge=0, le=100)
    ambient_pressure: Optional[float] = Field(None, ge=800, le=1200)
    zone_temp: Optional[float] = Field(None, ge=-50, le=150)
    
    # Pressures (PSIG)
    suction_pressure: Optional[float] = Field(None, ge=-15, le=500)
    discharge_pressure: Optional[float] = Field(None, ge=-15, le=800)
    
    # Calculated values
    superheat: Optional[float] = None
    subcool: Optional[float] = None
    
    # Control state
    setpoint: Optional[float] = None
    cooling_valve_pct: Optional[float] = Field(None, ge=0, le=100)
    heating_valve_pct: Optional[float] = Field(None, ge=0, le=100)
    damper_position_pct: Optional[float] = Field(None, ge=0, le=100)
    reversing_valve_heat: bool = False

    # Context (optional)
    occupancy_fraction: Optional[float] = Field(None, ge=0, le=1)
    energy_price: Optional[float] = Field(None, ge=0)
    
    # Extra data
    extra_data: Optional[Dict[str, Any]] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "timestamp": "2024-01-15T14:30:00Z",
                "asset_id": "RTU_001",
                "site_id": "site_001",
                "compressor_on": True,
                "compressor_current": 15.2,
                "suction_pressure": 68.0,
                "discharge_pressure": 275.0,
                "supply_air_temp": 55.0,
                "return_air_temp": 75.0,
                "ambient_temp": 95.0,
            }]
        }
    }


class TelemetryBatchRequest(BaseModel):
    """Batch telemetry request"""
    readings: List[TelemetryRequest] = Field(..., min_items=1, max_items=1000)


class TelemetryResponse(BaseModel):
    """Telemetry processing response"""
    asset_id: str
    timestamp: datetime
    regime: str
    regime_confidence: float
    sensor_trust_summary: Dict[str, float] = Field(default_factory=dict)
    alert: Optional["AlertResponse"] = None
    processed: bool = True
    message: str = ""


# =============================================================================
# Alerts
# =============================================================================

class AlertResponse(BaseModel):
    """Alert information"""
    alert_id: str
    asset_id: str
    alert_type: str  # sensor_integrity, watch, actionable
    severity: str  # info, low, medium, high, critical
    
    confidence: float = Field(..., ge=0, le=1)
    false_alarm_probability: float = Field(..., ge=0, le=1)
    
    primary_fault: Optional[str] = None
    secondary_fault: Optional[str] = None
    fault_beliefs: Dict[str, float] = Field(default_factory=dict)
    
    evidence_summary: List[str] = Field(default_factory=list)
    recommended_action: str = ""
    action_urgency: str = "monitor"
    
    regime_at_detection: str = "unknown"
    ambient_temp_at_detection: Optional[float] = None
    
    status: str = "active"
    created_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "alert_id": "ALT_12345678",
                "asset_id": "RTU_001",
                "alert_type": "actionable",
                "severity": "high",
                "confidence": 0.87,
                "false_alarm_probability": 0.08,
                "primary_fault": "refrigerant_leak",
                "evidence_summary": [
                    "Elevated superheat (18°F vs expected 12°F)",
                    "Low suction pressure trend over 48 hours"
                ],
                "recommended_action": "Check refrigerant charge and inspect for leaks",
                "action_urgency": "schedule",
                "created_at": "2024-01-15T14:30:00Z",
                "status": "active"
            }]
        }
    }


class AlertListResponse(BaseModel):
    """List of alerts"""
    alerts: List[AlertResponse]
    total: int
    page: int = 1
    page_size: int = 50


class AlertAcknowledgeRequest(BaseModel):
    """Acknowledge alert request"""
    acknowledged_by: str = Field(default="operator_ui", min_length=1, max_length=100)
    notes: Optional[str] = None


class AlertDismissRequest(BaseModel):
    """Dismiss/suppress alert request"""
    dismissed_by: str = Field(default="operator_ui", min_length=1, max_length=100)
    notes: str = ""


class AlertResolveRequest(BaseModel):
    """Resolve alert request"""
    resolved_by: str = Field(..., min_length=1, max_length=100)
    resolution_notes: str = ""


# =============================================================================
# Feedback
# =============================================================================

class FeedbackRequest(BaseModel):
    """Feedback submission request"""
    alert_id: str = Field(..., min_length=1)
    outcome: str = Field(..., pattern="^(confirmed_fault|no_issue_found|sensor_problem|pending)$")
    confirmed_fault_type: Optional[str] = None
    notes: str = ""
    feedback_by: Optional[str] = None
    
    model_config = {
        "json_schema_extra": {
            "examples": [{
                "alert_id": "ALT_12345678",
                "outcome": "confirmed_fault",
                "confirmed_fault_type": "refrigerant_leak",
                "notes": "Found 2lb low on R-410A, recharged",
                "feedback_by": "tech_john"
            }]
        }
    }


class AlertFeedbackQuickRequest(BaseModel):
    """Backward-compatible alert feedback payload for /alerts/{id}/feedback"""
    helpful: Optional[bool] = None
    outcome: Optional[str] = Field(None, pattern="^(confirmed_fault|no_issue_found|sensor_problem|pending)$")
    confirmed_fault_type: Optional[str] = None
    notes: str = ""
    feedback_by: Optional[str] = None


class FeedbackResponse(BaseModel):
    """Feedback submission response"""
    feedback_id: str
    alert_id: str
    outcome: str
    recorded_at: datetime


# =============================================================================
# Assets
# =============================================================================

class AssetRequest(BaseModel):
    """Asset creation/update request"""
    asset_id: str = Field(..., min_length=1, max_length=100)
    site_id: str = Field(..., min_length=1, max_length=100)
    asset_type: str = "hvac_rtu"
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    serial_number: Optional[str] = None
    install_date: Optional[datetime] = None
    refrigerant_type: Optional[str] = None
    nominal_capacity_tons: Optional[float] = None


class AssetResponse(BaseModel):
    """Asset information"""
    asset_id: str
    site_id: str
    asset_type: str
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None
    is_active: bool = True
    last_telemetry_at: Optional[datetime] = None
    created_at: datetime
    
    # Status summary
    current_regime: Optional[str] = None
    active_alerts: int = 0
    fingerprint_ready: bool = False
    hours_monitored: float = 0.0


class AssetListResponse(BaseModel):
    """List of assets"""
    assets: List[AssetResponse]
    total: int


# =============================================================================
# System Status
# =============================================================================

class SystemStatusResponse(BaseModel):
    """System status summary"""
    asset_id: str
    current_regime: str
    is_steady_state: bool
    hours_of_operation: float
    total_observations: int
    
    sensor_trust: Dict[str, Dict[str, Any]] = Field(default_factory=dict)
    active_changes: List[Dict[str, Any]] = Field(default_factory=list)
    current_hypothesis: Optional[Dict[str, Any]] = None
    current_alert: Optional[AlertResponse] = None
    
    fingerprint_ready: bool = False
    policy_summary: Dict[str, Any] = Field(default_factory=dict)


class DashboardResponse(BaseModel):
    """Operator dashboard data"""
    asset_id: str
    status: str  # normal, watching, action_required, sensor_issue
    regime: str
    hours_monitored: float
    sensor_health: str
    
    primary_fault: Optional[str] = None
    confidence: Optional[str] = None
    false_alarm_prob: Optional[str] = None
    recommended_action: Optional[str] = None


# =============================================================================
# Metrics
# =============================================================================

class DeploymentMetricsResponse(BaseModel):
    """Deployment metrics"""
    period_start: datetime
    period_end: datetime
    total_alarms: int
    actionable_alarms: int
    watch_alarms: int
    sensor_alerts: int
    alarms_per_unit_per_month: float
    actionable_per_unit_per_month: float
    no_issue_found_rate: float
    lead_time_hours_mean: Optional[float] = None
    lead_time_hours_p50: Optional[float] = None
    lead_time_hours_p90: Optional[float] = None
    lead_time_hours_p95: Optional[float] = None
    lead_time_hours_min: Optional[float] = None
    lead_time_hours_max: Optional[float] = None
    lead_time_hours_histogram: Optional[Dict[str, int]] = None
    precision_at_k: Dict[int, float] = Field(default_factory=dict)


class CalibrationMetricsResponse(BaseModel):
    """Calibration metrics"""
    total_feedback_records: int
    feedback_by_outcome: Dict[str, int]
    calibration_curve: Dict[str, float]
    last_calibration: Optional[datetime] = None


# =============================================================================
# RAG / Query
# =============================================================================

class QueryRequest(BaseModel):
    """Conversational query request"""
    query: str = Field(..., min_length=1)
    asset_id: Optional[str] = None
    site_id: Optional[str] = None
    top_k: int = Field(default=5, ge=1, le=20)


class QuerySource(BaseModel):
    """Source document returned by RAG search"""
    doc_id: str
    doc_type: str
    score: float
    snippet: str
    asset_id: Optional[str] = None
    site_id: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


class QueryResponse(BaseModel):
    """Query response"""
    query: str
    answer: str
    sources: List[QuerySource] = Field(default_factory=list)
    transcription: Optional[str] = None


# =============================================================================
# Scenario Chat
# =============================================================================

class ScenarioChatRequest(BaseModel):
    persona_id: str
    persona_prompt: str
    message: str
    scope: str = Field(default="company")
    marketing_budget: str
    risk_level: str
    payback_timeline: str


class ScenarioAgentInstruction(BaseModel):
    agent_id: str
    title: str
    instruction: str


class ScenarioAgentOutput(BaseModel):
    agent_id: str
    title: str
    summary: str


class ScenarioChatResponse(BaseModel):
    persona_id: str
    instructions: List[ScenarioAgentInstruction]
    outputs: List[ScenarioAgentOutput]
    created_at: datetime


class PersonaResponse(BaseModel):
    id: str
    name: str
    tagline: str
    prompt: str


class PersonaListResponse(BaseModel):
    personas: List[PersonaResponse]


# Update forward references
TelemetryResponse.update_forward_refs()
