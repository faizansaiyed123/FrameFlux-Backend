from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone, timedelta
from threading import RLock
from uuid import uuid4


def _iso(hours_ago: float = 0) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


DEMO_USER = {
    "id": "demo-user-0001",
    "email": "demo@frameflux.app",
    "full_name": "Demo Editor",
    "is_active": True,
    "created_at": _iso(24 * 120),
    "updated_at": _iso(1),
    "avatar_url": None,
    "preferences": None,
}


def _media(**kwargs):
    base = {
        "user_id": DEMO_USER["id"],
        "duration": None,
        "width": None,
        "height": None,
        "video_codec": None,
        "audio_codec": None,
        "fps": None,
        "project_id": None,
        "folder": None,
        "tags": [],
        "processing_status": "completed",
        "processed_filename": None,
        "processing_error": None,
        "created_at": _iso(4),
    }
    base.update(kwargs)
    return base


def create_state() -> dict:
    projects = [
        {
            "id": "demo-project-001",
            "user_id": DEMO_USER["id"],
            "name": "Product Launch",
            "description": "Launch assets, trailers, and social cutdowns.",
            "created_at": _iso(24 * 18),
            "updated_at": _iso(3),
        },
        {
            "id": "demo-project-002",
            "user_id": DEMO_USER["id"],
            "name": "Brand Refresh",
            "description": "Brand video, interviews, and campaign source footage.",
            "created_at": _iso(24 * 11),
            "updated_at": _iso(8),
        },
        {
            "id": "demo-project-003",
            "user_id": DEMO_USER["id"],
            "name": "Creator Shorts",
            "description": "Fast-turn social clips and vertical exports.",
            "created_at": _iso(24 * 5),
            "updated_at": _iso(1),
        },
    ]

    media = [
        _media(id="demo-media-001", original_filename="product-launch-master.mp4", stored_filename="product-launch-master-demo.mp4",
               media_type="video", mime_type="video/mp4", file_size=148_400_000, project_id=projects[0]["id"],
               folder="Masters", tags=["launch", "master", "hero"], processing_status="completed",
               processed_filename="product-launch-master-demo.mp4", duration=94.4, width=3840, height=2160,
               video_codec="h264", audio_codec="aac", fps="29.97", created_at=_iso(4)),
        _media(id="demo-media-002", original_filename="product-launch-vertical.mp4", stored_filename="product-launch-vertical-demo.mp4",
               media_type="video", mime_type="video/mp4", file_size=58_400_000, project_id=projects[0]["id"],
               folder="Social", tags=["launch", "vertical", "social"], processing_status="processing",
               duration=27.8, width=1080, height=1920, video_codec="h264", audio_codec="aac", fps="30", created_at=_iso(7)),
        _media(id="demo-media-003", original_filename="founder-interview.wav", stored_filename="founder-interview-demo.wav",
               media_type="audio", mime_type="audio/wav", file_size=38_200_000, project_id=projects[1]["id"],
               folder="Interviews", tags=["interview", "founder", "audio"], processed_filename="founder-interview-demo.wav",
               duration=612.2, audio_codec="pcm_s16le", created_at=_iso(10)),
        _media(id="demo-media-004", original_filename="brand-film.mov", stored_filename="brand-film-demo.mov",
               media_type="video", mime_type="video/quicktime", file_size=312_800_000, project_id=projects[1]["id"],
               folder="Masters", tags=["brand", "film"], processing_status="queued",
               duration=156.7, width=3840, height=2160, video_codec="prores", audio_codec="pcm_s24le", fps="24", created_at=_iso(14)),
        _media(id="demo-media-005", original_filename="creator-hook-01.mp4", stored_filename="creator-hook-01-demo.mp4",
               media_type="video", mime_type="video/mp4", file_size=22_900_000, project_id=projects[2]["id"],
               folder="Hooks", tags=["short", "hook", "creator"], processed_filename="creator-hook-01-demo.mp4",
               duration=14.2, width=1080, height=1920, video_codec="h264", audio_codec="aac", fps="30", created_at=_iso(20)),
        _media(id="demo-media-006", original_filename="creator-hook-02.mp4", stored_filename="creator-hook-02-demo.mp4",
               media_type="video", mime_type="video/mp4", file_size=24_100_000, project_id=projects[2]["id"],
               folder="Hooks", tags=["short", "hook", "creator"], processed_filename="creator-hook-02-demo.mp4",
               duration=16.6, width=1080, height=1920, video_codec="h264", audio_codec="aac", fps="30", created_at=_iso(27)),
        _media(id="demo-media-007", original_filename="campaign-thumbnail.png", stored_filename="campaign-thumbnail-demo.png",
               media_type="image", mime_type="image/png", file_size=4_200_000, project_id=projects[1]["id"],
               folder="Brand", tags=["thumbnail", "campaign"], processed_filename="campaign-thumbnail-demo.png",
               width=1920, height=1080, created_at=_iso(32)),
        _media(id="demo-media-008", original_filename="social-teaser.webm", stored_filename="social-teaser-demo.webm",
               media_type="video", mime_type="video/webm", file_size=31_400_000, project_id=None,
               folder="Inbox", tags=["teaser", "webm"], processing_status="failed",
               processing_error="Demo processing failure: unsupported audio track.",
               duration=38.1, width=1920, height=1080, video_codec="vp9", audio_codec="opus", fps="30", created_at=_iso(44)),
    ]

    jobs = [
        {
            "job_id": "demo-job-001", "status": "processing", "progress": 68, "stage": "Encoding",
            "result": None, "error": None, "media_id": "demo-media-002", "project_id": None,
            "operation": "convert", "created_at": _iso(0.6), "started_at": _iso(0.58), "finished_at": None,
        },
        {
            "job_id": "demo-job-002", "status": "queued", "progress": 0, "stage": "Queued",
            "result": None, "error": None, "media_id": "demo-media-004", "project_id": None,
            "operation": "process", "created_at": _iso(0.9), "started_at": None, "finished_at": None,
        },
    ]

    return {
        "user": deepcopy(DEMO_USER),
        "projects": projects,
        "media": media,
        "jobs": jobs,
        "folders": {
            projects[0]["id"]: [
                {"id": "folder-001", "name": "Masters", "parent_id": None},
                {"id": "folder-002", "name": "Social", "parent_id": None},
            ],
            projects[1]["id"]: [
                {"id": "folder-003", "name": "Interviews", "parent_id": None},
                {"id": "folder-004", "name": "Brand", "parent_id": None},
            ],
            projects[2]["id"]: [{"id": "folder-005", "name": "Hooks", "parent_id": None}],
        },
        "workflows": {
            projects[0]["id"]: [{"id": "workflow-001", "user_id": DEMO_USER["id"], "name": "Launch social pack",
                                 "description": "Create social-ready exports from the launch master.",
                                 "is_builtin": True,
                                 "operations": [{"type": "trim"}, {"type": "convert"}, {"type": "thumbnail"}],
                                 "created_at": _iso(24 * 8), "updated_at": _iso(24 * 8)}],
            projects[1]["id"]: [],
            projects[2]["id"]: [],
        },
        "history": {
            projects[0]["id"]: [
                {"id": "history-001", "media_id": "demo-media-001", "operation": "convert", "status": "completed",
                 "settings": None, "error": None, "started_at": None, "finished_at": _iso(5), "created_at": _iso(5)},
                {"id": "history-002", "media_id": "demo-media-001", "operation": "thumbnail", "status": "completed",
                 "settings": None, "error": None, "started_at": None, "finished_at": _iso(19), "created_at": _iso(19)},
            ],
            projects[1]["id"]: [{"id": "history-003", "media_id": "demo-media-003", "operation": "upload", "status": "completed",
                                  "settings": None, "error": None, "started_at": None, "finished_at": _iso(10), "created_at": _iso(10)}],
            projects[2]["id"]: [],
        },
        "notifications": [
            {"id": "notification-001", "event": "processing.completed",
             "message": "product-launch-master.mp4 finished processing.", "is_read": False, "created_at": _iso(2)},
            {"id": "notification-002", "event": "processing.started",
             "message": "creator-hook-02.mp4 is ready for editing.", "is_read": True, "created_at": _iso(7)},
        ],
        "presets": [
            {"id": "preset-001", "user_id": None, "name": "Social 1080x1920",
             "description": "Vertical social export preset.", "is_builtin": True,
             "settings": {"format": "mp4", "resolution": "1080p", "aspect_ratio": "9:16"},
             "created_at": _iso(24 * 20), "updated_at": _iso(24 * 20)},
            {"id": "preset-002", "user_id": None, "name": "Web 1080p",
             "description": "Balanced web delivery preset.", "is_builtin": True,
             "settings": {"format": "webm", "resolution": "1080p", "quality": 30},
             "created_at": _iso(24 * 20), "updated_at": _iso(24 * 20)},
        ],
        "favorites": ["demo-media-001", "demo-media-005"],
        "resumables": [],
        "shares": [],
        "versions": [],
        "preferences": {"theme": "dark", "playback_quality": "auto", "compact_mode": "false"},
        "quick_actions": {
            "video": [
                {"id": "compress", "label": "Compress", "icon": "minimize-2"},
                {"id": "convert", "label": "Convert", "icon": "repeat-2"},
                {"id": "thumbnail", "label": "Thumbnail", "icon": "image"},
            ],
            "audio": [
                {"id": "extract-audio", "label": "Extract audio", "icon": "audio-lines"},
                {"id": "convert-audio", "label": "Convert audio", "icon": "refresh-cw"},
            ],
            "image": [
                {"id": "resize", "label": "Resize", "icon": "maximize-2"},
                {"id": "thumbnail", "label": "Preview", "icon": "image"},
            ],
        },
        "last_reset_at": _iso(),
    }


class DemoStore:
    def __init__(self):
        self._lock = RLock()
        self.state = create_state()

    def snapshot(self):
        with self._lock:
            return deepcopy(self.state)

    def reset(self):
        with self._lock:
            self.state = create_state()
            return deepcopy(self.state)

    def update(self, fn):
        with self._lock:
            return fn(self.state)


store = DemoStore()
