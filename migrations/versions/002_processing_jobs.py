"""create processing_jobs table

Revision ID: 002_processing_jobs
Revises: 001_media_versions
Create Date: 2026-09-10

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "002_processing_jobs"
down_revision: Union[str, Sequence[str], None] = "001_media_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "processing_jobs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("media_id", sa.UUID(), nullable=True),
        sa.Column("media_version_id", sa.UUID(), nullable=True),
        sa.Column("user_id", sa.UUID(), nullable=True),
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
        sa.ForeignKeyConstraint(["media_id"], ["media.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["media_version_id"], ["media_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_jobs_arq_job_id"), "processing_jobs", ["arq_job_id"], unique=False)
    op.create_index(op.f("ix_processing_jobs_media_id"), "processing_jobs", ["media_id"], unique=False)
    op.create_index(op.f("ix_processing_jobs_media_version_id"), "processing_jobs", ["media_version_id"], unique=False)
    op.create_index(op.f("ix_processing_jobs_status"), "processing_jobs", ["status"], unique=False)
    op.create_index(op.f("ix_processing_jobs_user_id"), "processing_jobs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_jobs_user_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_status"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_media_version_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_media_id"), table_name="processing_jobs")
    op.drop_index(op.f("ix_processing_jobs_arq_job_id"), table_name="processing_jobs")
    op.drop_table("processing_jobs")
