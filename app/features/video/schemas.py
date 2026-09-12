from pydantic import BaseModel, ConfigDict, Field


class VideoAdjustRequest(BaseModel):
    brightness: float | None = Field(default=None, ge=-1.0, le=1.0, description="Brightness adjustment (-1 to 1)")
    contrast: float | None = Field(default=None, ge=0.0, le=2.0, description="Contrast adjustment (0 to 2)")
    saturation: float | None = Field(default=None, ge=0.0, le=3.0, description="Saturation adjustment (0 to 3)")
    gamma: float | None = Field(default=None, ge=0.1, le=10.0, description="Gamma correction (0.1 to 10)")
    hue: float | None = Field(default=None, ge=0.0, le=360.0, description="Hue rotation in degrees (0 to 360)")


class VideoFilterRequest(BaseModel):
    operation: str = Field(description="Filter operation: sharpen, blur")
    intensity: float | None = Field(default=1.0, gt=0, description="Filter intensity factor")


class VideoFadeRequest(BaseModel):
    fade_type: str = Field(description="Fade type: in or out")
    duration: float = Field(gt=0, description="Fade duration in seconds")
    start_time: float | None = Field(default=0.0, ge=0, description="Start time for fade")


class VideoReverseRequest(BaseModel):
    output_format: str = Field(default="mp4", description="Output container format")


class VideoAdjustResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    output_filename: str
    operation: str
    media_id: str
