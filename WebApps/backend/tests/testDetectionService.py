import unittest
from unittest.mock import AsyncMock, patch

from pydantic import ValidationError

from schemas.detection import DetectionStop
from schemas.event import (
    BinType,
    CameraId,
    DetectedClass,
    EventCategory,
)
from services.detectionService import DetectionService
from services.eventService import EventCreationResult
from services.errors import RecordingConflictError


class DetectionSchemaTest(unittest.TestCase):
    def testMisclassificationRemainsBackwardCompatible(self):
        detectionStop = DetectionStop(
            recordingId="recording-1",
            cameraId=CameraId.ELEVTOP,
            detectionId="detection-1",
            trackingId=7,
            detectedClass=DetectedClass.PLASTIC_CAN,
            binId="BIN-PAPER",
            binType=BinType.PAPER,
            isMisclassified=True,
            confidenceScore=0.91,
            modelVersion="yolo26-mvp-1",
        )

        self.assertEqual(
            detectionStop.eventCategory,
            EventCategory.MISCLASSIFICATION,
        )

    def testOverflowAcceptsOnlySideCameraFields(self):
        detectionStop = DetectionStop(
            recordingId="recording-2",
            cameraId=CameraId.ELEVSIDE,
            eventCategory=EventCategory.OVERFLOW,
            detectionId="overflow-1",
            binId="BIN-GENERAL",
            binType=BinType.GENERAL,
            overflowDuration=5.2,
            overflowThreshold=5.0,
            modelVersion="overflow-mvp-1",
        )

        self.assertIsNone(detectionStop.detectedClass)
        self.assertEqual(detectionStop.overflowDuration, 5.2)

    def testOverflowRejectsMisclassificationFields(self):
        with self.assertRaises(ValidationError):
            DetectionStop(
                recordingId="recording-3",
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.OVERFLOW,
                detectionId="overflow-2",
                detectedClass=DetectedClass.GENERAL,
                binId="BIN-GENERAL",
                binType=BinType.GENERAL,
                isMisclassified=False,
                confidenceScore=0.8,
                modelVersion="overflow-mvp-1",
            )


class DetectionServiceTest(unittest.IsolatedAsyncioTestCase):
    async def testOverflowUsesRecordingMediaAndEventPipeline(self):
        service = DetectionService()
        frames = [object()]
        savedEvent = object()

        with (
            patch(
                "services.detectionService.recordingService.stop",
                AsyncMock(return_value=(frames, 5.2)),
            ) as stopRecording,
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="gridfs-file-id"),
            ),
            patch(
                "services.detectionService.eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=savedEvent,
                        created=True,
                    )
                ),
            ) as createEvent,
        ):
            result = await service.stopDetectionWithStatus(
                recordingId="recording-2",
                cameraId=CameraId.ELEVSIDE,
                eventCategory=EventCategory.OVERFLOW,
                detectionId="overflow-1",
                trackingId=None,
                detectedClass=None,
                binId="BIN-GENERAL",
                binType=BinType.GENERAL,
                isMisclassified=None,
                confidenceScore=None,
                overflowDuration=5.2,
                overflowThreshold=5.0,
                modelVersion="overflow-mvp-1",
            )

        eventCreate = createEvent.await_args.args[0]
        stopRecording.assert_awaited_once_with(
            "recording-2",
            expectedCameraId=CameraId.ELEVSIDE,
        )
        self.assertIs(result.event, savedEvent)
        self.assertTrue(result.created)
        self.assertEqual(eventCreate.eventCategory, EventCategory.OVERFLOW)
        self.assertEqual(eventCreate.imageFileId, "gridfs-file-id")
        self.assertEqual(eventCreate.overflowDuration, 5.2)
        self.assertEqual(eventCreate.overflowThreshold, 5.0)

    async def testSuppressedEventDeletesUploadedClip(self):
        service = DetectionService()

        with (
            patch(
                "services.detectionService.recordingService.stop",
                AsyncMock(return_value=([object()], 1.0)),
            ),
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="unused-gridfs-id"),
            ),
            patch(
                "services.detectionService.mediaService.deleteClip",
                AsyncMock(),
            ) as deleteClip,
            patch(
                "services.detectionService.eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=None,
                        created=False,
                    )
                ),
            ),
        ):
            result = await service.stopDetectionWithStatus(
                recordingId="recording-suppressed",
                cameraId=CameraId.ELEVTOP,
                eventCategory=EventCategory.MISCLASSIFICATION,
                detectionId="detection-suppressed",
                trackingId=3,
                detectedClass=DetectedClass.PAPER,
                binId="BIN-PAPER",
                binType=BinType.PAPER,
                isMisclassified=False,
                confidenceScore=0.88,
                overflowDuration=None,
                overflowThreshold=None,
                modelVersion="test-v1",
            )

        self.assertFalse(result.created)
        self.assertIsNone(result.event)
        deleteClip.assert_awaited_once_with(
            "unused-gridfs-id",
            CameraId.ELEVTOP,
        )

    async def testStopRetryUsesCachedResultAndRejectsNewDetectionId(
        self
    ):
        service = DetectionService()
        savedEvent = object()
        stopArguments = {
            "recordingId": "recording-idempotent",
            "cameraId": CameraId.ELEVTOP,
            "eventCategory": EventCategory.MISCLASSIFICATION,
            "detectionId": "detection-idempotent",
            "trackingId": 11,
            "detectedClass": DetectedClass.PLASTIC_CAN,
            "binId": "BIN-PAPER",
            "binType": BinType.PAPER,
            "isMisclassified": True,
            "confidenceScore": 0.94,
            "overflowDuration": None,
            "overflowThreshold": None,
            "modelVersion": "test-v1",
        }

        with (
            patch(
                "services.detectionService.recordingService.stop",
                AsyncMock(return_value=([object()], 1.0)),
            ) as stopRecording,
            patch(
                "services.detectionService."
                "recordingService.releaseStopped",
                AsyncMock(),
            ) as releaseStopped,
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="cached-gridfs-id"),
            ) as saveClip,
            patch(
                "services.detectionService."
                "eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=savedEvent,
                        created=True,
                    )
                ),
            ) as createEvent,
        ):
            firstResult = await service.stopDetectionWithStatus(
                **stopArguments
            )
            retryResult = await service.stopDetectionWithStatus(
                **stopArguments
            )

            conflictingArguments = {
                **stopArguments,
                "detectionId": "different-detection",
            }

            with self.assertRaises(RecordingConflictError):
                await service.stopDetectionWithStatus(
                    **conflictingArguments
                )

        self.assertIs(firstResult.event, retryResult.event)
        self.assertTrue(firstResult.created)
        self.assertFalse(retryResult.created)
        stopRecording.assert_awaited_once()
        saveClip.assert_awaited_once()
        createEvent.assert_awaited_once()
        releaseStopped.assert_awaited_once_with(
            "recording-idempotent"
        )

    async def testEventSaveFailureDeletesUploadedClip(self):
        service = DetectionService()

        with (
            patch(
                "services.detectionService.recordingService.stop",
                AsyncMock(return_value=([object()], 1.0)),
            ),
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="failed-gridfs-id"),
            ),
            patch(
                "services.detectionService.mediaService.deleteClip",
                AsyncMock(),
            ) as deleteClip,
            patch(
                "services.detectionService.eventService.createEventWithStatus",
                AsyncMock(side_effect=RuntimeError("database failed")),
            ),
        ):
            with self.assertRaises(RuntimeError):
                await service.stopDetectionWithStatus(
                    recordingId="recording-failed",
                    cameraId=CameraId.ELEVTOP,
                    eventCategory=EventCategory.MISCLASSIFICATION,
                    detectionId="detection-failed",
                    trackingId=4,
                    detectedClass=DetectedClass.PLASTIC_CAN,
                    binId="BIN-PAPER",
                    binType=BinType.PAPER,
                    isMisclassified=True,
                    confidenceScore=0.91,
                    overflowDuration=None,
                    overflowThreshold=None,
                    modelVersion="test-v1",
                )

        deleteClip.assert_awaited_once_with(
            "failed-gridfs-id",
            CameraId.ELEVTOP,
        )

    async def testSuppressedEventIgnoresCompensationDeleteFailure(self):
        service = DetectionService()
        existingEvent = object()

        with (
            patch(
                "services.detectionService.recordingService.stop",
                AsyncMock(return_value=([object()], 1.0)),
            ),
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="orphan-gridfs-id"),
            ),
            patch(
                "services.detectionService.mediaService.deleteClip",
                AsyncMock(side_effect=RuntimeError("gridfs unavailable")),
            ) as deleteClip,
            patch(
                "services.detectionService.eventService.createEventWithStatus",
                AsyncMock(
                    return_value=EventCreationResult(
                        event=existingEvent,
                        created=False,
                    )
                ),
            ),
        ):
            result = await service.stopDetectionWithStatus(
                recordingId="recording-duplicate",
                cameraId=CameraId.ELEVTOP,
                eventCategory=EventCategory.MISCLASSIFICATION,
                detectionId="detection-duplicate",
                trackingId=5,
                detectedClass=DetectedClass.PLASTIC_CAN,
                binId="BIN-PAPER",
                binType=BinType.PAPER,
                isMisclassified=True,
                confidenceScore=0.9,
                overflowDuration=None,
                overflowThreshold=None,
                modelVersion="test-v1",
            )

        self.assertIs(result.event, existingEvent)
        self.assertFalse(result.created)
        deleteClip.assert_awaited_once_with(
            "orphan-gridfs-id",
            CameraId.ELEVTOP,
        )


if __name__ == "__main__":
    unittest.main()
