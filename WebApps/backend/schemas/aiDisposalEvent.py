from pydantic import BaseModel, Field


class AiDisposalEvent(BaseModel):
    """models/trashdetect/tracking2.py의 create_disposal_event() 출력 그대로 받는 입력 스키마.

    필드명/값 체계가 우리 내부 EventCreate와 달라서(예: detectedClass="recyclables",
    result="correct") controllers/api.py에서 EventCreate로 변환한 뒤 기존
    eventService.createEventWithStatus 파이프라인을 그대로 재사용한다.
    """

    eventId: str = Field(min_length=1)
    trackId: int
    timestamp: str
    cameraId: str
    detectedClass: str
    binId: str
    result: str
    imagePath: str | None = None
