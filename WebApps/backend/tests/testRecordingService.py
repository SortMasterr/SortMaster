import asyncio
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from schemas.event import CameraId
from services.recordingService import (
    RecordingService,
    RecordingSession,
)


def recordingSession(recordingId="recording-test"):
    return RecordingSession(
        recordingId=recordingId,
        cameraId=CameraId.ELEVTOP,
        startedAt=datetime.now(timezone.utc),
        fps=5.0,
    )


class RecordingServiceTest(unittest.IsolatedAsyncioTestCase):
    async def testCameraMismatchKeepsSessionForCorrectRetry(self):
        service = RecordingService({})
        session = recordingSession()
        service.sessions[session.recordingId] = session

        with self.assertRaises(ValueError):
            await service.stop(
                session.recordingId,
                expectedCameraId=CameraId.ELEVSIDE,
            )

        self.assertIs(
            session,
            service.sessions[session.recordingId],
        )
        self.assertFalse(session.stopped.is_set())

    async def testTimedOutCaptureReleasesSessionAndFrames(self):
        service = RecordingService({})
        session = recordingSession("recording-timeout")
        session.frames.append(object())
        service.sessions[session.recordingId] = session
        cameraManager = AsyncMock()

        with patch(
            "services.recordingService.maxRecordingSeconds",
            0.0,
        ):
            await service._captureLoop(
                cameraManager,
                session,
            )

        self.assertNotIn(
            session.recordingId,
            service.sessions,
        )
        self.assertEqual([], session.frames)
        cameraManager.readFrame.assert_not_awaited()

    async def testCaptureExceptionReleasesSessionAndFrames(self):
        service = RecordingService({})
        session = recordingSession("recording-read-failure")
        session.frames.append(object())
        service.sessions[session.recordingId] = session
        cameraManager = AsyncMock()
        cameraManager.readFrame.side_effect = RuntimeError(
            "camera read failed"
        )

        with self.assertRaisesRegex(
            RuntimeError,
            "camera read failed",
        ):
            await service._captureLoop(
                cameraManager,
                session,
            )

        self.assertNotIn(
            session.recordingId,
            service.sessions,
        )
        self.assertEqual([], session.frames)

    async def testCompletedRecordingCanBeRetried(self):
        service = RecordingService({})
        session = recordingSession("recording-retry")
        frame = object()
        session.frames.append(frame)
        service.sessions[session.recordingId] = session

        firstFrames, firstDuration = await service.stop(
            session.recordingId,
            expectedCameraId=CameraId.ELEVTOP,
        )
        retryFrames, retryDuration = await service.stop(
            session.recordingId,
            expectedCameraId=CameraId.ELEVTOP,
        )

        self.assertEqual([frame], firstFrames)
        self.assertIsNot(firstFrames, retryFrames)
        self.assertEqual(firstFrames, retryFrames)
        self.assertEqual(firstDuration, retryDuration)

        with self.assertRaises(ValueError):
            await service.stop(
                session.recordingId,
                expectedCameraId=CameraId.ELEVSIDE,
            )

    async def testConcurrentStopRequestsShareCompletedRecording(self):
        service = RecordingService({})
        session = recordingSession("recording-concurrent-stop")
        frame = object()
        session.frames.append(frame)
        service.sessions[session.recordingId] = session

        firstResult, secondResult = await asyncio.gather(
            service.stop(
                session.recordingId,
                expectedCameraId=CameraId.ELEVTOP,
            ),
            service.stop(
                session.recordingId,
                expectedCameraId=CameraId.ELEVTOP,
            ),
        )

        self.assertIsNot(firstResult[0], secondResult[0])
        self.assertEqual(firstResult[0], secondResult[0])
        self.assertEqual([frame], firstResult[0])

    async def testCompletedRecordingExpiresWithoutAnotherStop(self):
        service = RecordingService({})
        session = recordingSession("recording-expiry")
        frames = session.frames
        frames.append(object())
        service.sessions[session.recordingId] = session

        with patch(
            "services.recordingService."
            "stoppedRecordingRetentionSeconds",
            0.0,
        ):
            returnedFrames, _ = await service.stop(
                session.recordingId,
                expectedCameraId=CameraId.ELEVTOP,
            )

        await asyncio.sleep(0)
        await asyncio.sleep(0)

        self.assertNotIn(
            session.recordingId,
            service.stoppedRecordings,
        )
        self.assertEqual([], frames)
        self.assertEqual(1, len(returnedFrames))

    async def testShutdownCancelsTasksAndClearsAllFrames(self):
        service = RecordingService({})
        activeSession = recordingSession("recording-active")
        activeSession.frames.append(object())
        activeSession.task = asyncio.create_task(
            asyncio.sleep(60)
        )
        service.sessions[activeSession.recordingId] = (
            activeSession
        )

        completedSession = recordingSession(
            "recording-completed"
        )
        completedSession.frames.append(object())
        service.sessions[completedSession.recordingId] = (
            completedSession
        )
        await service.stop(
            completedSession.recordingId,
            expectedCameraId=CameraId.ELEVTOP,
        )

        await service.shutdown()

        self.assertTrue(activeSession.task.cancelled())
        self.assertEqual({}, service.sessions)
        self.assertEqual({}, service.stoppedRecordings)
        self.assertEqual(set(), service.cleanupTasks)
        self.assertEqual([], activeSession.frames)
        self.assertEqual([], completedSession.frames)


if __name__ == "__main__":
    unittest.main()
