"""SIDE(ELEV-SIDE) 넘침 판정 — 로컬 백엔드가 MobileNet_V3_Small을 CPU(또는 GPU 있으면
자동 사용)로 직접 실행해서 판정한다(GPU 서버 미사용, architecture.md "탐지 파이프라인"
참고 — 원래 룰 베이스로 확정했던 결정을 재전환, 이유는 decisionLog.md 참고).

모델 자체는 models/trashoverflow/trashoverflowApi.py에 있던 독립 FastAPI 앱의 추론 로직을
그대로 가져와서, cameraManager(ELEV-SIDE) 프레임을 입력으로 쓰고 판정 결과는
binStateService.applyUpdate()로 넘겨 기존 BIN_STATES/EVENT/WS 파이프라인에 그대로 태운다
(POST /api/binStates의 in-process 버전 — 별도 HTTP 호출 없이 같은 프로세스 안에서 호출).

모델 가중치(bestSide.pt)나 roi.json이 없으면 조용히 비활성화된다 — 다른 카메라/기능에는
영향 없음(팀원이 가중치 파일을 models/trashoverflow/에 받아두면 다음 백엔드 재시작 시
자동으로 활성화됨).
"""
import asyncio
import json
import logging
import os
import time

import numpy as np

from schemas.binState import BinCurrentState, BinStateUpdate
from schemas.event import BinType, CameraId
from services.binStateService import binStateService
from streaming.cameraManager import cameraManagers

logger = logging.getLogger(__name__)

_modelDir = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "models", "trashoverflow"
)
modelPath = os.path.join(_modelDir, "bestSide.pt")
roiPath = os.path.join(_modelDir, "roi.json")
defaultImageSize = 224

overflowSeconds = 30.0
normalResetSeconds = 1.0
confidenceThreshold = 0.70
sampleIntervalSeconds = 1.0
cameraRetryIntervalSeconds = 10.0
modelVersion = "trashoverflow-mobilenet_v3_small-v1"

# 물리 통 4개(binId) 중 이 모델/roi.json이 실제로 보고 있는 통 하나 — roi.json이 현재
# 단일 ROI만 지원해서 우선 통 1개로 매핑(decisionLog.md 참고, 통 4개 각각 독립 판정하려면
# ROI를 나누고 모델을 통별로 돌려야 함 — TBD).
overflowBinId = os.getenv("OVERFLOW_BIN_ID", "bin-side-01")
overflowBinType = BinType(os.getenv("OVERFLOW_BIN_TYPE", BinType.NORMAL.value))


class OverflowDetectionService:
    def __init__(self):
        self.device = None
        self.model = None
        self.classes = None
        self.transform = None
        self.roi = None
        self.available = False
        self.task: asyncio.Task | None = None
        self.overflowStartTime: float | None = None
        self.normalStartTime: float | None = None
        self.finalOverflow = False
        self.overflowDuration = 0.0
        self.sessionId: str | None = None

    def _loadModel(self) -> bool:
        if not os.path.exists(modelPath):
            logger.warning(
                "SIDE overflow 모델 가중치가 없어 비활성화됨: %s "
                "(models/trashoverflow/에 bestSide.pt 배치 후 재시작하면 활성화)",
                modelPath,
            )
            return False

        if not os.path.exists(roiPath):
            logger.warning(
                "SIDE overflow ROI 설정이 없어 비활성화됨: %s", roiPath
            )
            return False

        import torch
        from torch import nn
        from torchvision import models, transforms

        with open(roiPath, "r", encoding="utf-8") as roiFile:
            self.roi = json.load(roiFile)

        for key in ("x1", "y1", "x2", "y2"):
            if key not in self.roi:
                logger.warning(
                    "SIDE overflow ROI 설정에 %s 누락, 비활성화됨: %s",
                    key,
                    roiPath,
                )
                return False

        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        checkpoint = torch.load(modelPath, map_location=self.device)

        model = models.mobilenet_v3_small(weights=None)
        model.classifier[3] = nn.Linear(
            model.classifier[3].in_features, 2
        )
        model.load_state_dict(checkpoint["model_state_dict"])
        model = model.to(self.device)
        model.eval()

        self.model = model
        self.classes = checkpoint.get(
            "classes", ["normal", "overflow"]
        )
        resolvedImageSize = checkpoint.get(
            "image_size", defaultImageSize
        )
        self.transform = transforms.Compose(
            [
                transforms.ToPILImage(),
                transforms.Resize(
                    (resolvedImageSize, resolvedImageSize)
                ),
                transforms.ToTensor(),
                transforms.Normalize(
                    mean=[0.485, 0.456, 0.406],
                    std=[0.229, 0.224, 0.225],
                ),
            ]
        )

        logger.info(
            "SIDE overflow 모델 로드 완료 (device=%s, classes=%s)",
            self.device,
            self.classes,
        )
        return True

    def _cropRoi(self, frame: np.ndarray) -> np.ndarray:
        height, width = frame.shape[:2]
        x1 = max(0, min(int(self.roi["x1"]), width))
        y1 = max(0, min(int(self.roi["y1"]), height))
        x2 = max(0, min(int(self.roi["x2"]), width))
        y2 = max(0, min(int(self.roi["y2"]), height))

        if x2 <= x1 or y2 <= y1:
            raise ValueError("ROI 좌표가 잘못되었습니다.")

        return frame[y1:y2, x1:x2]

    def _runInference(
        self, frame: np.ndarray
    ) -> tuple[str, float, bool]:
        import torch

        roiImage = self._cropRoi(frame)
        image = (
            self.transform(roiImage)
            .unsqueeze(0)
            .to(self.device)
        )

        with torch.no_grad():
            output = self.model(image)
            probabilities = torch.softmax(output, dim=1)[0]

        predictedIndex = torch.argmax(probabilities).item()
        confidence = probabilities[predictedIndex].item()
        predictedClass = self.classes[predictedIndex]

        frameOverflow = (
            predictedClass == "overflow"
            and confidence >= confidenceThreshold
        )

        return predictedClass, confidence, frameOverflow

    def _updateOverflowState(
        self, frameOverflow: bool, clockTime: float
    ) -> None:
        if frameOverflow:
            self.normalStartTime = None

            if self.overflowStartTime is None:
                self.overflowStartTime = clockTime

            self.overflowDuration = (
                clockTime - self.overflowStartTime
            )

            if self.overflowDuration >= overflowSeconds:
                self.finalOverflow = True
        else:
            if self.overflowStartTime is None:
                self.overflowDuration = 0.0
                self.finalOverflow = False
                self.normalStartTime = None
            else:
                if self.normalStartTime is None:
                    self.normalStartTime = clockTime

                if (
                    clockTime - self.normalStartTime
                    >= normalResetSeconds
                ):
                    self.overflowStartTime = None
                    self.normalStartTime = None
                    self.overflowDuration = 0.0
                    self.finalOverflow = False

    async def start(self) -> bool:
        if self.task is not None:
            return self.available

        try:
            self.available = await asyncio.to_thread(
                self._loadModel
            )
        except Exception:
            logger.exception(
                "SIDE overflow 모델 로드 실패 — 비활성화 상태로 진행"
            )
            self.available = False

        if not self.available:
            return False

        self.sessionId = f"side-{int(time.time())}"
        self.task = asyncio.create_task(self._loop())
        return True

    async def stop(self) -> None:
        if self.task is None:
            return

        self.task.cancel()

        try:
            await self.task
        except asyncio.CancelledError:
            pass

        self.task = None

    async def _loop(self) -> None:
        cameraManager = cameraManagers[CameraId.ELEVSIDE.value]
        previousFinalOverflow = False

        while True:
            sleepSeconds = sampleIntervalSeconds

            try:
                await cameraManager.start()
                frame = await cameraManager.readFrame()

                if frame is not None:
                    _predictedClass, confidence, frameOverflow = (
                        await asyncio.to_thread(
                            self._runInference, frame
                        )
                    )
                    self._updateOverflowState(
                        frameOverflow, time.monotonic()
                    )

                    if (
                        self.finalOverflow
                        != previousFinalOverflow
                    ):
                        await self._reportBinState(confidence)
                        previousFinalOverflow = (
                            self.finalOverflow
                        )
            except asyncio.CancelledError:
                raise
            except RuntimeError as error:
                logger.warning(
                    "SIDE overflow 카메라 연결 실패, %.0f초 후 재시도: %s",
                    cameraRetryIntervalSeconds,
                    error,
                )
                sleepSeconds = cameraRetryIntervalSeconds
            except Exception:
                logger.exception("SIDE overflow 추론 루프 오류")

            await asyncio.sleep(sleepSeconds)

    async def _reportBinState(self, confidence: float) -> None:
        update = BinStateUpdate(
            binId=overflowBinId,
            cameraId=CameraId.ELEVSIDE,
            binType=overflowBinType,
            sessionId=self.sessionId,
            currentState=(
                BinCurrentState.FULL
                if self.finalOverflow
                else BinCurrentState.NORMAL
            ),
            confidenceScore=confidence,
            overflowDuration=self.overflowDuration,
            overflowThreshold=overflowSeconds,
            detectionId=(
                f"{self.sessionId}-{int(time.monotonic() * 1000)}"
            ),
            modelVersion=modelVersion,
        )

        try:
            await binStateService.applyUpdate(update)
        except Exception:
            logger.exception(
                "SIDE overflow BIN_STATES 갱신 실패 (binId=%s)",
                overflowBinId,
            )


overflowDetectionService = OverflowDetectionService()
