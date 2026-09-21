from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1c9f0d3b8e2"
down_revision: Union[str, Sequence[str], None] = "7f2c1e8b9a10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_table("media_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=False),
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
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
    )
    op.create_index("ix_media_versions_media_id", "media_versions", ["media_id"])
    op.create_table("processing_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media.id", ondelete="CASCADE"), nullable=True),
        sa.Column("media_version_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("media_versions.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("task_name", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="queued"),
        sa.Column("progress", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stage", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("input_filename", sa.String(length=255), nullable=True),
        sa.Column("output_filename", sa.String(length=255), nullable=True),
        sa.Column("operation_type", sa.String(length=50), nullable=True),
        sa.Column("operation_params", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("arq_job_id", sa.String(length=255), nullable=True),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    for name, table, col in [
        ("ix_processing_jobs_media_id","processing_jobs","media_id"),
        ("ix_processing_jobs_media_version_id","processing_jobs","media_version_id"),
        ("ix_processing_jobs_user_id","processing_jobs","user_id"),
        ("ix_processing_jobs_status","processing_jobs","status"),
        ("ix_processing_jobs_arq_job_id","processing_jobs","arq_job_id"),
    ]:
        op.create_index(name, table, [col])

    op.create_table("workflows",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("operations", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_workflows_user_id","workflows",["user_id"])
    op.create_table("project_folders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_project_folders_project_id","project_folders",["project_id"])
    op.create_table("processing_history",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_processing_history_user_id","processing_history",["user_id"])
    op.create_index("ix_processing_history_media_id","processing_history",["media_id"])
    op.create_table("notifications",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_notifications_user_id","notifications",["user_id"])
    op.create_table("presets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_builtin", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("settings", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_presets_user_id","presets",["user_id"])
    op.create_table("share_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token", sa.Text(), nullable=False),
        sa.Column("password", sa.Text(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("allow_download", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("view_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("allowed_domains", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_share_links_user_id","share_links",["user_id"])
    op.create_index("ix_share_links_media_id","share_links",["media_id"])
    op.create_unique_constraint("uq_share_links_token","share_links",["token"])
    op.create_table("user_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("key", sa.Text(), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_user_preferences_user_id","user_preferences",["user_id"])
    op.create_table("video_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("media_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("operation", sa.String(length=50), nullable=False),
        sa.Column("parameters", sa.String(length=500), nullable=False),
    )
    op.create_index("ix_video_adjustments_media_id","video_adjustments",["media_id"])
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
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_table("user_preferences")
    op.drop_constraint("uq_share_links_token", "share_links", type_="unique")
    op.drop_index("ix_share_links_media_id", table_name="share_links")
    op.drop_index("ix_share_links_user_id", table_name="share_links")
    op.drop_table("share_links")
    op.drop_index("ix_presets_user_id", table_name="presets")
    op.drop_table("presets")
    op.drop_index("ix_notifications_user_id", table_name="notifications")
    op.drop_table("notifications")
    op.drop_index("ix_processing_history_media_id", table_name="processing_history")
    op.drop_index("ix_processing_history_user_id", table_name="processing_history")
    op.drop_table("processing_history")
    op.drop_index("ix_project_folders_project_id", table_name="project_folders")
    op.drop_table("project_folders")
    op.drop_index("ix_workflows_user_id", table_name="workflows")
    op.drop_table("workflows")
    op.drop_index("ix_processing_jobs_arq_job_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_status", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_user_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_media_version_id", table_name="processing_jobs")
    op.drop_index("ix_processing_jobs_media_id", table_name="processing_jobs")
    op.drop_table("processing_jobs")
    op.drop_index("ix_media_versions_media_id", table_name="media_versions")
    op.drop_table("media_versions")
