"""Build module: GitHub webhook connection per project

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-22
"""

import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("github_hook_version", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("github_repo", sa.String(140), nullable=True))
        batch.add_column(sa.Column("github_last_event_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_ingested_events_external_id", "ingested_events", ["project_id", "external_id"])


def downgrade() -> None:
    op.drop_index("ix_ingested_events_external_id", table_name="ingested_events")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("github_last_event_at")
        batch.drop_column("github_repo")
        batch.drop_column("github_hook_version")
