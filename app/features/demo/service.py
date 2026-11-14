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
from app.features.media.models import Media, MediaVersion
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
    source_path = upload_root / stored_filename

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
        try:
            _, stderr = await asyncio.wait_for(process.communicate(), timeout=30)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise RuntimeError("Synthetic media generation exceeded its 30-second limit")
        if process.returncode != 0 or not source_path.is_file():
            message = stderr.decode("utf-8", errors="replace")[-1000:]
            raise RuntimeError(f"Could not create synthetic media fixture: {message}")
        file_size = source_path.stat().st_size
        if file_size <= 0 or file_size > settings.demo_max_storage_bytes:
            raise RuntimeError("Synthetic media fixture exceeded the demo storage budget")
    except Exception as exc:
        source_path.unlink(missing_ok=True)
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
        processed_filename=None,
        media_type="video",
        mime_type="video/mp4",
        file_size=file_size,
        duration=5.0,
        width=320,
        height=180,
        video_codec="h264",
        fps="24/1",
        processing_status="pending",
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
    incoming_files: int = 1,
    is_demo_user: bool = False,
) -> None:
    if not is_demo_user:
        return
    demo_session = await get_active_demo_session(db, user_id)
    if demo_session is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Demo session is no longer active.",
        )
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
    if count + incoming_files > settings.demo_max_media_files or total_bytes + incoming_bytes > settings.demo_max_storage_bytes:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="This demo workspace has reached its media limit. End the demo to reset the workspace.",
        )


async def enforce_demo_job_quota(
    db: AsyncSession,
    user_id: UUID,
    exclude_media_id: UUID | None = None,
) -> None:
    demo_session = await get_active_demo_session(db, user_id)
    if demo_session is None:
        return
    media_query = select(func.count(Media.id)).where(
        Media.user_id == user_id,
        Media.processing_status.in_(["queued", "processing"]),
    )
    if exclude_media_id is not None:
        media_query = media_query.where(Media.id != exclude_media_id)
    media_active = await db.scalar(media_query)
    jobs_active = await db.scalar(
        select(func.count(ProcessingJob.id)).where(
            ProcessingJob.user_id == user_id,
            ProcessingJob.status.in_(["queued", "running", "retrying"]),
        )
    )
    if max(int(media_active or 0), int(jobs_active or 0)) >= settings.demo_max_concurrent_jobs_per_user:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="The demo workspace allows one active processing job at a time.",
        )


async def end_demo_session(db: AsyncSession, user_id: UUID) -> str:
    demo_session = await get_active_demo_session(db, user_id)
    if demo_session is None:
        # An expired or already-ended session is not an active browser session.
        return "already-ended"
    now = datetime.now(timezone.utc)
    demo_session.revoked_at = now
    demo_session.cleanup_state = "pending"
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is not None:
        user.is_active = False
    await db.commit()
    await cleanup_expired_demo_sessions(db, session_ids=[demo_session.id])
    return "cleanup-requested"


async def _delete_owned_redis_state(user_id: UUID, media_ids: list[UUID], job_ids: list[str]) -> bool:
    from app.infrastructure.redis import get_redis_client

    redis = get_redis_client()
    try:
        # Resumable-upload keys contain an owner field. Never delete by prefix alone.
        async for key in redis.scan_iter(match="resumable_upload:*", count=200):
            metadata = await redis.hgetall(key)
            if metadata.get("user_id") == str(user_id):
                upload_id = key.rsplit(":", 1)[-1]
                temp_dir = Path(settings.upload_dir) / "resumable" / upload_id
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
                await redis.delete(key)

        # Upload-progress hashes are similarly scoped by their stored owner.
        async for key in redis.scan_iter(match="upload:progress:*", count=200):
            metadata = await redis.hgetall(key)
            if metadata.get("user_id") == str(user_id):
                await redis.delete(key)

        discovered_job_ids = set(job_ids)
        for media_id in media_ids:
            last_job_id = await redis.get(f"media:last_job:{media_id}")
            if last_job_id:
                discovered_job_ids.add(str(last_job_id))
            await redis.delete(
                f"media:progress:{media_id}",
                f"media:last_job:{media_id}",
            )
        for job_id in discovered_job_ids:
            await redis.delete(f"job:progress:{job_id}")
        return True
    except Exception:
        return False
    finally:
        await redis.aclose()


def _safe_remove_upload_file(filename: str | None) -> bool:
    if not filename:
        return True
    root = Path(settings.upload_dir).resolve()
    candidate = (root / filename).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    try:
        candidate.unlink(missing_ok=True)
        return True
    except OSError:
        return False


async def cleanup_expired_demo_sessions(
    db: AsyncSession,
    session_ids: list[UUID] | None = None,
    batch_size: int = 25,
) -> dict[str, int]:
    """Revoke and remove only expired demo-owned data; defer while media jobs run."""
    from sqlalchemy import delete, or_

    from app.features.comparisons.models import MediaComparison
    from app.features.favorites.models import Favorite
    from app.features.history.models import ProcessingHistory
    from app.features.notifications.models import Notification
    from app.features.presets.models import Preset
    from app.features.projects.folder_models import ProjectFolder
    from app.features.sharing.models import ShareLink
    from app.features.ui.models import UserPreference
    from app.features.video.models import VideoAdjustment
    from app.features.workflows.models import Workflow

    now = datetime.now(timezone.utc)
    query = select(DemoSession).where(
        DemoSession.cleaned_at.is_(None),
        or_(
            DemoSession.expires_at <= now,
            DemoSession.revoked_at.is_not(None),
        ),
    )
    if session_ids:
        query = query.where(DemoSession.id.in_(session_ids))
    query = query.order_by(DemoSession.expires_at).limit(batch_size).with_for_update(skip_locked=True)
    result = await db.execute(query)
    sessions = list(result.scalars().all())

    cleaned = 0
    waiting = 0
    failed = 0

    for demo_session in sessions:
        demo_session.revoked_at = demo_session.revoked_at or now
        demo_session.cleanup_state = "waiting_for_jobs"
        user_result = await db.execute(select(User).where(User.id == demo_session.user_id))
        user = user_result.scalar_one_or_none()
        if user is None:
            demo_session.cleaned_at = now
            demo_session.cleanup_state = "cleaned"
            await db.commit()
            cleaned += 1
            continue

        user.is_active = False
        media_result = await db.execute(select(Media).where(Media.user_id == user.id))
        media_rows = list(media_result.scalars().all())
        media_ids = [item.id for item in media_rows]

        # Queued/running media is allowed to finish before its files are removed.
        active_media = await db.scalar(
            select(func.count(Media.id)).where(
                Media.user_id == user.id,
                Media.processing_status.in_(["queued", "processing"]),
            )
        )
        active_jobs = await db.scalar(
            select(func.count(ProcessingJob.id)).where(
                ProcessingJob.user_id == user.id,
                ProcessingJob.status.in_(["queued", "running", "retrying"]),
            )
        )
        if int(active_media or 0) + int(active_jobs or 0) > 0:
            demo_session.cleanup_state = "waiting_for_jobs"
            await db.commit()
            waiting += 1
            continue

        job_result = await db.execute(
            select(ProcessingJob.arq_job_id).where(
                ProcessingJob.user_id == user.id,
                ProcessingJob.arq_job_id.is_not(None),
            )
        )
        job_ids = [value for value in job_result.scalars().all() if value]
        version_result = await db.execute(
            select(MediaVersion).where(MediaVersion.media_id.in_(media_ids))
        ) if media_ids else None
        versions = list(version_result.scalars().all()) if version_result is not None else []
        project_result = await db.execute(select(Project.id).where(Project.user_id == user.id))
        project_ids = list(project_result.scalars().all())

        if not await _delete_owned_redis_state(user.id, media_ids, job_ids):
            demo_session.cleanup_state = "waiting_for_redis"
            await db.commit()
            failed += 1
            continue

        files_ok = True
        for media in media_rows:
            files_ok = _safe_remove_upload_file(media.stored_filename) and files_ok
            files_ok = _safe_remove_upload_file(media.processed_filename) and files_ok
        for version in versions:
            files_ok = _safe_remove_upload_file(version.stored_filename) and files_ok
        if not files_ok:
            demo_session.cleanup_state = "waiting_for_files"
            await db.commit()
            failed += 1
            continue

        # These legacy tables use soft UUID references rather than cascading FKs.
        if media_ids:
            await db.execute(
                delete(MediaComparison).where(
                    or_(
                        MediaComparison.media_a_id.in_(media_ids),
                        MediaComparison.media_b_id.in_(media_ids),
                    )
                )
            )
            await db.execute(delete(VideoAdjustment).where(VideoAdjustment.media_id.in_(media_ids)))
        if project_ids:
            await db.execute(delete(ProjectFolder).where(ProjectFolder.project_id.in_(project_ids)))
        await db.execute(delete(ProcessingHistory).where(ProcessingHistory.user_id == user.id))
        await db.execute(delete(Notification).where(Notification.user_id == user.id))
        await db.execute(delete(ShareLink).where(ShareLink.user_id == user.id))
        await db.execute(delete(Workflow).where(Workflow.user_id == user.id))
        await db.execute(delete(UserPreference).where(UserPreference.user_id == user.id))
        await db.execute(delete(Preset).where(Preset.user_id == user.id))
        await db.execute(delete(Favorite).where(Favorite.user_id == user.id))

        demo_session.cleanup_state = "cleaned"
        demo_session.cleaned_at = now
        await db.delete(user)
        await db.commit()
        cleaned += 1

    return {"cleaned": cleaned, "waiting_for_jobs": waiting, "failed_cleanup": failed}
