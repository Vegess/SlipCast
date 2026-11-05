"""advice layer: request log and suggestion feedback

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "advice_logs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("llm_called", sa.Boolean(), nullable=False),
        sa.Column("privacy_mode", sa.Boolean(), nullable=False),
        sa.Column("generated", sa.Integer(), nullable=False),
        sa.Column("accepted", sa.Integer(), nullable=False),
        sa.Column("rejected", sa.Integer(), nullable=False),
        sa.Column("error", sa.String(300), nullable=False),
    )
    op.create_index("ix_advice_logs_project_id", "advice_logs", ["project_id"])
    op.create_index("ix_advice_logs_user_id", "advice_logs", ["user_id"])
    op.create_table(
        "advice_feedback",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("suggestion_key", sa.String(40), nullable=False),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("helpful", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("project_id", "user_id", "suggestion_key", name="uq_advice_feedback"),
    )
    op.create_index("ix_advice_feedback_project_id", "advice_feedback", ["project_id"])
    op.create_index("ix_advice_feedback_user_id", "advice_feedback", ["user_id"])


def downgrade() -> None:
    op.drop_table("advice_feedback")
    op.drop_table("advice_logs")
