"""create media_versions table

Revision ID: 001_media_versions
Revises: e59ad3bb6694
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "001_media_versions"
down_revision: Union[str, Sequence[str], None] = "e59ad3bb6694"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "media_versions",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("stored_filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("duration", sa.Float(), nullable=True),
        sa.Column("width", sa.Integer(), nullable=True),
        sa.Column("height", sa.Integer(), nullable=True),
        sa.Column("video_codec", sa.String(length=50), nullable=True),
        sa.Column("audio_codec", sa.String(length=50), nullable=True),
        sa.Column("fps", sa.String(length=50), nullable=True),
        sa.Column("processing_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("processing_error", sa.Text(), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_media_versions_media_id"), "media_versions", ["media_id"], unique=False)
    op.create_index(op.f("ix_media_versions_version_number"), "media_versions", ["media_id", "version_number"], unique=True)


def downgrade() -> None:
    op.drop_index(op.f("ix_media_versions_version_number"), table_name="media_versions")
    op.drop_index(op.f("ix_media_versions_media_id"), table_name="media_versions")
    op.drop_table("media_versions")
