import unittest
from unittest.mock import AsyncMock, patch

from schemas.event import CameraId
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
            patch.object(
                service,
                "_startGpuSamplingStub",
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
            patch.object(service, "_stopGpuSamplingStub"),
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


if __name__ == "__main__":
    unittest.main()
