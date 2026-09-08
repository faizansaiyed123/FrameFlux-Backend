# FrameFlux Backend API Documentation

FrameFlux is a high-performance media processing and editing backend built with FastAPI, PostgreSQL, Redis, ARQ background task queues, and FFmpeg.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI HTTP Service                     │
│  /media  |  /media/resumable  |  /jobs  |  /projects        │
└───────────────┬─────────────────────────────┬───────────────┘
                │                             │
       PostgreSQL (AsyncPG)             Redis & ARQ
       - Media metadata                 - Job progress tracking
       - Project relations              - Distributed task queue
       - Status records                 - Resumable chunk manifests
                                              │
                                    ARQ Worker (FFmpeg)
                                    - Probe & Transcode
                                    - Clip, Trim, Split, Merge
                                    - Watermark & Overlays
```

---

## Configuration & Size Limits

Configuration is loaded via Pydantic settings from environment variables or `.env`:

| Variable | Default | Description |
| :--- | :--- | :--- |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL async connection string |
| `REDIS_URL` | `redis://redis:6379/0` | Redis connection for ARQ queue and progress state |
| `UPLOAD_DIR` | `storage/uploads` | Path to store uploaded media |
| `PROCESSED_DIR` | `storage/processed` | Path to store exported media |
| `TEMP_DIR` | `storage/temp` | Temporary working and chunk storage |
| `FFMPEG_BINARY` | `ffmpeg` | Path to FFmpeg executable |
| `FFPROBE_BINARY` | `ffprobe` | Path to FFprobe executable |
| `MAX_UPLOAD_SIZE_BYTES` | `524288000` (500 MB) | Maximum permitted total upload file size |
| `MAX_CHUNK_SIZE_BYTES` | `52428800` (50 MB) | Maximum permitted individual upload chunk size |

### Validation & Security Policies
- **Extension Allowlist**: Supported extensions include `.mp4`, `.mov`, `.avi`, `.mkv`, `.webm`, `.mp3`, `.wav`, `.m4a`, `.jpg`, `.jpeg`, `.png`, `.webp`, `.srt`, `.vtt`.
- **MIME Type Validation**: Rejects disallowed, script, or executable MIME types (e.g. `application/x-executable`, `text/html`, `application/javascript`). Enforces category matching between extension and MIME type.
- **Binary Signature Inspection**: Inspects the first bytes of uploads to block DOS/PE (`MZ`), Linux ELF (`\x7fELF`), Mach-O binaries, compiled bytecode, and injected script payloads.
- **HTTP Status Codes**:
  - `400 Bad Request`: Returned for missing filenames, unsupported extensions, invalid MIME categories, empty files, or invalid content signatures.
  - `413 Content Too Large`: Returned when a file exceeds `MAX_UPLOAD_SIZE_BYTES` or a chunk exceeds `MAX_CHUNK_SIZE_BYTES`.

---

## Media Upload APIs

### 1. Direct Upload
**`POST /media/upload`**  
Uploads a single media file in multipart/form-data.

- **Request**: `multipart/form-data` with `file`
- **Response** (`201 Created`):
```json
{
  "id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "original_filename": "clip.mp4",
  "stored_filename": "d3b07384d113edec49eaa6238ad5ff00.mp4",
  "media_type": "video",
  "mime_type": "video/mp4",
  "file_size": 15482910,
  "processing_status": "pending",
  "project_id": null,
  "created_at": "2026-09-08T10:00:00Z"
}
```

---

### 2. Resumable Chunked Uploads
Designed for large files, unstable connections, and pause/resume support.

- **Initialize Upload Session**:  
  **`POST /media/resumable/init`**  
  ```json
  {
    "original_filename": "raw_footage.mp4",
    "total_size": 104857600,
    "chunk_size": 10485760
  }
  ```
  Returns `200 OK` with `{"upload_id": "<uuid>"}`.

- **Upload Chunk**:  
  **`POST /media/resumable/{upload_id}/chunk/{index}`**  
  Multipart form with `file` representing the chunk index (`0`, `1`, ...).

- **Pause Session**:  
  **`POST /media/resumable/{upload_id}/pause`**  
  Pauses the resumable session state in Redis.

- **Resume Session**:  
  **`POST /media/resumable/{upload_id}/resume`**  
  Resumes the paused upload session.

- **Retry Chunk**:  
  **`POST /media/resumable/{upload_id}/retry?index={index}`**  
  Re-uploads a specific chunk.

- **Cancel Upload**:  
  **`DELETE /media/resumable/{upload_id}`**  
  Cancels the upload session and deletes temporary chunks from disk and Redis.

- **Finalize Upload**:  
  **`POST /media/resumable/{upload_id}/finalize`**  
  Assembles all chunks in sequence, verifies file signatures, cleans up temporary storage, and creates the persistent `Media` record (`200 OK`).

---

## Media Processing, Status & Progress APIs

### 1. Enqueue Processing
**`POST /media/{media_id}/process`**  
Extracts technical metadata (duration, width, height, codecs, fps) and generates a poster thumbnail.
- Returns `200 OK` with `{"media_id": "<uuid>", "status": "queued", "job_id": "<arq_job_id>"}`.
- Returns `409 Conflict` if the media is already queued, processing, or completed.

### 2. Status Monitoring
**`GET /media/{media_id}/status`**  
Fetches the processing status and error diagnostics, along with real-time percentage progress if actively processing.
```json
{
  "media_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "status": "processing",
  "progress": 65,
  "error": null,
  "processed_filename": null
}
```

### 3. Real-Time Progress
**`GET /media/{media_id}/progress`**  
Queries real-time progress from Redis:
```json
{
  "media_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "progress": 65,
  "status": "processing"
}
```

---

## Background Jobs APIs

Inspect and monitor background ARQ tasks:

- **List Jobs**:  
  **`GET /jobs`**  
  Returns all registered background tasks with their current execution status and timestamps.
- **Get Job Details**:  
  **`GET /jobs/{job_id}`**  
  Returns execution details, function name, arguments, and completion status for a specific job.

---

## Media Editing & Conversion APIs

All media transformation endpoints submit asynchronous jobs to the ARQ worker and return `200 OK` with the queued `job_id`.

### 1. Format Conversion & Audio/Video Options
**`POST /media/{media_id}/convert`**  
```json
{
  "format": "webm",
  "aspect_ratio": "16:9",
  "resolution": "1080p",
  "quality": 23,
  "video_codec": "libvpx-vp9",
  "video_bitrate": "2M",
  "audio_codec": "opus",
  "audio_bitrate": "128k"
}
```

### 2. Trimming, Cutting & Extraction
**`POST /media/{media_id}/edit`**  
```json
{
  "operation": "trim",
  "start": 5.0,
  "end": 15.0
}
```
Supported operations: `trim`, `cut`, `extract`.

### 3. Media Splitting
**`POST /media/{media_id}/split`**  
```json
{
  "split_points": [10.0, 25.5, 60.0]
}
```
Splits media at the specified timestamps into segmented files.

### 4. Multi-Clip Operations
- **Keep Clips**: `POST /media/{media_id}/clips/keep`  
  Extracts and concatenates the specified ranges: `{"clips": [{"start": 0, "end": 10}, {"start": 20, "end": 30}]}`
- **Delete Clips**: `POST /media/{media_id}/clips/delete`  
  Removes the specified segments and stitches the remainder.
- **Reorder Clips**: `POST /media/{media_id}/clips/reorder`  
  Reorders a list of clips: `{"media_ids": ["clip2.mp4", "clip1.mp4"]}`
- **Append Clips**: `POST /media/{media_id}/clips/append`  
  Appends clips to the current media: `{"media_ids": ["intro.mp4", "outro.mp4"]}`

### 5. Overlays & Watermarks
**`POST /media/{media_id}/overlay`**  
Supports single text, image watermarks, or arrays of multiple overlays:
```json
{
  "overlays": [
    {
      "operation": "text",
      "text": "Live Broadcast",
      "x": 40,
      "y": 40,
      "font_size": 24,
      "font_color": "white"
    },
    {
      "operation": "watermark",
      "image_filename": "logo.png",
      "opacity": 0.8
    }
  ]
}
```

### 6. Video Transformations
**`POST /media/{media_id}/transform`**  
Applies geometric transformations or playback speed alterations:
```json
{
  "operation": "speed",
  "speed": 1.5
}
```
Operations: `scale`, `rotate`, `crop`, `speed`.

### 7. Freeze Frame
**`POST /media/{media_id}/freeze`**  
Creates a freeze-frame pause at a timestamp for a given duration:
```json
{
  "timestamp": 4.5,
  "duration": 2.0
}
```

---

## Projects APIs

Organize media into collaborative projects and process assets in batches.

- **Create Project**: `POST /projects` (`{"name": "Project Alpha", "description": "..."}`)
- **List Projects**: `GET /projects`
- **Get Project**: `GET /projects/{project_id}`
- **Update Project**: `PATCH /projects/{project_id}`
- **Delete Project**: `DELETE /projects/{project_id}`
- **List Project Media**: `GET /projects/{project_id}/media`
- **Batch Process Project**: `POST /projects/{project_id}/process` (queues background processing for all media in the project)
- **Aggregated Status**: `GET /projects/{project_id}/status` (returns counts for `completed`, `processing`, `queued`, `failed`, and overall status)

---

## Testing & Quality Assurance

Run the test suite using `pytest`:

```bash
pytest
```

The test suite covers:
- **Validation**: Filename, extensions, MIME categories, executable signature detection, and size limits (400 and 413 responses).
- **Uploads**: Direct uploads, resumable initialization, chunk streaming, pause/resume, retry, cancel, and finalize.
- **Media Processing & Editing**: Metadata probe, conversions, trims, cuts, splits, overlays, transforms, freeze frames, and clip management.
- **Status & Progress Tracking**: Real-time Redis progress reporting and task status aggregation.
- **Jobs & Projects APIs**: Background task tracking, project CRUD, batch processing, and status rollup.
