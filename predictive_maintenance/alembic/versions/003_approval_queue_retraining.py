"""Add approval queue and retraining request tables

Revision ID: 003
Revises: 002_autopilot
Create Date: 2026-02-10

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003"
down_revision = "002_autopilot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pdm_approval_queue",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("item_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("approval_id", sa.String(100), nullable=False, index=True),
        sa.Column("run_id", sa.String(100), nullable=False, index=True),
        sa.Column("incident_id", sa.String(100), nullable=False, index=True),
        sa.Column("playbook_id", sa.String(100), nullable=False),
        sa.Column("step_id", sa.String(100), nullable=False),
        sa.Column("tenant_id", sa.String(100), nullable=False, index=True),
        sa.Column("site_id", sa.String(100), nullable=False),
        sa.Column("asset_id", sa.String(100), nullable=False, index=True),
        sa.Column("item_type", sa.String(50), server_default="action_approval"),
        sa.Column("risk_tier", sa.String(20), server_default="MEDIUM"),
        sa.Column("priority", sa.Integer, server_default="50"),
        sa.Column("proposed_actions", postgresql.JSONB, server_default="[]"),
        sa.Column("action_summary", sa.Text, server_default=""),
        sa.Column("telemetry_snapshot", postgresql.JSONB, server_default="{}"),
        sa.Column("fault_context", postgresql.JSONB, server_default="{}"),
        sa.Column("evidence", postgresql.JSONB, server_default="{}"),
        sa.Column("status", sa.String(30), server_default="pending", index=True),
        sa.Column("explanation_data", postgresql.JSONB, nullable=True),
        sa.Column("explanation_error", sa.Text, nullable=True),
        sa.Column("validation_data", postgresql.JSONB, nullable=True),
        sa.Column("validation_error", sa.Text, nullable=True),
        sa.Column("decision_data", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
        sa.Column("updated_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime, nullable=True),
        sa.Column("assigned_to", sa.String(100), nullable=True),
        sa.Column("assigned_at", sa.DateTime, nullable=True),
        sa.Column("escalation_level", sa.Integer, server_default="0"),
    )
    op.create_index("ix_pdm_aq_tenant_status", "pdm_approval_queue", ["tenant_id", "status"])
    op.create_index("ix_pdm_aq_priority", "pdm_approval_queue", ["priority"])

    op.create_table(
        "pdm_retraining_requests",
        sa.Column("id", postgresql.UUID(as_uuid=False), primary_key=True),
        sa.Column("request_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("trigger_type", sa.String(30), nullable=False, index=True),
        sa.Column("model_id", sa.String(100), nullable=True, index=True),
        sa.Column("asset_id", sa.String(100), nullable=True, index=True),
        sa.Column("fault_type", sa.String(50), nullable=True),
        sa.Column("false_positive_rate", sa.Float, server_default="0"),
        sa.Column("false_negative_rate", sa.Float, server_default="0"),
        sa.Column("mean_absolute_error", sa.Float, server_default="0"),
        sa.Column("n_incorrect_recent", sa.Integer, server_default="0"),
        sa.Column("n_observations_since_train", sa.Integer, server_default="0"),
        sa.Column("evidence", postgresql.JSONB, server_default="{}"),
        sa.Column("status", sa.String(30), server_default="pending", index=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_pdm_retrain_status_type", "pdm_retraining_requests", ["status", "trigger_type"])


def downgrade() -> None:
    op.drop_table("pdm_retraining_requests")
    op.drop_table("pdm_approval_queue")
