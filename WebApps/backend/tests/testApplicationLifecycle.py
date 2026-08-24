import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import main


class ApplicationLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def testLifespanChecksDatabaseAndReleasesResources(self):
        cameraManager = Mock()
        cameraManager.stop = AsyncMock()

        with (
            patch.object(
                main,
                "pingMongo",
                AsyncMock(),
            ) as pingMongo,
            patch.object(
                main.eventRepository,
                "ensureIndexes",
                AsyncMock(),
            ) as ensureIndexes,
            patch.object(
                main.recordingService,
                "shutdown",
                AsyncMock(),
            ) as shutdownRecording,
            patch.object(
                main,
                "cameraManagers",
                {"ELEV-TOP": cameraManager},
            ),
            patch.object(
                main,
                "closeMongoClient",
            ) as closeMongoClient,
        ):
            async with main.lifespan(main.app):
                pingMongo.assert_awaited_once_with()
                ensureIndexes.assert_awaited_once_with()

            shutdownRecording.assert_awaited_once_with()
            cameraManager.stop.assert_awaited_once_with()
            closeMongoClient.assert_called_once_with()

    async def testStartupFailureStillReleasesResources(self):
        cameraManager = Mock()
        cameraManager.stop = AsyncMock()

        with (
            patch.object(
                main,
                "pingMongo",
                AsyncMock(
                    side_effect=RuntimeError("database unavailable")
                ),
            ),
            patch.object(
                main.eventRepository,
                "ensureIndexes",
                AsyncMock(),
            ) as ensureIndexes,
            patch.object(
                main.recordingService,
                "shutdown",
                AsyncMock(),
            ) as shutdownRecording,
            patch.object(
                main,
                "cameraManagers",
                {"ELEV-TOP": cameraManager},
            ),
            patch.object(
                main,
                "closeMongoClient",
            ) as closeMongoClient,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "database unavailable",
            ):
                async with main.lifespan(main.app):
                    self.fail("lifespan should not start")

            ensureIndexes.assert_not_awaited()
            shutdownRecording.assert_awaited_once_with()
            cameraManager.stop.assert_awaited_once_with()
            closeMongoClient.assert_called_once_with()

    async def testMongoClosesEvenIfRecordingShutdownFails(self):
        cameraManager = Mock()
        cameraManager.stop = AsyncMock()

        with (
            patch.object(
                main,
                "pingMongo",
                AsyncMock(),
            ),
            patch.object(
                main.eventRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.recordingService,
                "shutdown",
                AsyncMock(
                    side_effect=RuntimeError("shutdown failed")
                ),
            ),
            patch.object(
                main,
                "cameraManagers",
                {"ELEV-TOP": cameraManager},
            ),
            patch.object(
                main,
                "closeMongoClient",
            ) as closeMongoClient,
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "shutdown failed",
            ):
                async with main.lifespan(main.app):
                    pass

            cameraManager.stop.assert_awaited_once_with()
            closeMongoClient.assert_called_once_with()

    async def testMongoPingHasWholeOperationTimeout(self):
        cameraManager = Mock()
        cameraManager.stop = AsyncMock()

        async def neverReturns():
            await asyncio.Event().wait()

        with (
            patch.object(
                main,
                "pingMongo",
                side_effect=neverReturns,
            ),
            patch.object(
                main,
                "mongoStartupTimeoutSeconds",
                0.001,
            ),
            patch.object(
                main.eventRepository,
                "ensureIndexes",
                AsyncMock(),
            ) as ensureIndexes,
            patch.object(
                main.recordingService,
                "shutdown",
                AsyncMock(),
            ),
            patch.object(
                main,
                "cameraManagers",
                {"ELEV-TOP": cameraManager},
            ),
            patch.object(
                main,
                "closeMongoClient",
            ) as closeMongoClient,
        ):
            with self.assertRaises(TimeoutError):
                async with main.lifespan(main.app):
                    self.fail("lifespan should time out")

            ensureIndexes.assert_not_awaited()
            closeMongoClient.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
