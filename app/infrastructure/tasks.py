from uuid import UUID

from sqlalchemy import select

from app.features.media.models import Media
from app.features.media.processor import process_media
from app.features.projects.models import Project  # registers projects table
from app.infrastructure.database import AsyncSessionLocal


async def process_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
):
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Media).where(Media.id == UUID(media_id))
        )

        media = result.scalar_one_or_none()

        if media is None:
            return {
                "media_id": media_id,
                "status": "failed",
                "error": "Media not found",
            }

        try:
            media.processing_status = "processing"
            media.processing_error = None
            await db.commit()

            output_filename = process_media(
                media.id,
                stored_filename,
            )

            media.processed_filename = output_filename
            media.processing_status = "completed"
            media.processing_error = None

            await db.commit()

            return {
                "media_id": media_id,
                "status": "completed",
                "output_filename": output_filename,
            }

        except Exception as exc:
            await db.rollback()

            media.processing_status = "failed"
            media.processing_error = str(exc)[:500]

            await db.commit()

            return {
                "media_id": media_id,
                "status": "failed",
                "error": str(exc),
            }
