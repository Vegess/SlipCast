"""accounts and teams: Google/GitHub sign-in, invites, roles, token revocation

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-21
"""

import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=True)
        batch.add_column(sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"))

    op.create_table(
        "oauth_accounts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(20), nullable=False),
        sa.Column("provider_user_id", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_identity"),
    )
    op.create_index("ix_oauth_accounts_user_id", "oauth_accounts", ["user_id"])

    op.create_table(
        "invites",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("used_by", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_invites_workspace_id", "invites", ["workspace_id"])
    op.create_index("ix_invites_token_hash", "invites", ["token_hash"], unique=True)

    # Personal workspaces were created with role "owner"; the role set is now admin | member | viewer.
    op.execute("UPDATE memberships SET role = 'admin' WHERE role = 'owner'")


def downgrade() -> None:
    op.execute("UPDATE memberships SET role = 'owner' WHERE role = 'admin'")
    op.drop_table("invites")
    op.drop_table("oauth_accounts")
    with op.batch_alter_table("users") as batch:
        batch.drop_column("token_version")
        batch.alter_column("password_hash", existing_type=sa.String(255), nullable=False)
