"""
SQLAlchemy ORM models for enterprise governance modules.

Tables:
- gov_lineage_events       — OpenLineage-compatible event log
- gov_model_versions       — MLOps model version registry
- gov_drift_alerts         — Drift detection alerts
- gov_quality_reports      — Data quality validation reports
- gov_exceptions           — Operating model exception records
- gov_sla_measurements     — SLA threshold measurements
- gov_security_controls    — ISO 27001 control status
- gov_compliance_reports   — Compliance report snapshots

All tables use the 'gov_' prefix to avoid collision with PdM tables.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    Index, JSON,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB

try:
    from predictive_maintenance.persistence.database import Base
except ImportError:
    from sqlalchemy.orm import declarative_base
    Base = declarative_base()


def _uuid():
    return str(uuid.uuid4())


# =========================================================================
# Lineage events
# =========================================================================

class LineageEventRow(Base):
    """Persisted OpenLineage event."""
    __tablename__ = "gov_lineage_events"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    event_type = Column(String(20), nullable=False, index=True)  # START, COMPLETE, FAIL
    job_id = Column(String(64), nullable=False, index=True)
    job_name = Column(String(200))
    job_type = Column(String(60))
    run_id = Column(String(64), nullable=False, index=True)
    parent_run_id = Column(String(64))
    company_id = Column(String(100), index=True)
    correlation_id = Column(String(64), index=True)
    input_datasets = Column(JSONB, default=list)
    output_datasets = Column(JSONB, default=list)
    duration_ms = Column(Integer)
    status = Column(String(20))
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_gov_lineage_company_ts", "company_id", "created_at"),
    )


# =========================================================================
# MLOps model versions
# =========================================================================

class ModelVersionRow(Base):
    """Persisted model version record."""
    __tablename__ = "gov_model_versions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    version_id = Column(String(64), unique=True, nullable=False)
    model_name = Column(String(200), nullable=False, index=True)
    version = Column(String(40), nullable=False)
    model_type = Column(String(60))
    stage = Column(String(30), nullable=False, index=True)
    artifact_uri = Column(Text)
    artifact_hash = Column(String(64))
    training_run_id = Column(String(64))
    metrics = Column(JSONB, default=dict)
    parameters = Column(JSONB, default=dict)
    tags = Column(JSONB, default=dict)
    promoted_by = Column(String(100))
    promoted_ts = Column(DateTime)
    rollback_reason = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_gov_model_name_stage", "model_name", "stage"),
    )


# =========================================================================
# Drift alerts
# =========================================================================

class DriftAlertRow(Base):
    """Persisted drift detection alert."""
    __tablename__ = "gov_drift_alerts"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    alert_id = Column(String(64), unique=True, nullable=False)
    model_name = Column(String(200), nullable=False, index=True)
    drift_type = Column(String(40), nullable=False)
    severity = Column(String(30), nullable=False, index=True)
    metric_name = Column(String(100))
    baseline_value = Column(Float)
    current_value = Column(Float)
    threshold = Column(Float)
    description = Column(Text)
    resolved = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# =========================================================================
# Data quality reports
# =========================================================================

class QualityReportRow(Base):
    """Persisted data quality validation report."""
    __tablename__ = "gov_quality_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    report_id = Column(String(64), unique=True, nullable=False)
    suite_id = Column(String(64), nullable=False, index=True)
    dataset_name = Column(String(200), nullable=False, index=True)
    total = Column(Integer)
    passed = Column(Integer)
    failed = Column(Integer)
    warnings = Column(Integer)
    pass_rate = Column(Float)
    overall_score = Column(Float)
    dimension_scores = Column(JSONB, default=dict)
    gate_decision = Column(String(20), nullable=False, index=True)
    gate_reason = Column(Text)
    duration_ms = Column(Integer)
    results_detail = Column(JSONB, default=list)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_gov_qr_dataset_gate", "dataset_name", "gate_decision"),
    )


# =========================================================================
# Exception records
# =========================================================================

class ExceptionRow(Base):
    """Persisted exception record from operating model."""
    __tablename__ = "gov_exceptions"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    exception_id = Column(String(64), unique=True, nullable=False)
    exception_type = Column(String(40), nullable=False, index=True)
    priority = Column(String(20), nullable=False, index=True)
    status = Column(String(30), nullable=False, index=True)
    title = Column(String(500))
    description = Column(Text)
    company_id = Column(String(100), index=True)
    location_id = Column(String(100))
    asset_id = Column(String(100))
    kpi_name = Column(String(100))
    assigned_to = Column(String(100))
    escalated_to = Column(String(100))
    resolution = Column(Text)
    root_cause = Column(Text)
    preventive_action = Column(Text)
    blocked_kpis = Column(JSONB, default=list)
    sla_due_ts = Column(DateTime)
    triaged_ts = Column(DateTime)
    resolved_ts = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    __table_args__ = (
        Index("ix_gov_exc_company_status", "company_id", "status"),
    )


# =========================================================================
# SLA measurements
# =========================================================================

class SLAMeasurementRow(Base):
    """Persisted SLA measurement."""
    __tablename__ = "gov_sla_measurements"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    sla_name = Column(String(200), nullable=False, index=True)
    company_id = Column(String(100), index=True)
    measured_value = Column(Float, nullable=False)
    threshold = Column(Float)
    breached = Column(Boolean, default=False, index=True)
    measurement_type = Column(String(40))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


# =========================================================================
# Security controls
# =========================================================================

class SecurityControlRow(Base):
    """Persisted security control status."""
    __tablename__ = "gov_security_controls"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    control_id = Column(String(64), unique=True, nullable=False)
    framework = Column(String(40), nullable=False, index=True)  # ISO_27001, OWASP_ASVS
    category = Column(String(100))
    name = Column(String(300))
    description = Column(Text)
    status = Column(String(30), nullable=False, index=True)
    evidence = Column(JSONB, default=dict)
    last_assessed_ts = Column(DateTime)
    next_review_ts = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)


# =========================================================================
# Compliance reports
# =========================================================================

class ComplianceReportRow(Base):
    """Persisted compliance report snapshot."""
    __tablename__ = "gov_compliance_reports"

    id = Column(UUID(as_uuid=False), primary_key=True, default=_uuid)
    report_id = Column(String(64), unique=True, nullable=False)
    framework = Column(String(40), nullable=False, index=True)
    company_id = Column(String(100), index=True)
    total_controls = Column(Integer)
    implemented = Column(Integer)
    not_implemented = Column(Integer)
    partial = Column(Integer)
    compliance_rate = Column(Float)
    findings = Column(JSONB, default=list)
    generated_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
