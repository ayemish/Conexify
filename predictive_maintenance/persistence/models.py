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
