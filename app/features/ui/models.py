from datetime import datetime
from uuid import UUID, uuid4

import sqlalchemy as sa
from sqlalchemy import Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class UserPreference(Base):
    __tablename__ = "user_preferences"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    key: Mapped[str] = mapped_column(Text, nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(server_default=sa.text("now()"), nullable=False)
