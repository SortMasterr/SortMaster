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


class DetectionSchemaTest(unittest.TestCase):
    def testMisclassificationRemainsBackwardCompatible(self):
        detectionStop = DetectionStop(
            recordingId="recording-1",
            cameraId=CameraId.ELEVTOP,
            detectionId="detection-1",
            trackingId=7,
            detectedClass=DetectedClass.PLASTIC,
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
            ),
            patch(
                "services.detectionService.mediaService.saveClipAsGif",
                AsyncMock(return_value="gridfs-file-id"),
            ),
            patch(
                "services.detectionService.eventService.createEvent",
                AsyncMock(return_value=savedEvent),
            ) as createEvent,
        ):
            result = await service.stopDetection(
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
        self.assertIs(result, savedEvent)
        self.assertEqual(eventCreate.eventCategory, EventCategory.OVERFLOW)
        self.assertEqual(eventCreate.imageFileId, "gridfs-file-id")
        self.assertEqual(eventCreate.overflowDuration, 5.2)
        self.assertEqual(eventCreate.overflowThreshold, 5.0)


if __name__ == "__main__":
    unittest.main()
