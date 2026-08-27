import io
import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

from PIL import Image

from schemas.event import (
    ActionTaken,
    BinType,
    CameraId,
    DetectedClass,
    Event,
    EventCategory,
)
from schemas.visitClip import VisitClip
from services.eventMediaService import EventMediaService
from services.mediaService import _extractGifSegment


class MemoryEventRepository:
    def __init__(self, updated=True):
        self.updated = updated
        self.calls = []

    async def updateImageFileIdIfMissing(self, eventId, imageFileId):
        self.calls.append((eventId, imageFileId))
        return self.updated


def buildEvent(timestamp):
    return Event(
        eventId="event-1",
        timestamp=timestamp,
        cameraId=CameraId.ELEVTOP,
        eventCategory=EventCategory.MISCLASSIFICATION,
        detectionId="detection-1",
        trackingId=15,
        detectedClass=DetectedClass.NORMAL,
        binId="BIN-PAPER",
        binType=BinType.PAPER,
        isMisclassified=True,
        confidenceScore=0.9,
        actionTaken=ActionTaken.LIGHT_AND_SOUND,
        modelVersion="test",
    )


class EventMediaServiceTest(unittest.IsolatedAsyncioTestCase):
    async def testStoredVisitClipCreatesPreviousFiveSecondPreview(self):
        startedAt = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
        event = buildEvent(startedAt + timedelta(seconds=12))
        visitClip = VisitClip(
            cameraId=CameraId.ELEVTOP,
            startedAt=startedAt,
            endedAt=startedAt + timedelta(seconds=20),
            imageFileId="source-file",
        )
        repository = MemoryEventRepository()
        mediaService = AsyncMock()
        mediaService.saveStoredClipSegmentAsGif.return_value = "preview-file"
        service = EventMediaService(repository, mediaService)

        updated = await service.attachPreviewFromVisitClip(
            event,
            visitClip,
        )

        mediaService.saveStoredClipSegmentAsGif.assert_awaited_once_with(
            "source-file",
            CameraId.ELEVTOP,
            event.timestamp,
            7.0,
            12.0,
        )
        self.assertEqual("preview-file", updated.imageFileId)

    async def testUnusedDerivedPreviewIsDeleted(self):
        startedAt = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
        event = buildEvent(startedAt + timedelta(seconds=3))
        visitClip = VisitClip(
            cameraId=CameraId.ELEVTOP,
            startedAt=startedAt,
            endedAt=startedAt + timedelta(seconds=20),
            imageFileId="source-file",
        )
        repository = MemoryEventRepository(updated=False)
        mediaService = AsyncMock()
        mediaService.saveStoredClipSegmentAsGif.return_value = "preview-file"
        service = EventMediaService(repository, mediaService)

        updated = await service.attachPreviewFromVisitClip(
            event,
            visitClip,
        )

        mediaService.deleteClip.assert_awaited_once_with(
            "preview-file",
            CameraId.ELEVTOP,
        )
        self.assertIsNone(updated.imageFileId)

    def testGifSegmentKeepsOnlyRequestedTimeRange(self):
        frames = [
            Image.new("RGB", (8, 8), (index * 20, 0, 0))
            for index in range(10)
        ]
        source = io.BytesIO()
        frames[0].save(
            source,
            format="GIF",
            save_all=True,
            append_images=frames[1:],
            duration=200,
            loop=0,
            optimize=False,
        )

        segment = _extractGifSegment(
            source.getvalue(),
            0.6,
            1.6,
        )

        with Image.open(io.BytesIO(segment)) as result:
            self.assertEqual(5, result.n_frames)


if __name__ == "__main__":
    unittest.main()
