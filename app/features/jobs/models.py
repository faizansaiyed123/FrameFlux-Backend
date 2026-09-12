from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.infrastructure.database import Base


class JobStatus(str):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    retrying = "retrying"


class ProcessingJob(Base):
    __tablename__ = "processing_jobs"

    id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
    )

    media_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("media.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    media_version_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("media_versions.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    user_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )

    task_name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )

    status: Mapped[str] = mapped_column(
        String(20),
        default=JobStatus.queued,
        nullable=False,
        index=True,
    )

    progress: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    stage: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    error: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    input_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    output_filename: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    operation_type: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )

    operation_params: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    retry_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
    )

    max_retries: Mapped[int] = mapped_column(
        Integer,
        default=3,
        nullable=False,
    )

    arq_job_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    enqueued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
