"""create tables that no other revision creates

Revision ID: a1c9f0d3b8e2
Revises: 7f2c1e8b9a10
Create Date: 2026-09-18

media_versions, processing_jobs, workflows, presets, share_links,
processing_history, project_folders, notifications and user_preferences are all
created by the 001-012 branch, so creating them here raised DuplicateTable once
both branches were applied. Only video_adjustments and media_comparisons are
unique to this revision and are still created below.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1c9f0d3b8e2"
down_revision: Union[str, Sequence[str], None] = "7f2c1e8b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("video_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("parameters", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_video_adjustments_media_id", "video_adjustments", ["media_id"])
    op.create_table("media_comparisons",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_a_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("media_b_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("comparison_data", sa.Text(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("media_comparisons")
    op.drop_index("ix_video_adjustments_media_id", table_name="video_adjustments")
    op.drop_table("video_adjustments")
