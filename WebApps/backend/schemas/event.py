from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field, field_validator, model_validator


_legacyBinIds = {
    "bin-side-01": "BIN-GENERAL",
    "bin-side-1": "BIN-GENERAL",
}


def normalizeBinId(value: str) -> str:
    return _legacyBinIds.get(value, value)


class CameraId(str, Enum):
    ELEVTOP = "ELEV-TOP"
    ELEVSIDE = "ELEV-SIDE"
    REST4F01 = "REST-4F-01"


class EventCategory(str, Enum):
    MISCLASSIFICATION = "misclassification"
    OVERFLOW = "overflow"


class DetectedClass(str, Enum):
    NORMAL = "normal"
    PAPER = "paper"
    RECYCLABLES = "recyclables"
    COFFEE_CUP = "coffeeCup"


class BinType(str, Enum):
    NORMAL = "normal"
    RECYCLABLES = "recyclables"
    COFFEE_CUP = "coffeeCup"
    PAPER = "paper"


class ActionTaken(str, Enum):
    LIGHT_AND_SOUND = "lightAndSound"
    SOUND_ONLY = "soundOnly"
    LIGHT_ONLY = "lightOnly"
    NOTIFICATION_ONLY = "notificationOnly"
    NONE = "none"


class EventCreate(BaseModel):
    cameraId: CameraId
    eventCategory: EventCategory
    detectionId: str = Field(min_length=1)
    trackingId: int | None = Field(default=None, ge=0)
    detectedClass: DetectedClass | None = None
    binId: str = Field(min_length=1)
    binType: BinType
    isMisclassified: bool | None = None
    confidenceScore: float | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    # 녹화 파이프라인이 GIF를 GridFS에 업로드한 뒤 채워서 전달(선택). 외부 수동 호출 시 생략 가능.
    imageFileId: str | None = None
    overflowDuration: float | None = Field(default=None, ge=0.0)
    overflowThreshold: float | None = Field(default=None, ge=0.0)
    modelVersion: str = Field(min_length=1)

    @field_validator("binId", mode="before")
    @classmethod
    def normalizeLegacyBinId(cls, value):
        return normalizeBinId(value) if isinstance(value, str) else value

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

        if (
            self.eventCategory == EventCategory.MISCLASSIFICATION
            and self.cameraId != CameraId.ELEVTOP
        ):
            raise ValueError(
                "misclassification 이벤트는 ELEV-TOP 카메라에서만 생성할 수 있습니다."
            )

        if self.eventCategory == EventCategory.OVERFLOW:
            if self.cameraId != CameraId.ELEVSIDE:
                raise ValueError(
                    "overflow 이벤트는 ELEV-SIDE 카메라에서만 생성할 수 있습니다."
                )

            if (
                self.detectedClass is not None
                or self.isMisclassified is not None
                or self.confidenceScore is not None
            ):
                raise ValueError(
                    "overflow 이벤트에는 분류 결과 필드를 사용할 수 없습니다."
                )

        return self


class Event(EventCreate):
    eventId: str
    timestamp: datetime
    actionTaken: ActionTaken
    acknowledgedAt: datetime | None = None
    notes: str | None = None


class EventAcknowledgementBatch(BaseModel):
    eventIds: list[str] = Field(min_length=1, max_length=500)
