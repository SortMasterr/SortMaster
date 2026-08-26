import asyncio
import json
import logging
import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from time import monotonic

import cv2
import numpy as np
from dotenv import load_dotenv

from schemas.binPositionMonitor import BinPositionMonitorStatus
from schemas.event import CameraId
from schemas.mode import Mode, ModeUpdate
from services.modeService import ModeService, modeService
from services.webSocketManager import WebSocketManager, webSocketManager
from streaming.cameraManager import cameraManagers


load_dotenv()
logger = logging.getLogger(__name__)


class BinPositionCalibrationError(RuntimeError):
    pass


@dataclass(frozen=True)
class BinPositionMonitorConfig:
    enabled: bool
    markerIds: tuple[int, int, int]
    baselinePath: Path
    positionToleranceRatio: float
    awayConfirmSeconds: float
    returnConfirmSeconds: float
    pollSeconds: float


def _parseBool(value: str) -> bool:
    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def loadBinPositionMonitorConfig() -> BinPositionMonitorConfig:
    markerIds = tuple(
        int(value.strip())
        for value in os.getenv(
            "RPA_BIN_MARKER_IDS",
            "0,1,2",
        ).split(",")
        if value.strip()
    )

    if len(markerIds) != 3 or len(set(markerIds)) != 3:
        raise ValueError(
            "RPA_BIN_MARKER_IDS에는 서로 다른 마커 ID 3개가 필요합니다."
        )

    stateDirectory = Path(
        os.getenv(
            "RPA_STATE_DIRECTORY",
            "RPAs/reportAutomation/state",
        )
    )
    baselinePathValue = os.getenv(
        "RPA_BIN_MARKER_BASELINE_PATH",
        "",
    ).strip()
    baselinePath = Path(
        baselinePathValue
        or stateDirectory / "binMarkerBaseline.json"
    )

    positionToleranceRatio = float(
        os.getenv("RPA_BIN_POSITION_TOLERANCE_RATIO", "0.06")
    )
    awayConfirmSeconds = float(
        os.getenv("RPA_BIN_AWAY_CONFIRM_SECONDS", "3")
    )
    returnConfirmSeconds = float(
        os.getenv("RPA_BIN_RETURN_CONFIRM_SECONDS", "5")
    )
    pollSeconds = float(
        os.getenv("RPA_BIN_POSITION_POLL_SECONDS", "0.5")
    )

    if not 0 < positionToleranceRatio < 1:
        raise ValueError(
            "RPA_BIN_POSITION_TOLERANCE_RATIO는 0과 1 사이여야 합니다."
        )

    if min(awayConfirmSeconds, returnConfirmSeconds, pollSeconds) <= 0:
        raise ValueError(
            "쓰레기통 위치 감지 시간 설정은 0보다 커야 합니다."
        )

    return BinPositionMonitorConfig(
        enabled=_parseBool(
            os.getenv("RPA_BIN_POSITION_ENABLED", "false")
        ),
        markerIds=markerIds,
        baselinePath=baselinePath,
        positionToleranceRatio=positionToleranceRatio,
        awayConfirmSeconds=awayConfirmSeconds,
        returnConfirmSeconds=returnConfirmSeconds,
        pollSeconds=pollSeconds,
    )


class BinMarkerDetector:
    def __init__(self):
        dictionary = cv2.aruco.getPredefinedDictionary(
            cv2.aruco.DICT_4X4_50
        )
        parameters = cv2.aruco.DetectorParameters()
        self.detector = cv2.aruco.ArucoDetector(
            dictionary,
            parameters,
        )

    def detect(
        self,
        jpegBytes: bytes,
    ) -> dict[int, tuple[float, float]]:
        encodedFrame = np.frombuffer(
            jpegBytes,
            dtype=np.uint8,
        )
        frame = cv2.imdecode(
            encodedFrame,
            cv2.IMREAD_GRAYSCALE,
        )

        if frame is None:
            return {}

        corners, markerIds, _ = self.detector.detectMarkers(frame)

        if markerIds is None:
            return {}

        frameHeight, frameWidth = frame.shape[:2]
        positions: dict[int, tuple[float, float]] = {}

        for markerCorners, markerId in zip(corners, markerIds.flatten()):
            center = markerCorners[0].mean(axis=0)
            positions[int(markerId)] = (
                float(center[0]) / frameWidth,
                float(center[1]) / frameHeight,
            )

        return positions


class BinPositionMonitorService:
    def __init__(
        self,
        cameraManager,
        modeService: ModeService,
        webSocketManager: WebSocketManager,
    ):
        self.cameraManager = cameraManager
        self.modeService = modeService
        self.webSocketManager = webSocketManager
        self.detector = BinMarkerDetector()
        self.config: BinPositionMonitorConfig | None = None
        self.baseline: dict[int, tuple[float, float]] = {}
        self.visiblePositions: dict[int, tuple[float, float]] = {}
        self.lastFrameAt: str | None = None
        self.state = "DISABLED"
        self.message = "자동 위치 감지가 비활성화되어 있습니다."
        self.awaySince: float | None = None
        self.homeSince: float | None = None
        self.automaticModeRevision: int | None = None
        self.manualOverrideActive = False
        self.pollTask: asyncio.Task | None = None

    async def start(self) -> None:
        self.config = loadBinPositionMonitorConfig()
        self._loadBaseline()

        if not self.config.enabled:
            self.state = "DISABLED"
            self.message = "RPA_BIN_POSITION_ENABLED=false"
            return

        self.state = (
            "MONITORING"
            if self.baseline
            else "UNCALIBRATED"
        )
        self.message = (
            "3개 쓰레기통 위치를 감시하고 있습니다."
            if self.baseline
            else "3개 마커가 원위치에 있을 때 기준 위치를 등록해 주세요."
        )
        self.pollTask = asyncio.create_task(self._pollLoop())

    async def shutdown(self) -> None:
        if self.pollTask is None:
            return

        self.pollTask.cancel()

        try:
            await self.pollTask
        except asyncio.CancelledError:
            pass

        self.pollTask = None

    async def calibrate(self) -> BinPositionMonitorStatus:
        config = self._requireConfig()

        if not config.enabled:
            raise BinPositionCalibrationError(
                "RPA_BIN_POSITION_ENABLED=true로 설정한 뒤 재시작해 주세요."
            )

        positions = await self._readPositions()
        missingMarkerIds = [
            markerId
            for markerId in config.markerIds
            if markerId not in positions
        ]

        if missingMarkerIds:
            missingText = ", ".join(
                str(markerId) for markerId in missingMarkerIds
            )
            raise BinPositionCalibrationError(
                f"SIDE 카메라에서 마커 {missingText}을(를) 찾지 못했습니다."
            )

        self.baseline = {
            markerId: positions[markerId]
            for markerId in config.markerIds
        }
        self._saveBaseline()
        self.awaySince = None
        self.homeSince = None
        self.state = "MONITORING"
        self.message = "3개 쓰레기통의 원위치 등록이 완료되었습니다."
        return self.getStatus()

    def getStatus(self) -> BinPositionMonitorStatus:
        config = self.config

        if config is None:
            try:
                config = loadBinPositionMonitorConfig()
            except ValueError as error:
                return BinPositionMonitorStatus(
                    enabled=False,
                    state="CONFIG_ERROR",
                    configuredMarkerIds=[],
                    visibleMarkerIds=[],
                    baselineConfigured=False,
                    automaticallyChangedMode=False,
                    currentMode=self.modeService.getMode().mode,
                    message=str(error),
                )

        return BinPositionMonitorStatus(
            enabled=config.enabled,
            state=self.state,
            configuredMarkerIds=list(config.markerIds),
            visibleMarkerIds=sorted(self.visiblePositions),
            baselineConfigured=bool(self.baseline),
            automaticallyChangedMode=(
                self.automaticModeRevision is not None
            ),
            currentMode=self.modeService.getMode().mode,
            lastFrameAt=self.lastFrameAt,
            message=self.message,
        )

    async def _pollLoop(self) -> None:
        config = self._requireConfig()

        while True:
            try:
                positions = await self._readPositions()
                await self.evaluatePositions(
                    positions,
                    monotonic(),
                )
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.state = "CAMERA_UNAVAILABLE"
                self.message = (
                    "SIDE 카메라 위치 감지를 일시적으로 수행할 수 없습니다. "
                    "현재 모드는 유지됩니다."
                )
                logger.warning(
                    "쓰레기통 위치 감지 실패: %s",
                    error,
                )

            await asyncio.sleep(config.pollSeconds)

    async def _readPositions(self) -> dict[int, tuple[float, float]]:
        await self.cameraManager.start()
        jpegBytes = await self.cameraManager.readFrame()

        if jpegBytes is None:
            raise RuntimeError("SIDE 카메라 프레임이 없습니다.")

        positions = await asyncio.to_thread(
            self.detector.detect,
            jpegBytes,
        )
        self.visiblePositions = positions
        self.lastFrameAt = datetime.now(timezone.utc).isoformat()
        return positions

    async def evaluatePositions(
        self,
        positions: dict[int, tuple[float, float]],
        now: float,
    ) -> None:
        config = self._requireConfig()

        if not self.baseline:
            self.state = "UNCALIBRATED"
            self.message = "원위치 기준이 등록되지 않았습니다."
            return

        self._discardAutomaticOwnershipAfterManualChange()
        allBinsHome = all(
            markerId in positions
            and self._distance(
                positions[markerId],
                self.baseline[markerId],
            ) <= config.positionToleranceRatio
            for markerId in config.markerIds
        )

        if allBinsHome:
            self.awaySince = None

            if self.manualOverrideActive:
                self.manualOverrideActive = False
                self.homeSince = None
                self.state = "MONITORING"
                self.message = (
                    "3개 쓰레기통이 원위치에 있습니다. "
                    "수동 모드는 그대로 유지합니다."
                )
                return

            if self.automaticModeRevision is None:
                self.homeSince = None
                self.state = "MONITORING"
                self.message = "3개 쓰레기통이 모두 원위치에 있습니다."
                return

            if self.homeSince is None:
                self.homeSince = now

            remainingSeconds = max(
                0,
                config.returnConfirmSeconds - (now - self.homeSince),
            )
            self.state = "RETURN_CONFIRMING"
            self.message = (
                f"원위치 복귀 확인 중입니다({remainingSeconds:.1f}초 남음)."
            )

            if now - self.homeSince >= config.returnConfirmSeconds:
                await self._changeModeAutomatically(Mode.manage)
                self.automaticModeRevision = None
                self.homeSince = None
                self.state = "MONITORING"
                self.message = "원위치 복귀를 확인해 관리 모드로 전환했습니다."

            return

        self.homeSince = None

        if self.manualOverrideActive:
            self.state = "MANUAL_OVERRIDE"
            self.message = (
                "사람이 선택한 모드를 유지합니다. "
                "모든 쓰레기통이 원위치로 돌아오면 자동 감지를 다시 준비합니다."
            )
            return

        if self.automaticModeRevision is not None:
            self.state = "AUTO_COLLECT"
            self.message = "쓰레기통 수거를 감지해 수거 모드를 유지하고 있습니다."
            return

        if self.awaySince is None:
            self.awaySince = now

        remainingSeconds = max(
            0,
            config.awayConfirmSeconds - (now - self.awaySince),
        )
        self.state = "AWAY_CONFIRMING"
        self.message = (
            f"쓰레기통 이동 여부 확인 중입니다({remainingSeconds:.1f}초 남음)."
        )

        if now - self.awaySince < config.awayConfirmSeconds:
            return

        if self.modeService.getMode().mode != Mode.manage:
            self.state = "MANUAL_COLLECT"
            self.message = "수동 수거 모드를 유지합니다. 자동 복귀하지 않습니다."
            return

        await self._changeModeAutomatically(Mode.collect)
        revision, _ = self.modeService.getChangeMetadata()
        self.automaticModeRevision = revision
        self.state = "AUTO_COLLECT"
        self.message = "쓰레기통 이동을 확인해 수거 모드로 전환했습니다."

    async def _changeModeAutomatically(self, mode: Mode) -> None:
        response = self.modeService.updateModeAutomatically(
            ModeUpdate(mode=mode)
        )
        await self.webSocketManager.broadcast(
            {
                "eventType": "MODE_CHANGED",
                "mode": response.mode.value,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def _discardAutomaticOwnershipAfterManualChange(self) -> None:
        if self.automaticModeRevision is None:
            return

        revision, changeSource = self.modeService.getChangeMetadata()

        if (
            revision != self.automaticModeRevision
            or changeSource != "AUTO_BIN_POSITION"
        ):
            self.automaticModeRevision = None
            self.homeSince = None
            self.manualOverrideActive = True
            self.message = "수동 모드 변경을 우선 적용했습니다."

    def _loadBaseline(self) -> None:
        config = self._requireConfig()

        if not config.baselinePath.exists():
            self.baseline = {}
            return

        try:
            payload = json.loads(
                config.baselinePath.read_text(encoding="utf-8")
            )
            positions = payload["positions"]
            self.baseline = {
                markerId: (
                    float(positions[str(markerId)]["x"]),
                    float(positions[str(markerId)]["y"]),
                )
                for markerId in config.markerIds
            }
        except (
            KeyError,
            TypeError,
            ValueError,
            OSError,
            json.JSONDecodeError,
        ) as error:
            self.baseline = {}
            logger.warning("쓰레기통 원위치 파일을 읽을 수 없습니다: %s", error)

    def _saveBaseline(self) -> None:
        config = self._requireConfig()
        config.baselinePath.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "markerIds": list(config.markerIds),
            "positions": {
                str(markerId): {
                    "x": position[0],
                    "y": position[1],
                }
                for markerId, position in self.baseline.items()
            },
            "calibratedAt": datetime.now(timezone.utc).isoformat(),
        }
        temporaryPath = config.baselinePath.with_suffix(".tmp")
        temporaryPath.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporaryPath.replace(config.baselinePath)

    def _requireConfig(self) -> BinPositionMonitorConfig:
        if self.config is None:
            self.config = loadBinPositionMonitorConfig()

        return self.config

    @staticmethod
    def _distance(
        current: tuple[float, float],
        baseline: tuple[float, float],
    ) -> float:
        return math.hypot(
            current[0] - baseline[0],
            current[1] - baseline[1],
        )


binPositionMonitorService = BinPositionMonitorService(
    cameraManager=cameraManagers[CameraId.ELEVSIDE.value],
    modeService=modeService,
    webSocketManager=webSocketManager,
)
