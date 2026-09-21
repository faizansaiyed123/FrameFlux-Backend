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
    storage_base_url: str = "http://localhost:8000"

    upload_dir: str = "storage/uploads"
    processed_dir: str = "storage/processed"
    temp_dir: str = "storage/temp"

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    max_upload_size_bytes: int = 500 * 1024 * 1024
    max_chunk_size_bytes: int = 50 * 1024 * 1024

    worker_job_timeout: int = 3600
    worker_max_jobs: int = 4

    max_video_duration_seconds: int = 7200
    max_video_resolution: int = 3840
    max_concurrent_jobs_per_user: int = 10

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

    @property
    def allowed_app_origins(self) -> list[str]:
        return list(
            dict.fromkeys(
                origin.strip()
                for origin in self.app_origin.split(",")
                if origin.strip()
            )
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
