from uuid import UUID

from app.features.media.processor import process_media


async def process_media_task(
    ctx,
    media_id: str,
    stored_filename: str,
):
    output_filename = process_media(
        UUID(media_id),
        stored_filename,
    )

    return {
        "media_id": media_id,
        "status": "processed",
        "output_filename": output_filename,
    }
