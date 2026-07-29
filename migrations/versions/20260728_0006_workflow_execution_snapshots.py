"""Add executable workflow step snapshots.

Revision ID: 20260728_0006
Revises: 20260728_0005
Create Date: 2026-07-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260728_0006"
down_revision: str | None = "20260728_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Snapshot parameters, conditions, failure policy, and rollback inputs."""
    empty_object = sa.text("'{}'::jsonb")
    op.add_column(
        "workflow_steps",
        sa.Column(
            "parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=empty_object,
        ),
    )
    op.add_column(
        "workflow_steps",
        sa.Column(
            "continue_on_failure",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "workflow_steps",
        sa.Column(
            "condition",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=True,
        ),
    )
    op.add_column(
        "workflow_steps",
        sa.Column(
            "rollback_parameters",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=empty_object,
        ),
    )
    op.add_column(
        "workflow_steps",
        sa.Column(
            "rollback_timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="300",
        ),
    )
    op.create_check_constraint(
        "workflow_step_rollback_timeout",
        "workflow_steps",
        "rollback_timeout_seconds BETWEEN 1 AND 3600",
    )
    for column in (
        "parameters",
        "continue_on_failure",
        "rollback_parameters",
        "rollback_timeout_seconds",
    ):
        op.alter_column("workflow_steps", column, server_default=None)


def downgrade() -> None:
    """Remove executable step snapshot fields."""
    op.drop_constraint(
        "ck_workflow_steps_workflow_step_rollback_timeout",
        "workflow_steps",
        type_="check",
    )
    for column in (
        "rollback_timeout_seconds",
        "rollback_parameters",
        "condition",
        "continue_on_failure",
        "parameters",
    ):
        op.drop_column("workflow_steps", column)
