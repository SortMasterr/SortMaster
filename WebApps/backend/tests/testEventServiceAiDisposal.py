import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, patch

from schemas.aiDisposalEvent import AiDisposalEvent
from schemas.event import CameraId, DetectedClass
from schemas.visitClip import VisitClip
from services.eventService import EventService


class MemoryEventRepository:
    def __init__(self):
        self.events = []

    async def findByDetectionId(self, detectionId):
        return next(
            (
                event
                for event in self.events
                if event.detectionId == detectionId
            ),
            None,
        )

    async def save(self, event):
        self.events.append(event)
        return event

    async def updateImageFileId(self, eventId, imageFileId):
        self.events = [
            event.model_copy(
                update={"imageFileId": imageFileId}
            )
            if event.eventId == eventId
            else event
            for event in self.events
        ]


def buildAiEvent(**overrides):
    payload = {
        "eventId": "event-1",
        "trackId": 15,
        "timestamp": "2026-08-23T16:12:00+09:00",
        "cameraId": "CAM-01",
        "detectedClass": "recyclables",
        "binId": "recyclables",
        "result": "incorrect",
        "imagePath": "waste_events/event-1.jpg",
    }
    payload.update(overrides)
    return AiDisposalEvent(**payload)


class EventServiceAiDisposalTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.repository = MemoryEventRepository()
        self.service = EventService(self.repository)
        self.registerResolution = patch(
            "services.eventService.visitClipService.registerAiDisposalResolution",
            AsyncMock(return_value=None),
        ).start()
        self.registerTrackEnded = patch(
            "services.eventService.visitClipService.registerTrackEnded",
            AsyncMock(return_value=None),
        ).start()
        self.addCleanup(patch.stopall)

    async def testIncorrectResultCreatesMisclassificationEvent(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent()
        )

        self.assertTrue(result.created)
        self.assertEqual(
            CameraId.ELEVTOP, result.event.cameraId
        )
        self.assertEqual(
            DetectedClass.RECYCLABLES,
            result.event.detectedClass,
        )
        self.assertTrue(result.event.isMisclassified)
        self.assertEqual(15, result.event.trackingId)
        self.assertEqual(
            "event-1", result.event.detectionId
        )

    async def testIncorrectResultWaitsForStoredVisitClip(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent()
        )

        self.assertIsNone(result.event.imageFileId)
        self.registerResolution.assert_awaited_once()

    async def testLateIncorrectResultUsesStoredVisitClip(self):
        startedAt = datetime(2026, 8, 23, 7, 11, 50, tzinfo=timezone.utc)
        visitClip = VisitClip(
            cameraId=CameraId.ELEVTOP,
            startedAt=startedAt,
            endedAt=startedAt + timedelta(seconds=30),
            imageFileId="507f1f77bcf86cd799439010",
            trackIds=[15],
        )
        self.registerResolution.return_value = visitClip

        async def attachPreview(event, _visitClip, _timestamp):
            return event.model_copy(
                update={
                    "imageFileId": "507f1f77bcf86cd799439011"
                }
            )

        with patch(
            "services.eventService.eventMediaService.attachPreviewFromVisitClip",
            AsyncMock(side_effect=attachPreview),
        ) as attach:
            result = await self.service.createEventFromAiDisposal(
                buildAiEvent()
            )

        attach.assert_awaited_once()
        self.assertEqual(
            "507f1f77bcf86cd799439011",
            result.event.imageFileId,
        )

    async def testCorrectResultCreatesNoEvent(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent(result="correct")
        )

        self.assertFalse(result.created)
        self.assertIsNone(result.event)
        self.assertEqual(0, len(self.repository.events))

    async def testUnknownResultIsIgnored(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent(result="unknown")
        )

        self.assertFalse(result.created)
        self.assertIsNone(result.event)
        self.assertEqual(0, len(self.repository.events))

    async def testUnmappedDetectedClassIsIgnored(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent(detectedClass="unexpected-class")
        )

        self.assertFalse(result.created)
        self.assertIsNone(result.event)

    async def testUnmappedCameraIdIsIgnored(self):
        result = await self.service.createEventFromAiDisposal(
            buildAiEvent(cameraId="CAM-99")
        )

        self.assertFalse(result.created)
        self.assertIsNone(result.event)

    async def testSameEventIdIsIdempotent(self):
        first = await self.service.createEventFromAiDisposal(
            buildAiEvent()
        )
        second = await self.service.createEventFromAiDisposal(
            buildAiEvent()
        )

        self.assertTrue(first.created)
        self.assertFalse(second.created)
        self.assertEqual(
            first.event.eventId, second.event.eventId
        )
        self.assertEqual(1, len(self.repository.events))


if __name__ == "__main__":
    unittest.main()
