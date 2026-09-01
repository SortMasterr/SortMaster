import asyncio
import io
from datetime import datetime

from PIL import Image

from repositories.mediaRepository import (
    MediaRepository,
    mediaRepository,
)
from schemas.event import CameraId
from services.errors import EmptyRecordingError


def _encodeFramesAsGif(
    frames: list,
    fps: float,
) -> bytes:
    if not frames:
        raise ValueError(
            "GIF로 인코딩할 프레임이 없습니다."
        )

    images = [
        Image.open(io.BytesIO(frame)).convert("RGB")
        for frame in frames
    ]

    durationMs = int(1000 / fps) if fps > 0 else 200

    buffer = io.BytesIO()
    images[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=images[1:],
        duration=durationMs,
        loop=0,
    )

    return buffer.getvalue()


def _extractGifSegment(
    gifBytes: bytes,
    startSeconds: float,
    endSeconds: float,
) -> bytes:
    startMs = max(0, round(startSeconds * 1000))
    endMs = max(startMs + 1, round(endSeconds * 1000))
    selectedImages = []
    selectedDurations = []
    elapsedMs = 0

    with Image.open(io.BytesIO(gifBytes)) as source:
        defaultDurationMs = source.info.get("duration", 200)

        for frameIndex in range(source.n_frames):
            source.seek(frameIndex)
            durationMs = source.info.get(
                "duration",
                defaultDurationMs,
            )
            frameEndMs = elapsedMs + durationMs

            if frameEndMs > startMs and elapsedMs < endMs:
                selectedImages.append(
                    source.convert("RGB").copy()
                )
                selectedDurations.append(durationMs)

            elapsedMs = frameEndMs

            if elapsedMs >= endMs:
                break

        if not selectedImages:
            source.seek(max(0, source.n_frames - 1))
            selectedImages.append(
                source.convert("RGB").copy()
            )
            selectedDurations.append(defaultDurationMs)

    buffer = io.BytesIO()
    selectedImages[0].save(
        buffer,
        format="GIF",
        save_all=True,
        append_images=selectedImages[1:],
        duration=selectedDurations,
        loop=0,
    )

    return buffer.getvalue()


class MediaService:
    def __init__(
        self,
        repository: MediaRepository,
    ):
        self.repository = repository

    async def saveClipAsGif(
        self,
        frames: list,
        cameraId: CameraId,
        timestamp: datetime,
        fps: float = 5.0,
    ) -> str:
        if not frames:
            raise EmptyRecordingError(
                "GIF로 인코딩할 프레임이 없습니다."
            )

        gifBytes = await asyncio.to_thread(
            _encodeFramesAsGif, frames, fps
        )

        filename = (
            f"{cameraId.value}-"
            f"{timestamp.strftime('%Y%m%dT%H%M%S')}.gif"
        )

        return await self.repository.saveBytes(
            filename,
            gifBytes,
            cameraId,
        )

    async def deleteClip(
        self,
        fileId: str,
        cameraId: CameraId,
    ) -> None:
        await self.repository.deleteById(
            fileId,
            cameraId,
        )

    async def getClip(
        self,
        fileId: str,
        cameraId: CameraId,
    ) -> bytes | None:
        return await self.repository.getBytesById(
            fileId,
            cameraId,
        )

    async def saveStoredClipSegmentAsGif(
        self,
        sourceFileId: str,
        cameraId: CameraId,
        timestamp: datetime,
        startSeconds: float,
        endSeconds: float,
    ) -> str | None:
        sourceBytes = await self.getClip(
            sourceFileId,
            cameraId,
        )

        if sourceBytes is None:
            return None

        gifBytes = await asyncio.to_thread(
            _extractGifSegment,
            sourceBytes,
            startSeconds,
            endSeconds,
        )
        filename = (
            f"{cameraId.value}-"
            f"{timestamp.strftime('%Y%m%dT%H%M%S')}-preview.gif"
        )

        return await self.repository.saveBytes(
            filename,
            gifBytes,
            cameraId,
        )


mediaService = MediaService(mediaRepository)
