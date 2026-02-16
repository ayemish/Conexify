"""Add governance enterprise module tables.

Revision ID: 004
Revises: 003
Create Date: 2026-02-10

Tables:
- gov_lineage_events
- gov_model_versions
- gov_drift_alerts
- gov_quality_reports
- gov_exceptions
- gov_sla_measurements
- gov_security_controls
- gov_compliance_reports
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- gov_lineage_events ---
    op.create_table(
        "gov_lineage_events",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("event_type", sa.String(20), nullable=False, index=True),
        sa.Column("job_id", sa.String(64), nullable=False, index=True),
        sa.Column("job_name", sa.String(200)),
        sa.Column("job_type", sa.String(60)),
        sa.Column("run_id", sa.String(64), nullable=False, index=True),
        sa.Column("parent_run_id", sa.String(64)),
        sa.Column("company_id", sa.String(100), index=True),
        sa.Column("correlation_id", sa.String(64), index=True),
        sa.Column("input_datasets", JSONB, server_default="[]"),
        sa.Column("output_datasets", JSONB, server_default="[]"),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("status", sa.String(20)),
        sa.Column("error_message", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_gov_lineage_company_ts", "gov_lineage_events", ["company_id", "created_at"])

    # --- gov_model_versions ---
    op.create_table(
        "gov_model_versions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("version_id", sa.String(64), unique=True, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False, index=True),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("model_type", sa.String(60)),
        sa.Column("stage", sa.String(30), nullable=False, index=True),
        sa.Column("artifact_uri", sa.Text),
        sa.Column("artifact_hash", sa.String(64)),
        sa.Column("training_run_id", sa.String(64)),
        sa.Column("metrics", JSONB, server_default="{}"),
        sa.Column("parameters", JSONB, server_default="{}"),
        sa.Column("tags", JSONB, server_default="{}"),
        sa.Column("promoted_by", sa.String(100)),
        sa.Column("promoted_ts", sa.DateTime),
        sa.Column("rollback_reason", sa.Text),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_gov_model_name_stage", "gov_model_versions", ["model_name", "stage"])

    # --- gov_drift_alerts ---
    op.create_table(
        "gov_drift_alerts",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("alert_id", sa.String(64), unique=True, nullable=False),
        sa.Column("model_name", sa.String(200), nullable=False, index=True),
        sa.Column("drift_type", sa.String(40), nullable=False),
        sa.Column("severity", sa.String(30), nullable=False, index=True),
        sa.Column("metric_name", sa.String(100)),
        sa.Column("baseline_value", sa.Float),
        sa.Column("current_value", sa.Float),
        sa.Column("threshold", sa.Float),
        sa.Column("description", sa.Text),
        sa.Column("resolved", sa.Boolean, server_default="false", index=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )

    # --- gov_quality_reports ---
    op.create_table(
        "gov_quality_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("report_id", sa.String(64), unique=True, nullable=False),
        sa.Column("suite_id", sa.String(64), nullable=False, index=True),
        sa.Column("dataset_name", sa.String(200), nullable=False, index=True),
        sa.Column("total", sa.Integer),
        sa.Column("passed", sa.Integer),
        sa.Column("failed", sa.Integer),
        sa.Column("warnings", sa.Integer),
        sa.Column("pass_rate", sa.Float),
        sa.Column("overall_score", sa.Float),
        sa.Column("dimension_scores", JSONB, server_default="{}"),
        sa.Column("gate_decision", sa.String(20), nullable=False, index=True),
        sa.Column("gate_reason", sa.Text),
        sa.Column("duration_ms", sa.Integer),
        sa.Column("results_detail", JSONB, server_default="[]"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_gov_qr_dataset_gate", "gov_quality_reports", ["dataset_name", "gate_decision"])

    # --- gov_exceptions ---
    op.create_table(
        "gov_exceptions",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("exception_id", sa.String(64), unique=True, nullable=False),
        sa.Column("exception_type", sa.String(40), nullable=False, index=True),
        sa.Column("priority", sa.String(20), nullable=False, index=True),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("title", sa.String(500)),
        sa.Column("description", sa.Text),
        sa.Column("company_id", sa.String(100), index=True),
        sa.Column("location_id", sa.String(100)),
        sa.Column("asset_id", sa.String(100)),
        sa.Column("kpi_name", sa.String(100)),
        sa.Column("assigned_to", sa.String(100)),
        sa.Column("escalated_to", sa.String(100)),
        sa.Column("resolution", sa.Text),
        sa.Column("root_cause", sa.Text),
        sa.Column("preventive_action", sa.Text),
        sa.Column("blocked_kpis", JSONB, server_default="[]"),
        sa.Column("sla_due_ts", sa.DateTime),
        sa.Column("triaged_ts", sa.DateTime),
        sa.Column("resolved_ts", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index("ix_gov_exc_company_status", "gov_exceptions", ["company_id", "status"])

    # --- gov_sla_measurements ---
    op.create_table(
        "gov_sla_measurements",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("sla_name", sa.String(200), nullable=False, index=True),
        sa.Column("company_id", sa.String(100), index=True),
        sa.Column("measured_value", sa.Float, nullable=False),
        sa.Column("threshold", sa.Float),
        sa.Column("breached", sa.Boolean, server_default="false", index=True),
        sa.Column("measurement_type", sa.String(40)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )

    # --- gov_security_controls ---
    op.create_table(
        "gov_security_controls",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("control_id", sa.String(64), unique=True, nullable=False),
        sa.Column("framework", sa.String(40), nullable=False, index=True),
        sa.Column("category", sa.String(100)),
        sa.Column("name", sa.String(300)),
        sa.Column("description", sa.Text),
        sa.Column("status", sa.String(30), nullable=False, index=True),
        sa.Column("evidence", JSONB, server_default="{}"),
        sa.Column("last_assessed_ts", sa.DateTime),
        sa.Column("next_review_ts", sa.DateTime),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    # --- gov_compliance_reports ---
    op.create_table(
        "gov_compliance_reports",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("report_id", sa.String(64), unique=True, nullable=False),
        sa.Column("framework", sa.String(40), nullable=False, index=True),
        sa.Column("company_id", sa.String(100), index=True),
        sa.Column("total_controls", sa.Integer),
        sa.Column("implemented", sa.Integer),
        sa.Column("not_implemented", sa.Integer),
        sa.Column("partial", sa.Integer),
        sa.Column("compliance_rate", sa.Float),
        sa.Column("findings", JSONB, server_default="[]"),
        sa.Column("generated_by", sa.String(100)),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )


def downgrade() -> None:
    op.drop_table("gov_compliance_reports")
    op.drop_table("gov_security_controls")
    op.drop_table("gov_sla_measurements")
    op.drop_table("gov_exceptions")
    op.drop_table("gov_quality_reports")
    op.drop_table("gov_drift_alerts")
    op.drop_table("gov_model_versions")
    op.drop_table("gov_lineage_events")
