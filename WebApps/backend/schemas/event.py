from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, model_validator


class CameraId(str, Enum):
    ELEVTOP = "ELEV-TOP"
    ELEVSIDE = "ELEV-SIDE"
    REST4F01 = "REST-4F-01"


class EventCategory(str, Enum):
    MISCLASSIFICATION = "misclassification"
    OVERFLOW = "overflow"


class DetectedClass(str, Enum):
    GENERAL = "general"
    PAPER = "paper"
    PLASTIC = "plastic"
    COFFEE_CUP = "coffeeCup"
    MIXED = "mixed"
    UNCERTAIN = "uncertain"


class ActionTaken(str, Enum):
    LIGHT_AND_SOUND = "lightAndSound"
    SOUND_ONLY = "soundOnly"
    LIGHT_ONLY = "lightOnly"
    NOTIFICATION_ONLY = "notificationOnly"
    NONE = "none"


class EventCreate(BaseModel):
    cameraId: CameraId
    eventCategory: EventCategory
    detectedClass: DetectedClass | None = None
    isMisclassified: bool | None = None
    confidenceScore: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    # 녹화 파이프라인이 GIF를 GridFS에 업로드한 뒤 채워서 전달(선택). 외부 수동 호출 시 생략 가능.
    imageFileId: str | None = None

    @model_validator(mode="after")
    def checkMisclassificationFields(self):
        if self.eventCategory == EventCategory.MISCLASSIFICATION and (
            self.detectedClass is None
            or self.isMisclassified is None
            or self.confidenceScore is None
        ):
            raise ValueError(
                "misclassification 이벤트는 detectedClass/isMisclassified/"
                "confidenceScore가 모두 필요합니다."
            )

        return self


class Event(EventCreate):
    eventId: str
    timestamp: datetime
    actionTaken: ActionTaken
    notes: str | None = None