"""Create project_folders table

Revision ID: 009_project_folders
Revises: 008_processing_history
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "009_project_folders"
down_revision: Union[str, Sequence[str], None] = "008_processing_history"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "project_folders",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("project_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("parent_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_folders_project_id"), "project_folders", ["project_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_project_folders_project_id"), table_name="project_folders")
    op.drop_table("project_folders")
