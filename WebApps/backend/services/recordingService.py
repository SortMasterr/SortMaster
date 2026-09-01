"""
이벤트 트리거 녹화 세션 관리.

architecture.md 원칙대로 상시 녹화가 아니라 트리거 시점에만 캡처한다. 고정 10초가
아니라, 탐지 파이프라인(향후 detectionService.py)이 보내는 시작/종료 두 신호 사이의
실제 구간을 캡처한다 — start()로 캡처를 켜고, stop()이 호출된 시점까지의 프레임을
반환한다. 종료 신호가 유실되는 경우를 대비해 세션당 최대 캡처 길이를 둔다.
"""
import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from schemas.event import CameraId
from services.errors import (
    CameraUnavailableError,
    RecordingCameraMismatchError,
    RecordingNotFoundError,
)
from streaming.cameraManager import cameraManagers

captureIntervalSeconds = 0.2  # ~5fps
maxRecordingSeconds = 30.0
stoppedRecordingRetentionSeconds = 120.0
logger = logging.getLogger(__name__)


@dataclass
class RecordingSession:
    recordingId: str
    cameraId: CameraId
    startedAt: datetime
    fps: float
    frames: list = field(default_factory=list)
    task: asyncio.Task | None = None
    stopped: asyncio.Event = field(
        default_factory=asyncio.Event
    )


@dataclass
class StoppedRecording:
    cameraId: CameraId
    frames: list
    durationSeconds: float
    expiresAt: float


class RecordingService:
    def __init__(self, cameraManagers: dict):
        self.cameraManagers = cameraManagers
        self.sessions: dict[str, RecordingSession] = {}
        self.stoppedRecordings: dict[
            str,
            StoppedRecording,
        ] = {}
        self.stopLock = asyncio.Lock()
        self.cleanupTasks: set[asyncio.Task] = set()

    async def start(
        self,
        cameraId: CameraId,
    ) -> str:
        cameraManager = self.cameraManagers[
            cameraId.value
        ]
        try:
            await cameraManager.start()
        except RuntimeError as error:
            raise CameraUnavailableError(str(error)) from error

        session = RecordingSession(
            recordingId=str(uuid.uuid4()),
            cameraId=cameraId,
            startedAt=datetime.now(timezone.utc),
            fps=1 / captureIntervalSeconds,
        )
        session.task = asyncio.create_task(
            self._captureLoop(cameraManager, session)
        )
        session.task.add_done_callback(
            self._logCaptureFailure
        )

        self.sessions[session.recordingId] = session

        return session.recordingId

    async def stop(
        self,
        recordingId: str,
        expectedCameraId: CameraId | None = None,
    ) -> tuple[list, float]:
        async with self.stopLock:
            return await self._stop(
                recordingId,
                expectedCameraId,
            )

    async def _stop(
        self,
        recordingId: str,
        expectedCameraId: CameraId | None = None,
    ) -> tuple[list, float]:
        self._pruneStoppedRecordings()
        session = self.sessions.get(recordingId)

        if session is None:
            stoppedRecording = self.stoppedRecordings.get(
                recordingId
            )

            if stoppedRecording is not None:
                if (
                    expectedCameraId is not None
                    and stoppedRecording.cameraId
                    != expectedCameraId
                ):
                    raise RecordingCameraMismatchError(
                        "Recording camera does not match "
                        "the start request."
                    )

                return (
                    list(stoppedRecording.frames),
                    stoppedRecording.durationSeconds,
                )

            raise RecordingNotFoundError(
                f"녹화 세션을 찾을 수 없음: {recordingId}"
            )

        if (
            expectedCameraId is not None
            and session.cameraId != expectedCameraId
        ):
            raise RecordingCameraMismatchError(
                'Recording camera does not match the start request.'
            )

        self.sessions.pop(recordingId, None)
        session.stopped.set()

        if session.task is not None:
            await session.task

        durationSeconds = (
            datetime.now(timezone.utc)
            - session.startedAt
        ).total_seconds()

        self.stoppedRecordings[recordingId] = StoppedRecording(
            cameraId=session.cameraId,
            frames=session.frames,
            durationSeconds=durationSeconds,
            expiresAt=(
                time.monotonic()
                + stoppedRecordingRetentionSeconds
            ),
        )
        cleanupTask = asyncio.create_task(
            self._expireStoppedRecording(
                recordingId,
                stoppedRecordingRetentionSeconds,
            )
        )
        self.cleanupTasks.add(cleanupTask)
        cleanupTask.add_done_callback(
            self.cleanupTasks.discard
        )

        return list(session.frames), durationSeconds

    async def releaseStopped(
        self,
        recordingId: str,
    ) -> None:
        async with self.stopLock:
            recording = self.stoppedRecordings.pop(
                recordingId,
                None,
            )

            if recording is not None:
                recording.frames.clear()

    async def shutdown(self) -> None:
        async with self.stopLock:
            sessions = list(self.sessions.values())
            self.sessions.clear()
            stoppedRecordings = list(
                self.stoppedRecordings.values()
            )
            self.stoppedRecordings.clear()
            cleanupTasks = list(self.cleanupTasks)
            self.cleanupTasks.clear()

            captureTasks = []

            for session in sessions:
                session.stopped.set()

                if session.task is not None:
                    session.task.cancel()
                    captureTasks.append(session.task)

            for cleanupTask in cleanupTasks:
                cleanupTask.cancel()

        if captureTasks or cleanupTasks:
            await asyncio.gather(
                *captureTasks,
                *cleanupTasks,
                return_exceptions=True,
            )

        for session in sessions:
            session.frames.clear()

        for recording in stoppedRecordings:
            recording.frames.clear()

    async def _expireStoppedRecording(
        self,
        recordingId: str,
        delaySeconds: float,
    ) -> None:
        await asyncio.sleep(delaySeconds)

        async with self.stopLock:
            recording = self.stoppedRecordings.get(
                recordingId
            )

            if (
                recording is not None
                and recording.expiresAt <= time.monotonic()
            ):
                self.stoppedRecordings.pop(recordingId, None)
                recording.frames.clear()

    def _pruneStoppedRecordings(self) -> None:
        currentTime = time.monotonic()
        expiredRecordingIds = [
            recordingId
            for recordingId, recording
            in self.stoppedRecordings.items()
            if recording.expiresAt <= currentTime
        ]

        for recordingId in expiredRecordingIds:
            recording = self.stoppedRecordings.pop(recordingId)
            recording.frames.clear()

    async def _captureLoop(
        self,
        cameraManager,
        session: RecordingSession,
    ) -> None:
        try:
            while not session.stopped.is_set():
                elapsed = (
                    datetime.now(timezone.utc)
                    - session.startedAt
                ).total_seconds()

                if elapsed >= maxRecordingSeconds:
                    print(
                        f"[recordingService] '{session.recordingId}' "
                        f"최대 녹화 길이({maxRecordingSeconds}s) 초과, "
                        "자동 종료"
                    )
                    break

                frame = await cameraManager.readFrame()

                if frame is not None:
                    session.frames.append(frame)

                try:
                    await asyncio.wait_for(
                        session.stopped.wait(),
                        timeout=captureIntervalSeconds,
                    )
                except asyncio.TimeoutError:
                    pass
        finally:
            if self.sessions.get(session.recordingId) is session:
                self.sessions.pop(session.recordingId, None)
                session.frames.clear()

    @staticmethod
    def _logCaptureFailure(task: asyncio.Task) -> None:
        if task.cancelled():
            return

        error = task.exception()

        if error is not None:
            logger.error(
                "Recording capture task failed",
                exc_info=(
                    type(error),
                    error,
                    error.__traceback__,
                ),
            )


recordingService = RecordingService(cameraManagers)
