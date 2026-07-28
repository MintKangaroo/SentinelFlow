"""Create auditable workflow runs, step state, and immutable events.

Revision ID: 20260728_0004
Revises: 20260728_0003
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0004"
down_revision: str | None = "20260728_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workflow aggregate, snapshotted steps, and append-only events."""
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("playbook_id", sa.Uuid(), nullable=False),
        sa.Column("playbook_version_id", sa.Uuid(), nullable=False),
        sa.Column("playbook_version", sa.Integer(), nullable=False),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False),
        sa.CheckConstraint("version >= 1", name="workflow_version_positive"),
        sa.CheckConstraint("playbook_version >= 1", name="workflow_playbook_version_positive"),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'awaiting_approval', 'compensating', "
            "'succeeded', 'failed', 'cancelled')",
            name="workflow_status",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_workflow_runs_incident_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["playbook_version_id", "workspace_id"],
            ["playbook_versions.id", "playbook_versions.workspace_id"],
            name="fk_workflow_runs_playbook_version_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_runs"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_workflow_runs_id_workspace"),
    )
    op.create_index("ix_workflow_runs_workspace_id", "workflow_runs", ["workspace_id"])
    op.create_index(
        "ix_workflow_runs_workspace_status_updated",
        "workflow_runs",
        ["workspace_id", "status", "updated_at"],
    )

    op.create_table(
        "workflow_steps",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("risk", sa.String(length=8), nullable=False),
        sa.Column("adapter", sa.String(length=100), nullable=True),
        sa.Column("operation", sa.String(length=100), nullable=True),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("rollback_strategy", sa.String(length=10), nullable=True),
        sa.Column("rollback_operation", sa.String(length=100), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "output",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("position >= 0", name="workflow_step_position_nonnegative"),
        sa.CheckConstraint("timeout_seconds BETWEEN 1 AND 3600", name="workflow_step_timeout"),
        sa.CheckConstraint("max_attempts BETWEEN 1 AND 10", name="workflow_step_attempt_budget"),
        sa.CheckConstraint("attempt >= 0", name="workflow_step_attempt_nonnegative"),
        sa.CheckConstraint(
            "kind IN ('enrichment', 'approval', 'action', 'validation', 'notification')",
            name="workflow_step_kind",
        ),
        sa.CheckConstraint(
            "risk IN ('low', 'medium', 'high', 'critical')",
            name="workflow_step_risk",
        ),
        sa.CheckConstraint(
            "rollback_strategy IS NULL OR rollback_strategy IN ('compensate', 'restore')",
            name="workflow_rollback_strategy",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'running', 'waiting_approval', 'succeeded', "
            "'failed', 'skipped', 'compensating', 'compensated')",
            name="workflow_step_status",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_workflow_steps_workflow_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_steps"),
        sa.UniqueConstraint("workflow_id", "position", name="uq_workflow_steps_position"),
        sa.UniqueConstraint("workflow_id", "step_key", name="uq_workflow_steps_key"),
    )
    op.create_index("ix_workflow_steps_workspace_id", "workflow_steps", ["workspace_id"])
    op.create_index(
        "ix_workflow_steps_workspace_workflow",
        "workflow_steps",
        ["workspace_id", "workflow_id", "position"],
    )

    op.create_table(
        "workflow_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('workflow_created', 'workflow_started', "
            "'workflow_step_succeeded', 'workflow_step_failed', "
            "'workflow_step_retried', 'workflow_approval_recorded', "
            "'workflow_cancel_requested', 'workflow_compensation_recorded', "
            "'workflow_step_timed_out')",
            name="workflow_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_workflow_events_workflow_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_workflow_events"),
        sa.UniqueConstraint(
            "workflow_id",
            "sequence",
            name="uq_workflow_events_workflow_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_workflow_events_workspace_idempotency",
        ),
    )
    op.create_index("ix_workflow_events_workspace_id", "workflow_events", ["workspace_id"])
    op.create_index(
        "ix_workflow_events_workspace_workflow",
        "workflow_events",
        ["workspace_id", "workflow_id", "sequence"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_workflow_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'workflow_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER workflow_events_append_only
        BEFORE UPDATE OR DELETE ON workflow_events
        FOR EACH ROW EXECUTE FUNCTION reject_workflow_event_mutation()
        """
    )


def downgrade() -> None:
    """Remove workflow records in dependency order."""
    op.execute("DROP TRIGGER workflow_events_append_only ON workflow_events")
    op.execute("DROP FUNCTION reject_workflow_event_mutation()")
    op.drop_index("ix_workflow_events_workspace_workflow", table_name="workflow_events")
    op.drop_index("ix_workflow_events_workspace_id", table_name="workflow_events")
    op.drop_table("workflow_events")
    op.drop_index("ix_workflow_steps_workspace_workflow", table_name="workflow_steps")
    op.drop_index("ix_workflow_steps_workspace_id", table_name="workflow_steps")
    op.drop_table("workflow_steps")
    op.drop_index("ix_workflow_runs_workspace_status_updated", table_name="workflow_runs")
    op.drop_index("ix_workflow_runs_workspace_id", table_name="workflow_runs")
    op.drop_table("workflow_runs")
