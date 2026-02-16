"""Pydantic models for the AI Work Order system."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ── Enums ───────────────────────────────────────────────────────────

class WorkOrderPriority(str, Enum):
    EMERGENCY = "emergency"
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    PLANNED = "planned"


class WorkOrderStatus(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PENDING_APPROVAL = "pending_approval"
    COMPLETED = "completed"
    VERIFIED = "verified"
    REOPENED = "reopened"


class WorkOrderSource(str, Enum):
    MANUAL = "manual"
    AI_NLP = "ai_nlp"
    AI_SENSOR = "ai_sensor"
    PDM_ALERT = "pdm_alert"


# ── Request / Response Models ───────────────────────────────────────

class NLInterpretRequest(BaseModel):
    """Natural-language work order creation request."""
    text: str = Field(..., description="Free-text issue description from user")
    voice_transcript: Optional[str] = Field(None, description="Optional voice-to-text transcript")
    context: Optional[Dict[str, Any]] = Field(None, description="Additional context (current location, recent alerts, etc.)")


class NLInterpretResponse(BaseModel):
    """Structured work order draft extracted by LLM."""
    title: str
    description: str
    asset_id: Optional[str] = None
    estate: Optional[str] = None
    location: Optional[str] = None
    priority: WorkOrderPriority
    problem_type: str
    symptoms: List[str] = []
    confidence: float = Field(ge=0.0, le=1.0)
    clarifications: List[str] = Field(default_factory=list, description="Questions when LLM is uncertain")
    raw_llm_response: Optional[str] = Field(None, description="Full LLM output for audit")


class SensorSignal(BaseModel):
    """PdM sensor signal that may trigger autonomous WO creation."""
    asset_id: str
    sensor_type: str
    anomaly_type: str
    change_score: float = Field(ge=0.0, le=1.0)
    persistence_hours: float
    regime: str = "unknown"
    fault_hypothesis: Optional[str] = None
    fault_probability: Optional[float] = None
    sensor_trust: float = 1.0
    telemetry_snapshot: Optional[Dict[str, float]] = None


class AutoCreateWORequest(BaseModel):
    """Autonomous WO creation from PdM signals."""
    signals: List[SensorSignal]
    site_id: str = "default"


class AutoCreateWOResponse(BaseModel):
    """LLM-generated WO from sensor signals."""
    title: str
    description: str
    asset_id: str
    priority: WorkOrderPriority
    problem_type: str
    diagnostic_context: str
    recommended_tags: List[str] = []
    confidence: float
    should_create: bool = Field(description="Whether signals warrant WO creation")
    rationale: str
    raw_llm_response: Optional[str] = None


class AIImpactAssessment(BaseModel):
    """AI-generated impact assessment for prioritization."""
    safety_risk: str = "Low"
    revenue_impact: float = 0.0
    sla_breach_risk: float = 0.0
    brand_impact: str = "No"
    priority_score: int = Field(ge=0, le=100)
    recommended_sla_hours: int = 72
    rationale: str = ""
    raw_llm_response: Optional[str] = None


class PrioritizeRequest(BaseModel):
    """Request to prioritize/triage a work order."""
    work_order_id: str
    title: str
    description: str
    asset_id: str
    estate: str
    location: str
    priority: WorkOrderPriority
    source: WorkOrderSource
    created_at: str
    historical_context: Optional[Dict[str, Any]] = Field(None, description="Past WOs for this asset")


class PrioritizeResponse(BaseModel):
    """LLM-generated prioritization result."""
    work_order_id: str
    assessment: AIImpactAssessment
    suggested_priority: WorkOrderPriority
    rationale_summary: str
    raw_llm_response: Optional[str] = None


class Provider(BaseModel):
    """Service provider profile."""
    id: str
    name: str
    specialty: str
    rating: float
    ftfr: float
    avg_cost: float
    avg_response_hrs: float
    proximity_miles: float
    certifications: List[str] = []
    available: bool = True


class ProviderMatch(BaseModel):
    """AI-scored provider match."""
    provider: Provider
    match_score: int = Field(ge=0, le=100)
    recommended: bool = False
    rationale: str = ""


class MatchRequest(BaseModel):
    """Request to match providers to a work order."""
    work_order_id: str
    title: str
    description: str
    asset_id: str
    priority: WorkOrderPriority
    problem_type: str
    location: str
    providers: List[Provider]


class MatchResponse(BaseModel):
    """LLM-generated provider match results."""
    work_order_id: str
    matches: List[ProviderMatch]
    rationale_summary: str
    raw_llm_response: Optional[str] = None


class CostRecommendation(BaseModel):
    """AI cost/approval recommendation."""
    action: str = Field(description="approve | reject | review")
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    historical_comparison: Optional[str] = None
    risk_factors: List[str] = []


class CostRecommendRequest(BaseModel):
    """Request for cost recommendation."""
    work_order_id: str
    title: str
    description: str
    asset_id: str
    priority: WorkOrderPriority
    estimated_cost: float
    provider_name: Optional[str] = None
    historical_similar: Optional[List[Dict[str, Any]]] = None


class CostRecommendResponse(BaseModel):
    """LLM-generated cost recommendation."""
    work_order_id: str
    recommendation: CostRecommendation
    raw_llm_response: Optional[str] = None


class VerificationRequest(BaseModel):
    """Request to verify post-service effectiveness."""
    work_order_id: str
    title: str
    asset_id: str
    problem_type: str
    pre_service_metrics: Dict[str, float]
    post_service_metrics: Dict[str, float]
    service_description: Optional[str] = None


class VerificationResult(BaseModel):
    """AI verification of service effectiveness."""
    passed: bool
    confidence: float = Field(ge=0.0, le=1.0)
    post_metrics_improved: bool
    evidence_summary: str
    reopen_reason: Optional[str] = None
    recommendations: List[str] = []


class VerificationResponse(BaseModel):
    """LLM-generated verification result."""
    work_order_id: str
    verification: VerificationResult
    raw_llm_response: Optional[str] = None


class ForecastRequest(BaseModel):
    """Request for WO volume forecast."""
    site_id: str = "default"
    horizon_days: int = 30
    historical_wo_counts: Optional[List[Dict[str, Any]]] = None
    asset_risk_scores: Optional[Dict[str, float]] = None


class ForecastPoint(BaseModel):
    """Single forecast point."""
    date: str
    predicted_count: int
    confidence_low: int
    confidence_high: int
    risk_drivers: List[str] = []


class ForecastResponse(BaseModel):
    """LLM-augmented forecast."""
    site_id: str
    points: List[ForecastPoint]
    narrative: str = Field(description="LLM-generated interpretation of forecast")
    risk_estates: Optional[Dict[str, float]] = None
    raw_llm_response: Optional[str] = None


class WorkOrder(BaseModel):
    """Full work order model."""
    id: str = Field(default_factory=lambda: f"WO-{datetime.now(timezone.utc).strftime('%Y')}-{str(uuid.uuid4())[:8].upper()}")
    title: str
    description: str
    asset_id: str
    estate: str = ""
    location: str = ""
    priority: WorkOrderPriority = WorkOrderPriority.MEDIUM
    status: WorkOrderStatus = WorkOrderStatus.OPEN
    source: WorkOrderSource = WorkOrderSource.MANUAL
    problem_type: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    sla_deadline: Optional[datetime] = None
    estimated_cost: float = 0.0
    actual_cost: Optional[float] = None
    assigned_provider: Optional[Provider] = None
    ai_priority_score: int = 50
    ai_impact_assessment: Optional[AIImpactAssessment] = None
    ai_rationale: str = ""
    verification: Optional[VerificationResult] = None


class ABBaselineMetrics(BaseModel):
    """The 12 core A/B test KPIs."""
    alert_to_wo: float = Field(default=0, description="% of PdM alerts that became WOs")
    wo_volume: int = Field(default=0, description="Total WOs in the time window")
    reactive_pct: float = Field(default=0, description="% reactive/emergency WOs")
    proactive_pct: float = Field(default=0, description="% planned/PM WOs")
    mttr: float = Field(default=0, description="Mean time to repair (hours)")
    mttd: float = Field(default=0, description="Mean time to dispatch (hours)")
    ftfr: float = Field(default=0, description="First-time fix rate %")
    avg_cost: float = Field(default=0, description="Average cost per WO ($)")
    sla_compliance: float = Field(default=0, description="% of WOs meeting SLA")
    reopen_rate: float = Field(default=0, description="% of WOs reopened")
    downtime_hrs: float = Field(default=0, description="Avg equipment downtime hours")
    nif_rate: float = Field(default=0, description="No-issue-found dispatch rate %")


class ABMetricProvenance(BaseModel):
    """Tracks whether each metric was computed from real data or estimated."""
    metric_id: str
    source: str = Field(description="db_computed | kpi_config | estimated | default")
    record_count: int = Field(default=0, description="Number of records used")
    note: str = Field(default="")


class ABBaselineResponse(BaseModel):
    """Full A/B baseline response with real + predicted metrics."""
    baseline: ABBaselineMetrics
    predicted: ABBaselineMetrics
    time_range: str = "30d"
    site_id: str = "default"
    provenance: List[ABMetricProvenance] = Field(default_factory=list)
    computed_at: str = Field(default="")


# Documented improvement factors for the AI WO system
AB_IMPROVEMENT_FACTORS = {
    "alert_to_wo":    {"mode": "target", "value": 89},        # Autonomous creation → 89% conversion
    "wo_volume":      {"mode": "multiply", "value": 0.72},    # Proactive reduces cascade failures
    "reactive_pct":   {"mode": "target", "value": 22},        # PdM shifts to planned
    "proactive_pct":  {"mode": "target", "value": 78},        # Mirror of reactive
    "mttr":           {"mode": "multiply", "value": 0.37},    # Better diagnostics
    "mttd":           {"mode": "multiply", "value": 0.23},    # AI dispatch
    "ftfr":           {"mode": "target", "value": 91},        # Right diagnosis → right fix
    "avg_cost":       {"mode": "multiply", "value": 0.65},    # Proactive is cheaper
    "sla_compliance": {"mode": "target", "value": 96},        # Faster detection + dispatch
    "reopen_rate":    {"mode": "target", "value": 3},         # Post-service verification
    "downtime_hrs":   {"mode": "multiply", "value": 0.25},    # Proactive intervention
    "nif_rate":       {"mode": "target", "value": 3},         # AI triage eliminates false dispatches
}


class ABTestRequest(BaseModel):
    """A/B test comparison request — baseline vs AI-predicted metrics."""
    baseline: Dict[str, Any] = Field(..., description="Actual WO KPIs without AI system")
    predicted: Dict[str, Any] = Field(..., description="Projected WO KPIs with AI system")
    time_range: str = Field(default="30d", description="Analysis window (7d, 30d, 90d, 12m)")


class ABTestResponse(BaseModel):
    """LLM-generated A/B test analysis."""
    insight: str = Field(description="Analytical narrative comparing baseline vs predicted")
    top_improvements: List[str] = Field(default_factory=list, description="Top 3 improved metric IDs")
    risk_areas: List[str] = Field(default_factory=list, description="Metrics with marginal improvement")
    confidence_level: str = Field(default="medium", description="high | medium | low")
    executive_summary: str = Field(default="", description="One-sentence executive summary")
    raw_llm_response: Optional[str] = None
