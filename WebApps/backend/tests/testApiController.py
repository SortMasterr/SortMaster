import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from controllers import api
from fastapi import HTTPException
from schemas.detection import DetectionStop
from schemas.detection import DetectionStart
from schemas.event import (
    ActionTaken,
    BinType,
    CameraId,
    DetectedClass,
    Event,
    EventCategory,
    EventCreate,
)
from services.eventService import EventCreationResult
from services.errors import (
    CameraUnavailableError,
    RecordingCameraMismatchError,
    RecordingNotFoundError,
)


def eventCreate():
    return EventCreate(
        cameraId=CameraId.ELEVTOP,
        eventCategory=EventCategory.MISCLASSIFICATION,
        detectionId="controller-detection",
        trackingId=8,
        detectedClass=DetectedClass.PLASTIC_CAN,
        binId="BIN-PAPER",
        binType=BinType.PAPER,
        isMisclassified=True,
        confidenceScore=0.92,
        modelVersion="controller-test-v1",
    )


def savedEvent():
    request = eventCreate()
    return Event(
        **request.model_dump(),
        eventId="controller-event",
        timestamp=datetime.now(timezone.utc),
        actionTaken=ActionTaken.LIGHT_AND_SOUND,
    )


def detectionStop():
    return DetectionStop(
        recordingId="controller-recording",
        **eventCreate().model_dump(
            exclude={"imageFileId"}
        ),
    )


class ApiControllerBroadcastTest(
    unittest.IsolatedAsyncioTestCase
):
    async def testDuplicateResponseDoesNotBroadcastAgain(self):
        event = savedEvent()

        with (
            patch(
                "controllers.api.eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=event,
                        created=False,
                    )
                ),
            ),
            patch(
                "controllers.api._broadcastIfManageMode",
                AsyncMock(),
            ) as broadcast,
        ):
            response = await api.createEvent(eventCreate())

        self.assertIs(response, event)
        broadcast.assert_not_awaited()

    async def testNewEventBroadcastsOnce(self):
        event = savedEvent()

        with (
            patch(
                "controllers.api.eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=event,
                        created=True,
                    )
                ),
            ),
            patch(
                "controllers.api._broadcastIfManageMode",
                AsyncMock(),
            ) as broadcast,
        ):
            response = await api.createEvent(eventCreate())

        self.assertIs(response, event)
        broadcast.assert_awaited_once_with(event)

    async def testDuplicateStopResponseDoesNotBroadcastAgain(self):
        event = savedEvent()

        with (
            patch(
                "controllers.api.detectionService.stopDetectionWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=event,
                        created=False,
                    )
                ),
            ),
            patch(
                "controllers.api._broadcastIfManageMode",
                AsyncMock(),
            ) as broadcast,
        ):
            response = await api.stopDetection(detectionStop())

        self.assertIs(response, event)
        broadcast.assert_not_awaited()

    async def testStopCameraMismatchReturnsHttp400(self):
        with patch(
            "controllers.api.detectionService.stopDetectionWithStatus",
            AsyncMock(
                side_effect=RecordingCameraMismatchError(
                    "camera mismatch"
                )
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                await api.stopDetection(detectionStop())

        self.assertEqual(400, context.exception.status_code)

    async def testStopNotFoundReturnsHttp404(self):
        with patch(
            "controllers.api.detectionService.stopDetectionWithStatus",
            AsyncMock(
                side_effect=RecordingNotFoundError(
                    "recording missing"
                )
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                await api.stopDetection(detectionStop())

        self.assertEqual(404, context.exception.status_code)

    async def testUnexpectedValueErrorIsNotMisreportedAsHttp400(self):
        with patch(
            "controllers.api.detectionService.stopDetectionWithStatus",
            AsyncMock(
                side_effect=ValueError("internal conversion bug")
            ),
        ):
            with self.assertRaisesRegex(
                ValueError,
                "internal conversion bug",
            ):
                await api.stopDetection(detectionStop())

    async def testExpectedCameraFailureReturnsHttp503(self):
        request = DetectionStart(cameraId=CameraId.ELEVTOP)

        with patch(
            "controllers.api.detectionService.startDetection",
            AsyncMock(
                side_effect=CameraUnavailableError(
                    "camera unavailable"
                )
            ),
        ):
            with self.assertRaises(HTTPException) as context:
                await api.startDetection(request)

        self.assertEqual(503, context.exception.status_code)

    async def testUnexpectedRuntimeErrorIsNotMisreportedAsHttp503(self):
        request = DetectionStart(cameraId=CameraId.ELEVTOP)

        with patch(
            "controllers.api.detectionService.startDetection",
            AsyncMock(
                side_effect=RuntimeError("internal start bug")
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "internal start bug",
            ):
                await api.startDetection(request)


if __name__ == "__main__":
    unittest.main()
