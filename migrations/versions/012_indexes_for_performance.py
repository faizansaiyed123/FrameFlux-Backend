"""Add indexes for frequently queried columns.

Revision ID: 012_indexes_for_performance
Revises: 011_user_preferences
Create Date: 2026-09-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012_indexes_for_performance"
down_revision: str = "011_user_preferences"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index("ix_media_user_id", "media", ["user_id"], if_not_exists=True)
    op.create_index("ix_media_processing_status", "media", ["processing_status"], if_not_exists=True)
    op.create_index("ix_projects_user_id", "projects", ["user_id"], if_not_exists=True)
    op.create_index("ix_processing_jobs_user_id", "processing_jobs", ["user_id"], if_not_exists=True)
    op.create_index("ix_processing_jobs_media_id", "processing_jobs", ["media_id"], if_not_exists=True)
    op.create_index("ix_favorites_user_id", "favorites", ["user_id"], if_not_exists=True)
    op.create_index("ix_processing_history_user_id", "processing_history", ["user_id"], if_not_exists=True)
    op.create_index("ix_media_versions_media_id", "media_versions", ["media_id"], if_not_exists=True)
    op.create_index("ix_share_links_token", "share_links", ["token"], if_not_exists=True)
    op.create_index("ix_share_links_is_active", "share_links", ["is_active"], if_not_exists=True)


def downgrade() -> None:
    # ix_media_user_id and ix_projects_user_id are already created (and dropped
    # again) by e59ad3bb6694, and the rest are owned by the revisions below, so
    # only the two indexes this revision introduces are dropped here.
    op.drop_index("ix_share_links_is_active", table_name="share_links", if_exists=True)
    op.drop_index("ix_media_processing_status", table_name="media", if_exists=True)
