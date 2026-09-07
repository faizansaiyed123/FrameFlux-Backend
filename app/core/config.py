from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FrameFlux API"
    app_version: str = "0.1.0"
    environment: str = "development"
    debug: bool = False

    database_url: str
    redis_url: str

    upload_dir: str = "storage/uploads"
    processed_dir: str = "storage/processed"
    temp_dir: str = "storage/temp"

    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
