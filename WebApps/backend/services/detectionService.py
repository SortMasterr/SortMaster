"""
MVP 시연용 임시 스텁 — GPU 서버 `inference` 실제 연동 전까지, debug/detection/의 스크립트로
"쓰레기 감지" 시작 신호와 "투척 완료+분류 결과" 종료 신호를 수동 HTTP 요청으로 보내 DB에
이벤트 데이터를 채워 넣기 위한 진입점. recordingService/mediaService/eventService를 그대로
호출한다. GPU `inference`→백엔드 신호 전달 방식(MQTT/HTTP/WS, architecture.md 기준 TBD)이
확정되면 진입점만 그쪽으로 바꾸고 아래 로직은 재사용하면 됨.
"""
import asyncio
import logging
import time
import weakref
from dataclasses import dataclass
from datetime import datetime, timezone

from schemas.event import (
    CameraId,
    BinType,
    DetectedClass,
    Event,
    EventCategory,
    EventCreate,
)
from services.eventService import (
    EventCreationResult,
    eventService,
)
from services.errors import (
    RecordingCameraMismatchError,
    RecordingConflictError,
)
from services.mediaService import mediaService
from services.recordingService import recordingService


logger = logging.getLogger(__name__)
detectionResultRetentionSeconds = 120.0


@dataclass(frozen=True)
class RecordingBinding:
    cameraId: CameraId
    detectionId: str
    expiresAt: float


@dataclass(frozen=True)
class CompletedDetection:
    cameraId: CameraId
    detectionId: str
    result: EventCreationResult
    expiresAt: float


class DetectionService:
    def __init__(self):
        self.recordingBindings: dict[
            str,
            RecordingBinding,
        ] = {}
        self.completedDetections: dict[
            str,
            CompletedDetection,
        ] = {}
        self.processingLocks = weakref.WeakValueDictionary()
        self.processingLocksGuard = asyncio.Lock()

    async def startDetection(
        self,
        cameraId: CameraId,
    ) -> str:
        return await recordingService.start(cameraId)

    async def stopDetection(
        self,
        *args,
        **kwargs,
    ) -> Event | None:
        result = await self.stopDetectionWithStatus(
            *args,
            **kwargs,
        )
        return result.event

    async def stopDetectionWithStatus(
        self,
        recordingId: str,
        cameraId: CameraId,
        eventCategory: EventCategory,
        detectionId: str,
        trackingId: int | None,
        detectedClass: DetectedClass | None,
        binId: str,
        binType: BinType,
        isMisclassified: bool | None,
        confidenceScore: float | None,
        overflowDuration: float | None,
        overflowThreshold: float | None,
        modelVersion: str,
    ) -> EventCreationResult:
        eventCreate = EventCreate(
            cameraId=cameraId,
            eventCategory=eventCategory,
            detectionId=detectionId,
            trackingId=trackingId,
            detectedClass=detectedClass,
            binId=binId,
            binType=binType,
            isMisclassified=isMisclassified,
            confidenceScore=confidenceScore,
            imageFileId=None,
            overflowDuration=overflowDuration,
            overflowThreshold=overflowThreshold,
            modelVersion=modelVersion,
        )

        processingLock = await self._getProcessingLock(
            recordingId
        )

        async with processingLock:
            self._pruneDetectionState()
            completedDetection = self.completedDetections.get(
                recordingId
            )

            if completedDetection is not None:
                self._validateRecordingIdentity(
                    completedDetection.cameraId,
                    completedDetection.detectionId,
                    cameraId,
                    detectionId,
                )
                return completedDetection.result

            binding = self.recordingBindings.get(recordingId)

            if binding is not None:
                self._validateRecordingIdentity(
                    binding.cameraId,
                    binding.detectionId,
                    cameraId,
                    detectionId,
                )

            frames, _durationSeconds = await recordingService.stop(
                recordingId,
                expectedCameraId=cameraId,
            )

            if binding is None:
                self.recordingBindings[recordingId] = (
                    RecordingBinding(
                        cameraId=cameraId,
                        detectionId=detectionId,
                        expiresAt=(
                            time.monotonic()
                            + detectionResultRetentionSeconds
                        ),
                    )
                )

            imageFileId = await mediaService.saveClipAsGif(
                frames,
                cameraId,
                datetime.now(timezone.utc),
            )

            eventCreate = eventCreate.model_copy(
                update={"imageFileId": imageFileId}
            )

            try:
                result = await eventService.createEventWithStatus(
                    eventCreate
                )
            except Exception:
                try:
                    await mediaService.deleteClip(
                        imageFileId,
                        cameraId,
                    )
                except Exception:
                    logger.exception(
                        'GridFS compensation delete failed'
                    )
                raise

            if not result.created:
                try:
                    await mediaService.deleteClip(
                        imageFileId,
                        cameraId,
                    )
                except Exception:
                    logger.exception(
                        'GridFS compensation delete failed'
                    )

            expiresAt = (
                time.monotonic()
                + detectionResultRetentionSeconds
            )
            self.recordingBindings[recordingId] = RecordingBinding(
                cameraId=cameraId,
                detectionId=detectionId,
                expiresAt=expiresAt,
            )
            self.completedDetections[recordingId] = (
                CompletedDetection(
                    cameraId=cameraId,
                    detectionId=detectionId,
                    result=EventCreationResult(
                        event=result.event,
                        created=False,
                    ),
                    expiresAt=expiresAt,
                )
            )
            await recordingService.releaseStopped(recordingId)

            return result

    async def _getProcessingLock(
        self,
        recordingId: str,
    ) -> asyncio.Lock:
        async with self.processingLocksGuard:
            processingLock = self.processingLocks.get(recordingId)

            if processingLock is None:
                processingLock = asyncio.Lock()
                self.processingLocks[recordingId] = processingLock

            return processingLock

    def _pruneDetectionState(self) -> None:
        currentTime = time.monotonic()

        for stateByRecordingId in (
            self.recordingBindings,
            self.completedDetections,
        ):
            expiredRecordingIds = [
                recordingId
                for recordingId, state
                in stateByRecordingId.items()
                if state.expiresAt <= currentTime
            ]

            for recordingId in expiredRecordingIds:
                stateByRecordingId.pop(recordingId, None)

    @staticmethod
    def _validateRecordingIdentity(
        boundCameraId: CameraId,
        boundDetectionId: str,
        cameraId: CameraId,
        detectionId: str,
    ) -> None:
        if boundCameraId != cameraId:
            raise RecordingCameraMismatchError(
                "Recording camera does not match "
                "the start request."
            )

        if boundDetectionId != detectionId:
            raise RecordingConflictError(
                "recordingId가 이미 다른 detectionId에 "
                "사용되었습니다."
            )


detectionService = DetectionService()
