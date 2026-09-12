from app.features.comparisons.schemas import MediaComparisonResponse


def compare_media(media_a, media_b) -> dict:
    size_diff = media_a.file_size - media_b.file_size
    duration_diff = (media_a.duration or 0) - (media_b.duration or 0)
    resolution_match = (media_a.width == media_b.width and media_a.height == media_b.height)
    video_codec_match = media_a.video_codec == media_b.video_codec
    audio_codec_match = media_a.audio_codec == media_b.audio_codec
    storage_saved = max(0, size_diff)
    return {
        "media_a_id": str(media_a.id),
        "media_b_id": str(media_b.id),
        "size_diff": size_diff,
        "duration_diff": duration_diff,
        "resolution_match": resolution_match,
        "video_codec_match": video_codec_match,
        "audio_codec_match": audio_codec_match,
        "storage_saved": storage_saved,
    }
