from pydantic import BaseModel, ConfigDict, Field
from typing import Any, Literal
from uuid import UUID


class BatchUploadRequest(BaseModel):
    files: list[str] = Field(min_length=1, max_length=50, description="List of file paths to upload")


class BatchUploadResponse(BaseModel):
    job_id: str
    total_files: int
    status: str


class BatchOperationRequest(BaseModel):
    media_ids: list[UUID] = Field(min_length=1, max_length=50)
    operation: Literal["convert", "compress", "extract_audio", "generate_thumbnail", "generate_preview", "trim", "cut", "crop", "resize", "rotate", "remove_audio", "replace_audio", "add_subtitles", "create_gif"]
    options: dict[str, Any] = Field(default_factory=dict)


class BatchOperationResponse(BaseModel):
    job_id: str
    total_items: int
    operation: str
    status: str
    results: list[dict[str, Any]]


class BatchResultResponse(BaseModel):
    job_id: str
    status: str
    total: int
    completed: int
    failed: int
    results: list[dict[str, Any]]
