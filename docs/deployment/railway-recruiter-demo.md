# FrameFlux deployment on Railway

This repository contains the production container used for the FrameFlux API and worker.

## Services

Run four isolated services in the Railway project:

1. PostgreSQL — application database.
2. Redis — ARQ queue, resumable-upload manifests and progress.
3. API — this repository, using the root Dockerfile and railway.json.
4. Worker — this repository, using the same Dockerfile with the service start command overridden to `uv run --no-sync arq app.infrastructure.worker.WorkerSettings`.

The API service should expose its public URL and use `/health/ready` for the deployment healthcheck.

## Required API variables

Set these from the Railway PostgreSQL/Redis service connection values and the public frontend/API URLs:

- `DATABASE_URL`
- `REDIS_URL`
- `APP_ORIGIN`
- `API_BASE_URL`
- `STORAGE_BASE_URL`
- `JWT_SECRET_KEY`

For the isolated recruiter demo deployment, explicitly enable `DEMO_ENABLED=true` and keep the demo limits documented in `.env.example`.

Do not copy real production/customer data into this environment.

## Worker

The worker needs the same `DATABASE_URL`, `REDIS_URL`, FFmpeg settings, job limits and `JWT_SECRET_KEY` values as the API. It does not need a public HTTP endpoint.

Attach a persistent volume to both API and worker services at `/app/storage` so the worker can consume uploaded media and the API can serve processed files.

## Frontend

After the API receives its public HTTPS URL, build the FrameFlux frontend with `NEXT_PUBLIC_API_URL=<public API URL>` and `NEXT_PUBLIC_DEMO_ENABLED=true`.

The ordinary production frontend should keep `NEXT_PUBLIC_DEMO_ENABLED=false` until the dedicated demo API is verified end-to-end.
