import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock

from schemas.mode import Mode, ModeUpdate
from services.binPositionMonitorService import (
    BinPositionMonitorConfig,
    BinPositionMonitorService,
)
from services.modeService import ModeService


class BinPositionMonitorServiceTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temporaryDirectory = tempfile.TemporaryDirectory()
        self.modeService = ModeService()
        self.webSocketManager = Mock()
        self.webSocketManager.broadcast = AsyncMock()
        self.service = BinPositionMonitorService(
            cameraManager=Mock(),
            modeService=self.modeService,
            webSocketManager=self.webSocketManager,
        )
        self.service.config = BinPositionMonitorConfig(
            enabled=True,
            markerIds=(0, 1, 2),
            baselinePath=(
                Path(self.temporaryDirectory.name) / "baseline.json"
            ),
            positionToleranceRatio=0.06,
            awayConfirmSeconds=3,
            returnConfirmSeconds=5,
            pollSeconds=0.5,
        )
        self.service.baseline = {
            0: (0.2, 0.5),
            1: (0.5, 0.5),
            2: (0.8, 0.5),
        }
        self.homePositions = dict(self.service.baseline)

    def tearDown(self):
        self.temporaryDirectory.cleanup()

    async def testMovesToCollectAndBackToManageAfterStableReturn(self):
        awayPositions = {
            0: (0.35, 0.5),
            1: (0.5, 0.5),
            2: (0.8, 0.5),
        }

        await self.service.evaluatePositions(awayPositions, 0)
        await self.service.evaluatePositions(awayPositions, 3)

        self.assertEqual(self.modeService.getMode().mode, Mode.collect)
        self.assertTrue(self.service.getStatus().automaticallyChangedMode)

        await self.service.evaluatePositions(self.homePositions, 4)
        await self.service.evaluatePositions(self.homePositions, 9)

        self.assertEqual(self.modeService.getMode().mode, Mode.manage)
        self.assertFalse(self.service.getStatus().automaticallyChangedMode)
        self.assertEqual(self.webSocketManager.broadcast.await_count, 2)

    async def testMissingMarkerAlsoStartsCollectionMode(self):
        positionsWithMissingBin = {
            0: (0.2, 0.5),
            1: (0.5, 0.5),
        }

        await self.service.evaluatePositions(positionsWithMissingBin, 10)
        await self.service.evaluatePositions(positionsWithMissingBin, 13)

        self.assertEqual(self.modeService.getMode().mode, Mode.collect)

    async def testManualChangeDuringAutomaticCollectionIsNotOverwritten(self):
        awayPositions = {
            0: (0.35, 0.5),
            1: (0.5, 0.5),
            2: (0.8, 0.5),
        }
        await self.service.evaluatePositions(awayPositions, 0)
        await self.service.evaluatePositions(awayPositions, 3)
        self.modeService.updateMode(ModeUpdate(mode=Mode.collect))

        await self.service.evaluatePositions(self.homePositions, 4)
        await self.service.evaluatePositions(self.homePositions, 20)

        self.assertEqual(self.modeService.getMode().mode, Mode.collect)
        self.assertFalse(self.service.getStatus().automaticallyChangedMode)
        self.assertEqual(self.webSocketManager.broadcast.await_count, 1)

    async def testManualManageOverrideWhileAwayDoesNotImmediatelyAutoCollectAgain(self):
        awayPositions = {
            0: (0.35, 0.5),
            1: (0.5, 0.5),
            2: (0.8, 0.5),
        }
        await self.service.evaluatePositions(awayPositions, 0)
        await self.service.evaluatePositions(awayPositions, 3)
        self.modeService.updateMode(ModeUpdate(mode=Mode.manage))

        await self.service.evaluatePositions(awayPositions, 30)

        self.assertEqual(self.modeService.getMode().mode, Mode.manage)
        self.assertEqual(self.service.state, "MANUAL_OVERRIDE")


if __name__ == "__main__":
    unittest.main()
