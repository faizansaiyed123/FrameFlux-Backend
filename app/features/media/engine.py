import asyncio
import json
import logging
import os
import shutil
import tempfile
from pathlib import Path
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.features.media.models import Media
from app.features.media.schemas import ProcessingRequest, ProcessingOperation
from app.infrastructure.database import AsyncSessionLocal
from app.infrastructure.ffmpeg import probe_media
from app.infrastructure.local_storage import LocalStorage

logger = logging.getLogger(__name__)
settings = get_settings()
storage = LocalStorage()


class ProcessingEngineError(Exception):
    pass


class ProcessingEngine:
    async def execute(self, request: ProcessingRequest) -> dict:
        media_id = UUID(request.media_id)
        async with AsyncSessionLocal() as db:
            result = await db.execute(select(Media).where(Media.id == media_id))
            media = result.scalar_one_or_none()
            if media is None:
                raise ProcessingEngineError("Media not found")

            source_path = await storage.get_file_path(media.stored_filename)
            operations = self._validate_operations(request.operations)

            output_filename = f"{media_id}_processed_{uuid4().hex[:8]}.mp4"
            temp_dir = Path(settings.temp_dir) / str(media_id)
            temp_dir.mkdir(parents=True, exist_ok=True)

            try:
                output_path = temp_dir / output_filename
                await self._run_pipeline(source_path, output_path, operations)
                final_path = await storage.save_processed(
                    output_path.open("rb"),
                    output_filename,
                    str(media.user_id) if media.user_id else "global",
                )
                return {
                    "media_id": str(media_id),
                    "status": "completed",
                    "output_filename": output_filename,
                    "storage_path": final_path,
                }
            finally:
                shutil.rmtree(temp_dir, ignore_errors=True)

    def _validate_operations(self, operations: list[ProcessingOperation]) -> list[ProcessingOperation]:
        if not operations:
            raise ProcessingEngineError("No operations provided")
        for op in operations:
            if not isinstance(op, (dict, BaseModel)):
                raise ProcessingEngineError(f"Invalid operation type: {type(op)}")
        return operations

    async def _run_pipeline(self, input_path: Path, output_path: Path, operations: list[ProcessingOperation]) -> None:
        current_input = input_path
        temp_files = []

        try:
            for index, op in enumerate(operations):
                if index == len(operations) - 1:
                    current_output = output_path
                else:
                    temp_file = output_path.parent / f"step_{index}_{uuid4().hex[:8]}.mp4"
                    temp_files.append(temp_file)
                    current_output = temp_file

                await self._apply_operation(current_input, current_output, op)
                current_input = current_output
        except Exception:
            for f in temp_files:
                if f.exists():
                    f.unlink(missing_ok=True)
            raise

    async def _apply_operation(self, input_path: Path, output_path: Path, operation: ProcessingOperation) -> None:
        op_type = getattr(operation, "type", None)
        if op_type is None and isinstance(operation, dict):
            op_type = operation.get("type")

        if op_type == "trim":
            from app.features.media.editing import trim_media
            trim_media(str(input_path), str(output_path), operation.start, operation.end)
        elif op_type == "cut":
            from app.features.media.editing import cut_media
            cut_media(str(input_path), str(output_path), operation.start, operation.end)
        elif op_type == "crop":
            from app.features.media.editing import transform_media
            transform_media(str(input_path), str(output_path), "crop", width=operation.width, height=operation.height, x=operation.x, y=operation.y)
        elif op_type == "resize":
            from app.features.media.editing import transform_media
            transform_media(str(input_path), str(output_path), "resize", width=operation.width, height=operation.height)
        elif op_type == "rotate":
            from app.features.media.editing import transform_media
            transform_media(str(input_path), str(output_path), "rotate", angle=operation.angle)
        elif op_type == "flip":
            from app.features.media.editing import transform_media
            transform_media(str(input_path), str(output_path), operation.direction)
        elif op_type == "speed":
            from app.features.media.editing import transform_media
            transform_media(str(input_path), str(output_path), "speed", speed=operation.speed)
        elif op_type == "freeze":
            from app.features.media.editing import freeze_frame
            freeze_frame(str(input_path), str(output_path), operation.timestamp, operation.duration)
        elif op_type == "text_overlay":
            from app.features.media.editing import add_text_overlay
            add_text_overlay(str(input_path), str(output_path), operation.text, operation.x, operation.y, operation.font_size)
        elif op_type == "image_overlay":
            from app.features.media.editing import add_image_overlay
            add_image_overlay(str(input_path), operation.image_path, str(output_path), operation.x, operation.y, operation.opacity)
        elif op_type == "watermark":
            from app.features.media.editing import add_watermark
            add_watermark(str(input_path), operation.image_path, str(output_path), operation.x, operation.y, operation.opacity)
        elif op_type == "convert":
            from app.features.media.conversion import convert_media
            convert_media(
                str(input_path),
                str(output_path),
                output_format=operation.format,
                video_codec=operation.video_codec,
                audio_codec=operation.audio_codec,
                video_bitrate=operation.video_bitrate,
                audio_bitrate=operation.audio_bitrate,
                width=operation.width,
                height=operation.height,
                fps=operation.fps,
                quality=operation.quality,
                aspect_ratio=operation.aspect_ratio,
            )
        elif op_type == "extract_audio":
            from app.features.audio.service import extract_audio
            extract_audio(str(input_path), str(output_path), operation.format, operation.bitrate, operation.sample_rate)
        elif op_type == "merge":
            from app.features.media.merge import merge_media
            paths = [str(await storage.get_file_path(m)) for m in operation.media_ids]
            merge_media(paths, str(output_path))
        elif op_type == "audio_volume":
            from app.features.audio.service import adjust_volume
            adjust_volume(str(input_path), str(output_path), operation.volume, operation.fade_in, operation.fade_out)
        elif op_type == "audio_replace":
            from app.features.audio.service import replace_audio
            replace_audio(str(input_path), operation.audio_path, str(output_path), operation.fade_in, operation.fade_out)
        else:
            raise ProcessingEngineError(f"Unsupported operation: {op_type}")
