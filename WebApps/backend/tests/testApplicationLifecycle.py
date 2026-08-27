import asyncio
import unittest
from unittest.mock import AsyncMock, Mock, patch

import main


class ApplicationLifecycleTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.ensureVisitClipIndexes = patch.object(
            main.visitClipRepository,
            "ensureIndexes",
            AsyncMock(),
        ).start()
        self.addCleanup(patch.stopall)

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
                main.binStateRepository,
                "ensureIndexes",
                AsyncMock(),
            ) as ensureBinStateIndexes,
            patch.object(
                main.collectionTaskRepository,
                "ensureIndexes",
                AsyncMock(),
            ) as ensureCollectionTaskIndexes,
            patch.object(
                main.presenceGateService,
                "start",
                AsyncMock(),
            ) as startPresenceGate,
            patch.object(
                main.presenceGateService,
                "shutdown",
                AsyncMock(),
            ) as shutdownPresenceGate,
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
                ensureBinStateIndexes.assert_awaited_once_with()
                self.ensureVisitClipIndexes.assert_awaited_once_with()
                ensureCollectionTaskIndexes.assert_awaited_once_with()
                startPresenceGate.assert_awaited_once_with()

            shutdownPresenceGate.assert_awaited_once_with()
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
                main.binStateRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.collectionTaskRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "start",
                AsyncMock(),
            ) as startPresenceGate,
            patch.object(
                main.presenceGateService,
                "shutdown",
                AsyncMock(),
            ) as shutdownPresenceGate,
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
            startPresenceGate.assert_not_awaited()
            shutdownPresenceGate.assert_awaited_once_with()
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
                main.binStateRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.collectionTaskRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "start",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "shutdown",
                AsyncMock(),
            ) as shutdownPresenceGate,
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

            shutdownPresenceGate.assert_awaited_once_with()
            cameraManager.stop.assert_awaited_once_with()
            closeMongoClient.assert_called_once_with()

    async def testMongoClosesEvenIfPresenceGateShutdownFails(self):
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
                main.binStateRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.collectionTaskRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "start",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "shutdown",
                AsyncMock(
                    side_effect=RuntimeError(
                        "presence gate shutdown failed"
                    )
                ),
            ),
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
                "presence gate shutdown failed",
            ):
                async with main.lifespan(main.app):
                    pass

            shutdownRecording.assert_awaited_once_with()
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
                main.binStateRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.collectionTaskRepository,
                "ensureIndexes",
                AsyncMock(),
            ),
            patch.object(
                main.presenceGateService,
                "start",
                AsyncMock(),
            ) as startPresenceGate,
            patch.object(
                main.presenceGateService,
                "shutdown",
                AsyncMock(),
            ),
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
            startPresenceGate.assert_not_awaited()
            closeMongoClient.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
