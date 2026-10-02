"""Create share_links table

Revision ID: 007_sharing
Revises: 006_media_library
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "007_sharing"
down_revision: Union[str, Sequence[str], None] = "006_media_library"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "share_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("allow_download", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_share_links_user_id"), "share_links", ["user_id"], unique=False)
    op.create_index(op.f("ix_share_links_media_id"), "share_links", ["media_id"], unique=False)
    op.create_index(op.f("ix_share_links_token"), "share_links", ["token"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_share_links_token"), table_name="share_links")
    op.drop_index(op.f("ix_share_links_media_id"), table_name="share_links")
    op.drop_index(op.f("ix_share_links_user_id"), table_name="share_links")
    op.drop_table("share_links")
