"""Baseline migration placeholder for legacy bootstrap.

Revision ID: 001_initial
Revises:
Create Date: 2026-02-24
"""

from alembic import context, op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Establish migration lineage baseline.

    Existing deployments may already have tables created by early bootstrap
    code; this no-op baseline allows deterministic chains for later revisions.
    """
    def _create_legacy_work_orders() -> None:
        op.create_table(
            "pdm_work_orders",
            sa.Column("id", sa.String(length=36), nullable=False),
            sa.Column("wo_id", sa.String(length=100), nullable=False),
            sa.Column("asset_id", sa.String(length=100), nullable=False),
            sa.Column("site_id", sa.String(length=100), nullable=False),
            sa.Column("wo_type", sa.String(length=50), nullable=True),
            sa.Column("priority", sa.String(length=20), nullable=True),
            sa.Column("status", sa.String(length=30), nullable=True),
            sa.Column("cost", sa.Float(), nullable=True),
            sa.Column("labor_hours", sa.Float(), nullable=True),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("resolution", sa.Text(), nullable=True),
            sa.Column("provider", sa.String(length=50), nullable=True),
            sa.Column("opened_at", sa.DateTime(), nullable=False),
            sa.Column("closed_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("wo_id"),
        )
        op.create_index("ix_pdm_work_orders_wo_id", "pdm_work_orders", ["wo_id"], unique=False)
        op.create_index("ix_pdm_work_orders_asset_id", "pdm_work_orders", ["asset_id"], unique=False)
        op.create_index("ix_pdm_work_orders_site_id", "pdm_work_orders", ["site_id"], unique=False)
        op.create_index("ix_pdm_wo_site_type", "pdm_work_orders", ["site_id", "wo_type"], unique=False)
        op.create_index("ix_pdm_wo_asset_opened", "pdm_work_orders", ["asset_id", "opened_at"], unique=False)

    if context.is_offline_mode():
        _create_legacy_work_orders()
        return

    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # Legacy deployments often had this table created outside Alembic.
    # Create it only when absent so a fresh migration chain is valid.
    if "pdm_work_orders" not in existing_tables:
        _create_legacy_work_orders()


def downgrade() -> None:
    """No-op baseline downgrade."""
    op.execute(sa.text("SELECT 1"))
