from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class Media(Base):
    __tablename__ = "media"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    original_filename: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    stored_filename: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
    )

    media_type: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
    )

    mime_type: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    file_size: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )

    duration: Mapped[float | None] = mapped_column(
        nullable=True,
    )

    width: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    height: Mapped[int | None] = mapped_column(
        nullable=True,
    )

    video_codec: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    audio_codec: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    fps: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    project_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    processing_status: Mapped[str] = mapped_column(
        String(20),
        default="pending",
        nullable=False,
    )

    processed_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    processing_error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=datetime.utcnow,
        nullable=False,
    )
