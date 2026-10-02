"""merge the feature-table branch into the 001-012 branch

Revision ID: 013_merge_feature_branches
Revises: 012_indexes_for_performance, b7d4e1a09c33
Create Date: 2026-10-01

Both branches forked from e59ad3bb6694 and left the repository with two heads, so
`alembic upgrade head` failed with "Multiple head revisions are present". The
duplicated CREATE TABLE statements were removed from the other branch; this
revision only joins the two tips.
"""

from typing import Sequence, Union


revision: str = "013_merge_feature_branches"
down_revision: Union[str, Sequence[str], None] = (
    "012_indexes_for_performance",
    "b7d4e1a09c33",
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
