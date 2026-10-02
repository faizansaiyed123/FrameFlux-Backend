"""Create processing_history table

Revision ID: 008_processing_history
Revises: 007_sharing
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "008_processing_history"
down_revision: Union[str, Sequence[str], None] = "007_sharing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "processing_history",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("media_id", sa.UUID(), nullable=False),
        sa.Column("operation", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("settings", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_processing_history_user_id"), "processing_history", ["user_id"], unique=False)
    op.create_index(op.f("ix_processing_history_media_id"), "processing_history", ["media_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_processing_history_media_id"), table_name="processing_history")
    op.drop_index(op.f("ix_processing_history_user_id"), table_name="processing_history")
    op.drop_table("processing_history")
