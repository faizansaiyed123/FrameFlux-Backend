from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID, uuid4
from sqlalchemy import String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.infrastructure.database import Base


class VideoAdjustment(Base):
    __tablename__ = "video_adjustments"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    media_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False, index=True)
    operation: Mapped[str] = mapped_column(String(50), nullable=False)
    parameters: Mapped[str] = mapped_column(String(500), nullable=False)
