"""Add KPI pipeline and result tables.

Revision ID: 005
Revises: 004
Create Date: 2026-02-11

Tables:
- pdm_kpi_pipeline_runs — tracks KPI orchestration pipeline runs
- pdm_kpi_results — individual KPI computation results per run
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- pdm_kpi_pipeline_runs ---
    op.create_table(
        "pdm_kpi_pipeline_runs",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column("run_id", sa.String(50), unique=True, nullable=False, index=True),
        sa.Column("site_id", sa.String(100), nullable=False, index=True),
        sa.Column("status", sa.String(30), server_default="pending", index=True),
        sa.Column("phase", sa.String(50), server_default=""),
        sa.Column("phase_index", sa.Integer, server_default="0"),
        sa.Column("total_phases", sa.Integer, server_default="7"),
        sa.Column("crew_statuses", JSONB, server_default="{}"),
        sa.Column("result_payload", JSONB, nullable=True),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("completed_at", sa.DateTime, nullable=True),
        sa.Column("duration_seconds", sa.Float, nullable=True),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now(), index=True),
    )
    op.create_index(
        "ix_pdm_kpi_run_site_status",
        "pdm_kpi_pipeline_runs",
        ["site_id", "status"],
    )

    # --- pdm_kpi_results ---
    op.create_table(
        "pdm_kpi_results",
        sa.Column("id", UUID(as_uuid=False), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(50),
            sa.ForeignKey("pdm_kpi_pipeline_runs.run_id"),
            nullable=False,
            index=True,
        ),
        sa.Column("site_id", sa.String(100), nullable=False, index=True),
        sa.Column("kpi_name", sa.String(100), nullable=False, index=True),
        sa.Column("display_name", sa.String(200), server_default=""),
        sa.Column("category", sa.String(100), server_default=""),
        sa.Column("savings_low", sa.Float, server_default="0"),
        sa.Column("savings_medium", sa.Float, server_default="0"),
        sa.Column("savings_high", sa.Float, server_default="0"),
        sa.Column("confidence", sa.Float, server_default="0"),
        sa.Column("status", sa.String(30), server_default="pending"),
        sa.Column("narrative", sa.Text, server_default=""),
        sa.Column("assumptions", JSONB, server_default="[]"),
        sa.Column("supporting_metrics", JSONB, server_default="{}"),
        sa.Column("data_points_used", sa.Integer, server_default="0"),
        sa.Column("data_coverage_pct", sa.Float, server_default="0"),
        sa.Column("computed_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_pdm_kpi_result_run_kpi",
        "pdm_kpi_results",
        ["run_id", "kpi_name"],
    )
    op.create_index(
        "ix_pdm_kpi_result_site_kpi",
        "pdm_kpi_results",
        ["site_id", "kpi_name"],
    )


def downgrade() -> None:
    op.drop_table("pdm_kpi_results")
    op.drop_table("pdm_kpi_pipeline_runs")
