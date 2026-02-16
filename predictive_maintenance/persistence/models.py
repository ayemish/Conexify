"""
PDM Database Models

SQLAlchemy ORM models for persisting PDM system state.
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, JSON, Enum as SQLEnum, UniqueConstraint
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from .database import Base

try:
    from pgvector.sqlalchemy import Vector  # type: ignore
except Exception:  # pragma: no cover
    Vector = None  # type: ignore


def generate_uuid():
    return str(uuid.uuid4())


class AssetModel(Base):
    """Equipment/asset master record"""
    __tablename__ = "pdm_assets"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), unique=True, nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    
    # Asset metadata
    asset_type = Column(String(50), nullable=False, default="hvac_rtu")
    manufacturer = Column(String(100))
    model_number = Column(String(100))
    serial_number = Column(String(100))
    install_date = Column(DateTime)
    
    # Operational metadata
    refrigerant_type = Column(String(20))
    nominal_capacity_tons = Column(Float)
    nominal_voltage = Column(Float)
    
    # Status
    is_active = Column(Boolean, default=True)
    last_telemetry_at = Column(DateTime)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    telemetry = relationship("TelemetryModel", back_populates="asset", lazy="dynamic")
    alerts = relationship("AlertModel", back_populates="asset", lazy="dynamic")
    fingerprint = relationship("FingerprintModel", back_populates="asset", uselist=False)
    feedback = relationship("FeedbackModel", back_populates="asset", lazy="dynamic")
    
    __table_args__ = (
        Index("ix_pdm_assets_site_active", "site_id", "is_active"),
    )


class TelemetryModel(Base):
    """Raw telemetry data storage"""
    __tablename__ = "pdm_telemetry"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Operating state
    compressor_on = Column(Boolean)
    compressor_current = Column(Float)
    compressor_power = Column(Float)
    evap_fan_on = Column(Boolean)
    condenser_fan_on = Column(Boolean)
    supply_fan_speed = Column(Float)
    
    # Temperatures
    suction_temp = Column(Float)
    discharge_temp = Column(Float)
    supply_air_temp = Column(Float)
    return_air_temp = Column(Float)
    ambient_temp = Column(Float)
    zone_temp = Column(Float)
    
    # Pressures
    suction_pressure = Column(Float)
    discharge_pressure = Column(Float)
    
    # Calculated values
    superheat = Column(Float)
    subcool = Column(Float)
    
    # Control state
    setpoint = Column(Float)
    cooling_valve_pct = Column(Float)
    heating_valve_pct = Column(Float)
    damper_position_pct = Column(Float)
    
    # Detected regime
    regime = Column(String(30))
    regime_confidence = Column(Float)
    
    # Data quality
    data_quality_score = Column(Float, default=1.0)
    
    # Extra data as JSON
    extra_data = Column(JSONB)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    asset = relationship("AssetModel", back_populates="telemetry")
    
    __table_args__ = (
        Index("ix_pdm_telemetry_asset_time", "asset_id", "timestamp"),
        Index("ix_pdm_telemetry_time_regime", "timestamp", "regime"),
    )


class AlertModel(Base):
    """Maintenance alerts"""
    __tablename__ = "pdm_alerts"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    alert_id = Column(String(20), unique=True, nullable=False, index=True)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False)
    
    # Alert classification
    alert_type = Column(String(30), nullable=False)  # sensor_integrity, watch, actionable
    severity = Column(String(20), nullable=False)  # info, low, medium, high, critical
    
    # Probabilistic information
    false_alarm_probability = Column(Float)
    confidence = Column(Float)
    
    # Fault diagnosis
    primary_fault = Column(String(50))
    secondary_fault = Column(String(50))
    fault_beliefs = Column(JSONB)  # {fault_type: probability}
    
    # Evidence
    evidence_summary = Column(JSONB)  # List of evidence strings
    
    # Recommendations
    recommended_action = Column(Text)
    action_urgency = Column(String(20))  # monitor, schedule, urgent, immediate
    
    # Impact estimates
    energy_penalty_estimate_pct = Column(Float)
    downtime_risk_score = Column(Float)
    comfort_risk_score = Column(Float)
    estimated_cost_if_ignored = Column(Float)
    
    # Context
    regime_at_detection = Column(String(30))
    ambient_temp_at_detection = Column(Float)
    
    # Lifecycle
    status = Column(String(20), default="active")  # active, acknowledged, resolved, suppressed
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(100))
    resolved_at = Column(DateTime)
    resolved_by = Column(String(100))
    resolution_notes = Column(Text)
    
    # Feedback
    feedback_outcome = Column(String(30))  # confirmed_fault, no_issue_found, sensor_problem
    feedback_notes = Column(Text)
    feedback_at = Column(DateTime)
    
    # Relationships
    asset = relationship("AssetModel", back_populates="alerts")
    
    __table_args__ = (
        Index("ix_pdm_alerts_asset_status", "asset_id", "status"),
        Index("ix_pdm_alerts_type_created", "alert_type", "created_at"),
    )


class FingerprintModel(Base):
    """Equipment fingerprints for hierarchical modeling"""
    __tablename__ = "pdm_fingerprints"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    fingerprint_id = Column(String(20), unique=True, nullable=False)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), unique=True, nullable=False)
    
    # Learned parameters
    sensor_offsets = Column(JSONB)  # {sensor_id: offset}
    regime_baselines = Column(JSONB)  # {regime: {sensor: {mu, sigma}}}
    
    # Learning status
    hours_of_data = Column(Float, default=0.0)
    adaptation_confidence = Column(Float, default=0.0)
    n_regimes_observed = Column(JSONB)  # {regime: count}
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_fitted_at = Column(DateTime)
    
    # Relationships
    asset = relationship("AssetModel", back_populates="fingerprint")


class FeedbackModel(Base):
    """Human feedback records for calibration"""
    __tablename__ = "pdm_feedback"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    alert_id = Column(String(20), ForeignKey("pdm_alerts.alert_id"), nullable=False)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False)
    
    # Feedback
    outcome = Column(String(30), nullable=False)  # confirmed_fault, no_issue_found, sensor_problem
    confirmed_fault_type = Column(String(50))
    notes = Column(Text)
    
    # Context at prediction time
    alert_timestamp = Column(DateTime)
    predicted_fault_distribution = Column(JSONB)  # {fault_type: probability}
    predicted_false_alarm_prob = Column(Float)
    
    # Feedback metadata
    feedback_by = Column(String(100))
    feedback_at = Column(DateTime, default=datetime.utcnow)
    
    # Relationships
    asset = relationship("AssetModel", back_populates="feedback")
    
    __table_args__ = (
        Index("ix_pdm_feedback_asset_outcome", "asset_id", "outcome"),
    )


class RagDocumentModel(Base):
    """RAG document embeddings for agent summaries and digital twins"""
    __tablename__ = "pdm_rag_documents"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    doc_id = Column(String(32), unique=True, nullable=False, index=True)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=True, index=True)
    site_id = Column(String(100), nullable=True, index=True)
    
    doc_type = Column(String(50), nullable=False)  # agent_summary, digital_twin, etc.
    content = Column(Text, nullable=False)
    doc_metadata = Column(JSONB, default=dict)
    
    # Embedding stored as pgvector if available, else JSON array
    embedding = Column(Vector(1536)) if Vector is not None else Column(JSONB)
    embedding_dim = Column(Integer, default=1536)
    
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_pdm_rag_doc_type", "doc_type"),
        Index("ix_pdm_rag_asset_type", "asset_id", "doc_type"),
    )


class CalibrationStateModel(Base):
    """Persisted calibration curve/state"""
    __tablename__ = "pdm_calibration_state"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=True, index=True)
    asset_type = Column(String(50), nullable=True)
    
    # Calibration curve mapping raw confidence -> actual FA probability
    calibration_curve = Column(JSONB, default=dict)
    n_records = Column(Integer, default=0)
    
    last_calibrated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_pdm_calibration_asset_type", "asset_type"),
    )


class RegimeSegmentModel(Base):
    """Operating regime segments for analysis"""
    __tablename__ = "pdm_regime_segments"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False, index=True)
    
    regime = Column(String(30), nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime)
    
    confidence = Column(Float)
    n_samples = Column(Integer)
    avg_ambient_temp = Column(Float)
    
    # Statistics during segment
    stats = Column(JSONB)  # {sensor: {mean, std, min, max}}
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_pdm_regime_asset_time", "asset_id", "start_time"),
    )


class ChangeDetectionModel(Base):
    """Change detection events"""
    __tablename__ = "pdm_change_detections"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    detector_id = Column(String(50), nullable=False)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False)
    sensor_type = Column(String(30))
    
    # Detection state
    cusum_pos = Column(Float)
    cusum_neg = Column(Float)
    glr_statistic = Column(Float)
    
    change_detected = Column(Boolean, default=False)
    change_score = Column(Float)
    estimated_onset_time = Column(DateTime)
    
    # Persistence tracking
    anomaly_start_time = Column(DateTime)
    anomaly_duration_hours = Column(Float)
    n_anomalous_samples = Column(Integer)
    n_regimes_observed = Column(Integer)
    
    stability_score = Column(Float)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_pdm_change_asset_detected", "asset_id", "change_detected"),
    )


class FaultHypothesisModel(Base):
    """Fault hypothesis snapshots"""
    __tablename__ = "pdm_fault_hypotheses"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    hypothesis_id = Column(String(20), nullable=False, index=True)
    asset_id = Column(String(100), ForeignKey("pdm_assets.asset_id"), nullable=False)
    
    # Belief state
    priors = Column(JSONB)  # {fault_type: probability}
    posteriors = Column(JSONB)  # {fault_type: probability}
    evidence = Column(JSONB)  # List of evidence items
    
    # Summary
    most_likely_fault = Column(String(50))
    second_likely_fault = Column(String(50))
    probability_mass_top2 = Column(Float)
    is_concentrated = Column(Boolean, default=False)
    
    recommended_action = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_pdm_hypothesis_asset_time", "asset_id", "created_at"),
    )


class ModelVersionModel(Base):
    """Model version tracking"""
    __tablename__ = "pdm_model_versions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    version_id = Column(String(50), unique=True, nullable=False, index=True)
    model_name = Column(String(100), nullable=False)
    model_type = Column(String(50), nullable=False)
    version_number = Column(String(20), nullable=False)
    
    # Lifecycle
    stage = Column(String(20), default="development")
    is_active = Column(Boolean, default=True)
    
    # Training info
    training_job_id = Column(String(50))
    training_data_version = Column(String(50))
    n_training_samples = Column(Integer)
    
    # Configuration
    hyperparameters = Column(JSONB)
    feature_config = Column(JSONB)
    
    # Metrics
    validation_metrics = Column(JSONB)
    production_metrics = Column(JSONB)
    
    # Artifacts
    artifact_uri = Column(String(500))
    artifact_checksum = Column(String(64))
    
    # Governance
    approval_status = Column(String(20), default="pending")
    approved_by = Column(String(100))
    approved_at = Column(DateTime)
    
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))
    deployed_at = Column(DateTime)
    
    __table_args__ = (
        Index("ix_pdm_models_name_stage", "model_name", "stage"),
    )


class AuditLogModel(Base):
    """Audit trail"""
    __tablename__ = "pdm_audit_log"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    event_id = Column(String(20), unique=True, nullable=False)
    
    action = Column(String(50), nullable=False, index=True)
    actor = Column(String(100), nullable=False)
    target_type = Column(String(50))
    target_id = Column(String(100))
    
    details = Column(JSONB)
    
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)
    
    __table_args__ = (
        Index("ix_pdm_audit_action_time", "action", "timestamp"),
    )


class ApprovalQueueItemModel(Base):
    """Persisted approval queue items (replaces in-memory dict)."""
    __tablename__ = "pdm_approval_queue"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    item_id = Column(String(50), unique=True, nullable=False, index=True)

    # Source references
    approval_id = Column(String(100), nullable=False, index=True)
    run_id = Column(String(100), nullable=False, index=True)
    incident_id = Column(String(100), nullable=False, index=True)
    playbook_id = Column(String(100), nullable=False)
    step_id = Column(String(100), nullable=False)

    # Context
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False)
    asset_id = Column(String(100), nullable=False, index=True)

    # Classification
    item_type = Column(String(50), default="action_approval")
    risk_tier = Column(String(20), default="MEDIUM")
    priority = Column(Integer, default=50)

    # Proposed action (stored as JSON)
    proposed_actions = Column(JSONB, default=list)
    action_summary = Column(Text, default="")

    # Context data
    telemetry_snapshot = Column(JSONB, default=dict)
    fault_context = Column(JSONB, default=dict)
    evidence = Column(JSONB, default=dict)

    # Status
    status = Column(String(30), default="pending", index=True)

    # LLM explanation and validation (stored as JSON blobs)
    explanation_data = Column(JSONB, nullable=True)
    explanation_error = Column(Text, nullable=True)
    validation_data = Column(JSONB, nullable=True)
    validation_error = Column(Text, nullable=True)

    # Human decision
    decision_data = Column(JSONB, nullable=True)

    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime, nullable=True)

    # Assignment
    assigned_to = Column(String(100), nullable=True)
    assigned_at = Column(DateTime, nullable=True)

    # Escalation
    escalation_level = Column(Integer, default=0)

    __table_args__ = (
        Index("ix_pdm_aq_tenant_status", "tenant_id", "status"),
        Index("ix_pdm_aq_priority", "priority"),
    )


class RetrainingRequestModel(Base):
    """Persisted retraining requests."""
    __tablename__ = "pdm_retraining_requests"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    request_id = Column(String(50), unique=True, nullable=False, index=True)
    trigger_type = Column(String(30), nullable=False, index=True)
    model_id = Column(String(100), nullable=True, index=True)
    asset_id = Column(String(100), nullable=True, index=True)
    fault_type = Column(String(50), nullable=True)

    false_positive_rate = Column(Float, default=0.0)
    false_negative_rate = Column(Float, default=0.0)
    mean_absolute_error = Column(Float, default=0.0)
    n_incorrect_recent = Column(Integer, default=0)
    n_observations_since_train = Column(Integer, default=0)

    evidence = Column(JSONB, default=dict)
    status = Column(String(30), default="pending", index=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    completed_at = Column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_pdm_retrain_status_type", "status", "trigger_type"),
    )


class KPIPipelineRunModel(Base):
    """Tracks KPI orchestration pipeline runs."""
    __tablename__ = "pdm_kpi_pipeline_runs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    run_id = Column(String(50), unique=True, nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)

    # Pipeline status
    status = Column(String(30), default="pending", index=True)  # pending, running, completed, failed
    phase = Column(String(50), default="")  # current phase name
    phase_index = Column(Integer, default=0)
    total_phases = Column(Integer, default=7)

    # KPI crew statuses (JSON: {kpi_name: {status, started_at, completed_at, error}})
    crew_statuses = Column(JSONB, default=dict)

    # Results (full dashboard JSON when completed)
    result_payload = Column(JSONB, nullable=True)

    # Timing
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_seconds = Column(Float, nullable=True)

    # Error info
    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_pdm_kpi_run_site_status", "site_id", "status"),
    )


class KPIResultModel(Base):
    """Persisted individual KPI computation results."""
    __tablename__ = "pdm_kpi_results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    run_id = Column(String(50), ForeignKey("pdm_kpi_pipeline_runs.run_id"), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)

    kpi_name = Column(String(100), nullable=False, index=True)
    display_name = Column(String(200), default="")
    category = Column(String(100), default="")

    # Savings
    savings_low = Column(Float, default=0.0)
    savings_medium = Column(Float, default=0.0)
    savings_high = Column(Float, default=0.0)
    confidence = Column(Float, default=0.0)
    status = Column(String(30), default="pending")

    # Narrative and assumptions
    narrative = Column(Text, default="")
    assumptions = Column(JSONB, default=list)
    supporting_metrics = Column(JSONB, default=dict)

    # Data quality
    data_points_used = Column(Integer, default=0)
    data_coverage_pct = Column(Float, default=0.0)
    data_grounded = Column(Boolean, default=False)

    computed_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pdm_kpi_result_run_kpi", "run_id", "kpi_name"),
        Index("ix_pdm_kpi_result_site_kpi", "site_id", "kpi_name"),
    )


class SiteConfigModel(Base):
    """Per-site KPI configuration baselines loaded at runtime.

    Replaces hard-coded KPIConfig defaults with customer-specific values
    persisted during onboarding or updated via the admin API.
    """
    __tablename__ = "pdm_site_configs"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    site_id = Column(String(100), unique=True, nullable=False, index=True)
    customer_name = Column(String(200), default="Customer")

    # Fleet
    total_assets = Column(Integer, default=50)
    total_locations = Column(Integer, default=3)

    # Energy baseline
    baseline_annual_kwh = Column(Float, default=7_087_500.0)
    energy_cost_per_kwh = Column(Float, default=0.12)

    # Refrigerant baseline
    baseline_leak_rate_pct = Column(Float, default=25.0)
    refrigerant_cost_per_lb = Column(Float, default=15.0)
    avg_charge_lbs = Column(Float, default=12.0)

    # Work order baseline
    baseline_reactive_wo_per_month = Column(Integer, default=40)
    avg_wo_cost = Column(Float, default=350.0)

    # Food safety
    avg_temp_excursion_events_per_month = Column(Integer, default=12)
    food_waste_cost_per_event = Column(Float, default=800.0)
    food_safety_violation_cost = Column(Float, default=5_250.0)
    baseline_violations_per_year = Column(Integer, default=18)

    # Maintenance
    avg_dispatch_cost = Column(Float, default=450.0)
    baseline_dispatches_per_month = Column(Integer, default=22)
    baseline_pm_cost_annual = Column(Float, default=180_000.0)

    # Uptime
    baseline_uptime_pct = Column(Float, default=90.0)
    hourly_downtime_cost = Column(Float, default=150.0)
    operating_hours_per_year = Column(Float, default=8_760.0)

    # Call center
    baseline_calls_per_month = Column(Integer, default=80)
    cost_per_call = Column(Float, default=25.0)

    # CapEx
    avg_asset_replacement_cost = Column(Float, default=18_000.0)
    discount_rate = Column(Float, default=0.08)

    # ESG
    grid_emission_factor_tco2_per_kwh = Column(Float, default=0.0004)
    refrigerant_gwp = Column(Float, default=2_088.0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class AdvisorSessionModel(Base):
    """Persisted advisor chat session."""
    __tablename__ = "pdm_advisor_sessions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    session_id = Column(String(100), unique=True, nullable=False, index=True)
    ecosystem = Column(String(50), default="auto")
    site_id = Column(String(100), nullable=True, index=True)
    context = Column(JSONB, default=dict)
    is_active = Column(Boolean, default=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    messages = relationship("AdvisorMessageModel", back_populates="session", cascade="all, delete-orphan")


class AdvisorMessageModel(Base):
    """Individual message within an advisor session."""
    __tablename__ = "pdm_advisor_messages"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    session_id = Column(String(100), ForeignKey("pdm_advisor_sessions.session_id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    metadata_ = Column("metadata", JSONB, default=dict)

    created_at = Column(DateTime, default=datetime.utcnow)

    session = relationship("AdvisorSessionModel", back_populates="messages")

    __table_args__ = (
        Index("ix_pdm_advisor_msg_session_ts", "session_id", "created_at"),
    )


class WorkOrderModel(Base):
    """Work order records for work_order_reduction KPI."""
    __tablename__ = "pdm_work_orders"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    wo_id = Column(String(100), unique=True, nullable=False, index=True)
    asset_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)

    wo_type = Column(String(50), default="reactive")  # reactive, planned, emergency, pm
    priority = Column(String(20), default="normal")  # low, normal, high, critical
    status = Column(String(30), default="open")  # open, in_progress, completed, cancelled
    cost = Column(Float, default=0.0)
    labor_hours = Column(Float, default=0.0)
    description = Column(Text, default="")
    resolution = Column(Text, default="")
    provider = Column(String(50), default="in_house")  # in_house, vendor, service_bureau

    opened_at = Column(DateTime, nullable=False)
    dispatched_at = Column(DateTime, nullable=True)   # When provider was dispatched
    closed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    source_alert_id = Column(String(20), nullable=True, index=True)  # FK-light to pdm_alerts.alert_id

    __table_args__ = (
        Index("ix_pdm_wo_site_type", "site_id", "wo_type"),
        Index("ix_pdm_wo_asset_opened", "asset_id", "opened_at"),
    )


class EnergyDataModel(Base):
    """Energy consumption and cost records for energy_reduction KPI."""
    __tablename__ = "pdm_energy_data"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    site_id = Column(String(100), nullable=False, index=True)
    asset_id = Column(String(100), nullable=True, index=True)

    period_start = Column(DateTime, nullable=False)
    period_end = Column(DateTime, nullable=True)
    kwh_consumed = Column(Float, default=0.0)
    cost = Column(Float, default=0.0)
    rate_per_kwh = Column(Float, nullable=True)
    demand_kw = Column(Float, nullable=True)
    source = Column(String(50), default="utility_bill")  # utility_bill, submeter, bms

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pdm_energy_site_period", "site_id", "period_start"),
    )


class MaintenanceHistoryModel(Base):
    """Maintenance service history for PM optimization KPI."""
    __tablename__ = "pdm_maintenance_history"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)

    service_date = Column(DateTime, nullable=False)
    service_type = Column(String(50), default="pm")  # pm, repair, inspection, emergency
    cost = Column(Float, default=0.0)
    labor_hours = Column(Float, default=0.0)
    provider = Column(String(100), default="")  # in_house, vendor name
    description = Column(Text, default="")
    parts_replaced = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pdm_maint_asset_date", "asset_id", "service_date"),
        Index("ix_pdm_maint_site_type", "site_id", "service_type"),
    )


class RefrigerantRecordModel(Base):
    """Refrigerant tracking records for refrigerant_leak_reduction KPI."""
    __tablename__ = "pdm_refrigerant_records"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    asset_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)

    record_date = Column(DateTime, nullable=False)
    refrigerant_type = Column(String(30), default="R-410A")
    charge_lbs = Column(Float, default=0.0)
    lbs_added = Column(Float, default=0.0)
    lbs_recovered = Column(Float, default=0.0)
    leak_detected = Column(Boolean, default=False)
    leak_rate_pct = Column(Float, nullable=True)
    notes = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("ix_pdm_refrig_asset_date", "asset_id", "record_date"),
    )


class SchemaMappingModel(Base):
    """Persisted schema mapping configurations for the data normalizer."""
    __tablename__ = "pdm_schema_mappings"

    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    mapping_id = Column(String(50), unique=True, nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    name = Column(String(200), default="")
    description = Column(Text, default="")

    # Source info
    source_type = Column(String(50), default="csv")  # csv, api, database, sftp, s3
    source_columns = Column(JSONB, default=list)

    # Field mappings: [{source_field, target_field, transform, default_value}]
    field_mappings = Column(JSONB, default=list)

    # Validation rules
    validation_rules = Column(JSONB, default=list)

    # Status
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime, nullable=True)
    records_processed = Column(Integer, default=0)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
