"""
MVP 시연용 임시 스텁 — GPU 서버 `inference` 실제 연동 전까지, debug/detection/의 스크립트로
"쓰레기 감지" 시작 신호와 "투척 완료+분류 결과" 종료 신호를 수동 HTTP 요청으로 보내 DB에
이벤트 데이터를 채워 넣기 위한 진입점. recordingService/mediaService/eventService를 그대로
호출한다. GPU `inference`→백엔드 신호 전달 방식(MQTT/HTTP/WS, architecture.md 기준 TBD)이
확정되면 진입점만 그쪽으로 바꾸고 아래 로직은 재사용하면 됨.
"""
from datetime import datetime, timezone

from schemas.event import (
    CameraId,
    BinType,
    DetectedClass,
    Event,
    EventCategory,
    EventCreate,
)
from services.eventService import eventService
from services.mediaService import mediaService
from services.recordingService import recordingService


class DetectionService:
    async def startDetection(
        self,
        cameraId: CameraId,
    ) -> str:
        return await recordingService.start(cameraId)

    async def stopDetection(
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
    ) -> Event | None:
        frames, _durationSeconds = await recordingService.stop(
            recordingId
        )

        imageFileId = await mediaService.saveClipAsGif(
            frames,
            cameraId,
            datetime.now(timezone.utc),
        )

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
            imageFileId=imageFileId,
            overflowDuration=overflowDuration,
            overflowThreshold=overflowThreshold,
            modelVersion=modelVersion,
        )

        return await eventService.createEvent(eventCreate)


detectionService = DetectionService()
