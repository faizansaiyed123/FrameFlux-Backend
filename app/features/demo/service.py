import asyncio
import hashlib
import hmac
import secrets
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, hash_password
from app.features.auth.models import User
from app.features.demo.models import DemoSession
from app.features.jobs.models import ProcessingJob
from app.features.media.models import Media
from app.features.projects.models import Project

settings = get_settings()


def hash_client_ip(client_ip: str) -> str:
    digest = hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        client_ip.encode("utf-8"),
        hashlib.sha256,
    )
    return digest.hexdigest()


async def create_demo_workspace(
    db: AsyncSession,
    client_ip_hash: str,
) -> tuple[DemoSession, User, Project, Media, str]:
    if not settings.demo_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo mode is unavailable")

    now = datetime.now(timezone.utc)
    active_count = await db.scalar(
        select(func.count(DemoSession.id)).where(
            DemoSession.client_ip_hash == client_ip_hash,
            DemoSession.expires_at > now,
            DemoSession.revoked_at.is_(None),
            DemoSession.cleaned_at.is_(None),
        )
    )
    if int(active_count or 0) >= settings.demo_max_active_sessions_per_ip:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many active demo workspaces from this network. End an existing session or try later.",
        )

    user_id = uuid4()
    user = User(
        id=user_id,
        email=f"demo-{user_id.hex}@example.com",
        password_hash=hash_password(secrets.token_urlsafe(48)),
        full_name="FrameFlux Demo",
        is_active=True,
    )
    expires_at = now + timedelta(minutes=settings.demo_session_ttl_minutes)
    demo_session = DemoSession(
        user_id=user_id,
        client_ip_hash=client_ip_hash,
        expires_at=expires_at,
        cleanup_state="active",
    )
    project = Project(
        user_id=user_id,
        name="FrameFlux Demo Workspace",
        description="Synthetic media used to explore real FrameFlux processing workflows.",
    )

    upload_root = Path(settings.upload_dir).resolve()
    upload_root.mkdir(parents=True, exist_ok=True)
    stored_filename = f"demo-{uuid4().hex}.mp4"
    processed_filename = f"demo-{uuid4().hex}-preview.mp4"
    source_path = upload_root / stored_filename
    preview_path = upload_root / processed_filename

    command = [
        settings.ffmpeg_binary,
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "testsrc2=size=320x180:rate=24",
        "-t", "5",
        "-an",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "32",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        "-y",
        str(source_path),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        if process.returncode != 0 or not source_path.is_file():
            message = stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Could not create synthetic media fixture: {message}")
        shutil.copyfile(source_path, preview_path)
        file_size = source_path.stat().st_size
        if file_size <= 0 or file_size > settings.demo_max_storage_bytes:
            raise RuntimeError("Synthetic media fixture exceeded the demo storage budget")
    except Exception as exc:
        source_path.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="The demo media fixture is not ready. Please try again later.",
        ) from exc

    sample_media = Media(
        user_id=user_id,
        project_id=project.id,
        original_filename="frameflux-synthetic-test-pattern.mp4",
        stored_filename=stored_filename,
        processed_filename=processed_filename,
        media_type="video",
        mime_type="video/mp4",
        file_size=file_size,
        duration=5.0,
        width=320,
        height=180,
        video_codec="h264",
        fps="24/1",
        processing_status="completed",
        processing_error=None,
    )

    db.add_all([user, demo_session, project, sample_media])
    try:
        await db.commit()
        await db.refresh(user)
        await db.refresh(demo_session)
        await db.refresh(project)
        await db.refresh(sample_media)
    except Exception:
        await db.rollback()
        source_path.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise

    token = create_access_token(
        user.id,
        extra_claims={"demo_session_id": str(demo_session.id)},
        expires_minutes=settings.demo_session_ttl_minutes,
    )
    return demo_session, user, project, sample_media, token


async def get_active_demo_session(
    db: AsyncSession,
    user_id: UUID,
) -> DemoSession | None:
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(DemoSession).where(
            DemoSession.user_id == user_id,
            DemoSession.revoked_at.is_(None),
            DemoSession.expires_at > now,
            DemoSession.cleaned_at.is_(None),
        )
    )
    return result.scalar_one_or_none()


async def enforce_demo_upload_quota(
    db: AsyncSession,
    user_id: UUID,
    incoming_bytes: int,
) -> None:
    demo_session = await get_active_demo_session(db, user_id)
    if demo_session is None:
        return
    if incoming_bytes < 0 or incoming_bytes > settings.demo_max_upload_size_bytes:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Demo uploads are limited to {settings.demo_max_upload_size_bytes // (1024 * 1024)} MB per file.",
        )
    count, total_bytes = (
        await db.execute(
            select(func.count(Media.id), func.coalesce(func.sum(Media.file_size), 0)).where(
                Media.user_id == user_id
            )
        )
    ).one()
    if count >= settings.demo_max_media_files or total_bytes + incoming_bytes > settings.demo_max_storage_bytes:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This demo workspace has reached its media limit. End the demo to reset the workspace.",
        )


async def enforce_demo_job_quota(db: AsyncSession, user_id: UUID) -> None:
    demo_session = await get_active_demo_session(db, user_id)
    if demo_session is None:
        return
    media_active = await db.scalar(
        select(func.count(Media.id)).where(
            Media.user_id == user_id,
            Media.processing_status.in_([ "pending", "processing" ]),
        )
    )
    jobs_active = await db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.user_id == user_id,
            ProcessingJob.status.in_(["queued", "running", "retrying"]),
        )
    )
    if int(media_active or 0) + int(jobs_active or 0) > settings.demo_max_concurrent_jobs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The demo workspace allows one active processing job at a time.",
        )
