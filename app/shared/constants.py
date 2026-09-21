"""Shared constants across the FrameFlux backend."""

DEFAULT_MAX_UPLOAD_SIZE_BYTES = 500 * 1024 * 1024
DEFAULT_MAX_CHUNK_SIZE_BYTES = 50 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".mp4", ".mov", ".avi", ".mkv", ".webm",
    ".mp3", ".wav", ".m4a", ".aiff", ".aif", ".wma",
    ".ogg", ".flac", ".opus",
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".tiff", ".tif",
    ".srt", ".vtt", ".ass",
}

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm"}
AUDIO_EXTENSIONS = {
    ".mp3", ".wav", ".m4a", ".aiff", ".aif", ".wma",
    ".ogg", ".flac", ".opus",
}
IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp",
    ".tiff", ".tif",
}
SUBTITLE_EXTENSIONS = {".srt", ".vtt", ".ass"}

EXTENSION_TO_MIME = {
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".gif": "image/gif",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".m4a": "audio/mp4",
    ".aiff": "audio/aiff",
    ".aif": "audio/aiff",
    ".wma": "audio/x-ms-wma",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".opus": "audio/opus",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".srt": "text/plain",
    ".vtt": "text/vtt",
    ".ass": "text/plain",
}

ALLOWED_MIME_TYPES = {
    "video/mp4", "video/quicktime", "video/x-msvideo",
    "video/x-matroska", "video/webm", "video/avi", "video/msvideo",
    "audio/mpeg", "audio/mp3", "audio/wav", "audio/wave",
    "audio/x-wav", "audio/x-pn-wav", "audio/mp4", "audio/m4a",
    "audio/x-m4a", "audio/aac", "audio/ogg", "audio/aiff",
    "audio/x-aiff", "audio/x-ms-wma", "audio/flac", "audio/opus",
    "image/jpeg", "image/png", "image/webp", "image/gif",
    "image/bmp", "image/tiff",
    "text/plain", "text/vtt", "application/x-subrip",
    "text/x-subrip", "text/srt", "application/octet-stream",
}

DISALLOWED_MIME_PREFIXES = (
    "application/x-dosexec",
    "application/x-executable",
    "application/x-msdownload",
    "application/x-sh",
    "application/x-bat",
    "application/x-csh",
    "application/x-python",
    "text/html",
    "text/javascript",
    "application/javascript",
    "application/json",
    "application/xml",
    "application/zip",
    "application/x-tar",
    "application/gzip",
)
