"""
이벤트 트리거 녹화 세션 관리.

architecture.md 원칙대로 상시 녹화가 아니라 트리거 시점에만 캡처한다. 고정 10초가
아니라, 탐지 파이프라인(향후 detectionService.py)이 보내는 시작/종료 두 신호 사이의
실제 구간을 캡처한다 — start()로 캡처를 켜고, stop()이 호출된 시점까지의 프레임을
반환한다. 종료 신호가 유실되는 경우를 대비해 세션당 최대 캡처 길이를 둔다.
"""
import asyncio
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from schemas.event import CameraId
from streaming.cameraManager import cameraManagers

captureIntervalSeconds = 0.2  # ~5fps
maxRecordingSeconds = 30.0


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


class RecordingService:
    def __init__(self, cameraManagers: dict):
        self.cameraManagers = cameraManagers
        self.sessions: dict[str, RecordingSession] = {}

    async def start(
        self,
        cameraId: CameraId,
    ) -> str:
        cameraManager = self.cameraManagers[
            cameraId.value
        ]
        await cameraManager.start()

        session = RecordingSession(
            recordingId=str(uuid.uuid4()),
            cameraId=cameraId,
            startedAt=datetime.now(timezone.utc),
            fps=1 / captureIntervalSeconds,
        )
        session.task = asyncio.create_task(
            self._captureLoop(cameraManager, session)
        )

        self.sessions[session.recordingId] = session

        return session.recordingId

    async def stop(
        self,
        recordingId: str,
    ) -> tuple[list, float]:
        session = self.sessions.pop(recordingId, None)

        if session is None:
            raise KeyError(
                f"녹화 세션을 찾을 수 없음: {recordingId}"
            )

        session.stopped.set()

        if session.task is not None:
            await session.task

        durationSeconds = (
            datetime.now(timezone.utc)
            - session.startedAt
        ).total_seconds()

        return session.frames, durationSeconds

    async def _captureLoop(
        self,
        cameraManager,
        session: RecordingSession,
    ) -> None:
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


recordingService = RecordingService(cameraManagers)
