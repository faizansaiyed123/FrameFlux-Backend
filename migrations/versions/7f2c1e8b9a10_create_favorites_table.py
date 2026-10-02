"""create favorites table

Revision ID: 7f2c1e8b9a10
Revises: e59ad3bb6694
Create Date: 2026-09-18

The `favorites` table itself is created by 003_account_dashboard_extensions on the
001-012 branch, which also adds the unique index on (user_id, media_id). This
revision used to create the same table, which made the two branches mutually
exclusive: applying both raised DuplicateTable. It is kept in the history (so
existing databases stamped at 7f2c1e8b9a10 stay valid) but no longer creates
anything.
"""

from typing import Sequence, Union


revision: str = "7f2c1e8b9a10"
down_revision: Union[str, Sequence[str], None] = "e59ad3bb6694"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
