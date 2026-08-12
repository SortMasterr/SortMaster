import asyncio
import io
from datetime import datetime

import cv2
from PIL import Image

from repositories.mediaRepository import (
    MediaRepository,
    mediaRepository,
)
from schemas.event import CameraId


def _encodeFramesAsGif(
    frames: list,
    fps: float,
) -> bytes:
    if not frames:
        raise ValueError(
            "GIF로 인코딩할 프레임이 없습니다."
        )

    images = [
        Image.fromarray(
            cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        )
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
        gifBytes = await asyncio.to_thread(
            _encodeFramesAsGif, frames, fps
        )

        filename = (
            f"{cameraId.value}-"
            f"{timestamp.strftime('%Y%m%dT%H%M%S')}.gif"
        )

        return await self.repository.saveBytes(
            filename, gifBytes
        )


mediaService = MediaService(mediaRepository)
