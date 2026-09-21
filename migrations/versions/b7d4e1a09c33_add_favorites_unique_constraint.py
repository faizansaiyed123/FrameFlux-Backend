from typing import Sequence, Union
from alembic import op

revision: str = "b7d4e1a09c33"
down_revision: Union[str, Sequence[str], None] = "a1c9f0d3b8e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.create_unique_constraint("uq_favorites_user_media", "favorites", ["user_id", "media_id"])

def downgrade() -> None:
    op.drop_constraint("uq_favorites_user_media", "favorites", type_="unique")
