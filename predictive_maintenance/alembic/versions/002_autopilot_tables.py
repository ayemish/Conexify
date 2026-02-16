"""Add autopilot tables

Revision ID: 002_autopilot
Revises: 001_initial
Create Date: 2026-02-09

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '002_autopilot'
down_revision = '001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Playbooks
    op.create_table(
        'autopilot_playbooks',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('playbook_id', sa.String(50), nullable=False),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('asset_class', sa.String(50), nullable=False),
        sa.Column('fault_type', sa.String(100), nullable=False),
        sa.Column('risk_tier', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('current_version', sa.String(20), nullable=False, server_default='1.0.0'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('retired_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('playbook_id'),
    )
    op.create_index('ix_autopilot_playbooks_playbook_id', 'autopilot_playbooks', ['playbook_id'])
    op.create_index('ix_autopilot_playbooks_class_fault', 'autopilot_playbooks', ['asset_class', 'fault_type'])
    op.create_index('ix_autopilot_playbooks_risk_active', 'autopilot_playbooks', ['risk_tier', 'is_active'])

    # Playbook Versions
    op.create_table(
        'autopilot_playbook_versions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('playbook_id', sa.String(50), sa.ForeignKey('autopilot_playbooks.playbook_id'), nullable=False),
        sa.Column('version', sa.String(20), nullable=False),
        sa.Column('definition', postgresql.JSONB(), nullable=False),
        sa.Column('triggers', postgresql.JSONB(), nullable=True),
        sa.Column('preconditions', postgresql.JSONB(), nullable=True),
        sa.Column('steps', postgresql.JSONB(), nullable=True),
        sa.Column('verification', postgresql.JSONB(), nullable=True),
        sa.Column('escalation', postgresql.JSONB(), nullable=True),
        sa.Column('evidence_requirements', postgresql.JSONB(), nullable=True),
        sa.Column('schema_version', sa.String(20), nullable=True, server_default='1.0'),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('effective_from', sa.DateTime(), nullable=True),
        sa.Column('retired_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_autopilot_pb_versions_playbook', 'autopilot_playbook_versions', ['playbook_id', 'version'])

    # Incidents
    op.create_table(
        'autopilot_incidents',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('incident_id', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=False),
        sa.Column('asset_id', sa.String(100), nullable=False),
        sa.Column('fault_type', sa.String(100), nullable=False),
        sa.Column('severity', sa.String(20), nullable=False, server_default='medium'),
        sa.Column('source', sa.String(50), nullable=False),
        sa.Column('start_ts', sa.DateTime(), nullable=False),
        sa.Column('end_ts', sa.DateTime(), nullable=True),
        sa.Column('detected_at', sa.DateTime(), nullable=False),
        sa.Column('trigger_evidence', postgresql.JSONB(), nullable=True),
        sa.Column('point_values', postgresql.JSONB(), nullable=True),
        sa.Column('window_start', sa.DateTime(), nullable=True),
        sa.Column('window_end', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='open'),
        sa.Column('matched_playbook_id', sa.String(50), nullable=True),
        sa.Column('match_reason', sa.Text(), nullable=True),
        sa.Column('dedup_key', sa.String(200), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('closed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('incident_id'),
    )
    op.create_index('ix_autopilot_incidents_incident_id', 'autopilot_incidents', ['incident_id'])
    op.create_index('ix_autopilot_incidents_tenant_site', 'autopilot_incidents', ['tenant_id', 'site_id'])
    op.create_index('ix_autopilot_incidents_asset_status', 'autopilot_incidents', ['asset_id', 'status'])
    op.create_index('ix_autopilot_incidents_fault_time', 'autopilot_incidents', ['fault_type', 'detected_at'])
    op.create_index('ix_autopilot_incidents_dedup', 'autopilot_incidents', ['dedup_key'])

    # AutopilotRuns
    op.create_table(
        'autopilot_runs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('incident_id', sa.String(50), sa.ForeignKey('autopilot_incidents.incident_id'), nullable=False),
        sa.Column('playbook_id', sa.String(50), nullable=False),
        sa.Column('playbook_version', sa.String(20), nullable=False),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=False),
        sa.Column('asset_id', sa.String(100), nullable=False),
        sa.Column('thread_id', sa.String(50), nullable=False),
        sa.Column('current_checkpoint_id', sa.String(50), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='planning'),
        sa.Column('risk_tier', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('current_step_index', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('pending_approval_id', sa.String(50), nullable=True),
        sa.Column('evidence_pack_id', sa.String(50), nullable=True),
        sa.Column('outcome', sa.String(30), nullable=True),
        sa.Column('outcome_reason', sa.Text(), nullable=True),
        sa.Column('plan_rationale', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id'),
    )
    op.create_index('ix_autopilot_runs_run_id', 'autopilot_runs', ['run_id'])
    op.create_index('ix_autopilot_runs_incident', 'autopilot_runs', ['incident_id'])
    op.create_index('ix_autopilot_runs_thread', 'autopilot_runs', ['thread_id'])
    op.create_index('ix_autopilot_runs_status_time', 'autopilot_runs', ['status', 'created_at'])
    op.create_index('ix_autopilot_runs_asset_time', 'autopilot_runs', ['asset_id', 'created_at'])

    # Run Steps
    op.create_table(
        'autopilot_run_steps',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('step_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('autopilot_runs.run_id'), nullable=False),
        sa.Column('playbook_step_id', sa.String(50), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('action_type', sa.String(30), nullable=False),
        sa.Column('params', postgresql.JSONB(), nullable=True),
        sa.Column('requires_approval', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('approval_id', sa.String(50), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('result', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.Column('on_error', sa.String(20), nullable=True, server_default='ESCALATE'),
        sa.Column('retry_count', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('max_retries', sa.Integer(), nullable=True, server_default='3'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('step_id'),
    )
    op.create_index('ix_autopilot_steps_step_id', 'autopilot_run_steps', ['step_id'])
    op.create_index('ix_autopilot_steps_run_index', 'autopilot_run_steps', ['run_id', 'step_index'])

    # Run Actions
    op.create_table(
        'autopilot_run_actions',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('action_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('autopilot_runs.run_id'), nullable=False),
        sa.Column('step_id', sa.String(50), nullable=False),
        sa.Column('action_type', sa.String(30), nullable=False),
        sa.Column('target', sa.String(200), nullable=True),
        sa.Column('point_id', sa.String(100), nullable=True),
        sa.Column('value_before', sa.Float(), nullable=True),
        sa.Column('value_after', sa.Float(), nullable=True),
        sa.Column('ttl_seconds', sa.Integer(), nullable=True),
        sa.Column('correlation_id', sa.String(50), nullable=False),
        sa.Column('policy_approved', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('policy_id', sa.String(50), nullable=True),
        sa.Column('executed_at', sa.DateTime(), nullable=True),
        sa.Column('executed_by', sa.String(100), nullable=True, server_default='autopilot'),
        sa.Column('success', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('response', postgresql.JSONB(), nullable=True),
        sa.Column('error', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('action_id'),
    )
    op.create_index('ix_autopilot_actions_action_id', 'autopilot_run_actions', ['action_id'])
    op.create_index('ix_autopilot_actions_correlation', 'autopilot_run_actions', ['correlation_id'])
    op.create_index('ix_autopilot_actions_run_time', 'autopilot_run_actions', ['run_id', 'executed_at'])

    # Approvals
    op.create_table(
        'autopilot_approvals',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('approval_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('autopilot_runs.run_id'), nullable=False),
        sa.Column('step_id', sa.String(50), nullable=True),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('approval_type', sa.String(30), nullable=False, server_default='step'),
        sa.Column('risk_tier', sa.String(20), nullable=False, server_default='MEDIUM'),
        sa.Column('proposed_actions', postgresql.JSONB(), nullable=True),
        sa.Column('rationale', sa.Text(), nullable=True),
        sa.Column('evidence_snapshot', postgresql.JSONB(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('decision', sa.String(20), nullable=True),
        sa.Column('decided_by', sa.String(100), nullable=True),
        sa.Column('decided_at', sa.DateTime(), nullable=True),
        sa.Column('decision_notes', sa.Text(), nullable=True),
        sa.Column('edited_params', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=True),
        sa.Column('escalation_triggered', sa.Boolean(), nullable=True, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('approval_id'),
    )
    op.create_index('ix_autopilot_approvals_approval_id', 'autopilot_approvals', ['approval_id'])
    op.create_index('ix_autopilot_approvals_status_time', 'autopilot_approvals', ['status', 'created_at'])
    op.create_index('ix_autopilot_approvals_tenant_status', 'autopilot_approvals', ['tenant_id', 'status'])

    # Checkpoints
    op.create_table(
        'autopilot_checkpoints',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('checkpoint_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('autopilot_runs.run_id'), nullable=False),
        sa.Column('thread_id', sa.String(50), nullable=False),
        sa.Column('step_index', sa.Integer(), nullable=False),
        sa.Column('run_status', sa.String(30), nullable=False),
        sa.Column('state_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True, server_default='autopilot'),
        sa.Column('reason', sa.String(100), nullable=True),
        sa.Column('parent_checkpoint_id', sa.String(50), nullable=True),
        sa.Column('is_replay', sa.Boolean(), nullable=True, server_default='false'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('checkpoint_id'),
    )
    op.create_index('ix_autopilot_checkpoints_checkpoint_id', 'autopilot_checkpoints', ['checkpoint_id'])
    op.create_index('ix_autopilot_checkpoints_thread', 'autopilot_checkpoints', ['thread_id'])
    op.create_index('ix_autopilot_checkpoints_run_time', 'autopilot_checkpoints', ['run_id', 'created_at'])

    # Verifications
    op.create_table(
        'autopilot_verifications',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('verification_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), sa.ForeignKey('autopilot_runs.run_id'), nullable=False),
        sa.Column('check_expression', sa.Text(), nullable=False),
        sa.Column('window_seconds', sa.Integer(), nullable=True, server_default='900'),
        sa.Column('must_hold', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(30), nullable=False, server_default='pending'),
        sa.Column('passed', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('before_values', postgresql.JSONB(), nullable=True),
        sa.Column('after_values', postgresql.JSONB(), nullable=True),
        sa.Column('delta', postgresql.JSONB(), nullable=True),
        sa.Column('message', sa.Text(), nullable=True),
        sa.Column('stability_achieved_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('verification_id'),
    )
    op.create_index('ix_autopilot_verifications_verification_id', 'autopilot_verifications', ['verification_id'])
    op.create_index('ix_autopilot_verifications_run', 'autopilot_verifications', ['run_id'])

    # Evidence Packs
    op.create_table(
        'autopilot_evidence_packs',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('pack_id', sa.String(50), nullable=False),
        sa.Column('run_id', sa.String(50), nullable=False),
        sa.Column('incident_id', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=False),
        sa.Column('asset_id', sa.String(100), nullable=False),
        sa.Column('playbook_id', sa.String(50), nullable=False),
        sa.Column('playbook_version', sa.String(20), nullable=False),
        sa.Column('incident_start', sa.DateTime(), nullable=False),
        sa.Column('run_start', sa.DateTime(), nullable=False),
        sa.Column('run_end', sa.DateTime(), nullable=False),
        sa.Column('before_telemetry_window', postgresql.JSONB(), nullable=True),
        sa.Column('before_window_start', sa.DateTime(), nullable=True),
        sa.Column('before_window_end', sa.DateTime(), nullable=True),
        sa.Column('actions', postgresql.JSONB(), nullable=True),
        sa.Column('approvals', postgresql.JSONB(), nullable=True),
        sa.Column('after_telemetry_window', postgresql.JSONB(), nullable=True),
        sa.Column('after_window_start', sa.DateTime(), nullable=True),
        sa.Column('after_window_end', sa.DateTime(), nullable=True),
        sa.Column('verification_results', postgresql.JSONB(), nullable=True),
        sa.Column('outcome', sa.String(30), nullable=False),
        sa.Column('outcome_reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('created_by', sa.String(100), nullable=True, server_default='autopilot'),
        sa.Column('content_hash', sa.String(64), nullable=True),
        sa.Column('signed_at', sa.DateTime(), nullable=True),
        sa.Column('cmms_ticket_ids', postgresql.JSONB(), nullable=True),
        sa.Column('blob_uri', sa.String(500), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('pack_id'),
    )
    op.create_index('ix_autopilot_evidence_pack_id', 'autopilot_evidence_packs', ['pack_id'])
    op.create_index('ix_autopilot_evidence_run', 'autopilot_evidence_packs', ['run_id'])
    op.create_index('ix_autopilot_evidence_tenant_time', 'autopilot_evidence_packs', ['tenant_id', 'created_at'])

    # Policies
    op.create_table(
        'autopilot_policies',
        sa.Column('id', postgresql.UUID(as_uuid=False), nullable=False),
        sa.Column('policy_id', sa.String(50), nullable=False),
        sa.Column('tenant_id', sa.String(100), nullable=False),
        sa.Column('site_id', sa.String(100), nullable=True),
        sa.Column('asset_id', sa.String(100), nullable=True),
        sa.Column('name', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('auto_approve_risk_tiers', postgresql.JSONB(), nullable=True),
        sa.Column('require_approval_risk_tiers', postgresql.JSONB(), nullable=True),
        sa.Column('require_two_person_approval', sa.Boolean(), nullable=True, server_default='false'),
        sa.Column('constraints', postgresql.JSONB(), nullable=True),
        sa.Column('max_setpoint_delta', sa.Float(), nullable=True, server_default='5.0'),
        sa.Column('max_override_duration_seconds', sa.Integer(), nullable=True, server_default='3600'),
        sa.Column('max_commands_per_asset_per_hour', sa.Integer(), nullable=True, server_default='10'),
        sa.Column('store_hours_start', sa.Integer(), nullable=True, server_default='6'),
        sa.Column('store_hours_end', sa.Integer(), nullable=True, server_default='22'),
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='true'),
        sa.Column('effective_from', sa.DateTime(), nullable=True),
        sa.Column('retired_at', sa.DateTime(), nullable=True),
        sa.Column('version', sa.String(20), nullable=True, server_default='1.0.0'),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('policy_id'),
    )
    op.create_index('ix_autopilot_policies_policy_id', 'autopilot_policies', ['policy_id'])
    op.create_index('ix_autopilot_policies_tenant_site', 'autopilot_policies', ['tenant_id', 'site_id'])
    op.create_index('ix_autopilot_policies_active', 'autopilot_policies', ['is_active'])


def downgrade() -> None:
    op.drop_table('autopilot_policies')
    op.drop_table('autopilot_evidence_packs')
    op.drop_table('autopilot_verifications')
    op.drop_table('autopilot_checkpoints')
    op.drop_table('autopilot_approvals')
    op.drop_table('autopilot_run_actions')
    op.drop_table('autopilot_run_steps')
    op.drop_table('autopilot_runs')
    op.drop_table('autopilot_incidents')
    op.drop_table('autopilot_playbook_versions')
    op.drop_table('autopilot_playbooks')
