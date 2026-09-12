from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class JobStatusResponse(BaseModel):
    job_id: str
    status: str = Field(
        description="Job status: queued, processing, completed, failed, or not_found"
    )
    progress: int = Field(
        default=0,
        ge=0,
        le=100,
        description="Processing progress percentage from 0 to 100",
    )
    stage: str | None = Field(
        default=None,
        description="Human-readable stage description of the current task",
    )
    task_name: str | None = Field(
        default=None,
        description="Name of the background task function being executed",
    )
    media_id: str | None = Field(
        default=None,
        description="Associated media UUID",
    )
    enqueue_time: datetime | str | None = Field(
        default=None,
        description="Time the job was enqueued",
    )
    start_time: datetime | str | None = Field(
        default=None,
        description="Time the worker started running the job",
    )
    finish_time: datetime | str | None = Field(
        default=None,
        description="Time the job completed or failed",
    )
    success: bool | None = Field(
        default=None,
        description="Whether the job succeeded (true/false) or is still running (null)",
    )
    result: Any | None = Field(
        default=None,
        description="Result payload returned by the task on success",
    )
    error: str | None = Field(
        default=None,
        description="Error message if the job failed",
    )


class ProcessingJobResponse(BaseModel):
    job_id: str
    media_id: str | None = None
    media_version_id: str | None = None
    task_name: str
    status: str
    progress: int = Field(default=0, ge=0, le=100)
    stage: str | None = None
    error: str | None = None
    operation_type: str | None = None
    retry_count: int = 0
    enqueued_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
