"""forecast ledger: every forecast made, scored when the outcome arrives

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-05
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "forecasts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(32),
            sa.ForeignKey("projects.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subject_id", sa.String(32), nullable=True),
        sa.Column("made_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("inputs", sa.JSON(), nullable=False),
        sa.Column("p50_date", sa.Date(), nullable=True),
        sa.Column("p85_date", sa.Date(), nullable=True),
        sa.Column("p10_days", sa.Float(), nullable=True),
        sa.Column("p50_days", sa.Float(), nullable=True),
        sa.Column("p85_days", sa.Float(), nullable=True),
        sa.Column("p90_days", sa.Float(), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actual_date", sa.Date(), nullable=True),
        sa.Column("actual_days", sa.Float(), nullable=True),
        sa.Column("hit_p85", sa.Boolean(), nullable=True),
        sa.Column("void", sa.Boolean(), nullable=False),
    )
    op.create_index("ix_forecasts_project_id", "forecasts", ["project_id"])
    op.create_index("ix_forecasts_subject_id", "forecasts", ["subject_id"])


def downgrade() -> None:
    op.drop_table("forecasts")
