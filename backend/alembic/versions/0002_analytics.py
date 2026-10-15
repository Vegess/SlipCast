"""task history: status events, ticket text, type labels and timestamps

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-14
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("description", sa.Text(), nullable=False, server_default=""))
        batch.add_column(sa.Column("kind", sa.String(20), nullable=True))
        batch.add_column(sa.Column("kind_source", sa.String(10), nullable=False, server_default=""))
        batch.add_column(sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("external_id", sa.String(64), nullable=True))

    op.create_table(
        "task_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(32),
            sa.ForeignKey("tasks.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("from_status", sa.String(20), nullable=True),
        sa.Column("to_status", sa.String(20), nullable=False),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_task_events_task_id", "task_events", ["task_id"])


def downgrade() -> None:
    op.drop_table("task_events")
    with op.batch_alter_table("tasks") as batch:
        for col in (
            "external_id",
            "completed_at",
            "started_at",
            "kind_source",
            "kind",
            "description",
        ):
            batch.drop_column(col)
