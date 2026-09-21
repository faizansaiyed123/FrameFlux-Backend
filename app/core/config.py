from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FrameFlux API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str
    redis_url: str

    app_origin: str = "http://localhost:3000"
    api_base_url: str = "http://localhost:8000"

    upload_dir: str = "storage/uploads"
    processed_dir: str = "storage/processed"
    temp_dir: str = "storage/temp"

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    # Configurable file-size limits
    max_upload_size_bytes: int = 500 * 1024 * 1024  # 500 MB
    max_chunk_size_bytes: int = 50 * 1024 * 1024   # 50 MB

    # Worker limits
    worker_job_timeout: int = 3600  # 1 hour
    worker_max_jobs: int = 4

    # Resource limits
    max_video_duration_seconds: int = 7200  # 2 hours
    max_video_resolution: int = 3840  # 4K width
    max_concurrent_jobs_per_user: int = 10

    # Auth / JWT settings
    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    password_reset_expire_minutes: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    def get_worker_job_timeout(self) -> int:
        return self.worker_job_timeout

    def get_worker_max_jobs(self) -> int:
        return self.worker_max_jobs


@lru_cache
def get_settings() -> Settings:
    return Settings()
