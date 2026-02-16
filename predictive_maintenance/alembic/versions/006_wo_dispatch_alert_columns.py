"""Add dispatched_at and source_alert_id columns to pdm_work_orders.

Revision ID: 006
Revises: 005
Create Date: 2026-02-11

These columns enable:
- dispatched_at: precise MTTD (mean time to dispatch) computation for A/B testing
- source_alert_id: direct alert-to-WO conversion tracking (replaces loose asset-level join)
"""

from alembic import op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pdm_work_orders",
        sa.Column("dispatched_at", sa.DateTime(), nullable=True,
                  comment="When provider was dispatched — enables precise MTTD"),
    )
    op.add_column(
        "pdm_work_orders",
        sa.Column("source_alert_id", sa.String(20), nullable=True,
                  comment="FK-light to pdm_alerts.alert_id — enables alert-to-WO conversion tracking"),
    )
    op.create_index("ix_pdm_wo_source_alert", "pdm_work_orders", ["source_alert_id"])


def downgrade() -> None:
    op.drop_index("ix_pdm_wo_source_alert", table_name="pdm_work_orders")
    op.drop_column("pdm_work_orders", "source_alert_id")
    op.drop_column("pdm_work_orders", "dispatched_at")
