"""Add short-lived recruiter demo sessions.

Revision ID: 014_demo_sessions
Revises: 013_merge_feature_branches
Create Date: 2026-11-14
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "014_demo_sessions"
down_revision: Union[str, Sequence[str], None] = "013_merge_feature_branches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "demo_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("client_ip_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cleanup_state", sa.String(length=24), server_default="active", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("cleaned_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("user_id", name="uq_demo_sessions_user_id"),
    )
    op.create_index("ix_demo_sessions_user_id", "demo_sessions", ["user_id"], unique=True)
    op.create_index("ix_demo_sessions_client_ip_hash", "demo_sessions", ["client_ip_hash"], unique=False)
    op.create_index("ix_demo_sessions_expires_at", "demo_sessions", ["expires_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_demo_sessions_expires_at", table_name="demo_sessions")
    op.drop_index("ix_demo_sessions_client_ip_hash", table_name="demo_sessions")
    op.drop_index("ix_demo_sessions_user_id", table_name="demo_sessions")
    op.drop_table("demo_sessions")
