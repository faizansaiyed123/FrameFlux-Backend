"""add media processing status

Revision ID: 9e32e6e2a655
Revises: e4395cb07e92
Create Date: 2026-09-08 08:06:40.969906

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "9e32e6e2a655"
down_revision: Union[str, Sequence[str], None] = "e4395cb07e92"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "media",
        sa.Column(
            "processing_status",
            sa.String(length=20),
            nullable=False,
            server_default="pending",
        ),
    )

    op.add_column(
        "media",
        sa.Column(
            "processed_filename",
            sa.String(length=255),
            nullable=True,
        ),
    )

    op.add_column(
        "media",
        sa.Column(
            "processing_error",
            sa.Text(),
            nullable=True,
        ),
    )

    # Remove the default after existing rows have been populated.
    op.alter_column(
        "media",
        "processing_status",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("media", "processing_error")
    op.drop_column("media", "processed_filename")
    op.drop_column("media", "processing_status")
