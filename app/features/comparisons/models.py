from sqlalchemy.orm import Mapped, mapped_column
from uuid import UUID, uuid4
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from app.infrastructure.database import Base


class MediaComparison(Base):
    __tablename__ = "media_comparisons"

    id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    media_a_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    media_b_id: Mapped[UUID] = mapped_column(PG_UUID(as_uuid=True), nullable=False)
    comparison_data: Mapped[str] = mapped_column(nullable=False)
