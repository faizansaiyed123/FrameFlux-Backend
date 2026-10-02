"""Add folder and tags to media table

Revision ID: 006_media_library
Revises: 005_workflows
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "006_media_library"
down_revision: Union[str, Sequence[str], None] = "005_workflows"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("media", sa.Column("folder", sa.String(length=255), nullable=True))
    op.add_column("media", sa.Column("tags", sa.Text(), nullable=True))
    op.create_index(op.f("ix_media_folder"), "media", ["folder"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_media_folder"), table_name="media")
    op.drop_column("media", "tags")
    op.drop_column("media", "folder")
