        watermark=watermark_path,
        show_waveform=data.show_waveform,
        visualizer_style=data.visualizer_style,
        resolution=data.resolution,
        fps=data.fps,
        aspect_ratio=data.aspect_ratio,
        duration=data.duration,
        output_format=data.output_format,
    )
    return FileResponse(path=output_path, media_type=f"video/{data.output_format}", filename=output_filename)


@router.post("/{media_id}/sync-audio")
async def sync_audio_video_endpoint(
    media_id: UUID,
    data: AudioVideoSyncRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Media).where(Media.id == media_id, Media.user_id == current_user.id))
    media = result.scalar_one_or_none()
    if media is None:
        raise HTTPException(status_code=404, detail="Media not found")

    if media.media_type != "video":
        raise HTTPException(status_code=400, detail="Media must be a video file")

    input_path = get_uploaded_file(media.stored_filename)
    audio_file = get_uploaded_file(data.audio_path)
    output_filename = f"{media_id}_synced_{uuid4().hex[:8]}.{data.output_format}"
    output_path = get_uploaded_file(output_filename)

    await asyncio.to_thread(
        sync_audio_video,
        str(input_path),
        str(audio_file),
        str(output_path),
        audio_offset=data.audio_offset,
        video_duration=data.video_duration,
        audio_duration=data.audio_duration,
        fade_in=data.fade_in,
        fade_out=data.fade_out,
        volume=data.volume,
        mix=data.mix,
        mix_volume=data.mix_volume,
    )

    media.processed_filename = output_filename
    media.processing_status = "completed"
    media.processing_error = None
    await db.commit()

    return {
        "output_filename": output_filename,
        "operation": "sync_audio",
        "media_id": str(media_id),
    }