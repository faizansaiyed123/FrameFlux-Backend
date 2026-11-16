# FrameFlux backend recruiter demo

The `demo` branch includes a standalone backend target that is intentionally isolated from the production application.

## Run

From this repository:

```bash
uv run uvicorn app.demo.main:app --host 0.0.0.0 --port 8000
```

Or with the repository's Python environment:

```python
python -m uvicorn app.demo.main:app --host 0.0.0.0 --port 8000
```

The demo server does **not** import the production `app.main:app`, does not require PostgreSQL or Redis, and does not run FFmpeg. State lives in memory for the current process.

## What it demonstrates

The demo server exposes the same core HTTP shapes used by the recruiter frontend: authentication/profile, projects, media, uploads, processing jobs, versions, batch operations, storage, search, notifications, preferences, favorites, quick actions, sharing, previews, thumbnails, subtitles, audio/video operations, and reset.

Media-processing operations create simulated jobs and advance their progress when the job is queried. Generated media is representative demo content, not a real FFmpeg export.

Use:

`POST /demo/reset`

to restore the seeded workspace.

## Production isolation

The production backend remains at `app.main:app`. This demo target is only added on the `demo` branch and uses its own in-memory state. No production database schema, worker code, or deployment entrypoint is changed by the demo server.
