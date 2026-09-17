from pydantic import BaseModel
from typing import Optional


class ImageConvertRequest(BaseModel):
    format: str
    width: Optional[int] = None
    height: Optional[int] = None
    quality: Optional[int] = None