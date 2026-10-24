"""Add missing sharing columns used by the ShareLink ORM model.

Revision ID: 014_sharing_columns
Revises: 013_merge_feature_branches
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "014_sharing_columns"
down_revision: Union[str, Sequence[str], None] = "013_merge_feature_branches"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "share_links",
        sa.Column("view_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
    )
    op.add_column(
        "share_links",
        sa.Column("allowed_domains", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("share_links", "allowed_domains")
    op.drop_column("share_links", "view_count")
