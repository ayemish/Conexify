"""
Autopilot Database Models

SQLAlchemy ORM models for the Operations Autopilot system.
"""

from datetime import datetime
from typing import Optional
import uuid

from sqlalchemy import (
    Column, String, Integer, Float, Boolean, DateTime, Text,
    ForeignKey, Index, Enum as SQLEnum
)
from sqlalchemy.orm import relationship
from sqlalchemy.dialects.postgresql import UUID, JSONB

from ..persistence.database import Base


def generate_uuid():
    return str(uuid.uuid4())


# =============================================================================
# Playbook Models
# =============================================================================

class PlaybookModel(Base):
    """Playbook definition - latest version pointer"""
    __tablename__ = "autopilot_playbooks"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    playbook_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Identity
    name = Column(String(200), nullable=False)
    description = Column(Text)
    
    # Classification
    asset_class = Column(String(50), nullable=False, index=True)  # HVAC, REFRIGERATION, etc.
    fault_type = Column(String(100), nullable=False, index=True)
    risk_tier = Column(String(20), nullable=False, default="MEDIUM")  # LOW, MEDIUM, HIGH
    
    # Latest version
    current_version = Column(String(20), nullable=False, default="1.0.0")
    
    # Lifecycle
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    retired_at = Column(DateTime, nullable=True)
    
    # Relationships
    versions = relationship("PlaybookVersionModel", back_populates="playbook", lazy="dynamic")
    
    __table_args__ = (
        Index("ix_autopilot_playbooks_class_fault", "asset_class", "fault_type"),
        Index("ix_autopilot_playbooks_risk_active", "risk_tier", "is_active"),
    )


class PlaybookVersionModel(Base):
    """Immutable playbook version"""
    __tablename__ = "autopilot_playbook_versions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    playbook_id = Column(String(50), ForeignKey("autopilot_playbooks.playbook_id"), nullable=False)
    version = Column(String(20), nullable=False)
    
    # Full playbook definition (JSONB for schema flexibility)
    definition = Column(JSONB, nullable=False)
    
    # Parsed components for querying
    triggers = Column(JSONB, default=list)
    preconditions = Column(JSONB, default=list)
    steps = Column(JSONB, default=list)
    verification = Column(JSONB, default=list)
    escalation = Column(JSONB, default=dict)
    evidence_requirements = Column(JSONB, default=dict)
    
    # Metadata
    schema_version = Column(String(20), default="1.0")
    content_hash = Column(String(64))  # SHA-256 of definition for integrity
    
    # Lifecycle
    effective_from = Column(DateTime, default=datetime.utcnow)
    retired_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    created_by = Column(String(100))
    
    # Relationships
    playbook = relationship("PlaybookModel", back_populates="versions")
    
    __table_args__ = (
        Index("ix_autopilot_pb_versions_playbook", "playbook_id", "version"),
    )


# =============================================================================
# Incident Models
# =============================================================================

class IncidentModel(Base):
    """Detected condition requiring action"""
    __tablename__ = "autopilot_incidents"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    incident_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Identity
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    asset_id = Column(String(100), nullable=False, index=True)
    
    # Classification
    fault_type = Column(String(100), nullable=False, index=True)
    severity = Column(String(20), nullable=False, default="medium")
    source = Column(String(50), nullable=False)  # rules_engine, anomaly_detector, external
    
    # Timing
    start_ts = Column(DateTime, nullable=False)
    end_ts = Column(DateTime, nullable=True)
    detected_at = Column(DateTime, nullable=False, default=datetime.utcnow)
    
    # Evidence
    trigger_evidence = Column(JSONB, default=dict)
    point_values = Column(JSONB, default=dict)
    window_start = Column(DateTime, nullable=True)
    window_end = Column(DateTime, nullable=True)
    
    # Status
    status = Column(String(30), nullable=False, default="open")
    
    # Matching
    matched_playbook_id = Column(String(50), nullable=True)
    match_reason = Column(Text, nullable=True)
    
    # Deduplication
    dedup_key = Column(String(200), nullable=False, index=True)
    
    # Lifecycle
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    
    # Relationships
    runs = relationship("AutopilotRunModel", back_populates="incident", lazy="dynamic")
    
    __table_args__ = (
        Index("ix_autopilot_incidents_tenant_site", "tenant_id", "site_id"),
        Index("ix_autopilot_incidents_asset_status", "asset_id", "status"),
        Index("ix_autopilot_incidents_fault_time", "fault_type", "detected_at"),
    )


# =============================================================================
# AutopilotRun Models
# =============================================================================

class AutopilotRunModel(Base):
    """Execution instance of a playbook against an incident"""
    __tablename__ = "autopilot_runs"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    run_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # References
    incident_id = Column(String(50), ForeignKey("autopilot_incidents.incident_id"), nullable=False)
    playbook_id = Column(String(50), nullable=False, index=True)
    playbook_version = Column(String(20), nullable=False)
    
    # Identity
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False, index=True)
    asset_id = Column(String(100), nullable=False, index=True)
    
    # Workflow state
    thread_id = Column(String(50), nullable=False, index=True)
    current_checkpoint_id = Column(String(50), nullable=True)
    
    # Status
    status = Column(String(30), nullable=False, default="planning")
    risk_tier = Column(String(20), nullable=False, default="MEDIUM")
    
    # Execution tracking
    current_step_index = Column(Integer, default=0)
    
    # Approvals
    pending_approval_id = Column(String(50), nullable=True)
    
    # Evidence
    evidence_pack_id = Column(String(50), nullable=True)
    
    # Outcome
    outcome = Column(String(30), nullable=True)  # RESOLVED, PARTIAL, FAILED
    outcome_reason = Column(Text, nullable=True)
    
    # Explainability
    plan_rationale = Column(Text, nullable=True)
    
    # Lifecycle
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Relationships
    incident = relationship("IncidentModel", back_populates="runs")
    steps = relationship("RunStepModel", back_populates="run", lazy="dynamic")
    actions = relationship("RunActionModel", back_populates="run", lazy="dynamic")
    approvals = relationship("ApprovalModel", back_populates="run", lazy="dynamic")
    checkpoints = relationship("CheckpointModel", back_populates="run", lazy="dynamic")
    verifications = relationship("VerificationResultModel", back_populates="run", lazy="dynamic")
    
    __table_args__ = (
        Index("ix_autopilot_runs_incident", "incident_id"),
        Index("ix_autopilot_runs_status_time", "status", "created_at"),
        Index("ix_autopilot_runs_asset_time", "asset_id", "created_at"),
    )


class RunStepModel(Base):
    """Individual step within an AutopilotRun"""
    __tablename__ = "autopilot_run_steps"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    step_id = Column(String(50), unique=True, nullable=False, index=True)
    run_id = Column(String(50), ForeignKey("autopilot_runs.run_id"), nullable=False)
    
    # From playbook
    playbook_step_id = Column(String(50), nullable=False)
    step_index = Column(Integer, nullable=False)
    action_type = Column(String(30), nullable=False)
    
    # Parameters
    params = Column(JSONB, default=dict)
    
    # Approval
    requires_approval = Column(Boolean, default=False)
    approval_id = Column(String(50), nullable=True)
    
    # Execution
    status = Column(String(30), nullable=False, default="pending")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    
    # Result
    result = Column(JSONB, default=dict)
    error = Column(Text, nullable=True)
    
    # Error handling
    on_error = Column(String(20), default="ESCALATE")
    retry_count = Column(Integer, default=0)
    max_retries = Column(Integer, default=3)
    
    # Relationships
    run = relationship("AutopilotRunModel", back_populates="steps")
    
    __table_args__ = (
        Index("ix_autopilot_steps_run_index", "run_id", "step_index"),
    )


class RunActionModel(Base):
    """Immutable action record for audit trail"""
    __tablename__ = "autopilot_run_actions"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    action_id = Column(String(50), unique=True, nullable=False, index=True)
    run_id = Column(String(50), ForeignKey("autopilot_runs.run_id"), nullable=False)
    step_id = Column(String(50), nullable=False)
    
    # Action details
    action_type = Column(String(30), nullable=False)
    target = Column(String(200), nullable=True)
    
    # For control writes
    point_id = Column(String(100), nullable=True)
    value_before = Column(Float, nullable=True)
    value_after = Column(Float, nullable=True)
    ttl_seconds = Column(Integer, nullable=True)
    
    # Correlation
    correlation_id = Column(String(50), nullable=False, index=True)
    
    # Policy
    policy_approved = Column(Boolean, default=False)
    policy_id = Column(String(50), nullable=True)
    
    # Execution
    executed_at = Column(DateTime, default=datetime.utcnow, index=True)
    executed_by = Column(String(100), default="autopilot")
    
    # Result
    success = Column(Boolean, default=False)
    response = Column(JSONB, default=dict)
    error = Column(Text, nullable=True)
    
    # Relationships
    run = relationship("AutopilotRunModel", back_populates="actions")
    
    __table_args__ = (
        Index("ix_autopilot_actions_run_time", "run_id", "executed_at"),
    )


# =============================================================================
# Approval Models
# =============================================================================

class ApprovalModel(Base):
    """Human approval record"""
    __tablename__ = "autopilot_approvals"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    approval_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Context
    run_id = Column(String(50), ForeignKey("autopilot_runs.run_id"), nullable=False)
    step_id = Column(String(50), nullable=True)
    tenant_id = Column(String(100), nullable=False, index=True)
    
    # What needs approval
    approval_type = Column(String(30), nullable=False, default="step")
    risk_tier = Column(String(20), nullable=False, default="MEDIUM")
    
    # Proposed action details
    proposed_actions = Column(JSONB, default=list)
    rationale = Column(Text, nullable=True)
    evidence_snapshot = Column(JSONB, default=dict)
    
    # Status
    status = Column(String(30), nullable=False, default="pending", index=True)
    
    # Decision
    decision = Column(String(20), nullable=True)
    decided_by = Column(String(100), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    decision_notes = Column(Text, nullable=True)
    
    # Edits
    edited_params = Column(JSONB, default=dict)
    
    # Timing
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    expires_at = Column(DateTime, nullable=True)
    
    # Escalation
    escalation_triggered = Column(Boolean, default=False)
    
    # Relationships
    run = relationship("AutopilotRunModel", back_populates="approvals")
    
    __table_args__ = (
        Index("ix_autopilot_approvals_status_time", "status", "created_at"),
        Index("ix_autopilot_approvals_tenant_status", "tenant_id", "status"),
    )


# =============================================================================
# Checkpoint Models
# =============================================================================

class CheckpointModel(Base):
    """Workflow checkpoint for durable execution"""
    __tablename__ = "autopilot_checkpoints"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    checkpoint_id = Column(String(50), unique=True, nullable=False, index=True)
    run_id = Column(String(50), ForeignKey("autopilot_runs.run_id"), nullable=False)
    thread_id = Column(String(50), nullable=False, index=True)
    
    # State
    step_index = Column(Integer, nullable=False)
    run_status = Column(String(30), nullable=False)
    
    # Serialized state
    state_json = Column(Text, nullable=False, default="{}")
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(String(100), default="autopilot")
    reason = Column(String(100), nullable=True)
    
    # For replay
    parent_checkpoint_id = Column(String(50), nullable=True)
    is_replay = Column(Boolean, default=False)
    
    # Relationships
    run = relationship("AutopilotRunModel", back_populates="checkpoints")
    
    __table_args__ = (
        Index("ix_autopilot_checkpoints_run_time", "run_id", "created_at"),
    )


# =============================================================================
# Verification Models
# =============================================================================

class VerificationResultModel(Base):
    """Verification result after action execution"""
    __tablename__ = "autopilot_verifications"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    verification_id = Column(String(50), unique=True, nullable=False, index=True)
    run_id = Column(String(50), ForeignKey("autopilot_runs.run_id"), nullable=False)
    
    # Check definition
    check_expression = Column(Text, nullable=False)
    window_seconds = Column(Integer, default=900)
    must_hold = Column(Boolean, default=True)
    
    # Execution
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    
    # Result
    status = Column(String(30), nullable=False, default="pending")
    passed = Column(Boolean, default=False)
    
    # Evidence
    before_values = Column(JSONB, default=dict)
    after_values = Column(JSONB, default=dict)
    delta = Column(JSONB, default=dict)
    
    # Details
    message = Column(Text, nullable=True)
    stability_achieved_at = Column(DateTime, nullable=True)
    
    # Relationships
    run = relationship("AutopilotRunModel", back_populates="verifications")
    
    __table_args__ = (
        Index("ix_autopilot_verifications_run", "run_id"),
    )


# =============================================================================
# Evidence Pack Models
# =============================================================================

class EvidencePackModel(Base):
    """Immutable audit-grade evidence artifact"""
    __tablename__ = "autopilot_evidence_packs"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    pack_id = Column(String(50), unique=True, nullable=False, index=True)
    run_id = Column(String(50), nullable=False, index=True)
    incident_id = Column(String(50), nullable=False, index=True)
    
    # Identity
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=False)
    asset_id = Column(String(100), nullable=False)
    
    # Playbook
    playbook_id = Column(String(50), nullable=False)
    playbook_version = Column(String(20), nullable=False)
    
    # Timing
    incident_start = Column(DateTime, nullable=False)
    run_start = Column(DateTime, nullable=False)
    run_end = Column(DateTime, nullable=False)
    
    # Before state
    before_telemetry_window = Column(JSONB, default=dict)
    before_window_start = Column(DateTime, nullable=True)
    before_window_end = Column(DateTime, nullable=True)
    
    # Actions
    actions = Column(JSONB, default=list)
    approvals = Column(JSONB, default=list)
    
    # After state
    after_telemetry_window = Column(JSONB, default=dict)
    after_window_start = Column(DateTime, nullable=True)
    after_window_end = Column(DateTime, nullable=True)
    
    # Verification
    verification_results = Column(JSONB, default=list)
    
    # Outcome
    outcome = Column(String(30), nullable=False)
    outcome_reason = Column(Text, nullable=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    created_by = Column(String(100), default="autopilot")
    
    # Immutability
    content_hash = Column(String(64), nullable=True)
    signed_at = Column(DateTime, nullable=True)
    
    # Links
    cmms_ticket_ids = Column(JSONB, default=list)
    
    # Storage
    blob_uri = Column(String(500), nullable=True)  # For PDF/JSON export
    
    __table_args__ = (
        Index("ix_autopilot_evidence_run", "run_id"),
        Index("ix_autopilot_evidence_tenant_time", "tenant_id", "created_at"),
    )


# =============================================================================
# Policy Models
# =============================================================================

class PolicyModel(Base):
    """Site/tenant policy constraints"""
    __tablename__ = "autopilot_policies"
    
    id = Column(UUID(as_uuid=False), primary_key=True, default=generate_uuid)
    policy_id = Column(String(50), unique=True, nullable=False, index=True)
    
    # Scope
    tenant_id = Column(String(100), nullable=False, index=True)
    site_id = Column(String(100), nullable=True, index=True)
    asset_id = Column(String(100), nullable=True)
    
    # Name
    name = Column(String(200), nullable=False)
    description = Column(Text, nullable=True)
    
    # Risk tier requirements
    auto_approve_risk_tiers = Column(JSONB, default=["LOW"])
    require_approval_risk_tiers = Column(JSONB, default=["MEDIUM", "HIGH"])
    require_two_person_approval = Column(Boolean, default=False)
    
    # Constraints (JSONB for flexibility)
    constraints = Column(JSONB, default=list)
    
    # Global limits
    max_setpoint_delta = Column(Float, default=5.0)
    max_override_duration_seconds = Column(Integer, default=3600)
    max_commands_per_asset_per_hour = Column(Integer, default=10)
    
    # Store hours
    store_hours_start = Column(Integer, default=6)
    store_hours_end = Column(Integer, default=22)
    
    # Lifecycle
    is_active = Column(Boolean, default=True)
    effective_from = Column(DateTime, default=datetime.utcnow)
    retired_at = Column(DateTime, nullable=True)
    
    # Versioning
    version = Column(String(20), default="1.0.0")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_autopilot_policies_tenant_site", "tenant_id", "site_id"),
        Index("ix_autopilot_policies_active", "is_active"),
    )
