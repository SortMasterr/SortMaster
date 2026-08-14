"""
실제 YOLO26 모델(젯슨 엣지) 완성 전까지, "쓰레기 감지" 시작 신호와 "투척 완료+분류
결과" 종료 신호를 API로 직접 받아 recordingService/mediaService/eventService를
그대로 호출하는 임시 스텁. 엣지→백엔드 신호 전달 방식(MQTT/HTTP/WS, architecture.md
기준 TBD)이 확정되면 진입점만 그쪽으로 바꾸고 아래 로직은 재사용하면 됨.
"""
from datetime import datetime, timezone

from schemas.event import (
    CameraId,
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
        detectedClass: DetectedClass,
        isMisclassified: bool,
        confidenceScore: float,
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
            eventCategory=EventCategory.MISCLASSIFICATION,
            detectedClass=detectedClass,
            isMisclassified=isMisclassified,
            confidenceScore=confidenceScore,
            imageFileId=imageFileId,
        )

        return await eventService.createEvent(eventCreate)


detectionService = DetectionService()
