"""Add dispatched_at and source_alert_id columns to pdm_work_orders.

Revision ID: 006
Revises: 005
Create Date: 2026-02-11

These columns enable:
- dispatched_at: precise MTTD (mean time to dispatch) computation for A/B testing
- source_alert_id: direct alert-to-WO conversion tracking (replaces loose asset-level join)
"""

from alembic import context, op
import sqlalchemy as sa

revision = "006"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if context.is_offline_mode():
        op.add_column(
            "pdm_work_orders",
            sa.Column(
                "dispatched_at",
                sa.DateTime(),
                nullable=True,
                comment="When provider was dispatched — enables precise MTTD",
            ),
        )
        op.add_column(
            "pdm_work_orders",
            sa.Column(
                "source_alert_id",
                sa.String(20),
                nullable=True,
                comment="FK-light to pdm_alerts.alert_id — enables alert-to-WO conversion tracking",
            ),
        )
        op.create_index("ix_pdm_wo_source_alert", "pdm_work_orders", ["source_alert_id"])
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pdm_work_orders" not in inspector.get_table_names():
        return

    column_names = {col["name"] for col in inspector.get_columns("pdm_work_orders")}

    if "dispatched_at" not in column_names:
        op.add_column(
            "pdm_work_orders",
            sa.Column(
                "dispatched_at",
                sa.DateTime(),
                nullable=True,
                comment="When provider was dispatched — enables precise MTTD",
            ),
        )
    if "source_alert_id" not in column_names:
        op.add_column(
            "pdm_work_orders",
            sa.Column(
                "source_alert_id",
                sa.String(20),
                nullable=True,
                comment="FK-light to pdm_alerts.alert_id — enables alert-to-WO conversion tracking",
            ),
        )

    index_names = {idx["name"] for idx in inspector.get_indexes("pdm_work_orders")}
    if "ix_pdm_wo_source_alert" not in index_names:
        op.create_index("ix_pdm_wo_source_alert", "pdm_work_orders", ["source_alert_id"])


def downgrade() -> None:
    if context.is_offline_mode():
        op.drop_index("ix_pdm_wo_source_alert", table_name="pdm_work_orders")
        op.drop_column("pdm_work_orders", "source_alert_id")
        op.drop_column("pdm_work_orders", "dispatched_at")
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "pdm_work_orders" not in inspector.get_table_names():
        return

    index_names = {idx["name"] for idx in inspector.get_indexes("pdm_work_orders")}
    if "ix_pdm_wo_source_alert" in index_names:
        op.drop_index("ix_pdm_wo_source_alert", table_name="pdm_work_orders")

    column_names = {col["name"] for col in inspector.get_columns("pdm_work_orders")}
    if "source_alert_id" in column_names:
        op.drop_column("pdm_work_orders", "source_alert_id")
    if "dispatched_at" in column_names:
        op.drop_column("pdm_work_orders", "dispatched_at")
