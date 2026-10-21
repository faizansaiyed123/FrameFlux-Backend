"""create media table

Revision ID: 29b935c5a042
Revises: 1158307c4d34
Create Date: 2026-09-07 21:29:44.610246

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '29b935c5a042'
down_revision: Union[str, Sequence[str], None] = '1158307c4d34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('media',
    sa.Column('id', sa.UUID(), nullable=False),
    sa.Column('original_filename', sa.String(length=255), nullable=False),
    sa.Column('stored_filename', sa.String(length=255), nullable=False),
    sa.Column('media_type', sa.String(length=50), nullable=False),
    sa.Column('mime_type', sa.String(length=100), nullable=False),
    sa.Column('file_size', sa.BigInteger(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stored_filename')
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('media')
