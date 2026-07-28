"""Create incidents and append-only timeline events.

Revision ID: 20260722_0002
Revises: 20260722_0001
Create Date: 2026-07-22
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260722_0002"
down_revision: str | None = "20260722_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create workspace-scoped incidents and their immutable event stream."""
    op.create_table(
        "incidents",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=8), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(title) > 0", name="title_not_empty"),
        sa.CheckConstraint(
            "severity IN ('low', 'medium', 'high', 'critical')",
            name="incident_severity",
        ),
        sa.CheckConstraint(
            "status IN ('new', 'triaging', 'investigating', 'awaiting_approval', "
            "'responding', 'validating', 'resolved', 'closed', 'reopened')",
            name="incident_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incidents"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_incidents_id_workspace"),
    )
    op.create_index("ix_incidents_workspace_id", "incidents", ["workspace_id"])
    op.create_index(
        "ix_incidents_workspace_status_updated",
        "incidents",
        ["workspace_id", "status", "updated_at"],
    )

    op.create_table(
        "incident_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("incident_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('incident_created', 'status_changed', 'note_added')",
            name="incident_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["incident_id", "workspace_id"],
            ["incidents.id", "incidents.workspace_id"],
            name="fk_incident_events_incident_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_incident_events"),
        sa.UniqueConstraint("incident_id", "sequence", name="uq_incident_events_incident_sequence"),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_incident_events_workspace_idempotency",
        ),
    )
    op.create_index("ix_incident_events_workspace_id", "incident_events", ["workspace_id"])
    op.create_index(
        "ix_incident_events_workspace_incident",
        "incident_events",
        ["workspace_id", "incident_id", "sequence"],
    )
    op.execute(
        """
        CREATE FUNCTION reject_incident_event_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'incident_events is append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    op.execute(
        """
        CREATE TRIGGER incident_events_append_only
        BEFORE UPDATE OR DELETE ON incident_events
        FOR EACH ROW EXECUTE FUNCTION reject_incident_event_mutation()
        """
    )


def downgrade() -> None:
    """Remove timeline and incident tables in dependency order."""
    op.execute("DROP TRIGGER incident_events_append_only ON incident_events")
    op.execute("DROP FUNCTION reject_incident_event_mutation()")
    op.drop_index("ix_incident_events_workspace_incident", table_name="incident_events")
    op.drop_index("ix_incident_events_workspace_id", table_name="incident_events")
    op.drop_table("incident_events")
    op.drop_index("ix_incidents_workspace_status_updated", table_name="incidents")
    op.drop_index("ix_incidents_workspace_id", table_name="incidents")
    op.drop_table("incidents")
