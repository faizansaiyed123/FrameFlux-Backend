from datetime import datetime

from pydantic import BaseModel

from app.features.auth.schemas import UserResponse
from app.features.media.schemas import MediaResponse
from app.features.projects.schemas import ProjectResponse


class DemoSessionResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    demo_session_id: str
    expires_at: datetime
    user: UserResponse
    project: ProjectResponse
    sample_media: MediaResponse


class DemoSessionEndResponse(BaseModel):
    detail: str
    cleanup_state: str
