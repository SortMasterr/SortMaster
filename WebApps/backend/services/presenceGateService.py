"""
TOP 카메라(ELEV-TOP) 사람 존재 감지 게이팅.

architecture.md "탐지 파이프라인"의 사람 존재 감지 게이팅을 구현한다: 사람이 통 앞에
있는 동안만 녹화를 켜고(추후 GPU 프레임 샘플링도 같이 켤 예정 — 아래 TODO 스텁), 사람이
벗어나면(약 3초 유예 후) 녹화를 끈다. 모션(움직임) 감지는 투척 시작 순간을 놓칠 수
있어 기각됐고(decisionLog.md), 대신 detection/presenceDetector.py의 배경 차분
전경 비율을 임계값+디바운스로 게이팅한다.

GPU `inference` API가 아직 없어서, 이탈 시 stopDetectionWithStatus(분류 결과 필요)는
호출하지 않는다 — recordingService.stop()만 직접 호출해 녹화를 종료하고 프레임은
버린다(Event 미생성). GPU 연동 후에는 이 부분이 "GPU 판정 대기 → stopDetectionWithStatus"로
교체될 예정.
"""
import asyncio
import logging
import os
import time
from enum import Enum

import cv2
import numpy as np

from detection.presenceDetector import PersonPresenceDetector
from schemas.event import CameraId
from services.detectionService import detectionService
from services.errors import (
    CameraUnavailableError,
    RecordingCameraMismatchError,
    RecordingNotFoundError,
)
from services.recordingService import recordingService
from streaming.cameraManager import cameraManagers

logger = logging.getLogger(__name__)

pollIntervalSeconds = float(os.getenv("PRESENCE_POLL_INTERVAL_SECONDS", "0.2"))
foregroundRatioThreshold = float(os.getenv("PRESENCE_FOREGROUND_RATIO_THRESHOLD", "0.05"))
entryConfirmSeconds = float(os.getenv("PRESENCE_ENTRY_CONFIRM_SECONDS", "0.5"))
exitGraceSeconds = float(os.getenv("PRESENCE_EXIT_GRACE_SECONDS", "3.0"))
# 카메라 재오픈 재시도 간격 — 튜닝 노브가 아니라 구현 디테일이라 .env로 노출하지 않음
cameraStartRetryIntervalSeconds = 5.0
# MOG2 배경 모델이 "빈 화면"을 다시 학습하는 데 걸리는 대략적 시간 — cv2 기본값(history=500)은
# 30fps 기준(약 16초)이라, 우리 폴링 주기(pollIntervalSeconds)로 환산하면 실제로는 훨씬 오래
# 걸림(0.2초 간격이면 100초!). 백엔드가 재시작될 때마다 그만큼 오탐(사람이 없어도 PRESENT로
# 잘못 판단하거나, 사람이 나가도 ABSENT로 안 돌아오는 문제)이 재현됐던 것 — 실기기 테스트로
# 확인됨. 폴링 주기에 맞춰 history를 계산해서 항상 이 정도 시간 안에 수렴하게 한다.
backgroundHistorySeconds = 20.0


class PresenceState(str, Enum):
    ABSENT = "ABSENT"
    PRESENT = "PRESENT"


class PresenceGateService:
    def __init__(self, cameraId: CameraId, cameraManagers: dict):
        self.cameraId = cameraId
        self.cameraManagers = cameraManagers
        self.presenceDetector = PersonPresenceDetector(
            history=max(
                1,
                round(backgroundHistorySeconds / pollIntervalSeconds),
            )
        )
        self.state = PresenceState.ABSENT
        self.recordingId: str | None = None
        self.aboveThresholdSince: float | None = None
        self.belowThresholdSince: float | None = None
        self.lastCameraStartAttemptAt: float | None = None
        self.pollTask: asyncio.Task | None = None
        self.stopped = asyncio.Event()

    async def start(self) -> None:
        if self.pollTask is not None:
            return

        # 카메라를 여기서 직접 열지 않음 — RTSP 소스가 아직 응답이 없으면
        # cameraManager.start()의 재시도(최대 5회) x OpenCV RTSP 연결 타임아웃(기본
        # 30초)이 겹쳐 앱 시작 자체가 몇 분씩 멈출 수 있음(실기기 테스트 중 실측 확인).
        # 폴링 루프를 먼저 띄우고, 카메라 열기는 _handleNoFrame()이 백그라운드에서
        # 재시도하게 해서 main.py의 lifespan을 절대 막지 않는다.
        self.stopped.clear()
        self.pollTask = asyncio.create_task(self._pollLoop())

    async def shutdown(self) -> None:
        self.stopped.set()

        if self.pollTask is not None:
            self.pollTask.cancel()

            try:
                await self.pollTask
            except asyncio.CancelledError:
                pass

            self.pollTask = None

        if self.recordingId is not None:
            await self._stopRecording()

    async def _pollLoop(self) -> None:
        cameraManager = self.cameraManagers[self.cameraId.value]

        try:
            while not self.stopped.is_set():
                frame = await cameraManager.readFrame()
                now = time.monotonic()
                decoded = (
                    await asyncio.to_thread(self._decodeFrame, frame)
                    if frame is not None
                    else None
                )

                if decoded is not None:
                    ratio = await asyncio.to_thread(
                        self.presenceDetector.foregroundRatio,
                        decoded,
                    )
                    await self._handleRatio(ratio, now)
                else:
                    await self._handleNoFrame(now)

                try:
                    await asyncio.wait_for(
                        self.stopped.wait(),
                        timeout=pollIntervalSeconds,
                    )
                except asyncio.TimeoutError:
                    pass
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception(
                "[presenceGateService] '%s' 폴링 루프가 예기치 않게 종료됨",
                self.cameraId.value,
            )

    @staticmethod
    def _decodeFrame(frame: bytes):
        # cameraManager.readFrame()은 항상 JPEG bytes를 반환함(RTSP/로컬 웹캠 공통) —
        # 배경 차분(PersonPresenceDetector)은 numpy 배열을 기대하므로 다시 디코딩한다.
        decoded = cv2.imdecode(
            np.frombuffer(frame, dtype=np.uint8),
            cv2.IMREAD_COLOR,
        )
        return decoded if decoded is not None else None

    async def _handleNoFrame(self, now: float) -> None:
        if (
            self.lastCameraStartAttemptAt is not None
            and now - self.lastCameraStartAttemptAt
            < cameraStartRetryIntervalSeconds
        ):
            return

        self.lastCameraStartAttemptAt = now
        cameraManager = self.cameraManagers[self.cameraId.value]

        try:
            await cameraManager.start()
        except RuntimeError:
            pass

    async def _handleRatio(self, ratio: float, now: float) -> None:
        isAboveThreshold = ratio >= foregroundRatioThreshold

        if self.state == PresenceState.ABSENT:
            if isAboveThreshold:
                if self.aboveThresholdSince is None:
                    self.aboveThresholdSince = now

                if now - self.aboveThresholdSince >= entryConfirmSeconds:
                    await self._enterPresent()
            else:
                self.aboveThresholdSince = None
        else:
            if isAboveThreshold:
                self.belowThresholdSince = None
            else:
                if self.belowThresholdSince is None:
                    self.belowThresholdSince = now

                if now - self.belowThresholdSince >= exitGraceSeconds:
                    await self._exitToAbsent()

    async def _enterPresent(self) -> None:
        self.state = PresenceState.PRESENT
        self.aboveThresholdSince = None

        try:
            self.recordingId = await detectionService.startDetection(
                self.cameraId
            )
        except CameraUnavailableError as error:
            logger.warning(
                "[presenceGateService] '%s' 녹화 시작 실패, ABSENT로 되돌림: %s",
                self.cameraId.value,
                error,
            )
            self.state = PresenceState.ABSENT
            return

        logger.info(
            "[presenceGateService] '%s' 사람 감지, 녹화 시작 (recordingId=%s)",
            self.cameraId.value,
            self.recordingId,
        )
        self._startGpuSamplingStub()

    async def _exitToAbsent(self) -> None:
        self.state = PresenceState.ABSENT
        self.belowThresholdSince = None
        self._stopGpuSamplingStub()
        await self._stopRecording()

    async def _stopRecording(self) -> None:
        recordingId = self.recordingId
        self.recordingId = None

        if recordingId is None:
            return

        try:
            _frames, durationSeconds = await recordingService.stop(
                recordingId,
                expectedCameraId=self.cameraId,
            )
        except (
            RecordingNotFoundError,
            RecordingCameraMismatchError,
        ) as error:
            logger.warning(
                "[presenceGateService] '%s' 녹화 종료 중 이미 정리됨"
                "(recordingId=%s): %s",
                self.cameraId.value,
                recordingId,
                error,
            )
            return

        logger.info(
            "[presenceGateService] '%s' 사람 이탈, 녹화 종료 "
            "(recordingId=%s, %.1fs, GPU 판정 없어 Event 미생성)",
            self.cameraId.value,
            recordingId,
            durationSeconds,
        )

    def _startGpuSamplingStub(self) -> None:
        # TODO: GPU inference API 연동 후 교체 — 5~10fps로 프레임 샘플링해 세션 시작 호출
        logger.debug(
            "[presenceGateService] '%s' GPU 프레임 샘플링 시작 (미구현 스텁)",
            self.cameraId.value,
        )

    def _stopGpuSamplingStub(self) -> None:
        # TODO: GPU inference API 연동 후 교체 — 세션 종료 호출
        logger.debug(
            "[presenceGateService] '%s' GPU 프레임 샘플링 종료 (미구현 스텁)",
            self.cameraId.value,
        )


presenceGateService = PresenceGateService(CameraId.ELEVTOP, cameraManagers)
