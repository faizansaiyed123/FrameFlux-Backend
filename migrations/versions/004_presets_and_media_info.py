"""Add presets table and media info extensions

Revision ID: 004_presets_and_media_info
Revises: 003_account_dashboard_extensions
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "004_presets_and_media_info"
down_revision: Union[str, Sequence[str], None] = "003_account_dashboard_extensions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "presets",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("settings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_presets_user_id"), "presets", ["user_id"], unique=False)

    op.add_column("media", sa.Column("bitrate", sa.String(length=50), nullable=True))
    op.add_column("media", sa.Column("audio_channels", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("sample_rate", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("container_format", sa.String(length=50), nullable=True))
    op.add_column("media", sa.Column("audio_tracks", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("subtitle_tracks", sa.Integer(), nullable=True))
    op.add_column("media", sa.Column("available_streams", sa.Text(), nullable=True))
    op.add_column("media", sa.Column("metadata", sa.Text(), nullable=True))
    op.add_column("media", sa.Column("creation_metadata", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("media", "creation_metadata")
    op.drop_column("media", "metadata")
    op.drop_column("media", "available_streams")
    op.drop_column("media", "subtitle_tracks")
    op.drop_column("media", "audio_tracks")
    op.drop_column("media", "container_format")
    op.drop_column("media", "sample_rate")
    op.drop_column("media", "audio_channels")
    op.drop_column("media", "bitrate")
    op.drop_index(op.f("ix_presets_user_id"), table_name="presets")
    op.drop_table("presets")
