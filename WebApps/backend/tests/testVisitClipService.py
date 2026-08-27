import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from schemas.event import CameraId
from schemas.visitClip import VisitClip
from services.visitClipService import VisitClipService


def buildVisitClip(startedAt):
    return VisitClip(
        cameraId=CameraId.ELEVTOP,
        startedAt=startedAt,
        endedAt=startedAt + timedelta(seconds=10),
        imageFileId="visit-file",
    )


class VisitClipServiceTest(unittest.IsolatedAsyncioTestCase):
    async def testLateEventFallsBackToCameraAndTimestamp(self):
        service = VisitClipService()
        timestamp = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
        clip = buildVisitClip(timestamp - timedelta(seconds=5))

        with patch(
            "services.visitClipService.visitClipRepository"
        ) as repository:
            repository.addMatchedEvent = AsyncMock(return_value=None)
            repository.addMatchedEventByTimestamp = AsyncMock(
                return_value=clip
            )

            result = await service.registerAiDisposalResolution(
                15,
                "event-1",
                CameraId.ELEVTOP,
                timestamp,
            )

        self.assertIs(clip, result)
        repository.addMatchedEventByTimestamp.assert_awaited_once_with(
            CameraId.ELEVTOP,
            timestamp,
            "event-1",
            5.0,
        )

    async def testStoredVisitContainsTrackAndMatchedEvents(self):
        service = VisitClipService()
        startedAt = datetime(2026, 8, 27, 1, 0, tzinfo=timezone.utc)
        endedAt = startedAt + timedelta(seconds=10)
        service.recordTrackStarted(
            15,
            CameraId.ELEVTOP,
            startedAt + timedelta(seconds=1),
        )
        await service.registerAiDisposalResolution(
            15,
            "event-track",
            CameraId.ELEVTOP,
            startedAt + timedelta(seconds=5),
        )

        with patch(
            "services.visitClipService.visitClipRepository"
        ) as repository:
            repository.save = AsyncMock()
            clip = await service.createClipForVisit(
                CameraId.ELEVTOP,
                startedAt,
                endedAt,
                "visit-file",
                ["event-time", "event-track"],
            )

        self.assertEqual([15], clip.trackIds)
        self.assertEqual(
            ["event-track", "event-time"],
            clip.matchedEventIds,
        )
        self.assertEqual([], clip.unresolvedTrackIds)
        repository.save.assert_awaited_once_with(clip)


if __name__ == "__main__":
    unittest.main()
