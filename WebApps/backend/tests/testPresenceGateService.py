import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, Mock, patch

from schemas.event import CameraId, EventCategory
from schemas.visitClip import VisitClip
from services.errors import (
    CameraUnavailableError,
    RecordingNotFoundError,
)
from services.presenceGateService import (
    PresenceGateService,
    PresenceState,
)


def gateService(cameraManager=None):
    cameraManagers = {
        CameraId.ELEVTOP.value: cameraManager or AsyncMock(),
    }
    return PresenceGateService(CameraId.ELEVTOP, cameraManagers)


class PresenceGateServiceTest(unittest.IsolatedAsyncioTestCase):
    async def testBackgroundHistoryScalesWithPollInterval(self):
        with patch(
            "services.presenceGateService.pollIntervalSeconds",
            0.2,
        ):
            service = gateService()

        # 20초(backgroundHistorySeconds) / 0.2초 폴링 = 100프레임 안에 배경 모델이
        # 수렴해야 함 — cv2 기본값(500)을 그대로 쓰면 실제로 100초가 걸려 실기기에서
        # 재시작 직후 오탐이 재현됐던 문제(폴링 주기 미반영)를 회귀 방지
        self.assertEqual(
            100,
            service.presenceDetector._backgroundSubtractor.getHistory(),
        )

    async def testSingleTickAboveThresholdStaysAbsent(self):
        service = gateService()

        with patch(
            "services.presenceGateService.entryConfirmSeconds",
            1.0,
        ):
            await service._handleRatio(ratio=0.5, now=0.0)

        self.assertEqual(PresenceState.ABSENT, service.state)
        self.assertIsNone(service.recordingId)

    async def testSustainedAboveThresholdEntersPresent(self):
        service = gateService()

        with (
            patch(
                "services.presenceGateService.entryConfirmSeconds",
                1.0,
            ),
            patch(
                "services.presenceGateService.detectionService"
            ) as detectionService,
        ):
            detectionService.startDetection = AsyncMock(
                return_value="recording-1"
            )

            await service._handleRatio(ratio=0.5, now=0.0)
            await service._handleRatio(ratio=0.5, now=1.0)

        self.assertEqual(PresenceState.PRESENT, service.state)
        self.assertEqual("recording-1", service.recordingId)
        detectionService.startDetection.assert_awaited_once_with(
            CameraId.ELEVTOP
        )

    async def testBriefDropWhilePresentDoesNotExit(self):
        service = gateService()
        service.state = PresenceState.PRESENT
        service.recordingId = "recording-1"

        with patch(
            "services.presenceGateService.exitGraceSeconds",
            1.0,
        ):
            await service._handleRatio(ratio=0.0, now=0.0)
            await service._handleRatio(ratio=0.5, now=0.1)

        self.assertEqual(PresenceState.PRESENT, service.state)
        self.assertEqual("recording-1", service.recordingId)
        self.assertIsNone(service.belowThresholdSince)

    async def testSustainedBelowThresholdExitsAndStopsRecording(self):
        service = gateService()
        service.state = PresenceState.PRESENT
        service.recordingId = "recording-1"

        with (
            patch(
                "services.presenceGateService.exitGraceSeconds",
                1.0,
            ),
            patch(
                "services.presenceGateService.recordingService"
            ) as recordingService,
        ):
            recordingService.stop = AsyncMock(
                return_value=([], 2.5)
            )

            await service._handleRatio(ratio=0.0, now=0.0)
            await service._handleRatio(ratio=0.0, now=1.0)

        self.assertEqual(PresenceState.ABSENT, service.state)
        self.assertIsNone(service.recordingId)
        recordingService.stop.assert_awaited_once_with(
            "recording-1",
            expectedCameraId=CameraId.ELEVTOP,
        )

    async def testCameraUnavailableDuringEnterKeepsAbsent(self):
        service = gateService()

        with patch(
            "services.presenceGateService.detectionService"
        ) as detectionService:
            detectionService.startDetection = AsyncMock(
                side_effect=CameraUnavailableError("no camera")
            )

            await service._enterPresent()

        self.assertEqual(PresenceState.ABSENT, service.state)
        self.assertIsNone(service.recordingId)

    async def testRecordingNotFoundDuringExitIsSwallowed(self):
        service = gateService()
        service.state = PresenceState.PRESENT
        service.recordingId = "recording-1"

        with patch(
            "services.presenceGateService.recordingService"
        ) as recordingService:
            recordingService.stop = AsyncMock(
                side_effect=RecordingNotFoundError("gone")
            )

            await service._exitToAbsent()

        self.assertEqual(PresenceState.ABSENT, service.state)
        self.assertIsNone(service.recordingId)

    async def testShutdownStopsInFlightRecording(self):
        service = gateService()
        service.recordingId = "recording-1"

        with patch(
            "services.presenceGateService.recordingService"
        ) as recordingService:
            recordingService.stop = AsyncMock(
                return_value=([], 4.0)
            )

            await service.shutdown()

        recordingService.stop.assert_awaited_once_with(
            "recording-1",
            expectedCameraId=CameraId.ELEVTOP,
        )
        self.assertIsNone(service.recordingId)

    async def testHandleNoFrameRetriesAreThrottled(self):
        cameraManager = AsyncMock()
        service = gateService(cameraManager)

        with patch(
            "services.presenceGateService."
            "cameraStartRetryIntervalSeconds",
            5.0,
        ):
            await service._handleNoFrame(now=0.0)
            await service._handleNoFrame(now=1.0)
            await service._handleNoFrame(now=6.0)

        self.assertEqual(2, cameraManager.start.await_count)

    async def testSavedVisitClipAttachesDatabasePreviewToEvent(self):
        service = gateService()
        event = Mock(
            eventId="event-1",
            cameraId=CameraId.ELEVTOP,
            eventCategory=EventCategory.MISCLASSIFICATION,
            isMisclassified=True,
        )
        endedAt = datetime.now(timezone.utc)
        visitClip = VisitClip(
            cameraId=CameraId.ELEVTOP,
            startedAt=endedAt - timedelta(seconds=8),
            endedAt=endedAt,
            imageFileId="visit-file",
            matchedEventIds=["event-1"],
        )

        with (
            patch(
                "services.presenceGateService.mediaService"
            ) as mediaService,
            patch(
                "services.presenceGateService.eventRepository"
            ) as eventRepository,
            patch(
                "services.presenceGateService.visitClipService"
            ) as visitClipService,
            patch(
                "services.presenceGateService.eventMediaService"
            ) as eventMediaService,
        ):
            mediaService.saveClipAsGif = AsyncMock(
                return_value="visit-file"
            )
            eventRepository.findAll = AsyncMock(
                return_value=[event]
            )
            visitClipService.createClipForVisit = AsyncMock(
                return_value=visitClip
            )
            eventMediaService.attachPreviewFromVisitClip = (
                AsyncMock()
            )

            await service._saveVisitClip([object()], 8.0)

        visitClipService.createClipForVisit.assert_awaited_once()
        self.assertEqual(
            ["event-1"],
            visitClipService.createClipForVisit.await_args.args[4],
        )
        eventMediaService.attachPreviewFromVisitClip.assert_awaited_once_with(
            event,
            visitClip,
        )


if __name__ == "__main__":
    unittest.main()
