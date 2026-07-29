"""Create risk-based human approval requests and immutable decisions.

Revision ID: 20260728_0005
Revises: 20260728_0004
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0005"
down_revision: str | None = "20260728_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create approval aggregates, immutable decisions, and append-only events."""
    op.create_table(
        "approval_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("workflow_id", sa.Uuid(), nullable=False),
        sa.Column("step_key", sa.String(length=64), nullable=False),
        sa.Column("action_summary", sa.String(length=300), nullable=False),
        sa.Column("risk", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("required_approvals", sa.Integer(), nullable=False),
        sa.Column(
            "eligible_roles",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("requested_by", sa.String(length=200), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "risk IN ('low', 'medium', 'high', 'critical')",
            name="approval_risk",
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'approved', 'rejected', 'expired', 'cancelled')",
            name="approval_status",
        ),
        sa.CheckConstraint(
            "required_approvals BETWEEN 1 AND 5",
            name="approval_required_count",
        ),
        sa.CheckConstraint("version >= 1", name="approval_version_positive"),
        sa.CheckConstraint("round >= 1", name="approval_round_positive"),
        sa.ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_approval_requests_incident_workspace",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["workflow_id", "workspace_id"],
            ["workflow_runs.id", "workflow_runs.workspace_id"],
            name="fk_approval_requests_workflow_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_requests"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_approval_requests_id_workspace"),
        sa.UniqueConstraint(
            "workflow_id",
            "step_key",
            name="uq_approval_requests_workflow_step",
        ),
    )
    op.create_index("ix_approval_requests_workspace_id", "approval_requests", ["workspace_id"])
    op.create_index(
        "ix_approval_requests_workspace_status_updated",
        "approval_requests",
        ["workspace_id", "status", "updated_at"],
    )

    op.create_table(
        "approval_decisions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
        sa.Column("round", sa.Integer(), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("actor_role", sa.String(length=100), nullable=False),
        sa.Column("decision", sa.String(length=8), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approve', 'reject')",
            name="approval_decision",
        ),
        sa.CheckConstraint("round >= 1", name="approval_decision_round_positive"),
        sa.ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approval_requests.id", "approval_requests.workspace_id"],
            name="fk_approval_decisions_request_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_decisions"),
        sa.UniqueConstraint(
            "approval_id",
            "round",
            "actor_id",
            name="uq_approval_decisions_round_actor",
        ),
    )
    op.create_index(
        "ix_approval_decisions_workspace_id",
        "approval_decisions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_approval_decisions_workspace_request",
        "approval_decisions",
        ["workspace_id", "approval_id", "round"],
    )

    op.create_table(
        "approval_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("approval_id", sa.Uuid(), nullable=False),
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
            "event_type IN ('approval_created', 'approval_decision_recorded', "
            "'approval_expired', 'approval_renewed', 'approval_cancelled')",
            name="approval_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["approval_id", "workspace_id"],
            ["approval_requests.id", "approval_requests.workspace_id"],
            name="fk_approval_events_request_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_approval_events"),
        sa.UniqueConstraint(
            "approval_id",
            "sequence",
            name="uq_approval_events_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_approval_events_workspace_idempotency",
        ),
    )
    op.create_index("ix_approval_events_workspace_id", "approval_events", ["workspace_id"])
    op.create_index(
        "ix_approval_events_workspace_request",
        "approval_events",
        ["workspace_id", "approval_id", "sequence"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_approval_audit_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'approval decisions and events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("approval_decisions", "approval_events"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_approval_audit_mutation()
            """
        )


def downgrade() -> None:
    """Remove approval records in dependency order."""
    for table in ("approval_events", "approval_decisions"):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_approval_audit_mutation()")
    op.drop_index("ix_approval_events_workspace_request", table_name="approval_events")
    op.drop_index("ix_approval_events_workspace_id", table_name="approval_events")
    op.drop_table("approval_events")
    op.drop_index(
        "ix_approval_decisions_workspace_request",
        table_name="approval_decisions",
    )
    op.drop_index("ix_approval_decisions_workspace_id", table_name="approval_decisions")
    op.drop_table("approval_decisions")
    op.drop_index(
        "ix_approval_requests_workspace_status_updated",
        table_name="approval_requests",
    )
    op.drop_index("ix_approval_requests_workspace_id", table_name="approval_requests")
    op.drop_table("approval_requests")
