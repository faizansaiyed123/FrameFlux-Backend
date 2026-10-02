from functools import lru_cache

from pydantic import model_validator
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
    trust_proxy_headers: bool = False

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

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if self.environment.lower() == "production":
            if self.debug:
                raise ValueError("DEBUG must be false in production")
            for name, value in (
                ("APP_ORIGIN", self.app_origin),
                ("API_BASE_URL", self.api_base_url),
                ("STORAGE_BASE_URL", self.storage_base_url),
            ):
                if not value or "localhost" in value.lower() or "127.0.0.1" in value:
                    raise ValueError(f"{name} must be a non-local production URL")
            if len(self.jwt_secret_key) < 32 or self.jwt_secret_key.startswith("CHANGE_ME"):
                raise ValueError("JWT_SECRET_KEY must be a strong production secret")
        return self

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
