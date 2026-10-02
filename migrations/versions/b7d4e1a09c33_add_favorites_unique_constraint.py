"""add favorites unique constraint

Revision ID: b7d4e1a09c33
Revises: a1c9f0d3b8e2

003_account_dashboard_extensions already creates the unique index
ix_favorites_user_id_media_id on (user_id, media_id), so a separate
uq_favorites_user_media constraint is redundant. It is kept in the history so
databases stamped at b7d4e1a09c33 stay valid, but it is only added when the
uniqueness is in fact missing.
"""

from typing import Sequence, Union

from alembic import op
from sqlalchemy import inspect

revision: str = "b7d4e1a09c33"
down_revision: Union[str, Sequence[str], None] = "a1c9f0d3b8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_CONSTRAINT = "uq_favorites_user_media"


def _uniqueness_already_enforced() -> bool:
    inspector = inspect(op.get_bind())
    if "favorites" not in inspector.get_table_names():
        return True
    unique_columns = [
        set(constraint["column_names"])
        for constraint in inspector.get_unique_constraints("favorites")
    ]
    if any(columns == {"user_id", "media_id"} for columns in unique_columns):
        return True
    return any(
        set(index["column_names"]) == {"user_id", "media_id"} and index["unique"]
        for index in inspector.get_indexes("favorites")
    )


def _constraint_exists() -> bool:
    inspector = inspect(op.get_bind())
    if "favorites" not in inspector.get_table_names():
        return False
    return any(
        constraint["name"] == _CONSTRAINT
        for constraint in inspector.get_unique_constraints("favorites")
    )


def upgrade() -> None:
    if not _uniqueness_already_enforced():
        op.create_unique_constraint(_CONSTRAINT, "favorites", ["user_id", "media_id"])


def downgrade() -> None:
    if _constraint_exists():
        op.drop_constraint(_CONSTRAINT, "favorites", type_="unique")
