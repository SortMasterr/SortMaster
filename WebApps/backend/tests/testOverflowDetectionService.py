import unittest
from unittest.mock import AsyncMock, patch

from schemas.binState import BinCurrentState
from schemas.event import BinType, CameraId
from services.overflowDetectionService import (
    OverflowDetectionService,
    overflowSeconds,
)


class OverflowStateMachineTest(unittest.TestCase):
    def setUp(self):
        self.service = OverflowDetectionService()

    def testAccumulatesDurationWhileOverflowPersists(self):
        self.service._updateOverflowState(True, clockTime=0.0)
        self.service._updateOverflowState(True, clockTime=5.0)

        self.assertEqual(5.0, self.service.overflowDuration)
        self.assertFalse(self.service.finalOverflow)

    def testMarksFinalOverflowOnceThresholdReached(self):
        self.service._updateOverflowState(True, clockTime=0.0)
        self.service._updateOverflowState(
            True, clockTime=overflowSeconds
        )

        self.assertTrue(self.service.finalOverflow)

    def testBriefNormalBlipDoesNotResetOverflowStart(self):
        self.service._updateOverflowState(True, clockTime=0.0)
        self.service._updateOverflowState(True, clockTime=10.0)
        # normalResetSeconds is 1.0s, this blip is shorter
        self.service._updateOverflowState(False, clockTime=10.5)
        self.service._updateOverflowState(True, clockTime=11.0)

        self.assertEqual(11.0, self.service.overflowDuration)

    def testSustainedNormalResetsOverflowTracking(self):
        self.service._updateOverflowState(True, clockTime=0.0)
        self.service._updateOverflowState(True, clockTime=10.0)
        self.service._updateOverflowState(False, clockTime=10.0)
        self.service._updateOverflowState(False, clockTime=12.0)

        self.assertEqual(0.0, self.service.overflowDuration)
        self.assertFalse(self.service.finalOverflow)
        self.assertIsNone(self.service.overflowStartTime)

    def testStayingNormalNeverStartsOverflowTracking(self):
        self.service._updateOverflowState(False, clockTime=0.0)
        self.service._updateOverflowState(False, clockTime=1.0)

        self.assertEqual(0.0, self.service.overflowDuration)
        self.assertIsNone(self.service.overflowStartTime)


class OverflowDetectionServiceLifecycleTest(
    unittest.IsolatedAsyncioTestCase
):
    async def testStartReturnsFalseWhenModelWeightsMissing(self):
        service = OverflowDetectionService()

        started = await service.start()

        self.assertFalse(started)
        self.assertFalse(service.available)
        self.assertIsNone(service.task)

    async def testStopIsNoopWhenNeverStarted(self):
        service = OverflowDetectionService()

        await service.stop()  # 예외 없이 조용히 반환돼야 함

        self.assertIsNone(service.task)

    async def testReportBinStateSendsElevSideUpdateToBinStateService(
        self,
    ):
        service = OverflowDetectionService()
        service.sessionId = "side-test"
        service.finalOverflow = True
        service.overflowDuration = overflowSeconds

        with patch(
            "services.overflowDetectionService.binStateService.applyUpdate",
            AsyncMock(),
        ) as applyUpdate:
            await service._reportBinState(confidence=0.91)

        applyUpdate.assert_awaited_once()
        (sentUpdate,), _kwargs = applyUpdate.call_args

        self.assertEqual(CameraId.ELEVSIDE, sentUpdate.cameraId)
        self.assertEqual(
            BinCurrentState.FULL, sentUpdate.currentState
        )
        self.assertEqual(0.91, sentUpdate.confidenceScore)
        self.assertEqual(
            overflowSeconds, sentUpdate.overflowDuration
        )
        self.assertIsInstance(sentUpdate.binType, BinType)

    async def testReportBinStateSwallowsBinStateServiceFailure(self):
        service = OverflowDetectionService()
        service.sessionId = "side-test"
        service.finalOverflow = False

        with patch(
            "services.overflowDetectionService.binStateService.applyUpdate",
            AsyncMock(side_effect=RuntimeError("db down")),
        ):
            await service._reportBinState(confidence=0.5)
            # 예외가 위로 전파되지 않아야 함(추론 루프 전체가 죽으면 안 됨)


if __name__ == "__main__":
    unittest.main()
