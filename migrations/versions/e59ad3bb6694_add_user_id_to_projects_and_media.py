"""add_user_id_to_projects_and_media

Revision ID: e59ad3bb6694
Revises: 27ca3dfc0748
Create Date: 2026-09-08 16:07:38.446787

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e59ad3bb6694'
down_revision: Union[str, Sequence[str], None] = '27ca3dfc0748'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('projects', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_projects_user_id'), 'projects', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_projects_user_id_users',
        'projects',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )

    op.add_column('media', sa.Column('user_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_media_user_id'), 'media', ['user_id'], unique=False)
    op.create_foreign_key(
        'fk_media_user_id_users',
        'media',
        'users',
        ['user_id'],
        ['id'],
        ondelete='CASCADE',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_media_user_id_users', 'media', type_='foreignkey')
    op.drop_index(op.f('ix_media_user_id'), table_name='media')
    op.drop_column('media', 'user_id')

    op.drop_constraint('fk_projects_user_id_users', 'projects', type_='foreignkey')
    op.drop_index(op.f('ix_projects_user_id'), table_name='projects')
    op.drop_column('projects', 'user_id')
