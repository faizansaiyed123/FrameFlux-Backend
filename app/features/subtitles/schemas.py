from pydantic import BaseModel, ConfigDict, Field
from typing import Literal


class SubtitleTrackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int | str
    codec: str | None = None
    language: str | None = None
    title: str | None = None
    is_default: bool = False
    is_forced: bool = False


class SubtitleEditRequest(BaseModel):
    operation: Literal["update_text", "update_timing", "add_entry", "delete_entry", "split_entry", "merge_entries", "change_position", "change_font", "change_size", "change_color", "change_background", "change_alignment"]
    entry_index: int | None = None
    start: float | None = None
    end: float | None = None
    text: str | None = None
    position: str | None = None
    font: str | None = None
    size: int | None = None
    color: str | None = None
    background_color: str | None = None
    alignment: str | None = None


class SubtitleBurnRequest(BaseModel):
    subtitle_path: str
    font_size: int = 24
    font_color: str = "white"
    background_color: str = "black@0.5"
    position: str = "bottom"
    font: str | None = None
    alignment: str | None = None


class SubtitleSyncRequest(BaseModel):
    subtitle_path: str
    offset_seconds: float = 0.0
    scale: float = 1.0
    preview: bool = False
