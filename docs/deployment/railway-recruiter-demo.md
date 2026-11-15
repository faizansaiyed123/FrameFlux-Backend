# FrameFlux recruiter demo deployment on Railway

This branch is deployment-only preparation for an isolated recruiter environment.

## Runtime topology

Use one Railway service for the recruiter API and ARQ worker together:

1. FrameFlux recruiter service — builds Dockerfile.recruiter-demo, runs FastAPI and the ARQ worker under Supervisor, and owns the media volume at /app/storage.
2. PostgreSQL — dedicated database for recruiter sessions and synthetic product data.
3. Redis — dedicated ARQ queue, upload manifests, and progress state.

This single-service API + worker arrangement is intentional. Railway volumes attach to one service, so the API and worker must share the same process/container when the application uses local shared media storage. Do not create separate API and worker services that each mount different volumes and expect the files to be shared.

## Recruiter service

railway.json selects Dockerfile.recruiter-demo.

The startup script:

- creates the mounted storage directories,
- waits for PostgreSQL by retrying Alembic migrations,
- starts FastAPI,
- starts the ARQ worker,
- keeps both processes supervised and restartable.

The Railway service should expose the API and use:

- public HTTPS networking,
- /health/ready as the healthcheck,
- a persistent volume mounted at /app/storage.

The recruiter deployment must use its own isolated Postgres, Redis and storage. Do not copy production/customer data.

## Required variables

Set these on the recruiter service from the dedicated Railway resources and generated deployment URLs:

- DATABASE_URL
- REDIS_URL
- APP_ORIGIN
- API_BASE_URL
- STORAGE_BASE_URL
- JWT_SECRET_KEY

Keep these recruiter controls enabled only on this isolated deployment:

- DEMO_ENABLED=true
- DEMO_SESSION_TTL_MINUTES=120
- DEMO_MAX_ACTIVE_SESSIONS_PER_IP=2
- DEMO_BOOTSTRAP_REQUESTS_PER_IP=3
- DEMO_BOOTSTRAP_WINDOW_SECONDS=3600
- DEMO_MAX_UPLOAD_SIZE_BYTES=15728640
- DEMO_MAX_CHUNK_SIZE_BYTES=2097152
- DEMO_MAX_STORAGE_BYTES=41943040
- DEMO_MAX_MEDIA_FILES=4
- DEMO_MAX_CONCURRENT_JOBS_PER_USER=1

The normal FrameFlux deployment must keep DEMO_ENABLED=false.

## Frontend

Once the recruiter API has a verified public HTTPS URL, build the dedicated recruiter frontend with:

- NEXT_PUBLIC_API_URL=<verified recruiter API URL>
- NEXT_PUBLIC_DEMO_ENABLED=true

The ordinary production frontend must continue using NEXT_PUBLIC_DEMO_ENABLED=false.

## Verification gate

Deployment preparation is not proof that the demo works.

Before changing the portfolio status from verification-pending, verify from a clean browser/session that:

1. the recruiter workspace can be created without signup,
2. the seeded synthetic video opens in the real editor,
3. an actual media-processing job reaches the ARQ worker and FFmpeg,
4. progress and the processed output are visible,
5. at least one genuine failure/retry path is tested when supported,
6. a second recruiter session cannot see the first session's data,
7. ending the demo revokes access and removes or queues the session data for cleanup,
8. the normal production account path remains unchanged.

Only the observed deployment URL and runtime behavior should be written into the portfolio after this verification.
