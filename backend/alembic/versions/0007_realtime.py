"""real-time engine: project stages, API keys, event ingestion, alerts

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("projects") as batch:
        batch.add_column(sa.Column("template", sa.String(20), nullable=False, server_default="software"))
        batch.add_column(sa.Column("last_p85", sa.Date(), nullable=True))
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("stage", sa.String(40), nullable=True))
        batch.add_column(sa.Column("item_type", sa.String(20), nullable=False, server_default=""))
        batch.add_column(sa.Column("attributes", sa.JSON(), nullable=True))
        batch.create_index("ix_tasks_external_id", ["external_id"])

    op.create_table(
        "workflow_stages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("key", sa.String(40), nullable=False),
        sa.Column("label", sa.String(60), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(10), nullable=False),
        sa.UniqueConstraint("project_id", "key", name="uq_stage_key"),
    )
    op.create_index("ix_workflow_stages_project_id", "workflow_stages", ["project_id"])

    op.create_table(
        "project_api_keys",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("prefix", sa.String(16), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_project_api_keys_project_id", "project_api_keys", ["project_id"])
    op.create_index("ix_project_api_keys_key_hash", "project_api_keys", ["key_hash"], unique=True)

    op.create_table(
        "ingested_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "external_id", "stage", "occurred_at", name="uq_ingested_event"),
    )
    op.create_index("ix_ingested_events_project_id", "ingested_events", ["project_id"])

    op.create_table(
        "alerts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("severity", sa.String(10), nullable=False),
        sa.Column("message", sa.String(300), nullable=False),
        sa.Column("data", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_alerts_project_id", "alerts", ["project_id"])
    op.create_index("ix_alerts_created_at", "alerts", ["created_at"])


def downgrade() -> None:
    op.drop_table("alerts")
    op.drop_table("ingested_events")
    op.drop_table("project_api_keys")
    op.drop_table("workflow_stages")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_external_id")
        batch.drop_column("attributes")
        batch.drop_column("item_type")
        batch.drop_column("stage")
    with op.batch_alter_table("projects") as batch:
        batch.drop_column("last_p85")
        batch.drop_column("template")
