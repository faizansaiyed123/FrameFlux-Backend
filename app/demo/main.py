from __future__ import annotations

import json
import time
from datetime import datetime, timezone, timedelta
from pathlib import PurePosixPath
from typing import Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from app.demo.state import store


app = FastAPI(
    title="FrameFlux Recruiter Demo API",
    version="demo-1.0.0",
    description="Standalone in-memory demo backend. Production services are not imported.",
)

app.add_middleware(
    CORSMiddleware,
    # Browser fetches use credentials: "include". Reflect approved HTTP(S)
    # origins so credentialed CORS requests are accepted in demo environments.
    allow_origins=[],
    allow_origin_regex=r"https?://[^/]+",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class DemoMessage(BaseModel):
    detail: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id(prefix: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}"


def _json(request: Request) -> dict:
    return request.state.body if hasattr(request.state, "body") and isinstance(request.state.body, dict) else {}


async def _read_json(request: Request) -> dict:
    try:
        payload = await request.json()
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


async def _read_form(request: Request) -> dict:
    try:
        form = await request.form()
        result: dict[str, Any] = {}
        for key, value in form.multi_items():
            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(value)
            else:
                result[key] = value
        return result
    except Exception:
        return {}


def _media(state: dict, media_id: str) -> dict | None:
    return next((m for m in state["media"] if m["id"] == media_id), None)


def _project(state: dict, project_id: str) -> dict | None:
    return next((p for p in state["projects"] if p["id"] == project_id), None)


def _media_result(media: dict, operation: str, job_id: str) -> dict:
    ext = media["original_filename"].rsplit(".", 1)[-1] if "." in media["original_filename"] else "mp4"
    stem = media["original_filename"].rsplit(".", 1)[0]
    return {
        "media_id": media["id"],
        "status": "queued",
        "operation": operation,
        "job_id": job_id,
        "output_filename": f"{stem}-{operation}-demo.{ext}",
    }


def _queue_job(state: dict, media_id: str | None, operation: str, project_id: str | None = None) -> dict:
    job_id = _new_id("demo-job")
    job = {
        "job_id": job_id,
        "status": "processing",
        "progress": 8,
        "stage": "Preparing demo output",
        "result": None,
        "error": None,
        "media_id": media_id,
        "project_id": project_id,
        "operation": operation,
        "created_at": _now(),
        "started_at": _now(),
        "finished_at": None,
        "_last_touch": time.monotonic(),
    }
    state["jobs"].insert(0, job)
    if media_id:
        media = _media(state, media_id)
        if media:
            media["processing_status"] = "processing"
            media["processing_error"] = None
    return job


def _advance_jobs(state: dict) -> None:
    now = time.monotonic()
    for job in state["jobs"]:
        if job.get("status") not in {"queued", "processing"}:
            continue
        last = job.get("_last_touch", now)
        steps = max(0, int((now - last) // 0.5))
        if steps <= 0:
            continue
        job["_last_touch"] = now
        if job["status"] == "queued":
            job["status"] = "processing"
            job["stage"] = "Working"
        job["progress"] = min(100, int(job["progress"]) + steps * 17)
        if job["progress"] >= 100:
            job["progress"] = 100
            job["status"] = "completed"
            job["stage"] = "Completed"
            job["finished_at"] = _now()
            job["result"] = {
                "demo": True,
                "message": f"Simulated {job['operation']} output generated for recruiter demo.",
            }
            media_id = job.get("media_id")
            if media_id:
                media = _media(state, media_id)
                if media:
                    media["processing_status"] = "completed"
                    if not media.get("processed_filename"):
                        media["processed_filename"] = media["stored_filename"]


def _job_public(job: dict) -> dict:
    return {k: v for k, v in job.items() if not k.startswith("_")}


def _storage_rows(state: dict, field: str):
    totals: dict[str, dict[str, int]] = {}
    for media in state["media"]:
        key = media.get(field) or "Unassigned"
        row = totals.setdefault(key, {"total_size": 0, "count": 0})
        row["total_size"] += int(media.get("file_size") or 0)
        row["count"] += 1
    return totals


def _placeholder_bytes(media: dict | None, kind: str = "media") -> tuple[bytes, str]:
    name = media["original_filename"] if media else "FrameFlux demo asset"
    svg = (
        "<svg xmlns='http://www.w3.org/2000/svg' width='1280' height='720' viewBox='0 0 1280 720'>"
        "<rect width='100%' height='100%' fill='#111827'/>"
        "<text x='64' y='320' font-family='Arial, sans-serif' font-size='42' fill='#f9fafb'>"
        f"FrameFlux Demo — {name}</text>"
        f"<text x='64' y='380' font-family='Arial, sans-serif' font-size='24' fill='#9ca3af'>"
        f"Representative {kind} output</text></svg>"
    ).encode()
    return svg, "image/svg+xml"


@app.get("/")
async def root():
    return {"name": "FrameFlux Recruiter Demo API", "mode": "demo", "reset": "/demo/reset"}


@app.get("/health")
async def health():
    return {"status": "ok", "mode": "demo", "dependencies": {"postgres": "not-used", "redis": "not-used", "ffmpeg": "simulated"}}


@app.post("/demo/reset")
async def demo_reset():
    state = store.reset()
    return {"status": "reset", "last_reset_at": state["last_reset_at"]}


@app.api_route("/{full_path:path}", methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"])
async def demo_api(full_path: str, request: Request):
    path = "/" + full_path.lstrip("/")
    method = request.method
    state = store.state
    _advance_jobs(state)
    query = dict(request.query_params)

    if path in {"/docs", "/openapi.json"}:
        return JSONResponse({"message": "Use the demo app API routes. This standalone server intentionally keeps the generated schema minimal."})

    if path == "/auth/signup" and method == "POST":
        body = await _read_json(request)
        user = dict(state["user"])
        user["email"] = body.get("email") or user["email"]
        user["full_name"] = body.get("full_name") or user["full_name"]
        user["updated_at"] = _now()
        state["user"] = user
        return JSONResponse(user, status_code=201)

    if path == "/auth/login" and method == "POST":
        return {"access_token": "frameflux-demo-token", "token_type": "bearer", "expires_in": 3600}

    if path == "/auth/logout" and method == "POST":
        return {"detail": "Successfully logged out."}

    if path == "/auth/me" and method == "GET":
        return state["user"]

    if path == "/auth/me" and method == "PATCH":
        body = await _read_json(request)
        state["user"].update({k: v for k, v in body.items() if k in {"full_name", "avatar_url", "preferences"}})
        state["user"]["updated_at"] = _now()
        return state["user"]

    if path in {"/auth/forgot-password", "/auth/reset-password", "/auth/change-password"} and method == "POST":
        return {"detail": "Demo action completed successfully."}

    if path == "/dashboard/overview" and method == "GET":
        media = state["media"]
        by_type: dict[str, int] = {}
        by_status: dict[str, int] = {}
        for item in media:
            by_type[item["media_type"]] = by_type.get(item["media_type"], 0) + 1
            by_status[item["processing_status"]] = by_status.get(item["processing_status"], 0) + 1
        projects = []
        for project in state["projects"]:
            count = sum(1 for item in media if item.get("project_id") == project["id"])
            projects.append({**project, "media_count": count})
        return {
            "total_projects": len(state["projects"]),
            "total_media": len(media),
            "media_by_type": by_type,
            "processing_status_counts": by_status,
            "total_storage_used_bytes": sum(int(m.get("file_size") or 0) for m in media),
            "recent_projects": projects[:5],
            "recent_media": media[:8],
            "active_jobs_count": sum(1 for job in state["jobs"] if job["status"] in {"queued", "processing"}),
        }

    if path.startswith("/dashboard/recent-processing") and method == "GET":
        limit = int(query.get("limit", "10"))
        return [_job_public(job) for job in state["jobs"][:limit]]

    if path == "/projects" and method == "GET":
        return state["projects"]

    if path == "/projects" and method == "POST":
        body = await _read_json(request)
        project = {
            "id": _new_id("demo-project"),
            "user_id": state["user"]["id"],
            "name": body.get("name") or "Untitled Project",
            "description": body.get("description"),
            "created_at": _now(),
            "updated_at": _now(),
        }
        state["projects"].insert(0, project)
        state["folders"][project["id"]] = []
        state["workflows"][project["id"]] = []
        state["history"][project["id"]] = []
        return JSONResponse(project, status_code=201)

    parts = [part for part in path.split("/") if part]
    if len(parts) >= 2 and parts[0] == "projects":
        project_id = parts[1]
        project = _project(state, project_id)
        if project is None:
            return JSONResponse({"detail": "Project not found"}, status_code=404)

        if len(parts) == 2 and method == "GET":
            return project
        if len(parts) == 2 and method == "PATCH":
            body = await _read_json(request)
            if "name" in body:
                project["name"] = body["name"]
            if "description" in body:
                project["description"] = body["description"]
            project["updated_at"] = _now()
            return project
        if len(parts) == 2 and method == "DELETE":
            state["projects"] = [item for item in state["projects"] if item["id"] != project_id]
            state["media"] = [item for item in state["media"] if item.get("project_id") != project_id]
            return Response(status_code=204)

        if parts[2:] == ["media"] and method == "GET":
            return [m for m in state["media"] if m.get("project_id") == project_id]
        if parts[2:] == ["process"] and method == "POST":
            media = [m for m in state["media"] if m.get("project_id") == project_id]
            jobs = []
            for item in media:
                job = _queue_job(state, item["id"], "process", project_id)
                jobs.append({"media_id": item["id"], "job_id": job["job_id"]})
            return {"project_id": project_id, "status": "queued", "jobs": jobs}
        if parts[2:] == ["status"] and method == "GET":
            media = [m for m in state["media"] if m.get("project_id") == project_id]
            counts = {key: sum(1 for m in media if m["processing_status"] == key) for key in ["completed", "processing", "queued", "failed"]}
            if not media:
                status = "empty"
            elif counts["failed"]:
                status = "failed"
            elif counts["completed"] == len(media):
                status = "completed"
            elif counts["processing"]:
                status = "processing"
            else:
                status = "queued"
            return {"project_id": project_id, "status": status, "total": len(media), **counts}
        if parts[2:] == ["folders"] and method == "GET":
            return state["folders"].get(project_id, [])
        if parts[2:] == ["folders"] and method == "POST":
            folder = {"id": _new_id("folder"), "name": query.get("name") or "New Folder", "parent_id": query.get("parent_id")}
            state["folders"].setdefault(project_id, []).append(folder)
            return folder
        if parts[2:] == ["workflows"] and method == "GET":
            return [{"id": w["id"], "name": w["name"]} for w in state["workflows"].get(project_id, [])]
        if parts[2:] == ["history"] and method == "GET":
            return state["history"].get(project_id, [])


    if path == "/media/batch-download" and method == "POST":
        body = await _read_json(request)
        ids = body.get("media_ids") or []
        selected = [m for m in state["media"] if m["id"] in ids]
        return {
            "jobs": [{"media_id": m["id"], "original_filename": m["original_filename"], "file_size": m["file_size"]} for m in selected],
            "total": len(selected),
        }

    if path == "/media" and method == "GET":
        result = list(state["media"])
        search = query.get("search", "").lower()
        media_type = query.get("media_type")
        folder = query.get("folder")
        tag = query.get("tag")
        if search:
            result = [m for m in result if search in m["original_filename"].lower() or search in (m.get("folder") or "").lower()]
        if media_type:
            result = [m for m in result if m["media_type"] == media_type]
        if folder:
            result = [m for m in result if m.get("folder") == folder]
        if tag:
            result = [m for m in result if tag in (m.get("tags") or [])]
        return result

    if path == "/media/upload" and method == "POST":
        form = await _read_form(request)
        uploaded = form.get("file")
        filename = getattr(uploaded, "filename", None) or "demo-upload.mp4"
        content_type = getattr(uploaded, "content_type", None) or "video/mp4"
        media_type = "audio" if content_type.startswith("audio/") else "image" if content_type.startswith("image/") else "video"
        size = 0
        try:
            content = await uploaded.read()
            size = len(content)
        except Exception:
            pass
        suffix = filename.rsplit(".", 1)[-1] if "." in filename else "mp4"
        media = {
            "id": _new_id("demo-media"), "user_id": state["user"]["id"], "original_filename": filename,
            "stored_filename": f"{_new_id('upload')}.{suffix}", "media_type": media_type,
            "mime_type": content_type, "file_size": size or 1_000_000, "project_id": None,
            "folder": "Inbox", "tags": ["uploaded", "demo"], "processing_status": "completed",
            "processed_filename": None, "processing_error": None, "duration": None,
            "width": None, "height": None, "video_codec": None, "audio_codec": None, "fps": None,
            "created_at": _now(),
        }
        state["media"].insert(0, media)
        return JSONResponse(media, status_code=201)

    if path == "/media/upload-multiple" and method == "POST":
        form = await _read_form(request)
        files = form.get("files", [])
        if not isinstance(files, list):
            files = [files]
        created = []
        for uploaded in files:
            filename = getattr(uploaded, "filename", None) or "demo-upload.mp4"
            content_type = getattr(uploaded, "content_type", None) or "video/mp4"
            media_type = "audio" if content_type.startswith("audio/") else "image" if content_type.startswith("image/") else "video"
            try:
                content = await uploaded.read()
                size = len(content)
            except Exception:
                size = 1_000_000
            item = {
                "id": _new_id("demo-media"), "user_id": state["user"]["id"], "original_filename": filename,
                "stored_filename": f"{_new_id('upload')}.{filename.rsplit('.', 1)[-1] if '.' in filename else 'mp4'}",
                "media_type": media_type, "mime_type": content_type, "file_size": size or 1_000_000,
                "project_id": None, "folder": "Inbox", "tags": ["uploaded", "demo"], "processing_status": "completed",
                "processed_filename": None, "processing_error": None, "duration": None, "width": None, "height": None,
                "video_codec": None, "audio_codec": None, "fps": None, "created_at": _now(),
            }
            state["media"].insert(0, item)
            created.append(item)
        return created

    if path.startswith("/media/resumable/"):
        rest = parts[2:]
        upload_id = parts[2] if len(parts) > 2 else ""
        resumable = next((r for r in state["resumables"] if r["upload_id"] == upload_id), None)
        if path == "/media/resumable/init" and method == "POST":
            body = await _read_json(request)
            resumable = {
                "upload_id": _new_id("upload"), "filename": body.get("original_filename") or "demo-upload.mp4",
                "total_size": int(body.get("total_size") or 0), "uploaded_size": 0, "status": "active", "progress": 0,
            }
            state["resumables"].append(resumable)
            return {"upload_id": resumable["upload_id"]}
        if resumable:
            if len(parts) >= 4 and parts[3] == "chunk" and method == "POST":
                chunk_index = int(parts[4]) if len(parts) > 4 else 0
                chunk_size = int(query.get("chunk_size", "1"))
                resumable["uploaded_size"] = min(resumable["total_size"], resumable["uploaded_size"] + max(chunk_size, 1))
                resumable["progress"] = round((resumable["uploaded_size"] / resumable["total_size"]) * 100) if resumable["total_size"] else 100
                return {"upload_id": upload_id, "index": chunk_index, "status": "uploaded", "progress": resumable["progress"]}
            if len(parts) == 4 and parts[3] == "pause" and method == "POST":
                resumable["status"] = "paused"; return {"status": "paused"}
            if len(parts) == 4 and parts[3] == "resume" and method == "POST":
                resumable["status"] = "active"; return {"status": "active"}
            if len(parts) == 4 and parts[3] == "retry" and method == "POST":
                return {"status": "retrying", "index": query.get("index")}
            if len(parts) == 3 and method == "DELETE":
                resumable["status"] = "cancelled"; return {"status": "cancelled"}
            if len(parts) == 4 and parts[3] == "finalize" and method == "POST":
                resumable["status"] = "completed"; resumable["progress"] = 100
                item = {
                    "id": _new_id("demo-media"), "user_id": state["user"]["id"],
                    "original_filename": resumable["filename"], "stored_filename": resumable["filename"],
                    "media_type": "video", "mime_type": "video/mp4", "file_size": resumable["total_size"] or 1_000_000,
                    "project_id": None, "folder": "Inbox", "tags": ["resumable", "demo"], "processing_status": "completed",
                    "processed_filename": None, "processing_error": None, "duration": None, "width": None, "height": None,
                    "video_codec": None, "audio_codec": None, "fps": None, "created_at": _now(),
                }
                state["media"].insert(0, item)
                return item


    if path.startswith("/media/uploads/") and path.endswith("/progress") and method == "GET":
        upload_id = parts[2] if len(parts) > 2 else ""
        resumable = next((r for r in state["resumables"] if r["upload_id"] == upload_id), None)
        if resumable:
            return {"upload_id": upload_id, "progress": resumable["progress"], "status": resumable["status"]}
        return {"upload_id": upload_id, "progress": 100, "status": "completed"}

    if len(parts) >= 2 and parts[0] == "media":
        media_id = parts[1]
        media = _media(state, media_id)
        if media is None:
            return JSONResponse({"detail": "Media not found"}, status_code=404)

        action = "/".join(parts[2:])
        if not action and method == "GET":
            return media
        if not action and method == "DELETE":
            state["media"] = [m for m in state["media"] if m["id"] != media_id]
            state["favorites"] = [m for m in state["favorites"] if m != media_id]
            return Response(status_code=204)
        if action in {"download", "processed"} and method == "GET":
            payload, mime = _placeholder_bytes(media, "download")
            return Response(payload, media_type=mime)
        if action == "status" and method == "GET":
            job = next((j for j in state["jobs"] if j.get("media_id") == media_id and j["status"] in {"queued", "processing"}), None)
            return {"media_id": media_id, "status": media["processing_status"], "progress": job["progress"] if job else (100 if media["processing_status"] == "completed" else 0),
                    "error": media.get("processing_error"), "processed_filename": media.get("processed_filename")}
        if action == "progress" and method == "GET":
            job = next((j for j in state["jobs"] if j.get("media_id") == media_id and j["status"] in {"queued", "processing"}), None)
            return {"media_id": media_id, "status": media["processing_status"], "progress": job["progress"] if job else 100}
        if action == "process" and method == "POST":
            job = _queue_job(state, media_id, "process")
            return {"media_id": media_id, "status": "queued", "job_id": job["job_id"]}

        if action in {"extract", "convert", "to-video"} and method == "POST":
            payload, mime = _placeholder_bytes(media, "audio")
            return Response(payload, media_type=mime)

        if action in {"compress", "convert", "edit", "merge", "transform", "freeze", "overlay"} and method == "POST":
            body = await _read_json(request)
            operation = action
            if action == "edit":
                operation = body.get("operation") or "edit"
            job = _queue_job(state, media_id, operation)
            return _media_result(media, operation, job["job_id"]) | ({"operation": operation} if action == "edit" else {})
        if action == "split" and method == "POST":
            job = _queue_job(state, media_id, "split")
            return {"media_id": media_id, "status": "queued", "operation": "split", "job_id": job["job_id"], "output_prefix": f"{media['original_filename']}-part"}
        if action.startswith("clips/") and method == "POST":
            op = action.split("/", 1)[1]
            job = _queue_job(state, media_id, op)
            return _media_result(media, op, job["job_id"])
        if action == "project" and len(parts) >= 4 and method == "PATCH":
            return media
        if action.startswith("project/") and len(parts) >= 4 and method == "PATCH":
            project_id = parts[3]
            if _project(state, project_id):
                media["project_id"] = project_id
            return media
        if action == "versions" and method == "GET":
            return [v for v in state["versions"] if v["media_id"] == media_id]
        if action.startswith("versions/"):
            version_id = parts[3]
            version = next((v for v in state["versions"] if v["id"] == version_id), None)
            if action.endswith("/restore") and method == "POST" and version:
                media.update({k: version[k] for k in ("original_filename", "stored_filename", "file_size", "mime_type", "duration", "width", "height", "video_codec", "audio_codec", "fps") if k in version})
                return {"status": "restored", "media_id": media_id, "version_id": version_id}
            if version and method == "GET":
                return version
            if version and method == "DELETE":
                state["versions"] = [v for v in state["versions"] if v["id"] != version_id]
                return Response(status_code=204)

    if path == "/jobs" and method == "GET":
        return [_job_public(job) for job in state["jobs"]]
    if len(parts) == 2 and parts[0] == "jobs" and method == "GET":
        job = next((j for j in state["jobs"] if j["job_id"] == parts[1]), None)
        if job:
            return _job_public(job)
        return JSONResponse({"detail": "Job not found"}, status_code=404)

    if path == "/batch" or path.startswith("/batch/"):
        if method == "POST":
            job = _queue_job(state, None, "batch")
            return {"job_id": job["job_id"], "status": "queued"}
        if len(parts) >= 3 and parts[2] == "status":
            job = next((j for j in state["jobs"] if j["job_id"] == parts[1]), None)
            return _job_public(job) if job else {"job_id": parts[1], "status": "completed", "progress": 100}

    if path == "/presets" and method == "GET":
        return state["presets"]
    if path == "/presets" and method == "POST":
        body = await _read_json(request)
        preset = {"id": _new_id("preset"), "user_id": state["user"]["id"], "name": body.get("name", "Demo Preset"),
                  "description": body.get("description"), "is_builtin": False, "settings": body.get("settings", {}),
                  "created_at": _now(), "updated_at": _now()}
        state["presets"].insert(0, preset)
        return preset
    if len(parts) == 2 and parts[0] == "presets":
        if method == "GET":
            preset = next((p for p in state["presets"] if p["id"] == parts[1]), None); return preset or JSONResponse({"detail": "Preset not found"}, status_code=404)
        if method == "DELETE":
            state["presets"] = [p for p in state["presets"] if p["id"] != parts[1]]; return Response(status_code=204)
        if method in {"PATCH", "PUT"}:
            body = await _read_json(request)
            preset = next((p for p in state["presets"] if p["id"] == parts[1]), None)
            if preset:
                preset.update(body); preset["updated_at"] = _now()
                return preset

    if path == "/workflows" and method == "GET":
        return [workflow for group in state["workflows"].values() for workflow in group]
    if path == "/workflows" and method == "POST":
        body = await _read_json(request)
        workflow = {"id": _new_id("workflow"), "user_id": state["user"]["id"], "name": body.get("name", "Demo workflow"),
                    "description": body.get("description"), "is_builtin": False, "operations": body.get("operations", []),
                    "created_at": _now(), "updated_at": _now()}
        state["workflows"].setdefault("", []).append(workflow)
        return workflow
    if len(parts) == 2 and parts[0] == "workflows":
        wf = next((w for group in state["workflows"].values() for w in group if w["id"] == parts[1]), None)
        if method == "GET": return wf or JSONResponse({"detail": "Workflow not found"}, status_code=404)
        if method == "DELETE": 
            for project_id, group in state["workflows"].items(): state["workflows"][project_id] = [w for w in group if w["id"] != parts[1]]
            return Response(status_code=204)
    if len(parts) == 3 and parts[0] == "workflows" and parts[2] == "run" and method == "POST":
        job = _queue_job(state, query.get("media_id"), "workflow")
        return {"status": "queued", "job_id": job["job_id"]}

    if path == "/storage/usage" and method == "GET":
        return {"total_size": sum(int(m.get("file_size") or 0) for m in state["media"]), "total_files": len(state["media"]), "user_id": state["user"]["id"]}
    if path == "/storage/usage/by-type" and method == "GET":
        rows = _storage_rows(state, "media_type"); return [{"media_type": k, **v} for k, v in rows.items()]
    if path == "/storage/usage/by-folder" and method == "GET":
        rows = _storage_rows(state, "folder"); return [{"folder": k, **v} for k, v in rows.items()]

    if path == "/search/media" and method == "GET":
        result = list(state["media"])
        q = query.get("q", "").lower()
        if q: result = [m for m in result if q in m["original_filename"].lower() or q in " ".join(m.get("tags") or []).lower()]
        if query.get("media_type"): result = [m for m in result if m["media_type"] == query["media_type"]]
        if query.get("folder"): result = [m for m in result if m.get("folder") == query["folder"]]
        if query.get("tag"): result = [m for m in result if query["tag"] in (m.get("tags") or [])]
        if query.get("processing_status"): result = [m for m in result if m["processing_status"] == query["processing_status"]]
        return [{"id": m["id"], "original_filename": m["original_filename"], "media_type": m["media_type"], "file_size": m["file_size"],
                 "duration": m["duration"], "processing_status": m["processing_status"], "folder": m["folder"], "tags": ",".join(m["tags"] or []), "created_at": m["created_at"]} for m in result]

    if path == "/history" and method == "GET":
        return [entry for group in state["history"].values() for entry in group]
    if path == "/history" and method == "POST":
        entry = {"id": _new_id("history"), "media_id": query.get("media_id"), "operation": query.get("operation", "demo"),
                 "status": query.get("status", "completed"), "settings": None, "error": None, "started_at": None,
                 "finished_at": _now(), "created_at": _now()}
        state["history"].setdefault("global", []).insert(0, entry)
        return entry

    if path == "/notifications" and method == "GET":
        page = int(query.get("page", "1")); page_size = int(query.get("page_size", "20"))
        items = [n for n in state["notifications"] if not query.get("unread_only") or not n["is_read"]]
        start = max(0, (page - 1) * page_size)
        page_items = items[start:start + page_size]
        return {"items": page_items, "page": page, "page_size": page_size, "total": len(items), "total_pages": max(1, (len(items) + page_size - 1) // page_size)}
    if path == "/notifications" and method == "POST":
        body = await _read_json(request)
        note = {"id": _new_id("notification"), "event": body.get("event", "demo.event"), "message": body.get("message", "Demo notification"),
                "is_read": False, "created_at": _now()}
        state["notifications"].insert(0, note); return note
    if path == "/notifications/unread-count" and method == "GET":
        return {"unread_count": sum(1 for n in state["notifications"] if not n["is_read"])}
    if path == "/notifications/read-all" and method == "POST":
        for n in state["notifications"]: n["is_read"] = True
        return {"status": "ok"}
    if len(parts) == 3 and parts[0] == "notifications" and parts[2] == "read" and method == "POST":
        note = next((n for n in state["notifications"] if n["id"] == parts[1]), None)
        if note: note["is_read"] = True
        return note or JSONResponse({"detail": "Notification not found"}, status_code=404)

    if path == "/ui/preferences" and method == "GET":
        return [{"id": f"pref-{k}", "key": k, "value": v, "updated_at": _now()} for k, v in state["preferences"].items()]
    if path.startswith("/ui/preferences/"):
        key = parts[2]
        if method in {"POST", "PUT", "PATCH"}:
            body = await _read_json(request)
            state["preferences"][key] = str(body.get("value", ""))
        return {"key": key, "value": state["preferences"].get(key, "")}

    if path == "/favorites" and method == "GET":
        return [{"id": f"favorite-{m}", "media_id": m, "user_id": state["user"]["id"], "created_at": _now()} for m in state["favorites"]]
    if path == "/favorites" and method == "POST":
        body = await _read_json(request); media_id = body.get("media_id")
        if media_id and media_id not in state["favorites"]: state["favorites"].append(media_id)
        return {"id": f"favorite-{media_id}", "media_id": media_id, "user_id": state["user"]["id"], "created_at": _now()}
    if len(parts) == 2 and parts[0] == "favorites" and method == "DELETE":
        state["favorites"] = [m for m in state["favorites"] if m != parts[1]]; return Response(status_code=204)

    if path == "/quick-actions" and method == "GET":
        return state["quick_actions"]
    if len(parts) == 3 and parts[0] == "quick-actions" and parts[2] == "execute" and method == "POST":
        return {"media_id": parts[1], "action_id": query.get("action_id", "unknown"), "status": "queued"}

    if path == "/sharing" and method == "GET":
        return state["shares"]
    if path == "/sharing" and method == "POST":
        body = await _read_json(request)
        token = _new_id("share").replace("-", "")
        expires = None
        if body.get("expires_in_hours"):
            expires = (datetime.now(timezone.utc) + timedelta(hours=float(body["expires_in_hours"]))).isoformat()
        share = {"id": _new_id("share"), "media_id": body.get("media_id"), "token": token, "has_password": bool(body.get("password")),
                 "expires_at": expires, "is_active": True, "allow_download": body.get("allow_download", True),
                 "view_count": 0, "allowed_domains": body.get("allowed_domains"), "created_at": _now()}
        state["shares"].insert(0, share); return share
    if len(parts) == 2 and parts[0] == "sharing" and method == "GET":
        share = next((s for s in state["shares"] if s["token"] == parts[1]), None)
        if share:
            share["view_count"] += 1
            return share
        return JSONResponse({"detail": "Share not found"}, status_code=404)
    if len(parts) == 3 and parts[0] == "sharing" and parts[1] == "embed" and method == "GET":
        token = parts[2]
        return {"embed_url": f"https://demo.frameflux.app/share/{token}", "embed_code": f"<iframe src='https://demo.frameflux.app/share/{token}'></iframe>", "media_title": "FrameFlux demo media"}
    if len(parts) == 3 and parts[0] == "sharing" and parts[2] == "disable" and method == "POST":
        share = next((s for s in state["shares"] if s["id"] == parts[1]), None)
        if share: share["is_active"] = False
        return share or JSONResponse({"detail": "Share not found"}, status_code=404)
    if len(parts) == 2 and parts[0] == "sharing" and method == "DELETE":
        state["shares"] = [s for s in state["shares"] if s["id"] != parts[1]]; return Response(status_code=204)

    if path.startswith("/media-info/") and method == "GET":
        media = _media(state, parts[1])
        if media:
            return {"media_id": media["id"], "filename": media["original_filename"], "mime_type": media["mime_type"],
                    "file_size": media["file_size"], "duration": media["duration"], "width": media["width"], "height": media["height"],
                    "video_codec": media["video_codec"], "audio_codec": media["audio_codec"], "fps": media["fps"]}
        return JSONResponse({"detail": "Media not found"}, status_code=404)

    if path.startswith("/thumbnails/") and method in {"GET", "POST"}:
        media = _media(state, parts[1])
        if path.endswith("/set") or path.endswith("/crop") or path.endswith("/select"):
            return {"media_id": parts[1], "status": "completed", "thumbnail_url": f"/demo/thumbnails/{parts[1]}.svg"}
        return {"media_id": parts[1], "thumbnail_url": f"/demo/thumbnails/{parts[1]}.svg"}

    if path.startswith("/preview/") or path.startswith("/gif/"):
        media_id = parts[1] if len(parts) > 1 else None
        media = _media(state, media_id) if media_id else None
        payload, mime = _placeholder_bytes(media, "preview")
        return Response(payload, media_type=mime)


    if path == "/subtitles/upload" and method == "POST":
        form = await _read_form(request)
        uploaded = form.get("file")
        return {
            "id": _new_id("subtitle"),
            "filename": getattr(uploaded, "filename", None) or "captions.srt",
            "status": "uploaded",
        }

    if path.startswith("/subtitles/") or path.startswith("/video/") or path.startswith("/audio/") or path.startswith("/images/") or path.startswith("/export/") or path.startswith("/metadata/") or path.startswith("/comparisons/"):
        if method == "GET":
            media_id = next((p for p in reversed(parts) if _media(state, p)), None)
            media = _media(state, media_id) if media_id else None
            payload, mime = _placeholder_bytes(media, "demo response")
            if path.startswith("/subtitles/"):
                return {"media_id": media_id, "tracks": [], "status": "completed"} if path.endswith("/tracks") else {"status": "completed"}
            if path.startswith("/comparisons/"):
                return {"media_a": parts[-2], "media_b": parts[-1], "differences": [], "status": "ready"}
            return Response(payload, media_type=mime)
        media_id = next((p for p in reversed(parts) if _media(state, p)), None)
        if media_id:
            job = _queue_job(state, media_id, parts[0], None)
            return {"media_id": media_id, "status": "queued", "job_id": job["job_id"], "output_filename": f"demo-{parts[0].strip('/')}.mp4"}
        return {"status": "completed"}

    if path == "/demo/runtime" and method == "GET":
        return {"mode": "in-memory", "persistent": False, "production_isolated": True}

    return JSONResponse({"detail": f"Demo endpoint not implemented: {method} {path}"}, status_code=404)
