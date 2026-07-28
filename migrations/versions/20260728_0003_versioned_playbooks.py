"""Create versioned response playbooks and append-only audit records.

Revision ID: 20260728_0003
Revises: 20260722_0002
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0003"
down_revision: str | None = "20260722_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create playbook identities, immutable revisions, and audit events."""
    op.create_table(
        "playbooks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("latest_version", sa.Integer(), nullable=False),
        sa.Column("active_version", sa.Integer(), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("char_length(name) > 0", name="name_not_empty"),
        sa.CheckConstraint("latest_version >= 1", name="latest_version_positive"),
        sa.CheckConstraint("version >= 1", name="version_positive"),
        sa.CheckConstraint(
            "active_version IS NULL OR active_version <= latest_version",
            name="active_version_valid",
        ),
        sa.CheckConstraint(
            "status IN ('draft', 'active', 'archived')",
            name="playbook_status",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbooks"),
        sa.UniqueConstraint("id", "workspace_id", name="uq_playbooks_id_workspace"),
    )
    op.create_index("ix_playbooks_workspace_id", "playbooks", ["workspace_id"])
    op.create_index(
        "ix_playbooks_workspace_status_updated",
        "playbooks",
        ["workspace_id", "status", "updated_at"],
    )

    op.create_table(
        "playbook_versions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("playbook_id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column(
            "steps",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("definition_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by", sa.String(length=200), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["playbook_id", "workspace_id"],
            ["playbooks.id", "playbooks.workspace_id"],
            name="fk_playbook_versions_playbook_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_versions"),
        sa.UniqueConstraint(
            "playbook_id",
            "number",
            name="uq_playbook_versions_playbook_number",
        ),
        sa.UniqueConstraint(
            "id",
            "workspace_id",
            name="uq_playbook_versions_id_workspace",
        ),
    )
    op.create_index(
        "ix_playbook_versions_workspace_id",
        "playbook_versions",
        ["workspace_id"],
    )
    op.create_index(
        "ix_playbook_versions_workspace_playbook",
        "playbook_versions",
        ["workspace_id", "playbook_id", "number"],
    )

    op.create_table(
        "playbook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("playbook_id", sa.Uuid(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(length=28), nullable=False),
        sa.Column("actor_id", sa.String(length=200), nullable=False),
        sa.Column("idempotency_key", sa.String(length=200), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "event_type IN ('playbook_created', 'playbook_version_created', "
            "'playbook_published', 'playbook_archived')",
            name="playbook_event_type",
        ),
        sa.ForeignKeyConstraint(
            ["playbook_id", "workspace_id"],
            ["playbooks.id", "playbooks.workspace_id"],
            name="fk_playbook_events_playbook_workspace",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_playbook_events"),
        sa.UniqueConstraint(
            "playbook_id",
            "sequence",
            name="uq_playbook_events_playbook_sequence",
        ),
        sa.UniqueConstraint(
            "workspace_id",
            "idempotency_key",
            name="uq_playbook_events_workspace_idempotency",
        ),
    )
    op.create_index("ix_playbook_events_workspace_id", "playbook_events", ["workspace_id"])
    op.create_index(
        "ix_playbook_events_workspace_playbook",
        "playbook_events",
        ["workspace_id", "playbook_id", "sequence"],
    )

    op.execute(
        """
        CREATE FUNCTION reject_playbook_immutable_mutation()
        RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION 'playbook versions and events are append-only';
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in ("playbook_versions", "playbook_events"):
        op.execute(
            f"""
            CREATE TRIGGER {table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION reject_playbook_immutable_mutation()
            """
        )


def downgrade() -> None:
    """Remove playbook records in dependency order."""
    for table in ("playbook_events", "playbook_versions"):
        op.execute(f"DROP TRIGGER {table}_append_only ON {table}")
    op.execute("DROP FUNCTION reject_playbook_immutable_mutation()")
    op.drop_index("ix_playbook_events_workspace_playbook", table_name="playbook_events")
    op.drop_index("ix_playbook_events_workspace_id", table_name="playbook_events")
    op.drop_table("playbook_events")
    op.drop_index(
        "ix_playbook_versions_workspace_playbook",
        table_name="playbook_versions",
    )
    op.drop_index("ix_playbook_versions_workspace_id", table_name="playbook_versions")
    op.drop_table("playbook_versions")
    op.drop_index("ix_playbooks_workspace_status_updated", table_name="playbooks")
    op.drop_index("ix_playbooks_workspace_id", table_name="playbooks")
    op.drop_table("playbooks")
