"""account and dashboard extensions

Revision ID: 003_account_dashboard_extensions
Revises: 002_processing_jobs
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "003_account_dashboard_extensions"
down_revision: Union[str, Sequence[str], None] = "002_processing_jobs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("avatar_url", sa.String(length=255), nullable=True))
    op.add_column("users", sa.Column("preferences", sa.String(length=255), nullable=True))
    op.create_table(
        "favorites",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_favorites_media_id"), "favorites", ["media_id"], unique=False)
    op.create_index(op.f("ix_favorites_user_id"), "favorites", ["user_id"], unique=False)
    op.create_index(op.f("ix_favorites_user_id_media_id"), "favorites", ["user_id", "media_id"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_favorites_user_id_media_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_user_id"), table_name="favorites")
    op.drop_index(op.f("ix_favorites_media_id"), table_name="favorites")
    op.drop_table("favorites")
    op.drop_column("users", "preferences")
    op.drop_column("users", "avatar_url")
